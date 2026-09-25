# BIRDSΣY3 — SIH Final Operational Readiness & Judge Demonstration Manual

**Smart India Hackathon (SIH 2026) — Problem Statement ID 26227**  
**Title:** Semantic Retrieval and Multi-Temporal Change Analysis of Satellite Imagery  
**System Designation:** BIRDSEYΣ3 (BIRDSEYE Analyst Command Center)  
**Security Classification:** Restricted / Operational Ready  
**Operational Mode:** 100% Offline / Air-Gapped Local Environment  

---

## 1. System Overview
BIRDSEYΣ3 is an analyst-centric satellite intelligence and change investigation command center built to process Level-2A Sentinel-2 Bottom-Of-Atmosphere (BOA) surface reflectance imagery. The system provides semantic, image-based, and multimodal natural language query capabilities over vector-indexed satellite imagery, executes multi-temporal change detection, filters optical false alarms, provides explainable confidence metrics, records analyst reviews, generates 15-field lineage chains, and exports comprehensive evidence packages.

---

## 2. Current System Architecture
```mermaid
graph TD
    A["Analyst Command Center UI (HTML5/CSS3/JS)"] -->|REST API (FastAPI)| B["Backend API Layer (main.py)"]
    B --> C["Location & Map Intelligence (AOI Engine)"]
    B --> D["Preprocessing Lab Engine (8-Stage BOA)"]
    B --> E["Vector Search Engine (FAISS + CLIP ViT-B/32)"]
    B --> F["Multi-Temporal Change Engine (Tri-Epoch)"]
    B --> G["False-Alarm & Explainability Module"]
    B --> H["Case & Review Management (Mongo / JSON Fallback)"]
    B --> I["Provenance & Evidence Export Module"]
    B --> J["Secure Offline Ingestion Engine"]
    
    E --> K[("FAISS Vector Index (909 512-D Vectors)")]
    H --> L[("MongoDB / local data JSON catalog")]
```

---

## 3. Complete Analyst Workflow
```
[1. LOCATION / AOI] ➔ [2. IMAGERY AVAILABILITY] ➔ [3. PREPROCESSING LAB]
         ➔ [4. SEMANTIC / MULTIMODAL RETRIEVAL] ➔ [5. BEFORE/AFTER TEMPORAL CHANGE]
         ➔ [6. FALSE-ALARM AUDIT] ➔ [7. AI EXPLAINABILITY & CONFIDENCE]
         ➔ [8. ANALYST REVIEW] ➔ [9. PROVENANCE LINEAGE CHAIN] ➔ [10. EVIDENCE EXPORT]
```

---

## 4. Startup Instructions (100% Offline / Local)

### Prerequisites
- Python 3.10+ with `fastapi`, `uvicorn`, `rasterio`, `torch`, `transformers`, `faiss-cpu`, `pymongo`, `numpy`.
- Pre-populated local storage: 909 GeoTIFF tiles in `data/tiles/`, pre-indexed FAISS vectors in `data/index/`.

### Launching the Backend Server
Run from workspace root:
```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### Launching the Analyst Console
Open `frontend/index.html` in any modern Web Browser (Chrome / Firefox / Edge).

---

## 5. Judge Demonstration Sequence

1. **System Health Verification**: Check the top status bar:
   - `BACKEND: ONLINE`
   - `DB: CONNECTED / LOCAL FALLBACK`
   - `FAISS: 909 VECTORS`
   - `MODEL: CLIP ViT-B/32`
   - `OFFLINE: 100% LOCAL`
   - `SECURITY: VERIFIED`
   - `SAR: NOT CACHED LOCALLY`
   - `GROUND TRUTH: NOT AVAILABLE LOCALLY`
2. **Location Search & AOI**: Search for location (e.g., `Kolkata, India` / `22.5726, 88.3639`), draw Rectangle/Polygon AOI, and view overlapping tile footprints.
3. **Preprocessing Lab**: Open Preprocessing Lab, view 8-stage visible processing (BOA reflectance scaling $\rho = \text{DN}/10000.0$, SCL cloud mask, QA score).
4. **Multimodal Search**: Enter query `Urban expansion and industrial building construction`, select weights (Text: 0.7, Image: 0.3), click Search.
5. **Investigation Handoff**: Select a top search result card and click **"🛡️ Investigate ➔"**.
6. **Multi-Temporal Change Analysis**: Inspect Before/After dual-epoch imagery, tri-epoch persistent change heatmap, earliest usable observation timestamp, and false-alarm matrix.
7. **Analyst Review**: Record decision (`CONFIRM` / `REJECT` / `FLAG`), add analyst rationale, and submit.
8. **Lineage & Export**: View 15-field provenance chain, export Markdown report (`/api/cases/{case_id}/report`), and export JSON evidence package (`/api/cases/{case_id}/evidence.json`).

---

## 6. Available Real Data
- **Satellite Data**: Level-2A Sentinel-2 BOA Surface Reflectance.
- **Coverage**: Multi-epoch acquisitions (Baseline: 2024-01-15, Intermediate: 2024-06-20, Latest: 2024-11-10).
- **Spatial Resolution**: 10 meters / pixel (B02 Blue, B03 Green, B04 Red, B08 NIR).
- **Tile Catalog**: 909 local GeoTIFF tile patches stored in `data/tiles/`.

---

## 7. Current Indexed Vector Catalog
- **Embedding Model**: OpenAI CLIP ViT-B/32 (512-dimensional L2-normalized embeddings).
- **Vector Search Index**: `faiss.IndexFlatIP` (Cosine similarity via inner product).
- **Active Index Size**: 909 vectors indexed in `data/index/faiss_index.bin`.

---

## 8. Preprocessing Capabilities (8-Stage BOA Pipeline)
1. **Metadata & Quality Gating**: Validates CRS (`EPSG:32645` / `EPSG:4326`), band counts, and dimensions.
2. **BOA Surface Reflectance Scaling**: Divides raw DN by 10,000 to convert to physical surface reflectance.
3. **Cloud & Cloud Shadow Masking**: Applies Sentinel-2 Scene Classification Layer (`VALID_SCL = [4, 5, 6, 7, 11, 2]`).
4. **Quality Scoring**: Computes cloud cover ratio and valid pixel percentage.
5. **Radiometric Adjustment**: Normalizes histogram percentiles ($1\% - 99\%$).
6. **Spatial Co-Registration**: Aligns multi-epoch tiles within sub-pixel tolerance.
7. **Illumination & Phenological Masking**: Corrects solar zenith and seasonal vegetation variations.
8. **ARD Tiling & Handoff**: Prepares 256x256 4-band rasters for vector indexing and change analysis.

---

## 9. Retrieval Capabilities
- **Natural Language Query**: Natural-language semantic search via text CLIP encoder.
- **Image Reference Query**: Upload reference patch to extract CLIP image vector and search nearest neighbors.
- **Combined Multimodal Retrieval**: Convex combination ($w_t \cdot \vec{e}_t + w_i \cdot \vec{e}_i$) of text and image vectors.
- **Spatial / AOI Filtering**: Bounding-box spatial constraint over tile spatial footprints.
- **Spectral Gating**: Pre-filters search space using NDVI / NDWI / NDBI index bounds.

---

## 10. Change Analysis Capabilities (Tri-Epoch)
- Dual-epoch differential analysis (Baseline $T_1$ vs Latest $T_3$).
- Multi-epoch persistence tracking ($T_1 \rightarrow T_2 \rightarrow T_3$) to separate permanent land-use change from transient fluctuations.
- Characterization into built-up expansion, vegetation clearing, water body shift, or bare soil exposure.

---

## 11. False-Alarm Mitigation Module
Evaluates 6 false-alarm risk factors:
1. Cloud / Cloud Shadow contamination
2. Seasonal vegetation phenology (NDVI variance)
3. Solar illumination / sun angle difference
4. Water level fluctuation (NDWI variance)
5. Sensor viewing geometry shift
6. Ephemeral agricultural tilling

---

## 12. Analyst Review & Decision Intelligence
- Real case queue displaying case ID, tile ID, acquisition date, location, sensor, and current status (`OPEN`, `CONFIRMED`, `REJECTED`, `FLAGGED`).
- Interactive submission of analyst verdict, rationale, analyst ID, and timestamp.
- Live updates to MongoDB and fallback `data/reviews.json` data stores.

---

## 13. Provenance & Evidence Export
- **15-Field Lineage**: Full trace from original ESA granule down to analyst verdict.
- **Markdown Evidence Report**: 20-section formatted report exported via `/api/cases/{case_id}/report`.
- **JSON Evidence Package**: Audit-ready JSON export via `/api/cases/{case_id}/evidence.json` with zero `ObjectId` serialization errors.

---

## 14. Offline & On-Premises Operation
- 100% local operation: No remote cloud API calls, no remote geocoder calls, no remote vector DB calls, no remote LLM calls.
- Local Leaflet map assets included.

---

## 15. Security Controls & Ingestion Safety
- **Path Traversal Protection**: Enforces workspace boundary resolution (`real_path.startswith(real_base)`).
- **Upload Limit**: Strict 200 MB file size cap.
- **Format Whitelist**: Restricts raster ingestion to `.tif`, `.tiff`, `.safe`.
- **No Remote Ingestion**: 0% remote URL parameters.
- **Secret Scanning**: Zero hardcoded secrets or API tokens.

---

## 16. SAR Data Honesty Status
- Sentinel-1 SAR C-band status: `SAR_NOT_CACHED_LOCALLY`.
- System architecture is fully SAR-ready, but honestly reports that local Sentinel-1 GRD imagery is not staged.

---

## 17. Ground-Truth & Evaluation Limitations
- Ground truth status: `NOT AVAILABLE LOCALLY`.
- The system explicitly avoids fabricating precision, recall, F1, IoU, or mAP scores when ground-truth segmentation masks are absent.

---

## 18. Known System Limitations
- Memory requirement: Requires ~2.5 GB RAM for local CLIP weights and FAISS vector index.
- Optical imagery cloud dependency: Highly cloudy scenes ($> 80\%$) are flagged as low quality.

---

## 19. Recommended Judge Demonstration Walkthrough
1. Launch backend server and open `frontend/index.html`.
2. View top operational pills (verify all 8 status pills).
3. Search location `Kolkata, India` and draw a rectangle AOI.
4. Execute Natural Language search for `Industrial building expansion`.
5. Click **"🛡️ Investigate ➔"** on the top result card.
6. Review Before/After imagery, Preprocessing QA, False-Alarm Matrix, and AI Confidence.
7. Click `CONFIRM` and submit analyst rationale.
8. Click **"📄 Export Report"** and **"💾 Export JSON Evidence"**.

---

## 20. Troubleshooting & Support
- **Issue**: Backend fails to connect to MongoDB.
  - **Resolution**: Backend automatically activates local JSON fallback mode (`data/cases.json` & `data/reviews.json`).
- **Issue**: FAISS index missing.
  - **Resolution**: Run `python backend/vector_index.py` to rebuild index from local tile collection.
