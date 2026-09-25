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

print("=" * 75)
print("BIRDSEYE3 PHASE 3B — ANALYST REVIEW WORKFLOW SUITE")
print("Target: Controlled Review Decisions, History Timeline, Error Handling & Persistence")
print("=" * 75)

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
total_tests = 12

TEST_CASE_ID = "CASE-2026-e87b4d6c"

# ---------------------------------------------------------
# 1. Backend Startup & Health
# ---------------------------------------------------------
def test_1_backend_startup():
    r = client.get("/")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    r_health = client.get("/health")
    assert r_health.status_code == 200, f"Expected 200, got {r_health.status_code}"
    data = r_health.json()
    assert data.get("status") == "healthy"
    print(f"       Backend online & database connected: {data}")

if run_test("1. Backend Startup & Health Test", test_1_backend_startup):
    passed_tests += 1

# ---------------------------------------------------------
# 2. Phase 1 Regression Suite
# ---------------------------------------------------------
def test_2_phase1_regression():
    r1 = client.get("/api/aoi/footprints?limit=5")
    assert r1.status_code == 200
    r2 = client.post("/api/aoi/query", json={"bbox": [88.34, 22.55, 88.38, 22.60], "limit": 5})
    assert r2.status_code == 200
    r3 = client.post("/api/aoi/analyze", json={"tile_id": "e87b4d6c-9cdb-4293-8a8b-7ad7a5af6e43"})
    assert r3.status_code == 200
    print("       Phase 1 regression passed: Footprints, Query, AOI Analysis functional")

if run_test("2. Phase 1 Regression Suite", test_2_phase1_regression):
    passed_tests += 1

# ---------------------------------------------------------
# 3. Phase 2 Regression Suite
# ---------------------------------------------------------
def test_3_phase2_regression():
    r1 = client.get("/api/preprocessing/scenes")
    assert r1.status_code == 200
    r2 = client.post("/api/preprocessing/pipeline", json={"year": 2026, "tile_id": "e87b4d6c-9cdb-4293-8a8b-7ad7a5af6e43"})
    assert r2.status_code == 200
    res = r2.json()
    assert res.get("status") == "success"
    print("       Phase 2 regression passed: Copernicus XML Telemetry & 8-Stage Pipeline functional")

if run_test("3. Phase 2 Regression Suite", test_3_phase2_regression):
    passed_tests += 1

# ---------------------------------------------------------
# 4. Create CONFIRM Review
# ---------------------------------------------------------
def test_4_create_confirm_review():
    r = client.post(f"/api/cases/{TEST_CASE_ID}/review", json={
        "decision": "CONFIRM",
        "rationale": "Verified real spectral canopy loss and surface expansion.",
        "analyst_id": "analyst_1",
        "case_id": TEST_CASE_ID
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data["status"] == "success"
    assert data["review"]["decision"] == "CONFIRM"
    assert data["updated_case"]["current_status"] == "CONFIRMED"
    print(f"       CONFIRM review created: Review ID={data['review']['review_id']}")

if run_test("4. Create CONFIRM Review", test_4_create_confirm_review):
    passed_tests += 1

# ---------------------------------------------------------
# 5. Create FLAG Review
# ---------------------------------------------------------
def test_5_create_flag_review():
    r = client.post(f"/api/cases/{TEST_CASE_ID}/review", json={
        "decision": "FLAG",
        "rationale": "Ambiguous seasonal phenology drift requiring secondary inspection.",
        "analyst_id": "analyst_2",
        "case_id": TEST_CASE_ID
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data["status"] == "success"
    assert data["review"]["decision"] == "FLAG"
    assert data["updated_case"]["current_status"] == "FLAGGED"
    print(f"       FLAG review created: Review ID={data['review']['review_id']}")

if run_test("5. Create FLAG Review", test_5_create_flag_review):
    passed_tests += 1

# ---------------------------------------------------------
# 6. Create REJECT Review
# ---------------------------------------------------------
def test_6_create_reject_review():
    r = client.post(f"/api/cases/{TEST_CASE_ID}/review", json={
        "decision": "REJECT",
        "rationale": "Transient cloud shadow artifact suppressed by SCL mask.",
        "analyst_id": "analyst_3",
        "case_id": TEST_CASE_ID
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data["status"] == "success"
    assert data["review"]["decision"] == "REJECT"
    assert data["updated_case"]["current_status"] == "REJECTED"
    print(f"       REJECT review created: Review ID={data['review']['review_id']}")

if run_test("6. Create REJECT Review", test_6_create_reject_review):
    passed_tests += 1

# ---------------------------------------------------------
# 7. Retrieve Current Review
# ---------------------------------------------------------
def test_7_get_current_review():
    r = client.get(f"/api/cases/{TEST_CASE_ID}/review")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data["status"] == "success"
    assert data["case_id"] == TEST_CASE_ID
    assert data["current_status"] == "REJECTED"
    assert data["analyst_decision"] == "REJECT"
    curr = data.get("current_review")
    assert curr is not None
    assert curr["decision"] == "REJECT"
    print(f"       Current review retrieved: Decision={curr['decision']}, Rationale='{curr['rationale']}'")

if run_test("7. Retrieve Current Active Review", test_7_get_current_review):
    passed_tests += 1

# ---------------------------------------------------------
# 8. Retrieve Review History Timeline
# ---------------------------------------------------------
def test_8_get_review_history():
    r = client.get(f"/api/cases/{TEST_CASE_ID}/reviews")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data["status"] == "success"
    history = data.get("history", [])
    assert len(history) >= 3, f"Expected at least 3 review history entries, got {len(history)}"
    decisions = [h["decision"] for h in history]
    assert "CONFIRM" in decisions and "FLAG" in decisions and "REJECT" in decisions
    print(f"       Review history timeline retrieved: {len(history)} entries ({', '.join(decisions)})")

if run_test("8. Retrieve Review History Timeline", test_8_get_review_history):
    passed_tests += 1

# ---------------------------------------------------------
# 9. Invalid Decision Handling (Enum Validation)
# ---------------------------------------------------------
def test_9_invalid_decision_handling():
    r = client.post(f"/api/cases/{TEST_CASE_ID}/review", json={
        "decision": "INVALID_DECISION_TYPE",
        "rationale": "Testing enum validation",
        "analyst_id": "analyst",
        "case_id": TEST_CASE_ID
    })
    assert r.status_code in {400, 422}, f"Expected 400 or 422 for invalid decision, got {r.status_code}"
    print(f"       Invalid decision safely rejected with HTTP {r.status_code}: {r.text}")

if run_test("9. Invalid Decision Enum Validation (HTTP 400/422)", test_9_invalid_decision_handling):
    passed_tests += 1

# ---------------------------------------------------------
# 10. Missing Case/Change Handling (HTTP 404)
# ---------------------------------------------------------
def test_10_missing_case_handling():
    fake_case = "CASE-9999-NONEXISTENT"
    r1 = client.get(f"/api/cases/{fake_case}")
    assert r1.status_code == 404, f"Expected 404 for missing case, got {r1.status_code}"
    
    r2 = client.get(f"/api/cases/{fake_case}/review")
    assert r2.status_code == 404, f"Expected 404 for missing case review, got {r2.status_code}"
    
    r3 = client.get(f"/api/cases/{fake_case}/reviews")
    assert r3.status_code == 404, f"Expected 404 for missing case review history, got {r3.status_code}"
    print(f"       Missing case safely handled with HTTP 404 across endpoints")

if run_test("10. Missing Case/Change Handling (HTTP 404)", test_10_missing_case_handling):
    passed_tests += 1

# ---------------------------------------------------------
# 11. Persistence in MongoDB / Local Storage
# ---------------------------------------------------------
def test_11_persistence_verification():
    # Verify by retrieving case list and reading case document
    r = client.get(f"/api/cases/{TEST_CASE_ID}")
    assert r.status_code == 200
    case_data = r.json().get("case", {})
    assert case_data.get("current_status") == "REJECTED"
    assert len(case_data.get("reviews_history", [])) >= 3
    print(f"       Persistence verified: {len(case_data['reviews_history'])} entries retained in storage")

if run_test("11. Persistence Verification (MongoDB & Local JSON)", test_11_persistence_verification):
    passed_tests += 1

# ---------------------------------------------------------
# 12. Frontend Console UI Integration
# ---------------------------------------------------------
def test_12_frontend_ui_integration():
    with open(r"c:\Users\Hiya\OneDrive\Desktop\BIRDSEYE\frontend\index.html", "r", encoding="utf-8") as f:
        html = f.read()
    with open(r"c:\Users\Hiya\OneDrive\Desktop\BIRDSEYE\frontend\script.js", "r", encoding="utf-8") as f:
        js = f.read()
    with open(r"c:\Users\Hiya\OneDrive\Desktop\BIRDSEYE\frontend\style.css", "r", encoding="utf-8") as f:
        css = f.read()

    assert 'id="review-display-case-id"' in html, "Missing Case ID element in HTML"
    assert 'id="review-display-change-id"' in html, "Missing Change ID element in HTML"
    assert 'id="review-display-status"' in html, "Missing Review Status element in HTML"
    assert 'id="review-history-list"' in html, "Missing Review History element in HTML"
    assert 'review-history-timeline' in css, "Missing Review History timeline CSS"
    assert 'review-display-status' in js, "Missing Review Status updater in script.js"
    print("       Frontend integration verified in index.html, script.js, style.css")

if run_test("12. Frontend Console UI Integration Verification", test_12_frontend_ui_integration):
    passed_tests += 1

print("\n" + "=" * 75)
print(f"FINAL RESULT: {passed_tests} / {total_tests} TESTS PASSED ({(passed_tests/total_tests)*100:.1f}%)")
print("=" * 75)
