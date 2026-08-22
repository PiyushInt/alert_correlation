import datetime
import http.server
import json
import os
import signal
import sys
from urllib.parse import urlparse

PORT = 8000

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PAYLOADS_DIR = os.path.join(REPO_ROOT, "estate", "captures", "payloads")
TRACES_DIR = os.path.join(REPO_ROOT, "estate", "captures", "traces")

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
        body = b""
        try:
            path = urlparse(self.path).path
            stats[path] = stats.get(path, 0) + 1

            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b""

            now = datetime.datetime.now(datetime.UTC)
            epoch_ms = int(now.timestamp() * 1000)
            path_slug = path.strip("/").replace("/", "-")
            if not path_slug:
                path_slug = "root"

            headers_dict = dict(self.headers)
            alert_names = []

            if path == "/v1/traces":
                target_dir = TRACES_DIR
                filename = f"{epoch_ms}-{path_slug}.bin"
                with open(os.path.join(target_dir, filename), "wb") as f:
                    f.write(body)
                with open(
                    os.path.join(target_dir, f"{epoch_ms}-{path_slug}.headers.json"), "w"
                ) as f:
                    json.dump(headers_dict, f)
            else:
                target_dir = PAYLOADS_DIR
                filename = f"{epoch_ms}-{path_slug}.json"

                if "application/json" in headers_dict.get("Content-Type", ""):
                    try:
                        parsed_body = json.loads(body)
                        if isinstance(parsed_body, dict) and "alerts" in parsed_body:
                            for alert in parsed_body["alerts"]:
                                name = alert.get("labels", {}).get("alertname")
                                if name:
                                    alert_names.append(name)
                    except:
                        pass

                try:
                    raw_body_str = body.decode("utf-8", errors="strict")
                    record = {
                        "received_at": now.isoformat(),
                        "path": path,
                        "headers": headers_dict,
                        "raw_body": raw_body_str,
                    }
                    with open(os.path.join(target_dir, filename), "w") as f:
                        json.dump(record, f)
                except UnicodeDecodeError:
                    # Fallback to binary
                    bin_filename = f"{epoch_ms}-{path_slug}.bin"
                    with open(os.path.join(target_dir, bin_filename), "wb") as f:
                        f.write(body)
                    print(
                        f"ERROR: UnicodeDecodeError for {path}. Raw bytes written to {bin_filename}"
                    )

            log_names = f" alerts:[{','.join(alert_names)}]" if alert_names else ""
            print(f"[{now.isoformat()}] POST {path} {len(body)} bytes{log_names}")
            sys.stdout.flush()

        except Exception as e:
            print(f"ERROR in sink handler: {e}")
            import traceback

            traceback.print_exc()
            try:
                now = datetime.datetime.now(datetime.UTC)
                epoch_ms = int(now.timestamp() * 1000)
                with open(os.path.join(PAYLOADS_DIR, f"{epoch_ms}-fallback.bin"), "wb") as f:
                    f.write(body)
            except Exception as write_err:
                print(f"ERROR writing fallback payload: {write_err}")

        finally:
            try:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")
            except:
                pass

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
