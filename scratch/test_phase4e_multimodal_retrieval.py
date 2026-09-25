"""
Phase 4E Verification Test Suite — SEMANTIC + MULTIMODAL RETRIEVAL INTELLIGENCE
Validates natural-language text search, reference-image search, combined multimodal fusion,
AOI spatial filtering, date range filtering, sensor filtering, transparent explainability,
diversity control, SAR honesty, and regressions across Phases 1-4D.
"""

import unittest
import os
import json
import numpy as np
from fastapi.testclient import TestClient
from PIL import Image
import io

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from main import app

class TestPhase4EMultimodalRetrieval(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.test_tile_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
            "data", "tiles", "tile_00528d6c-d9cd-4523-b4d8-9cb3eb30af96.tif"
        )
        if not os.path.exists(cls.test_tile_path):
            # Fallback to any tile in directory
            tiles_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tiles")
            t_files = [f for f in os.listdir(tiles_dir) if f.endswith(".tif")]
            if t_files:
                cls.test_tile_path = os.path.join(tiles_dir, t_files[0])

    def test_01_backend_health(self):
        """Verifies backend API health check endpoint."""
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["mongodb"], "connected")

    def test_02_semantic_search_endpoint(self):
        """Verifies POST /api/search/semantic executes successfully."""
        payload = {
            "query": "new construction near roads",
            "top_k": 5,
            "spectral_gate": True,
            "action_mode": False
        }
        res = self.client.post("/api/search/semantic", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("results", data)
        self.assertGreater(len(data["results"]), 0)

    def test_03_text_query_ranking(self):
        """Verifies text semantic search produces sorted ranked results with match percentages."""
        payload = {
            "query": "cleared vegetation and deforestation",
            "top_k": 6,
            "spectral_gate": True
        }
        res = self.client.post("/api/search/semantic", json=payload)
        self.assertEqual(res.status_code, 200)
        results = res.json()["results"]
        self.assertGreater(len(results), 0)
        # Check rank ordering
        scores = [r["match_percentage"] for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))
        for r in results:
            self.assertIn("rank", r)
            self.assertIn("explanation", r)

    def test_04_image_upload_retrieval(self):
        """Verifies POST /api/search/image/upload with real tile GeoTIFF."""
        self.assertTrue(os.path.exists(self.test_tile_path), "Test tile GeoTIFF missing on disk.")
        with open(self.test_tile_path, "rb") as f:
            res = self.client.post(
                "/api/search/image/upload",
                files={"file": ("reference_patch.tif", f, "image/tiff")},
                data={"top_k": "5"}
            )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["mode"], "image_only")
        self.assertIn("results", data)
        self.assertGreater(len(data["results"]), 0)
        top_res = data["results"][0]
        self.assertIn("similarity_percentage", top_res)
        self.assertIn("explanation", top_res)

    def test_05_multimodal_retrieval_fusion(self):
        """Verifies POST /api/search/multimodal fuses text query AND reference image."""
        self.assertTrue(os.path.exists(self.test_tile_path))
        with open(self.test_tile_path, "rb") as f:
            res = self.client.post(
                "/api/search/multimodal",
                files={"file": ("reference_patch.tif", f, "image/tiff")},
                data={
                    "query": "expansion of built-up area",
                    "text_weight": "0.6",
                    "image_weight": "0.4",
                    "top_k": "5",
                    "spectral_gate": "true"
                }
            )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["mode"], "multimodal_fusion")
        self.assertIn("fusion_weights", data)
        self.assertEqual(data["fusion_weights"]["text"], 0.6)
        self.assertEqual(data["fusion_weights"]["image"], 0.4)
        results = data["results"]
        self.assertGreater(len(results), 0)
        top_item = results[0]
        self.assertIn("semantic_similarity", top_item)
        self.assertIn("image_similarity", top_item)
        self.assertIn("final_score", top_item)
        self.assertIn("explanation", top_item)
        # Check explanations list contains fusion info
        exp_str = " ".join(top_item["explanation"])
        self.assertIn("Multimodal fusion match", exp_str)

    def test_06_multimodal_text_fallback(self):
        """Verifies multimodal search with text query only falls back to text mode."""
        res = self.client.post(
            "/api/search/multimodal",
            data={"query": "water body expansion", "top_k": "5"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["mode"], "text_only")
        self.assertGreater(len(data["results"]), 0)

    def test_07_multimodal_image_fallback(self):
        """Verifies multimodal search with image file only falls back to image mode."""
        with open(self.test_tile_path, "rb") as f:
            res = self.client.post(
                "/api/search/multimodal",
                files={"file": ("patch.tif", f, "image/tiff")},
                data={"top_k": "5"}
            )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["mode"], "image_only")
        self.assertGreater(len(data["results"]), 0)

    def test_08_multimodal_invalid_query_error(self):
        """Verifies multimodal search with neither text nor image returns HTTP 400 validation error."""
        res = self.client.post(
            "/api/search/multimodal",
            data={"top_k": "5"}
        )
        self.assertEqual(res.status_code, 400)
        detail = res.json()["detail"]
        self.assertIn("At least one query modality", detail)

    def test_09_aoi_spatial_filtering(self):
        """Verifies AOI spatial restriction filters retrieval candidates."""
        aoi_bbox = [88.30, 22.50, 88.45, 22.62] # Kolkata region
        payload = {
            "query": "road development",
            "top_k": 5,
            "aoi_bbox": aoi_bbox
        }
        res = self.client.post("/api/search/semantic", json=payload)
        self.assertEqual(res.status_code, 200)
        results = res.json()["results"]
        for r in results:
            self.assertTrue(r["filters"]["aoi"])
            exp_str = " ".join(r["explanation"])
            self.assertIn("Inside requested AOI", exp_str)

    def test_10_date_range_filtering(self):
        """Verifies start_date and end_date filter candidates by acquisition date."""
        payload = {
            "query": "new infrastructure",
            "top_k": 5,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31"
        }
        res = self.client.post("/api/search/semantic", json=payload)
        self.assertEqual(res.status_code, 200)
        results = res.json()["results"]
        for r in results:
            acq_date = r["acquisition_date"]
            self.assertTrue(acq_date.startswith("2024"), f"Date {acq_date} outside 2024 filter range.")
            self.assertTrue(r["filters"]["date"])

    def test_11_sensor_filtering(self):
        """Verifies OPTICAL returns optical imagery, SAR honestly reports unavailable."""
        # OPTICAL query
        res_opt = self.client.post("/api/search/semantic", json={"query": "vegetation loss", "sensor_filter": "OPTICAL"})
        self.assertEqual(res_opt.status_code, 200)
        self.assertGreater(len(res_opt.json()["results"]), 0)

        # SAR query
        res_sar = self.client.post("/api/search/semantic", json={"query": "vegetation loss", "sensor_filter": "SAR"})
        self.assertEqual(res_sar.status_code, 200)
        sar_data = res_sar.json()
        self.assertFalse(sar_data["available"])
        self.assertEqual(len(sar_data["results"]), 0)
        self.assertIn("Sentinel-1 SAR C-band data is not currently available", sar_data["message"])

    def test_12_explainability_fields(self):
        """Verifies ranked results expose all required explainability fields."""
        res = self.client.post("/api/search/semantic", json={"query": "water body expansion", "top_k": 3})
        self.assertEqual(res.status_code, 200)
        top = res.json()["results"][0]
        self.assertIn("explanation", top)
        self.assertIsInstance(top["explanation"], list)
        self.assertIn("semantic_similarity", top)
        self.assertIn("physical_score", top)
        self.assertIn("filters", top)
        self.assertIn("rank", top)

    def test_13_ranking_determinism(self):
        """Verifies identical inputs produce identical scores and rankings."""
        payload = {"query": "new construction near roads", "top_k": 5}
        res1 = self.client.post("/api/search/semantic", json=payload).json()["results"]
        res2 = self.client.post("/api/search/semantic", json=payload).json()["results"]
        self.assertEqual(len(res1), len(res2))
        for i in range(len(res1)):
            self.assertEqual(res1[i]["tile_id"], res2[i]["tile_id"])
            self.assertEqual(res1[i]["match_percentage"], res2[i]["match_percentage"])

    def test_14_no_sar_fabrication_audit(self):
        """Zero-fabrication audit: Verifies SAR is never fake-generated."""
        res = self.client.post("/api/search/semantic", json={"query": "sar radar change", "sensor_filter": "SAR"})
        data = res.json()
        self.assertFalse(data["available"])
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["results"], [])
        self.assertEqual(data["search_id"], "sar_not_cached")

    def test_15_phase4c_map_aoi_regression(self):
        """Phase 4C Regression: Verifies location search, footprints, AOI query and analysis."""
        # Location search
        res_loc = self.client.get("/api/location/search?q=Kolkata")
        self.assertEqual(res_loc.status_code, 200)
        self.assertEqual(res_loc.json()["status"], "success")

        # Footprints GeoJSON
        res_fp = self.client.get("/api/aoi/footprints?limit=10")
        self.assertEqual(res_fp.status_code, 200)
        self.assertEqual(res_fp.json()["type"], "FeatureCollection")

        # AOI query
        res_aoi = self.client.post("/api/aoi/query", json={"bbox": [88.30, 22.50, 88.45, 22.62], "limit": 5})
        self.assertEqual(res_aoi.status_code, 200)
        self.assertEqual(res_aoi.json()["status"], "success")

    def test_16_phase4d_change_investigation_regression(self):
        """Phase 4D Regression: Verifies investigation timeline, decision logging, report generation."""
        # List cases
        res_cases = self.client.get("/api/cases")
        self.assertEqual(res_cases.status_code, 200)
        cases = res_cases.json()["cases"]
        self.assertGreater(len(cases), 0)
        cid = cases[0]["case_id"]

        # Investigation payload
        res_inv = self.client.get(f"/api/cases/{cid}/investigation")
        self.assertEqual(res_inv.status_code, 200)
        inv = res_inv.json()
        self.assertIn("investigation_summary", inv)
        self.assertIn("false_alarm_intelligence", inv)

        # Analyst decision
        res_dec = self.client.post(f"/api/cases/{cid}/review", json={
            "decision": "CONFIRM",
            "rationale": "Phase 4E regression test verified confirmed built-up expansion.",
            "analyst_id": "test_analyst"
        })
        self.assertEqual(res_dec.status_code, 200)
        self.assertEqual(res_dec.json()["status"], "success")

        # Report Markdown export
        res_rep = self.client.get(f"/api/cases/{cid}/report")
        self.assertEqual(res_rep.status_code, 200)
        self.assertIn("markdown_content", res_rep.json())

    def test_17_preprocessing_and_change_regression(self):
        """Phase 2 & Phase 1 Regression: Verifies preprocessing lab and change detection."""
        # Change analysis for tile
        res_chg = self.client.get("/api/change/tile/e87b4d6c-9cdb-4293-8a8b-7ad7a5af6e43")
        self.assertEqual(res_chg.status_code, 200)
        self.assertIn("stats", res_chg.json())

        # Preprocessing lab pipeline
        res_prep = self.client.post("/api/preprocessing/pipeline", json={
            "year": 2024,
            "tile_id": "e87b4d6c-9cdb-4293-8a8b-7ad7a5af6e43"
        })
        self.assertEqual(res_prep.status_code, 200)
        self.assertEqual(res_prep.json()["status"], "success")

if __name__ == "__main__":
    unittest.main()
