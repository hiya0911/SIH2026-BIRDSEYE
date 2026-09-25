from typing import Optional
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware

from database import searches_collection, tiles_collection, provenance_collection
from models import create_search_document, create_tile_document, create_provenance_document
from schemas import (
    SearchRequest, 
    SemanticSearchRequest, 
    ImageSearchRequest,
    AOIQueryRequest,
    AOIAnalyzeRequest,
    PreprocessingPipelineRequest,
    CaseCreateRequest,
    AnalystReviewRequest
)
import cases_service
from services import (
    calculate_change,
    build_timeline,
    create_location_label,
    perform_semantic_search,
    perform_image_search,
    perform_image_search_from_pil,
    get_aoi_engine,
    get_embedder,
    vector_index
)

app = FastAPI(
    title="BIRDSΣY3 Backend",
    description=(
        "Semantic Retrieval and Multi-Temporal "
        "Satellite Change Analysis API"
    ),
    version="1.0.0"
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# HOME
# =========================================================

@app.get("/")
def home():
    return {
        "message": "BIRDSΣY3 Backend is running!",
        "project": (
            "Semantic Retrieval and "
            "Multi-Temporal Change Analysis"
        ),
        "status": "online"
    }


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health")
def health():
    try:
        searches_collection.database.command("ping")
        return {
            "status": "healthy",
            "mongodb": "connected"
        }
    except Exception as error:
        return {
            "status": "unhealthy",
            "mongodb": "disconnected",
            "error": str(error)
        }


# =========================================================
# SEARCH
# =========================================================

@app.post("/api/search")
def search_satellite_data(request: SearchRequest):
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query cannot be empty.")

    if request.from_year > request.to_year:
        raise HTTPException(status_code=400, detail="From year must be less than or equal to To year.")

    location_label = create_location_label(request.location)

    latitude = request.location.lat if request.location else None
    longitude = request.location.lon if request.location else None

    # -----------------------------------------------
    # CHANGE DETECTION
    # -----------------------------------------------
    change_data = calculate_change(
        query=query,
        location=location_label,
        from_year=request.from_year,
        to_year=request.to_year
    )

    years = abs(request.to_year - request.from_year) or 1

    # -----------------------------------------------
    # CREATE MONGODB DOCUMENT
    # -----------------------------------------------
    document = create_search_document(
        query=query,
        location=location_label,
        lat=latitude,
        lon=longitude,
        from_year=request.from_year,
        to_year=request.to_year,
        change_data=change_data
    )

    result = searches_collection.insert_one(document)

    return {
        "search_id": str(result.inserted_id),
        "query": query,
        "location": location_label,
        "latitude": latitude,
        "longitude": longitude,
        "from_year": request.from_year,
        "to_year": request.to_year,
        "years": years,
        "change": change_data["total"],
        "change_breakdown": change_data
    }


# =========================================================
# SEMANTIC SEARCH
# =========================================================

@app.post("/api/search/semantic")
def semantic_search(request: SemanticSearchRequest):
    try:
        sf = (request.sensor_filter or "ALL").upper()
        if sf == "SAR":
            return {
                "query": request.query,
                "sensor_filter": "SAR",
                "available": False,
                "results": [],
                "total": 0,
                "search_id": "sar_not_cached",
                "message": "Sentinel-1 SAR C-band data is not currently available in local storage. Pipeline remains ready for future Sentinel-1 GRD ingestion."
            }

        from services import get_advanced_engine
        adv_engine = get_advanced_engine()
        results = adv_engine.search(
            query=request.query,
            top_k=request.top_k,
            spectral_gate=request.spectral_gate,
            force_action_mode=request.action_mode
        )
        
        # 1. Log provenance
        prov_doc = create_provenance_document(
            action="semantic_search",
            source_files=[],
            output_files=[],
            parameters={"query": request.query, "top_k": request.top_k, "spectral_gate": request.spectral_gate}
        )
        provenance_collection.insert_one(prov_doc)

        # 2. Extract top result IDs and metrics
        items = results.get("results", []) if isinstance(results, dict) else results
        top_previews = []
        for it in items[:5]:
            top_previews.append({
                "tile_id": it.get("tile_id"),
                "similarity": round(float(it.get("similarity", 0.0)), 4),
                "confidence": round(float(it.get("confidence", 0.0)), 4) if it.get("confidence") else None
            })

        # 3. Save Search History into MongoDB searches_collection
        search_record = {
            "search_type": "semantic",
            "query": request.query,
            "top_k": request.top_k,
            "spectral_gate": request.spectral_gate,
            "action_mode": request.action_mode,
            "results_count": len(items),
            "top_results": top_previews,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        res_mongo = searches_collection.insert_one(search_record)
        search_id = str(getattr(res_mongo, "inserted_id", ""))

        if isinstance(results, dict):
            results["search_id"] = search_id
            results["saved_to_mongodb"] = True
            return results
            
        return {"query": request.query, "results": results, "search_id": search_id, "saved_to_mongodb": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# IMAGE SEARCH
# =========================================================

@app.post("/api/search/image")
def image_search(request: ImageSearchRequest):
    try:
        results = perform_image_search(request.tile_id, request.top_k)
        
        # 1. Log provenance
        prov_doc = create_provenance_document(
            action="image_search",
            source_files=[request.tile_id],
            output_files=[],
            parameters={"tile_id": request.tile_id, "top_k": request.top_k}
        )
        provenance_collection.insert_one(prov_doc)

        # 2. Save Search History into MongoDB searches_collection
        search_record = {
            "search_type": "image_similarity",
            "query": f"Visual Similarity for Tile: {request.tile_id}",
            "tile_id": request.tile_id,
            "top_k": request.top_k,
            "results_count": len(results) if isinstance(results, list) else 0,
            "top_results": [
                {
                    "tile_id": r.get("tile_id"),
                    "similarity": round(float(r.get("similarity", 0.0)), 4)
                }
                for r in (results if isinstance(results, list) else [])[:5]
            ],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        res_mongo = searches_collection.insert_one(search_record)
        search_id = str(getattr(res_mongo, "inserted_id", ""))
        
        return {
            "tile_id": request.tile_id,
            "results": results,
            "search_id": search_id,
            "saved_to_mongodb": True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/search/image/upload")
async def image_search_upload(
    file: UploadFile = File(...),
    top_k: int = Form(12)
):
    """
    True Image-to-Image Search: Accepts an uploaded satellite image,
    extracts 512-D CLIP embedding, queries FAISS index, and returns
    ranked matching tiles with similarity scores and verified metadata.
    """
    # 1. Validate file extension and MIME type
    allowed_exts = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".webp"}
    filename = file.filename or "uploaded_image.png"
    ext = os.path.splitext(filename)[1].lower()
    
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file format '{ext}'. Allowed formats: {', '.join(sorted(allowed_exts))}"
        )

    try:
        # Read file contents (limit 20MB for security)
        MAX_UPLOAD_SIZE = 20 * 1024 * 1024
        contents = await file.read()
        if len(contents) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=400, detail="File size exceeds maximum permitted limit (20MB).")
        
        # Load into PIL Image
        # If GeoTIFF, try rasterio first or PIL
        pil_img = None
        if ext in {".tif", ".tiff"}:
            try:
                import io
                import rasterio.io
                with rasterio.io.MemoryFile(contents) as memfile:
                    with memfile.open() as src:
                        cnt = src.count
                        if cnt >= 3:
                            r, g, b = src.read(3), src.read(2), src.read(1)
                        else:
                            band = src.read(1)
                            r, g, b = band, band, band
                        def norm(a):
                            return np.clip(a.astype(float) / 2500.0 * 255.0, 0, 255).astype(np.uint8)
                        rgb = np.stack([norm(r), norm(g), norm(b)], axis=-1)
                        pil_img = Image.fromarray(rgb)
            except Exception as ex:
                print(f"[IMAGE UPLOAD] MemoryFile open fallback: {ex}")
                pil_img = Image.open(io.BytesIO(contents)).convert("RGB")
        else:
            import io
            pil_img = Image.open(io.BytesIO(contents)).convert("RGB")

        # Create thumbnail preview base64 for direct frontend display
        preview_buf = io.BytesIO()
        thumb = pil_img.copy()
        thumb.thumbnail((300, 300))
        thumb.save(preview_buf, format="JPEG", quality=85)
        preview_base64 = "data:image/jpeg;base64," + base64.b64encode(preview_buf.getvalue()).decode("utf-8")

        # Perform embedding extraction & FAISS search
        results = perform_image_search_from_pil(pil_img, top_k=top_k)

        # Log provenance
        prov_doc = create_provenance_document(
            action="image_to_image_search_upload",
            source_files=[filename],
            output_files=[r["tile_id"] for r in results[:5]],
            parameters={"filename": filename, "file_size_bytes": len(contents), "top_k": top_k}
        )
        provenance_collection.insert_one(prov_doc)

        # Record in search history
        search_record = {
            "search_type": "image_upload_similarity",
            "query": f"Image-to-Image Query: {filename}",
            "filename": filename,
            "top_k": top_k,
            "results_count": len(results),
            "top_results": [
                {
                    "tile_id": r["tile_id"],
                    "similarity": r["similarity_percentage"]
                }
                for r in results[:5]
            ],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        res_mongo = searches_collection.insert_one(search_record)
        search_id = str(getattr(res_mongo, "inserted_id", ""))

        return {
            "status": "success",
            "filename": filename,
            "file_size": len(contents),
            "preview_image": preview_base64,
            "results": results,
            "search_id": search_id,
            "saved_to_mongodb": True
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image-to-Image search failed: {str(e)}")


# =========================================================
# AOI & GEOSPATIAL MAP ENDPOINTS
# =========================================================

@app.get("/api/aoi/footprints")
def get_aoi_tile_footprints(limit: Optional[int] = Query(None)):
    """
    Returns GeoJSON FeatureCollection of tile boundaries in WGS84 for interactive map overlay.
    """
    try:
        aoi_eng = get_aoi_engine()
        return aoi_eng.get_footprints_geojson(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/aoi/query")
def query_aoi_tiles(request: AOIQueryRequest):
    """
    Identifies intersecting Sentinel-2 tiles from the 909-tile catalog
    based on a WGS84 bounding box or polygon coordinates.
    """
    try:
        aoi_eng = get_aoi_engine()
        
        if request.polygon and len(request.polygon) >= 3:
            matches = aoi_eng.query_by_polygon(request.polygon, limit=request.limit or 30)
            query_type = "polygon"
        elif request.bbox and len(request.bbox) == 4:
            min_lon, min_lat, max_lon, max_lat = request.bbox
            matches = aoi_eng.query_by_bbox(min_lon, min_lat, max_lon, max_lat, limit=request.limit or 30)
            query_type = "bbox"
        else:
            raise HTTPException(status_code=400, detail="Must provide either valid 'bbox' [min_lon, min_lat, max_lon, max_lat] or 'polygon' [[lon, lat], ...].")

        return {
            "status": "success",
            "query_type": query_type,
            "total_matches": len(matches),
            "tiles": matches
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/aoi/analyze")
def analyze_selected_aoi(request: AOIAnalyzeRequest):
    """
    Executes tri-epoch multi-temporal change detection over the selected AOI or target tile.
    """
    try:
        aoi_eng = get_aoi_engine()
        result = aoi_eng.analyze_aoi(bbox_wgs84=request.bbox, tile_id=request.tile_id)
        
        # Log provenance
        prov_doc = create_provenance_document(
            action="aoi_temporal_analysis",
            source_files=[result.get("tile_id", "")],
            output_files=[],
            parameters={"tile_id": result.get("tile_id"), "target_wgs_bbox": result.get("target_wgs_bbox")}
        )
        provenance_collection.insert_one(prov_doc)

        return {
            "status": "success",
            "aoi_analysis": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# SEARCH HISTORY (MONGODB)
# =========================================================

@app.get("/api/search/history")
def get_search_history(limit: int = 30):
    """
    Returns chronological search history directly from MongoDB searches_collection.
    """
    try:
        cursor = searches_collection.find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
        docs = list(cursor)
        return {
            "status": "success",
            "database": "MongoDB (birdsey3.searches)",
            "total_searches": searches_collection.count_documents({}),
            "history": docs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# DATASET PROCESSING (BACKGROUND)
# =========================================================

def process_dataset_background(data_dir: str):
    import os
    from tiling import Tiler
    
    # 1. Tiling
    tiler = Tiler(data_dir)
    tiles_meta = tiler.generate_tiles()
    
    # Save tiles to DB
    for meta in tiles_meta:
        doc = create_tile_document(**meta)
        tiles_collection.update_one(
            {"tile_id": meta["tile_id"]}, 
            {"$set": doc}, 
            upsert=True
        )
        
    # 2. Embeddings
    emb = get_embedder()
    for meta in tiles_meta:
        vector = emb.extract_from_tile(meta["filepath"])
        vector_index.add_embedding(meta["tile_id"], vector)
        
    vector_index.save()
    
    # Log provenance
    prov_doc = create_provenance_document(
        action="dataset_ingestion",
        source_files=[data_dir],
        output_files=[meta["filepath"] for meta in tiles_meta],
        parameters={"tile_size": tiler.tile_size, "valid_threshold": tiler.valid_threshold}
    )
    provenance_collection.insert_one(prov_doc)


@app.post("/api/dataset/process")
def trigger_processing(background_tasks: BackgroundTasks):
    import os
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    background_tasks.add_task(process_dataset_background, data_dir)
    return {"message": "Dataset processing started in the background."}


# =========================================================
# TILE-LEVEL CHANGE DETECTION (2024 vs 2025)
# =========================================================

@app.get("/api/change/tile/{tile_id}")
def get_tile_change_analysis(tile_id: str):
    tile_meta = tiles_collection.find_one({"tile_id": tile_id}, {"_id": 0})
    if not tile_meta:
        raise HTTPException(status_code=404, detail="Tile ID not found in database.")
    
    bbox = tile_meta.get("bbox")
    if not bbox or len(bbox) != 4:
        raise HTTPException(status_code=400, detail="Tile missing valid bounding box.")
        
    from services import get_change_engine
    engine = get_change_engine()
    _, _, _, _, stats = engine.analyze_tile_by_bbox(bbox)
    
    # Log provenance
    prov_doc = create_provenance_document(
        action="tile_temporal_change_analysis",
        source_files=[tile_meta.get("filepath", "")],
        output_files=[],
        parameters={"tile_id": tile_id, "bbox": bbox, "epochs": ["2024-02-23", "2025-02-27"]}
    )
    provenance_collection.insert_one(prov_doc)
    
    return {
        "tile_id": tile_id,
        "bbox": bbox,
        "stats": stats
    }


# =========================================================

# TIMELINE
# =========================================================

@app.get("/api/timeline")
def get_timeline(query: str, from_year: int, to_year: int):
    timeline = build_timeline(query, from_year, to_year)
    return {
        "query": query,
        "from_year": from_year,
        "to_year": to_year,
        "timeline": timeline
    }


# =========================================================
# DASHBOARD
# =========================================================

@app.get("/api/dashboard")
def dashboard():
    documents = list(searches_collection.find())
    total_searches = len(documents)

    if total_searches == 0:
        return {
            "total_searches": 0,
            "locations_analyzed": 0,
            "average_change": 0,
            "average_years": 0,
            "recent_searches": []
        }

    locations = set()
    total_change = 0
    total_years = 0

    for document in documents:
        location = document.get("location")
        if location and location != "Not specified":
            locations.add(location)
        total_change += document.get("change", 0)
        total_years += document.get("years", 0)

    average_change = round(total_change / total_searches)
    average_years = round(total_years / total_searches)

    recent_documents = list(searches_collection.find().sort("created_at", -1).limit(10))
    recent_searches = []

    for document in recent_documents:
        recent_searches.append({
            "id": str(document["_id"]),
            "query": document.get("query"),
            "location": document.get("location", "Not specified"),
            "change": document.get("change", 0),
            "from": document.get("from_year"),
            "to": document.get("to_year"),
            "years": document.get("years", 0)
        })

    return {
        "total_searches": total_searches,
        "locations_analyzed": len(locations),
        "average_change": average_change,
        "average_years": average_years,
        "recent_searches": recent_searches
    }


# =========================================================
# CLUSTERING
# =========================================================

from clustering import LandscapeClusterEngine

cluster_engine = None

def get_cluster_engine():
    global cluster_engine
    if cluster_engine is None:
        cluster_engine = LandscapeClusterEngine()
    return cluster_engine

@app.get("/api/clustering/summary")
def get_clustering_summary():
    try:
        engine = get_cluster_engine()
        return engine.get_cluster_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/clustering/cluster/{cluster_id}")
def get_cluster_tiles(cluster_id: int):
    try:
        engine = get_cluster_engine()
        tiles = engine.get_tiles_in_cluster(cluster_id)
        return {"cluster_id": cluster_id, "tiles": tiles}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =========================================================
# TRI-EPOCH CHANGE ANALYSIS & TILE LISTING
# =========================================================

import base64
import io
from PIL import Image

def _pil_to_base64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")

@app.get("/api/tiles/list")
def list_available_tiles(limit: int = 100, sensor_filter: str = "ALL"):
    sf = sensor_filter.upper()
    if sf == "SAR":
        return {
            "total": 0,
            "sensor_filter": "SAR",
            "available": False,
            "message": "Sentinel-1 SAR C-band data is not currently available in local storage.",
            "tiles": []
        }
    docs = list(tiles_collection.find({}, {"tile_id": 1, "bbox": 1, "valid_ratio": 1, "crs": 1, "_id": 0}).limit(limit))
    return {
        "total": tiles_collection.count_documents({}),
        "sensor_filter": sf,
        "available": True,
        "tiles": docs
    }

@app.get("/api/change/tri_epoch/{tile_id}")
def get_tri_epoch_change(tile_id: str):
    from services import get_change_engine
    change_engine = get_change_engine()
    doc = tiles_collection.find_one({"tile_id": tile_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Tile not found")
        
    bbox = tuple(doc["bbox"])
    try:
        res = change_engine.analyze_tri_epoch_by_bbox(bbox)
        # Convert PIL images to Base64 strings for direct frontend display
        images_payload = {
            "epoch_2024": _pil_to_base64(res["rgb_2024"]),
            "epoch_2025": _pil_to_base64(res["rgb_2025"]),
            "epoch_2026": _pil_to_base64(res["rgb_2026"]),
            "change_mask": _pil_to_base64(res["change_rgb_cumulative"])
        }
        
        return {
            "tile_id": tile_id,
            "bbox": bbox,
            "images": images_payload,
            "stats_cumulative": res.get("stats_cumulative", {}),
            "stats_24_25": res.get("stats_24_25", {}),
            "stats_25_26": res.get("stats_25_26", {}),
            "temporal_persistence": res.get("temporal_persistence", {}),
            "explainability": res.get("stats_cumulative", {}).get("explainability", {}),
            "time_series": res.get("time_series", {})
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =========================================================
# PREPROCESSING LAB (PHASE 2)
# =========================================================

@app.get("/api/preprocessing/scenes")
def get_preprocessing_scenes():
    """
    Returns available Sentinel-2 SAFE products and real ESA XML metadata.
    """
    try:
        from services import get_preprocessing_lab_engine
        engine = get_preprocessing_lab_engine()
        return {
            "status": "success",
            "scenes": engine.get_available_scenes()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/preprocessing/pipeline")
def run_preprocessing_pipeline(request: PreprocessingPipelineRequest):
    """
    Executes the visible 8-stage preprocessing pipeline with real telemetry
    and raw vs processed visual previews.
    """
    try:
        from services import get_preprocessing_lab_engine
        engine = get_preprocessing_lab_engine()
        
        target_bbox = request.bbox
        if not target_bbox and request.tile_id:
            doc = tiles_collection.find_one({"tile_id": request.tile_id})
            if doc:
                target_bbox = doc.get("bbox")
                
        result = engine.run_pipeline(
            year=request.year,
            tile_id=request.tile_id,
            bbox=target_bbox,
            baseline_year=request.baseline_year
        )
        return {
            "status": "success",
            "pipeline": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# STATIC FILE MOUNTS & TILE IMAGES
# =========================================================
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
import os
import glob
import rasterio
import numpy as np

# Mount the static directory for Tech Spec
app.mount("/static_docs", StaticFiles(directory=r"c:\Users\Hiya\OneDrive\Desktop\BIRDSEYE"), name="static_docs")

# Mount frontend directory for one-click unified analyst console access
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/console", StaticFiles(directory=frontend_dir, html=True), name="console")


@app.get("/api/image/{tile_id}")
def get_tile_image(tile_id: str):
    doc = tiles_collection.find_one({"tile_id": tile_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Tile not found in database")
        
    filepath = doc.get("filepath")
    if not filepath or not os.path.exists(filepath):
        # Fallback to search in data/tiles
        matches = glob.glob(f"c:\\Users\\Hiya\\OneDrive\\Desktop\\BIRDSEYE\\data\\tiles\\*{tile_id}*.tif")
        if matches and os.path.exists(matches[0]):
            filepath = matches[0]
        else:
            raise HTTPException(status_code=404, detail="Image file not found on disk")
    
    try:
        with rasterio.open(filepath) as src:
            count = src.count
            if count >= 3:
                r = src.read(3)
                g = src.read(2)
                b = src.read(1)
            else:
                band = src.read(1)
                r, g, b = band, band, band

            def norm(arr):
                v = arr.astype(float)
                return np.clip(v / 2500.0 * 255.0, 0, 255).astype(np.uint8)

            rgb = np.stack([norm(r), norm(g), norm(b)], axis=-1)
            img = Image.fromarray(rgb)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            buf.seek(0)
            return StreamingResponse(buf, media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image decoding failed: {str(e)}")

@app.get("/api/clustering/pca")
def get_clustering_pca():
    from clustering import LandscapeClusterEngine
    engine = LandscapeClusterEngine()
    return engine.get_all_pca_data()

@app.get("/api/metrics/evaluate")
def evaluate_system_metrics():
    try:
        from evaluation import SystemEvaluator
        evaluator = SystemEvaluator()
        return evaluator.run_full_evaluation()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# PHASE 3: ACTIVE LEARNING, REVIEWS, EVIDENCE WORKSPACE & SAR
# =========================================================

@app.get("/api/sar/status")
def get_sar_status():
    """
    Returns honest SAR (Sentinel-1) status for the project environment.
    """
    return cases_service.get_sar_status()


@app.get("/api/sar/products")
def get_sar_products():
    """
    Returns list of local Sentinel-1 products discovered on disk.
    Returns honest empty list when no local SAR data exists.
    """
    from sar_engine import discover_sar_products
    return discover_sar_products()


@app.get("/api/sar/tile/{tile_id}")
def get_sar_tile_analysis_endpoint(tile_id: str):
    """
    Returns SAR analysis for a specific tile.
    Returns 404 when no real local SAR raster exists for tile_id.
    """
    from sar_engine import get_sar_tile_analysis
    res = get_sar_tile_analysis(tile_id)
    if not res.get("available"):
        raise HTTPException(status_code=404, detail=res.get("message", f"Sentinel-1 SAR raster is not cached locally for tile '{tile_id}'."))
    return res


@app.post("/api/cases")
def create_investigation_case(request: CaseCreateRequest):
    """
    Creates an investigation case and initializes Evidence Workspace.
    """
    try:
        case = cases_service.create_case(
            tile_id=request.tile_id,
            aoi_name=request.aoi_name,
            notes=request.notes
        )
        return {"status": "success", "case": case}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Case creation failed: {str(e)}")


@app.get("/api/cases")
def list_investigation_cases():
    """
    Lists all active investigation cases.
    """
    try:
        cases = cases_service.get_all_cases()
        return {"total": len(cases), "cases": cases}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Listing cases failed: {str(e)}")


@app.get("/api/cases/{case_id}")
def get_case_details(case_id: str):
    """
    Retrieves full Evidence Workspace for a case ID.
    """
    case = cases_service.get_case_by_id(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")
    return {"status": "success", "case": case}


@app.post("/api/cases/{case_id}/review")
def submit_case_review(case_id: str, request: AnalystReviewRequest):
    """
    Submits analyst decision (CONFIRM, REJECT, FLAG) with rationale for a case.
    """
    try:
        result = cases_service.submit_review(
            case_id=case_id,
            decision=request.decision,
            rationale=request.rationale,
            analyst_id=request.analyst_id,
            tile_id=request.tile_id,
            change_id=request.change_id
        )
        return result
    except KeyError as ke:
        raise HTTPException(status_code=404, detail=str(ke).strip("'"))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Review submission failed: {str(e)}")


@app.post("/api/reviews")
def submit_direct_review(request: AnalystReviewRequest):
    """
    Direct endpoint for submitting analyst decisions from any UI view.
    """
    try:
        result = cases_service.submit_review(
            case_id=request.case_id,
            decision=request.decision,
            rationale=request.rationale,
            analyst_id=request.analyst_id,
            tile_id=request.tile_id,
            change_id=request.change_id
        )
        return result
    except KeyError as ke:
        raise HTTPException(status_code=404, detail=str(ke).strip("'"))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Review submission failed: {str(e)}")


@app.get("/api/cases/{case_id}/review")
def get_current_case_review(case_id: str):
    """
    Retrieves the current active review for a case or candidate change.
    """
    try:
        review_data = cases_service.get_current_review(case_id)
        return review_data
    except KeyError as ke:
        raise HTTPException(status_code=404, detail=str(ke).strip("'"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Retrieving current review failed: {str(e)}")


@app.get("/api/cases/{case_id}/reviews")
def get_case_review_history(case_id: str):
    """
    Retrieves the complete audit history timeline of all review decisions for a case.
    """
    try:
        history_data = cases_service.get_review_history(case_id)
        return history_data
    except KeyError as ke:
        raise HTTPException(status_code=404, detail=str(ke).strip("'"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Retrieving review history failed: {str(e)}")


@app.get("/api/cases/{case_id}/provenance")
def get_case_provenance_endpoint(case_id: str):
    """
    Returns step-by-step 9-stage end-to-end provenance lineage chain with SHA-256 hashes and decision trace.
    """
    try:
        return cases_service.get_case_provenance(case_id)
    except KeyError as ke:
        raise HTTPException(status_code=404, detail=str(ke).strip("'"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Provenance retrieval failed: {str(e)}")


@app.get("/api/cases/{case_id}/report")
def get_case_report_endpoint(case_id: str):
    """
    Generates structured 20-section Satellite Incident Evidence Report in Markdown format.
    """
    try:
        return cases_service.export_case_report(case_id)
    except KeyError as ke:
        raise HTTPException(status_code=404, detail=str(ke).strip("'"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")


@app.get("/api/cases/{case_id}/evidence.json")
def get_case_evidence_json_endpoint(case_id: str):
    """
    Returns complete structured JSON evidence & provenance package for external verification.
    """
    try:
        return cases_service.get_case_evidence_json(case_id)
    except KeyError as ke:
        raise HTTPException(status_code=404, detail=str(ke).strip("'"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evidence JSON export failed: {str(e)}")


@app.get("/api/cases/{case_id}/export")
def export_case_report_endpoint(case_id: str, format: str = "markdown"):
    """
    Exports comprehensive evidence & analyst report with actual system data in markdown or json format.
    """
    try:
        if format.lower() == "json":
            return cases_service.get_case_evidence_json(case_id)
        return cases_service.export_case_report(case_id)
    except KeyError as ke:
        raise HTTPException(status_code=404, detail=str(ke).strip("'"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report export failed: {str(e)}")


@app.get("/api/cases/{case_id}/investigation")
def get_case_investigation(case_id: str):
    """
    Unified Evidence & Investigation Workspace endpoint.
    Aggregates location analysis, before/after imagery, multi-temporal change stats,
    8-stage preprocessing summary, false-alarm suppression, explainability,
    and analyst review state for one-screen inspection.
    """
    try:
        data = cases_service.get_case_investigation(case_id)
        return data
    except KeyError as ke:
        raise HTTPException(status_code=404, detail=str(ke).strip("'"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Investigation workspace retrieval failed: {str(e)}")




