"""Deterministic contract and regression tests. No network or LLM is required."""
from __future__ import annotations

import json
import base64
import io
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

    def test_numeric_lookup_returns_all_documents_once_without_retrieval_or_model(self):
        for i in range(10):
            app.index_document(f"资料 {i}", f"note-{i}.md", "正文包含 2 项配置。" + "背景说明。" * 100 + "末尾再次出现 2。")
        with patch.dict(os.environ, {"KBQA_LLM_ENABLED": "1"}), \
                patch.object(app, "query") as query, patch.object(app, "embed_text") as embed, \
                patch.object(app.urllib.request, "urlopen") as model:
            for mode in ("hybrid", "bm25", "vector"):
                with self.subTest(retrieval_mode=mode):
                    result = app.answer("  2\n", limit=1, retrieval_mode=mode)
                    self.assertEqual("lookup", result["mode"])
                    self.assertEqual("2", result["lookup"]["term"])
                    self.assertEqual(10, result["lookup"]["matched_documents"])
                    matches = result["lookup"]["matches"]
                    self.assertEqual(10, len(matches))
                    self.assertEqual(10, len({match["document_id"] for match in matches}))
                    self.assertTrue(all("2" in match["snippet"] for match in matches))
                    self.assertTrue(all(match["chunk_id"] for match in matches))
                    self.assertEqual([], result["citations"])
                    self.assertEqual({"method": "literal", "hits": []}, result["retrieval"])
                    self.assertFalse(result["refused"])
                    self.assertIsNone(result["model"])
                    self.assertGreaterEqual(result["elapsed_ms"], 0)
            query.assert_not_called()
            embed.assert_not_called()
            model.assert_not_called()

    def test_numeric_lookup_shows_first_match_near_end_and_original_page(self):
        first_page = "第一部分没有目标内容。" * 80
        second_page = "第二部分介绍背景。" * 80 + "\n\t原文记录 2024 年的情况。" + "后续说明。" * 80 + "后面也有 2024 年记录。"
        app.index_pages("年度记录", "upload://annual.pdf", [(1, first_page), (2, second_page)], kind="pdf")
        match = app.answer("2024")["lookup"]["matches"][0]
        self.assertIn("原文记录 2024 年的情况。", match["snippet"])
        self.assertIn("\n\t", match["snippet"])
        self.assertLessEqual(len(match["snippet"]), 220)
        self.assertEqual(2, match["page"])
        document = app.get_document(match["document_id"])
        self.assertIn(match["snippet"], document["document"]["content"])
        chunk = next(item for item in document["chunks"] if item["chunk_id"] == match["chunk_id"])
        self.assertIn("2024", chunk["content"])
        self.assertEqual(2, chunk["page"])

    def test_numeric_lookup_matches_contiguous_substrings_only_in_body(self):
        app.index_document("双位数", "twelve.md", "共 12 项。")
        app.index_document("年份", "year.md", "发表于 2024 年。")
        app.index_document("2 和 2024", "2024-2.md", "正文没有任何数字。")
        app.index_document("分隔数字", "separated.md", "数字顺序为 2 024。")
        result = app.answer("2")
        self.assertEqual({"twelve.md", "year.md", "separated.md"}, {item["source"] for item in result["lookup"]["matches"]})
        result = app.answer("2024")
        self.assertEqual(["year.md"], [item["source"] for item in result["lookup"]["matches"]])

    def test_numeric_lookup_with_no_match_is_an_empty_search_not_a_refusal(self):
        app.index_document("无数字", "empty.md", "正文没有数字。")
        result = app.answer("999")
        self.assertEqual("lookup", result["mode"])
        self.assertFalse(result["refused"])
        self.assertEqual({"term": "999", "matched_documents": 0, "matches": []}, result["lookup"])
        self.assertEqual([], result["citations"])
        self.assertIn("未找到", result["answer"])

    def test_numeric_lookup_keeps_long_matched_term_inside_snippet(self):
        term = "1234567890" * 30
        app.index_document("长编号", "identifier.md", "背景" * 200 + term + "结束")
        match = app.answer(term)["lookup"]["matches"][0]
        self.assertIn(term, match["snippet"])
        self.assertIsNone(match["chunk_id"])
        self.assertIsNone(match["page"])

    def test_numeric_lookup_returns_all_passages_and_merges_overlapping_context(self):
        content = "甲处 2 以及附近 12。" + "间隔背景。" * 80 + "乙处 2024 年。" + "末尾背景。" * 80 + "丙处 2。"
        app.index_document("多处记录", "many.md", content)
        result = app.answer("2", limit=1)
        self.assertEqual(1, result["lookup"]["matched_documents"])
        match = result["lookup"]["matches"][0]
        self.assertEqual(3, len(match["passages"]))
        for text, passage in zip(("甲处 2 以及附近 12。", "乙处 2024 年。", "丙处 2。"), match["passages"]):
            self.assertIn(text, passage["snippet"])
            self.assertIn(passage["snippet"], content)
        self.assertEqual(match["passages"][0], {key: match[key] for key in ("snippet", "chunk_id", "page")})

    def test_numeric_lookup_preserves_later_page_locations_and_long_overlapping_matches(self):
        app.index_pages("分页记录", "pages.pdf", [(1, "首段记录 2。" + "甲背景。" * 100), (2, "乙背景。" * 100 + "末段记录 2。")], kind="pdf")
        passages = app.answer("2")["lookup"]["matches"][0]["passages"]
        self.assertEqual([1, 2], [passage["page"] for passage in passages])
        term = "2" * 300
        content = "起点" + "2" * 301 + "分隔" * 200 + term + "终点"
        app.index_document("长数字", "long.md", content)
        passages = app.answer(term)["lookup"]["matches"][0]["passages"]
        self.assertEqual(2, len(passages))
        self.assertIn("2" * 301, passages[0]["snippet"])
        self.assertTrue(all(term in passage["snippet"] for passage in passages))

    def test_pure_expression_without_explicit_result_refuses_and_never_generates(self):
        cases = ("第 1 页包含 1 个样例。", "练习：计算 1 + 1。", "11 + 11 = 22。", "1 + 10 = 11。",
                 "2 + 1 + 1 = 4。", "1 + 1 + 2 = 4。", "1.1 + 1 = 2.1。")
        for content in cases:
            app.index_document("数字资料", "numbers.md", content)
            with self.subTest(content=content), patch.dict(os.environ, {"KBQA_LLM_ENABLED": "1"}), \
                    patch.object(app.urllib.request, "urlopen") as model:
                result = app.answer("1 + 1")
                self.assertTrue(result["refused"])
                self.assertEqual([], result["citations"])
                self.assertEqual("refusal", result["mode"])
                model.assert_not_called()

    def test_pure_expression_uses_explicit_equation_beyond_topk_without_generating(self):
        for i in range(10):
            app.index_document(f"数字 {i}", f"number-{i}.md", "1 " * 100 + "练习：计算 1+1。")
        app.index_document("算式答案", "answer.md", "前例 8+8=16。明确记录：1 + 1 = 2。后例 3+3=6。")
        with patch.dict(os.environ, {"KBQA_LLM_ENABLED": "1"}), patch.object(app, "query") as query, \
                patch.object(app.urllib.request, "urlopen") as model:
            result = app.answer(" 1\t+ 1 ", limit=1)
        self.assertFalse(result["refused"])
        self.assertEqual("offline", result["mode"])
        self.assertEqual(["answer.md"], [citation["source"] for citation in result["citations"]])
        self.assertEqual("1 + 1 = 2", result["citations"][0]["snippet"])
        self.assertNotIn("8+8", result["answer"])
        query.assert_not_called()
        model.assert_not_called()

    def test_pure_expression_normalizes_common_multiplication_and_division_symbols(self):
        app.index_document("乘除", "operations.md", "2 × 3 等于 6。8 ÷ 2 = 4。")
        for question, snippet in (("2 * 3", "2 × 3 等于 6"), ("8 / 2", "8 ÷ 2 = 4")):
            with self.subTest(question=question):
                result = app.answer(question)
                self.assertFalse(result["refused"])
                self.assertEqual(snippet, result["citations"][0]["snippet"])

    def test_pure_expression_does_not_truncate_unsupported_numeric_results(self):
        for content in ("1 / 2 = 1/2。", "1 / 2 = 5e-1。", "1 / 2 = 1 - 0.5。"):
            with self.subTest(content=content):
                app.index_document("除法", "fraction.md", content)
                result = app.answer("1 / 2")
                self.assertTrue(result["refused"])
                self.assertEqual([], result["citations"])
        app.index_document("负数", "negative.md", "1 - 2 = -1。")
        result = app.answer("1 - 2")
        self.assertEqual("1 - 2 = -1", result["citations"][0]["snippet"])

    def test_numbers_in_natural_questions_and_non_ascii_digits_stay_in_qa(self):
        for question in ("2 的三次方是多少？", "２", "٢", "2.0", "-2", "2 3"):
            with self.subTest(question=question), patch.object(app, "query", return_value=[]) as query:
                result = app.answer(question)
                self.assertEqual("refusal", result["mode"])
                self.assertNotIn("lookup", result)
                query.assert_called_once_with(question, 5, "hybrid")

    def test_numeric_lookup_preserves_question_and_retrieval_validation(self):
        invalid = ((2, 5, "hybrid"), ("2" * 2001, 5, "hybrid"), ("2", 0, "hybrid"),
                   ("2", 9, "hybrid"), ("2", True, "hybrid"), ("2", 1.5, "hybrid"),
                   ("2", "1", "hybrid"), ("2", 5, "literal"))
        for question, limit, mode in invalid:
            with self.subTest(question=str(question)[:10], limit=limit, mode=mode), self.assertRaises(ValueError):
                app.answer(question, limit, mode)

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

    def test_generated_citation_gate_keeps_original_evidence_on_invalid_references(self):
        with patch.dict(os.environ, {"KBQA_LLM_ENABLED": "0", "KBQA_EMBEDDINGS_ENABLED": "0"}):
            app.index_document("RAG", "rag.md", "RAG 检索资料后生成回答。")
            original = app.answer("RAG 如何回答？")
        cases = (("RAG 检索资料后生成回答。", False),
                 ("RAG 检索资料后生成回答。[99]", False),
                 ("[1] RAG 检索资料后生成回答。", True))
        for text, accepted in cases:
            payload = json.dumps({"choices": [{"message": {"content": text}}]}).encode()
            with self.subTest(output=text), patch.dict(os.environ, {"KBQA_LLM_ENABLED": "1", "KBQA_EMBEDDINGS_ENABLED": "0"}), \
                    patch.object(app.urllib.request, "urlopen", return_value=io.BytesIO(payload)):
                result = app.answer("RAG 如何回答？")
            self.assertEqual(original["citations"], result["citations"])
            if accepted:
                self.assertEqual("llm", result["mode"])
                self.assertEqual(text, result["answer"])
            else:
                self.assertEqual("offline", result["mode"])
                self.assertTrue(result.get("warning"))
                self.assertEqual(original["answer"], result["answer"])


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


class LiveMetricsTest(unittest.TestCase):
    def setUp(self):
        import metrics
        self.metrics = metrics
        self.tmp = tempfile.TemporaryDirectory(prefix="kbqa-metrics-")
        self.previous_path = app.DB_PATH
        app.DB_PATH = Path(self.tmp.name) / "metrics.sqlite3"

    def tearDown(self):
        app.DB_PATH = self.previous_path
        self.tmp.cleanup()

    def sample(self, refused=False):
        return {"answer": "没有足够证据" if refused else "RAG 使用检索证据 [1] [2]",
                "refused": refused, "mode": "refusal" if refused else "offline",
                "retrieval": {"hits": [{"source": "rag.md"}, {"source": "other.md"}, {"source": "third.md"}, {"source": "fourth.md"}]},
                "citations": [] if refused else [{"id": 1, "source": "rag.md", "snippet": "RAG 使用检索证据"}, {"id": 2, "source": "other.md", "snippet": "其他资料"}]}

    def automatic_review(self, method="local-model"):
        return {"answerable": True, "expected_sources": ["rag.md"], "citation_verdicts": {"1": True, "2": False},
                "method": method, "model": "test-model" if method == "local-model" else None,
                "reason": "测试用自动估算", "scope": {"kind": "candidate-pool", "candidate_chunks": 4, "total_chunks": 8},
                "evaluated_at": "2026-11-24T12:00:00+00:00", "elapsed_ms": 1}

    def test_migrates_old_history_without_changing_human_reviews(self):
        response = self.sample()
        review = {"answerable": True, "expected_sources": ["rag.md"], "citation_verdicts": {"1": True}}
        database = app.db()
        with database:
            database.execute("CREATE TABLE query_events (id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT NOT NULL, response TEXT NOT NULL, created_at TEXT NOT NULL, review TEXT)")
            database.execute("INSERT INTO query_events VALUES(7,?,?,?,?)", ("旧问答", json.dumps(response), "2026-11-24T12:00:00+00:00", json.dumps(review)))
        database.close()
        item = self.metrics.history()[0]
        self.assertEqual((7, response, review, None), (item["id"], item["response"], item["review"], item["auto_review"]))
        self.assertEqual(1, self.metrics.summary()["reviewed_questions"])
        self.assertEqual(0, self.metrics.summary()["pending_questions"])
        self.assertEqual(8, self.metrics.record_query("新问答", response, self.automatic_review()))

    def test_automatic_scores_update_and_human_votes_override_individually(self):
        first = self.metrics.record_query("RAG 是什么？", self.sample(), self.automatic_review())
        second_auto = {**self.automatic_review("lexical-fallback"), "expected_sources": ["missing.md"], "citation_verdicts": {"1": False, "2": True}}
        self.metrics.record_query("另一个问题", self.sample(), second_auto)
        self.metrics.record_query("尚未评估", self.sample(refused=True))
        summary = self.metrics.summary()
        self.assertEqual((2, 1, 1, 0, 1), (summary["auto_evaluated_questions"], summary["model_evaluated_questions"], summary["rule_evaluated_questions"], summary["reviewed_questions"], summary["pending_questions"]))
        self.assertEqual({"value": 0.5, "hits": 1, "total": 2}, summary["recall"])
        self.assertEqual({"value": 0.5, "correct": 2, "total": 4}, summary["citation_accuracy"])
        self.metrics.save_review(first, {"answerable": True, "expected_sources": ["missing.md"], "citation_verdicts": {"2": True}})
        summary = self.metrics.summary()
        self.assertEqual({"value": 0.0, "hits": 0, "total": 2}, summary["recall"])
        self.assertEqual({"value": 0.75, "correct": 3, "total": 4}, summary["citation_accuracy"])
        self.assertEqual(1, summary["reviewed_questions"])
        self.assertEqual(self.automatic_review(), next(item for item in self.metrics.history() if item["id"] == first)["auto_review"])

    def test_backfill_is_idempotent_and_preserves_manual_overrides(self):
        first = self.metrics.record_query("待补评", self.sample())
        manual = {"answerable": True, "expected_sources": ["missing.md"], "citation_verdicts": {"1": False}}
        self.metrics.save_review(first, manual)
        existing = self.automatic_review("lexical-fallback")
        self.metrics.record_query("已有自动评估", self.sample(), existing)
        with patch("auto_eval.evaluate", return_value=self.automatic_review()) as evaluate:
            self.assertEqual({"evaluated": 1, "failed": 0, "total_questions": 2}, self.metrics.backfill_missing())
            evaluate.assert_called_once_with("待补评", self.sample(), backfill=True)
            self.assertEqual({"evaluated": 0, "failed": 0, "total_questions": 2}, self.metrics.backfill_missing())
            self.assertEqual(1, evaluate.call_count)
        history = self.metrics.history()
        self.assertEqual(existing, history[0]["auto_review"])
        self.assertEqual(manual, history[1]["review"])
        self.assertEqual({"value": 0.5, "hits": 1, "total": 2}, self.metrics.summary()["recall"])

    def test_http_evaluation_failure_keeps_the_answer_and_pending_record(self):
        import server
        with server.Server(("127.0.0.1", 0), server.Handler) as http:
            thread = threading.Thread(target=http.serve_forever, daemon=True)
            thread.start()
            try:
                request = Request(f"http://127.0.0.1:{http.server_port}/api/query", data=json.dumps({"question": "RAG 是什么？"}).encode(), headers={"Content-Type": "application/json"}, method="POST")
                with patch.object(app, "answer", return_value=self.sample()), patch.object(server.auto_eval, "evaluate", side_effect=RuntimeError("unexpected evaluator failure")):
                    with urlopen(request, timeout=3) as response:
                        answer = json.load(response)
                self.assertEqual(self.sample()["answer"], answer["answer"])
                self.assertIsNone(answer["auto_review"])
                self.assertTrue(answer["evaluation_warning"])
                self.assertEqual(1, answer["metrics"]["pending_questions"])
                snapshot = self.metrics.history()[0]["response"]
                self.assertNotIn("metrics", snapshot)
                self.assertNotIn("auto_review", snapshot)
            finally:
                http.shutdown()
                thread.join(timeout=3)

    def test_http_numeric_lookup_does_not_evaluate_or_change_history_and_metrics(self):
        import server
        app.index_document("数学", "math.md", "2 的三次方等于 8。")
        self.metrics.record_query("已有问题", self.sample(), self.automatic_review())
        before_history, before_metrics = self.metrics.history(), self.metrics.summary()
        with server.Server(("127.0.0.1", 0), server.Handler) as http:
            thread = threading.Thread(target=http.serve_forever, daemon=True)
            thread.start()
            try:
                with patch.object(server.auto_eval, "evaluate", return_value=None) as evaluate:
                    for question in ("2", "999"):
                        request = Request(f"http://127.0.0.1:{http.server_port}/api/query", data=json.dumps({"question": question}).encode(), headers={"Content-Type": "application/json"}, method="POST")
                        with urlopen(request, timeout=3) as response:
                            result = json.load(response)
                        self.assertEqual("lookup", result["mode"])
                        self.assertIsNone(result["query_id"])
                        self.assertIsNone(result["auto_review"])
                        self.assertEqual(before_metrics, result["metrics"])
                    evaluate.assert_not_called()
                    self.assertEqual(before_history, self.metrics.history())
                    self.assertEqual(before_metrics, self.metrics.summary())
                    request = Request(f"http://127.0.0.1:{http.server_port}/api/query", data=json.dumps({"question": "2 的三次方是多少？"}).encode(), headers={"Content-Type": "application/json"}, method="POST")
                    with urlopen(request, timeout=3) as response:
                        result = json.load(response)
                    self.assertNotEqual("lookup", result["mode"])
                    self.assertIsInstance(result["query_id"], int)
                    self.assertEqual(before_metrics["total_questions"] + 1, result["metrics"]["total_questions"])
                    self.assertEqual(len(before_history) + 1, len(self.metrics.history()))
                    evaluate.assert_called_once()
            finally:
                http.shutdown()
                thread.join(timeout=3)

    def test_empty_and_unreviewed_questions_do_not_invent_quality_scores(self):
        empty = self.metrics.summary()
        self.assertEqual(0, empty["total_questions"])
        for name in ("recall", "citation_accuracy", "refusal_rate"):
            self.assertIsNone(empty[name]["value"])
        app.answer("没有资料的问题")
        self.assertEqual(0, self.metrics.summary()["total_questions"], "direct offline evaluations must not enter live statistics")
        self.metrics.record_query("RAG 是什么？", self.sample())
        self.metrics.record_query("今天的天气？", self.sample(refused=True))
        result = self.metrics.summary()
        self.assertEqual((2, 2, 0), (result["total_questions"], result["pending_questions"], result["reviewed_questions"]))
        self.assertIsNone(result["recall"]["value"])
        self.assertIsNone(result["citation_accuracy"]["value"])
        self.assertEqual({"value": 0.5, "refused": 1, "total": 2}, result["refusal_rate"])

    def test_review_replaces_votes_and_uses_only_top_three_saved_sources(self):
        first = self.metrics.record_query("RAG 是什么？", self.sample())
        second = self.metrics.record_query("第四份资料是什么？", self.sample())
        self.metrics.save_review(first, {"answerable": True, "expected_sources": ["rag.md"], "citation_verdicts": {"1": True}})
        self.metrics.save_review(second, {"answerable": True, "expected_sources": ["fourth.md"], "citation_verdicts": {}})
        result = self.metrics.summary()
        self.assertEqual({"value": 0.5, "hits": 1, "total": 2}, result["recall"])
        self.assertEqual({"value": 1.0, "correct": 1, "total": 1}, result["citation_accuracy"])
        self.metrics.save_review(first, {"answerable": True, "expected_sources": ["missing.md"], "citation_verdicts": {"1": False, "2": True}})
        result = self.metrics.summary()
        self.assertEqual({"value": 0.0, "hits": 0, "total": 2}, result["recall"])
        self.assertEqual({"value": 0.5, "correct": 1, "total": 2}, result["citation_accuracy"])
        self.assertEqual(2, result["reviewed_questions"])
        self.metrics.save_review(second, {"answerable": False, "expected_sources": [], "citation_verdicts": {}})
        self.assertEqual(1, self.metrics.summary()["recall"]["total"])

    def test_invalid_reviews_do_not_change_saved_review(self):
        query_id = self.metrics.record_query("RAG 是什么？", self.sample())
        valid = {"answerable": True, "expected_sources": ["rag.md"], "citation_verdicts": {"1": True}}
        self.metrics.save_review(query_id, valid)
        invalid = [
            {**valid, "answerable": 1}, {**valid, "expected_sources": []},
            {**valid, "expected_sources": ["rag.md", " rag.md "]},
            {**valid, "expected_sources": ["x" * 2049]},
            {**valid, "expected_sources": "rag.md"},
            {**valid, "answerable": False},
            {**valid, "citation_verdicts": {"99": True}},
            {**valid, "citation_verdicts": {"1": 1}},
            {**valid, "citation_verdicts": {"1": None}},
        ]
        for review in invalid:
            with self.subTest(review=review), self.assertRaises(ValueError):
                self.metrics.save_review(query_id, review)
        self.assertEqual(valid, self.metrics.history()[0]["review"])
        self.assertIsNone(self.metrics.save_review(999, valid))

    def test_snapshots_survive_document_deletion_and_database_reopen(self):
        app.index_document("RAG", "rag.md", "RAG 使用检索证据。")
        response = app.answer("RAG 是什么？")
        query_id = self.metrics.record_query("RAG 是什么？", response)
        document_id = app.list_documents()[0]["id"]
        app.delete_document(document_id)
        self.metrics.save_review(query_id, {"answerable": True, "expected_sources": ["rag.md"], "citation_verdicts": {"1": True}})
        item = self.metrics.history()[0]
        self.assertEqual(response, item["response"])
        self.assertEqual(query_id, item["id"])
        self.assertEqual(1.0, self.metrics.summary()["recall"]["value"])
        self.assertEqual([], app.list_documents())


class SeedUpgradeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="kbqa-seed-")
        self.root = Path(self.tmp.name)
        knowledge = self.root / "data" / "knowledge"
        knowledge.mkdir(parents=True)
        (self.root / "data" / "sample.md").write_text("# AI 示例\nRAG 从资料检索证据。", encoding="utf-8")
        (knowledge / "math.md").write_text("# 数学\n勾股定理适用于直角三角形。", encoding="utf-8")
        (knowledge / "biology.md").write_text("# 生物\n光合作用把光能转化为化学能。", encoding="utf-8")
        self.environment = patch.dict(os.environ, {"KBQA_LLM_ENABLED": "0", "KBQA_EMBEDDINGS_ENABLED": "0"})
        self.environment.start()
        self.paths = patch.multiple(app, ROOT=self.root, DB_PATH=self.root / "test.sqlite3")
        self.paths.start()

    def tearDown(self):
        self.paths.stop()
        self.environment.stop()
        self.tmp.cleanup()

    def test_fresh_seed_keeps_ai_and_adds_general_documents_once(self):
        app.seed()
        documents = app.list_documents()
        self.assertEqual({"data/sample.md", "example://math.md", "example://biology.md"}, {item["source"] for item in documents})
        app.seed()
        self.assertEqual(documents, app.list_documents())
        for document in documents:
            app.delete_document(document["id"])
        app.seed()
        self.assertEqual([], app.list_documents())

    def test_old_seed_adds_new_batch_without_replacing_content_or_history(self):
        import metrics
        app.index_document("旧示例", "data/sample.md", "原有 RAG 资料不可覆盖。")
        app.index_document("用户修改的数学", "example://math.md", "用户自定义内容不可覆盖。")
        app.index_document("用户上传", "upload://notes.md", "用户笔记保持不变。")
        database = app.db()
        with database:
            database.execute("INSERT INTO metadata VALUES('sample_seed_v2','1')")
        database.close()
        response = {"answer": "历史回答 [1]", "refused": False,
                    "retrieval": {"hits": [{"source": "data/sample.md"}]},
                    "citations": [{"id": 1, "source": "data/sample.md", "snippet": "原有 RAG 资料不可覆盖。"}]}
        automatic = {"answerable": True, "expected_sources": ["data/sample.md"], "citation_verdicts": {"1": True},
                     "method": "lexical-fallback", "reason": "升级前的估算"}
        ident = metrics.record_query("历史问题", response, automatic)
        metrics.save_review(ident, {"answerable": True, "expected_sources": ["data/sample.md"], "citation_verdicts": {"1": True}})
        history = metrics.history()
        old_documents = {item["source"]: app.get_document(item["id"]) for item in app.list_documents()}
        app.seed()
        self.assertEqual(history, metrics.history())
        self.assertEqual(4, len(app.list_documents()))
        for source, document in old_documents.items():
            self.assertEqual(document, app.get_document(document["document"]["id"]), source)
        app.seed()
        self.assertEqual(4, len(app.list_documents()))
        self.assertEqual(history, metrics.history())

    def test_upgrade_does_not_restore_a_deleted_old_sample(self):
        database = app.db()
        with database:
            database.execute("INSERT INTO metadata VALUES('sample_seed_v2','1')")
        database.close()
        app.seed()
        self.assertEqual({"example://math.md", "example://biology.md"}, {item["source"] for item in app.list_documents()})

    def test_bundled_general_knowledge_answers_across_domains(self):
        with patch.object(app, "ROOT", ROOT):
            app.seed()
        cases = (
            ("指数运算中 2 的三次方是多少？", "general-math-exponents.md"),
            ("均值和中位数有什么区别？", "general-statistics-center.md"),
            ("牛顿第二定律怎样联系合力和加速度？", "general-physics-newton.md"),
            ("光合作用利用哪些原料并释放什么气体？", "general-biology-photosynthesis.md"),
            ("机会成本指什么？", "general-economics-opportunity-cost.md"),
            ("Python 列表和元组在可修改性上有什么区别？", "general-programming-python.md"),
        )
        for question, filename in cases:
            with self.subTest(question=question):
                result = app.answer(question)
                self.assertFalse(result["refused"])
                self.assertIn("example://" + filename, {citation["source"] for citation in result["citations"]})
                self.assertTrue(all(citation["snippet"] and citation["chunk_id"] for citation in result["citations"]))
        for question in ("我今天午餐吃了什么？", "我的银行卡密码是多少？"):
            with self.subTest(unsupported_question=question):
                self.assertTrue(app.answer(question)["refused"])


class HTTPFlowTest(unittest.TestCase):
    """Real localhost end-to-end flow using a disposable DB and port."""

    def test_import_query_citation_list_and_delete(self):
        with tempfile.TemporaryDirectory(prefix="kbqa-http-") as td:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            env = os.environ.copy()
            env.update({"KBQA_DB": str(Path(td) / "http.sqlite3"), "KBQA_PORT": str(port), "KBQA_LLM_ENABLED": "0", "KBQA_EMBEDDINGS_ENABLED": "0"})
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
                with urlopen(base + "/api/metrics", timeout=3) as response:
                    self.assertEqual(0, json.load(response)["total_questions"])
                empty_question = Request(base + "/api/query", data=b'{"question":"   "}', headers={"Content-Type": "application/json"}, method="POST")
                with self.assertRaises(HTTPError) as invalid:
                    urlopen(empty_question, timeout=3)
                self.assertEqual(400, invalid.exception.code)
                invalid.exception.close()
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
                self.assertEqual(1, answer["metrics"]["total_questions"])
                self.assertEqual("lexical-fallback", answer["auto_review"]["method"])
                self.assertIsNotNone(answer["metrics"]["citation_accuracy"]["value"])
                self.assertEqual(1, answer["metrics"]["auto_evaluated_questions"])
                self.assertEqual(0, answer["metrics"]["pending_questions"])
                self.assertIsInstance(answer["query_id"], int)
                review = {"answerable": True, "expected_sources": ["upload://fixture.md"], "citation_verdicts": {str(answer["citations"][0]["id"]): True}}
                request = Request(base + f'/api/history/{answer["query_id"]}/review', data=json.dumps(review).encode(), headers={"Content-Type": "application/json"}, method="POST")
                with urlopen(request, timeout=3) as response:
                    reviewed = json.load(response)
                self.assertEqual(1.0, reviewed["metrics"]["recall"]["value"])
                self.assertEqual(review, reviewed["review"])
                request = Request(base + "/api/history/999999/review", data=json.dumps(review).encode(), headers={"Content-Type": "application/json"}, method="POST")
                with self.assertRaises(HTTPError) as missing:
                    urlopen(request, timeout=3)
                self.assertEqual(404, missing.exception.code)
                missing.exception.close()
                request = Request(base + "/api/query", data=json.dumps({"question": "我今天午餐吃了什么？"}).encode(), headers={"Content-Type": "application/json"}, method="POST")
                with urlopen(request, timeout=6) as response:
                    refused = json.load(response)
                self.assertTrue(refused["refused"])
                self.assertEqual({"value": 0.5, "refused": 1, "total": 2}, refused["metrics"]["refusal_rate"])
                with urlopen(base + "/api/documents", timeout=3) as response:
                    docs = json.load(response)["documents"]
                document_id = next(doc["id"] for doc in docs if doc["source"].endswith("fixture.md"))
                request = Request(base + f"/api/documents/{document_id}", method="DELETE")
                with urlopen(request, timeout=3) as response:
                    self.assertTrue(json.load(response).get("ok"))
                # A fresh server process must retain reviews and the original citation snapshot.
                proc.terminate()
                proc.wait(timeout=4)
                proc.stderr.close()
                proc = subprocess.Popen([sys.executable, str(ROOT / "server.py")], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                deadline = time.monotonic() + 12
                while time.monotonic() < deadline:
                    try:
                        with urlopen(base + "/api/history", timeout=1) as response:
                            history = json.load(response)["history"]
                        break
                    except OSError:
                        time.sleep(0.1)
                else:
                    self.fail("restarted server did not return stored history")
                self.assertEqual([refused["query_id"], answer["query_id"]], [item["id"] for item in history])
                self.assertEqual(review, history[1]["review"])
                self.assertEqual(answer["citations"], history[1]["response"]["citations"])
                self.assertEqual(answer["auto_review"], history[1]["auto_review"])
                with urlopen(base + "/api/metrics", timeout=3) as response:
                    persisted = json.load(response)
                self.assertEqual(2, persisted["total_questions"])
                self.assertEqual(1, persisted["reviewed_questions"])
                self.assertEqual(1.0, persisted["citation_accuracy"]["value"])
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
