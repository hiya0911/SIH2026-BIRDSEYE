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
        return

    port = 9222
    user_data_dir = r"c:\Users\Hiya\OneDrive\Desktop\BIRDSEYE\scratch\edge_temp_profile_phase1"
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

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(2)

    try:
        req = urllib.request.urlopen(f"http://127.0.0.1:{port}/json")
        pages = json.loads(req.read().decode('utf-8'))
        ws_url = pages[0]["webSocketDebuggerUrl"]
        print(f"[CDP Connected] WebSocket URL: {ws_url}")

        client = SimpleCDPClient(ws_url)

        # 1. Navigate to Console URL
        target_url = "http://localhost:8000/console/index.html"
        print(f"Navigating to {target_url}...")
        client.send_cmd("Page.enable")
        client.send_cmd("Page.navigate", {"url": target_url})
        for _ in range(20):
            time.sleep(0.5)
            ready = client.evaluate("document.readyState")
            if ready == "complete":
                break

        # 2. Check document title and all 11 tabs
        title = client.evaluate("document.title")
        print(f"Document Title: '{title}'")
        assert "BIRDSΣY3" in title, f"Title mismatch: {title}"

        tab_names = client.evaluate("Array.from(document.querySelectorAll('nav.tabs button')).map(b => b.textContent.trim())")
        print("\nAll 11 Navigation Tabs in Order:")
        for idx, tname in enumerate(tab_names, 1):
            print(f"  [{idx:02d}] {tname}")

        expected_tabs = [
            "1. Overview",
            "2. Semantic Retrieval",
            "3. Change Analysis",
            "4. Preprocessing Lab",
            "5. False Alarm",
            "6. Discovery & Cluster",
            "7. Evaluation Metrics",
            "8. Ingestion",
            "9. Analyst Brief & Provenance",
            "10. Mission Board",
            "11. Technical Specifications"
        ]
        assert tab_names == expected_tabs, f"Tabs order mismatch:\nGot: {tab_names}\nExpected: {expected_tabs}"

        # 3. Verify Overview Telemetry (Connected to Real Backend)
        tiles_text = client.evaluate("document.getElementById('statTilesCount')?.textContent")
        faiss_text = client.evaluate("document.getElementById('statVectorsCount')?.textContent")
        model_text = client.evaluate("document.getElementById('statModel')?.textContent")
        status_pill = client.evaluate("document.getElementById('statusText')?.textContent")

        print("\nOverview Real Telemetry:")
        print(f"  Tiles Catalog:  {tiles_text}")
        print(f"  FAISS Vectors:  {faiss_text}")
        print(f"  Model:          {model_text}")
        print(f"  Header Pill:    {status_pill}")

        assert "909" in tiles_text, f"Expected 909 tiles, got {tiles_text}"
        assert "908" in faiss_text, f"Expected 908 vectors, got {faiss_text}"

        # 4. Switch to Semantic Retrieval Tab
        client.evaluate("showTab('retrieval')")
        time.sleep(1)

        # 5. Check Search Input and Execute Search
        q_val = client.evaluate("document.getElementById('q')?.value")
        print(f"\nInitial Query in Search Bar: '{q_val}'")

        print("Executing Semantic Search via Backend...")
        client.evaluate("executeSemanticSearch()")
        time.sleep(4)

        # 6. Verify Results from Real Backend
        result_meta = client.evaluate("document.getElementById('resultMeta')?.textContent")
        result_count = client.evaluate("document.querySelectorAll('#resultsList .tile').length")
        first_tile_id = client.evaluate("document.querySelector('#resultsList .tile')?.dataset.id")
        first_tile_score = client.evaluate("document.querySelector('#resultsList .tile .meter span')?.textContent")
        first_img_src = client.evaluate("document.querySelector('#resultsList .tile img')?.src")

        print("\nSemantic Retrieval Results:")
        print(f"  Result Meta:       {result_meta}")
        print(f"  Tile Cards Count:  {result_count}")
        print(f"  Top Match Tile ID: {first_tile_id}")
        print(f"  Top Match Score:   {first_tile_score}")
        print(f"  First Image Src:   {first_img_src}")

        assert result_count > 0, "No result tiles rendered!"
        assert first_tile_id and len(first_tile_id) > 10, f"Invalid tile_id: {first_tile_id}"
        assert "image/" in first_img_src, f"Image src is not from backend: {first_img_src}"

        # 7. Check Tab 3 (Change Analysis Placeholder)
        client.evaluate("showTab('temporal')")
        time.sleep(1)
        tab3_badge = client.evaluate("document.querySelector('#panel-temporal .badge')?.textContent")
        tab3_pill = client.evaluate("document.querySelector('#panel-temporal .pill')?.textContent")
        print(f"\nTab 3 (Change Analysis) State:")
        print(f"  Badge: {tab3_badge}")
        print(f"  Pill:  {tab3_pill}")
        assert "Tab 3" in tab3_badge and "pending" in tab3_pill.lower()

        # 8. Check Command Palette (Ctrl+K)
        client.evaluate("openPalette()")
        time.sleep(1)
        palette_hidden = client.evaluate("document.getElementById('palette')?.hidden")
        cmd_count = client.evaluate("document.querySelectorAll('#paletteList button').length")
        print(f"\nCommand Palette:")
        print(f"  Modal Open (hidden=False): {not palette_hidden}")
        print(f"  Available Commands:        {cmd_count}")
        assert not palette_hidden, "Command palette did not open!"
        assert cmd_count >= 11, f"Expected at least 11 commands, got {cmd_count}"

        client.evaluate("closePalette()")
        time.sleep(1)

        print("\n[SUCCESS] Phase 1 Headless Browser Validation 100% PASSED!")

        client.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()

if __name__ == "__main__":
    run_headless_validation()
