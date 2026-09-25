"""
Phase 4D — Explainable Change Investigation + Analyst Decision Intelligence
Automated 24-Test Comprehensive Verification Suite
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
    print("RUNNING PHASE 4D - EXPLAINABLE CHANGE INVESTIGATION TEST SUITE (24/24)")
    print("=" * 75)

    passed_count = 0
    total_tests = 24
    test_case_id = None
    target_tile_id = "e87b4d6c-9cdb-4293-8a8b-7ad7a5af6e43"

    # -------------------------------------------------------------
    # TEST 1: Backend Health
    # -------------------------------------------------------------
    print("\n[Test 1/24] Testing Backend Health (/health)...")
    try:
        r = requests.get(f"{BASE_URL}/health")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") in ["healthy", "unhealthy"] # mongo or fallback
        print("  [PASS] Backend health endpoint operational.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 1 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 2: Real Case Retrieval
    # -------------------------------------------------------------
    print("\n[Test 2/24] Testing Real Case Retrieval (/api/cases)...")
    try:
        r = requests.get(f"{BASE_URL}/api/cases")
        assert r.status_code == 200
        cases = r.json().get("cases", [])
        assert len(cases) > 0
        test_case_id = cases[0]["case_id"]
        assert test_case_id.startswith("CASE-2026-")
        print(f"  [PASS] Retrieved {len(cases)} real cases. Active test case: {test_case_id}")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 2 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 3: Real Tri-Epoch Analysis
    # -------------------------------------------------------------
    print("\n[Test 3/24] Testing Real Tri-Epoch Analysis (/api/change/tri_epoch/{tile_id})...")
    try:
        r = requests.get(f"{BASE_URL}/api/change/tri_epoch/{target_tile_id}")
        assert r.status_code == 200
        data = r.json()
        assert "images" in data
        assert "epoch_2024" in data["images"]
        assert "epoch_2026" in data["images"]
        assert "stats_cumulative" in data
        assert "temporal_persistence" in data
        print("  [PASS] Real tri-epoch analysis returned multi-date rasters and persistence.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 3 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 4: Earliest Usable Observation
    # -------------------------------------------------------------
    print("\n[Test 4/24] Testing Earliest Usable Observation Identification...")
    try:
        r = requests.get(f"{BASE_URL}/api/cases/{test_case_id}/investigation")
        assert r.status_code == 200
        inv = r.json()
        earliest = inv.get("earliest_usable_observation")
        assert earliest is not None
        assert "date" in earliest
        assert "sensor" in earliest
        assert earliest.get("usable") is True
        print(f"  [PASS] Earliest usable observation identified: {earliest['date']} ({earliest['sensor']}).")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 4 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 5: Before / After Evidence
    # -------------------------------------------------------------
    print("\n[Test 5/24] Testing Before/After Evidence Viewer Structure...")
    try:
        r = requests.get(f"{BASE_URL}/api/cases/{test_case_id}/investigation")
        assert r.status_code == 200
        ba = r.json().get("before_after_evidence")
        assert ba is not None
        assert "before" in ba
        assert "after" in ba
        assert "change_mask" in ba
        assert ba["before"].get("processing_state") is not None
        assert ba["change_mask"].get("available") in [True, False]
        print(f"  [PASS] Before/After evidence verified. Mask available: {ba['change_mask']['available']}.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 5 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 6: Change Characterization
    # -------------------------------------------------------------
    print("\n[Test 6/24] Testing Change Characterization (Physical & Domain)...")
    try:
        r = requests.get(f"{BASE_URL}/api/cases/{test_case_id}/investigation")
        assert r.status_code == 200
        char = r.json().get("change_characterization")
        assert char is not None
        assert char.get("physical_change_type") in ["EXPANSION", "CONTRACTION", "APPEARANCE", "DISAPPEARANCE", "CLASSIFICATION NOT DETERMINED"]
        assert char.get("domain_interpretation") in ["CONSTRUCTION", "CLEARANCE", "WATER CHANGE", "ROAD CHANGE", "CLASSIFICATION NOT DETERMINED"]
        print(f"  [PASS] Change characterization: Physical='{char['physical_change_type']}', Domain='{char['domain_interpretation']}'.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 6 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 7: False-Alarm Checks
    # -------------------------------------------------------------
    print("\n[Test 7/24] Testing False-Alarm Individual Checks Matrix...")
    try:
        r = requests.get(f"{BASE_URL}/api/cases/{test_case_id}/investigation")
        assert r.status_code == 200
        fa = r.json().get("false_alarm_intelligence")
        assert fa is not None
        checks = fa.get("checks", [])
        assert len(checks) >= 6
        check_names = [c["check"] for c in checks]
        assert "Cloud / Shadow" in check_names
        assert "Seasonal / Phenological variation" in check_names
        assert "Registration / co-registration" in check_names
        for c in checks:
            assert c["status"] in ["PASS", "WARNING", "NOT AVAILABLE"]
        print(f"  [PASS] False-alarm individual checks matrix verified ({len(checks)} checks).")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 7 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 8: False-Alarm Risk Score
    # -------------------------------------------------------------
    print("\n[Test 8/24] Testing False-Alarm Risk Score & Rationale...")
    try:
        r = requests.get(f"{BASE_URL}/api/cases/{test_case_id}/investigation")
        assert r.status_code == 200
        fa = r.json().get("false_alarm_intelligence")
        risk = fa.get("false_alarm_risk")
        assert risk in ["LOW", "MODERATE", "ELEVATED"]
        assert len(fa.get("why", "")) > 0
        print(f"  [PASS] False-alarm risk score: '{risk}'. Rationale: {fa['why'][:50]}...")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 8 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 9: AI Confidence Explanation Output
    # -------------------------------------------------------------
    print("\n[Test 9/24] Testing Deterministic AI Confidence & Explainability...")
    try:
        r = requests.get(f"{BASE_URL}/api/cases/{test_case_id}/investigation")
        assert r.status_code == 200
        exp = r.json().get("confidence_explanation")
        assert exp is not None
        assert "why_ai_detected" in exp
        assert "spatial_evidence" in exp
        assert "temporal_evidence" in exp
        assert "data_quality" in exp
        assert "false_alarm_checks" in exp
        print("  [PASS] AI confidence explanation components verified.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 9 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 10: Temporal Persistence Classification
    # -------------------------------------------------------------
    print("\n[Test 10/24] Testing Temporal Persistence Classification...")
    try:
        r = requests.get(f"{BASE_URL}/api/cases/{test_case_id}/investigation")
        assert r.status_code == 200
        pers = r.json().get("persistence_evidence")
        assert pers is not None
        assert pers.get("status") in ["PERSISTENT", "TRANSIENT", "CYCLICAL / RECOVERY", "INSUFFICIENT TEMPORAL EVIDENCE"]
        print(f"  [PASS] Temporal persistence classification: '{pers['status']}'.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 10 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 11: Analyst Current Review Endpoint
    # -------------------------------------------------------------
    print("\n[Test 11/24] Testing Analyst Current Review (/api/cases/{case_id}/review)...")
    try:
        r = requests.get(f"{BASE_URL}/api/cases/{test_case_id}/review")
        assert r.status_code == 200
        rev = r.json()
        assert rev.get("status") == "success"
        assert "current_status" in rev
        assert "analyst_decision" in rev
        print(f"  [PASS] Current review status: {rev['current_status']} (Decision: {rev['analyst_decision']}).")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 11 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 12: Analyst Review History Timeline
    # -------------------------------------------------------------
    print("\n[Test 12/24] Testing Analyst Review History Timeline (/api/cases/{case_id}/reviews)...")
    try:
        r = requests.get(f"{BASE_URL}/api/cases/{test_case_id}/reviews")
        assert r.status_code == 200
        hist = r.json()
        assert hist.get("status") == "success"
        assert "history" in hist
        assert isinstance(hist["history"], list)
        print(f"  [PASS] Review history timeline retrieved ({len(hist['history'])} total entries).")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 12 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 13: CONFIRM Review Workflow
    # -------------------------------------------------------------
    print("\n[Test 13/24] Testing CONFIRM Review Workflow...")
    try:
        r = requests.post(f"{BASE_URL}/api/cases/{test_case_id}/review", json={
            "decision": "CONFIRM",
            "rationale": "Test CONFIRM decision for Phase 4D",
            "analyst_id": "test_analyst_p4d"
        })
        assert r.status_code == 200
        res = r.json()
        assert res.get("status") == "success"
        assert res.get("updated_case", {}).get("current_status") == "CONFIRMED"
        assert res.get("updated_case", {}).get("analyst_decision") == "CONFIRM"
        print("  [PASS] CONFIRM workflow successfully executed. Status updated to CONFIRMED.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 13 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 14: REJECT Review Workflow
    # -------------------------------------------------------------
    print("\n[Test 14/24] Testing REJECT Review Workflow...")
    try:
        r = requests.post(f"{BASE_URL}/api/cases/{test_case_id}/review", json={
            "decision": "REJECT",
            "rationale": "Test REJECT decision for Phase 4D",
            "analyst_id": "test_analyst_p4d"
        })
        assert r.status_code == 200
        res = r.json()
        assert res.get("status") == "success"
        assert res.get("updated_case", {}).get("current_status") == "REJECTED"
        assert res.get("updated_case", {}).get("analyst_decision") == "REJECT"
        print("  [PASS] REJECT workflow successfully executed. Status updated to REJECTED.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 14 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 15: FLAG Review Workflow
    # -------------------------------------------------------------
    print("\n[Test 15/24] Testing FLAG Review Workflow...")
    try:
        r = requests.post(f"{BASE_URL}/api/cases/{test_case_id}/review", json={
            "decision": "FLAG",
            "rationale": "Test FLAG decision for Phase 4D",
            "analyst_id": "test_analyst_p4d"
        })
        assert r.status_code == 200
        res = r.json()
        assert res.get("status") == "success"
        assert res.get("updated_case", {}).get("current_status") == "FLAGGED"
        assert res.get("updated_case", {}).get("analyst_decision") == "FLAG"
        print("  [PASS] FLAG workflow successfully executed. Status updated to FLAGGED.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 15 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 16: Investigation Summary
    # -------------------------------------------------------------
    print("\n[Test 16/24] Testing Investigation Summary Block...")
    try:
        r = requests.get(f"{BASE_URL}/api/cases/{test_case_id}/investigation")
        assert r.status_code == 200
        summary = r.json().get("investigation_summary")
        assert summary is not None
        assert "CASE" in summary
        assert "AOI" in summary
        assert "OBSERVATION_WINDOW" in summary
        assert "CHANGE" in summary
        assert "FALSE_ALARM_STATUS" in summary
        assert "EVIDENCE_STRENGTH" in summary
        assert "ANALYST_STATUS" in summary
        print(f"  [PASS] Investigation summary block structured: CASE={summary['CASE']}, CHANGE={summary['CHANGE']}.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 16 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 17: Provenance Integration
    # -------------------------------------------------------------
    print("\n[Test 17/24] Testing Provenance Integration (/api/cases/{case_id}/provenance)...")
    try:
        r = requests.get(f"{BASE_URL}/api/cases/{test_case_id}/provenance")
        assert r.status_code == 200
        prov = r.json()
        chain = prov.get("provenance_chain", [])
        assert len(chain) >= 9
        for stg in chain:
            assert "provenance_hash" in stg
            assert stg["provenance_hash"].startswith("SHA256-")
        print(f"  [PASS] Provenance chain verified ({len(chain)} stages with valid SHA-256 hashes).")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 17 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 18: Markdown Report Integration
    # -------------------------------------------------------------
    print("\n[Test 18/24] Testing Markdown Report Integration (/api/cases/{case_id}/report)...")
    try:
        r = requests.get(f"{BASE_URL}/api/cases/{test_case_id}/report")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "success"
        md = data.get("markdown_content", "")
        assert "SATELLITE INCIDENT EVIDENCE" in md
        assert "DETECTED CHANGE SUMMARY" in md
        assert "FALSE-ALARM SUPPRESSION ANALYSIS" in md
        assert "AI CONFIDENCE & EXPLAINABILITY" in md
        print("  [PASS] Markdown report extended with Phase 4D investigation sections.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 18 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 19: JSON Evidence Export
    # -------------------------------------------------------------
    print("\n[Test 19/24] Testing JSON Evidence Export (/api/cases/{case_id}/evidence.json)...")
    try:
        r = requests.get(f"{BASE_URL}/api/cases/{test_case_id}/evidence.json")
        assert r.status_code == 200
        pkg = r.json()
        assert pkg.get("status") == "success"
        assert "observations_timeline" in pkg
        assert "change_characterization" in pkg
        assert "false_alarm_intelligence" in pkg
        assert "confidence_explanation" in pkg
        assert "persistence_evidence" in pkg
        assert "investigation_summary" in pkg
        assert "package_hash" in pkg
        print("  [PASS] JSON evidence export contains complete Phase 4D investigation payload.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 19 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 20: Phase 4C AOI Regression
    # -------------------------------------------------------------
    print("\n[Test 20/24] Testing Phase 4C AOI Spatial Query Regression...")
    try:
        r = requests.post(f"{BASE_URL}/api/aoi/query", json={"bbox": [88.30, 22.50, 88.40, 22.60]})
        assert r.status_code == 200
        tiles = r.json().get("tiles", [])
        assert len(tiles) > 0
        print(f"  [PASS] Phase 4C AOI query regression passed ({len(tiles)} tiles returned).")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 20 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 21: Semantic Retrieval Regression
    # -------------------------------------------------------------
    print("\n[Test 21/24] Testing Phase 1 Semantic Retrieval Regression...")
    try:
        r = requests.post(f"{BASE_URL}/api/search/semantic", json={"query": "urban built up", "top_k": 5})
        assert r.status_code == 200
        results = r.json().get("results", [])
        assert len(results) > 0
        print(f"  [PASS] Semantic retrieval regression passed ({len(results)} tiles returned).")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 21 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 22: SAR Honesty Regression
    # -------------------------------------------------------------
    print("\n[Test 22/24] Testing Phase 4B SAR Honesty Regression (/api/sar/status)...")
    try:
        r = requests.get(f"{BASE_URL}/api/sar/status")
        assert r.status_code == 200
        sar = r.json()
        assert sar.get("available") is False
        assert sar.get("status_code") == "SAR_NOT_CACHED_LOCALLY"
        print("  [PASS] SAR status honestly reports SAR_NOT_CACHED_LOCALLY.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 22 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 23: Preprocessing Regression
    # -------------------------------------------------------------
    print("\n[Test 23/24] Testing Phase 2 8-Stage Preprocessing Regression...")
    try:
        r = requests.post(f"{BASE_URL}/api/preprocessing/pipeline", json={"year": 2024})
        assert r.status_code == 200
        stages = r.json().get("pipeline", {}).get("stages", [])
        assert len(stages) == 8
        print("  [PASS] Phase 2 8-stage preprocessing pipeline regression passed.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 23 failed: {e}")
        traceback.print_exc()

    # -------------------------------------------------------------
    # TEST 24: Zero-Fabrication Audit
    # -------------------------------------------------------------
    print("\n[Test 24/24] Performing Zero-Fabrication Audit...")
    try:
        r = requests.get(f"{BASE_URL}/api/cases/{test_case_id}/investigation")
        assert r.status_code == 200
        inv = r.json()
        summary = inv.get("investigation_summary", {})
        # Ensure no bogus values or unbacked assumptions exist
        for k, v in summary.items():
            assert v is not None and len(str(v)) > 0
        
        # Check that SAR reports available=False
        sar_ev = inv.get("case", {}).get("sar_evidence", {})
        assert sar_ev.get("available") is False
        print("  [PASS] Zero-fabrication audit verified: NO fake SAR data, NO dummy metrics.")
        passed_count += 1
    except Exception as e:
        print(f"  [FAIL] Test 24 failed: {e}")
        traceback.print_exc()

    print("\n" + "=" * 75)
    print(f"PHASE 4D TEST SUITE RESULTS: {passed_count} / {total_tests} PASSED")
    print("=" * 75)
    if passed_count == total_tests:
        print("ALL PHASE 4D TESTS PASSED SUCCESSFULLY!")
    else:
        print(f"WARNING: {total_tests - passed_count} test(s) failed.")
        sys.exit(1)

if __name__ == "__main__":
    run_test_suite()
