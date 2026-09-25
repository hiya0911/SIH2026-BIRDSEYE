# BIRDSEYΣ3 SENTINEL-1 SAR READINESS DOCUMENTATION

**Engine Status:** `SAR_NOT_CACHED_LOCALLY` (Architecture Ready & Integrated)  
**Target Sensor:** Copernicus Sentinel-1 C-SAR (Synthetic Aperture Radar)  
**Target Acquisition Mode:** IW GRDH (Interferometric Wide Swath Ground Range Detected High Resolution)  
**Supported Polarizations:** Dual-Pol `VV + VH` (or `VV` / `VH` single-pol)  

---

## 1. Current System Behavior (No Fabrication Policy)

In accordance with strict operational integrity guidelines:
- **Zero fake SAR measurements, rasters, dB values, or confidence scores are created.**
- When no Sentinel-1 `.SAFE` packages or GeoTIFF rasters exist in local storage (`data/` or `data/tiles/` or `data/sar/`), the system honestly reports:
  - Status: `available: False`
  - Status Code: `SAR_NOT_CACHED_LOCALLY`
  - Message: *"Sentinel-1 SAR C-band imagery is not currently cached in local storage. Pipeline architecture remains ready for future Sentinel-1 GRD ingestion."*
- Optical Sentinel-2 analysis remains 100% active and un-affected.

---

## 2. Ingestion & Preprocessing Workflow (Once Real Data is Added)

When Sentinel-1 IW GRDH products are placed into `data/tiles/` or `data/sar/`, `backend/sar_engine.py` will execute the following automated 8-stage pipeline:

1. **Product & Metadata Discovery:** Safe directory scan restricting filesystem access to configured project data directories.
2. **GRD Structure & CRS Validation:** Verifies raster dimensions, geospatial bounding box, and CRS (e.g., `EPSG:32645` / UTM Zone 45N).
3. **Radiometric Calibration ($\sigma^0$):** Converts Linear amplitude/intensity values into decibel ($\text{dB}$) backscatter scale:
   $$\sigma^0_{\text{dB}} = 10 \cdot \log_{10}(\text{intensity} + 1e-6)$$
4. **Sub-pixel Terrain Alignment:** Slices spatial window aligned with optical Sentinel-2 tile bounding box.
5. **Speckle Noise Suppression:** Applies 2D 3x3 median filter via `scipy.ndimage.median_filter`.
6. **VV/VH Dual-Pol Preparation:** Computes cross-polarization ratio ($\text{VH} / \text{VV}$) for surface roughness & vegetation structural analysis.
7. **False-Color RGB Composite Generation:** Renders preview composite:
   - **Red:** $\text{VV}$ backscatter
   - **Green:** $\text{VH}$ backscatter
   - **Blue:** $\text{VH} / \text{VV}$ cross-ratio
8. **Analysis-Ready SAR Tile Handoff:** Exposes SAR backscatter metrics and raster references to the Evidence Workspace & Multi-Sensor Change Engine.

---

## 3. How to Ingest Real Sentinel-1 Data in the Future

1. Download Copernicus Sentinel-1 IW GRDH products (e.g. `S1A_IW_GRDH_1SDV_...`) from ESA Copernicus Data Space Ecosystem.
2. Place extracted VV and VH GeoTIFF rasters or `.SAFE` package into `data/tiles/` or `data/sar/`.
3. Name rasters following standard format (e.g. `sar_vv_vh.tif` or `s1_2024_vv.tif`).
4. The discovery service will automatically detect the files and activate real SAR evidence.

---

## 4. REST API Reference

- `GET /api/sar/status`: Returns environment SAR status and local file discovery results.
- `GET /api/sar/products`: Returns list of discovered Sentinel-1 products on disk.
- `GET /api/sar/tile/{tile_id}`: Returns SAR analysis for a given tile ID (returns HTTP 404 if SAR raster is absent).
- `POST /api/search/semantic`: Supports `sensor_filter: "ALL" | "OPTICAL" | "SAR"`.

---

**Note:** No processing has been claimed against fake SAR rasters. All baseline Optical Sentinel-2 functionality remains verified and intact.
