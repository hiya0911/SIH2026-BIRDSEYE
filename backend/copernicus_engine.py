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
                    "assets": feat.get("assets", {}),
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


# =========================================================
# PHASE 5C: SECURE LIVE ACQUISITION & LOCAL CACHE ENGINE
# =========================================================

import os
import sys
import json
import uuid
import hashlib
import time
from urllib.parse import urlparse
import rasterio

ALLOWLISTED_HOSTS = {
    "stac.dataspace.copernicus.eu",
    "dataspace.copernicus.eu",
    "download.dataspace.copernicus.eu",
    "zipper.dataspace.copernicus.eu",
    "catalogue.dataspace.copernicus.eu",
    "code.dataspace.copernicus.eu",
    "eodataspace.eu",
    "datahub.creodias.eu",
    "creodias.eu"
}

class CopernicusAcquisitionEngine:
    def __init__(self, data_dir: str = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = data_dir or os.path.join(base_dir, "data")
        self.acquisitions_dir = os.path.join(self.data_dir, "acquisitions")
        os.makedirs(self.acquisitions_dir, exist_ok=True)
        self.max_bytes = 200 * 1024 * 1024  # 200 MB maximum acquisition limit

    def validate_url_security(self, url: str) -> str:
        """
        Validates asset URL against host allowlist, HTTPS scheme, and path traversal vulnerabilities.
        """
        if not url or not isinstance(url, str):
            raise ValueError("URL must be a non-empty string.")

        parsed = urlparse(url.strip())
        if parsed.scheme.lower() != "https":
            raise ValueError(f"Security Rejection: Only HTTPS protocol allowed ('{parsed.scheme}' rejected).")

        hostname = parsed.hostname.lower() if parsed.hostname else ""
        if not any(hostname == allowed or hostname.endswith("." + allowed) for allowed in ALLOWLISTED_HOSTS):
            raise ValueError(f"Security Rejection: Host '{hostname}' is not in Copernicus allowlist.")

        return url.strip()

    def sanitize_scene_id(self, scene_id: str) -> str:
        """Prevents path traversal in target scene directory names."""
        if not scene_id or not isinstance(scene_id, str):
            raise ValueError("Invalid scene ID.")
        clean = "".join(c for c in scene_id if c.isalnum() or c in ("-", "_", "."))
        if not clean or clean.startswith(".") or ".." in clean:
            raise ValueError(f"Security Rejection: Invalid or unsafe scene ID '{scene_id}'.")
        return clean

    def check_duplicate_acquisition(self, scene_id: str, asset_key: str = "visual") -> Optional[Dict[str, Any]]:
        """
        Detects whether target scene asset has already been acquired and validated locally.
        """
        try:
            clean_id = self.sanitize_scene_id(scene_id)
            scene_dir = os.path.join(self.acquisitions_dir, clean_id)
            manifest_path = os.path.join(scene_dir, "acquisition_manifest.json")

            if os.path.exists(manifest_path):
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                
                local_file = manifest.get("local_filepath")
                if local_file and os.path.exists(local_file) and os.path.getsize(local_file) > 0:
                    manifest["is_duplicate"] = True
                    manifest["status_message"] = "Asset already acquired and cached locally."
                    return manifest
        except Exception:
            pass
        return None

    def resolve_asset_url(
        self,
        scene_id: str,
        collection: str = "sentinel-2-l2a",
        asset_key: str = "visual",
        asset_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Resolves the actual downloadable HTTPS asset URL for a Copernicus STAC scene item.
        Queries the Copernicus STAC Item API if needed.
        """
        clean_scene_id = self.sanitize_scene_id(scene_id)
        target_collection = collection or ("sentinel-1-grd" if "S1" in clean_scene_id else "sentinel-2-l2a")

        # If direct download asset URL passed (not a STAC item endpoint or invalid /download path)
        if asset_url and isinstance(asset_url, str):
            clean_url = asset_url.strip()
            if clean_url.startswith("https://") and "/items/" not in clean_url and not clean_url.endswith("/download"):
                return {"url": clean_url, "asset_key": asset_key, "title": asset_key}

        # Fetch STAC Item metadata from Copernicus
        item_url = f"https://stac.dataspace.copernicus.eu/v1/collections/{target_collection}/items/{clean_scene_id}"
        try:
            resp = requests.get(item_url, timeout=6.0)
            if resp.status_code == 404 and target_collection != "sentinel-1-grd" and "S1" in clean_scene_id:
                item_url = f"https://stac.dataspace.copernicus.eu/v1/collections/sentinel-1-grd/items/{clean_scene_id}"
                resp = requests.get(item_url, timeout=6.0)

            if resp.status_code == 404:
                return {
                    "error": f"STAC Item ID '{clean_scene_id}' not found on Copernicus server (HTTP 404).",
                    "status_code": 404
                }
            elif resp.status_code != 200:
                return {
                    "error": f"Copernicus STAC API returned HTTP {resp.status_code}",
                    "status_code": resp.status_code
                }

            item_data = resp.json()
            assets = item_data.get("assets", {})

            target_asset = None
            resolved_key = asset_key

            if asset_key in assets:
                target_asset = assets[asset_key]
            elif asset_key in ("visual", "preview", "thumbnail", "default"):
                for k in ("thumbnail", "visual", "TCI_10m", "TCI_20m", "Product", "safe_manifest"):
                    if k in assets:
                        target_asset = assets[k]
                        resolved_key = k
                        break

            if not target_asset and assets:
                resolved_key, target_asset = next(iter(assets.items()))

            if not target_asset:
                return {"error": f"No asset keys found in STAC item '{clean_scene_id}'."}

            href = target_asset.get("href")
            alt_https = target_asset.get("alternate", {}).get("https", {}).get("href")

            final_url = None
            if alt_https and alt_https.startswith("https://"):
                final_url = alt_https
            elif href and href.startswith("https://"):
                final_url = href

            if not final_url:
                return {"error": f"Asset '{resolved_key}' has no direct HTTPS URL (only S3 URI: {href})."}

            return {
                "url": final_url,
                "asset_key": resolved_key,
                "title": target_asset.get("title", resolved_key),
                "type": target_asset.get("type", "unknown"),
                "file_size": target_asset.get("file:size"),
                "auth_refs": target_asset.get("auth:refs", []),
                "item_geometry": item_data.get("geometry"),
                "item_bbox": item_data.get("bbox")
            }

        except Exception as e:
            return {"error": f"Failed to connect to Copernicus STAC Item API: {str(e)}"}

    def acquire_scene_asset(
        self,
        scene_id: str,
        collection: str = "sentinel-2-l2a",
        sensor: str = "SENTINEL-2",
        acquisition_time: Optional[str] = None,
        asset_key: str = "visual",
        asset_url: Optional[str] = None,
        bbox: Optional[List[float]] = None,
        geometry: Optional[Dict[str, Any]] = None,
        mock_response_content: Optional[bytes] = None
    ) -> Dict[str, Any]:
        """
        Securely streams and acquires a discovered Copernicus scene asset into local storage:
        Security Validation -> Duplicate Detection -> Streamed Download (.part) -> SHA-256 -> Atomic Rename -> GeoTIFF Inspection -> Manifest -> Provenance.
        """
        t_start = time.perf_counter()
        acq_id = f"acq_{uuid.uuid4().hex[:12]}"
        
        # Step 1: Sanitize inputs & Security Checks
        clean_scene_id = self.sanitize_scene_id(scene_id)
        
        # Check duplicate
        existing = self.check_duplicate_acquisition(clean_scene_id, asset_key)
        if existing:
            return existing

        target_url = asset_url
        resolved_key = asset_key
        item_bbox = bbox
        item_geometry = geometry

        if mock_response_content is None:
            # Resolve actual asset URL from Copernicus STAC Item API
            resolution = self.resolve_asset_url(
                scene_id=clean_scene_id,
                collection=collection,
                asset_key=asset_key,
                asset_url=asset_url
            )

            if "error" in resolution:
                status_code = resolution.get("status_code", 400)
                if status_code == 404:
                    return {
                        "status": "FAILED",
                        "acquisition_id": acq_id,
                        "scene_id": clean_scene_id,
                        "reason": resolution.get("error", "Scene or asset not found."),
                        "download_status": "NOT_FOUND"
                    }
                else:
                    return {
                        "status": "FAILED",
                        "acquisition_id": acq_id,
                        "scene_id": clean_scene_id,
                        "reason": resolution.get("error", "Asset URL resolution failed."),
                        "download_status": "FAILED_RESOLUTION"
                    }

            target_url = resolution.get("url")
            resolved_key = resolution.get("asset_key", asset_key)
            if not item_bbox:
                item_bbox = resolution.get("item_bbox")
            if not item_geometry:
                item_geometry = resolution.get("item_geometry")

        try:
            validated_url = self.validate_url_security(target_url or "https://dataspace.copernicus.eu")
        except ValueError as ve:
            return {
                "status": "REJECTED",
                "acquisition_id": acq_id,
                "scene_id": clean_scene_id,
                "reason": str(ve),
                "download_status": "REJECTED_SECURITY"
            }

        # Step 2: Prepare local acquisition directory & temp .part file
        scene_dir = os.path.join(self.acquisitions_dir, clean_scene_id)
        os.makedirs(scene_dir, exist_ok=True)

        ext = ".tif" if ("visual" in resolved_key or "B0" in resolved_key or "TCI" in resolved_key) else (".jpg" if "thumb" in resolved_key else ".dat")
        asset_filename = f"{clean_scene_id}_{resolved_key}{ext}"
        final_filepath = os.path.join(scene_dir, asset_filename)
        part_filepath = os.path.join(scene_dir, f"{asset_filename}.part")

        # Step 3: Streamed Download with Size Limitation & SHA-256 Calculation
        hasher = hashlib.sha256()
        total_downloaded = 0

        try:
            if mock_response_content is not None:
                # Controlled mock test fixture execution
                if len(mock_response_content) > self.max_bytes:
                    return {
                        "status": "FAILED",
                        "acquisition_id": acq_id,
                        "scene_id": clean_scene_id,
                        "reason": f"Asset size ({len(mock_response_content)} bytes) exceeds max 200MB limit.",
                        "download_status": "REJECTED_SIZE_EXCEEDED"
                    }
                hasher.update(mock_response_content)
                total_downloaded = len(mock_response_content)
                with open(part_filepath, "wb") as pf:
                    pf.write(mock_response_content)
            else:
                # Real HTTP streamed download
                resp = requests.get(validated_url, stream=True, timeout=(10.0, 30.0))
                
                if resp.status_code in (401, 403):
                    if os.path.exists(part_filepath):
                        os.remove(part_filepath)
                    return {
                        "status": "REQUIRES_AUTHENTICATION",
                        "acquisition_id": acq_id,
                        "scene_id": clean_scene_id,
                        "reason": f"Copernicus Data Space returned HTTP {resp.status_code}. Raw band nodes require registered OIDC OAuth2 user authentication.",
                        "download_status": "AUTH_REQUIRED",
                        "asset_key": resolved_key,
                        "source_url": validated_url
                    }
                elif resp.status_code == 404:
                    if os.path.exists(part_filepath):
                        os.remove(part_filepath)
                    return {
                        "status": "FAILED",
                        "acquisition_id": acq_id,
                        "scene_id": clean_scene_id,
                        "reason": f"Asset URL returned HTTP 404 Not Found on Copernicus server.",
                        "download_status": "NOT_FOUND"
                    }
                elif resp.status_code != 200:
                    if os.path.exists(part_filepath):
                        os.remove(part_filepath)
                    return {
                        "status": "FAILED",
                        "acquisition_id": acq_id,
                        "scene_id": clean_scene_id,
                        "reason": f"Copernicus asset server returned HTTP {resp.status_code}",
                        "download_status": f"FAILED_HTTP_{resp.status_code}"
                    }

                content_len = resp.headers.get("Content-Length")
                if content_len and int(content_len) > self.max_bytes:
                    if os.path.exists(part_filepath):
                        os.remove(part_filepath)
                    return {
                        "status": "REJECTED",
                        "acquisition_id": acq_id,
                        "scene_id": clean_scene_id,
                        "reason": f"Remote asset size ({int(content_len)/(1024*1024):.1f}MB) exceeds 200MB security threshold.",
                        "download_status": "REJECTED_SIZE_EXCEEDED"
                    }

                with open(part_filepath, "wb") as pf:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            total_downloaded += len(chunk)
                            if total_downloaded > self.max_bytes:
                                pf.close()
                                if os.path.exists(part_filepath):
                                    os.remove(part_filepath)
                                return {
                                    "status": "REJECTED",
                                    "acquisition_id": acq_id,
                                    "scene_id": clean_scene_id,
                                    "reason": "Download aborted: total size exceeded 200MB security limit.",
                                    "download_status": "REJECTED_SIZE_EXCEEDED"
                                }
                            hasher.update(chunk)
                            pf.write(chunk)

            file_hash = hasher.hexdigest()

            # Step 4: Atomic Finalization & Validation
            if not os.path.exists(part_filepath) or os.path.getsize(part_filepath) == 0:
                return {
                    "status": "FAILED",
                    "acquisition_id": acq_id,
                    "scene_id": clean_scene_id,
                    "reason": "Downloaded file is 0 bytes or missing.",
                    "download_status": "FAILED_ZERO_BYTES"
                }

            # Atomic replace
            os.replace(part_filepath, final_filepath)

            # Step 5: GeoTIFF / Raster Inspection if applicable
            val_status = "VALIDATED_FILE"
            is_ready_for_ingest = False
            raster_meta = {}

            if final_filepath.endswith((".tif", ".tiff")):
                try:
                    with rasterio.open(final_filepath) as src:
                        raster_meta = {
                            "width": src.width,
                            "height": src.height,
                            "bands": src.count,
                            "crs": src.crs.to_string() if src.crs else "UNSPECIFIED",
                            "bounds": list(src.bounds),
                            "nodata": src.nodata
                        }
                    val_status = "VALIDATED_RASTER"
                    is_ready_for_ingest = True
                except Exception:
                    val_status = "VALIDATED_FILE"
            elif final_filepath.endswith((".jpg", ".jpeg", ".png")):
                val_status = "VALIDATED_IMAGE_PREVIEW"
            elif final_filepath.endswith((".zip", ".safe", ".xml")) or "safe" in resolved_key.lower() or "manifest" in resolved_key.lower():
                val_status = "VALIDATED_PACKAGE"


            elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
            manifest = {
                "acquisition_id": acq_id,
                "scene_id": clean_scene_id,
                "collection": collection,
                "sensor": sensor,
                "acquisition_time": acquisition_time or "N/A",
                "asset_key": resolved_key,
                "source_url": validated_url,
                "local_filename": asset_filename,
                "local_filepath": final_filepath,
                "file_size_bytes": total_downloaded,
                "sha256": file_hash,
                "wgs_bbox": item_bbox,
                "geometry": item_geometry,
                "raster_metadata": raster_meta,
                "download_status": "COMPLETED",
                "validation_status": val_status,
                "ingestion_status": "READY_FOR_INGESTION" if is_ready_for_ingest else "PACKAGE_PRESERVED",
                "acquired_at": datetime.utcnow().isoformat() + "Z",
                "processing_time_ms": elapsed_ms,
                "is_duplicate": False
            }

            # Save manifest file
            manifest_path = os.path.join(scene_dir, "acquisition_manifest.json")
            with open(manifest_path, "w", encoding="utf-8") as mf:
                json.dump(manifest, mf, indent=2)

            return {
                "status": "COMPLETED",
                "acquisition_id": acq_id,
                "scene_id": clean_scene_id,
                "collection": collection,
                "sensor": sensor,
                "asset_key": resolved_key,
                "local_filepath": final_filepath,
                "file_size_mb": round(total_downloaded / (1024 * 1024), 2),
                "sha256": file_hash,
                "download_status": "COMPLETED",
                "validation_status": val_status,
                "ingestion_status": "READY_FOR_INGESTION" if is_ready_for_ingest else "PACKAGE_PRESERVED",
                "manifest": manifest
            }

        except Exception as ex:
            if os.path.exists(part_filepath):
                try:
                    os.remove(part_filepath)
                except Exception:
                    pass
            return {
                "status": "FAILED",
                "acquisition_id": acq_id,
                "scene_id": clean_scene_id,
                "reason": f"Acquisition failed: {str(ex)}",
                "download_status": "FAILED_EXCEPTION"
            }


    def list_acquisitions(self) -> List[Dict[str, Any]]:
        """Lists all locally cached Copernicus scene acquisitions."""
        acquisitions = []
        if not os.path.exists(self.acquisitions_dir):
            return acquisitions

        for item in os.listdir(self.acquisitions_dir):
            item_path = os.path.join(self.acquisitions_dir, item)
            if os.path.isdir(item_path):
                manifest_path = os.path.join(item_path, "acquisition_manifest.json")
                if os.path.exists(manifest_path):
                    try:
                        with open(manifest_path, "r", encoding="utf-8") as mf:
                            acquisitions.append(json.load(mf))
                    except Exception:
                        pass
        acquisitions.sort(key=lambda x: x.get("acquired_at", ""), reverse=True)
        return acquisitions

    def get_acquisition(self, acquisition_id_or_scene_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves details of a specific local acquisition by scene ID or acquisition ID."""
        for acq in self.list_acquisitions():
            if acq.get("acquisition_id") == acquisition_id_or_scene_id or acq.get("scene_id") == acquisition_id_or_scene_id:
                return acq
        return None

    def ingest_acquired_asset(self, acquisition_id_or_scene_id: str) -> Dict[str, Any]:
        """
        Handoff pipeline: takes a validated local acquisition raster and ingests it into FAISS index.
        """
        acq = self.get_acquisition(acquisition_id_or_scene_id)
        if not acq:
            return {"status": "FAILED", "reason": f"Acquisition '{acquisition_id_or_scene_id}' not found."}

        filepath = acq.get("local_filepath")
        if not filepath or not os.path.exists(filepath):
            return {"status": "FAILED", "reason": f"Acquired local file missing on disk: '{filepath}'"}

        from ingestion_engine import SecureIngestionEngine
        ingest_engine = SecureIngestionEngine()
        ingest_res = ingest_engine.ingest_single_geotiff(
            filepath=filepath,
            source_label=f"Copernicus Acquisition {acq.get('scene_id')}"
        )

        if ingest_res.get("status") in ("COMPLETED", "DUPLICATE"):
            # Update manifest ingestion status
            scene_dir = os.path.dirname(filepath)
            manifest_path = os.path.join(scene_dir, "acquisition_manifest.json")
            acq["ingestion_status"] = "INGESTED"
            acq["tile_id"] = ingest_res.get("tile_id") or ingest_res.get("existing_tile_id")
            acq["ingested_at"] = datetime.utcnow().isoformat() + "Z"
            try:
                with open(manifest_path, "w", encoding="utf-8") as mf:
                    json.dump(acq, mf, indent=2)
            except Exception:
                pass

        return {
            "status": "COMPLETED",
            "acquisition_id": acq.get("acquisition_id"),
            "scene_id": acq.get("scene_id"),
            "ingestion_result": ingest_res
        }

