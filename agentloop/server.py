"""Loopback-only development server; standard library, no build step."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .runtime import Runtime
from .store import Store
from .tools import SCENARIOS

WEB = Path(__file__).resolve().parent.parent / "web"


def handler_for(runtime):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, body, content_type="application/json"):
            data = json.dumps(body).encode() if content_type == "application/json" else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {"error": "Use a loopback host"})
            path = urlsplit(self.path).path
            if path == "/api/config":
                return self.send(200, {"scenarios": SCENARIOS, "mode": "synthetic local demo"})
            if path == "/api/runs":
                return self.send(200, runtime.store.list_runs())
            if path.startswith("/api/runs/"):
                try:
                    return self.send(200, runtime.snapshot(path.split("/")[3]))
                except KeyError:
                    return self.send(404, {"error": "Run not found"})
            assets = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/style.css": ("style.css", "text/css; charset=utf-8")}
            if path not in assets:
                return self.send(404, {"error": "Not found"})
            filename, mime = assets[path]
            return self.send(200, (WEB / filename).read_bytes(), mime)

        def do_POST(self):
            if not self.valid_host():
                return self.send(403, {"error": "Use a loopback host"})
            # Block browser cross-origin writes to the local control surface.
            origin = self.headers.get("Origin")
            expected = f"http://{self.headers.get('Host')}"
            if origin and origin != expected:
                return self.send(403, {"error": "Cross-origin requests are disabled"})
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                return self.send(403, {"error": "Cross-site requests are disabled"})
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.send(415, {"error": "Use application/json"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 16_384:
                    return self.send(413, {"error": "Body must contain 1–16384 bytes"})
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("JSON body must be an object")
                path = urlsplit(self.path).path
                if path == "/api/runs":
                    allowed = {"goal", "scenario", "planner", "max_steps"}
                    if set(body) - allowed:
                        raise ValueError("Unknown request fields")
                    run = runtime.start(**body)
                    return self.send(201, runtime.snapshot(run.id))
                parts = path.strip("/").split("/")
                if len(parts) == 4 and parts[:2] == ["api", "runs"]:
                    run_id, action = parts[2:]
                    if action == "step" and body == {}:
                        runtime.step(run_id)
                    elif action == "advance" and body == {}:
                        runtime.run_until_pause(run_id)
                    elif action == "approval" and set(body) == {"approved"}:
                        runtime.approve(run_id, body["approved"])
                    else:
                        raise ValueError("Unknown action or invalid fields")
                    return self.send(200, runtime.snapshot(run_id))
                return self.send(404, {"error": "Not found"})
            except KeyError:
                self.send(404, {"error": "Run not found"})
            except (TypeError, ValueError, UnicodeDecodeError) as exc:
                self.send(400, {"error": str(exc)})

        def valid_host(self):
            port = self.server.server_port
            return self.headers.get("Host") in {f"127.0.0.1:{port}", f"localhost:{port}"}
    return Handler


def main():
    parser = argparse.ArgumentParser(description="Start AgentLoop Studio locally")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--db", default="data/agentloop.db")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(Runtime(Store(args.db))))
    print(f"AgentLoop Studio → http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
