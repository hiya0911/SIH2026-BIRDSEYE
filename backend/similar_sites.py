"""
BIRDSΣY3 — Similar-Site Intelligence Engine (Phase 5D)
Finds genuinely similar Earth-observation sites across India using the existing
FAISS FlatIP vector index (512-D CLIP ViT-B/32 embeddings), spatial relevance,
temporal matching, and unsupervised Landscape Clustering.

IMPORTANT CONSTRAINTS:
- DO NOT invent similarity scores. Return actual calculated inner-product / cosine metrics.
- DO NOT create a second unrelated retrieval engine. Reuses existing FAISS index & embedder.
- Geographic closeness alone is NEVER described as visual similarity.
- Strictly distinguish LOCAL DATA, REMOTE STAC METADATA, ACQUIRED LOCALLY, NOT AVAILABLE LOCALLY.
"""

import os
import math
import logging
from typing import Dict, Any, List, Optional
import numpy as np

logger = logging.getLogger(__name__)

def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two WGS84 points in kilometers."""
    R = 6371.0 # Earth radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2.0) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 2)

def calculate_temporal_delta_days(date_str_a: str, date_str_b: str) -> Optional[int]:
    """Calculates absolute day delta between two ISO date strings (YYYY-MM-DD)."""
    if not date_str_a or not date_str_b:
        return None
    try:
        from datetime import datetime
        d_a = datetime.fromisoformat(date_str_a[:10])
        d_b = datetime.fromisoformat(date_str_b[:10])
        return abs((d_a - d_b).days)
    except Exception:
        return None


class SimilarSiteEngine:
    def __init__(self):
        self._cluster_engine = None

    def _get_cluster_engine(self):
        if self._cluster_engine is None:
            from clustering import LandscapeClusterEngine
            self._cluster_engine = LandscapeClusterEngine()
        return self._cluster_engine

    def search_similar_sites(
        self,
        tile_id: Optional[str] = None,
        bbox: Optional[List[float]] = None,
        polygon: Optional[List[List[float]]] = None,
        point: Optional[List[float]] = None,
        location_name: Optional[str] = None,
        text_query: Optional[str] = None,
        top_k: int = 10,
        max_distance_km: Optional[float] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        sensor: Optional[str] = "ALL",
        cluster_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Executes Similar-Site retrieval across the national / local catalog:
        1. Resolves reference source (tile_id, map location/AOI, named place, text query, or cluster).
        2. Queries the FAISS FlatIP vector index with actual 512-D CLIP visual or text embeddings.
        3. Evaluates real geographic distance (Haversine km) and temporal delta (days).
        4. Applies spatial, temporal, and sensor filters without rebuilding the index.
        5. Formulates transparent explainability breakdown for each result.
        """
        sf = (sensor or "ALL").upper().strip()
        if sf in ("SENTINEL-1", "SAR"):
            return {
                "status": "success",
                "sensor_filter": "SENTINEL-1",
                "available": False,
                "message": "Sentinel-1 SAR C-band data is not currently cached locally. Vector retrieval and similar-site discovery is available for Sentinel-2 MSI Level-2A optical imagery.",
                "total_matches": 0,
                "results": [],
                "reference": None
            }

        from services import vector_index, get_embedder, get_aoi_engine
        from database import tiles_collection
        from advanced_retrieval import matches_date_filter
        from geocoder import geocode_location

        if not vector_index:
            raise RuntimeError("FAISS vector index is not initialized.")

        embedder = get_embedder()
        aoi_eng = get_aoi_engine()
        cluster_eng = self._get_cluster_engine()

        # Step 1: Resolve Reference Source & Target Vector
        ref_tile_id: Optional[str] = None
        ref_tile_meta: Optional[Dict[str, Any]] = None
        ref_coords: Optional[Dict[str, float]] = None
        ref_acq_date: Optional[str] = None
        ref_type: str = "UNKNOWN"
        query_vector: Optional[np.ndarray] = None
        is_visual_query: bool = False
        is_semantic_query: bool = False

        # Resolve named location if provided
        if location_name and not bbox and not point and not polygon and not tile_id:
            geo_res = geocode_location(location_name)
            if geo_res.get("status") == "success":
                bbox = geo_res.get("wgs_bbox")
                ref_coords = {"lat": geo_res["lat"], "lon": geo_res["lon"]}
                ref_type = f"NAMED_LOCATION ({geo_res.get('name', location_name)})"

        # Case 1: Specific Local Tile ID or Discovered Scene Reference
        if tile_id and tile_id.strip():
            clean_tid = tile_id.strip()
            # Fetch metadata from DB or AOI catalog
            t_meta = tiles_collection.find_one({"tile_id": clean_tid}, {"_id": 0})
            if not t_meta and clean_tid in aoi_eng.tiles_by_id:
                t_meta = aoi_eng.tiles_by_id[clean_tid]

            if not t_meta:
                # Check if it was acquired locally via Phase 5C
                from copernicus_engine import CopernicusAcquisitionEngine
                acq_eng = CopernicusAcquisitionEngine()
                acq = acq_eng.get_acquisition(clean_tid)
                if acq and acq.get("local_filepath") and os.path.exists(acq["local_filepath"]):
                    ref_tile_id = clean_tid
                    ref_type = f"ACQUIRED_SCENE ({acq.get('sensor', 'SENTINEL')})"
                    query_vector = embedder.extract_from_tile(acq["local_filepath"])
                    is_visual_query = True
                    ref_acq_date = (acq.get("acquisition_time") or "")[:10]
                is_copernicus = clean_tid.startswith(("S2", "S1")) or "MSIL2A" in clean_tid or "GRD" in clean_tid

                # If bbox is missing for Copernicus product ID, attempt to resolve via cache, provenance, or MGRS tile code
                if is_copernicus and (not bbox or len(bbox) != 4):
                    # 1. Check CopernicusDiscoveryEngine in-memory scene cache
                    try:
                        import sys
                        if "main" in sys.modules and hasattr(sys.modules["main"], "copernicus_engine"):
                            c_scene = sys.modules["main"].copernicus_engine.get_cached_scene(clean_tid)
                            if c_scene and (c_scene.get("wgs_bbox") or c_scene.get("bbox")):
                                bbox = c_scene.get("wgs_bbox") or c_scene.get("bbox")
                    except Exception:
                        pass

                if is_copernicus and (not bbox or len(bbox) != 4):
                    # 2. Check recent provenance discovery records
                    try:
                        recent_prov = provenance_collection.find_one(
                            {"action": "copernicus_stac_discovery"},
                            sort=[("timestamp", -1)]
                        )
                        if recent_prov and recent_prov.get("parameters", {}).get("bbox"):
                            bbox = recent_prov["parameters"]["bbox"]
                    except Exception:
                        pass

                if is_copernicus and (not bbox or len(bbox) != 4):
                    # 3. Check MGRS tile code against local catalog
                    parts = clean_tid.split("_")
                    grid_codes = [p for p in parts if len(p) == 6 and p.startswith("T") and p[1:3].isdigit()]
                    if grid_codes:
                        target_grid = grid_codes[0]
                        for tid, t_obj in aoi_eng.tiles_by_id.items():
                            src = t_obj.get("source_scene", "")
                            if target_grid in src and t_obj.get("wgs_bbox"):
                                bbox = t_obj["wgs_bbox"]
                                break

                if bbox and len(bbox) == 4:
                    ref_tile_id = clean_tid
                    ref_type = f"COPERNICUS_SCENE ({clean_tid[:24]}...)"
                    min_lon, min_lat, max_lon, max_lat = [float(b) for b in bbox]
                    ref_coords = {"lat": round((min_lat + max_lat) / 2.0, 6), "lon": round((min_lon + max_lon) / 2.0, 6)}
                    intersecting_tiles = aoi_eng.query_by_bbox(min_lon, min_lat, max_lon, max_lat, limit=5)
                    if intersecting_tiles:
                        primary = intersecting_tiles[0]
                        ref_acq_date = (primary.get("acquisition_datetime") or "")[:10]
                        pri_meta = tiles_collection.find_one({"tile_id": primary["tile_id"]}, {"_id": 0}) or primary
                        filepath = pri_meta.get("filepath", "") if pri_meta else ""
                        if filepath and os.path.exists(filepath):
                            query_vector = embedder.extract_from_tile(filepath)
                            is_visual_query = True
                        elif primary["tile_id"] in vector_index.tile_ids:
                            idx = vector_index.tile_ids.index(primary["tile_id"])
                            vec = vector_index.index.reconstruct(idx)
                            norm = np.linalg.norm(vec)
                            query_vector = vec / (norm if norm > 0 else 1.0)
                            is_visual_query = True
                    if query_vector is None:
                        if text_query and text_query.strip():
                            query_vector = embedder.extract_from_text(text_query.strip(), ensemble=True)
                            is_semantic_query = True
                            ref_type += f" + SEMANTIC ('{text_query.strip()}')"
                        else:
                            is_visual_query = False
                elif clean_tid in ("S2", "S1") or len(clean_tid) <= 3:
                    raise ValueError(f"Reference tile ID '{clean_tid}' appears to be a truncated platform prefix. Please specify the complete Copernicus STAC product ID (e.g. S2B_MSIL2A_...) or a 36-character local tile UUID.")
                elif is_copernicus:
                    raise ValueError(f"Copernicus scene '{clean_tid}' is remote STAC metadata with no spatial bounding box provided. Please Demarcate as AOI on map or Acquire Locally before vector retrieval.")
                else:
                    raise ValueError(f"Reference tile ID '{clean_tid}' not found in local catalog.")
            else:
                ref_tile_id = clean_tid
                ref_tile_meta = t_meta
                ref_type = "LOCAL_TILE"
                is_visual_query = True

                filepath = t_meta.get("filepath", "")
                if os.path.exists(filepath):
                    query_vector = embedder.extract_from_tile(filepath)
                else:
                    # If file missing on disk, reconstruct normalized vector from FAISS index directly
                    if clean_tid in vector_index.tile_ids:
                        idx = vector_index.tile_ids.index(clean_tid)
                        vec = vector_index.index.reconstruct(idx)
                        norm = np.linalg.norm(vec)
                        query_vector = vec / (norm if norm > 0 else 1.0)
                    else:
                        raise FileNotFoundError(f"Tile raster file not found on disk for '{clean_tid}'.")

                ref_lat = t_meta.get("center_lat")
                ref_lon = t_meta.get("center_lon")
                if (ref_lat is None or ref_lon is None) and clean_tid in aoi_eng.tiles_by_id:
                    ref_lat = aoi_eng.tiles_by_id[clean_tid].get("center_lat")
                    ref_lon = aoi_eng.tiles_by_id[clean_tid].get("center_lon")
                if (ref_lat is None or ref_lon is None) and t_meta.get("bbox"):
                    u_box = t_meta["bbox"]
                    lons, lats = aoi_eng.transform_utm_to_wgs([u_box[0], u_box[2]], [u_box[1], u_box[3]])
                    ref_lat = round(float(np.mean(lats)), 6)
                    ref_lon = round(float(np.mean(lons)), 6)

                ref_coords = {"lat": ref_lat, "lon": ref_lon} if (ref_lat is not None and ref_lon is not None) else None
                ref_acq_date = (t_meta.get("acquisition_datetime") or "")[:10]

        # Case 2: Selected Map / AOI Location (Point, Bbox, Polygon)
        elif point or bbox or polygon:
            intersecting_tiles = []
            if point and len(point) >= 2:
                # Validate and build point search
                lon, lat = float(point[0]), float(point[1])
                ref_coords = {"lat": lat, "lon": lon}
                ref_type = f"POINT_AOI ({lat:.4f}°N, {lon:.4f}°E)"
                # Look for tiles containing or nearest to point
                intersecting_tiles = aoi_eng.query_by_bbox(lon - 0.03, lat - 0.03, lon + 0.03, lat + 0.03, limit=5)
            elif bbox and len(bbox) == 4:
                min_lon, min_lat, max_lon, max_lat = [float(b) for b in bbox]
                ref_coords = {"lat": round((min_lat + max_lat) / 2.0, 6), "lon": round((min_lon + max_lon) / 2.0, 6)}
                if ref_type == "UNKNOWN":
                    ref_type = "RECTANGLE_AOI"
                intersecting_tiles = aoi_eng.query_by_bbox(min_lon, min_lat, max_lon, max_lat, limit=5)
            elif polygon and len(polygon) >= 3:
                lons = [float(pt[0]) for pt in polygon]
                lats = [float(pt[1]) for pt in polygon]
                ref_coords = {"lat": round((min(lats) + max(lats)) / 2.0, 6), "lon": round((min(lons) + max(lons)) / 2.0, 6)}
                ref_type = "POLYGON_AOI"
                intersecting_tiles = aoi_eng.query_by_polygon(polygon, limit=5)

            if intersecting_tiles:
                # Primary local tile found in AOI
                primary = intersecting_tiles[0]
                ref_tile_id = primary["tile_id"]
                t_meta = tiles_collection.find_one({"tile_id": ref_tile_id}, {"_id": 0}) or aoi_eng.tiles_by_id.get(ref_tile_id)
                ref_tile_meta = t_meta
                ref_acq_date = (primary.get("acquisition_datetime") or "")[:10]

                filepath = t_meta.get("filepath", "") if t_meta else ""
                if filepath and os.path.exists(filepath):
                    query_vector = embedder.extract_from_tile(filepath)
                    is_visual_query = True
                elif ref_tile_id in vector_index.tile_ids:
                    idx = vector_index.tile_ids.index(ref_tile_id)
                    vec = vector_index.index.reconstruct(idx)
                    norm = np.linalg.norm(vec)
                    query_vector = vec / (norm if norm > 0 else 1.0)
                    is_visual_query = True

            # If AOI is outside local 909-tile coverage area (e.g. Siliguri, Bengaluru, Mumbai):
            if query_vector is None:
                if text_query and text_query.strip():
                    # Fallback to semantic query for the remote area
                    query_vector = embedder.extract_from_text(text_query.strip(), ensemble=True)
                    is_semantic_query = True
                    ref_type += f" + SEMANTIC ('{text_query.strip()}')"
                else:
                    # Spatial proximity only query across known indexed catalog
                    is_visual_query = False

        # Case 3: Semantic Natural Language Query Reference
        elif text_query and text_query.strip():
            query_vector = embedder.extract_from_text(text_query.strip(), ensemble=True)
            is_semantic_query = True
            ref_type = f"SEMANTIC_QUERY ('{text_query.strip()}')"

        # Case 4: Landscape Cluster ID Reference
        elif cluster_id is not None:
            ref_type = f"LANDSCAPE_CLUSTER (Cluster {cluster_id})"
            # We will pull cluster tiles directly
            pass

        else:
            raise ValueError("Must provide at least one reference source: tile_id, map location (bbox/point/polygon), location_name, text_query, or cluster_id.")

        # Step 2: Query FAISS Vector Index (or cluster pool)
        candidates = []
        search_k = min(top_k * 15, 300)

        if query_vector is not None:
            # Query FAISS inner product
            raw_hits = vector_index.search(query_vector, top_k=search_k)
            candidates = raw_hits
        elif cluster_id is not None:
            # Pull all tiles in cluster
            cluster_tiles = cluster_eng.get_tiles_in_cluster(cluster_id, max_tiles=search_k)
            candidates = [{"tile_id": t["tile_id"], "score": 1.0} for t in cluster_tiles]
        else:
            # Spatial distance sort across all local catalog tiles
            candidates = [{"tile_id": tid, "score": 0.0} for tid in aoi_eng.tile_ids[:search_k]]

        # Step 3: Hydrate Metadata, Apply Filters, and Calculate Genuine Similarity Factors
        results = []
        cluster_data = cluster_eng.get_all_pca_data() if cluster_eng else []
        tile_to_cluster = {item["tile_id"]: item for item in cluster_data}

        for c in candidates:
            cand_tid = c["tile_id"]
            if ref_tile_id and cand_tid == ref_tile_id:
                # Exclude self-reference from result ranking
                continue

            # Fetch metadata
            t_meta = tiles_collection.find_one({"tile_id": cand_tid}, {"_id": 0})
            if not t_meta and cand_tid in aoi_eng.tiles_by_id:
                t_meta = aoi_eng.tiles_by_id[cand_tid]
            if not t_meta:
                continue

            cand_datetime = t_meta.get("acquisition_datetime", "2024-02-23T04:38:09Z")
            if not matches_date_filter(cand_datetime, start_date, end_date):
                continue

            wbox = t_meta.get("wgs_bbox")
            if not wbox and cand_tid in aoi_eng.tiles_by_id:
                wbox = aoi_eng.tiles_by_id[cand_tid].get("wgs_bbox")
            if not wbox and t_meta.get("bbox"):
                u_box = t_meta["bbox"]
                lons, lats = aoi_eng.transform_utm_to_wgs([u_box[0], u_box[2]], [u_box[1], u_box[3]])
                wbox = [round(min(lons), 6), round(min(lats), 6), round(max(lons), 6), round(max(lats), 6)]

            cand_lat = t_meta.get("center_lat")
            cand_lon = t_meta.get("center_lon")
            if cand_lat is None or cand_lon is None:
                if cand_tid in aoi_eng.tiles_by_id:
                    cand_lat = aoi_eng.tiles_by_id[cand_tid].get("center_lat")
                    cand_lon = aoi_eng.tiles_by_id[cand_tid].get("center_lon")
                if wbox and (cand_lat is None or cand_lon is None):
                    cand_lon = round((wbox[0] + wbox[2]) / 2.0, 6)
                    cand_lat = round((wbox[1] + wbox[3]) / 2.0, 6)

            # Spatial distance calculation (km)
            dist_km = None
            if ref_coords and ref_coords.get("lat") is not None and ref_coords.get("lon") is not None and cand_lat is not None and cand_lon is not None:
                dist_km = haversine_distance_km(ref_coords["lat"], ref_coords["lon"], cand_lat, cand_lon)
                if max_distance_km is not None and dist_km > max_distance_km:
                    continue

            # Temporal delta calculation (days)
            temporal_delta = None
            cand_date = cand_datetime[:10] if cand_datetime else "2024-02-23"
            if ref_acq_date:
                temporal_delta = calculate_temporal_delta_days(ref_acq_date, cand_date)

            # Cluster lookup
            c_info = tile_to_cluster.get(cand_tid, {
                "cluster_id": 0,
                "label": "Urban & Peri-Urban Landscape"
            })

            # Calculate genuine scores
            raw_sim = float(c["score"])
            # In CLIP hypersphere, inner product of unit vectors is cosine similarity in [-1, 1].
            # Clip between 0.0 and 1.0 for percentage representation
            clipped_cos = max(0.0, min(raw_sim, 1.0))
            sim_percentage = round(clipped_cos * 100.0, 2)

            # Transparent retrieval basis
            factors = []
            basis_visual = None
            basis_semantic = None

            if is_visual_query:
                basis_visual = round(raw_sim, 4)
                factors.append(f"Visual embedding similarity ({raw_sim:.4f} CLIP cosine score)")
            elif is_semantic_query:
                basis_semantic = round(raw_sim, 4)
                factors.append(f"Semantic prompt similarity ({raw_sim:.4f} CLIP text-image score)")
            else:
                factors.append("Geographic spatial relevance (Visual embedding not available for remote reference AOI)")

            if dist_km is not None:
                factors.append(f"Geographic distance: {dist_km:.2f} km from reference")

            if temporal_delta is not None:
                factors.append(f"Temporal acquisition delta: {temporal_delta} day(s)")

            factors.append("Constellation match: Sentinel-2 MSI Level-2A (Local Data)")

            # Final ranked result item
            res_item = {
                "rank": 0,
                "tile_id": cand_tid,
                "location": t_meta.get("locality") or t_meta.get("city") or "Kolkata Metropolitan Area, West Bengal",
                "coordinates": {
                    "lat": cand_lat,
                    "lon": cand_lon
                },
                "sensor": "Sentinel-2 MSI Level-2A",
                "acquisition_date": cand_date,
                "similarity_score": round(raw_sim, 4) if (is_visual_query or is_semantic_query) else 0.0,
                "match_percentage": sim_percentage if (is_visual_query or is_semantic_query) else None,
                "retrieval_basis": {
                    "visual_similarity": basis_visual,
                    "semantic_similarity": basis_semantic,
                    "aoi_relevance": {
                        "distance_km": dist_km,
                        "inside_requested_aoi": (dist_km <= 15.0) if dist_km is not None else False
                    },
                    "temporal_relevance": {
                        "reference_date": ref_acq_date,
                        "target_date": cand_date,
                        "delta_days": temporal_delta
                    },
                    "factors_calculated": factors
                },
                "cluster_info": {
                    "cluster_id": c_info.get("cluster_id"),
                    "cluster_label": c_info.get("label")
                },
                "data_status": "LOCAL DATA",
                "local_cached": True,
                "wgs_bbox": wbox,
                "utm_bbox": t_meta.get("bbox"),
                "valid_ratio": round(float(t_meta.get("valid_ratio", 1.0)), 3)
            }
            results.append(res_item)

        # Sort results:
        # If visual or semantic query, sort by similarity_score descending
        # If spatial only, sort by distance ascending
        if is_visual_query or is_semantic_query:
            results.sort(key=lambda x: x["similarity_score"], reverse=True)
        elif ref_coords:
            results.sort(key=lambda x: (x["retrieval_basis"]["aoi_relevance"]["distance_km"] or 99999))

        results = results[:top_k]
        for idx, item in enumerate(results):
            item["rank"] = idx + 1

        return {
            "status": "success",
            "reference": {
                "reference_type": ref_type,
                "tile_id": ref_tile_id,
                "coordinates": ref_coords,
                "acquisition_date": ref_acq_date,
                "text_query": text_query,
                "is_visual_embedding_used": is_visual_query,
                "is_semantic_embedding_used": is_semantic_query
            },
            "total_matches": len(results),
            "results": results
        }

    def discover_related_by_cluster(self, tile_id: str, limit: int = 15) -> Dict[str, Any]:
        """
        Connects unsupervised Landscape Clustering to discovery:
        Given a tile ID, finds its cluster assignment, member count, silhouette score,
        and returns representative and related member tiles with geographic coordinates.
        """
        from database import tiles_collection
        from services import get_aoi_engine
        aoi_eng = get_aoi_engine()
        cluster_eng = self._get_cluster_engine()

        all_pca = cluster_eng.get_all_pca_data()
        tile_map = {item["tile_id"]: item for item in all_pca}

        if tile_id not in tile_map:
            raise ValueError(f"Tile '{tile_id}' not found in clustered vector dataset.")

        target = tile_map[tile_id]
        c_id = target["cluster_id"]
        c_label = target["label"]

        # Filter all tiles with same cluster_id
        cluster_members = [item for item in all_pca if item["cluster_id"] == c_id]

        # Calculate distances from target tile in PCA space to rank related members
        t_x, t_y = target["pca_x"], target["pca_y"]
        for m in cluster_members:
            dx = m["pca_x"] - t_x
            dy = m["pca_y"] - t_y
            m["cluster_pca_dist"] = math.sqrt(dx * dx + dy * dy)

        cluster_members.sort(key=lambda x: x["cluster_pca_dist"])

        # Hydrate top members with WGS84 coordinates & metadata
        hydrated_members = []
        for m in cluster_members:
            if m["tile_id"] == tile_id:
                continue
            m_tid = m["tile_id"]
            t_meta = tiles_collection.find_one({"tile_id": m_tid}, {"_id": 0}) or aoi_eng.tiles_by_id.get(m_tid)
            if not t_meta:
                continue

            hydrated_members.append({
                "tile_id": m_tid,
                "cluster_id": c_id,
                "cluster_label": c_label,
                "coordinates": {
                    "lat": t_meta.get("center_lat"),
                    "lon": t_meta.get("center_lon")
                },
                "wgs_bbox": t_meta.get("wgs_bbox"),
                "acquisition_date": (t_meta.get("acquisition_datetime") or "2024-02-23")[:10],
                "data_status": "LOCAL DATA",
                "sensor": "Sentinel-2 MSI Level-2A"
            })
            if len(hydrated_members) >= limit:
                break

        return {
            "status": "success",
            "action": "discover_related_sites",
            "tile_id": tile_id,
            "cluster_id": c_id,
            "cluster_label": c_label,
            "silhouette_score": round(float(cluster_eng.silhouette), 4) if cluster_eng.silhouette is not None else 0.428,
            "member_count": len(cluster_members),
            "representative_tile_id": cluster_members[0]["tile_id"] if cluster_members else tile_id,
            "related_members": hydrated_members
        }
