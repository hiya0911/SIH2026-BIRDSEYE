# BIRDSΣY3 — EXPLAINABLE CHANGE INVESTIGATION & ANALYST DECISION INTELLIGENCE WORKFLOW

## System Overview & Architecture

Phase 4D upgrades the BIRDSEYΣ3 Evidence & Investigation Workspace into a deterministic, fully explainable multi-temporal change investigation system.

The system connects real Sentinel-2 satellite data and physical pipeline outputs along a 7-stage evidence lineage chain:

```
AOI
  └─► 1. OBSERVATIONS TIMELINE
        └─► 2. PREPROCESSING & LEVEL-2A QUALITY
              └─► 3. TRI-EPOCH CHANGE DETECTION
                    └─► 4. FALSE-ALARM SUPPRESSION
                          └─► 5. AI EXPLAINABILITY & CONFIDENCE
                                └─► 6. ANALYST DECISION INTELLIGENCE
                                      └─► 7. PROVENANCE REPORT & EVIDENCE EXPORT
```

---

## 1. Temporal Investigation Timeline

The investigation engine scans available Sentinel-2 `.SAFE` granules chronologically and presents an un-fabricated timeline of available observations:

- **Earliest Usable Observation:** The earliest cloud-cleared Level-2A observation (e.g. `2024-02-23`, Sentinel-2B MSI Level-2A, `S2B_MSIL2A_20240223T043809_N0510_R033_T45QXF`).
- **Intermediate Observation:** Epoch progression markers (e.g. `2025-02-27`, Sentinel-2B).
- **Latest Observation:** The most recent observation (e.g. `2026-02-27`, Sentinel-2C MSI Level-2A).

Each observation details:
- Acquisition Date
- Constellation & Sensor (Sentinel-2B / Sentinel-2C Level-2A)
- Official ESA Product Identifier
- Usable Pixel Quality (`Valid Pixel Ratio`, `Cloud Cover %`)

---

## 2. Before / After Evidence & Change Characterization

### Imagery Evidence
Displays verified high-resolution multi-spectral patches:
- **BEFORE:** 2024 Baseline BOA Reflectance (RGB)
- **AFTER:** 2026 Target BOA Reflectance (RGB)
- **CHANGE MASK:** Multi-temporal difference mask (or `CHANGE MASK NOT AVAILABLE` if uncomputed).

### Physical Change Characterization & Domain Interpretation
Based on deterministic multi-spectral index differencing ($\Delta\text{BR}$, $\Delta\text{NDVI}$, $\Delta\text{NDWI}$):
- **Physical Change Types:** `EXPANSION`, `CONTRACTION`, `APPEARANCE`, `DISAPPEARANCE` (or `CLASSIFICATION NOT DETERMINED`).
- **Domain Interpretations:** `CONSTRUCTION`, `CLEARANCE`, `WATER CHANGE`, `ROAD CHANGE` (or `CLASSIFICATION NOT DETERMINED`).

---

## 3. False-Alarm Intelligence Matrix

Every candidate change undergoes an explicit 6-check deterministic false-alarm audit:

1. **Cloud / Shadow Check:** Validated against 20m Scene Classification Layer (SCL) mask. `PASS` if valid ratio $\ge 85\%$.
2. **Seasonal / Phenological Check:** Regional phenological drift baseline subtracted ($\mu_{\text{pheno}}$). `PASS`.
3. **Illumination Correction Check:** Solar zenith angle ratio normalization applied ($0.8 \le \text{factor} \le 1.2$). `PASS`.
4. **Registration / Co-registration Check:** Sub-pixel 2D FFT phase correlation RMSE evaluated. `PASS` if RMSE $< 1.0$ px.
5. **Temporal Persistence Check:** Multi-epoch presence verified across 2024, 2025, 2026 observations. `PASS`.
6. **Image Quality Check:** Signal-to-Noise Ratio proxy evaluated. `PASS` if SNR $\ge 6.0$ dB.

### False-Alarm Risk Score
- **LOW:** All 6 checks passed cleanly, zero cloud contamination.
- **MODERATE:** Partial cloud/shadow occlusion or speckle noise filtered.
- **ELEVATED:** High cloud contamination or registration offset $> 1.5$ px.

---

## 4. AI Confidence & Explainability

Exposes component-level explainability without synthetic ML scores:
- **Spatial Evidence:** Contiguous pixel cluster geometry & sub-pixel alignment RMSE.
- **Temporal Evidence:** Tri-epoch multi-date persistence across 3 consecutive years.
- **Data Quality:** Valid pixel ratio ($99.8\%$), SCL Cloud Cover ($0.0\%$), SNR ($8.22\text{ dB}$).
- **False-Alarm Checks:** Audit matrix status across 6 physical criteria.
- **Retrieval Similarity:** FAISS CLIP ViT-B/32 512-D visual similarity vector score.

---

## 5. Temporal Persistence Analysis

Classifies multi-date disturbance behavior into four deterministic categories:
- `PERSISTENT`: Disturbance maintained across 2024, 2025, and 2026 epochs without vegetation recovery.
- `TRANSIENT`: Short-duration anomaly present in single observation.
- `CYCLICAL / RECOVERY`: Seasonal agricultural browning followed by vegetative greening.
- `INSUFFICIENT TEMPORAL EVIDENCE`: Fewer than 3 usable observations available.

---

## 6. Analyst Decision Intelligence Workflow

Integrates human-in-the-loop active learning directly into the investigation workspace:
- **Decisions:** `CONFIRM`, `REJECT`, `FLAG`
- **Audit Trail:** Every decision records the decision type, analyst ID, timestamp, and detailed rationale without overwriting historical records.
- **Live State Synchronization:** Submitting a review immediately updates the workspace UI, case badge, review status, and audit log.

---

## 7. Report Export & Provenance Lineage

- **Markdown Report (`/api/cases/{case_id}/report`):** Generates a 20-section formal incident report including AOI coordinates, acquisition dates, ESA product IDs, change stats, 8-stage preprocessing telemetry, false-alarm matrix, explainability triggers, analyst verdict, and SHA-256 provenance chain.
- **JSON Evidence Package (`/api/cases/{case_id}/evidence.json`):** Exportable structured JSON bundle containing complete machine-readable telemetry, decision trace, and cryptographic package hash (`SHA256-...`).
