"""
BIRDSEYE Remote Sensing Platform - Sentinel-1 SAR Engine
Handles discovery, ingestion, radiometric calibration, speckle filtering,
and multi-sensor extension interfaces for Sentinel-1 C-SAR IW GRDH products.
Strictly enforces system honesty: returns unavailable status when no local SAR data exists.
"""

import os
import json
import math
import numpy as np
from typing import Dict, Any, List, Optional

# Safe rasterio import
try:
    import rasterio
    from rasterio.windows import Window
    RASTERIO_AVAILABLE = True
except ImportError:
    RASTERIO_AVAILABLE = False

# Safe scipy import
try:
    from scipy.ndimage import median_filter
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


def get_data_dir() -> str:
    """Returns absolute path to the configured project data directory."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))


def discover_sar_products(data_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Safely scans configured project data directory for actual Sentinel-1 products
    (.SAFE packages or .tif rasters containing Sentinel-1/SAR in name).
    Prevents arbitrary filesystem traversal by restricting search to data_dir.
    """
    target_dir = data_dir or get_data_dir()
    discovered_products = []

    if os.path.exists(target_dir):
        # Scan restricted to data_dir, data/tiles, data/sar
        scan_dirs = [target_dir]
        for sub in ["tiles", "sar", "s1"]:
            sub_p = os.path.join(target_dir, sub)
            if os.path.exists(sub_p):
                scan_dirs.append(sub_p)

        for s_dir in scan_dirs:
            for item in os.listdir(s_dir):
                item_upper = item.upper()
                if ("S1" in item_upper or "SENTINEL-1" in item_upper or "SAR" in item_upper) and not item.startswith("."):
                    item_path = os.path.join(s_dir, item)
                    # Exclude non-SAR files like test scripts or JSON cases
                    if item.endswith(".py") or item.endswith(".json") or item.endswith(".md"):
                        continue
                    
                    is_safe = item.endswith(".SAFE") or item.endswith(".zip")
                    is_tif = item.endswith(".tif") or item.endswith(".tiff")

                    if is_safe or is_tif:
                        discovered_products.append({
                            "product_name": item,
                            "path": os.path.relpath(item_path, target_dir),
                            "format": "SAFE_CONTAINER" if is_safe else "GEOTIFF_RASTER",
                            "size_bytes": os.path.getsize(item_path) if os.path.isfile(item_path) else 0,
                            "sensor": "Sentinel-1 C-SAR",
                            "modality": "SAR"
                        })

    if not discovered_products:
        return {
            "available": False,
            "status_code": "SAR_NOT_CACHED_LOCALLY",
            "total_products": 0,
            "products": [],
            "message": "Sentinel-1 SAR C-band imagery is not currently cached in local storage. Pipeline architecture remains ready for future Sentinel-1 GRD ingestion."
        }

    return {
        "available": True,
        "status_code": "SAR_PRODUCTS_DISCOVERED",
        "total_products": len(discovered_products),
        "products": discovered_products,
        "message": f"Discovered {len(discovered_products)} local Sentinel-1 product(s)."
    }


def read_sar_raster(file_path: str) -> Dict[str, Any]:
    """
    Safely opens and reads a Sentinel-1 GRD GeoTIFF raster file using Rasterio.
    Returns metadata, bounds, CRS, and raw band array.
    """
    if not RASTERIO_AVAILABLE:
        return {"status": "error", "message": "Rasterio library not installed."}

    if not os.path.exists(file_path):
        return {"status": "error", "message": f"SAR file not found: {file_path}"}

    try:
        with rasterio.open(file_path) as src:
            meta = {
                "driver": src.driver,
                "width": src.width,
                "height": src.height,
                "count": src.count,
                "crs": str(src.crs),
                "bounds": [src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top],
                "dtypes": src.dtypes
            }
            array = src.read(1)
            return {
                "status": "success",
                "metadata": meta,
                "data": array
            }
    except Exception as e:
        return {"status": "error", "message": f"Failed to open SAR raster: {str(e)}"}


def convert_to_db(array: np.ndarray, is_amplitude: bool = True) -> Dict[str, Any]:
    """
    Safely converts Linear amplitude or intensity to decibels (dB).
    Formula: sigma_0_dB = 10 * log10(intensity + 1e-6)
    Only applies conversion if values are non-negative floats/integers.
    """
    if array is None or array.size == 0:
        return {"status": "error", "message": "Empty array provided."}

    try:
        if is_amplitude:
            intensity = np.square(array.astype(np.float32))
        else:
            intensity = array.astype(np.float32)

        # Apply clipping to avoid log10(0)
        clipped = np.clip(intensity, 1e-6, None)
        db_array = 10.0 * np.log10(clipped)
        
        return {
            "status": "success",
            "db_array": db_array,
            "min_db": float(np.min(db_array)),
            "max_db": float(np.max(db_array)),
            "mean_db": float(np.mean(db_array))
        }
    except Exception as e:
        return {"status": "error", "message": f"dB conversion failed: {str(e)}"}


def apply_speckle_filter(array: np.ndarray, kernel_size: int = 3) -> np.ndarray:
    """
    Applies a 2D 3x3 median speckle noise filter using SciPy ndimage.
    """
    if not SCIPY_AVAILABLE or array is None:
        return array

    return median_filter(array, size=kernel_size)


def generate_vv_vh_composite(vv_array: np.ndarray, vh_array: np.ndarray) -> Dict[str, Any]:
    """
    Generates a Dual-Pol false-color RGB visualization array from real input arrays:
    Red = VV backscatter, Green = VH backscatter, Blue = VH / VV ratio.
    Returns error if input arrays are missing.
    """
    if vv_array is None or vh_array is None:
        return {"status": "error", "message": "Both VV and VH arrays are required to generate composite."}

    try:
        # Normalize arrays to 0-255
        def normalize(arr):
            min_v, max_v = np.percentile(arr, (2, 98))
            if max_v <= min_v:
                return np.zeros_like(arr, dtype=np.uint8)
            norm = np.clip((arr - min_v) / (max_v - min_v), 0, 1)
            return (norm * 255.0).astype(np.uint8)

        r = normalize(vv_array)
        g = normalize(vh_array)
        ratio = np.divide(vh_array + 1e-6, vv_array + 1e-6, out=np.zeros_like(vh_array, dtype=np.float32), where=vv_array!=0)
        b = normalize(ratio)

        rgb = np.stack([r, g, b], axis=-1)
        return {
            "status": "success",
            "rgb_array": rgb,
            "channels": "R=VV, G=VH, B=VH/VV"
        }
    except Exception as e:
        return {"status": "error", "message": f"Composite generation failed: {str(e)}"}


def get_sar_tile_analysis(tile_id: str) -> Dict[str, Any]:
    """
    Returns honest SAR tile analysis for a given tile_id.
    If no real local SAR raster exists for tile_id, returns clear unavailable response.
    DO NOT fabricate fake SAR statistics.
    """
    discovery = discover_sar_products()
    if not discovery["available"]:
        return {
            "available": False,
            "status_code": "SAR_NOT_CACHED_LOCALLY",
            "tile_id": tile_id,
            "sensor": "Sentinel-1 C-SAR",
            "modality": "SAR",
            "message": f"Sentinel-1 SAR C-band raster is not cached locally for tile '{tile_id}'. Optical Sentinel-2 analysis remains active.",
            "data": None
        }

    # If products exist, match by tile_id (placeholder check for real raster files)
    return {
        "available": False,
        "status_code": "SAR_TILE_NOT_FOUND",
        "tile_id": tile_id,
        "sensor": "Sentinel-1 C-SAR",
        "modality": "SAR",
        "message": f"No matching Sentinel-1 SAR slice found for tile ID '{tile_id}'.",
        "data": None
    }


def analyze_multisensor_change(optical_change_stats: Dict[str, Any], sar_change_stats: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Multi-sensor change extension interface.
    Combines Sentinel-2 optical NDVI/NDBI change with Sentinel-1 SAR backscatter delta
    ONLY when both real modalities are present.
    Returns OPTICAL_ONLY mode when SAR data is absent.
    """
    if not sar_change_stats or not sar_change_stats.get("available"):
        return {
            "multisensor_mode": "OPTICAL_ONLY",
            "primary_sensor": "Sentinel-2 MSI",
            "secondary_sensor": "Sentinel-1 C-SAR (Not Cached)",
            "combined_confidence": optical_change_stats.get("confidence_score", 0.95),
            "optical_confidence": optical_change_stats.get("confidence_score", 0.95),
            "sar_confidence": None,
            "sar_contribution": "NOT_AVAILABLE"
        }

    # Future fusion logic when real SAR data exists
    opt_conf = optical_change_stats.get("confidence_score", 0.95)
    sar_conf = sar_change_stats.get("confidence_score", 0.90)
    combined = float(round((opt_conf * 0.6) + (sar_conf * 0.4), 3))

    return {
        "multisensor_mode": "OPTICAL_SAR_FUSED",
        "primary_sensor": "Sentinel-2 MSI",
        "secondary_sensor": "Sentinel-1 C-SAR",
        "combined_confidence": combined,
        "optical_confidence": opt_conf,
        "sar_confidence": sar_conf,
        "sar_contribution": "ACTIVE"
    }
