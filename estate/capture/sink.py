import http.server
import time
import datetime
import json
import os
import signal
import sys
from urllib.parse import urlparse

PORT = 8000
PAYLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "captures", "payloads")
TRACES_DIR = os.path.join(os.path.dirname(__file__), "..", "captures", "traces")

os.makedirs(PAYLOADS_DIR, exist_ok=True)
os.makedirs(TRACES_DIR, exist_ok=True)

stats = {}

def handle_sigint(sig, frame):
    print("\n--- Capture Summary ---")
    for path, count in stats.items():
        print(f"{path}: {count} requests")
    print("-----------------------")
    sys.exit(0)

signal.signal(signal.SIGINT, handle_sigint)

class CaptureHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        path = urlparse(self.path).path
        stats[path] = stats.get(path, 0) + 1
        
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""
        
        now = datetime.datetime.now(datetime.timezone.utc)
        epoch_ms = int(now.timestamp() * 1000)
        path_slug = path.strip("/").replace("/", "-")
        if not path_slug:
            path_slug = "root"

        if path == "/v1/traces":
            target_dir = TRACES_DIR
            filename = f"{epoch_ms}-{path_slug}.bin"
            with open(os.path.join(target_dir, filename), "wb") as f:
                f.write(body)
        else:
            target_dir = PAYLOADS_DIR
            filename = f"{epoch_ms}-{path_slug}.json"
            
            headers_dict = dict(self.headers)
            alert_names = []
            if "application/json" in headers_dict.get("Content-Type", ""):
                try:
                    parsed_body = json.loads(body)
                    if isinstance(parsed_body, dict) and "alerts" in parsed_body:
                        for alert in parsed_body["alerts"]:
                            name = alert.get("labels", {}).get("alertname")
                            if name: alert_names.append(name)
                except:
                    pass
            
            # The write path uses rfile.read() bytes with no json.loads/dumps round-trip 
            # for the payload body itself. It's stored as a raw string inside the wrapper JSON.
            record = {
                "received_at": now.isoformat(),
                "path": path,
                "headers": headers_dict,
                "raw_body": body.decode('utf-8', errors='replace')
            }
            
            with open(os.path.join(target_dir, filename), "w") as f:
                json.dump(record, f)

        log_names = f" alerts:[{','.join(alert_names)}]" if alert_names else ""
        print(f"[{now.isoformat()}] POST {path} {len(body)} bytes{log_names}")
        sys.stdout.flush()

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
        
    def log_message(self, format, *args):
        pass

class ThreadedHTTPServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = True

if __name__ == "__main__":
    with ThreadedHTTPServer(("", PORT), CaptureHandler) as httpd:
        print(f"Listening on port {PORT} for captures...")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
