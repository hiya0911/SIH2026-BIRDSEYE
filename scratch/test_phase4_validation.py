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

    port = 9225
    user_data_dir = r"c:\Users\Hiya\OneDrive\Desktop\BIRDSEYE\scratch\edge_temp_profile_phase4"
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

    print("[1] Spawning headless Edge browser on debug port 9225...")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(2)

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
        print("[6] Validating Phase 3 Preprocessing Lab...")
        client.evaluate("showTab('preprocessing')")
        time.sleep(1.0)
        client.evaluate("document.getElementById('runPipelineBtn').click()")
        time.sleep(4.0)
        stages_count = client.evaluate("document.querySelectorAll('#prepStagesList .prep-stage-card').length")
        print(f"    Preprocessing stages rendered: {stages_count}")
        assert stages_count == 8, f"Expected 8 stages, got {stages_count}"
        print("    [PASS] Phase 3 Preprocessing Lab intact.")

        print("[7] Validating Phase 3 False Alarm Suppression...")
        client.evaluate("showTab('suppression')")
        time.sleep(1.0)
        client.evaluate("document.getElementById('supAnalyzeBtn').click()")
        time.sleep(3.5)
        funnel_count = client.evaluate("document.querySelectorAll('#funnel .fstage').length")
        print(f"    Funnel stages: {funnel_count}")
        assert funnel_count >= 8, f"Expected 8 funnel stages, got {funnel_count}"
        print("    [PASS] Phase 3 False Alarm Suppression intact.")

        # Step 8: Validate Phase 4 Discovery & Cluster Analysis
        print("[8] Validating Phase 4 Discovery and Cluster Analysis...")
        client.evaluate("showTab('clusters')")
        time.sleep(2.5)

        # 8a. Telemetry Ribbon & Cluster Summary
        silhouette = client.evaluate("document.getElementById('clusterSilhouette').textContent")
        cluster_count = client.evaluate("document.getElementById('clusterCount').textContent")
        embedding_count = client.evaluate("document.getElementById('clusterEmbeddingCount').textContent")
        print(f"    Silhouette score: {silhouette}, Clusters: {cluster_count}, Embeddings: {embedding_count}")
        assert float(silhouette) > 0.05, f"Invalid silhouette score: {silhouette}"
        assert int(cluster_count) == 5, f"Expected 5 clusters, got {cluster_count}"
        assert int(embedding_count) == 908, f"Expected 908 embeddings, got {embedding_count}"
        print("    [PASS] Cluster telemetry strip matches backend summary.")

        # 8b. PCA Embedding Space Projection
        pca_points_count = client.evaluate("APP.clusters.pcaData.length")
        print(f"    PCA 2D embedding points loaded: {pca_points_count}")
        assert pca_points_count == 908, f"Expected 908 PCA points, got {pca_points_count}"

        canvas_drawn = client.evaluate("""(() => {
            const canvas = document.getElementById('plot');
            return canvas && canvas.width > 0 && canvas.height > 0;
        })()""")
        print(f"    PCA canvas initialized: {canvas_drawn}")
        assert canvas_drawn, "PCA canvas failed to initialize!"

        # 8c. Selected Tile Inspector
        inspector_has_content = client.evaluate("""(() => {
            const el = document.getElementById('plotInspector');
            return el && el.innerHTML.includes('Sentinel-2');
        })()""")
        print(f"    Tile inspector populated: {inspector_has_content}")
        assert inspector_has_content, "Tile inspector empty!"

        # 8d. Execute Similar-Site Discovery Pass
        print("[9] Executing Similar-Site Discovery pass via POST /api/similar_sites...")
        client.evaluate("executeSimilarSitesDiscovery('e87b4d6c-9cdb-4293-8a8b-7ad7a5af6e43', 12)")
        time.sleep(3.5)

        cand_count = client.evaluate("APP.clusters.candidates.length")
        print(f"    Discovery candidates returned: {cand_count}")
        assert cand_count == 12, f"Expected 12 candidates, got {cand_count}"

        first_cand = client.evaluate("APP.clusters.candidates[0]")
        print(f"    Candidate #1 Tile ID: {first_cand['tile_id']}, Similarity: {first_cand['similarity_score']}, Cluster: {first_cand.get('cluster_info', {}).get('cluster_label')}")
        assert first_cand['similarity_score'] >= 0.70, f"Unreasonable similarity score: {first_cand['similarity_score']}"
        assert first_cand.get('cluster_info', {}).get('cluster_label') is not None, "Missing cluster info!"

        cand_cards_count = client.evaluate("document.querySelectorAll('#candGrid .cand').length")
        print(f"    Rendered candidate cards: {cand_cards_count}")
        assert cand_cards_count == 12, f"Expected 12 cards, got {cand_cards_count}"

        # 8e. Analyst Review Action: Confirm Candidate #1
        print("[10] Submitting Analyst Review 'CONFIRM' via POST /api/reviews...")
        client.evaluate(f"handleAnalystDecision('{first_cand['tile_id']}', 'CONFIRM')")
        time.sleep(2.5)

        decision_state = client.evaluate(f"APP.clusters.decisions.get('{first_cand['tile_id']}').decision")
        case_id = client.evaluate(f"APP.clusters.decisions.get('{first_cand['tile_id']}').case_id")
        print(f"    Decision recorded: {decision_state}, Case ID: {case_id}")
        assert decision_state == "CONFIRM", f"Expected CONFIRM, got {decision_state}"
        assert "CASE-" in case_id, f"Invalid case_id: {case_id}"

        # 8f. Analyst Review Action: Reject Candidate #2
        second_cand = client.evaluate("APP.clusters.candidates[1]")
        print("[11] Submitting Analyst Review 'REJECT' via POST /api/reviews...")
        client.evaluate(f"handleAnalystDecision('{second_cand['tile_id']}', 'REJECT')")
        time.sleep(2.5)

        decision_state_2 = client.evaluate(f"APP.clusters.decisions.get('{second_cand['tile_id']}').decision")
        print(f"    Decision recorded for candidate #2: {decision_state_2}")
        assert decision_state_2 == "REJECT", f"Expected REJECT, got {decision_state_2}"

        # 8g. Verify Audit Trail Log
        audit_rows_count = client.evaluate("document.querySelectorAll('#auditLog .log-row').length")
        print(f"    Audit trail rows: {audit_rows_count}")
        assert audit_rows_count >= 2, f"Expected at least 2 audit rows, got {audit_rows_count}"

        # 8h. Reranking from decisions
        print("[12] Testing Reranking from decisions...")
        client.evaluate("rerankClustersFromDecisions()")
        time.sleep(0.5)
        top_cand_after_rerank = client.evaluate("APP.clusters.candidates[0]['tile_id']")
        assert top_cand_after_rerank == first_cand['tile_id'], "Confirmed candidate should be at rank #1 after reranking!"
        print("    [PASS] Candidate reranking prioritizes confirmed sites.")

        print("\n========================================================")
        print("ALL 12 PHASE 4 VALIDATION TESTS PASSED PERFECTLY!")
        print("========================================================")
        return True

    finally:
        client.close()
        proc.terminate()
        proc.wait()
        # Clean up temp profile
        try:
            import shutil
            shutil.rmtree(user_data_dir, ignore_errors=True)
        except Exception:
            pass

if __name__ == "__main__":
    success = run_headless_validation()
    sys.exit(0 if success else 1)
