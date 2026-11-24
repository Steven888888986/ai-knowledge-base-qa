from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app import answer, db, index_document, read_file, seed

ROOT = Path(__file__).parent


class Handler(BaseHTTPRequestHandler):
    def send_json(self, value, code=200):
        data = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self.send_json({"ok": True, "service": "kbqa"}); return
        if parsed.path == "/api/stats":
            c = db(); self.send_json({"documents": c.execute("SELECT COUNT(*) FROM documents").fetchone()[0], "chunks": c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]}); c.close(); return
        if parsed.path == "/api/search":
            q = parse_qs(parsed.query).get("q", [""])[0]; self.send_json({"results": answer(q)["citations"]}); return
        if parsed.path in {"/", "/index.html"}:
            data = (ROOT / "static" / "index.html").read_bytes(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
        path = ROOT / parsed.path.lstrip("/")
        if path.is_file() and str(path.resolve()).startswith(str(ROOT.resolve())):
            data = path.read_bytes(); self.send_response(200); self.send_header("Content-Type", mimetypes.guess_type(str(path))[0] or "application/octet-stream"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
        self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path); length = int(self.headers.get("Content-Length", "0")); body = self.rfile.read(length)
        if parsed.path == "/api/query":
            try: payload = json.loads(body); self.send_json(answer(payload.get("question", ""), int(payload.get("limit", 5))))
            except Exception as e: self.send_json({"error": str(e)}, 400)
            return
        if parsed.path == "/api/ingest":
            try:
                payload = json.loads(body); title = payload.get("title") or payload.get("source", "untitled"); count = index_document(title, payload["source"], payload["content"]); self.send_json({"ok": True, "chunks": count})
            except Exception as e: self.send_json({"error": str(e)}, 400)
            return
        self.send_json({"error": "not found"}, 404)


if __name__ == "__main__":
    seed(); port = 8000; print(f"KBQA running at http://127.0.0.1:{port}"); ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
