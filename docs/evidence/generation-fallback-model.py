"""Verify opt-in generation against real configured models using an isolated database."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    with tempfile.TemporaryDirectory(prefix="kbqa-generation-model-") as temporary:
        os.environ["KBQA_DB"] = str(Path(temporary) / "isolated.sqlite3")
        os.environ["KBQA_LLM_ENABLED"] = "1"
        os.environ["KBQA_EMBEDDINGS_ENABLED"] = "1"
        import app
        import metrics
        import server

        assert app.model_status()["available"], "Start the configured generation model first"
        assert app.embedding_status()["available"], "Start the configured embedding model first"
        app.index_document("RAG 入门", "fixture://rag", "RAG 是检索增强生成。先从知识库检索与问题相关的资料，再将资料作为上下文交给大模型生成回答。")
        with server.Server(("127.0.0.1", 0), server.Handler) as service:
            worker = threading.Thread(target=service.serve_forever, daemon=True)
            worker.start()

            def post(path, payload):
                request = Request(f"http://127.0.0.1:{service.server_port}{path}", data=json.dumps(payload).encode(),
                                  headers={"Content-Type": "application/json"}, method="POST")
                with urlopen(request, timeout=240) as response:
                    return json.load(response)

            try:
                supported = post("/api/query", {"question": "RAG 是什么？"})
                assert supported["mode"] == "llm" and not supported["refused"] and supported["citations"], supported
                refused = post("/api/query", {"question": "1+1"})
                assert refused["refused"] and refused["citations"] == []
                assert refused["metrics"]["refusal_rate"] == {"value": 0.5, "refused": 1, "total": 2}
                before_history, before_metrics = metrics.history(), metrics.summary()
                generated = post("/api/generate", {"query_id": refused["query_id"], "confirmed": True})
                assert generated["mode"] == "llm-general" and generated["citations"] == [] and generated["answer"].strip()
                assert "2" in generated["answer"], generated
                assert metrics.history() == before_history and metrics.summary() == before_metrics
                report = {"passed": True, "isolated_database": True, "mocked_model": False,
                          "health": {"model": app.model_status(), "embedding": app.embedding_status()},
                          "supported": supported, "refused": refused, "generated": generated,
                          "history_unchanged_by_generation": True, "metrics_unchanged_by_generation": True,
                          "final_metrics": metrics.summary()}
                (ROOT / "docs/evidence/generation-fallback-model.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(json.dumps({"passed": True, "generated": generated, "refusal_rate": before_metrics["refusal_rate"]}, ensure_ascii=False))
            finally:
                service.shutdown()
                worker.join(timeout=3)


if __name__ == "__main__":
    main()
