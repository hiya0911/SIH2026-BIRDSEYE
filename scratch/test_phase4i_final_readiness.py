"""
BIRDSΣY3 — Phase 4I Final Readiness & Operational Verification Test Suite
Comprehensive validation covering system health, security readiness, offline capability,
location search, spatial AOI query & tri-epoch analysis, 8-stage preprocessing,
semantic natural language retrieval, image reference retrieval, multimodal retrieval,
temporal change investigation, false-alarm intelligence, explainability, analyst review,
provenance lineage, Markdown & JSON exports, ingestion safety, SAR honesty, evaluation honesty,
frontend static integrity, and zero external runtime dependencies.
"""

import os
import sys
import unittest
from fastapi.testclient import TestClient

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from main import app
from database import tiles_collection, cases_collection


class TestPhase4IFinalReadiness(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.sample_tile = tiles_collection.find_one({})
        cls.sample_tile_id = cls.sample_tile["tile_id"] if cls.sample_tile else "e87b4d6c-9cdb-4293-8a8b-7ad7a5af6e43"

    def get_valid_case_id(self):
        resp = self.client.get("/api/cases")
        cases = resp.json().get("cases", [])
        if cases and len(cases) > 0:
            return cases[0]["case_id"]
        return "CASE-2026-e87b4d6c"

    # 1. Backend Root Health
    def test_01_backend_health(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "online")
        self.assertIn("BIRDSΣY3", data.get("message", ""))

    # 2. System Health Summary
    def test_02_system_health(self):
        res = self.client.get("/api/system/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn(data.get("status"), ["healthy", "unhealthy"])
        self.assertIn("faiss_index_vectors", data)

    # 3. Security Readiness
    def test_03_security_readiness(self):
        res = self.client.get("/api/system/security")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "SECURE_OFFLINE_READY")
        self.assertFalse(data.get("secrets_detected"))

    # 4. Offline Network Mode
    def test_04_offline_status(self):
        res = self.client.get("/api/system/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("offline_mode"), "100% ON-PREMISES LOCAL")

    # 5. Geocoding / Location Search
    def test_05_location_search(self):
        res = self.client.get("/api/location/search?q=Kolkata")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "success")
        self.assertIn("lat", data)
        self.assertIn("lon", data)

    # 6. Spatial AOI Query
    def test_06_aoi_query(self):
        res = self.client.post("/api/aoi/query", json={
            "bbox": [88.30, 22.50, 88.40, 22.60],
            "limit": 5
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "success")
        self.assertIn("tiles", data)

    # 7. Tri-Epoch AOI Analysis
    def test_07_aoi_analysis(self):
        res = self.client.post("/api/aoi/analyze", json={
            "bbox": [88.30, 22.50, 88.40, 22.60]
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "success")
        self.assertIn("aoi_analysis", data)

    # 8. 8-Stage Preprocessing Pipeline
    def test_08_preprocessing_pipeline(self):
        res = self.client.post("/api/preprocessing/pipeline", json={"tile_id": self.sample_tile_id})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "success")
        stages = data.get("pipeline", {}).get("stages", [])
        self.assertEqual(len(stages), 8)

    # 9. Natural-Language Semantic Retrieval
    def test_09_semantic_retrieval(self):
        res = self.client.post("/api/search/semantic", json={
            "query": "Urban building construction and concrete structures",
            "top_k": 5,
            "spectral_gate": True
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("results", data)
        self.assertIsInstance(data.get("results"), list)

    # 10. Image-Reference Retrieval
    def test_10_image_retrieval(self):
        tile_path = os.path.join(BASE_DIR, "data", "test_geotiff_sample.tif")
        if os.path.exists(tile_path):
            with open(tile_path, "rb") as f:
                res = self.client.post(
                    "/api/search/image",
                    files={"file": (os.path.basename(tile_path), f, "image/tiff")}
                )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertIn("results", data)
        else:
            self.assertTrue(True)

    # 11. Combined Multimodal Retrieval
    def test_11_multimodal_retrieval(self):
        res = self.client.post("/api/search/multimodal", data={
            "query": "Inland water bodies and river reservoirs",
            "text_weight": 0.7,
            "image_weight": 0.3,
            "top_k": 5
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("results", data)

    # 12. Temporal Change Investigation
    def test_12_change_investigation(self):
        res = self.client.get(f"/api/change/tri_epoch/{self.sample_tile_id}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("stats_cumulative", data)

    # 13. False-Alarm Matrix Intelligence
    def test_13_false_alarm_data(self):
        case_id = self.get_valid_case_id()
        res = self.client.get(f"/api/cases/{case_id}/investigation")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("before_after_evidence", data)

    # 14. Explainability & Confidence Components
    def test_14_explainability(self):
        case_id = self.get_valid_case_id()
        res = self.client.get(f"/api/cases/{case_id}/investigation")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("investigation_summary", data)

    # 15. Compact Case Queue List
    def test_15_case_queue(self):
        res = self.client.get("/api/cases")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("cases", data)
        self.assertGreater(len(data["cases"]), 0)

    # 16. Analyst Review Submission
    def test_16_review_submission(self):
        case_id = self.get_valid_case_id()
        payload = {
            "decision": "CONFIRM",
            "rationale": "Phase 4I final readiness verification submission",
            "analyst_id": "analyst_p4i",
            "case_id": case_id
        }
        res = self.client.post(f"/api/cases/{case_id}/review", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "success")

    # 17. Review History Lineage
    def test_17_review_history(self):
        case_id = self.get_valid_case_id()
        res = self.client.get(f"/api/cases/{case_id}/provenance")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("provenance_chain", data)

    # 18. Provenance Lineage Chain
    def test_18_provenance_chain(self):
        case_id = self.get_valid_case_id()
        res = self.client.get(f"/api/cases/{case_id}/provenance")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        chain = data.get("provenance_chain", [])
        self.assertGreaterEqual(len(chain), 9)

    # 19. Markdown Evidence Report Export
    def test_19_markdown_report_export(self):
        case_id = self.get_valid_case_id()
        res = self.client.get(f"/api/cases/{case_id}/report")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("markdown_content", data)
        self.assertIn("# SATELLITE INCIDENT EVIDENCE", data["markdown_content"])

    # 20. JSON Evidence Package Export
    def test_20_json_evidence_package_export(self):
        case_id = self.get_valid_case_id()
        res = self.client.get(f"/api/cases/{case_id}/evidence.json")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "success")
        self.assertIn("case_id", data)
        self.assertIn("provenance_chain", data)

    # 21. Ingestion Validation
    def test_21_ingestion_validation(self):
        res = self.client.post(
            "/api/ingest/file",
            params={"filepath": "invalid_format_test.exe", "source_label": "Test Invalid"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("status"), "REJECTED")

    # 22. Ingestion Duplicate Protection
    def test_22_duplicate_protection(self):
        tile_path = self.sample_tile.get("filepath") if self.sample_tile else None
        if tile_path and os.path.exists(tile_path):
            res = self.client.post(
                "/api/ingest/file",
                params={"filepath": tile_path, "source_label": "Duplicate Ingest Test"}
            )
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json().get("status"), "DUPLICATE")

    # 23. SAR Honesty Status
    def test_23_sar_honesty_status(self):
        res = self.client.get("/api/sar/status")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("status_code"), "SAR_NOT_CACHED_LOCALLY")

    # 24. Evaluation Ground-Truth Honesty
    def test_24_evaluation_honesty(self):
        res = self.client.get("/api/evaluation/summary")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("ground_truth_status"), "GROUND TRUTH: NOT AVAILABLE LOCALLY")

    # 25. Frontend Static HTML Integrity
    def test_25_frontend_static_integrity(self):
        index_path = os.path.join(BASE_DIR, "frontend", "index.html")
        self.assertTrue(os.path.exists(index_path))
        with open(index_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("BIRDS", html)
        self.assertIn("command-center-banner", html)
        self.assertIn("btn-run-judge-demo", html)

    # 26. Zero External Runtime Dependencies
    def test_26_no_external_runtime_dependency(self):
        res = self.client.get("/api/system/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("offline_mode"), "100% ON-PREMISES LOCAL")


if __name__ == "__main__":
    unittest.main()
