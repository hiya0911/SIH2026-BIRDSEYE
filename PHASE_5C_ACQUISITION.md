# BIRDSEYΣ3 — Phase 5C Live Imagery Acquisition & Secure Local Cache Documentation

## Overview

Phase 5C extends the live Copernicus Data Space STAC discovery engine (**Phase 5B**) with an on-demand, secure, local satellite imagery acquisition and caching architecture. Analysts can select any real discovered STAC scene item and securely pull image assets into the local BIRDSEYΣ3 data cache (`data/acquisitions/<scene-id>/`), with end-to-end geospatial provenance tracking, security validation, and incremental vector-indexing handoff capabilities.

---

## 1. Architecture & Component Diagram

```
[ FRONTEND UI (Copernicus Console) ]
           │ (Analyst clicks "ACQUIRE LOCALLY")
           ▼
[ POST /api/copernicus/acquire ]
           │
           ▼
[ CopernicusAcquisitionEngine ]
   ├── 1. HTTPS Protocol & Host Allowlist Validation (*.dataspace.copernicus.eu)
   ├── 2. Path Traversal & Sanitize Scene ID
   ├── 3. Duplicate Detection (check local acquisition manifest)
   ├── 4. Bounded Stream Download (Max 200 MB, timeout-protected)
   ├── 5. Atomic Write via Temporary `.part` File
   ├── 6. Streaming SHA-256 Digest Calculation
   ├── 7. GeoTIFF / Package Metadata Inspection (rasterio CRS/bounds/transform)
   └── 8. Manifest & Provenance Preservation (`acquisition_manifest.json` + MongoDB)
           │
           ▼
[ SECURE LOCAL CACHE: data/acquisitions/<scene_id>/ ]
           │
           ▼ (Optional Handoff)
[ POST /api/copernicus/acquisitions/{id}/ingest ]
           │
           ▼
[ SecureIngestionEngine.ingest_single_geotiff() ]
           │
           ▼
[ INCREMENTAL FAISS VECTOR INDEX & MONGODB CATALOG ]
```

---

## 2. Acquisition Workflow & Endpoint API

### `POST /api/copernicus/acquire`
Initiates stream acquisition for a discovered Copernicus scene asset.

**Request Schema:**
```json
{
  "scene_id": "S2B_MSIL2A_20260227T051009_N0512_R019_T45QXF_20260227T074512",
  "collection": "sentinel-2-l2a",
  "sensor": "SENTINEL-2",
  "acquisition_time": "2026-02-27T05:10:09Z",
  "asset_key": "visual",
  "asset_url": "https://download.dataspace.copernicus.eu/v1/collections/sentinel-2-l2a/items/...",
  "bbox": [88.3, 22.5, 88.4, 22.6]
}
```

**Response Schema:**
```json
{
  "status": "COMPLETED",
  "acquisition_id": "acq_a1b2c3d4e5f6",
  "scene_id": "S2B_MSIL2A_20260227T051009_N0512_R019_T45QXF_20260227T074512",
  "collection": "sentinel-2-l2a",
  "sensor": "SENTINEL-2",
  "asset_key": "visual",
  "local_filepath": "C:\\...\\data\\acquisitions\\S2B_MSIL2A_...\\S2B_MSIL2A_..._visual.tif",
  "file_size_mb": 14.82,
  "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "download_status": "COMPLETED",
  "validation_status": "VALIDATED_RASTER",
  "ingestion_status": "READY_FOR_INGESTION"
}
```

### Additional Endpoints
- `GET /api/copernicus/acquisitions`: Lists all locally cached acquisitions.
- `GET /api/copernicus/acquisitions/{acquisition_id}`: Retrieves manifest details for an acquisition.
- `POST /api/copernicus/acquisitions/{acquisition_id}/ingest`: Hands off acquired GeoTIFF asset to the FAISS vector index.

---

## 3. Security Controls & Safeguards

1. **Host Allowlist Verification:** Only requests pointing to approved Copernicus Data Space Ecosystem domains (`stac.dataspace.copernicus.eu`, `download.dataspace.copernicus.eu`, `zipper.dataspace.copernicus.eu`, `eodataspace.eu`, etc.) are processed.
2. **HTTPS Enforcement:** Plain HTTP or non-secure schemes are rejected.
3. **Path Traversal Prevention:** `scene_id` and file paths are strictly sanitized to prevent relative directory traversal (`../`).
4. **200 MB Download Threshold:** Downloads exceeding 200 MB are rejected before or during streaming to protect local disk space and server memory.
5. **Atomic File Write:** Downloads stream to a `.part` temporary file and are atomically renamed to the final destination upon clean exit and non-zero byte validation.
6. **Incomplete File Cleanup:** Any aborted or failed download immediately removes its temporary `.part` file.
7. **No Remote Execution:** Acquired files are strictly parsed as data inputs and never executed as shell commands or scripts.

---

## 4. Local Cache Directory Structure

```
data/
  acquisitions/
    <scene_id>/
      acquisition_manifest.json
      <scene_id>_visual.tif
```

### Sample `acquisition_manifest.json`:
```json
{
  "acquisition_id": "acq_7f8a9b0c1d2e",
  "scene_id": "S2B_MSIL2A_20260227T051009_N0512_R019_T45QXF_20260227T074512",
  "collection": "sentinel-2-l2a",
  "sensor": "SENTINEL-2",
  "acquisition_time": "2026-02-27T05:10:09Z",
  "asset_key": "visual",
  "source_url": "https://stac.dataspace.copernicus.eu/...",
  "local_filename": "S2B_MSIL2A_..._visual.tif",
  "local_filepath": "C:\\...\\data\\acquisitions\\...\\S2B_MSIL2A_..._visual.tif",
  "file_size_bytes": 15542100,
  "sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
  "wgs_bbox": [88.3, 22.5, 88.4, 22.6],
  "raster_metadata": {
    "width": 10980,
    "height": 10980,
    "bands": 3,
    "crs": "EPSG:32645",
    "bounds": [600000.0, 2490240.0, 709800.0, 2600040.0]
  },
  "download_status": "COMPLETED",
  "validation_status": "VALIDATED_RASTER",
  "ingestion_status": "READY_FOR_INGESTION",
  "acquired_at": "2026-09-26T23:35:00Z",
  "processing_time_ms": 420.5
}
```

---

## 5. Provenance Tracking & Provenance Chain

Every successful acquisition appends an entry into MongoDB `provenance_collection`:

```
REMOTE COPERNICUS STAC ITEM
            ↓
  VALIDATED HTTPS TARGET
            ↓
STREAMED DOWNLOAD (.part)
            ↓
  SHA-256 DIGEST HASH
            ↓
LOCAL ACQUISITION CACHE (`data/acquisitions/<scene_id>/`)
            ↓
   PROVENANCE MANIFEST (`acquisition_manifest.json`)
            ↓
  OPTIONAL INGESTION HANDOFF (FAISS VECTOR INDEX)
```

---

## 6. Offline & Failure Behavior

- **No Fake Fallback Downloads:** If Copernicus services or external network connections are unreachable, the system returns a clear `⚠️ LIVE CATALOG / ACQUISITION UNAVAILABLE` status without generating dummy imagery files.
- **Local Data Continuity:** Full access to pre-indexed local imagery (909 tiles), semantic retrieval, map geocoding, multi-temporal change detection, and investigation case reviews remains 100% operational offline.

---

## 7. Known Limitations

- **Sentinel-1 SAFE Packages:** Full Sentinel-1 SAFE `.zip` product packages are stored intact with `VALIDATED_PACKAGE` status without forcing false GeoTIFF conversion until dedicated SAR decoders parse the internal polarimetric channels.
- **200 MB Limit:** High-resolution uncompressed full Sentinel-2 granules larger than 200 MB must be pre-tiled or acquired via windowed COG byte ranges.
