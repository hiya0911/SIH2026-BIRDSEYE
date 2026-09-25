import os
import rasterio
import numpy as np
from database import tiles_collection
from vector_index import VectorIndex
from embeddings import EmbeddingExtractor
from change_detection import TemporalChangeEngine

ACTION_KEYWORDS = [
    "new", "newly", "construction", "built", "expansion", "expanding",
    "cleared", "clearance", "loss", "lost", "shrinkage", "shrinking",
    "growth", "growing", "change", "changed", "sprawl", "deforestation"
]

WATER_KEYWORDS = [
    "water", "river", "lake", "wetland", "waterway", "channel", "canal",
    "coastal", "bay", "sea", "ocean", "stream", "reservoir", "marsh", "riparian"
]

VEG_KEYWORDS = [
    "forest", "vegetation", "green", "agriculture", "crop", "mangrove",
    "tree", "canopy", "grassland", "chlorophyll", "lush", "woodland", "foliage"
]

BUILT_KEYWORDS = [
    "building", "urban", "structure", "city", "road", "house", "concrete",
    "highway", "infrastructure", "industrial", "settlement", "pavement", "town"
]

BARREN_KEYWORDS = [
    "barren", "sand", "soil", "rock", "rocky", "desert", "dry", "arid",
    "bare", "exposed", "quarry"
]

def classify_query_intent(query: str):
    q_lower = query.lower()
    
    is_action = any(k in q_lower for k in ACTION_KEYWORDS)
    
    category = "GENERAL"
    if any(k in q_lower for k in WATER_KEYWORDS):
        category = "WATER"
    elif any(k in q_lower for k in VEG_KEYWORDS):
        category = "VEGETATION"
    elif any(k in q_lower for k in BUILT_KEYWORDS):
        category = "BUILT_UP"
    elif any(k in q_lower for k in BARREN_KEYWORDS):
        category = "BARREN"
        
    return {
        "is_action": is_action,
        "category": category
    }

def get_tile_spectral_indices(tile_path: str):
    """
    Computes mean NDVI, NDWI, and Surface Brightness directly from the 4-band tile GeoTIFF.
    B02=0 (Blue), B03=1 (Green), B04=2 (Red), B08=3 (NIR)
    """
    if not tile_path or not os.path.exists(tile_path):
        return {"ndvi": 0.0, "ndwi": 0.0, "brightness": 0.0}
        
    try:
        with rasterio.open(tile_path) as src:
            data = src.read().astype(np.float32)
            
        b02, b03, b04, b08 = data[0], data[1], data[2], data[3]
        valid = (b02 > 0) | (b03 > 0) | (b04 > 0) | (b08 > 0)
        
        if not np.any(valid):
            return {"ndvi": 0.0, "ndwi": 0.0, "brightness": 0.0}
            
        ndvi = (b08[valid] - b04[valid]) / (b08[valid] + b04[valid] + 1e-6)
        ndwi = (b03[valid] - b08[valid]) / (b03[valid] + b08[valid] + 1e-6)
        brightness = (b02[valid] + b03[valid] + b04[valid]) / 3.0
        
        return {
            "ndvi": round(float(np.mean(ndvi)), 4),
            "ndwi": round(float(np.mean(ndwi)), 4),
            "brightness": round(float(np.mean(brightness)), 1)
        }
    except Exception:
        return {"ndvi": 0.0, "ndwi": 0.0, "brightness": 0.0}

def calibrate_remote_sensing_score(
    raw_clip_score: float, 
    spectral: dict, 
    category: str, 
    spectral_gate: bool
) -> tuple:
    """
    Calibrates raw CLIP cosine similarity into a standardized Remote Sensing Match Percentage (0-100%).
    Fuses vision-language zero-shot alignment with physical multi-spectral verification (NDVI/NDWI).
    """
    # 1. Base calibration of raw CLIP similarity
    # In CLIP hypersphere, domain noise is ~0.15, good match is ~0.26, optimal is 0.32+
    clip_norm = (raw_clip_score - 0.16) / (0.34 - 0.16)
    clip_norm = float(np.clip(clip_norm, 0.0, 1.0))
    
    # Sigmoidal mapping centered at 78%
    base_confidence = 58.0 + 32.0 / (1.0 + np.exp(-6.5 * (clip_norm - 0.45)))
    
    if not spectral_gate:
        final_pct = round(float(np.clip(base_confidence, 10.0, 98.5)), 1)
        return final_pct, "Standard Vector Similarity"
        
    # 2. Multi-Spectral Physical Agreement Verification
    physics_boost = 0.0
    evidence_tags = []
    
    ndvi = spectral.get("ndvi", 0.0)
    ndwi = spectral.get("ndwi", 0.0)
    brightness = spectral.get("brightness", 0.0)
    
    if category == "VEGETATION":
        if ndvi > 0.40:
            boost = min(12.0, 5.0 + (ndvi - 0.40) * 25.0)
            physics_boost += boost
            evidence_tags.append(f"Photosynthetic Red-Edge (NDVI: {ndvi:.2f})")
        elif ndvi < 0.18:
            physics_boost -= 30.0
            evidence_tags.append(f"Rejected Non-Vegetation (NDVI: {ndvi:.2f})")
        else:
            evidence_tags.append(f"Moderate Chlorophyll (NDVI: {ndvi:.2f})")
            
    elif category == "WATER":
        if ndwi > 0.05:
            boost = min(14.0, 6.0 + (ndwi - 0.05) * 35.0)
            physics_boost += boost
            evidence_tags.append(f"Water Spectral Signature (NDWI: {ndwi:.2f})")
        elif ndwi < -0.15:
            physics_boost -= 35.0
            evidence_tags.append(f"Rejected Terrestrial Signature (NDWI: {ndwi:.2f})")
            
    elif category == "BUILT_UP":
        if brightness > 1350 and ndvi < 0.32:
            physics_boost += 8.0
            evidence_tags.append(f"Impervious Reflectance (Brightness: {brightness:.0f})")
        elif ndvi > 0.45:
            physics_boost -= 20.0
            evidence_tags.append(f"Suppressed (Dense Canopy, NDVI: {ndvi:.2f})")
            
    elif category == "BARREN":
        if brightness > 1400 and ndvi < 0.20:
            physics_boost += 10.0
            evidence_tags.append(f"Exposed Substrate (NDVI: {ndvi:.2f})")
        elif ndvi > 0.35:
            physics_boost -= 25.0
            
    final_pct = round(float(np.clip(base_confidence + physics_boost, 12.0, 99.1)), 1)
    evidence_str = " | ".join(evidence_tags) if evidence_tags else "Physical Verification Neutral"
    
    return final_pct, evidence_str


class AdvancedSemanticEngine:
    def __init__(self):
        self.change_engine = TemporalChangeEngine()

    def search(
        self,
        query: str,
        top_k: int = 12,
        spectral_gate: bool = True,
        force_action_mode: bool = False,
        target_year: int = None,
        allowed_tile_ids: set = None
    ):
        """
        Executes optimized multi-temporal semantic retrieval:
        1. Domain prompt ensembling via CLIP.
        2. Classifies query intent.
        3. Fuses multi-spectral physical indicators (NDVI, NDWI, Brightness).
        4. Calibrates raw scores into standardized 0-100% Match Confidence.
        5. Optionally filters by allowed_tile_ids when AOI spatial restriction is active.
        """
        from services import get_embedder, vector_index
        
        intent = classify_query_intent(query)
        is_action = intent["is_action"] or force_action_mode
        category = intent["category"]
        
        embedder = get_embedder()
        # Extract ensembled satellite text vector
        query_vec = embedder.extract_from_text(query, ensemble=True)
        
        # Retrieve extra candidates from FAISS for physical re-ranking
        search_k = min(top_k * 10 if allowed_tile_ids else top_k * 4, 100)
        candidates = vector_index.search(query_vec, top_k=search_k)
        
        enriched = []
        for c in candidates:
            if allowed_tile_ids is not None and c["tile_id"] not in allowed_tile_ids:
                continue

            tile_meta = tiles_collection.find_one({"tile_id": c["tile_id"]}, {"_id": 0})
            if not tile_meta:
                continue
                
            filepath = tile_meta.get("filepath", "")
            spectral = get_tile_spectral_indices(filepath)
            
            raw_clip = c["score"]
            match_pct, physics_note = calibrate_remote_sensing_score(
                raw_clip_score=raw_clip,
                spectral=spectral,
                category=category,
                spectral_gate=spectral_gate
            )
            
            # If dynamic action query: evaluate 2024 -> 2026 physical change delta
            change_stats = None
            if is_action and tile_meta.get("bbox"):
                try:
                    _, _, _, _, change_stats = self.change_engine.analyze_tile_by_bbox(
                        tile_meta["bbox"], 
                        year_a=2024, 
                        year_b=2026
                    )
                    # Boost score if tile actually underwent physical change
                    if category == "BUILT_UP" and change_stats["built_up_expansion_pct"] > 0.05:
                        match_pct = min(99.0, match_pct + change_stats["built_up_expansion_pct"] * 3.0)
                    elif category == "VEGETATION" and change_stats["vegetation_loss_pct"] > 0.1:
                        match_pct = min(99.0, match_pct + change_stats["vegetation_loss_pct"] * 3.0)
                    elif change_stats["total_change_pct"] > 2.0:
                        match_pct = min(99.0, match_pct + change_stats["total_change_pct"] * 1.5)
                except Exception:
                    pass
                    
            enriched.append({
                "tile_id": c["tile_id"],
                "score": round(match_pct / 100.0, 4),
                "match_percentage": match_pct,
                "clip_score": round(raw_clip, 4),
                "spectral_indices": spectral,
                "physics_evidence": physics_note,
                "change_stats": change_stats,
                "metadata": tile_meta
            })
            
        # Re-rank candidates by calibrated match percentage
        enriched.sort(key=lambda x: x["match_percentage"], reverse=True)
        
        return {
            "query": query,
            "intent": intent,
            "spectral_gate_applied": spectral_gate,
            "action_mode_applied": is_action,
            "results": enriched[:top_k]
        }

    def get_tile_trajectory(self, tile_id: str):
        """
        Retrieves the 3-year satellite progression (2024, 2025, 2026) for a specific tile.
        """
        tile_meta = tiles_collection.find_one({"tile_id": tile_id}, {"_id": 0})
        if not tile_meta or "bbox" not in tile_meta:
            return None
            
        return self.change_engine.analyze_tri_epoch_by_bbox(tile_meta["bbox"])
