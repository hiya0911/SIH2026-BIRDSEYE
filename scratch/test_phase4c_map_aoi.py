"""
Phase 4C — Interactive Satellite Analyst Map & Location/AOI Intelligence
Automated 20-Test Comprehensive Verification Suite
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

def run_test_suite():
    print("=" * 75)
    print("RUNNING PHASE 4C - MAP & AOI INTELLIGENCE TEST SUITE (20/20)")
    print("=" * 75)

    passed_count = 0
    total_tests = 20

    # -------------------------------------------------------------
    # TEST 1: Backend Startup & Health
    # -------------------------------------------------------------
    print("\n[Test 1/20] Testing Backend Startup & Health...")
    try:
        r = requests.get(f"{BASE_URL}/")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "online"
        print("  [PASS] Backend home endpoint online.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 1 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 2: Existing Optical Tile Retrieval
    # -------------------------------------------------------------
    print("\n[Test 2/20] Testing Optical Tile Retrieval (/api/tiles/list)...")
    try:
        r = requests.get(f"{BASE_URL}/api/tiles/list?limit=10")
        assert r.status_code == 200
        data = r.json()
        tiles = data.get("tiles", [])
        assert len(tiles) > 0
        tile_id = tiles[0]["tile_id"]
        assert "bbox" in tiles[0]
        print(f"  [PASS] Retrieved {len(tiles)} optical tiles. Sample tile: {tile_id}")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 2 failed: {e}")
        traceback.print_exc()
        tile_id = "test_tile"

    # -------------------------------------------------------------
    # TEST 3: Existing Semantic Retrieval
    # -------------------------------------------------------------
    print("\n[Test 3/20] Testing Semantic Search (/api/search/semantic)...")
    try:
        r = requests.post(f"{BASE_URL}/api/search/semantic", json={
            "query": "urban concrete building",
            "top_k": 5,
            "spectral_gate": True
        })
        assert r.status_code == 200
        data = r.json()
        results = data.get("results", [])
        assert len(results) > 0
        print(f"  [PASS] Semantic retrieval returned {len(results)} matching tiles.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 3 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 4: Satellite Footprints GeoJSON Endpoint
    # -------------------------------------------------------------
    print("\n[Test 4/20] Testing Tile Footprints GeoJSON (/api/aoi/footprints)...")
    try:
        r = requests.get(f"{BASE_URL}/api/aoi/footprints?limit=50")
        assert r.status_code == 200
        data = r.json()
        assert data.get("type") == "FeatureCollection"
        features = data.get("features", [])
        assert len(features) > 0
        feat = features[0]
        assert feat.get("geometry", {}).get("type") == "Polygon"
        assert "properties" in feat
        print(f"  [PASS] Footprints GeoJSON returned {len(features)} valid features.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 4 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 5: Point AOI Spatial Query
    # -------------------------------------------------------------
    print("\n[Test 5/20] Testing Point AOI Spatial Query...")
    try:
        # Buffer around Kolkata point (22.5726°N, 88.3639°E)
        point_bbox = [88.3489, 22.5576, 88.3789, 22.5876]
        r = requests.post(f"{BASE_URL}/api/aoi/query", json={"bbox": point_bbox})
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "success"
        tiles = data.get("tiles", [])
        assert len(tiles) > 0
        print(f"  [PASS] Point AOI returned {len(tiles)} intersecting tiles.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 5 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 6: Rectangle AOI Spatial Query
    # -------------------------------------------------------------
    print("\n[Test 6/20] Testing Rectangle AOI Spatial Query...")
    try:
        rect_bbox = [88.3000, 22.5000, 88.4200, 22.6200]
        r = requests.post(f"{BASE_URL}/api/aoi/query", json={"bbox": rect_bbox, "limit": 25})
        assert r.status_code == 200
        data = r.json()
        assert data.get("query_type") == "bbox"
        tiles = data.get("tiles", [])
        assert len(tiles) > 0
        print(f"  [PASS] Rectangle AOI returned {len(tiles)} intersecting tiles.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 6 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 7: Polygon AOI Spatial Query
    # -------------------------------------------------------------
    print("\n[Test 7/20] Testing Polygon AOI Spatial Query...")
    try:
        poly_coords = [
            [88.3400, 22.5500],
            [88.4000, 22.5500],
            [88.4000, 22.6000],
            [88.3400, 22.6000],
            [88.3400, 22.5500]
        ]
        r = requests.post(f"{BASE_URL}/api/aoi/query", json={"polygon": poly_coords})
        assert r.status_code == 200
        data = r.json()
        assert data.get("query_type") == "polygon"
        tiles = data.get("tiles", [])
        assert len(tiles) > 0
        print(f"  [PASS] Polygon AOI returned {len(tiles)} intersecting tiles.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 7 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 8: Invalid Latitude Rejection
    # -------------------------------------------------------------
    print("\n[Test 8/20] Testing Invalid Latitude Rejection (HTTP 400)...")
    try:
        r_bad_bbox = requests.post(f"{BASE_URL}/api/aoi/query", json={"bbox": [88.30, 150.0, 88.40, 160.0]})
        assert r_bad_bbox.status_code == 400
        assert "latitude" in r_bad_bbox.json().get("detail", "").lower()
        
        r_bad_search = requests.get(f"{BASE_URL}/api/location/search?q=150.0,88.36")
        assert r_bad_search.status_code == 400
        print("  [PASS] Invalid latitude correctly rejected with HTTP 400.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 8 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 9: Invalid Longitude Rejection
    # -------------------------------------------------------------
    print("\n[Test 9/20] Testing Invalid Longitude Rejection (HTTP 400)...")
    try:
        r_bad_lon = requests.post(f"{BASE_URL}/api/aoi/query", json={"bbox": [250.0, 22.50, 260.0, 22.60]})
        assert r_bad_lon.status_code == 400
        assert "longitude" in r_bad_lon.json().get("detail", "").lower()
        print("  [PASS] Invalid longitude correctly rejected with HTTP 400.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 9 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 10: Malformed Polygon Rejection
    # -------------------------------------------------------------
    print("\n[Test 10/20] Testing Malformed Polygon Rejection (HTTP 400)...")
    try:
        # Fewer than 3 points
        r_short_poly = requests.post(f"{BASE_URL}/api/aoi/query", json={"polygon": [[88.34, 22.55], [88.40, 22.55]]})
        assert r_short_poly.status_code == 400
        assert "polygon" in r_short_poly.json().get("detail", "").lower()
        print("  [PASS] Malformed polygon correctly rejected with HTTP 400.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 10 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 11: AOI -> Actual Imagery Query Intersections
    # -------------------------------------------------------------
    print("\n[Test 11/20] Testing AOI -> Actual Imagery Query...")
    try:
        r = requests.post(f"{BASE_URL}/api/aoi/query", json={"bbox": [88.32, 22.52, 88.38, 22.58]})
        assert r.status_code == 200
        tiles = r.json().get("tiles", [])
        assert len(tiles) > 0
        t0 = tiles[0]
        assert "tile_id" in t0
        assert "wgs_bbox" in t0
        assert "acquisition_datetime" in t0
        print(f"  [PASS] Intersecting imagery query verified. Tile ID: {t0['tile_id']}")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 11 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 12: AOI -> Actual Analysis Execution
    # -------------------------------------------------------------
    print("\n[Test 12/20] Testing AOI -> Actual Tri-Epoch Analysis (/api/aoi/analyze)...")
    try:
        r = requests.post(f"{BASE_URL}/api/aoi/analyze", json={"bbox": [88.32, 22.52, 88.38, 22.58]})
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "success"
        analysis = data.get("aoi_analysis", {})
        assert "images" in analysis
        assert "epoch_2024" in analysis["images"]
        assert "change_mask" in analysis["images"]
        print("  [PASS] AOI change analysis returned tri-epoch images & mask payload.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 12 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 13: Sensor Filtering Regression
    # -------------------------------------------------------------
    print("\n[Test 13/20] Testing Sensor Filtering Regression...")
    try:
        r_sar = requests.post(f"{BASE_URL}/api/search/semantic", json={"query": "water", "sensor_filter": "SAR"})
        assert r_sar.status_code == 200
        sar_res = r_sar.json()
        assert sar_res.get("available") is False
        assert sar_res.get("sensor_filter") == "SAR"

        r_opt = requests.post(f"{BASE_URL}/api/search/semantic", json={"query": "water", "sensor_filter": "OPTICAL"})
        assert r_opt.status_code == 200
        assert len(r_opt.json().get("results", [])) > 0
        print("  [PASS] Sensor filtering regression passed (SAR unavailable, Optical working).")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 13 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 14: SAR Honest Status (SAR_NOT_CACHED_LOCALLY)
    # -------------------------------------------------------------
    print("\n[Test 14/20] Testing SAR Status Honesty (/api/sar/status)...")
    try:
        r = requests.get(f"{BASE_URL}/api/sar/status")
        assert r.status_code == 200
        sar_status = r.json()
        assert sar_status.get("available") is False
        assert sar_status.get("status_code") == "SAR_NOT_CACHED_LOCALLY"
        print("  [PASS] SAR status accurately reports SAR_NOT_CACHED_LOCALLY.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 14 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 15: Phase 2 Preprocessing Lab Regression
    # -------------------------------------------------------------
    print("\n[Test 15/20] Testing Phase 2 Preprocessing Lab Regression...")
    try:
        r_scenes = requests.get(f"{BASE_URL}/api/preprocessing/scenes")
        assert r_scenes.status_code == 200
        scenes = r_scenes.json().get("scenes", [])
        assert len(scenes) > 0
        assert any(s.get("year") == 2024 or s.get("epoch_year") == 2024 for s in scenes)

        r_pipe = requests.post(f"{BASE_URL}/api/preprocessing/pipeline", json={"year": 2024})
        assert r_pipe.status_code == 200
        pipe_res = r_pipe.json().get("pipeline", {})
        assert len(pipe_res.get("stages", [])) == 8
        print("  [PASS] Phase 2 8-stage preprocessing pipeline regression passed.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 15 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 16: Phase 3B Analyst Review Workflow Regression
    # -------------------------------------------------------------
    print("\n[Test 16/20] Testing Phase 3B Analyst Review Regression...")
    try:
        r_case = requests.post(f"{BASE_URL}/api/cases", json={"tile_id": tile_id, "notes": "Phase 4C Test Case"})
        assert r_case.status_code == 200
        case_id = r_case.json()["case"]["case_id"]

        r_rev = requests.post(f"{BASE_URL}/api/cases/{case_id}/review", json={
            "decision": "CONFIRM",
            "rationale": "Verified Phase 4C AOI test case",
            "analyst_id": "analyst_p4c"
        })
        assert r_rev.status_code == 200
        res_json = r_rev.json()
        assert res_json.get("status") == "success"
        print(f"  [PASS] Phase 3B review workflow regression passed (Case: {case_id}).")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 16 failed: {e}")
        traceback.print_exc()
        case_id = "case_fallback"

    # -------------------------------------------------------------
    # TEST 17: Phase 3C Investigation Workspace Regression
    # -------------------------------------------------------------
    print("\n[Test 17/20] Testing Phase 3C Evidence Investigation Regression...")
    try:
        r_inv = requests.get(f"{BASE_URL}/api/cases/{case_id}/investigation")
        assert r_inv.status_code == 200
        inv_data = r_inv.json()
        assert inv_data.get("status") == "success"
        assert "case" in inv_data
        assert "investigation_summary" in inv_data
        print("  [PASS] Phase 3C Evidence Investigation workspace regression passed.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 17 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 18: Phase 3D Provenance & Evidence Report Regression
    # -------------------------------------------------------------
    print("\n[Test 18/20] Testing Phase 3D Provenance & Report Export Regression...")
    try:
        r_prov = requests.get(f"{BASE_URL}/api/cases/{case_id}/provenance")
        assert r_prov.status_code == 200
        assert len(r_prov.json().get("provenance_chain", [])) >= 9

        r_rep = requests.get(f"{BASE_URL}/api/cases/{case_id}/report")
        assert r_rep.status_code == 200
        assert "SATELLITE INCIDENT EVIDENCE" in r_rep.json().get("markdown_content", "")
        print("  [PASS] Phase 3D Provenance chain & report export regression passed.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 18 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 19: Frontend & Location Integration
    # -------------------------------------------------------------
    print("\n[Test 19/20] Testing Location Search & Console Integration...")
    try:
        r_loc = requests.get(f"{BASE_URL}/api/location/search?q=Kolkata")
        assert r_loc.status_code == 200
        loc_data = r_loc.json()
        assert loc_data.get("status") == "success"
        assert loc_data.get("lat") == 22.5726
        assert loc_data.get("lon") == 88.3639

        r_console = requests.get(f"{BASE_URL}/console/")
        assert r_console.status_code in [200, 304]
        print("  [PASS] Location search & Console web app endpoints integrated.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 19 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 20: No Fake Data Audit
    # -------------------------------------------------------------
    print("\n[Test 20/20] Performing Zero-Fabrication Audit...")
    try:
        r_sar_prod = requests.get(f"{BASE_URL}/api/sar/products")
        assert r_sar_prod.status_code == 200
        prods = r_sar_prod.json().get("products", [])
        assert len(prods) == 0 # Real audit: 0 SAR rasters on disk

        r_aoi = requests.post(f"{BASE_URL}/api/aoi/query", json={"bbox": [88.30, 22.50, 88.40, 22.60]})
        assert r_aoi.status_code == 200
        tiles = r_aoi.json().get("tiles", [])
        for t in tiles:
            assert isinstance(t["center_lat"], float)
            assert isinstance(t["center_lon"], float)
            assert "tile_id" in t

        print("  [PASS] Zero-fabrication audit verified: NO fake SAR data, coordinates genuine.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 20 failed: {e}")
        traceback.print_exc()

    print("\n" + "=" * 75)
    print(f"PHASE 4C TEST SUITE RESULTS: {passed_count} / {total_tests} PASSED")
    print("=" * 75)
    if passed_count == total_tests:
        print("ALL PHASE 4C TESTS PASSED SUCCESSFULLY!")
    else:
        print(f"WARNING: {total_tests - passed_count} test(s) failed.")
        sys.exit(1)

if __name__ == "__main__":
    run_test_suite()
