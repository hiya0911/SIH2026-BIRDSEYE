# PHASE 5D — NATIONAL EO DISCOVERY + SIMILAR-SITE INTELLIGENCE

**Project:** BIRDSEYΣ3  
**Phase:** 5D — National EO Discovery + Similar-Site Intelligence  
**Status:** COMPLETE (Ready for Manual UI Testing)  
**Base Commit:** `82b99a8` (Phase 5C live imagery acquisition)  

---

## 1. Executive Summary

Phase 5D elevates BIRDSEYΣ3 from regional AOI monitoring into a **National-Scale Earth Observation Discovery and Intelligence System**. Analysts can now:
1. Discover Sentinel-1 and Sentinel-2 satellite passes across India using named locations, geocoordinates, point AOIs, rectangular bounds, polygonal AOIs, or broader regions via the Copernicus STAC API.
2. Search and rank **genuinely similar sites** across the national territory using the existing 512-dimensional CLIP ViT-B/32 embedding space and FAISS `IndexFlatIP` vector index.
3. Inspect **explainable similarity breakdowns** where visual similarity, semantic similarity, geographic distance, and temporal deltas are calculated from actual mathematical data rather than fabricated approximations.
4. Seamlessly hand off discovery or similar-site results directly onto the Leaflet analyst map, demarcate new AOIs, or launch change detection investigations.
5. Cluster and discover landscape typologies using the unsupervised `LandscapeClusterEngine` with real silhouette scores and representative exemplar tiles.
6. Strictly uphold **data honesty** across 4 distinct availability tiers (`LOCAL DATA`, `ACQUIRED LOCALLY`, `REMOTE STAC METADATA`, and `NOT AVAILABLE LOCALLY`).

---

## 2. System Architecture & Data Flow

```
[ Analyst Interface (Frontend Console) ]
   │
   ├─► National EO Discovery Bar (Named Location / Coordinates / Point / Rect / Polygon / Region)
   │     │
   │     ▼
   │   [ CopernicusEngine.discover_scenes ] ──► OpenStreetMap Nominatim Geocoding
   │     │                                  ──► Copernicus CDSE STAC API (/search)
   │     │                                  ──► Local Catalog & Acquisition Cache Cross-Ref
   │     ▼
   │   Scenes with Availability Tiers:
   │   [LOCAL DATA | ACQUIRED LOCALLY | REMOTE STAC METADATA | NOT AVAILABLE LOCALLY]
   │
   └─► Similar-Site Intelligence Engine
         │
         ├── Reference Source:
         │     ├── Reference Tile ID (Local or Acquired)
         │     ├── Map / AOI Geographic Coordinates
         │     ├── Semantic Text Query
         │     └── External Reference Image Upload
         │
         ▼
       [ SimilarSiteEngine ]
         │
         ├── Vector Embedding: CLIP ViT-B/32 (512-dim Normalized)
         ├── Vector Retrieval: FAISS IndexFlatIP (Cosine Similarity)
         ├── Geodesic Calculations: Haversine Formula (WGS-84 Distance km)
         ├── Temporal Calculations: Absolute Date Delta (Days)
         │
         ├── Explainability Generator:
         │     ├── Visual Cosine Score (0.000 to 1.000)
         │     ├── Semantic Alignment Score
         │     ├── AOI Proximity (km & qualitative tier)
         │     └── Temporal Relevance (Days delta)
         │
         └── Clustering Integration:
               └── LandscapeClusterEngine (K-Means / PCA / Silhouette)
```

---

## 3. Similarity Calculation & Vector Retrieval

### 3.1 FAISS Vector Index
- **Index Type:** FAISS `IndexFlatIP` (Exact inner-product search on $\ell_2$-normalized 512-dimensional vectors, equivalent to Cosine Similarity).
- **Vectors Ingested:** 909 local Sentinel-2 multi-spectral scene tiles + locally acquired scenes.
- **Model:** CLIP ViT-B/32 (`openai/clip-vit-base-patch32`), generating 512-dimensional image/text embeddings.
- **Query Mechanism:**
  - When querying with a `tile_id`: Looks up the precomputed normalized vector in memory from `data/index/index_metadata.pkl`.
  - When querying with a `semantic_query`: Encodes the query text through CLIP's text encoder and normalizes to unit length.
  - When querying with a `reference_image`: Encodes the image tensor through CLIP's vision encoder and normalizes to unit length.
  - Query executed via `vector_index.search(query_vec, k=top_k)`.
  - **No duplicate index is created.** All queries strictly reuse the single existing FAISS instance loaded at backend startup.

### 3.2 Explainable Similarity Metrics
To preserve mathematical rigor and ensure zero fabricated metrics:
1. **Visual Similarity:** Calculated solely from the FAISS dot-product cosine score ($S_{\text{visual}} = \mathbf{q} \cdot \mathbf{v}_i \in [-1, 1]$). Scaled and formatted to 3 decimal places (e.g., `0.892`).
2. **Semantic Similarity:** Displayed only when a semantic text query or label embedding is evaluated.
3. **Geographic Relevance (Haversine Distance):**
   $$\Delta\sigma = 2 \arcsin \sqrt{\sin^2\left(\frac{\Delta\phi}{2}\right) + \cos\phi_1 \cos\phi_2 \sin^2\left(\frac{\Delta\lambda}{2}\right)}$$
   $$d = R \cdot \Delta\sigma \quad (R = 6371.0088 \text{ km})$$
   - Categorized transparently: `Co-located (< 5 km)`, `Proximate (< 50 km)`, `Regional (< 250 km)`, or `Distant (> 250 km)`.
   - **Crucial Rule:** Geographic proximity is *never* conflated with visual similarity. A site 2 km away with completely different terrain will clearly show high spatial proximity but low visual similarity.
4. **Temporal Relevance:** Calculated as $|T_{\text{ref}} - T_{\text{candidate}}|$ in calendar days.

---

## 4. National EO Discovery & Availability Tiers

National EO Discovery integrates the Copernicus Data Space Ecosystem (CDSE) STAC catalogue with automatic geocoding and local inventory cross-referencing:

### Availability Tiers:
| Availability Status | Meaning | Can Investigate Immediately? |
| :--- | :--- | :--- |
| **`LOCAL DATA`** | Tile is indexed in the local BIRDSEYΣ3 dataset with pre-processed multi-spectral GeoTIFFs and FAISS vectors. | Yes |
| **`ACQUIRED LOCALLY`** | Scene was previously downloaded from Copernicus CDSE via Phase 5C secure pipeline and verified in local cache. | Yes |
| **`REMOTE STAC METADATA`** | Satellite pass exists in Copernicus STAC catalog; metadata and footprint known, but pixel data has not yet been acquired. | No (Requires Acquisition) |
| **`NOT AVAILABLE LOCALLY`** | SAR (Sentinel-1) or distant scenes where the platform has metadata integration but no local raster storage. | No |

---

## 5. Landscape Clustering Integration

Phase 5D integrates the unsupervised `LandscapeClusterEngine` directly into the discovery workflow:
- **Action:** Analyst triggers `"Discover Related Sites (Clustering)"` on any tile or candidate.
- **Lookup:** Retrieves the tile's cluster assignment from the pre-computed K-Means/PCA cluster matrix.
- **Response:**
  - Cluster ID and total member count.
  - Overall cluster silhouette score (unsupervised clustering quality metric).
  - Exemplar / representative tile closest to the cluster centroid.
  - Member tiles with coordinates, acquisition dates, and direct links to map footprinting.
- **Integrity:** Cluster assignments are strictly derived from the clustering engine; no synthetic or randomized labels are returned.

---

## 6. Team Member's False-Alarm Idea: PIF-Based RRN Analysis

### 6.1 Proposed Concept
A team member proposed incorporating **Relative Radiometric Normalization (RRN)** using **Pseudo-Invariant Features (PIFs)** and linear regression:
$$Y_k = m_k \cdot X_k + c_k$$
where $X_k$ represents the DN or surface reflectance of band $k$ in the reference epoch, and $Y_k$ is the target epoch's band reflectance, with slope $m_k$ and intercept $c_k$ fitted on radiometrically stable pixels (e.g., deep water, paved airport runways, massive rock faces, mature building rooftops).

### 6.2 Architectural Evaluation of Existing Pipeline
We inspected the existing preprocessing pipeline (`backend/preprocessing.py`) and change detection engine (`backend/change_detection.py`):
1. **Current Pipeline Stages:**
   - Stage 1: Spatial Resampling to 10m Ground Sample Distance (GSD).
   - Stage 2: Radiometric Scaling (Sentinel-2 BOA reflectance integer scale conversion $\times 0.0001$).
   - Stage 3: Multi-Temporal Band Alignment (B02, B03, B04, B08).
   - Stage 4: Cloud and Shadow Masking (SCL / thresholding).
   - Stage 5: Topographic Illumination Correction (Cosine / Minnaert).
   - Stage 6: Sub-Pixel Co-Registration (Phase Correlation / FFT shift).
   - Stage 7: Spectral Normalization / Baseline Match.
2. **Current False Alarm Filtering:**
   - In `backend/change_detection.py`, false alarms from seasonal vegetation shifts are filtered via NDVI differencing thresholds ($\Delta\text{NDVI} > \tau_{\text{veg}}$), cloud edge dilation masks, and morphological opening/closing operations.

### 6.3 Recommended Future Integration Point
Rather than disrupting the active production pipeline, PIF-based RRN should be integrated as **Stage 6B** (immediately following Sub-Pixel Co-Registration and prior to Spectral Index Differencing):
- **PIF Selection:** Compute multi-temporal scattergram or IR-MAD (Iteratively Reweighted Multivariate Alteration Detection) over cloud-free, co-registered pixels. Select pixels whose multi-temporal residual is within the lowest 5th percentile ($\chi^2 \le \chi^2_{\text{crit}}$).
- **Linear Fit:** Perform robust regression (RANSAC or Theil-Sen) to estimate $m_k$ and $c_k$ for each spectral band ($B02, B03, B04, B08$).
- **Transformation:** Apply $X'_k = m_k X_k + c_k$ to normalize atmospheric differences and sensor drift before feeding into the change detection sub-pixel subtraction.
- *Status:* Documented and architecturally mapped for Phase 6 enhancements. Existing pipeline was preserved unmodified.

---

## 7. Automated Test Suite Verification

An exhaustive automated test suite was created in `scratch/test_phase5d_similar_sites.py` covering all 20 required specifications.

### Test Results Summary:
```
====================================================================================================
TEST RESULTS: 20/20 PASSED (0 failed)
====================================================================================================
  [PASS] 01. National Location Discovery (Nominatim + STAC)
  [PASS] 02. Point AOI Discovery
  [PASS] 03. Rectangle AOI Discovery
  [PASS] 04. Polygon AOI Discovery
  [PASS] 05. Date Filtering
  [PASS] 06. Sensor Filtering (Sentinel-2 vs Sentinel-1)
  [PASS] 07. Local vs Remote Distinction
  [PASS] 08. Similar Site Query Execution
  [PASS] 09. Actual Vector Similarity (FAISS FlatIP Cosine)
  [PASS] 10. Ranked Results Monotonicity
  [PASS] 11. Metadata Preservation
  [PASS] 12. Map Handoff Information
  [PASS] 13. Cluster Integration (LandscapeClusterEngine)
  [PASS] 14. Empty Results Handling
  [PASS] 15. Invalid Input Validation
  [PASS] 16. No Fabricated Similarity Scores
  [PASS] 17. Phase 5A Regression (Analyst Map & Tile Bounding Boxes)
  [PASS] 18. Phase 5B Regression (Interactive AOI Engine)
  [PASS] 19. Phase 5C Regression (Copernicus Acquisition Engine)
  [PASS] 20. SIH Core Requirement Regression (Change Detection & Verification)
====================================================================================================
```

In addition, regression testing against `scratch/test_phase5c_acquisition.py` passed with **22/22 PASSED** (0 failures).

---

## 8. Limitations & Known Boundaries

1. **Local Vector Catalog Extent:** The local FAISS vector index contains 909 pre-ingested Sentinel-2 tiles covering key operational regions. Remote STAC discovery covers the entire Indian subcontinent; however, similar-site vector matching retrieves nearest neighbors from indexed imagery. To search newly acquired remote scenes, they must be processed through the ingestion pipeline (`IngestionPipeline.ingest_raster`).
2. **Sentinel-1 (SAR) Vectors:** SAR integration is supported for STAC discovery, metadata filtering, and baseline radar calculations, but Sentinel-1 GRD imagery is not stored in the 909-tile optical FAISS index. SAR passes are accurately marked as `NOT AVAILABLE LOCALLY` or `REMOTE STAC METADATA`.
3. **Nominatim Rate Limits:** Named location geocoding uses OpenStreetMap Nominatim with caching. In offline or heavily restricted operational environments, analysts can input exact coordinates (Lat/Lon) directly into the discovery bar.

---

## 9. Reproducibility

To re-run the verification suites on any environment:
```powershell
# Phase 5D Test Suite (20 tests)
python scratch/test_phase5d_similar_sites.py

# Phase 5C Regression Suite (22 tests)
python scratch/test_phase5c_acquisition.py
```
Both suites run autonomously without external internet requirements by utilizing fallback mocks for live Copernicus STAC endpoints when credentials are not configured in `.env`.
