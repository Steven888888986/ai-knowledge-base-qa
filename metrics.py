"""Persistent live QA statistics; quality scores only use explicit human reviews."""
from __future__ import annotations

from datetime import datetime, timezone
import json

import app


def connection():
    database = app.db()
    database.execute("CREATE TABLE IF NOT EXISTS query_events (id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT NOT NULL, response TEXT NOT NULL, created_at TEXT NOT NULL, review TEXT)")
    return database


def record_query(question: str, response: dict) -> int:
    if not isinstance(question, str) or not question.strip() or len(question) > 2000:
        raise ValueError("问题不能为空，且不能超过 2000 字符")
    database = connection()
    try:
        with database:
            cursor = database.execute("INSERT INTO query_events(question,response,created_at) VALUES(?,?,?)",
                                      (question.strip(), json.dumps(response, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))
            return cursor.lastrowid
    finally:
        database.close()


def history() -> list[dict]:
    database = connection()
    try:
        rows = database.execute("SELECT * FROM query_events ORDER BY id DESC LIMIT 50").fetchall()
        return [{"id": row["id"], "question": row["question"], "created_at": row["created_at"],
                 "response": json.loads(row["response"]), "review": json.loads(row["review"]) if row["review"] else None} for row in rows]
    finally:
        database.close()


def save_review(query_id: int, review: dict) -> dict | None:
    database = connection()
    try:
        row = database.execute("SELECT response FROM query_events WHERE id=?", (query_id,)).fetchone()
        if row is None:
            return None
        if not isinstance(review, dict) or type(review.get("answerable")) is not bool:
            raise ValueError("answerable 必须为布尔值")
        sources = review.get("expected_sources")
        if not isinstance(sources, list) or len(sources) > 50 or any(not isinstance(source, str) or not source.strip() or len(source) > 2048 for source in sources):
            raise ValueError("expected_sources 应为最多 50 个非空来源，每项不超过 2048 字符")
        sources = [source.strip() for source in sources]
        if len(sources) != len(set(sources)):
            raise ValueError("标准来源不能重复")
        if review["answerable"] != bool(sources):
            raise ValueError("可回答的问题须指定标准来源；库外问题的标准来源须为空")
        verdicts = review.get("citation_verdicts", {})
        response = json.loads(row["response"])
        citation_ids = {str(citation["id"]) for citation in response.get("citations", [])}
        if not isinstance(verdicts, dict) or any(key not in citation_ids or type(value) is not bool for key, value in verdicts.items()):
            raise ValueError("引用核验只能包含本次回答的引用编号，且判断须为布尔值；待核验引用请省略")
        normalized = {"answerable": review["answerable"], "expected_sources": sources, "citation_verdicts": verdicts}
        with database:
            database.execute("UPDATE query_events SET review=? WHERE id=?", (json.dumps(normalized, ensure_ascii=False), query_id))
        return normalized
    finally:
        database.close()


def summary() -> dict:
    database = connection()
    try:
        rows = database.execute("SELECT response,review FROM query_events").fetchall()
    finally:
        database.close()
    refused = reviewed = recall_hits = recall_total = correct_citations = checked_citations = 0
    for row in rows:
        response = json.loads(row["response"])
        refused += bool(response.get("refused", response.get("mode") == "refusal"))
        if row["review"] is None:
            continue
        review = json.loads(row["review"])
        reviewed += 1
        if review["answerable"]:
            recall_total += 1
            retrieved = {hit["source"] for hit in response.get("retrieval", {}).get("hits", [])[:3]}
            recall_hits += bool(retrieved.intersection(review["expected_sources"]))
        votes = review["citation_verdicts"].values()
        correct_citations += sum(votes)
        checked_citations += len(review["citation_verdicts"])
    total = len(rows)
    return {"total_questions": total, "refused_questions": refused,
            "reviewed_questions": reviewed, "pending_questions": total - reviewed,
            "recall": {"value": recall_hits / recall_total if recall_total else None, "hits": recall_hits, "total": recall_total},
            "citation_accuracy": {"value": correct_citations / checked_citations if checked_citations else None, "correct": correct_citations, "total": checked_citations},
            "refusal_rate": {"value": refused / total if total else None, "refused": refused, "total": total}}
