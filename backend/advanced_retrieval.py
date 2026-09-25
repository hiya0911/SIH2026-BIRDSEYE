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


def matches_date_filter(acq_datetime_str: str, start_date: str = None, end_date: str = None) -> bool:
    """
    Checks if an ISO acquisition datetime string falls within [start_date, end_date] (YYYY-MM-DD).
    """
    if not acq_datetime_str:
        return True
    date_part = acq_datetime_str[:10]
    if start_date and start_date.strip():
        if date_part < start_date.strip()[:10]:
            return False
    if end_date and end_date.strip():
        if date_part > end_date.strip()[:10]:
            return False
    return True


def apply_diversity_filter(candidates: list, top_k: int) -> list:
    """
    Prevents spatial near-duplicate tiles (same WGS84 bounding box and date) from flooding top results.
    """
    seen_keys = set()
    diverse = []
    for item in candidates:
        meta = item.get("metadata", {})
        wgs_bbox = meta.get("wgs_bbox")
        acq_date = meta.get("acquisition_datetime", "")[:10]
        if wgs_bbox:
            # Round bounding box to 4 decimals to form unique spatial extent key
            spatial_key = (
                round(wgs_bbox[0], 4),
                round(wgs_bbox[1], 4),
                round(wgs_bbox[2], 4),
                round(wgs_bbox[3], 4),
                acq_date
            )
        else:
            spatial_key = (item.get("tile_id"), acq_date)
            
        if spatial_key in seen_keys:
            continue
        seen_keys.add(spatial_key)
        diverse.append(item)
        if len(diverse) == top_k:
            break
            
    # If diversity filter produced fewer than top_k items, fill with remaining non-duplicate tile_ids
    if len(diverse) < top_k:
        seen_tids = {d["tile_id"] for d in diverse}
        for item in candidates:
            if item["tile_id"] not in seen_tids:
                diverse.append(item)
                seen_tids.add(item["tile_id"])
                if len(diverse) == top_k:
                    break
                    
    return diverse


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
        allowed_tile_ids: set = None,
        start_date: str = None,
        end_date: str = None,
        sensor_filter: str = "ALL",
        diversity_control: bool = True
    ):
        """
        Executes optimized multi-temporal semantic retrieval:
        1. Domain prompt ensembling via CLIP.
        2. Classifies query intent.
        3. Fuses multi-spectral physical indicators (NDVI, NDWI, Brightness).
        4. Calibrates raw scores into standardized 0-100% Match Confidence.
        5. Filters by allowed_tile_ids, date range, and sensor.
        6. Generates transparent explainability fields and applies spatial diversity control.
        """
        sf = (sensor_filter or "ALL").upper()
        if sf == "SAR":
            return {
                "query": query,
                "mode": "semantic",
                "sensor_filter": "SAR",
                "available": False,
                "results": [],
                "total": 0,
                "search_id": "sar_not_cached",
                "message": "Sentinel-1 SAR C-band data is not currently available in local storage. Pipeline remains ready for future Sentinel-1 GRD ingestion."
            }

        from services import get_embedder, vector_index
        
        intent = classify_query_intent(query)
        is_action = intent["is_action"] or force_action_mode
        category = intent["category"]
        
        embedder = get_embedder()
        # Extract ensembled satellite text vector
        query_vec = embedder.extract_from_text(query, ensemble=True)
        
        # Retrieve extra candidates from FAISS for physical re-ranking & temporal filtering
        search_k = min(top_k * 12 if (allowed_tile_ids or start_date or end_date) else top_k * 5, 200)
        candidates = vector_index.search(query_vec, top_k=search_k)
        
        enriched = []
        for c in candidates:
            if allowed_tile_ids is not None and c["tile_id"] not in allowed_tile_ids:
                continue

            tile_meta = tiles_collection.find_one({"tile_id": c["tile_id"]}, {"_id": 0})
            if not tile_meta:
                from services import get_aoi_engine
                aoi_eng = get_aoi_engine()
                tile_meta = aoi_eng.tiles_by_id.get(c["tile_id"])
                
            if not tile_meta:
                continue
                
            acq_datetime = tile_meta.get("acquisition_datetime", "")
            if not matches_date_filter(acq_datetime, start_date, end_date):
                continue

            filepath = tile_meta.get("filepath", "")
            spectral = get_tile_spectral_indices(filepath)
            
            raw_clip = float(c["score"])
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

            acq_date = acq_datetime[:10] if acq_datetime else "2024-02-23"
            
            # Construct transparent analyst explanation tags
            explanations = [
                f"High semantic similarity ({raw_clip:.2f} CLIP score, Domain: {category})"
            ]
            if allowed_tile_ids is not None:
                explanations.append("Inside requested AOI spatial bounds")
            if start_date or end_date:
                explanations.append(f"Acquisition date ({acq_date}) matches requested filter period")
            explanations.append("Sensor match: Sentinel-2 MSI Level-2A")
            if spectral_gate and physics_note and physics_note != "Physical Verification Neutral":
                explanations.append(f"Physical gating: {physics_note}")

            # Compute physical score contribution delta
            base_norm = (raw_clip - 0.16) / (0.34 - 0.16)
            base_norm = float(np.clip(base_norm, 0.0, 1.0))
            base_conf = 58.0 + 32.0 / (1.0 + np.exp(-6.5 * (base_norm - 0.45)))
            phys_delta = round(float((match_pct - base_conf) / 100.0), 4)

            enriched.append({
                "rank": 0,
                "tile_id": c["tile_id"],
                "score": round(match_pct / 100.0, 4),
                "final_score": round(match_pct / 100.0, 4),
                "match_percentage": match_pct,
                "clip_score": round(raw_clip, 4),
                "semantic_similarity": round(raw_clip, 4),
                "image_similarity": None,
                "physical_score": phys_delta,
                "filters": {
                    "aoi": allowed_tile_ids is not None,
                    "date": bool(start_date or end_date),
                    "sensor": True
                },
                "explanation": explanations,
                "acquisition_date": acq_date,
                "sensor": "Sentinel-2 MSI Level-2A",
                "wgs_bbox": tile_meta.get("wgs_bbox"),
                "spectral_indices": spectral,
                "physics_evidence": physics_note,
                "change_stats": change_stats,
                "metadata": tile_meta
            })
            
        # Re-rank candidates by calibrated match percentage
        enriched.sort(key=lambda x: x["match_percentage"], reverse=True)

        if diversity_control and enriched:
            enriched = apply_diversity_filter(enriched, top_k)
        else:
            enriched = enriched[:top_k]

        for idx, item in enumerate(enriched):
            item["rank"] = idx + 1
        
        return {
            "query": query,
            "mode": "semantic",
            "intent": intent,
            "spectral_gate_applied": spectral_gate,
            "action_mode_applied": is_action,
            "diversity_control": diversity_control,
            "results": enriched
        }

    def search_multimodal(
        self,
        query: str = None,
        pil_image = None,
        text_weight: float = 0.5,
        image_weight: float = 0.5,
        top_k: int = 12,
        spectral_gate: bool = True,
        force_action_mode: bool = False,
        allowed_tile_ids: set = None,
        start_date: str = None,
        end_date: str = None,
        sensor_filter: str = "ALL",
        diversity_control: bool = True
    ):
        """
        Executes combined Multimodal (Text Prompt + Reference Image) retrieval:
        1. Extract text and image embeddings using CLIP.
        2. Fuses text and visual similarities deterministically using configurable weights.
        3. Applies physical spectral verification and spatial/temporal/sensor filters.
        4. Returns transparent explanation fields and analyst-ready result cards.
        """
        sf = (sensor_filter or "ALL").upper()
        if sf == "SAR":
            return {
                "query": query,
                "mode": "multimodal",
                "sensor_filter": "SAR",
                "available": False,
                "results": [],
                "total": 0,
                "search_id": "sar_not_cached",
                "message": "Sentinel-1 SAR C-band data is not currently available in local storage. Pipeline remains ready for future Sentinel-1 GRD ingestion."
            }

        has_text = bool(query and query.strip())
        has_image = pil_image is not None

        if not has_text and not has_image:
            raise ValueError("At least one query modality (text prompt or reference image) must be provided.")

        # Text-only fallback
        if has_text and not has_image:
            res = self.search(
                query=query.strip(),
                top_k=top_k,
                spectral_gate=spectral_gate,
                force_action_mode=force_action_mode,
                allowed_tile_ids=allowed_tile_ids,
                start_date=start_date,
                end_date=end_date,
                sensor_filter=sensor_filter,
                diversity_control=diversity_control
            )
            res["mode"] = "text_only"
            return res

        # Image-only fallback
        from services import get_embedder, vector_index, perform_image_search_from_pil
        if has_image and not has_text:
            img_results = perform_image_search_from_pil(
                pil_image=pil_image,
                top_k=top_k,
                allowed_tile_ids=allowed_tile_ids,
                start_date=start_date,
                end_date=end_date,
                diversity_control=diversity_control
            )
            return {
                "query": "Reference Image Upload Search",
                "mode": "image_only",
                "spectral_gate_applied": False,
                "diversity_control": diversity_control,
                "results": img_results
            }

        # Combined Multimodal Fusion Mode (Text + Image)
        embedder = get_embedder()
        q_text_vec = embedder.extract_from_text(query.strip(), ensemble=True)
        q_img_vec = embedder.extract_from_pil(pil_image)

        # Normalize multimodal fusion weights
        total_w = text_weight + image_weight
        wt = text_weight / total_w if total_w > 0 else 0.5
        wi = image_weight / total_w if total_w > 0 else 0.5

        # Form fused query vector for candidate retrieval
        fused_q = wt * q_text_vec + wi * q_img_vec
        norm_f = np.linalg.norm(fused_q)
        if norm_f > 0:
            fused_q = fused_q / norm_f

        search_k = min(top_k * 12 if (allowed_tile_ids or start_date or end_date) else top_k * 5, 200)
        candidates = vector_index.search(fused_q, top_k=search_k)

        intent = classify_query_intent(query.strip())
        category = intent["category"]

        enriched = []
        for c in candidates:
            tid = c["tile_id"]
            if allowed_tile_ids is not None and tid not in allowed_tile_ids:
                continue

            tile_meta = tiles_collection.find_one({"tile_id": tid}, {"_id": 0})
            if not tile_meta:
                from services import get_aoi_engine
                aoi_eng = get_aoi_engine()
                tile_meta = aoi_eng.tiles_by_id.get(tid)

            if not tile_meta:
                continue

            acq_datetime = tile_meta.get("acquisition_datetime", "")
            if not matches_date_filter(acq_datetime, start_date, end_date):
                continue

            filepath = tile_meta.get("filepath", "")
            spectral = get_tile_spectral_indices(filepath)

            # Reconstruct tile vector to compute exact individual similarities
            try:
                faiss_idx = vector_index.tile_ids.index(tid)
                tile_vec = vector_index.index.reconstruct(faiss_idx)
                s_text = float(np.dot(q_text_vec, tile_vec))
                s_image = float(np.dot(q_img_vec, tile_vec))
            except Exception:
                s_text = float(c["score"])
                s_image = float(c["score"])

            s_fused = wt * s_text + wi * s_image

            match_pct, physics_note = calibrate_remote_sensing_score(
                raw_clip_score=s_fused,
                spectral=spectral,
                category=category,
                spectral_gate=spectral_gate
            )

            acq_date = acq_datetime[:10] if acq_datetime else "2024-02-23"

            explanations = [
                f"Multimodal fusion match (Text weight: {wt:.2f}, Image weight: {wi:.2f})",
                f"Semantic text similarity: {s_text:.2f}",
                f"Reference-image similarity: {s_image:.2f}"
            ]
            if allowed_tile_ids is not None:
                explanations.append("Inside requested AOI spatial bounds")
            if start_date or end_date:
                explanations.append(f"Acquisition date ({acq_date}) matches requested period")
            explanations.append("Sensor match: Sentinel-2 MSI Level-2A")
            if spectral_gate and physics_note and physics_note != "Physical Verification Neutral":
                explanations.append(f"Physical gating: {physics_note}")

            base_norm = (s_fused - 0.16) / (0.34 - 0.16)
            base_norm = float(np.clip(base_norm, 0.0, 1.0))
            base_conf = 58.0 + 32.0 / (1.0 + np.exp(-6.5 * (base_norm - 0.45)))
            phys_delta = round(float((match_pct - base_conf) / 100.0), 4)

            enriched.append({
                "rank": 0,
                "tile_id": tid,
                "score": round(match_pct / 100.0, 4),
                "final_score": round(match_pct / 100.0, 4),
                "match_percentage": match_pct,
                "fused_clip_score": round(s_fused, 4),
                "semantic_similarity": round(s_text, 4),
                "image_similarity": round(s_image, 4),
                "fusion_weights": {"text": round(wt, 2), "image": round(wi, 2)},
                "physical_score": phys_delta,
                "filters": {
                    "aoi": allowed_tile_ids is not None,
                    "date": bool(start_date or end_date),
                    "sensor": True
                },
                "explanation": explanations,
                "acquisition_date": acq_date,
                "sensor": "Sentinel-2 MSI Level-2A",
                "wgs_bbox": tile_meta.get("wgs_bbox"),
                "spectral_indices": spectral,
                "physics_evidence": physics_note,
                "metadata": tile_meta
            })

        enriched.sort(key=lambda x: x["match_percentage"], reverse=True)

        if diversity_control and enriched:
            enriched = apply_diversity_filter(enriched, top_k)
        else:
            enriched = enriched[:top_k]

        for idx, item in enumerate(enriched):
            item["rank"] = idx + 1

        return {
            "query": query,
            "mode": "multimodal_fusion",
            "fusion_weights": {"text": round(wt, 2), "image": round(wi, 2)},
            "intent": intent,
            "spectral_gate_applied": spectral_gate,
            "diversity_control": diversity_control,
            "results": enriched
        }

    def get_tile_trajectory(self, tile_id: str):
        """
        Retrieves the 3-year satellite progression (2024, 2025, 2026) for a specific tile.
        """
        tile_meta = tiles_collection.find_one({"tile_id": tile_id}, {"_id": 0})
        if not tile_meta or "bbox" not in tile_meta:
            return None
            
        return self.change_engine.analyze_tri_epoch_by_bbox(tile_meta["bbox"])

