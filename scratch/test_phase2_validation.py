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

    port = 9223
    user_data_dir = r"c:\Users\Hiya\OneDrive\Desktop\BIRDSEYE\scratch\edge_temp_profile_phase2"
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

    print("[1] Spawning headless Edge browser on debug port 9223...")
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

        # Check console errors
        print("[3] Checking JavaScript evaluation & baseline...")
        doc_title = client.evaluate("document.title")
        print(f"    Page Title: {doc_title}")
        assert "BIRDSΣY3" in doc_title

        # Step A: Check 11 tabs order
        tab_names = client.evaluate("Array.from(document.querySelectorAll('nav.tabs button')).map(b => b.dataset.tab)")
        expected_tabs = [
            "overview", "retrieval", "temporal", "preprocessing",
            "suppression", "clusters", "evaluation", "ingest",
            "brief", "mission", "spec"
        ]
        print(f"    Tabs order: {tab_names}")
        assert tab_names == expected_tabs, f"Expected {expected_tabs} but got {tab_names}"
        print("    [PASS] Tab order strictly preserved across all 11 tabs.")

        # Step B: Semantic search returns a real tile
        print("[4] Executing real semantic retrieval...")
        client.evaluate("showTab('retrieval')")
        time.sleep(0.5)
        client.evaluate("document.getElementById('q').value = 'Dense forest canopy with high chlorophyll'")
        client.evaluate("executeSemanticSearch()")
        time.sleep(3.5)

        results_count = client.evaluate("APP.searchResults.length")
        first_tile_id = client.evaluate("APP.searchResults[0]?.tile_id")
        first_score = client.evaluate("APP.searchResults[0]?.match_percentage || Math.round((APP.searchResults[0]?.final_score || 0)*100)")
        print(f"    Retrieved {results_count} tiles. First tile: {first_tile_id} ({first_score}% match)")
        assert results_count > 0, "No tiles returned from search!"
        assert first_tile_id, "Missing tile ID!"

        # Step C: Select tile and click 'Analyse Changes'
        print(f"[5] Clicking 'Analyse Changes' on real tile {first_tile_id}...")
        analyse_clicked = client.evaluate(f"""
            (() => {{
                const btn = document.querySelector('.tile[data-id="{first_tile_id}"] [data-act="analyse"]');
                if (btn) {{
                    btn.click();
                    return true;
                }}
                return false;
            }})()
        """)
        assert analyse_clicked, "Could not find 'Analyse Changes' button!"
        time.sleep(3.5)

        # Step D: Verify Change Analysis tab is active and tile ID is populated
        print("[6] Verifying Change Analysis tab state...")
        active_tab = client.evaluate("Array.from(document.querySelectorAll('nav.tabs button')).find(b => b.getAttribute('aria-selected') === 'true')?.dataset.tab")
        print(f"    Active Tab: {active_tab}")
        assert active_tab == "temporal", f"Expected tab 'temporal', got {active_tab}"

        input_tile_id = client.evaluate("document.getElementById('temporalTileInput').value")
        print(f"    Target Tile Input: {input_tile_id}")
        assert input_tile_id == first_tile_id, f"Expected {first_tile_id}, got {input_tile_id}"

        # Step E: Verify real Change Analysis backend response
        print("[7] Verifying real Change Analysis results...")
        container_hidden = client.evaluate("document.getElementById('temporalResultsContainer').hidden")
        assert not container_hidden, "Results container should be visible!"

        total_change_badge = client.evaluate("document.getElementById('temporalTotalChangeBadge').textContent")
        print(f"    Total Change Badge: {total_change_badge}")
        assert "Total Change:" in total_change_badge and "%" in total_change_badge

        # Step F: Verify Before/After slider imagery (Real Base64 JPEG data URIs)
        print("[8] Verifying real Before / After observation layers...")
        bg_before = client.evaluate("document.getElementById('cmpBefore').style.backgroundImage")
        bg_after = client.evaluate("document.getElementById('cmpAfter').style.backgroundImage")
        tag_l = client.evaluate("document.getElementById('cmpTagL').textContent")
        tag_r = client.evaluate("document.getElementById('cmpTagR').textContent")
        print(f"    Tag Left:  {tag_l}")
        print(f"    Tag Right: {tag_r}")
        print(f"    Layer Before data URI: {bg_before[:45]}... (len {len(bg_before)})")
        print(f"    Layer After data URI:  {bg_after[:45]}... (len {len(bg_after)})")
        assert "data:image/jpeg;base64," in bg_before, "Before layer missing real Base64 image!"
        assert "data:image/jpeg;base64," in bg_after, "After layer missing real Base64 image!"

        # Step G: Verify Multi-Epoch Observation Ribbon
        print("[9] Verifying Multi-Epoch Observation Ribbon (2024 -> 2025 -> 2026)...")
        ribbon_dots = client.evaluate("Array.from(document.querySelectorAll('#observationRibbon .rp b')).map(el => el.textContent)")
        print(f"    Ribbon Observation Dates: {ribbon_dots}")
        assert "2024-02-23" in ribbon_dots and "2025-02-27" in ribbon_dots and "2026-02-27" in ribbon_dots

        # Step H: Verify Change Categories
        print("[10] Verifying detected change categories...")
        categories = client.evaluate("Array.from(document.querySelectorAll('#changeCategoriesList strong')).map(el => el.textContent)")
        print(f"    Categories displayed: {categories}")
        assert "Built-up Expansion" in categories or "Vegetation Gain" in categories or "Unchanged Baseline Matrix" in categories

        # Step I: Verify Earliest Supported Observation card
        print("[11] Verifying Earliest Supported Observation...")
        earliest_date = client.evaluate("document.getElementById('earliestObsDate').textContent")
        earliest_interval = client.evaluate("document.getElementById('earliestObsInterval').textContent")
        print(f"    Earliest Date: {earliest_date}")
        print(f"    Interval:      {earliest_interval}")
        assert "2025-02-27" in earliest_date or "Not established" in earliest_date

        # Step J: Verify Confidence / Evidence terminology
        print("[12] Verifying scientifically honest evidence terminology...")
        conf_num = client.evaluate("document.getElementById('confScoreNum').textContent")
        conf_label = client.evaluate("document.getElementById('confScoreLabel').textContent")
        print(f"    Evidence score: {conf_num} · Label: '{conf_label}'")
        assert conf_label == "Rule-based evidence score" or "evidence" in conf_label.lower()
        assert "accuracy" not in conf_label.lower(), "Terminology violation: 'accuracy' found!"

        # Step K: Verify Quality Checks section
        print("[13] Verifying Quality Checks section...")
        qc_items = client.evaluate("Array.from(document.querySelectorAll('#qualityChecksGrid strong')).map(el => el.textContent)")
        print(f"    Quality checks telemetry: {qc_items[:4]}")
        assert len(qc_items) >= 4, "Quality checks grid missing items!"

        # Step L: Verify 'Why this location?' explanation drawer
        print("[14] Testing 'Why this location?' drawer...")
        client.evaluate("document.getElementById('whyLocationBtn').click()")
        time.sleep(0.5)
        drawer_open = client.evaluate("document.getElementById('drawer').classList.contains('open')")
        drawer_title = client.evaluate("document.getElementById('drawerTitle').textContent")
        drawer_body_text = client.evaluate("document.getElementById('drawerBody').innerText")
        print(f"    Drawer Open: {drawer_open} · Title: '{drawer_title}'")
        assert drawer_open, "Drawer did not open!"
        assert "PHYSICAL SPECTRAL TRIGGERS" in drawer_body_text
        assert "SUB-PIXEL CO-REGISTRATION" in drawer_body_text

        # Close drawer
        client.evaluate("closeDrawer()")
        time.sleep(0.3)

        # Step M: Test Change Mask Mode
        print("[15] Testing Change Mask layer comparison...")
        client.evaluate("document.getElementById('modeChangeMask').click()")
        time.sleep(0.5)
        tag_r_mask = client.evaluate("document.getElementById('cmpTagR').textContent")
        bg_after_mask = client.evaluate("document.getElementById('cmpAfter').style.backgroundImage")
        print(f"    Tag Right in mask mode: {tag_r_mask}")
        assert "change evidence mask" in tag_r_mask or "spectral change mask" in tag_r_mask
        assert "data:image/jpeg;base64," in bg_after_mask

        # Step N: Test Slider Position Drag / Change
        print("[16] Testing Before/After comparison slider adjustment...")
        client.evaluate("applySliderPos(75)")
        clip_path = client.evaluate("document.getElementById('cmpAfter').style.clipPath")
        div_left = client.evaluate("document.getElementById('cmpDiv').style.left")
        print(f"    Clip Path: {clip_path} · Divider Left: {div_left}")
        assert "75%" in clip_path and "75%" in div_left

        # Step O: Re-verify Semantic Retrieval still works
        print("[17] Verifying Phase 1 Semantic Retrieval remains operational...")
        client.evaluate("showTab('retrieval')")
        time.sleep(0.5)
        active_tab_retrieval = client.evaluate("Array.from(document.querySelectorAll('nav.tabs button')).find(b => b.getAttribute('aria-selected') === 'true')?.dataset.tab")
        assert active_tab_retrieval == "retrieval"
        print("    [PASS] Semantic Retrieval tab accessible and operational.")

        print("\n========================================================")
        print(">>> ALL PHASE 2 VALIDATION CHECKS PASSED PERFECTLY! <<<")
        print("========================================================")
        client.close()
        return True

    finally:
        proc.kill()


if __name__ == "__main__":
    success = run_headless_validation()
    sys.exit(0 if success else 1)
