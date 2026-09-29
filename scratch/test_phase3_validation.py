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

    port = 9224
    user_data_dir = r"c:\Users\Hiya\OneDrive\Desktop\BIRDSEYE\scratch\edge_temp_profile_phase3"
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

    print("[1] Spawning headless Edge browser on debug port 9224...")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(2)

    try:
        # Discover targets
        req = urllib.request.urlopen(f"http://127.0.0.1:{port}/json")
        targets = json.loads(req.read().decode('utf-8'))
        page_target = next((t for t in targets if t.get("type") == "page"), None)
        if not page_target:
            print("ERROR: No page target found.")
            return False

        ws_url = page_target["webSocketDebuggerUrl"]
        client = SimpleCDPClient(ws_url)

        # Track console errors
        client.send_cmd("Console.enable")
        client.send_cmd("Runtime.enable")

        html_path = os.path.abspath("frontend/index.html").replace("\\", "/")
        file_url = f"file:///{html_path}"
        print(f"[2] Navigating to {file_url}...")
        client.send_cmd("Page.navigate", {"url": file_url})
        time.sleep(3)

        print("[3] Checking JavaScript evaluation & baseline...")
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
        time.sleep(0.5)
        client.evaluate("document.getElementById('q').value = 'Dense forest canopy with high chlorophyll'")
        client.evaluate("executeSemanticSearch()")
        time.sleep(3.5)

        results_count = client.evaluate("APP.searchResults.length")
        first_tile_id = client.evaluate("APP.searchResults[0]?.tile_id")
        first_score = client.evaluate("APP.searchResults[0]?.match_percentage || Math.round((APP.searchResults[0]?.final_score || 0)*100)")
        print(f"    Retrieved {results_count} tiles. Test anchor: {first_tile_id} ({first_score}%)")
        assert results_count > 0, "No tiles returned from search!"

        # Step 5: Validate Phase 2 Change Analysis
        print("[5] Validating Phase 2 Change Analysis...")
        client.evaluate(f"""
            (() => {{
                const btn = document.querySelector('.tile[data-id="{first_tile_id}"] [data-act="analyse"]');
                if (btn) btn.click();
            }})()
        """)
        time.sleep(3.5)
        bg_before = client.evaluate("document.getElementById('cmpBefore').style.backgroundImage")
        bg_after = client.evaluate("document.getElementById('cmpAfter').style.backgroundImage")
        total_change_badge = client.evaluate("document.getElementById('temporalTotalChangeBadge').textContent")
        print(f"    Change badge: {total_change_badge}")
        assert "data:image/jpeg;base64," in bg_before
        assert "data:image/jpeg;base64," in bg_after
        print("    [PASS] Phase 2 Change Analysis operational.")

        # Step 6: Validate Preprocessing Lab (Tab 4)
        print("[6] Validating Preprocessing Lab (Tab 4)...")
        client.evaluate("showTab('preprocessing')")
        time.sleep(1.0)
        active_tab = client.evaluate("Array.from(document.querySelectorAll('nav.tabs button')).find(b => b.getAttribute('aria-selected') === 'true')?.dataset.tab")
        assert active_tab == "preprocessing", f"Expected tab 'preprocessing', got {active_tab}"

        # Verify scenes loaded into select
        scenes_count = client.evaluate("document.querySelectorAll('#prepSceneSel option').length")
        print(f"    Available observation scenes in selector: {scenes_count}")
        assert scenes_count >= 3, "Expected at least 3 Sentinel-2 SAFE product options"

        # Check target tile input populated
        prep_tile = client.evaluate("document.getElementById('prepTileInput').value")
        print(f"    Target Tile in Preprocessing: {prep_tile}")
        assert prep_tile == first_tile_id, f"Expected {first_tile_id}, got {prep_tile}"

        # Trigger pipeline execution
        print("    Executing 8-stage ARD pipeline on backend...")
        client.evaluate("document.getElementById('runPipelineBtn').click()")
        time.sleep(4.0)

        # Verify 8 stages rendered
        stages_count = client.evaluate("document.querySelectorAll('#prepStagesList .prep-stage-card').length")
        print(f"    Verified stages rendered: {stages_count}")
        assert stages_count == 8, f"Expected 8 stages, got {stages_count}"

        # Verify Stage 1 and Stage 6 telemetry details
        stage1_name = client.evaluate("document.querySelector('#prepStagesList .prep-stage-card:nth-child(1) strong').textContent")
        stage6_name = client.evaluate("document.querySelector('#prepStagesList .prep-stage-card:nth-child(6) strong').textContent")
        print(f"    Stage 1: {stage1_name}")
        print(f"    Stage 6: {stage6_name}")
        assert "Metadata Validation" in stage1_name
        assert "Co-Registration" in stage6_name

        # Verify 3 visual previews (Raw RGB, SCL Mask, ARD BOA)
        raw_src = client.evaluate("document.getElementById('prevRawRgb').src")
        scl_src = client.evaluate("document.getElementById('prevSclMask').src")
        ard_src = client.evaluate("document.getElementById('prevArdRgb').src")
        print(f"    Raw RGB preview length: {len(raw_src)} (data URI: {'data:image/jpeg;base64,' in raw_src})")
        print(f"    SCL Mask preview length: {len(scl_src)} (data URI: {'data:image/jpeg;base64,' in scl_src})")
        print(f"    ARD BOA preview length:  {len(ard_src)} (data URI: {'data:image/jpeg;base64,' in ard_src})")
        assert "data:image/jpeg;base64," in raw_src, "Raw preview missing!"
        assert "data:image/jpeg;base64," in scl_src, "SCL mask preview missing!"
        assert "data:image/jpeg;base64," in ard_src, "ARD BOA preview missing!"

        # Verify summary stats
        stat_valid = client.evaluate("document.querySelector('#prepSummaryStats .stat:nth-child(2) b').textContent")
        stat_snr = client.evaluate("document.querySelector('#prepSummaryStats .stat:nth-child(4) b').textContent")
        stat_rmse = client.evaluate("document.querySelector('#prepSummaryStats .stat:nth-child(5) b').textContent")
        print(f"    Valid pixel ratio: {stat_valid} · SNR proxy: {stat_snr} · Sub-pixel RMSE: {stat_rmse}")
        assert "%" in stat_valid and "dB" in stat_snr and "px" in stat_rmse
        print("    [PASS] Preprocessing Lab 8-stage pipeline fully operational with real ARD previews.")

        # Step 7: Validate False Alarm Suppression (Tab 5)
        print("[7] Validating False Alarm Suppression (Tab 5)...")
        client.evaluate("showTab('suppression')")
        time.sleep(1.0)
        active_tab_sup = client.evaluate("Array.from(document.querySelectorAll('nav.tabs button')).find(b => b.getAttribute('aria-selected') === 'true')?.dataset.tab")
        assert active_tab_sup == "suppression", f"Expected tab 'suppression', got {active_tab_sup}"

        # Trigger analysis
        client.evaluate("document.getElementById('supAnalyzeBtn').click()")
        time.sleep(3.5)

        # Check candidate funnel stages
        funnel_stages = client.evaluate("Array.from(document.querySelectorAll('#funnel .fstage span')).map(el => el.textContent.split('(')[0].trim())")
        print(f"    Funnel stages: {funnel_stages}")
        assert len(funnel_stages) >= 8, f"Expected 8 funnel stages, got {len(funnel_stages)}"
        assert "Candidate Detections" in funnel_stages[0]
        assert "Verified Reported Change" in funnel_stages[-1]

        # Check False-Alarm checks (the 6 verified checks)
        checks_count = client.evaluate("document.querySelectorAll('#candStages .stage-row').length")
        print(f"    Verified False-Alarm Checks count: {checks_count}")
        assert checks_count == 6, f"Expected 6 false-alarm checks, got {checks_count}"

        # Check risk badge and diagnostic
        risk_badge = client.evaluate("document.getElementById('supRiskBadge').textContent")
        verdict_text = client.evaluate("document.getElementById('supVerdictText').textContent")
        print(f"    Risk Badge: {risk_badge}")
        print(f"    Screening Verdict: {verdict_text[:60]}...")
        assert "RISK" in risk_badge
        assert len(verdict_text) > 10

        # Check Before/After slider in False Alarm
        sup_before_bg = client.evaluate("document.getElementById('supBefore').style.backgroundImage")
        sup_after_bg = client.evaluate("document.getElementById('supAfter').style.backgroundImage")
        assert "data:image/jpeg;base64," in sup_before_bg, "False alarm before layer missing real image!"
        assert "data:image/jpeg;base64," in sup_after_bg, "False alarm after layer missing real image!"
        print(f"    False Alarm Before/After images verified.")

        # Check Removals Breakdown (#agg)
        agg_rows = client.evaluate("Array.from(document.querySelectorAll('#agg .agg-row .l')).map(el => el.textContent)")
        print(f"    Removals breakdown rows: {agg_rows}")
        assert len(agg_rows) == 4

        # Test clicking funnel stage opens drawer
        print("    Testing funnel stage detail drawer...")
        client.evaluate("document.querySelector('#funnel .fstage[data-fstage=\"pheno\"]').click()")
        time.sleep(0.5)
        drawer_open = client.evaluate("document.getElementById('drawer').classList.contains('open')")
        drawer_title = client.evaluate("document.getElementById('drawerTitle').textContent")
        print(f"    Drawer Open: {drawer_open} · Title: '{drawer_title}'")
        assert drawer_open
        assert "Phenological" in drawer_title
        client.evaluate("closeDrawer()")
        time.sleep(0.3)
        print("    [PASS] False Alarm Suppression fully operational with real confounder screening.")

        # Step 8: Verify honest terminology throughout
        print("[8] Auditing terminology for scientific honesty...")
        body_text = client.evaluate("document.body.innerText")
        forbidden = ["model accuracy", "prediction accuracy", "validated accuracy", "calibrated confidence", "95% accurate", "99% accurate"]
        for phrase in forbidden:
            assert phrase not in body_text.lower(), f"Forbidden phrase '{phrase}' found in UI!"
        print("    [PASS] Zero prohibited accuracy/confidence claims found.")

        print("\n========================================================")
        print(">>> ALL PHASE 3 VALIDATION CHECKS PASSED PERFECTLY! <<<")
        print("========================================================")
        client.close()
        return True

    finally:
        proc.kill()


if __name__ == "__main__":
    success = run_headless_validation()
    sys.exit(0 if success else 1)
