from __future__ import annotations

import base64
import binascii
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import app
import metrics

ROOT = app.ROOT
MAX_BODY = 14 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    def send_json(self, value, code=200):
        data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > MAX_BODY:
            raise ValueError("请求正文超过 11 MB")
        if "application/json" not in self.headers.get("Content-Type", ""):
            raise ValueError("请求须使用 application/json")
        data = json.loads(self.rfile.read(length))
        if not isinstance(data, dict):
            raise ValueError("请求正文应为 JSON 对象")
        return data

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/api/health":
            self.send_json({"ok": True, "service": "kbqa", "model": app.model_status(), "retrieval": "BM25 + cosine / RRF", "embedding_mode": app.embedding_status()}); return
        if parsed.path == "/api/stats":
            self.send_json(app.stats()); return
        if parsed.path == "/api/metrics":
            self.send_json(metrics.summary()); return
        if parsed.path == "/api/history":
            self.send_json({"history": metrics.history()}); return
        if parsed.path == "/api/documents":
            self.send_json({"documents": app.list_documents()}); return
        match = re.fullmatch(r"/api/documents/(\d+)", parsed.path)
        if match:
            data = app.get_document(int(match.group(1)))
            self.send_json(data or {"error": "文档不存在"}, 200 if data else 404); return
        if parsed.path == "/api/search":
            params = parse_qs(parsed.query)
            try:
                results = app.query(params.get("q", [""])[0], int(params.get("limit", ["5"])[0]), params.get("retrieval_mode", params.get("mode", ["hybrid"]))[0])
                self.send_json({"results": results})
            except (ValueError, TypeError) as error:
                self.send_json({"error": str(error)}, 400)
            return
        if parsed.path in {"/", "/index.html"}:
            self.send_static("index.html"); return
        # Only the explicitly public frontend assets are served. Never map URL
        # paths to arbitrary workspace files (e.g. .env, databases, or source).
        if parsed.path in {"/static/app.js", "/static/metrics.js", "/static/style.css"}:
            self.send_static(parsed.path.rsplit("/", 1)[1]); return
        self.send_json({"error": "not found"}, 404)

    def send_static(self, name):
        path = ROOT / "static" / name
        if not path.is_file():
            self.send_json({"error": "not found"}, 404); return
        content_type = "text/html; charset=utf-8" if name.endswith(".html") else "text/javascript; charset=utf-8" if name.endswith(".js") else "text/css; charset=utf-8"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; script-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        path = urlsplit(self.path).path
        try:
            payload = self.read_json()
            if path == "/api/query":
                question = payload.get("question", "")
                if not isinstance(question, str) or not question.strip():
                    raise ValueError("问题不能为空")
                retrieval_mode = payload.get("retrieval_mode", payload.get("mode", "hybrid"))
                response = app.answer(question, int(payload.get("limit", 5)), retrieval_mode)
                response["query_id"] = metrics.record_query(question, response)
                response["metrics"] = metrics.summary()
                self.send_json(response); return
            match = re.fullmatch(r"/api/history/(\d+)/review", path)
            if match:
                review = metrics.save_review(int(match.group(1)), payload)
                if review is None:
                    self.send_json({"error": "问答记录不存在"}, 404); return
                self.send_json({"metrics": metrics.summary(), "review": review}); return
            if path == "/api/ingest":
                count = app.index_document(payload.get("title", ""), payload.get("source", ""), payload.get("content", ""))
                self.send_json({"ok": True, "chunks": count}); return
            if path == "/api/upload":
                filename = payload.get("filename", "")
                try:
                    raw = base64.b64decode(payload.get("content_base64", ""), validate=True)
                except (binascii.Error, ValueError) as error:
                    raise ValueError("content_base64 不是有效的 base64") from error
                self.send_json(app.import_file(filename, raw, payload.get("title")), 201); return
            if path == "/api/import-url":
                self.send_json(app.import_url(payload.get("url", ""), payload.get("title")), 201); return
            self.send_json({"error": "not found"}, 404)
        except (ValueError, TypeError, KeyError, binascii.Error) as error:
            self.send_json({"error": str(error)}, 400)
        except RuntimeError as error:
            self.send_json({"error": str(error)}, 501)
        except Exception:
            self.log_error("unhandled request failure")
            self.send_json({"error": "服务端处理请求失败"}, 500)

    def do_DELETE(self):
        match = re.fullmatch(r"/api/documents/(\d+)", urlsplit(self.path).path)
        if not match:
            self.send_json({"error": "not found"}, 404); return
        deleted = app.delete_document(int(match.group(1)))
        self.send_json({"ok": deleted}, 200 if deleted else 404)

    def log_message(self, format, *args):
        if os.getenv("KBQA_ACCESS_LOG", "0") == "1":
            super().log_message(format, *args)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    app.seed()
    port = int(os.getenv("KBQA_PORT", "8765"))
    server = Server(("127.0.0.1", port), Handler)
    print(f"KBQA running at http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
