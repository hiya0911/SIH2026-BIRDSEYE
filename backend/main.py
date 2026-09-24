from typing import Optional
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

from database import searches_collection, tiles_collection, provenance_collection
from models import create_search_document, create_tile_document, create_provenance_document
from schemas import SearchRequest, SemanticSearchRequest, ImageSearchRequest
from services import (
    calculate_change,
    build_timeline,
    create_location_label,
    perform_semantic_search,
    perform_image_search,
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
def list_available_tiles(limit: int = 100):
    docs = list(tiles_collection.find({}, {"tile_id": 1, "bbox": 1, "valid_ratio": 1, "crs": 1, "_id": 0}).limit(limit))
    return {
        "total": tiles_collection.count_documents({}),
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
            "time_series": res.get("time_series", {})
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


