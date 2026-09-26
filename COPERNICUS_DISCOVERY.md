# BIRDSΣY3 — Copernicus Data Space Live STAC Discovery Architecture (Phase 5B)

## 1. Overview & System Objectives

Phase 5B integrates a live Copernicus Data Space Ecosystem STAC discovery layer into **BIRDSEYΣ3**. Analysts can query the official Copernicus STAC API in real time for **Sentinel-2 (Optical L2A / L1C)** and **Sentinel-1 (C-SAR GRD)** metadata over user-selected Areas of Interest (AOI).

---

## 2. STAC API Configuration & Endpoint Specification

- **STAC API Endpoint:** `https://stac.dataspace.copernicus.eu/v1/search`
- **Base Endpoint:** `https://stac.dataspace.copernicus.eu/v1/`
- **STAC Version:** 1.0.0
- **Supported Collections:**
  - `sentinel-2-l2a`: Sentinel-2 Level-2A Bottom of Atmosphere (BOA) Surface Reflectance (Default Optical)
  - `sentinel-2-l1c`: Sentinel-2 Level-1C Top of Atmosphere (TOA) Reflectance
  - `sentinel-1-grd`: Sentinel-1 Ground Range Detected C-band Synthetic Aperture Radar (Default SAR)
  - `sentinel-1-slc`: Sentinel-1 Single Look Complex C-SAR

---

## 3. Query Flow & Filter Pipeline

The backend module `backend/copernicus_engine.py` manages STAC queries via a 4-step pipeline:

```
[Analyst Console UI]
       │ (User clicks "Run Live Copernicus Discovery")
       ▼
[FastAPI /api/copernicus/search]
       │ Validate BBox / Polygon / Dates / Sensor Filter
       ▼
[CopernicusDiscoveryEngine]
       │ STAC POST Query Payload Construction
       ▼
[https://stac.dataspace.copernicus.eu/v1/search]
       │ Real HTTP POST (timeout 6.0s)
       ▼
[Feature Collection Normalization & Filter]
       │ Filter cloud cover for Sentinel-2, format platform/orbit/polarization
       ▼
[JSON Payload + Catalog Provenance Document]
```

### Supported Filters:
1. **Spatial Boundary:**
   - WGS84 BBox: `[min_lon, min_lat, max_lon, max_lat]`
   - WGS84 Polygon: GeoJSON Geometry `intersects` ring `[[lon, lat], ...]`
2. **Temporal Window:** ISO-8601 interval `start_date/end_date` (e.g. `2024-01-01T00:00:00Z/2026-12-31T23:59:59Z`).
3. **Cloud Cover Filter (Sentinel-2):** Post-filter thresholding using STAC property `eo:cloud_cover`.
4. **Result Limit:** Clamped integer `1 <= limit <= 50`.

---

## 4. Sentinel-1 vs. Sentinel-2 Metadata Field Extraction

The engine extracts verified STAC properties without inventing metadata:

| Metadata Field | Sentinel-2 Optical (L2A) | Sentinel-1 C-SAR (GRD) |
| :--- | :--- | :--- |
| **Product ID** | `S2A_MSIL2A_20240329T...` | `S1A_IW_GRDH_1SDV_20240326T...` |
| **Cloud Cover** | `eo:cloud_cover` (e.g. `14.2%`) | `N/A (SAR / Radar)` |
| **Platform / Orbit** | `platform` + `sat:orbit_state` | `platform` + `sat:orbit_state` (Ascending/Descending) |
| **Polarization** | `N/A` | `sar:polarization` (e.g. `VV+VH`, `HH+HV`) |
| **Processing Level**| `Level-2A` | `GRD` |
| **Data Status** | `COPERNICUS_DISCOVERED` | `COPERNICUS_DISCOVERED` |
| **Local Cache** | `False` | `False` (`LOCAL SAR: NOT CACHED LOCALLY`) |

---

## 5. Live Data vs. Local Staged Data Distinction

To maintain strict scientific integrity, the system differentiates between local and remote assets:

1. **Local Staged Dataset (909 Tiles):**
   - Pre-processed Sentinel-2 Level-2A GeoTIFF patches covering Kolkata & Sundarbans.
   - Status Indicator: `✓ LOCAL SENTINEL-2 IMAGERY AVAILABLE` (Local FAISS search, sub-pixel co-registration, Otsu change analysis active).

2. **Copernicus Live Discovery (Phase 5B):**
   - Remote catalog STAC metadata discovered live from Copernicus Data Space.
   - Status Indicator: `🌐 COPERNICUS DISCOVERED (REMOTE STAC METADATA ONLY)`.
   - **Crucial Rule:** Discovering Sentinel-1 or Sentinel-2 products remotely does **NOT** enable local SAR processing or local vector search. Local SAR status remains `SENTINEL-1 SAR — NOT CACHED LOCALLY`.

---

## 6. Offline Limitations & Error Handling

- **No Auto-Trigger on Startup:** The application starts 100% offline. STAC network calls are made **only** when an analyst explicitly triggers a live discovery operation.
- **Network Failure / Air-Gapped Mode:**
  - If the Copernicus STAC API is unreachable or network is offline, the system returns status `⚠️ LIVE CATALOG UNAVAILABLE`.
  - The UI displays an informational notice without crashing or freezing.
  - All local map navigation, place geocoding, AOI drawing, and 909-tile local satellite analysis remain 100% functional.

---

## 7. Provenance & Security

- **Discovery Provenance:** Every live discovery execution records a catalog provenance entry in MongoDB `provenance_collection` with `action: "copernicus_stac_discovery"`, capturing request parameters, collection ID, STAC endpoint, timestamp, and returned scene counts.
- **Security Scoping:**
  - No remote shell commands, arbitrary URL downloads, or remote code execution.
  - Strict input validation on dates, BBox ranges, polygon coordinates, and sensor strings.
  - Bounded 6.0-second HTTP timeouts to prevent looper thread deadlocks.

---

## 8. Explicit Phase Limitation

> **PHASE 5B LIMITATION CLAUSE:**
> Phase 5B performs STAC catalog discovery only. Remote imagery file downloading, local disk caching, automated ingestion, remote SAFE/GeoTIFF processing, and FAISS indexing of remote data are strictly out of scope for Phase 5B and are implemented separately in Phase 5C.
