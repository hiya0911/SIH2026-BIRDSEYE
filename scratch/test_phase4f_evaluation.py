"""
BIRDSΣY3 — Phase 4F Evaluation & Benchmarking Test Suite
Verifies reproducible evaluation engine, API endpoints, dataset inventory, provenance tracking,
multimodal fusion, change detection, false-alarm suppression, preprocessing telemetry,
performance reference timings, and regressions across Phase 1–4E without metric fabrication.
"""

import os
import sys
import json
import unittest
from fastapi.testclient import TestClient

# Ensure root and backend directories are on Python path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from main import app
from evaluation import SystemEvaluator
from database import tiles_collection

client = TestClient(app)


class TestPhase4FEvaluation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.evaluator = SystemEvaluator()
        cls.report = cls.evaluator.run_full_evaluation(write_files=True)

    # 1. Backend health
    def test_01_backend_health(self):
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "healthy")

    # 2. Evaluation report generation
    def test_02_evaluation_report_generation(self):
        self.assertIsNotNone(self.report)
        self.assertEqual(self.report.get("status"), "EVALUATED_AND_VERIFIED")
        self.assertTrue(os.path.exists(self.evaluator.output_json_path))
        self.assertTrue(os.path.exists(self.evaluator.output_md_path))

    # 3. Evaluation JSON validity
    def test_03_evaluation_json_validity(self):
        with open(self.evaluator.output_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("generated_at", data)
        self.assertIn("dataset_inventory", data)
        self.assertIn("model_provenance", data)
        self.assertIn("retrieval_validation", data)
        self.assertIn("performance_timings", data)

    # 4. Dataset inventory
    def test_04_dataset_inventory(self):
        inv = self.report.get("dataset_inventory", {})
        self.assertGreaterEqual(inv.get("indexed_tiles_count", 0), 900)
        self.assertGreaterEqual(inv.get("safe_products_staged", 0), 3)
        self.assertIn("Sentinel-2B MSI (Multi-Spectral Instrument)", inv.get("sensors_available", []))
        self.assertEqual(inv.get("sar_sentinel1_status"), "SAR_NOT_CACHED_LOCALLY")

    # 5. Model provenance
    def test_05_model_provenance(self):
        prov = self.report.get("model_provenance", {})
        self.assertEqual(prov.get("embedding_model", {}).get("name"), "OpenAI CLIP ViT-B/32")
        self.assertEqual(prov.get("embedding_model", {}).get("dimension"), 512)
        self.assertEqual(prov.get("vector_index", {}).get("library"), "FAISS (Facebook AI Similarity Search)")
        self.assertEqual(prov.get("ground_truth_annotations", {}).get("provenance_status"), "NOT RECORDED")

    # 6. Semantic retrieval validation
    def test_06_semantic_retrieval_validation(self):
        ret = self.report.get("retrieval_validation", {})
        self.assertEqual(ret.get("status"), "SYSTEM_FUNCTIONAL")
        self.assertEqual(ret.get("ground_truth_accuracy"), "Ground-truth relevance labels unavailable")
        queries = ret.get("queries_evaluated", [])
        self.assertEqual(len(queries), 4)
        for q in queries:
            self.assertTrue(q.get("rank_monotonicity_valid"))
            self.assertGreater(q.get("returned_count"), 0)

    # 7. Image retrieval validation
    def test_07_image_retrieval_validation(self):
        doc = tiles_collection.find_one()
        sample_tile_id = doc["tile_id"] if doc else "e87b4d6c-9cdb-4293-8a8b-7ad7a5af6e43"
        resp = client.post("/api/search/image", json={"tile_id": sample_tile_id, "top_k": 5})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("tile_id"), sample_tile_id)
        self.assertGreater(len(data.get("results", [])), 0)

    # 8. Multimodal validation
    def test_08_multimodal_validation(self):
        mm = self.report.get("multimodal_validation", {})
        self.assertEqual(mm.get("status"), "SYSTEM_FUNCTIONAL")
        self.assertEqual(mm.get("fusion_formula"), "S_multimodal = w_text * S_text + w_image * S_image")
        self.assertTrue(mm.get("weights", {}).get("sum_equals_1.0"))
        self.assertGreater(mm.get("returned_results_count"), 0)

    # 9. Change-analysis validation
    def test_09_change_analysis_validation(self):
        chg = self.report.get("change_validation", {})
        self.assertEqual(chg.get("status"), "SYSTEM_FUNCTIONAL")
        self.assertEqual(chg.get("earliest_usable_observation"), "2024-02-23")
        self.assertEqual(len(chg.get("available_epochs", [])), 3)
        self.assertTrue(chg.get("output_determinism_verified"))

    # 10. False-alarm validation
    def test_10_false_alarm_validation(self):
        fa = self.report.get("false_alarm_validation", {})
        self.assertEqual(fa.get("status"), "PASS")
        checks = fa.get("false_alarm_checks", [])
        self.assertGreaterEqual(len(checks), 3)
        for c in checks:
            self.assertIn(c.get("status"), ["SUPPRESSED", "PASS"])

    # 11. Preprocessing validation
    def test_11_preprocessing_validation(self):
        prep = self.report.get("preprocessing_validation", {})
        self.assertEqual(prep.get("status"), "PASS")
        self.assertEqual(prep.get("pipeline_stages_total"), 8)
        self.assertIn("Signal-to-Noise Ratio (SNR): NOT_AVAILABLE", prep.get("unmeasurable_metrics", []))

    # 12. Performance timing generation
    def test_12_performance_timing_generation(self):
        tim = self.report.get("performance_timings", {})
        self.assertIn("text_embedding_extraction_ms", tim)
        self.assertIn("image_embedding_extraction_ms", tim)
        self.assertIn("faiss_vector_search_top10_ms", tim)
        self.assertGreater(tim.get("total_full_evaluation_ms", 0), 0)

    # 13. API evaluation endpoints
    def test_13_api_evaluation_endpoints(self):
        resp_report = client.get("/api/evaluation/report")
        self.assertEqual(resp_report.status_code, 200)
        data_rep = resp_report.json()
        self.assertEqual(data_rep.get("status"), "EVALUATED_AND_VERIFIED")

        resp_summary = client.get("/api/evaluation/summary")
        self.assertEqual(resp_summary.status_code, 200)
        data_sum = resp_summary.json()
        self.assertEqual(data_sum.get("ground_truth_status"), "GROUND TRUTH: NOT AVAILABLE LOCALLY")

    # 14. Frontend evaluation integration
    def test_14_frontend_evaluation_integration(self):
        with open(os.path.join(BASE_DIR, "frontend", "index.html"), "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn('GROUND TRUTH STATUS: NOT AVAILABLE LOCALLY', html)
        self.assertIn('id="trigger-eval-btn"', html)

        with open(os.path.join(BASE_DIR, "frontend", "script.js"), "r", encoding="utf-8") as f:
            js = f.read()
        self.assertIn("loadEvaluationMetrics", js)
        self.assertIn("initLiveBenchmarkEvaluation", js)

    # 15. Offline local data verification
    def test_15_offline_local_data_verification(self):
        inv = self.report.get("dataset_inventory", {})
        self.assertEqual(inv.get("geographic_coverage", {}).get("native_crs"), "EPSG:32645 (WGS 84 / UTM zone 45N)")
        self.assertEqual(inv.get("geographic_coverage", {}).get("tile_grid_id"), "T45QXF")

    # 16. No fabricated accuracy metrics
    def test_16_no_fabricated_accuracy_metrics(self):
        gt = self.report.get("ground_truth_status", {})
        self.assertEqual(gt.get("labelled_relevance_pairs"), "UNAVAILABLE_LOCALLY")
        self.assertEqual(gt.get("pixel_level_change_masks"), "UNAVAILABLE_LOCALLY")
        self.assertNotIn("precision_pct", self.report.get("change_validation", {}))
        self.assertNotIn("iou_score", self.report.get("change_validation", {}))

    # 17. Phase 4E multimodal regression
    def test_17_phase_4e_multimodal_regression(self):
        resp = client.post("/api/search/multimodal", data={
            "query": "Dense forest canopy",
            "text_weight": 0.6,
            "image_weight": 0.4,
            "top_k": 5
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn(data.get("mode"), ["multimodal", "text_only"])
        self.assertGreater(len(data.get("results", [])), 0)

    # 18. Phase 4D change investigation regression
    def test_18_phase_4d_change_investigation_regression(self):
        doc = tiles_collection.find_one()
        sample_tile_id = doc["tile_id"] if doc else "e87b4d6c-9cdb-4293-8a8b-7ad7a5af6e43"
        resp_case = client.post("/api/cases", json={
            "tile_id": sample_tile_id,
            "aoi_name": "Phase 4F Regression Test AOI",
            "notes": "Testing Phase 4D investigation workspace regression"
        })
        self.assertEqual(resp_case.status_code, 200)
        case_id = resp_case.json().get("case", {}).get("case_id")
        self.assertTrue(case_id)

        resp_inv = client.get(f"/api/cases/{case_id}/investigation")
        self.assertEqual(resp_inv.status_code, 200)
        inv_data = resp_inv.json()
        self.assertIn("investigation_summary", inv_data)
        self.assertIn("observations_timeline", inv_data)

    # 19. Phase 4C AOI regression
    def test_19_phase_4c_aoi_regression(self):
        resp = client.post("/api/aoi/query", json={
            "bbox": [88.30, 22.50, 88.40, 22.60],
            "limit": 10
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "success")
        self.assertEqual(data.get("query_type"), "bbox")

    # 20. SAR honesty regression
    def test_20_sar_honesty_regression(self):
        resp_sar = client.get("/api/sar/status")
        self.assertEqual(resp_sar.status_code, 200)
        sar_data = resp_sar.json()
        self.assertEqual(sar_data.get("status_code"), "SAR_NOT_CACHED_LOCALLY")

        resp_search = client.post("/api/search/semantic", json={
            "query": "Water bodies",
            "sensor_filter": "SAR"
        })
        self.assertEqual(resp_search.status_code, 200)
        self.assertFalse(resp_search.json().get("available"))
        self.assertEqual(resp_search.json().get("search_id"), "sar_not_cached")


if __name__ == "__main__":
    unittest.main()
