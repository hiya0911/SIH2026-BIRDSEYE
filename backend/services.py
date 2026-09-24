import hashlib
import os
from database import tiles_collection
from vector_index import VectorIndex
from embeddings import EmbeddingExtractor

# Global instances for offline search
INDEX_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "index")
try:
    vector_index = VectorIndex(index_dir=INDEX_DIR)
    # Lazy load the model only when needed to save memory during startup
    embedder = None
except Exception as e:
    print(f"Warning: Could not initialize vector index: {e}")
    vector_index = None
    embedder = None

def get_embedder():
    global embedder
    if embedder is None:
        embedder = EmbeddingExtractor()
    return embedder

# Lazy load change engine
change_engine = None
def get_change_engine():
    global change_engine
    if change_engine is None:
        from change_detection import TemporalChangeEngine
        change_engine = TemporalChangeEngine()
    return change_engine

def calculate_change(
    query: str,
    location: str,
    from_year: int,
    to_year: int
):
    """
    Evaluates multi-temporal change using real Sentinel-2 satellite data across 2024, 2025, and 2026.
    """
    engine = get_change_engine()
    available_years = engine.get_available_years()

    if from_year in available_years and to_year in available_years and from_year != to_year:
        # Sample representative urban/environmental tile in Kolkata
        sample_bbox = [605120.0, 2597480.0, 607680.0, 2600040.0]
        _, _, _, _, stats = engine.analyze_tile_by_bbox(sample_bbox, year_a=from_year, year_b=to_year)
        
        return {
            "status": "derived_from_satellite_observations",
            "message": f"Calculated from Sentinel-2 L2A acquisitions ({from_year} vs {to_year}).",
            "from_year": from_year,
            "to_year": to_year,
            "total": int(round(stats["total_change_pct"])),
            "builtUp": int(round(stats["built_up_expansion_pct"])),
            "vegetation": int(round(stats["vegetation_loss_pct"] + stats["vegetation_gain_pct"])),
            "water": int(round(stats["water_variation_pct"])),
            "confidence_score": stats["confidence_score"],
            "evidence_details": stats
        }

    # If asking for years not in available datasets:
    return {
        "status": "requires_additional_temporal_observations",
        "message": f"Temporal change analysis between {from_year} and {to_year} requires additional temporal observations. Observations currently staged: {available_years}.",
        "total": 0,
        "builtUp": 0,
        "vegetation": 0,
        "water": 0
    }

def build_timeline(
    query: str,
    from_year: int,
    to_year: int
):
    timeline = [
        {
            "year": 2024,
            "description": "Baseline observation: 2024-02-23 (Sentinel-2B MSI Level-2A, Kolkata)."
        },
        {
            "year": 2025,
            "description": "Comparison observation: 2025-02-27 (Sentinel-2B MSI Level-2A, 2.66% cloud cover)."
        },
        {
            "year": 2026,
            "description": "Latest observation: 2026-02-27 (Sentinel-2C MSI Level-2A, Kolkata)."
        }
    ]
    return [t for t in timeline if from_year <= t["year"] <= to_year] or timeline


def create_location_label(location):
    if not location:
        return "Not specified"

    parts = [
        location.name,
        location.state,
        location.country
    ]

    return ", ".join(
        part for part in parts if part
    )

# Lazy load advanced engine
advanced_semantic_engine = None
def get_advanced_engine():
    global advanced_semantic_engine
    if advanced_semantic_engine is None:
        from advanced_retrieval import AdvancedSemanticEngine
        advanced_semantic_engine = AdvancedSemanticEngine()
    return advanced_semantic_engine

def perform_semantic_search(
    query: str, 
    top_k: int = 5,
    spectral_gate: bool = True,
    force_action: bool = False,
    target_year: int = None
):
    """
    Advanced multi-temporal semantic search with spectral gating and dynamic change ranking.
    """
    engine = get_advanced_engine()
    search_res = engine.search(
        query=query,
        top_k=top_k,
        spectral_gate=spectral_gate,
        force_action_mode=force_action,
        target_year=target_year
    )
    return search_res["results"]


def perform_image_search(tile_id: str, top_k: int = 5):
    """
    Given a tile ID, finds similar tiles based on their embeddings.
    """
    if not vector_index:
        raise RuntimeError("Vector index is not initialized.")
    
    tile_meta = tiles_collection.find_one({"tile_id": tile_id})
    if not tile_meta:
        raise ValueError(f"Tile {tile_id} not found in database.")
    
    filepath = tile_meta["filepath"]
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Tile file {filepath} missing on disk.")

    emb = get_embedder()
    query_vector = emb.extract_from_tile(filepath)
    
    # We ask for top_k + 1 because the query itself will likely be the top result
    results = vector_index.search(query_vector, top_k + 1)
    
    hydrated = []
    for r in results:
        if r["tile_id"] == tile_id:
            continue # skip self
        t_meta = tiles_collection.find_one({"tile_id": r["tile_id"]}, {"_id": 0})
        if t_meta:
            hydrated.append({
                "tile_id": r["tile_id"],
                "score": r["score"],
                "metadata": t_meta
            })
            if len(hydrated) == top_k:
                break
    return hydrated