# BIRDSEYΣ3 — SIH Core Requirement Compliance & Architecture Specification

## 1. Requirement Compliance Summary

| SIH Core Requirement | Status | Description & Implementation Evidence |
| :--- | :--- | :--- |
| **A. Multi-Temporal Change Analysis** | `IMPLEMENTED` | Real AOI + Time-Window change detection (`POST /api/temporal/multitemporal`) supported across arbitrary local observations. |
| **A. Chronological Observation Pipeline** | `IMPLEMENTED` | Discovers local observations, orders chronologically, verifies CRS & quality, and computes usability & cloud/shadow masking. |
| **A. 4 Core Change Behaviors** | `IMPLEMENTED` | Detects `APPEARANCE`, `DISAPPEARANCE`, `EXPANSION`, and `CONTRACTION` directly from spectral/surface reflectance deltas. |
| **A. Change Characterization** | `IMPLEMENTED` | Classifies `CONSTRUCTION`, `CLEARANCE`, `WATER EXTENT CHANGE`, `ROAD DEVELOPMENT`, or `UNCLASSIFIED / INSUFFICIENT EVIDENCE` with supporting evidence. |
| **A. Earliest Supported Observation** | `IMPLEMENTED` | Identifies `last_reliable_pre_change_observation`, `earliest_supported_observation`, and explicit `observation_interval`. |
| **A. Temporal Persistence** | `IMPLEMENTED` | Evaluates multi-epoch persistence (`CONFIRMED_PERMANENT`, `CYCLICAL_PHENOLOGY`, `EMERGING_NEW_DEVELOPMENT`). |
| **A. False-Alarm Intelligence** | `IMPLEMENTED` | Integrates cloud/shadow masking, sub-pixel registration RMSE, phenological drift factor, illumination factor, and speckle noise filtering. |
| **B. GeoTIFF / TIFF / COG Ingestion** | `IMPLEMENTED` | `POST /api/ingest/raster` validates GeoTIFF, standard TIFF, and Cloud-Optimized GeoTIFF (COG overviews, tiling, block shape). |
| **B. Geospatial Provenance** | `IMPLEMENTED` | Preserves 15-field geographic metadata (CRS, EPSG, affine transform, bounds, resolution, band count, nodata, SHA-256, acquisition datetime, sensor). |
| **B. Incremental Vector Indexing** | `IMPLEMENTED` | Appends vectors to FAISS index using `index.add()` without re-building the index. Updates `index_manifest.json` and catalog records. |
| **B. Duplicate Protection** | `IMPLEMENTED` | Prevents re-indexing duplicate files via SHA-256 digest, filename, and spatial bounds matching (`status: DUPLICATE`). |
| **B. Index Consistency Check** | `IMPLEMENTED` | `GET /api/index/consistency` verifies FAISS vector count against catalog metadata (`INDEX CONSISTENT` / `INDEX CONSISTENCY WARNING`). |
| **B. Georeferencing Traceability** | `IMPLEMENTED` | Preserves end-to-end lineage: `QUERY → VECTOR → TILE → SOURCE RASTER → GEOGRAPHIC LOCATION → ACQUISITION METADATA`. |
| **On-Premises / Offline Operation** | `IMPLEMENTED` | `GET /api/offline/status` confirms 100% local functionality without cloud APIs, external vector DBs, or internet connectivity. |

---

## 2. API Reference

### 2.1 Multi-Temporal Change Endpoint
- **URL**: `POST /api/temporal/multitemporal` (or `POST /api/change/multitemporal`)
- **Payload**:
  ```json
  {
    "bbox": [88.34, 22.55, 88.38, 22.59],
    "start_date": "2024-01-01",
    "end_date": "2026-12-31",
    "sensor": "SENTINEL-2"
  }
  ```
- **Response**:
  - `status`: `"COMPLETED"`
  - `aoi_info`: CRS, UTM bounds, WGS bounds, area in sq km.
  - `observations`: Chronological list of observations with `usable` status, `quality_info`, and `reason`.
  - `detected_behaviors`: Detailed evaluation of `APPEARANCE`, `DISAPPEARANCE`, `EXPANSION`, `CONTRACTION`.
  - `change_characterization`: Classification (`CONSTRUCTION`, `CLEARANCE`, etc.), confidence score, list of supporting evidence strings.
  - `earliest_supported_observation`: Pre-change observation date, earliest supported observation date, observation interval, disclaimer.
  - `temporal_persistence`: Permanence verdict and persistence rate.
  - `false_alarm_checks`: Detailed false-alarm suppression and registration evidence.

### 2.2 GeoTIFF / COG Ingestion Endpoint
- **URL**: `POST /api/ingest/raster`
- **Payload**:
  ```json
  {
    "filepath": "c:/Users/.../tile.tif",
    "source_label": "Analyst Import"
  }
  ```
- **Response**:
  - `status`: `"COMPLETED"` or `"DUPLICATE"`
  - `tile_id`: Unique UUID
  - `vector_count_before`: Integer count before addition
  - `vector_count_after`: Integer count after addition
  - `added_vectors`: `1` (or `0` if duplicate)
  - `provenance_id`: MongoDB provenance document ID

### 2.3 Vector Index Manifest Endpoint
- **URL**: `GET /api/index/manifest`
- **Response**: Index type, embedding model, dimension (`512`), `vector_count`, `build_timestamp`, `last_incremental_update`, `incremental_additions_count`, `source_imagery_count`, and `index_file_sha256`.

### 2.4 Index Consistency Check
- **URL**: `GET /api/index/consistency`
- **Response**: `is_consistent`, `status_code` (`INDEX CONSISTENT`), `faiss_vector_count`, `catalog_count`.

### 2.5 Offline Mode Status
- **URL**: `GET /api/offline/status`
- **Response**: `status`: `"OFFLINE_CORE_OPERATIONAL"`, `on_premises_mode`: `"100% LOCAL ON-PREMISES VERIFIED"`.

---

## 3. Explicit Operational Disclaimer
Phase 5B Copernicus Live Discovery remains optional and satellite imagery downloading or automatic remote acquisition is **not** performed. All core analytical, ingestion, FAISS retrieval, and multi-temporal change functions run **100% locally on-premises**.
