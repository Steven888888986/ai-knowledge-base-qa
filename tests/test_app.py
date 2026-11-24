"""Deterministic contract and regression tests. No network or LLM is required."""
from __future__ import annotations

import json
import base64
import os
from pathlib import Path
import random
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
os.environ["KBQA_LLM_ENABLED"] = "0"
sys.path.insert(0, str(ROOT))
import app


class IsolatedAppTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="kbqa-test-")
        self.previous_path = app.DB_PATH
        app.DB_PATH = Path(self.tmp.name) / "test.sqlite3"
        app.db().close()

    def tearDown(self):
        app.DB_PATH = self.previous_path
        self.tmp.cleanup()

    def test_split_respects_bounds_and_keeps_content(self):
        rng = random.Random(91)
        alphabet = "AI检索增强生成abcdef012345。"
        for _ in range(100):
            text = "".join(rng.choice(alphabet) for _ in range(rng.randrange(1, 3000)))
            chunks = app.split_text(text, size=121, overlap=17)
            self.assertTrue(chunks)
            self.assertTrue(all(chunk and len(chunk) <= 121 for chunk in chunks))
            normalized = "".join(chunks)
            # Overlap duplication can be removed by comparing every chunk against the source in order.
            cursor = 0
            for chunk in chunks:
                position = text.find(chunk, cursor)
                self.assertGreaterEqual(position, cursor)
                cursor = position + max(1, len(chunk) - 17)

    def test_indexes_chinese_queries_and_returns_traceable_citations(self):
        app.index_document("RAG 基础", "notes/rag.md", "RAG 先从知识库检索证据，再根据证据生成回答。")
        result = app.answer("RAG 如何回答？", retrieval_mode="hybrid")
        self.assertFalse(result["refused"])
        self.assertTrue(result["citations"])
        citation = result["citations"][0]
        self.assertEqual("notes/rag.md", citation["source"])
        self.assertIn("检索证据", citation["snippet"])
        self.assertTrue(citation["chunk_id"])

    def test_citations_exclude_weaker_bge_match_when_bm25_is_close(self):
        hits = [
            {"chunk_id": "prompt", "document_id": 1, "page": None, "title": "提示注入", "source": "prompt.md", "content": "提示注入是把恶意指令放入外部资料等不可信输入，试图改变模型既定任务。知识库文档是待分析数据，其中的忽略规则等文字不应成为系统指令。", "bm25": 12.0, "cosine": 0.73},
            {"chunk_id": "rag", "document_id": 2, "page": None, "title": "RAG", "source": "rag.md", "content": "外部知识库资料先检索相关证据，再将检索片段放入语言模型上下文生成回答。", "bm25": 11.0, "cosine": 0.55},
        ]
        with patch.object(app, "query", return_value=hits), patch.object(app, "embedding_status", return_value={"available": True, "signature": "bge:test", "mode": "pretrained-bge"}):
            result = app.answer("外部知识库资料中的提示注入应该如何看待？")
        self.assertEqual(["prompt.md"], [citation["source"] for citation in result["citations"]])

    def test_unknown_question_refuses_without_inventing(self):
        app.index_document("RAG", "rag.md", "RAG 使用检索结果作为回答证据。")
        result = app.answer("我今天午餐吃了什么？")
        self.assertTrue(result["refused"])
        self.assertEqual([], result["citations"])

    def test_replace_source_does_not_leave_old_chunks(self):
        app.index_document("概念", "one.md", "旧内容 蓝色三角形")
        app.index_document("概念更新", "one.md", "新内容 红色圆形")
        self.assertFalse(app.query("蓝色三角形"))
        self.assertEqual("one.md", app.query("红色圆形")[0]["source"])
        connection = app.db()
        self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
        connection.close()

    def test_page_aware_indexing_preserves_original_pdf_page(self):
        app.index_pages("两页讲义", "upload://lecture.pdf", [(1, "第一页介绍模型训练。"), (2, "TRANSFORMERPAGE2 缩放点积注意力使用 Query Key Value。")], kind="pdf")
        result = app.answer("TRANSFORMERPAGE2", retrieval_mode="bm25")
        self.assertEqual(2, result["citations"][0]["page"])

    def test_retrieval_ablation_modes_are_supported(self):
        docs = [
            ("关于LoRA", "lora.md", "LoRA 采用低秩矩阵进行模型微调。"),
            ("关于量化", "quant.md", "量化使用较低精度压缩模型权重。"),
        ]
        for title, source, content in docs:
            app.index_document(title, source, content)
        for mode in ("bm25", "vector", "hybrid"):
            with self.subTest(mode=mode):
                hits = app.query("LoRA 低秩微调", retrieval_mode=mode)
                self.assertTrue(hits)
                self.assertIn("lora.md", [hit["source"] for hit in hits])

    def test_prompt_injection_in_document_is_data_and_cited(self):
        content = "提示注入是将恶意指令放入不可信文档。文档应作为待分析数据。"
        app.index_document("提示注入", "security.md", content)
        result = app.answer("提示注入是什么？")
        self.assertEqual("offline", result["mode"])
        self.assertTrue(result["citations"])
        self.assertIn("security.md", result["citations"][0]["source"])

    def test_unavailable_local_model_never_claims_success(self):
        app.index_document("RAG", "rag.md", "RAG 检索资料后生成回答。")
        with patch.dict(os.environ, {"KBQA_LLM_ENABLED": "1", "OPENAI_BASE_URL": "http://127.0.0.1:1/v1", "KBQA_EMBEDDINGS_ENABLED": "0"}):
            result = app.answer("RAG 如何回答？")
        self.assertNotEqual("llm", result["mode"])
        self.assertTrue(result.get("warning"), "model connection failure must be visible")


class MCPSmokeTest(unittest.TestCase):
    def test_stdio_initialize_list_and_search(self):
        with tempfile.TemporaryDirectory(prefix="kbqa-mcp-") as td:
            env = os.environ.copy()
            env["KBQA_DB"] = str(Path(td) / "mcp.sqlite3")
            env["KBQA_LLM_ENABLED"] = "0"
            import app as local_app
            old_db = local_app.DB_PATH
            local_app.DB_PATH = Path(env["KBQA_DB"])
            try:
                local_app.index_document("RAG", "mcp.md", "RAG 检索资料后生成回答。")
            finally:
                local_app.DB_PATH = old_db
            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "search_knowledge_base", "arguments": {"query": "RAG 检索"}}},
            ]
            proc = subprocess.run([sys.executable, str(ROOT / "mcp_server.py")], input="".join(json.dumps(x, ensure_ascii=False) + "\n" for x in requests), text=True, encoding="utf-8", capture_output=True, env=env, timeout=10)
            self.assertEqual(0, proc.returncode, proc.stderr)
            lines = [json.loads(line) for line in proc.stdout.splitlines()]
            self.assertEqual([1, 2, 3], [line.get("id") for line in lines])
            self.assertIn("search_knowledge_base", json.dumps(lines[1]))
            self.assertIn("mcp.md", json.dumps(lines[2], ensure_ascii=False))


class EvaluationDatasetTest(unittest.TestCase):
    def test_development_set_has_labelled_ai_and_refusal_questions(self):
        questions = json.loads((ROOT / "eval/questions.json").read_text(encoding="utf-8"))
        corpus = json.loads((ROOT / "eval/corpus.json").read_text(encoding="utf-8"))
        known = [item for item in questions if item["sources"]]
        unknown = [item for item in questions if not item["sources"]]
        self.assertGreaterEqual(len(known), 24)
        self.assertGreaterEqual(len(unknown), 8)
        source_set = {item["source"] for item in corpus}
        self.assertTrue(all(item["sources"] and set(item["sources"]) <= source_set and item["evidence"] for item in known))
        self.assertTrue(all(item["evidence"] is None for item in unknown))
        self.assertEqual(len(questions), len({item["id"] for item in questions}))

    def test_secret_preflight_detects_a_synthetic_token(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import preflight
        sample = ROOT / ".preflight-secret-test"
        try:
            sample.write_bytes(b"OPENAI_API_KEY=sk-" + b"A" * 24)
            self.assertEqual([str(sample.relative_to(ROOT))], preflight.find_secrets([sample]))
        finally:
            sample.unlink(missing_ok=True)

    def test_secret_preflight_skips_downloaded_model_assets(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import preflight
        scanned_roots = {path.relative_to(ROOT).parts[0] for path in preflight.scan_files()}
        self.assertNotIn("models", scanned_roots)
        self.assertNotIn(".runtime", scanned_roots)


class HTTPFlowTest(unittest.TestCase):
    """Real localhost end-to-end flow using a disposable DB and port."""

    def test_import_query_citation_list_and_delete(self):
        with tempfile.TemporaryDirectory(prefix="kbqa-http-") as td:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            env = os.environ.copy()
            env.update({"KBQA_DB": str(Path(td) / "http.sqlite3"), "KBQA_PORT": str(port), "KBQA_LLM_ENABLED": "0"})
            proc = subprocess.Popen([sys.executable, str(ROOT / "server.py")], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            base = f"http://127.0.0.1:{port}"
            try:
                deadline = time.monotonic() + 12
                while time.monotonic() < deadline:
                    if proc.poll() is not None:
                        self.fail(f"server exited early: {proc.stderr.read().decode(errors='replace')}")
                    try:
                        with urlopen(base + "/api/health", timeout=1) as response:
                            health = json.load(response)
                        break
                    except OSError:
                        time.sleep(0.1)
                else:
                    self.fail("server did not become healthy within 12 seconds")
                self.assertTrue(health["ok"])
                # Web imports must refuse loopback targets before making a request.
                loopback = Request(base + "/api/import-url", data=json.dumps({"url": "http://127.0.0.1:8000/api/health"}).encode(), headers={"Content-Type": "application/json"}, method="POST")
                try:
                    urlopen(loopback, timeout=2)
                except HTTPError as error:
                    self.assertGreaterEqual(error.code, 400)
                    error.close()
                else:
                    self.fail("URL import accepted a loopback address")
                payload = {"filename": "fixture.md", "title": "Transformer", "content_base64": base64.b64encode("Transformer 使用 Query、Key、Value 计算缩放点积注意力。".encode()).decode()}
                request = Request(base + "/api/upload", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
                with urlopen(request, timeout=5) as response:
                    uploaded = json.load(response)
                self.assertTrue(uploaded.get("ok"))
                request = Request(base + "/api/query", data=json.dumps({"question": "Transformer 注意力使用哪些向量？", "limit": 5}).encode(), headers={"Content-Type": "application/json"}, method="POST")
                with urlopen(request, timeout=6) as response:
                    answer = json.load(response)
                self.assertNotEqual("refusal", answer["mode"])
                self.assertTrue(any(citation["source"].endswith("fixture.md") for citation in answer["citations"]))
                with urlopen(base + "/api/documents", timeout=3) as response:
                    docs = json.load(response)["documents"]
                document_id = next(doc["id"] for doc in docs if doc["source"].endswith("fixture.md"))
                request = Request(base + f"/api/documents/{document_id}", method="DELETE")
                with urlopen(request, timeout=3) as response:
                    self.assertTrue(json.load(response).get("ok"))
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill(); proc.wait(timeout=3)
                if proc.stderr:
                    proc.stderr.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
