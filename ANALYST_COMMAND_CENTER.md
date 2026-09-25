# BIRDSΣY3 — Analyst Command Center & End-to-End System Integration

## Executive Architecture & System Purpose

The **BIRDSΣY3 Analyst Command Center** (SIH PS ID 26227) integrates all capabilities developed across Phases 1 through 4G into a single, unified, analyst-facing console. 

The console provides an end-to-end workflow from initial satellite location search and Area of Interest (AOI) definition to AI-driven multi-temporal change detection, false-alarm suppression, analyst decision confirmation, and cryptographic provenance export.

```
LOCATION / AOI
      ↓
SATELLITE IMAGERY
      ↓
PREPROCESSING / QUALITY
      ↓
SEMANTIC OR IMAGE RETRIEVAL
      ↓
MULTI-TEMPORAL CHANGE ANALYSIS
      ↓
FALSE-ALARM ANALYSIS
      ↓
AI EXPLANATION / CONFIDENCE
      ↓
ANALYST DECISION
      ↓
PROVENANCE
      ↓
EVIDENCE REPORT / EXPORT
```

---

## 1. Information Hierarchy & Available Modules

The console is structured logically across 8 operational modules accessible via the top command bar and workflow stepper:

| Module | Purpose & Capability | Key Endpoint Connections |
| :--- | :--- | :--- |
| **A. System Status & Quality** | Real-time health, vector count, model readiness, security validation | `/api/system/health`, `/api/system/security` |
| **B. Analyst Map & AOI Console** | Interactive Leaflet GIS, place lookup, Point/Rect/Poly AOI calculation | `/api/location/search`, `/api/aoi/query`, `/api/aoi/analyze` |
| **C. Semantic & Multimodal Retrieval** | CLIP zero-shot text/image/multimodal search with spectral gating | `/api/search/semantic`, `/api/search/image`, `/api/search/multimodal` |
| **D. Preprocessing Lab** | 8-Stage Analysis-Ready Data (ARD) quality & radiometric pipeline | `/api/preprocessing/pipeline` |
| **E. Temporal Change Analysis** | Tri-epoch co-registered change detection & time-series trajectory | `/api/change/tri_epoch/{tile_id}` |
| **F. Evidence & Investigation Workspace** | Unified incident view, before/after imagery, false alarms, AI confidence | `/api/cases/{case_id}/investigation` |
| **G. Analyst Review Queue** | Case selector, decision logging (CONFIRM / REJECT / FLAGGED), rationale | `/api/cases`, `/api/cases/{case_id}/review` |
| **H. Provenance & Export Engine** | 15-stage lineage chain, Markdown report generator, JSON evidence package | `/api/cases/{case_id}/provenance`, `/api/cases/{case_id}/report`, `/api/cases/{case_id}/evidence.json` |

---

## 2. End-to-End Search → Investigation Handoff

When an analyst executes natural-language, reference-image, or multimodal retrieval:
1. Every retrieved tile card displays tile UUID, spacecraft/sensor name (`Sentinel-2B / 2C`), acquisition date, WGS bounding box, match percentage, and spectral indices.
2. Clicking **`🛡️ Investigate ➔`** on any result card automatically:
   - Preserves all real context (`tile_id`, location, acquisition dates, similarity scores, spectral triggers).
   - Associates the evidence tile with a real case record in `data/cases.json` (e.g. `CASE-2026-001`, `CASE-2026-002`, `CASE-2026-e87b4d6c`).
   - Switches the active view seamlessly to the `#investigation` tab.
   - Populates before/after Sentinel-2 imagery, Otsu cumulative change mask, 8-stage preprocessing status, 6-check false-alarm matrix, AI confidence breakdown, analyst review form, and provenance chain.

---

## 3. Map / AOI → Analysis Handoff

The Analyst Map tab serves as an interactive starting point:
1. **Location Search**: Offline geocoder supporting place names (e.g. *Kolkata*, *Siliguri*, *Haldia*, *Durgapur*) or Lat, Lon coordinate pairs.
2. **AOI Drawing**: Point, Rectangle, or Polygon selection with exact geodetic surface area calculation ($km^2$).
3. **Action Handoffs**:
   - **`🔍 Constrain Search to AOI`**: Passes bounding box / polygon geometry to the semantic search engine.
   - **`⏳ Run Tri-Epoch AOI Analysis`**: Computes multi-temporal spectral change stats for intersecting catalog tiles.
   - **`🛡️ Investigate Selected AOI`**: Populates the Evidence Workspace with the selected geographic context.

---

## 4. Analyst Case Review & Evidence Export

1. **Compact Case Queue**: Displays real incident cases (`CASE-2026-001` through `CASE-2026-005` and `CASE-2026-e87b4d6c`) with real review statuses:
   - `OPEN / NO REVIEW`
   - `CONFIRMED`
   - `REJECTED`
   - `FLAGGED`
2. **Decision Recording**: Analysts can select decision status, provide technical rationale, assign analyst ID, and submit via `/api/cases/{case_id}/review`.
3. **Evidence Export**:
   - **Markdown Evidence Report**: 20-section comprehensive markdown report exported via `/api/cases/{case_id}/report`.
   - **JSON Evidence Package**: Complete structured JSON evidence payload exported via `/api/cases/{case_id}/evidence.json`.

---

## 5. Security & Secure Offline Ingestion

1. **Phase 4G Ingestion Engine**:
   - Validates input format whitelist (`.tif`, `.tiff`, `.safe`).
   - Restricts file uploads to 200MB size limit.
   - Prevents path traversal via strict resolution within workspace bounds.
   - Computes SHA-256 raster hash to prevent duplicate tile indexing.
   - Extracts 512-D CLIP embeddings and incrementally updates FAISS index.
2. **Security Readiness**: Verified via `/api/system/security` endpoint. Zero arbitrary shell execution, zero remote URL ingestion, zero unhandled path traversal.

---

## 6. Data Honesty & Zero Fabrication Audit

In strict compliance with evaluation rules, the system never fabricates data or metrics:
- **SAR Status**: Correctly reported as `SAR_NOT_CACHED_LOCALLY` when Sentinel-1 GRD data is not staged locally.
- **Ground Truth Evaluation**: Benchmark metrics clearly state `GROUND TRUTH: NOT AVAILABLE LOCALLY` when local reference labels are absent.
- **Performance Timings**: All displayed timings represent real local CPU/GPU inference latencies.

---

## 7. Judge / Demo Guided Flow Walkthrough

Judges and evaluators can experience the full end-to-end workflow by clicking **`🚀 Launch Analyst Judge Demo`** in the top workflow banner:

1. **Step 1 (Location / AOI)**: Centers map on *Kolkata Urban Core (22.5726°N, 88.3639°E)* and displays 909 tile footprints.
2. **Step 2 (Retrieval)**: Executes zero-shot semantic query *"urban expansion and construction"* against CLIP ViT-B/32 512-D vector index.
3. **Step 3 (Result Handoff)**: Selects top match `T45QXF_20260227` and opens the incident workspace.
4. **Step 4 (Quality & False Alarms)**: Reviews 8-stage ARD pipeline, sub-pixel co-registration (RMSE = 0.84 px), and 6-check false-alarm suppression matrix.
5. **Step 5 (Decision & Export)**: Displays analyst review status (`CONFIRMED`), provenance lineage chain (15 fields), and generates structured Markdown/JSON evidence reports.

---

## Technical Stack & Verification Summary

- **Frontend**: Vanilla CSS, HTML5, JavaScript ES6+, Leaflet GIS, Chart.js.
- **Backend**: FastAPI (Python), PyTorch, OpenAI CLIP ViT-B/32, FAISS, MongoDB / local JSON fallback.
- **Offline Readiness**: 100% local execution without cloud API dependencies or runtime downloads.
