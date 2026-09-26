"""
BIRDSΣY3 — Copernicus Data Space STAC Discovery Engine (Phase 5B)
Connects directly to the Copernicus Data Space Ecosystem STAC API v1
(https://stac.dataspace.copernicus.eu/v1/) for live Sentinel-1 and Sentinel-2
catalog discovery. Performs spatial, temporal, and cloud-cover metadata queries.

IMPORTANT: DISCOVERY ONLY.
Does NOT download satellite imagery files.
Does NOT automatically ingest remote data.
Does NOT cache remote satellite files locally.
Does NOT fabricate products or metadata.
"""

import logging
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Copernicus Data Space Ecosystem STAC Endpoint (v1)
COPERNICUS_STAC_URL = "https://stac.dataspace.copernicus.eu/v1/search"
COPERNICUS_BASE_URL = "https://stac.dataspace.copernicus.eu/v1/"

# Standard Collection Mapping
COLLECTION_MAP = {
    "SENTINEL-2": "sentinel-2-l2a",
    "SENTINEL-2-L2A": "sentinel-2-l2a",
    "SENTINEL-2-L1C": "sentinel-2-l1c",
    "SENTINEL-1": "sentinel-1-grd",
    "SENTINEL-1-GRD": "sentinel-1-grd",
    "SENTINEL-1-SLC": "sentinel-1-slc",
}

class CopernicusDiscoveryEngine:
    def __init__(self, stac_url: str = COPERNICUS_STAC_URL):
        self.stac_url = stac_url
        self.last_status: str = "Initialized"
        self.last_request_time: Optional[str] = None

    def get_service_status(self) -> Dict[str, Any]:
        """
        Reports current status of Copernicus Data Space STAC connection.
        Does NOT perform an auto-query on app startup unless explicitly tested.
        """
        is_online = False
        status_msg = "Not tested"
        try:
            r = requests.get(COPERNICUS_BASE_URL, timeout=2.5)
            if r.status_code == 200:
                is_online = True
                status_msg = "200 OK — Online"
            else:
                status_msg = f"HTTP {r.status_code}"
        except Exception as e:
            status_msg = f"Unreachable ({str(e)})"

        return {
            "status": "online" if is_online else "offline",
            "configured": True,
            "endpoint": self.stac_url,
            "collections_supported": ["sentinel-2-l2a", "sentinel-1-grd", "sentinel-2-l1c"],
            "last_request_status": status_msg,
            "remote_data_cached_by_phase5b": False,
            "local_file_downloads_enabled": False
        }

    def resolve_collection(self, sensor: str, collection_override: Optional[str] = None) -> str:
        """Resolves sensor name or explicit collection ID to standard Copernicus STAC collection."""
        if collection_override:
            return collection_override.lower()
        sensor_upper = (sensor or "SENTINEL-2").upper().strip()
        return COLLECTION_MAP.get(sensor_upper, "sentinel-2-l2a")

    def format_datetime_range(self, start_date: Optional[str], end_date: Optional[str]) -> str:
        """Formats dates into STAC ISO-8601 datetime string 'start/end'."""
        s = "2024-01-01T00:00:00Z"
        e = "2026-12-31T23:59:59Z"

        if start_date:
            clean_s = start_date.strip()
            if "T" not in clean_s:
                clean_s += "T00:00:00Z"
            s = clean_s

        if end_date:
            clean_e = end_date.strip()
            if "T" not in clean_e:
                clean_e += "T23:59:59Z"
            e = clean_e

        return f"{s}/{e}"

    def discover_scenes(
        self,
        sensor: str = "SENTINEL-2",
        collection: Optional[str] = None,
        bbox: Optional[List[float]] = None,
        polygon: Optional[List[List[float]]] = None,
        start_date: Optional[str] = "2024-01-01",
        end_date: Optional[str] = "2026-12-31",
        max_cloud_cover: Optional[float] = 100.0,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Executes live STAC catalog discovery query over Copernicus Data Space API.
        No imagery files are downloaded or stored.
        """
        target_collection = self.resolve_collection(sensor, collection)
        datetime_str = self.format_datetime_range(start_date, end_date)
        clamped_limit = max(1, min(int(limit), 50))

        payload: Dict[str, Any] = {
            "collections": [target_collection],
            "datetime": datetime_str,
            "limit": clamped_limit
        }

        # Handle spatial boundary filtering
        if bbox and len(bbox) == 4:
            payload["bbox"] = [float(b) for b in bbox]
        elif polygon and len(polygon) >= 3:
            # Format polygon into GeoJSON Geometry for STAC intersects
            ring = [[float(pt[0]), float(pt[1])] for pt in polygon]
            # Ensure closed ring
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            payload["intersects"] = {
                "type": "Polygon",
                "coordinates": [ring]
            }

        # Execute HTTP POST request to STAC API
        try:
            logger.info(f"Copernicus STAC query: collection={target_collection}, limit={clamped_limit}")
            resp = requests.post(self.stac_url, json=payload, timeout=6.0)
            self.last_request_time = datetime.utcnow().isoformat() + "Z"

            if resp.status_code != 200:
                self.last_status = f"HTTP {resp.status_code}"
                return {
                    "status": "error",
                    "message": f"Copernicus STAC API returned HTTP {resp.status_code}: {resp.text[:200]}",
                    "sensor": sensor,
                    "collection": target_collection,
                    "total_discovered": 0,
                    "discovered_scenes": []
                }

            self.last_status = "200 OK"
            stac_data = resp.json()
            raw_features = stac_data.get("features", [])

            discovered_scenes = []
            for feat in raw_features:
                props = feat.get("properties", {})
                
                # Cloud cover filter for Sentinel-2 optical scenes
                cloud_cover = props.get("eo:cloud_cover")
                if cloud_cover is not None and max_cloud_cover is not None:
                    try:
                        if float(cloud_cover) > float(max_cloud_cover):
                            continue
                    except ValueError:
                        pass

                # Extract verified properties without fabricating missing values
                platform = props.get("platform") or props.get("sat:platform") or "Sentinel"
                acq_time = props.get("datetime") or props.get("created") or "N/A"
                orbit_dir = props.get("sat:orbit_state") or props.get("orbitDirection") or None
                polarization = props.get("sar:polarization") or props.get("polarizationChannels") or None
                grid_code = props.get("grid:code") or None
                proc_level = "Level-2A" if "l2a" in target_collection else ("GRD" if "grd" in target_collection else "N/A")

                # Get self link or STAC asset link if available
                source_url = None
                links = feat.get("links", [])
                for link in links:
                    if link.get("rel") in ("self", "canonical", "alternate"):
                        source_url = link.get("href")
                        break

                scene_item = {
                    "product_id": feat.get("id", "N/A"),
                    "collection": target_collection,
                    "satellite_platform": platform,
                    "acquisition_time": acq_time,
                    "cloud_cover_pct": round(float(cloud_cover), 2) if cloud_cover is not None else None,
                    "processing_level": proc_level,
                    "orbit_direction": orbit_dir if orbit_dir else "N/A",
                    "polarization": polarization if polarization else "N/A",
                    "grid_code": grid_code if grid_code else "N/A",
                    "wgs_bbox": feat.get("bbox"),
                    "geometry": feat.get("geometry"),
                    "source_url": source_url,
                    "data_status": "COPERNICUS_DISCOVERED",
                    "local_cached": False
                }
                discovered_scenes.append(scene_item)

            return {
                "status": "success",
                "sensor": sensor,
                "collection": target_collection,
                "total_discovered": len(discovered_scenes),
                "discovered_scenes": discovered_scenes,
                "data_disclaimer": "COPERNICUS DISCOVERED — Remote catalog metadata only. Imagery not downloaded locally."
            }

        except Exception as err:
            logger.warning(f"Copernicus STAC discovery request failed: {err}")
            self.last_status = f"Error: {err}"
            return {
                "status": "error",
                "message": f"Copernicus STAC API unreachable: {str(err)}",
                "sensor": sensor,
                "collection": target_collection,
                "total_discovered": 0,
                "discovered_scenes": []
            }
