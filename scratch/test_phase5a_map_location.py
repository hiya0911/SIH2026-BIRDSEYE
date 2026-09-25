"""
BIRDSΣY3 — Phase 5A Map & Fine-Grained Location Intelligence Comprehensive Test Suite
Automated Verification Suite (15 Test Cases)
"""

import sys
import os
import json
import time
import requests
import traceback

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "http://127.0.0.1:8000"

def run_phase5a_tests():
    print("=" * 80)
    print("RUNNING PHASE 5A — MAP & FINE-GRAINED LOCATION INTELLIGENCE TEST SUITE")
    print("=" * 80)

    passed_count = 0
    total_tests = 15

    # -------------------------------------------------------------
    # TEST 1: Backend Startup & Health Endpoint
    # -------------------------------------------------------------
    print("\n[Test 1/15] Testing Backend Startup & Health Endpoint (/)...")
    try:
        r = requests.get(f"{BASE_URL}/", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "online"
        print("  [PASS] Backend health endpoint online & responding.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 1 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 2: Existing Location Search Endpoint (Backwards Compatibility)
    # -------------------------------------------------------------
    print("\n[Test 2/15] Testing Location Search endpoint (/api/location/search?q=kolkata)...")
    try:
        r = requests.get(f"{BASE_URL}/api/location/search?q=kolkata", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "success"
        assert "lat" in data and "lon" in data
        assert abs(data["lat"] - 22.5726) < 0.1
        assert abs(data["lon"] - 88.3639) < 0.1
        print(f"  [PASS] Location search for 'kolkata' returned lat: {data['lat']}, lon: {data['lon']}")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 2 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 3: Kolkata City Search
    # -------------------------------------------------------------
    print("\n[Test 3/15] Testing Kolkata City Search ('Kolkata')...")
    try:
        r = requests.get(f"{BASE_URL}/api/location/search?q=Kolkata", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "success"
        assert len(data.get("results", [])) > 0
        print(f"  [PASS] 'Kolkata' resolved via provider: {data.get('provider')}")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 3 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 4: Fine-Grained Locality Search ('Lake Town, Kolkata, West Bengal, India')
    # -------------------------------------------------------------
    print("\n[Test 4/15] Testing Fine-Grained Locality Search ('Lake Town, Kolkata, West Bengal, India')...")
    try:
        r = requests.get(f"{BASE_URL}/api/location/search?q=Lake Town, Kolkata, West Bengal, India", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "success"
        results = data.get("results", [])
        assert len(results) > 0
        top = results[0]
        assert "lat" in top and "lon" in top
        print(f"  [PASS] Fine-grained 'Lake Town, Kolkata' resolved: lat={top['lat']}, lon={top['lon']}, provider={top['provider']}")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 4 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 5: Pan-India City Search ('Siliguri')
    # -------------------------------------------------------------
    print("\n[Test 5/15] Testing Pan-India City Search ('Siliguri')...")
    try:
        r = requests.get(f"{BASE_URL}/api/location/search?q=Siliguri", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "success"
        assert abs(data["lat"] - 26.7271) < 0.3
        print(f"  [PASS] 'Siliguri' resolved: lat={data['lat']}, lon={data['lon']}")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 5 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 6: Metro City Search ('Mumbai')
    # -------------------------------------------------------------
    print("\n[Test 6/15] Testing Metro City Search ('Mumbai')...")
    try:
        r = requests.get(f"{BASE_URL}/api/location/search?q=Mumbai", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "success"
        assert abs(data["lat"] - 19.0760) < 0.3
        print(f"  [PASS] 'Mumbai' resolved: lat={data['lat']}, lon={data['lon']}")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 6 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 7: Valid Numeric Coordinate Search ('22.5726, 88.3639')
    # -------------------------------------------------------------
    print("\n[Test 7/15] Testing Valid Coordinate Search ('22.5726, 88.3639')...")
    try:
        r = requests.get(f"{BASE_URL}/api/location/search?q=22.5726, 88.3639", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "success"
        assert data.get("location_type") == "coordinates"
        assert abs(data["lat"] - 22.5726) < 0.0001
        assert abs(data["lon"] - 88.3639) < 0.0001
        print("  [PASS] Numeric coordinates '22.5726, 88.3639' successfully parsed.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 7 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 8: Invalid Coordinate Rejection (Out of Range Lat > 90)
    # -------------------------------------------------------------
    print("\n[Test 8/15] Testing Invalid Coordinate Rejection ('120.0, 88.3639')...")
    try:
        r = requests.get(f"{BASE_URL}/api/location/search?q=120.0, 88.3639", timeout=10)
        assert r.status_code == 400
        detail = r.json().get("detail", "")
        assert "Invalid latitude" in detail or "Must be between" in detail
        print(f"  [PASS] Invalid coordinate correctly rejected with HTTP 400: '{detail}'")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 8 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 9: Search Suggestions / Ambiguous Candidates Handling
    # -------------------------------------------------------------
    print("\n[Test 9/15] Testing Search Suggestions / Results Candidate List...")
    try:
        r = requests.get(f"{BASE_URL}/api/location/search?q=New Town", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "success"
        results = data.get("results", [])
        assert isinstance(results, list) and len(results) > 0
        print(f"  [PASS] Candidate results list returned with {len(results)} items.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 9 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 10: Tile Footprints GeoJSON Endpoint Preservation
    # -------------------------------------------------------------
    print("\n[Test 10/15] Testing Tile Footprints Endpoint (/api/aoi/footprints)...")
    try:
        r = requests.get(f"{BASE_URL}/api/aoi/footprints?limit=909", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data.get("type") == "FeatureCollection"
        features = data.get("features", [])
        assert len(features) > 0
        print(f"  [PASS] Footprints GeoJSON returned {len(features)} indexed Sentinel-2 features.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 10 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 11: AOI Spatial Intersection Query Handoff (/api/aoi/query)
    # -------------------------------------------------------------
    print("\n[Test 11/15] Testing AOI Spatial Query (/api/aoi/query)...")
    try:
        r = requests.post(f"{BASE_URL}/api/aoi/query", json={
            "bbox": [88.34, 22.55, 88.38, 22.59]
        }, timeout=10)
        assert r.status_code == 200
        data = r.json()
        tiles = data.get("tiles", [])
        assert len(tiles) > 0
        print(f"  [PASS] AOI query returned {len(tiles)} intersecting Sentinel-2 scenes.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 11 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 12: AOI Analysis Handoff (/api/aoi/analyze)
    # -------------------------------------------------------------
    print("\n[Test 12/15] Testing AOI Analysis Handoff (/api/aoi/analyze)...")
    try:
        r = requests.post(f"{BASE_URL}/api/aoi/analyze", json={
            "bbox": [88.34, 22.55, 88.38, 22.59]
        }, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "success"
        assert "aoi_analysis" in data
        analysis = data.get("aoi_analysis", {})
        assert "tile_id" in analysis or "target_wgs_bbox" in analysis
        print(f"  [PASS] AOI analysis completed for tile: {analysis.get('tile_id')}")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 12 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 13: Semantic Retrieval Preservation (/api/search/semantic)
    # -------------------------------------------------------------
    print("\n[Test 13/15] Testing Semantic Retrieval Preservation (/api/search/semantic)...")
    try:
        r = requests.post(f"{BASE_URL}/api/search/semantic", json={
            "query": "Dense forest canopy with high chlorophyll and lush green vegetation",
            "top_k": 5,
            "spectral_gate": True
        }, timeout=25)
        assert r.status_code == 200
        data = r.json()
        results = data.get("results", [])
        assert len(results) > 0
        print(f"  [PASS] Semantic retrieval returned {len(results)} matching tiles.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 13 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 14: Multimodal Search Preservation (/api/search/multimodal)
    # -------------------------------------------------------------
    print("\n[Test 14/15] Testing Multimodal Search Preservation (/api/search/multimodal)...")
    try:
        r = requests.post(f"{BASE_URL}/api/search/multimodal", json={
            "query": "urban built up concrete",
            "text_weight": 0.5,
            "image_weight": 0.5,
            "top_k": 5
        }, timeout=25)
        assert r.status_code == 200
        data = r.json()
        results = data.get("results", [])
        assert len(results) > 0
        print(f"  [PASS] Multimodal search returned {len(results)} matching tiles.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 14 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 15: Non-existent Location Handling
    # -------------------------------------------------------------
    print("\n[Test 15/15] Testing Non-existent Location Handling...")
    try:
        r = requests.get(f"{BASE_URL}/api/location/search?q=XyzNonExistentPlace99999", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "not_found"
        print("  [PASS] Non-existent location gracefully returned 'not_found' status.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 15 failed: {e}")
        traceback.print_exc()


    print("\n" + "=" * 80)
    print(f"TEST RESULTS: {passed_count}/{total_tests} PASSED")
    print("=" * 80)

    if passed_count == total_tests:
        print("🎉 ALL PHASE 5A MAP & LOCATION INTELLIGENCE TESTS PASSED!")
        return 0
    else:
        print(f"⚠️ {total_tests - passed_count} TESTS FAILED.")
        return 1

if __name__ == "__main__":
    sys.exit(run_phase5a_tests())
