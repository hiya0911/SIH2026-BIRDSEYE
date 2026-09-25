import sys
import os
import glob
import time

# Ensure UTF-8 output on Windows console
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

print("=" * 70)
print("BIRDSEYE3 PHASE 3A — CORE STABILIZATION TEST SUITE")
print("Focus: Rasterio MemoryFile Fix & Phase 1/2 Regression Verification")
print("=" * 70)

def run_test(name, test_fn):
    print(f"\n[RUNNING TEST] {name}...")
    t0 = time.time()
    try:
        test_fn()
        dt = time.time() - t0
        print(f"[PASS] {name} ({dt:.3f}s)")
        return True
    except Exception as e:
        dt = time.time() - t0
        print(f"[FAIL] {name} ({dt:.3f}s): {e}")
        import traceback
        traceback.print_exc()
        return False

passed_tests = 0
total_tests = 6

# ---------------------------------------------------------
# 1. Backend Startup Test
# ---------------------------------------------------------
def test_backend_startup():
    r1 = client.get("/")
    assert r1.status_code == 200, f"Expected 200 on /, got {r1.status_code}"
    r2 = client.get("/health")
    assert r2.status_code == 200, f"Expected 200 on /health, got {r2.status_code}"
    data = r2.json()
    assert data.get("status") == "healthy"
    assert data.get("mongodb") == "connected"
    print(f"       Backend online & MongoDB connected: {data}")

if run_test("1. Backend Startup & Health Test", test_backend_startup):
    passed_tests += 1

# ---------------------------------------------------------
# 2. Image Upload Search Test (Rasterio MemoryFile Fix)
# ---------------------------------------------------------
def test_image_upload():
    sample_tiles = glob.glob(r"c:\Users\Hiya\OneDrive\Desktop\BIRDSEYE\data\tiles\*.tif")
    assert len(sample_tiles) > 0, "No sample tiles found on disk"
    test_tile = sample_tiles[0]
    filename = os.path.basename(test_tile)
    size_bytes = os.path.getsize(test_tile)
    print(f"       Uploading real tile: {filename} ({size_bytes} bytes)")
    
    with open(test_tile, "rb") as f:
        r = client.post("/api/search/image/upload", files={"file": (filename, f, "image/tiff")}, data={"top_k": 5})
    
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("status") == "success"
    assert "preview_image" in data and len(data["preview_image"]) > 100
    
    results = data.get("results", [])
    assert len(results) > 0, "Expected FAISS search results"
    
    target_id = filename.replace("tile_", "").replace(".tif", "")
    top_match = results[0]
    
    assert top_match["tile_id"] == target_id, f"Expected self match {target_id}, got {top_match['tile_id']}"
    assert top_match["similarity_percentage"] >= 95.0, f"Expected similarity >=95%, got {top_match['similarity_percentage']}%"
    assert "score" in top_match
    
    print(f"       Embedding extracted & FAISS retrieval verified!")
    print(f"       Rank #1 Match: {top_match['tile_id']} (Similarity: {top_match['similarity_percentage']}%, Cosine Score: {top_match['score']})")

if run_test("2. Image Upload Search Test (MemoryFile + CLIP + FAISS)", test_image_upload):
    passed_tests += 1

# ---------------------------------------------------------
# 3. Semantic Retrieval Regression Test
# ---------------------------------------------------------
def test_semantic_retrieval_regression():
    r = client.post("/api/search/semantic", json={
        "query": "Dense forest canopy and vegetative greening",
        "top_k": 5,
        "spectral_gate": True,
        "action_mode": False
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert "results" in data
    results = data.get("results", [])
    assert len(results) > 0, "Expected semantic search results"
    print(f"       Semantic Search verified: Query='Dense forest canopy', {len(results)} matches returned")

if run_test("3. Semantic Retrieval Regression Test", test_semantic_retrieval_regression):
    passed_tests += 1

# ---------------------------------------------------------
# 4. AOI Regression Test
# ---------------------------------------------------------
def test_aoi_regression():
    # Footprints
    r1 = client.get("/api/aoi/footprints?limit=10")
    assert r1.status_code == 200
    footprints = r1.json().get("features", [])
    assert len(footprints) == 10
    
    # Query BBox
    r2 = client.post("/api/aoi/query", json={"bbox": [88.34, 22.55, 88.38, 22.60], "limit": 5})
    assert r2.status_code == 200
    tiles = r2.json().get("tiles", [])
    assert len(tiles) > 0
    
    # AOI Analysis
    r3 = client.post("/api/aoi/analyze", json={"tile_id": "e87b4d6c-9cdb-4293-8a8b-7ad7a5af6e43"})
    assert r3.status_code == 200
    analysis = r3.json().get("aoi_analysis", {})
    assert "stats_cumulative" in analysis
    
    print("       AOI Footprints, BBox Query & AOI Analysis regression passed")

if run_test("4. AOI Footprints & Query Regression Test", test_aoi_regression):
    passed_tests += 1

# ---------------------------------------------------------
# 5. Phase 2 Preprocessing Regression Test
# ---------------------------------------------------------
def test_phase2_preprocessing_regression():
    r1 = client.get("/api/preprocessing/scenes")
    assert r1.status_code == 200
    scenes = r1.json().get("scenes", [])
    assert len(scenes) >= 2
    
    r2 = client.post("/api/preprocessing/pipeline", json={"year": 2026, "tile_id": "e87b4d6c-9cdb-4293-8a8b-7ad7a5af6e43"})
    assert r2.status_code == 200
    res = r2.json()
    assert res.get("status") == "success"
    pipeline_data = res.get("pipeline", {})
    assert "stages" in pipeline_data
    assert len(pipeline_data["stages"]) == 8
    
    print(f"       Copernicus XML Telemetry & 8-Stage Preprocessing Pipeline regression passed")

if run_test("5. Phase 2 Preprocessing Pipeline Regression Test", test_phase2_preprocessing_regression):
    passed_tests += 1

# ---------------------------------------------------------
# 6. Phase 2 Change-Detection Regression Test
# ---------------------------------------------------------
def test_phase2_change_detection_regression():
    tile_id = "e87b4d6c-9cdb-4293-8a8b-7ad7a5af6e43"
    r = client.get(f"/api/change/tri_epoch/{tile_id}")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert "temporal_persistence" in data
    assert "explainability" in data
    assert "stats_cumulative" in data
    
    explain = data["explainability"]
    fa = explain.get("false_alarm_suppression", {})
    assert "false_alarm_risk_score" in fa
    print(f"       Tri-Epoch Change Detection & False-Alarm Suppression regression passed (Risk: {fa['false_alarm_risk_score']})")

if run_test("6. Phase 2 Tri-Epoch Change Detection Regression Test", test_phase2_change_detection_regression):
    passed_tests += 1

print("\n" + "=" * 70)
print(f"PHASE 3A STABILIZATION RESULT: {passed_tests} / {total_tests} TESTS PASSED ({(passed_tests/total_tests)*100:.1f}%)")
print("=" * 70)
