"""
BIRDSΣY3 — Area of Interest (AOI) & Geospatial Retrieval Engine
Handles WGS84 (EPSG:4326) <-> UTM 45N (EPSG:32645) transformations,
spatial catalog intersection indexing, and AOI-directed multi-temporal queries.
"""

import os
import json
import logging
import rasterio.warp
import numpy as np

logger = logging.getLogger(__name__)

class AOIEngine:
    def __init__(self, catalog_path: str = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if catalog_path is None:
            catalog_path = os.path.join(base_dir, "data", "tiles_catalog.json")
            if not os.path.exists(catalog_path):
                catalog_path = os.path.join(os.path.dirname(base_dir), "data", "tiles_catalog.json")

        self.catalog_path = catalog_path
        self.tiles = []
        self.tiles_by_id = {}
        
        # Spatial arrays for ultra-fast vectorized bounding box filtering
        self.utm_bounds = None # (N, 4): [minx, miny, maxx, maxy]
        self.wgs_bounds = None # (N, 4): [min_lon, min_lat, max_lon, max_lat]
        self.tile_ids = []
        
        self._load_and_index()

    def _load_and_index(self):
        if not os.path.exists(self.catalog_path):
            logger.warning(f"AOIEngine: Catalog file not found at {self.catalog_path}")
            return

        with open(self.catalog_path, "r", encoding="utf-8") as f:
            self.tiles = json.load(f)

        if not self.tiles:
            return

        min_xs = []
        min_ys = []
        max_xs = []
        max_ys = []

        for t in self.tiles:
            tid = t["tile_id"]
            self.tiles_by_id[tid] = t
            self.tile_ids.append(tid)
            bbox = t["bbox"]
            min_xs.append(bbox[0])
            min_ys.append(bbox[1])
            max_xs.append(bbox[2])
            max_ys.append(bbox[3])

        self.utm_bounds = np.column_stack([min_xs, min_ys, max_xs, max_ys])

        # Batch transform all tile corners from EPSG:32645 to WGS84 (EPSG:4326)
        min_lons, min_lats = rasterio.warp.transform("EPSG:32645", "EPSG:4326", min_xs, min_ys)
        max_lons, max_lats = rasterio.warp.transform("EPSG:32645", "EPSG:4326", max_xs, max_ys)

        self.wgs_bounds = np.column_stack([min_lons, min_lats, max_lons, max_lats])

        # Attach precalculated WGS84 bounds and centers to catalog objects
        for i, t in enumerate(self.tiles):
            t["wgs_bbox"] = [
                round(float(min_lons[i]), 6),
                round(float(min_lats[i]), 6),
                round(float(max_lons[i]), 6),
                round(float(max_lats[i]), 6)
            ]
            t["center_lon"] = round((min_lons[i] + max_lons[i]) / 2.0, 6)
            t["center_lat"] = round((min_lats[i] + max_lats[i]) / 2.0, 6)

        logger.info(f"AOIEngine: Successfully indexed {len(self.tiles)} tiles in UTM 45N and WGS84.")

    def transform_wgs_to_utm(self, lons, lats):
        """Converts lists of lons, lats to UTM 45N xs, ys."""
        xs, ys = rasterio.warp.transform("EPSG:4326", "EPSG:32645", lons, lats)
        return xs, ys

    def transform_utm_to_wgs(self, xs, ys):
        """Converts lists of UTM xs, ys to WGS84 lons, lats."""
        lons, lats = rasterio.warp.transform("EPSG:32645", "EPSG:4326", xs, ys)
        return lons, lats

    def query_by_bbox(self, min_lon: float, min_lat: float, max_lon: float, max_lat: float, limit: int = 50):
        """
        Finds tiles in the catalog that intersect the specified WGS84 bounding box.
        """
        if self.utm_bounds is None or len(self.tiles) == 0:
            return []

        # Convert query box to UTM 45N
        xs, ys = self.transform_wgs_to_utm([min_lon, max_lon], [min_lat, max_lat])
        q_minx, q_maxx = min(xs), max(xs)
        q_miny, q_maxy = min(ys), max(ys)

        # Standard AABB overlap condition:
        # overlap_x = max(minx_a, minx_b) < min(maxx_a, maxx_b)
        # overlap_y = max(miny_a, miny_b) < min(maxy_a, maxy_b)
        x1 = np.maximum(q_minx, self.utm_bounds[:, 0])
        x2 = np.minimum(q_maxx, self.utm_bounds[:, 2])
        y1 = np.maximum(q_miny, self.utm_bounds[:, 1])
        y2 = np.minimum(q_maxy, self.utm_bounds[:, 3])

        overlap_w = np.maximum(0.0, x2 - x1)
        overlap_h = np.maximum(0.0, y2 - y1)
        overlap_area = overlap_w * overlap_h

        intersect_indices = np.where(overlap_area > 0)[0]
        
        # Sort by overlap area descending
        sorted_indices = intersect_indices[np.argsort(-overlap_area[intersect_indices])]
        selected = sorted_indices[:limit]

        results = []
        for idx in selected:
            t = self.tiles[idx]
            tile_area = (self.utm_bounds[idx, 2] - self.utm_bounds[idx, 0]) * (self.utm_bounds[idx, 3] - self.utm_bounds[idx, 1])
            overlap_pct = round(float((overlap_area[idx] / tile_area) * 100), 2)
            results.append({
                "tile_id": t["tile_id"],
                "overlap_pct": overlap_pct,
                "overlap_area_sqm": round(float(overlap_area[idx]), 1),
                "wgs_bbox": t.get("wgs_bbox"),
                "utm_bbox": t.get("bbox"),
                "center_lat": t.get("center_lat"),
                "center_lon": t.get("center_lon"),
                "valid_ratio": t.get("valid_ratio", 1.0),
                "source_scene": t.get("source_scene", ""),
                "acquisition_datetime": t.get("acquisition_datetime", "2024-02-23T04:38:09Z")
            })

        return results

    def query_by_polygon(self, coordinates: list, limit: int = 50):
        """
        Finds tiles intersecting a polygon defined by WGS84 coordinate pairs [[lon, lat], ...].
        """
        if not coordinates or len(coordinates) < 3:
            return []

        lons = [pt[0] for pt in coordinates]
        lats = [pt[1] for pt in coordinates]

        poly_min_lon, poly_max_lon = min(lons), max(lons)
        poly_min_lat, poly_max_lat = min(lats), max(lats)

        # 1. First coarse filter using the polygon bounding box
        candidate_tiles = self.query_by_bbox(poly_min_lon, poly_min_lat, poly_max_lon, poly_max_lat, limit=len(self.tiles))
        if not candidate_tiles:
            return []

        # 2. Refine intersection using point-in-polygon on tile centers and corners
        poly_xs, poly_ys = self.transform_wgs_to_utm(lons, lats)
        poly_points = list(zip(poly_xs, poly_ys))

        def point_in_poly(x, y, poly):
            n = len(poly)
            inside = False
            p1x, p1y = poly[0]
            for i in range(1, n + 1):
                p2x, p2y = poly[i % n]
                if y > min(p1y, p2y):
                    if y <= max(p1y, p2y):
                        if x <= max(p1x, p2x):
                            if p1y != p2y:
                                xints = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                            if p1x == p2x or x <= xints:
                                inside = not inside
                p1x, p1y = p2x, p2y
            return inside

        refined = []
        for cand in candidate_tiles:
            tid = cand["tile_id"]
            orig = self.tiles_by_id.get(tid)
            if not orig:
                continue
            bbox = orig["bbox"]
            center_x = (bbox[0] + bbox[2]) / 2.0
            center_y = (bbox[1] + bbox[3]) / 2.0

            # Test center or any corner
            corners = [
                (center_x, center_y),
                (bbox[0], bbox[1]),
                (bbox[2], bbox[1]),
                (bbox[2], bbox[3]),
                (bbox[0], bbox[3])
            ]

            is_inside = any(point_in_poly(cx, cy, poly_points) for cx, cy in corners)
            
            # Also check if any polygon vertex is inside this tile
            if not is_inside:
                for px, py in poly_points:
                    if bbox[0] <= px <= bbox[2] and bbox[1] <= py <= bbox[3]:
                        is_inside = True
                        break

            if is_inside:
                refined.append(cand)
                if len(refined) >= limit:
                    break

        return refined or candidate_tiles[:limit]

    def get_footprints_geojson(self, limit: int = None):
        """
        Returns GeoJSON FeatureCollection of tile boundaries in WGS84 for direct map rendering.
        """
        features = []
        selected_tiles = self.tiles[:limit] if limit else self.tiles

        for t in selected_tiles:
            w_box = t.get("wgs_bbox")
            if not w_box:
                continue
            min_lon, min_lat, max_lon, max_lat = w_box
            coords = [[
                [min_lon, min_lat],
                [max_lon, min_lat],
                [max_lon, max_lat],
                [min_lon, max_lat],
                [min_lon, min_lat]
            ]]
            features.append({
                "type": "Feature",
                "id": t["tile_id"],
                "geometry": {
                    "type": "Polygon",
                    "coordinates": coords
                },
                "properties": {
                    "tile_id": t["tile_id"],
                    "valid_ratio": round(float(t.get("valid_ratio", 1.0)), 3),
                    "center_lat": t.get("center_lat"),
                    "center_lon": t.get("center_lon"),
                    "resolution": t.get("resolution", 10.0),
                    "crs": t.get("crs", "EPSG:32645")
                }
            })

        return {
            "type": "FeatureCollection",
            "features": features
        }

    def analyze_aoi(self, bbox_wgs84: list = None, tile_id: str = None):
        """
        Runs multi-temporal change analysis over the selected AOI.
        """
        from services import get_change_engine
        engine = get_change_engine()

        target_tile = None
        if tile_id and tile_id in self.tiles_by_id:
            target_tile = self.tiles_by_id[tile_id]
        elif bbox_wgs84 and len(bbox_wgs84) == 4:
            matches = self.query_by_bbox(bbox_wgs84[0], bbox_wgs84[1], bbox_wgs84[2], bbox_wgs84[3], limit=1)
            if matches:
                target_tile = self.tiles_by_id[matches[0]["tile_id"]]

        if not target_tile:
            # Fallback to the first indexed tile
            target_tile = self.tiles[0]

        bbox_utm = target_tile["bbox"]
        res = engine.analyze_tri_epoch_by_bbox(bbox_utm)

        # Convert PIL images to Base64
        import io
        import base64
        def pil_to_b64(img):
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")

        return {
            "tile_id": target_tile["tile_id"],
            "target_utm_bbox": bbox_utm,
            "target_wgs_bbox": target_tile.get("wgs_bbox"),
            "center": {
                "lat": target_tile.get("center_lat"),
                "lon": target_tile.get("center_lon")
            },
            "images": {
                "epoch_2024": pil_to_b64(res["rgb_2024"]),
                "epoch_2025": pil_to_b64(res["rgb_2025"]),
                "epoch_2026": pil_to_b64(res["rgb_2026"]),
                "change_mask": pil_to_b64(res["change_rgb_cumulative"])
            },
            "stats_cumulative": res.get("stats_cumulative", {}),
            "stats_24_25": res.get("stats_24_25", {}),
            "stats_25_26": res.get("stats_25_26", {}),
            "time_series": res.get("time_series", {})
        }
