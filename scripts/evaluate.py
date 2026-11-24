"""Offline labelled retrieval/answer evaluation, isolated from the user's database."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def ratio(numerator, denominator):
    return numerator / denominator if denominator else 0.0


def evaluate(use_llm=False):
    os.environ["KBQA_LLM_ENABLED"] = "1" if use_llm else "0"
    import app

    corpus = json.loads((ROOT / "eval/corpus.json").read_text(encoding="utf-8"))
    questions = json.loads((ROOT / "eval/questions.json").read_text(encoding="utf-8"))
    previous_db = app.DB_PATH
    report = {
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "dataset": "KBQA AI development set v1 (24 answerable, 8 out-of-domain)",
        "generation": "configured-local-llm" if use_llm else "deterministic-offline",
        "limitations": "Development corpus; evidence citation metrics do not prove generated-claim correctness.",
        "modes": {},
    }
    with tempfile.TemporaryDirectory(prefix="kbqa-eval-") as temporary:
        app.DB_PATH = Path(temporary) / "evaluation.sqlite3"
        try:
            for document in corpus:
                app.index_document(document["title"], document["source"], document["content"])
            for mode in ("bm25", "vector", "hybrid"):
                cases = []
                for item in questions:
                    hits = app.query(item["question"], limit=3, retrieval_mode=mode)
                    started = time.perf_counter()
                    response = app.answer(item["question"], limit=3, retrieval_mode=mode)
                    elapsed = (time.perf_counter() - started) * 1000
                    cited = response.get("citations", [])
                    by_id = {str(hit["chunk_id"]): hit for hit in hits}
                    traces = []
                    supported = []
                    for citation in cited:
                        chunk = by_id.get(str(citation.get("chunk_id")), {})
                        snippet = citation.get("snippet", "")
                        traces.append(bool(snippet) and snippet in chunk.get("content", "")
                                      and citation.get("source") == chunk.get("source")
                                      and citation.get("page") == chunk.get("page"))
                        supported.append(citation.get("source") in item["sources"]
                                         and bool(item["evidence"])
                                         and item["evidence"] in snippet)
                    retrieved_sources = [hit["source"] for hit in hits]
                    cases.append({
                        **item,
                        "retrieved_sources": retrieved_sources,
                        "recall_at_1": bool(set(item["sources"]) & set(retrieved_sources[:1])),
                        "recall_at_3": bool(set(item["sources"]) & set(retrieved_sources)),
                        "refused": response.get("refused", response.get("mode") == "refusal"),
                        "answer_mode": response.get("mode"),
                        "latency_ms": round(elapsed, 3),
                        "supported_citations": sum(supported),
                        "traceable_citations": sum(traces),
                        "citation_count": len(cited),
                        "answer": response.get("answer"),
                        "citations": cited,
                        "warning": response.get("warning"),
                    })
                known = [case for case in cases if case["sources"]]
                unknown = [case for case in cases if not case["sources"]]
                latencies = sorted(case["latency_ms"] for case in cases)
                total_citations = sum(case["citation_count"] for case in cases)
                report["modes"][mode] = {
                    "metrics": {
                        "recall_at_1": ratio(sum(c["recall_at_1"] for c in known), len(known)),
                        "recall_at_3": ratio(sum(c["recall_at_3"] for c in known), len(known)),
                        "evidence_citation_accuracy": ratio(sum(c["supported_citations"] for c in cases), total_citations),
                        "citation_traceability": ratio(sum(c["traceable_citations"] for c in cases), total_citations),
                        "correct_refusal_rate": ratio(sum(c["refused"] for c in unknown), len(unknown)),
                        "false_refusal_rate": ratio(sum(c["refused"] for c in known), len(known)),
                        "mean_latency_ms": round(statistics.mean(latencies), 3),
                        "p95_latency_ms": latencies[math.ceil(len(latencies) * 0.95) - 1],
                        "llm_answer_count": sum(c["answer_mode"] == "llm" for c in cases),
                        "questions": len(cases),
                    },
                    "cases": cases,
                }
        finally:
            app.DB_PATH = previous_db
    return report


def render_markdown(report):
    lines = ["# 实测评估报告", "", f"生成时间：{report['generated_at']}", "",
             f"回答模式：`{report['generation']}`；12 篇自编短文、24 个可回答问题、8 个库外问题。", "",
             "| 检索模式 | Recall@1 | Recall@3 | 证据引用准确率 | 可追溯率 | 正确拒答率 | 误拒率 | P95 ms |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for mode, result in report["modes"].items():
        m = result["metrics"]
        lines.append(f"| {mode} | {m['recall_at_1']:.1%} | {m['recall_at_3']:.1%} | "
                     f"{m['evidence_citation_accuracy']:.1%} | {m['citation_traceability']:.1%} | "
                     f"{m['correct_refusal_rate']:.1%} | {m['false_refusal_rate']:.1%} | {m['p95_latency_ms']:.2f} |")
    lines += ["", "证据引用准确率按人工标注来源与原句计算，**不等价于大模型全部主张的事实正确率**。",
              "这是开发集，不能宣称未见真实场景上的泛化能力。`results.json` 保存逐题输出供复查。", "",
              "## 混合检索逐题结果", "", "| 题号 | 类型 | 证据命中@3 | 拒答 | 支持引用/全部引用 | 模式 |",
              "|---|---|---|---|---|---|"]
    for case in report["modes"]["hybrid"]["cases"]:
        lines.append(f"| {case['id']} | {'可回答' if case['sources'] else '库外'} | "
                     f"{case['recall_at_3'] if case['sources'] else '不适用'} | {case['refused']} | "
                     f"{case['supported_citations']}/{case['citation_count']} | {case['answer_mode']} |")
    return "\n".join(lines) + "\n"


def failures(report, use_llm=False):
    m = report["modes"]["hybrid"]["metrics"]
    gates = [
        (m["recall_at_3"] >= 0.85, "Recall@3 < 0.85"),
        (m["evidence_citation_accuracy"] >= 0.60, "evidence citation accuracy < 0.60"),
        (m["citation_traceability"] == 1.0, "citation traceability != 1.0"),
        (m["correct_refusal_rate"] >= 0.875, "correct refusal < 0.875"),
        (m["false_refusal_rate"] <= 0.15, "false refusal > 0.15"),
    ]
    if use_llm:
        gates.append((m["llm_answer_count"] > 0, "no genuine llm answers; model integration not verified"))
    return [message for passed, message in gates if not passed]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "eval")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--llm", action="store_true", help="Use configured model; slower and never enabled by CI")
    args = parser.parse_args()
    report = evaluate(args.llm)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")
    for mode, result in report["modes"].items():
        print(mode, json.dumps(result["metrics"], ensure_ascii=False))
    problems = failures(report, args.llm)
    if args.check and problems:
        print("FAIL: " + "; ".join(problems), file=sys.stderr)
        return 1
    print("PASS: evaluation gates" if not problems else "REPORT ONLY: " + "; ".join(problems))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
