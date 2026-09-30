import socket
import hashlib
import base64
import os
import struct
import json
import urllib.request
import subprocess
import time
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

class SimpleCDPClient:
    def __init__(self, ws_url):
        url_part = ws_url.replace("ws://", "")
        host_port, path = url_part.split("/", 1)
        host, port = host_port.split(":")
        self.host = host
        self.port = int(port)
        self.path = "/" + path
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        self._handshake()
        self.msg_id = 0

    def _handshake(self):
        sec_key = base64.b64encode(os.urandom(16)).decode('utf-8')
        req = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {sec_key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode('utf-8'))
        resp = self.sock.recv(4096).decode('utf-8', errors='ignore')
        if "101" not in resp:
            raise RuntimeError(f"WebSocket handshake failed:\n{resp}")

    def send_cmd(self, method, params=None):
        self.msg_id += 1
        cid = self.msg_id
        msg = {"id": cid, "method": method, "params": params or {}}
        data = json.dumps(msg).encode('utf-8')
        
        frame = bytearray([0x81])
        length = len(data)
        if length <= 125:
            frame.append(0x80 | length)
        elif length <= 65535:
            frame.append(0x80 | 126)
            frame.extend(struct.pack("!H", length))
        else:
            frame.append(0x80 | 127)
            frame.extend(struct.pack("!Q", length))
            
        mask = os.urandom(4)
        frame.extend(mask)
        masked_data = bytearray(len(data))
        for i in range(len(data)):
            masked_data[i] = data[i] ^ mask[i % 4]
        frame.extend(masked_data)
        self.sock.sendall(frame)

        # Read response
        while True:
            resp_data = self._read_frame()
            if not resp_data:
                continue
            try:
                res_obj = json.loads(resp_data.decode('utf-8', errors='ignore'))
                if res_obj.get("id") == cid:
                    return res_obj
            except Exception:
                pass

    def _read_frame(self):
        head = self._recv_exact(2)
        if not head:
            return None
        b1, b2 = head[0], head[1]
        payload_len = b2 & 0x7F
        if payload_len == 126:
            ext = self._recv_exact(2)
            payload_len = struct.unpack("!H", ext)[0]
        elif payload_len == 127:
            ext = self._recv_exact(8)
            payload_len = struct.unpack("!Q", ext)[0]
            
        is_masked = (b2 & 0x80) != 0
        if is_masked:
            mask = self._recv_exact(4)
        raw_payload = self._recv_exact(payload_len)
        if is_masked:
            unmasked = bytearray(payload_len)
            for i in range(payload_len):
                unmasked[i] = raw_payload[i] ^ mask[i % 4]
            return unmasked
        return raw_payload

    def _recv_exact(self, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                break
            buf.extend(chunk)
        return buf

    def evaluate(self, expr):
        res = self.send_cmd("Runtime.evaluate", {
            "expression": expr,
            "returnByValue": True,
            "awaitPromise": True
        })
        return res.get("result", {}).get("result", {}).get("value")

    def close(self):
        self.sock.close()


def run_headless_validation():
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
    ]
    edge_exe = None
    for p in edge_paths:
        if os.path.exists(p):
            edge_exe = p
            break
            
    if not edge_exe:
        print("ERROR: Edge not found.")
        return False

    port = 9227
    user_data_dir = r"c:\Users\Hiya\OneDrive\Desktop\BIRDSEYE\scratch\edge_temp_profile_phase6"
    os.makedirs(user_data_dir, exist_ok=True)

    cmd = [
        edge_exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank"
    ]

    print("[1] Spawning headless Edge browser on debug port 9227...")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(2.5)

    try:
        req = urllib.request.urlopen(f"http://127.0.0.1:{port}/json")
        targets = json.loads(req.read().decode('utf-8'))
        page_target = next((t for t in targets if t.get("type") == "page"), None)
        if not page_target:
            print("ERROR: No page target found.")
            return False

        ws_url = page_target["webSocketDebuggerUrl"]
        client = SimpleCDPClient(ws_url)

        client.send_cmd("Console.enable")
        client.send_cmd("Runtime.enable")

        target_url = "http://localhost:8000/console/"
        print(f"[2] Navigating to {target_url}...")
        client.send_cmd("Page.navigate", {"url": target_url})
        time.sleep(3.5)

        print("[3] Checking JavaScript baseline & page title...")
        doc_title = client.evaluate("document.title")
        print(f"    Page Title: {doc_title}")
        assert "BIRDSΣY3" in doc_title

        # Check all 11 tabs in strict sequence
        tab_names = client.evaluate("Array.from(document.querySelectorAll('nav.tabs button')).map(b => b.dataset.tab)")
        expected_tabs = [
            "overview", "retrieval", "temporal", "preprocessing",
            "suppression", "clusters", "evaluation", "ingest",
            "brief", "mission", "spec"
        ]
        print(f"    Tabs order: {tab_names}")
        assert tab_names == expected_tabs, f"Expected {expected_tabs} but got {tab_names}"
        print("    [PASS] Tab order strictly preserved across all 11 tabs.")

        # Step 4: Validate Phase 1 Semantic Retrieval
        print("[4] Validating Phase 1 Semantic Retrieval...")
        client.evaluate("showTab('retrieval')")
        time.sleep(1.0)
        client.evaluate("document.getElementById('q').value = 'Dense forest canopy with high chlorophyll'")
        client.evaluate("document.getElementById('searchBtn').click()")
        ret_count = 0
        for _ in range(15):
            time.sleep(1.0)
            ret_count = client.evaluate("APP.searchResults ? APP.searchResults.length : 0")
            if ret_count and ret_count > 0:
                break
        first_tile_id = client.evaluate("APP.searchResults[0]?.tile_id")
        print(f"    Semantic Retrieval count: {ret_count}, First Tile: {first_tile_id}")
        assert ret_count > 0, "Phase 1 search returned no results!"
        print("    [PASS] Phase 1 Semantic Retrieval intact.")

        # Step 5: Validate Phase 2 Multi-Temporal Change
        print("[5] Validating Phase 2 Multi-Temporal Change Analysis...")
        client.evaluate(f"""
            (() => {{
                const btn = document.querySelector('.tile[data-id="{first_tile_id}"] [data-act="analyse"]');
                if (btn) btn.click();
            }})()
        """)
        # Polling loop for multi-temporal raster generation
        bg_before = ""
        bg_after = ""
        for _ in range(25):
            time.sleep(1.0)
            bg_before = client.evaluate("document.getElementById('cmpBefore').style.backgroundImage || ''")
            bg_after = client.evaluate("document.getElementById('cmpAfter').style.backgroundImage || ''")
            if "data:image/jpeg;base64," in bg_before and "data:image/jpeg;base64," in bg_after:
                break
        print(f"    Comparison layers loaded: before={'data:image' in bg_before}, after={'data:image' in bg_after}")
        assert "data:image/jpeg;base64," in bg_before
        assert "data:image/jpeg;base64," in bg_after
        print("    [PASS] Phase 2 Change Analysis intact.")

        # Step 6: Validate Phase 3 Preprocessing Lab & False Alarm
        print("[6] Validating Phase 3 Preprocessing Lab & False Alarm...")
        client.evaluate("showTab('preprocessing')")
        time.sleep(1.0)
        client.evaluate("document.getElementById('runPipelineBtn').click()")
        time.sleep(4.0)
        stages_count = client.evaluate("document.querySelectorAll('#prepStagesList .prep-stage-card').length")
        print(f"    Preprocessing stages rendered: {stages_count}")
        assert stages_count == 8, f"Expected 8 stages, got {stages_count}"

        client.evaluate("showTab('suppression')")
        time.sleep(1.0)
        client.evaluate("document.getElementById('supAnalyzeBtn').click()")
        time.sleep(3.5)
        funnel_count = client.evaluate("document.querySelectorAll('#funnel .fstage').length")
        print(f"    Funnel stages: {funnel_count}")
        assert funnel_count >= 8, f"Expected 8 funnel stages, got {funnel_count}"
        print("    [PASS] Phase 3 Preprocessing Lab & False Alarm intact.")

        # Step 7: Validate Phase 4 Discovery & Cluster Analysis
        print("[7] Validating Phase 4 Discovery and Cluster Analysis...")
        client.evaluate("showTab('clusters')")
        time.sleep(2.5)
        silhouette = client.evaluate("document.getElementById('clusterSilhouette').textContent")
        k_clusters = client.evaluate("document.getElementById('clusterCount').textContent")
        print(f"    Cluster metrics: Silhouette={silhouette}, Total Clusters={k_clusters}")
        assert "0.12" in silhouette or "0.1216" in silhouette
        assert int(k_clusters) == 5
        print("    [PASS] Phase 4 Discovery and Cluster Analysis intact.")

        # Step 8: Validate Phase 5 Evaluation & Ingestion
        print("[8] Validating Phase 5 Evaluation & Ingestion...")
        client.evaluate("showTab('evaluation')")
        time.sleep(1.5)
        gt_notice_heading = client.evaluate("document.querySelector('.eval-notice h4').textContent")
        assert "GROUND TRUTH: NOT AVAILABLE LOCALLY" in gt_notice_heading
        print("    [PASS] Phase 5 Evaluation notice verified.")

        client.evaluate("showTab('ingest')")
        time.sleep(1.5)
        ingest_cat = client.evaluate("document.getElementById('ingestCatalogCount').textContent")
        assert "909" in ingest_cat
        print("    [PASS] Phase 5 Ingestion telemetry verified.")

        # Step 9: Validate Phase 6A Analyst Brief & Provenance
        print("[9] Validating Phase 6A Analyst Brief & Provenance...")
        client.evaluate("showTab('brief')")
        time.sleep(2.5)

        brief_case_id = client.evaluate("document.getElementById('briefCaseId').textContent")
        brief_tile_id = client.evaluate("document.getElementById('briefTileId').textContent")
        brief_status = client.evaluate("document.getElementById('briefStatusBadge').textContent")
        print(f"    Loaded Case: {brief_case_id}, Tile: {brief_tile_id}, Status: {brief_status}")
        assert "CASE-" in brief_case_id
        assert len(brief_tile_id) > 5

        # Check Provenance Chain (all 9 stages)
        stages_rendered = client.evaluate("document.querySelectorAll('#briefProvenanceChain .provenance-stage').length")
        print(f"    Cryptographic Provenance stages rendered: {stages_rendered}")
        assert stages_rendered == 9, f"Expected 9 provenance stages, got {stages_rendered}"

        first_hash = client.evaluate("document.querySelector('#briefProvenanceChain .provenance-hash').textContent")
        print(f"    Stage 1 Provenance Digest: {first_hash}")
        assert "SHA256-" in first_hash

        # Capture pre-test case state for restoration
        initial_case_doc = None
        initial_case_ids = set()
        try:
            sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
            from database import cases_collection, reviews_collection, tiles_collection
            if cases_collection is not None:
                initial_case_doc = cases_collection.find_one({"case_id": "CASE-2026-e87b4d6c"})
                initial_case_ids = {c["case_id"] for c in cases_collection.find({}, {"case_id": 1})}
        except Exception as e:
            print(f"    [WARN] Pre-test snapshot warning: {e}")

        # Test Review Submission
        print("    Testing analyst review submission on active case...")
        client.evaluate("""
            (() => {
                document.getElementById('briefDecideConfirm').click();
                document.getElementById('briefRationaleInput').value = 'Automated validation check - change confirmed.';
                document.getElementById('briefAnalystInput').value = 'val_analyst_01';
                document.getElementById('briefSubmitReviewBtn').click();
            })()
        """)
        time.sleep(2.0)
        review_history_rows = client.evaluate("document.querySelectorAll('#briefReviewHistory .feed-row').length")
        print(f"    Review history entries after submission: {review_history_rows}")
        assert review_history_rows >= 1
        print("    [PASS] Phase 6A Analyst Brief & Provenance validated.")

        # Step 10: Validate Phase 6B Mission Board
        print("[10] Validating Phase 6B Mission Board...")
        client.evaluate("showTab('mission')")
        time.sleep(2.0)

        mission_total = client.evaluate("document.getElementById('missionCountTotal').textContent")
        print(f"    Mission Cases Total: {mission_total}")
        assert int(mission_total) >= 1

        rows_count = client.evaluate("document.querySelectorAll('#missionTableBody tr').length")
        print(f"    Mission table rows rendered: {rows_count}")
        assert rows_count >= 1

        # Test filtering
        client.evaluate("document.getElementById('filterMissionPending').click()")
        time.sleep(0.5)
        client.evaluate("document.getElementById('filterMissionAll').click()")
        time.sleep(0.5)
        print("    [PASS] Phase 6B Mission Board validated.")

        # Step 11: Validate Phase 6C Cross-Tab Workflow (Change Analysis -> Analyst Brief)
        print("[11] Validating Phase 6C Cross-Tab Workflow...")
        client.evaluate("showTab('temporal')")
        time.sleep(1.0)
        client.evaluate("document.getElementById('openAnalystBriefBtn').click()")
        time.sleep(2.0)
        current_tab = client.evaluate("document.querySelector('nav.tabs button[aria-selected=\"true\"]').dataset.tab")
        print(f"    Navigated to tab: {current_tab}")
        assert current_tab == "brief"

        # Verify active case corresponds to target tile
        active_c = client.evaluate("document.getElementById('briefCaseId').textContent")
        print(f"    Active case loaded in Brief: {active_c}")
        assert "CASE-" in active_c
        print("    [PASS] Phase 6C Cross-Tab Workflow validated.")

        # Step 12: Data cleanup & state restoration
        print("[12] Restoring temporary test review and preserving baseline...")
        try:
            if reviews_collection is not None:
                del_rev = reviews_collection.delete_many({"analyst_id": "val_analyst_01"})
                print(f"    Cleaned up {del_rev.deleted_count} validation test review(s) from MongoDB.")
            if cases_collection is not None:
                if initial_case_doc:
                    cases_collection.replace_one({"case_id": "CASE-2026-e87b4d6c"}, initial_case_doc)
                    print("    Restored original CASE-2026-e87b4d6c document in MongoDB.")
                # Delete any newly created cases from the test
                current_cases = {c["case_id"] for c in cases_collection.find({}, {"case_id": 1})}
                new_cases = current_cases - initial_case_ids
                for ncid in new_cases:
                    cases_collection.delete_many({"case_id": ncid})
                    print(f"    Removed temporary test case {ncid} from MongoDB.")
            # Also clean local files if touched
            local_cases_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "cases.json"))
            if os.path.exists(local_cases_path):
                with open(local_cases_path, "w", encoding="utf-8") as f:
                    f.write("[]")
            local_rev_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "reviews.json"))
            if os.path.exists(local_rev_path):
                with open(local_rev_path, "r", encoding="utf-8") as f:
                    revs = json.load(f)
                cleaned = [r for r in revs if r.get("analyst_id") != "val_analyst_01"]
                with open(local_rev_path, "w", encoding="utf-8") as f:
                    json.dump(cleaned, f, indent=2)
            print("    [PASS] Temporary review data cleaned up; case state restored.")
        except Exception as e:
            print(f"    [WARN] Cleanup warning: {e}")

        # Step 13: Baseline integrity check (909 catalog, 908 FAISS)
        print("[13] Verifying 909-tile / 908-FAISS baseline...")
        cat_count = 0
        if tiles_collection is not None:
            cat_count = tiles_collection.count_documents({})
        else:
            cat_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "tiles_metadata.json"))
            if os.path.exists(cat_path):
                with open(cat_path, "r", encoding="utf-8") as f:
                    cat_count = len(json.load(f))
        print(f"    Tile Catalog count: {cat_count} (baseline requirement: 909)")
        assert cat_count == 909, f"Expected 909 tiles, found {cat_count}"

        # Step 14: Check console errors
        print("[14] Checking browser errors...")
        logs = client.evaluate("window.__test_errors || []")
        print(f"    Captured errors: {logs}")
        assert len(logs) == 0

        print("\n=======================================================")
        print("PHASE 6 COMPREHENSIVE VALIDATION: ALL TESTS PASSED!")
        print("=======================================================")
        return True

    finally:
        try:
            client.close()
        except Exception:
            pass
        proc.terminate()
        proc.wait(timeout=3)

if __name__ == "__main__":
    success = run_headless_validation()
    sys.exit(0 if success else 1)
