"""Automatic reviews must remain estimates and never invent evidence."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import auto_eval


class AutomaticReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="kbqa-auto-eval-")
        self.old_path = app.DB_PATH
        app.DB_PATH = Path(self.tmp.name) / "test.sqlite3"
        self.environment = patch.dict(os.environ, {"KBQA_LLM_ENABLED": "1", "KBQA_EMBEDDINGS_ENABLED": "0"})
        self.environment.start()
        app.index_document("RAG", "rag.md", "RAG 先检索知识库证据，再根据证据生成回答。")
        self.hit = app.query("RAG", retrieval_mode="bm25")[0]
        self.response = {
            "answer": "RAG 先检索知识库证据，再根据证据生成回答。[1]",
            "refused": False,
            "citations": [{"id": 1, "source": "rag.md", "chunk_id": self.hit["chunk_id"],
                           "snippet": self.hit["content"], "page": None, "document_id": self.hit["document_id"]}],
            "retrieval": {"hits": [self.hit]},
        }

    def tearDown(self):
        self.environment.stop()
        app.DB_PATH = self.old_path
        self.tmp.cleanup()

    def model_result(self, **updates):
        value = {"answerable": True, "expected_sources": ["S1"], "citation_verdicts": {"1": True}, "reason": "原文支持回答。"}
        value.update(updates)
        return json.dumps(value, ensure_ascii=False)

    def test_valid_model_json_uses_real_source_names(self):
        with patch.object(auto_eval, "_model_output", return_value=self.model_result()):
            result = auto_eval.evaluate("RAG", self.response)
        self.assertEqual("local-model", result["method"])
        self.assertEqual(["rag.md"], result["expected_sources"])
        self.assertEqual({"1": True}, result["citation_verdicts"])
        self.assertEqual("full-library", result["scope"]["kind"])
        self.assertIn("evaluated_at", result)

    def test_invalid_json_and_unknown_ids_use_explicit_fallback(self):
        cases = ["not JSON", self.model_result(expected_sources=["S999"]),
                 self.model_result(citation_verdicts={"1": True, "9": True}),
                 self.model_result(citation_verdicts={}),
                 self.model_result(citation_verdicts={"1": "true"})]
        for output in cases:
            with self.subTest(output=output), patch.object(auto_eval, "_model_output", return_value=output):
                result = auto_eval.evaluate("RAG", self.response)
            self.assertEqual("lexical-fallback", result["method"])
            self.assertEqual(["rag.md"], result["expected_sources"])
            self.assertEqual({"1": True}, result["citation_verdicts"])

    def test_fabricated_snippet_and_mismatched_source_are_denied(self):
        for changes in ({"snippet": "RAG 保证任何回答都正确。"}, {"source": "invented.md"}, {"chunk_id": "wrong"}):
            with self.subTest(changes=changes):
                citation = dict(self.response["citations"][0], **changes)
                response = dict(self.response, citations=[citation])
                with patch.object(auto_eval, "_model_output", return_value=self.model_result()):
                    result = auto_eval.evaluate("RAG", response)
                self.assertEqual({"1": False}, result["citation_verdicts"])

    def test_refusal_does_not_force_unanswerable(self):
        response = dict(self.response, answer=app.REFUSAL, refused=True, citations=[])
        with patch.object(auto_eval, "_model_output", return_value=self.model_result(citation_verdicts={})):
            result = auto_eval.evaluate("RAG", response)
        self.assertTrue(result["answerable"])
        self.assertEqual({}, result["citation_verdicts"])

    def test_independent_pool_finds_source_missed_by_answer_retrieval(self):
        app.index_document("LoRA", "lora.md", "LoRA 使用低秩矩阵进行参数高效微调。")
        response = {"answer": app.REFUSAL, "refused": True, "citations": [], "retrieval": {"hits": [self.hit]}}
        with patch.dict(os.environ, {"KBQA_LLM_ENABLED": "0"}):
            result = auto_eval.evaluate("LoRA", response)
        self.assertEqual(["lora.md"], result["expected_sources"])
        self.assertTrue(result["answerable"])

    def test_backfill_uses_saved_evidence_after_library_replacement(self):
        app.index_document("改写", "rag.md", "今日天气晴朗。")
        with patch.object(app, "db", side_effect=AssertionError("Backfill must not read current library")), patch.dict(os.environ, {"KBQA_LLM_ENABLED": "0"}):
            result = auto_eval.evaluate("RAG", self.response, backfill=True)
        self.assertEqual(["rag.md"], result["expected_sources"])
        self.assertEqual({"1": True}, result["citation_verdicts"])
        self.assertEqual("saved-retrieval", result["scope"]["kind"])
        self.assertIn("历史", result["reason"])

    def test_fallback_requires_claim_support_and_reference_marker(self):
        for answer in ("RAG 保证答案百分之百正确。[1]", "RAG 先检索知识库证据，再根据证据生成回答。"):
            with self.subTest(answer=answer), patch.dict(os.environ, {"KBQA_LLM_ENABLED": "0"}):
                result = auto_eval.evaluate("RAG", dict(self.response, answer=answer))
            self.assertEqual({"1": False}, result["citation_verdicts"])

    def test_adjacent_reference_markers_share_the_same_claim(self):
        citation = dict(self.response["citations"][0], id=2)
        response = dict(self.response, answer=self.response["answer"] + "[2]", citations=self.response["citations"] + [citation])
        with patch.dict(os.environ, {"KBQA_LLM_ENABLED": "0"}):
            result = auto_eval.evaluate("RAG", response)
        self.assertEqual({"1": True, "2": True}, result["citation_verdicts"])

    def test_no_evidence_or_citations_does_not_create_denominators(self):
        response = {"answer": app.REFUSAL, "refused": True, "citations": [], "retrieval": {"hits": []}}
        with patch.dict(os.environ, {"KBQA_LLM_ENABLED": "0"}):
            result = auto_eval.evaluate("午餐吃了什么", response)
        self.assertFalse(result["answerable"])
        self.assertEqual([], result["expected_sources"])
        self.assertEqual({}, result["citation_verdicts"])

    def test_large_library_is_disclosed_and_context_is_bounded(self):
        for number in range(20):
            app.index_document(str(number), f"large-{number}.md", "RAG 检索生成回答。" * 50)
        captured = []
        def output(payload):
            captured.append(payload)
            return self.model_result()
        with patch.object(auto_eval, "_model_output", side_effect=output):
            result = auto_eval.evaluate("RAG" * 500, self.response)
        self.assertEqual("candidate-pool", result["scope"]["kind"])
        self.assertLess(result["scope"]["candidate_chunks"], result["scope"]["total_chunks"])
        self.assertLess(len(json.dumps(captured[0], ensure_ascii=False)), 5000)

    def test_long_offline_answer_keeps_each_cited_claim(self):
        hits, citations = [], []
        for number in range(1, 4):
            content = "RAG 先检索知识库证据，再根据证据生成回答。" * 14
            hit = dict(self.hit, chunk_id=f"long-{number}", source=f"long-{number}.md", content=content)
            hits.append(hit)
            citations.append({"id": number, "source": hit["source"], "chunk_id": hit["chunk_id"],
                              "snippet": content, "page": None, "document_id": hit["document_id"]})
        response = {"answer": "根据知识库原文摘录：\n\n" + "\n\n".join(f'[{item["id"]}] {item["snippet"]}' for item in citations),
                    "citations": citations, "retrieval": {"hits": hits}, "refused": False}
        self.assertGreater(response["answer"].index("[3]"), 500)
        def output(payload):
            verdicts = {item["id"]: item["used_in_answer"] and bool(item["claim"]) and item["claim"] in item["snippet"]
                        for item in payload["citations"]}
            return self.model_result(expected_sources=["S1", "S2", "S3"], citation_verdicts=verdicts)
        with patch.object(auto_eval, "_model_output", side_effect=output):
            result = auto_eval.evaluate("RAG", response, backfill=True)
        self.assertEqual("local-model", result["method"])
        self.assertEqual({"1": True, "2": True, "3": True}, result["citation_verdicts"])


if __name__ == "__main__":
    unittest.main()
