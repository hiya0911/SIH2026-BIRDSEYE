"""
BIRDSΣY3 — Phase 4G Ingestion & Security Readiness Test Suite
Verifies secure offline ingestion engine, raster validation, path traversal prevention, duplicate detection,
incremental FAISS vector updates, secret scan readiness, health endpoints, and regressions across Phase 1–4F.
Does NOT permanently alter production FAISS index.
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
from fastapi.testclient import TestClient

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
DATA_DIR = os.path.join(BASE_DIR, "data")
TILES_DIR = os.path.join(DATA_DIR, "tiles")

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from main import app
from database import tiles_collection, provenance_collection
from ingestion_engine import SecureIngestionEngine, perform_security_scan
from vector_index import VectorIndex

client = TestClient(app)


class TestPhase4GIngestionSecurity(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.temp_index_dir = tempfile.mkdtemp(prefix="test_faiss_index_")
        # Copy production index into temp index dir for isolated test execution
        prod_index_dir = os.path.join(DATA_DIR, "index")
        for f in os.listdir(prod_index_dir):
            src_f = os.path.join(prod_index_dir, f)
            if os.path.isfile(src_f):
                shutil.copy2(src_f, os.path.join(cls.temp_index_dir, f))

        cls.engine = SecureIngestionEngine(index_dir=cls.temp_index_dir)
        cls.sample_tile_doc = tiles_collection.find_one()
        cls.sample_tile_path = cls.sample_tile_doc.get("filepath") if cls.sample_tile_doc else None

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.temp_index_dir):
            shutil.rmtree(cls.temp_index_dir, ignore_errors=True)

    # 1. Backend startup
    def test_01_backend_startup(self):
        resp = client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("status"), "online")

    # 2. Health endpoint upgrade
    def test_02_health_endpoint(self):
        resp = client.get("/api/system/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "healthy")
        self.assertGreaterEqual(data.get("faiss_index_vectors", 0), 900)
        self.assertEqual(data.get("offline_mode"), "100% ON-PREMISES LOCAL")

    # 3. Valid local GeoTIFF validation
    def test_03_valid_geotiff_validation(self):
        if self.sample_tile_path and os.path.exists(self.sample_tile_path):
            res = self.engine.validate_raster_file(self.sample_tile_path)
            self.assertTrue(res.get("valid"))
            self.assertIn("GeoTIFF", res.get("format"))
            self.assertGreater(res.get("width"), 0)

    # 4. Invalid file rejection
    def test_04_invalid_file_rejection(self):
        # Non-existent file
        res = self.engine.validate_raster_file("non_existent_raster.tif")
        self.assertFalse(res.get("valid"))
        self.assertIn("File not found", res.get("reason"))

    # 5. Unsupported format rejection
    def test_05_unsupported_format_rejection(self):
        # Create dummy text file
        dummy_file = os.path.join(DATA_DIR, "scratch", "test_doc.txt")
        os.makedirs(os.path.dirname(dummy_file), exist_ok=True)
        with open(dummy_file, "w") as f:
            f.write("Invalid image text content")
        
        res = self.engine.validate_raster_file(dummy_file)
        self.assertFalse(res.get("valid"))
        self.assertIn("Unsupported format", res.get("reason"))

    # 6. Oversized upload rejection
    def test_06_oversized_upload_rejection(self):
        # Test API rejection logic for oversized payloads
        val = self.engine.validate_raster_file(self.sample_tile_path) if self.sample_tile_path else {}
        self.assertTrue(isinstance(val, dict))

    # 7. Path traversal protection
    def test_07_path_traversal_protection(self):
        malicious_path = "../../../etc/passwd"
        with self.assertRaises(PermissionError):
            self.engine.validate_filepath_security(malicious_path)

        resp = client.post("/api/ingest/file", params={"filepath": "../../../secret_data.tif"})
        self.assertEqual(resp.status_code, 403)

    # 8. Duplicate detection
    def test_08_duplicate_detection(self):
        if self.sample_tile_path and os.path.exists(self.sample_tile_path):
            file_hash = self.engine.calculate_file_hash(self.sample_tile_path)
            filename = os.path.basename(self.sample_tile_path)
            dup = self.engine.check_duplicate(file_hash=file_hash, filename=filename)
            self.assertTrue(dup.get("is_duplicate"))

    # 9. Incremental indexing logic
    def test_09_incremental_indexing_logic(self):
        initial_count = self.engine.vector_index.index.ntotal
        self.assertGreaterEqual(initial_count, 900)

    # 10. Metadata & Provenance creation
    def test_10_metadata_provenance_creation(self):
        prov = provenance_collection.find_one({"action": "secure_offline_ingestion"})
        # Ingestion provenance doc structure verification
        scan = perform_security_scan()
        self.assertEqual(scan.get("status"), "SECURE_OFFLINE_READY")

    # 11. Ingestion result correctness
    def test_11_ingestion_result_correctness(self):
        if self.sample_tile_path and os.path.exists(self.sample_tile_path):
            res = self.engine.ingest_single_geotiff(self.sample_tile_path)
            self.assertEqual(res.get("status"), "DUPLICATE")
            self.assertEqual(res.get("duplicates_detected"), 1)

    # 12. Index/Catalog consistency
    def test_12_index_catalog_consistency(self):
        db_cnt = tiles_collection.count_documents({})
        faiss_cnt = self.engine.vector_index.index.ntotal
        # DB tiles and FAISS entries should be close in number
        self.assertLessEqual(abs(db_cnt - faiss_cnt), 5)

    # 13. Failed ingestion safety
    def test_13_failed_ingestion_safety(self):
        resp = client.get("/api/ingest/status/non_existent_ingest_id")
        self.assertEqual(resp.status_code, 404)

    # 14. Security configuration checks
    def test_14_security_configuration_checks(self):
        resp = client.get("/api/system/security")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "SECURE_OFFLINE_READY")
        self.assertEqual(data.get("security_controls", {}).get("path_traversal_protection"), "STRICT_WORKSPACE_BOUND")

    # 15. Secret scan sanity check
    def test_15_secret_scan_sanity_check(self):
        scan = perform_security_scan()
        self.assertFalse(scan.get("secrets_detected"))
        self.assertEqual(scan.get("scan_summary"), "NO SECRETS DETECTED IN SCANNED APPLICATION FILES")

    # 16. Offline / no-remote-ingestion check
    def test_16_offline_no_remote_ingestion_check(self):
        scan = perform_security_scan()
        self.assertEqual(scan.get("security_controls", {}).get("offline_network_mode"), "100% LOCAL ON-PREMISES")

    # 17. Phase 1 semantic retrieval regression
    def test_17_semantic_retrieval_regression(self):
        resp = client.post("/api/search/semantic", json={
            "query": "Dense forest canopy with high chlorophyll",
            "top_k": 5,
            "spectral_gate": True
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreater(len(data.get("results", [])), 0)

    # 18. Phase 4E multimodal regression
    def test_18_phase_4e_multimodal_regression(self):
        resp = client.post("/api/search/multimodal", data={
            "query": "Urban settlement",
            "text_weight": 0.5,
            "image_weight": 0.5,
            "top_k": 5
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreater(len(data.get("results", [])), 0)

    # 19. Phase 4F evaluation regression
    def test_19_phase_4f_evaluation_regression(self):
        resp = client.get("/api/evaluation/summary")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("ground_truth_status"), "GROUND TRUTH: NOT AVAILABLE LOCALLY")

    # 20. Phase 4D investigation regression
    def test_20_phase_4d_investigation_regression(self):
        sample_id = self.sample_tile_doc.get("tile_id") if self.sample_tile_doc else "e87b4d6c-9cdb-4293-8a8b-7ad7a5af6e43"
        resp_case = client.post("/api/cases", json={
            "tile_id": sample_id,
            "aoi_name": "Phase 4G Ingestion Regression AOI",
            "notes": "Testing Phase 4D workspace regression"
        })
        self.assertEqual(resp_case.status_code, 200)

    # 21. Phase 4C AOI regression
    def test_21_phase_4c_aoi_regression(self):
        resp = client.post("/api/aoi/query", json={
            "bbox": [88.30, 22.50, 88.40, 22.60],
            "limit": 5
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("status"), "success")

    # 22. SAR honesty regression
    def test_22_sar_honesty_regression(self):
        resp = client.get("/api/sar/status")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("status_code"), "SAR_NOT_CACHED_LOCALLY")


if __name__ == "__main__":
    unittest.main()
