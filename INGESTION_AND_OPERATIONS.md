# BIRDSΣY3 — Secure Offline Ingestion & Operations Guide

This operational manual documents the secure, on-premises, incremental satellite image ingestion workflow, FAISS index management, security controls, and index rebuild procedures for BIRDSEYΣ3.

---

## 1. Supported Input Formats
- **GeoTIFF / COG (Cloud-Optimized GeoTIFF):** Single-band or multi-band GeoTIFF rasters (`.tif`, `.tiff`).
- **Sentinel-2 L2A `.SAFE` Packages:** Official ESA Level-2A Bottom-Of-Atmosphere (BOA) surface reflectance packages containing `GRANULE/` sub-directories and `R10m`/`R20m`/`R60m` band JP2 rasters.
- **Image Patches:** 256x256 pixel 10m spatial resolution patches with standard map projections.

---

## 2. Raster Safety & Integrity Validation
Every input file undergoes a multi-stage validation check prior to ingestion:
1. **Path Traversal Guard:** Ensures the target file is physically located within the root workspace boundary (`c:\Users\Hiya\OneDrive\Desktop\BIRDSEYE`). Rejects `..` path escapes.
2. **Format Whitelist:** Restricts inputs to `.tif`, `.tiff`, and `.safe`.
3. **File Size Boundary:** Maximum file size cap of 200MB to prevent denial-of-service memory exhaustion.
4. **Raster Array Verification:** Uses `rasterio` to inspect dimensions ($> 0$), band counts ($\ge 1$), data types, spatial projection (CRS `EPSG:32645` / `EPSG:4326`), and verifies non-finite (`NaN` / `Inf`) data arrays.

---

## 3. Preprocessing & Quality Gating
- Integrates directly with the 8-stage visible preprocessing lab (`Preprocessor` / `PreprocessingLabEngine`).
- Extracts Level-2A surface reflectance bands (B02, B03, B04, B08) calibrated by the BOA scaling factor ($\rho = \text{DN} / 10000.0$).
- Applies SCL (Scene Classification Layer) cloud, cloud shadow, and saturated pixel filtering (`VALID_SCL_VALUES = [4, 5, 6, 7, 11, 2]`).

---

## 4. Tile Generation & Patch Extraction
- Large Sentinel-2 SAFE granules are windowed into 256x256 pixel patches (approx $2.56 \text{ km} \times 2.56 \text{ km}$ spatial footprint).
- Tiles with valid pixel ratio $< 50\%$ are automatically filtered out to preserve catalog quality.
- Each generated tile is assigned a UUID v4 tile identifier and saved as a GeoTIFF tile in `data/tiles/`.

---

## 5. Visual Embedding Extraction
- Embeddings are generated using OpenAI's pre-trained **CLIP ViT-B/32** model (512-dimensional vector space).
- Input tile RGB channels (B04, B03, B02) are normalized to $[0, 255]$ uint8 and processed through the CLIP vision transformer encoder.
- Visual feature vectors are $L_2$-normalized to enable exact Cosine Similarity matching via Inner Product.

---

## 6. Incremental Vector Indexing
- The vector index uses **FAISS `IndexFlatIP`** (512 dimensions).
- New tiles are added incrementally (`vector_index.add_embedding(tile_id, vector)`).
- Does **NOT** require rebuilding existing embeddings for previously indexed tiles ($909 \to 909 + N$).
- Index binary (`data/index/faiss_index.bin`) and metadata pickle (`data/index/index_metadata.pkl`) are saved atomically to disk.

---

## 7. Duplicate Detection & Prevention
Before adding a tile to FAISS or MongoDB:
1. **Content Hash Check:** Computes SHA-256 digest of input file and checks against existing provenance records.
2. **Filename Matching:** Checks `tiles_collection` for existing identical filenames.
3. **Spatial Bounds Matching:** Checks exact WGS84 bounding box coordinates.

If a duplicate is detected, ingestion returns status `DUPLICATE`, references the existing tile ID, and skips FAISS re-indexing to prevent duplicate search results.

---

## 8. Metadata Catalog Management
- Stores rich metadata records in MongoDB `birdsey3.tiles` collection.
- Fields recorded: `tile_id`, `filename`, `filepath`, `bbox`, `wgs_bbox`, `crs`, `valid_ratio`, `resolution`, `acquisition_datetime`, `source_scene`, `format`.

---

## 9. Provenance Tracking
For every ingestion transaction, a 15-field audit record is created in MongoDB `provenance_collection`:
- Action: `secure_offline_ingestion`
- Ingestion ID, Source File, Target File
- SHA-256 Content Hash
- Spatial Bounds & CRS
- Model (`OpenAI CLIP ViT-B/32`) & Vector Index Type (`FAISS IndexFlatIP`)
- Processing Time (ms)
- Offline Status: `100% ON-PREMISES VERIFIED`

---

## 10. Failure Recovery & Atomicity
- If embedding extraction fails or a corrupted file is encountered, the ingestion status is set to `FAILED` or `REJECTED`.
- Temporary scratch files are automatically cleaned up.
- Unfinished entries are **NOT** added to the FAISS index or MongoDB catalog.

---

## 11. Complete FAISS Index Rebuild Procedure
To perform a complete clean rebuild of the FAISS index from staged local tiles:

```bash
# 1. Run index rebuild script
python backend/index_tiles.py
```

### Rebuild Specification:
- **Input Catalog:** `data/tiles/tiles_metadata.json`
- **Tile Directory:** `data/tiles/*.tif`
- **Embedding Model:** OpenAI CLIP ViT-B/32 (512D)
- **Vector Space:** $L_2$-normalized cosine space
- **Index Binary Output:** `data/index/faiss_index.bin`
- **Metadata Pickle:** `data/index/index_metadata.pkl`

---

## 12. 100% Offline Operation Guarantee
- All model weights (`openai/clip-vit-base-patch32`) are loaded locally from Hugging Face transformers disk cache.
- No network connections or external API calls are made during ingestion or search.
- GIS map tiles and geocoding operate using offline Leaflet bundles and local landmark lookup tables.

---

## 13. Security Controls & Operational Readiness
- **Path Traversal Protection:** Enforces workspace root path containment.
- **Upload Size Cap:** 200MB maximum file size limit.
- **Shell Execution:** Completely disabled for user inputs.
- **CORS Configuration:** Restricted to controlled origins.
- **Secret Scan Status:** `NO SECRETS DETECTED IN SCANNED APPLICATION FILES`.

---

## 14. Current System Boundaries
- **SAR Status:** Sentinel-1 C-SAR rasters are `SAR_NOT_CACHED_LOCALLY`. Pipeline remains ready for future Sentinel-1 GRD ingestion.
- **Ground Truth Status:** Formal human pixel relevance masks are `UNAVAILABLE_LOCALLY`.
