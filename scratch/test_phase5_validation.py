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

    port = 9226
    user_data_dir = r"c:\Users\Hiya\OneDrive\Desktop\BIRDSEYE\scratch\edge_temp_profile_phase5"
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

    print("[1] Spawning headless Edge browser on debug port 9226...")
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

        html_path = os.path.abspath("frontend/index.html").replace("\\", "/")
        file_url = f"file:///{html_path}"
        print(f"[2] Navigating to {file_url}...")
        client.send_cmd("Page.navigate", {"url": file_url})
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
        client.evaluate("executeSemanticSearch()")
        time.sleep(3.5)
        ret_count = client.evaluate("APP.searchResults.length")
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
        time.sleep(3.5)
        bg_before = client.evaluate("document.getElementById('cmpBefore').style.backgroundImage")
        bg_after = client.evaluate("document.getElementById('cmpAfter').style.backgroundImage")
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

        # Step 8: Validate Phase 5A Evaluation Metrics Tab
        print("[8] Validating Phase 5A Evaluation Metrics...")
        client.evaluate("showTab('evaluation')")
        time.sleep(2.0)

        # Check Ground-Truth Notice
        gt_notice_heading = client.evaluate("document.querySelector('.eval-notice h4').textContent")
        print(f"    Ground-Truth Notice Heading: {gt_notice_heading}")
        assert "GROUND TRUTH: NOT AVAILABLE LOCALLY" in gt_notice_heading

        # Check Telemetry Strip values
        tiles_text = client.evaluate("document.getElementById('evalIndexedTiles').textContent")
        vectors_text = client.evaluate("document.getElementById('evalFaissVectors').textContent")
        safe_text = client.evaluate("document.getElementById('evalSafeProducts').textContent")
        sar_text = client.evaluate("document.getElementById('evalSarStatus').textContent")
        print(f"    Evaluation Telemetry: Tiles={tiles_text}, Vectors={vectors_text}, SAFE={safe_text}, SAR={sar_text}")
        assert "909" in tiles_text
        assert "908" in vectors_text
        assert "3" in safe_text
        assert "Not Cached" in sar_text

        # Run live benchmark pass
        print("    Triggering live benchmark pass button...")
        client.evaluate("document.getElementById('runEvalBenchmarkBtn').click()")
        for _ in range(25):
            time.sleep(1.0)
            if not client.evaluate("APP.evaluation.running"):
                break

        # Verify populated latency table
        lat_text = client.evaluate("document.getElementById('latTextEmb').textContent")
        lat_img = client.evaluate("document.getElementById('latImgEmb').textContent")
        lat_faiss = client.evaluate("document.getElementById('latFaiss').textContent")
        lat_spectral = client.evaluate("document.getElementById('latSpectral').textContent")
        lat_spatial = client.evaluate("document.getElementById('latSpatial').textContent")
        bench_stamp = client.evaluate("document.getElementById('evalBenchStamp').textContent")
        print(f"    Live Latency: Text={lat_text}, Vision={lat_img}, FAISS={lat_faiss}, Spectral={lat_spectral}, Spatial={lat_spatial}")
        print(f"    Benchmark Timestamp: {bench_stamp}")
        assert "ms" in lat_text
        assert "ms" in lat_img
        assert "ms" in lat_faiss
        assert "Verified live" in bench_stamp
        print("    [PASS] Phase 5A Evaluation Metrics validated.")

        # Step 9: Validate Phase 5B Ingestion & Indexing Tab
        print("[9] Validating Phase 5B Ingestion & Indexing...")
        client.evaluate("showTab('ingest')")
        time.sleep(2.0)

        # Check Ingest Telemetry Strip
        ingest_cat = client.evaluate("document.getElementById('ingestCatalogCount').textContent")
        ingest_vec = client.evaluate("document.getElementById('ingestVectorCount').textContent")
        ingest_sec = client.evaluate("document.getElementById('ingestSecurityMode').textContent")
        print(f"    Ingest Telemetry: Catalog={ingest_cat}, FAISS Vectors={ingest_vec}, Mode={ingest_sec}")
        assert "909" in ingest_cat
        assert "908" in ingest_vec
        assert "Strict Air-Gap" in ingest_sec or "Air-Gap" in ingest_sec

        # Execute Non-Destructive Ingestion Test
        print("    Executing non-destructive sample ingestion test with catalog tile...")
        client.evaluate("document.getElementById('testIngestSampleBtn').click()")
        for _ in range(40):
            time.sleep(1.0)
            has_feed = client.evaluate("APP.ingest.feed && APP.ingest.feed.length > 0")
            is_running = client.evaluate("APP.ingest.running")
            if has_feed and not is_running:
                break

        # Verify Step Checklist Results
        step_hash_status = client.evaluate("document.getElementById('stepHash').className")
        step_clip_status = client.evaluate("document.getElementById('stepClip').className")
        step_faiss_status = client.evaluate("document.getElementById('stepFaiss').className")
        print(f"    Checklist statuses: stepHash={step_hash_status}, stepClip={step_clip_status}, stepFaiss={step_faiss_status}")
        assert "ok" in step_hash_status
        assert "skipped" in step_clip_status
        assert "skipped" in step_faiss_status

        # Verify Feed row
        feed_rows_count = client.evaluate("document.querySelectorAll('#ingestFeed .feed-row').length")
        feed_badge = client.evaluate("document.querySelector('#ingestFeed .feed-row .badge')?.textContent")
        print(f"    Ingestion Feed entries: {feed_rows_count}, Latest Badge: {feed_badge}")
        assert feed_rows_count >= 1
        assert "DUPLICATE" in feed_badge

        # Verify vector count remains 908 (baseline preservation)
        vec_after = client.evaluate("APP.faissCount")
        print(f"    APP.faissCount baseline: {vec_after}")
        assert vec_after == 908
        print("    [PASS] Phase 5B Ingestion & Indexing validated.")

        # Step 10: Check console errors
        print("[10] Checking browser errors...")
        logs = client.evaluate("window.__test_errors || []")
        print(f"    Captured errors: {logs}")
        assert len(logs) == 0

        print("\n=======================================================")
        print("PHASE 5 COMPREHENSIVE VALIDATION: ALL TESTS PASSED!")
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
