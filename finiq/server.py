"""Loopback-only Fin-IQ web UI and guarded update controller."""
import argparse
import json
import os
import secrets
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .core import connect, import_csv, add_rule, report

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE = Path(os.environ.get("FINIQ_STATE_DIR", "~/.local/state/finiq")).expanduser()
WEB = ROOT / "web" / "index.html"

def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True,
                          text=True, timeout=30, check=False)

def version_status(fetch=False):
    current = git("branch", "--show-current")
    branch = current.stdout.strip() if current.returncode == 0 else ""
    if fetch:
        if not branch:
            raise ValueError("not a checked-out Git branch")
        fetched = git("fetch", "--quiet", "origin", branch)
        if fetched.returncode:
            raise ValueError("remote check failed; verify network and Git access")
    dirty = git("status", "--porcelain")
    head = git("rev-parse", "HEAD")
    upstream = git("rev-parse", f"origin/{branch}") if branch else None
    behind = git("rev-list", "--count", f"HEAD..origin/{branch}") if branch else None
    return {
        "branch":branch,
        "clean":dirty.returncode == 0 and dirty.stdout.strip() == "",
        "head":head.stdout.strip() if head.returncode == 0 else None,
        "remote":upstream.stdout.strip() if upstream and upstream.returncode == 0 else None,
        "behind":int(behind.stdout.strip()) if behind and behind.returncode == 0 else None,
    }

def handler_factory(db_path):
    token = secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def send_blob(self, content, mime="application/json", code=200):
            payload = content.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def send_json(self, value, code=200):
            self.send_blob(json.dumps(value), code=code)

        def allowed(self, mutate=False):
            authority = self.headers.get("Host", "")
            host = authority.split(":")[0].lower()
            if host not in ("127.0.0.1", "localhost"):
                self.send_json({"error":"loopback host required"}, 403)
                return False
            origin = self.headers.get("Origin")
            if origin:
                parsed = urlsplit(origin)
                if parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1") or parsed.port != self.server.server_port:
                    self.send_json({"error":"invalid origin"}, 403)
                    return False
            if mutate and self.headers.get("X-FinIQ-Token") != token:
                self.send_json({"error":"invalid local session"}, 403)
                return False
            return True

        def do_GET(self):
            if not self.allowed():
                return
            path = urlsplit(self.path).path
            if path == "/":
                self.send_blob(WEB.read_text(encoding="utf-8").replace("__FINIQ_TOKEN__", token), "text/html")
            elif path == "/api/report":
                with connect(db_path) as db:
                    self.send_json(report(db))
            elif path == "/api/version":
                self.send_json(version_status())
            elif path == "/health":
                self.send_json({"ok":True})
            else:
                self.send_json({"error":"not found"},404)

        def do_POST(self):
            if not self.allowed(True):
                return
            path = urlsplit(self.path).path
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size <= 0 or size > 5_500_000:
                    self.send_json({"error":"invalid request size"},413)
                    return
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("expected an object")
                if path == "/api/import":
                    content = body.get("csv")
                    account = body.get("account", "Default")
                    if not isinstance(content, str) or not isinstance(account, str):
                        raise ValueError("csv and account must be strings")
                    with connect(db_path) as db:
                        result = import_csv(db, content, account[:120])
                elif path == "/api/rule":
                    with connect(db_path) as db:
                        add_rule(db, body.get("pattern"), body.get("category"))
                    result = {"ok":True}
                elif path == "/api/check-updates":
                    result = version_status(fetch=True)
                elif path == "/api/upgrade":
                    if body.get("confirm") != "UPGRADE":
                        raise ValueError("confirmation required")
                    status = version_status(fetch=True)
                    if status["branch"] != "main" or not status["clean"] or status["behind"] is None:
                        raise ValueError("upgrade requires a clean main checkout with a reachable remote")
                    if status["behind"] == 0:
                        result = {"ok":True,"message":"Already up to date"}
                    else:
                        pulled = git("pull", "--ff-only", "origin", "main")
                        if pulled.returncode:
                            raise ValueError("fast-forward failed; review the Git checkout manually")
                        result = {"ok":True,"message":"Files updated; restart Fin-IQ to load new Python code"}
                else:
                    self.send_json({"error":"not found"},404)
                    return
                self.send_json(result)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self.send_json({"error":str(exc)},400)
            except Exception:
                self.send_json({"error":"operation failed; check local logs"},500)

    return Handler

def main():
    parser = argparse.ArgumentParser(description="Fin-IQ local-only dashboard")
    parser.add_argument("--port", type=int, default=18781)
    parser.add_argument("--database", default=str(DEFAULT_STATE / "finiq.sqlite3"))
    args = parser.parse_args()
    db_path = Path(args.database).expanduser()
    with connect(db_path):
        pass
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), handler_factory(db_path))
    print(f"Fin-IQ serving http://127.0.0.1:{args.port}/", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__ == "__main__":
    main()
