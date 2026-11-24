"""Small, dependency-free knowledge-base QA service.

It uses SQLite FTS5 when available and a deterministic token-overlap fallback.
The fallback makes the demo useful offline while preserving source citations.
"""
from __future__ import annotations

import html
import json
import os
import re
import sqlite3
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
DB_PATH = Path(os.getenv("KBQA_DB", ROOT / "data" / "kb.sqlite3"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def db() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY, title TEXT, source TEXT UNIQUE, content TEXT NOT NULL)")
    c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(title, source, content, doc_id UNINDEXED, tokenize='unicode61')")
    c.commit()
    return c


def split_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    out, start = [], 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            cut = text.rfind("。", start, end)
            if cut > start + size // 2:
                end = cut + 1
        out.append(text[start:end].strip())
        if end == len(text):
            break
        start = max(end - overlap, start + 1)
    return out


def index_document(title: str, source: str, content: str) -> int:
    c = db()
    old = c.execute("SELECT id FROM documents WHERE source=?", (source,)).fetchone()
    if old:
        c.execute("DELETE FROM chunks WHERE doc_id=?", (old["id"],))
        c.execute("DELETE FROM documents WHERE id=?", (old["id"],))
    cur = c.execute("INSERT INTO documents(title,source,content) VALUES(?,?,?)", (title, source, content))
    doc_id = cur.lastrowid
    for chunk in split_text(content):
        c.execute("INSERT INTO chunks(title,source,content,doc_id) VALUES(?,?,?,?)", (title, source, chunk, doc_id))
    c.commit()
    c.close()
    return len(split_text(content))


def read_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader  # optional dependency
            return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        except ImportError as e:
            raise RuntimeError("PDF support needs optional dependency pypdf; run: pip install -r requirements.txt") from e
    raw = path.read_text(encoding="utf-8", errors="ignore")
    if suffix in {".html", ".htm"}:
        raw = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", raw, flags=re.I)
        raw = re.sub(r"<[^>]+>", " ", raw)
        raw = html.unescape(raw)
    return raw


def query(q: str, limit: int = 5) -> list[dict[str, Any]]:
    q = q.strip()
    if not q:
        return []
    c = db()
    ascii_terms = re.findall(r"[a-zA-Z0-9_]+", q.lower())
    han = "".join(re.findall(r"[\u4e00-\u9fff]", q))
    terms = ascii_terms + [han[i:i+2] for i in range(max(0, len(han) - 1))]
    rows = []
    try:
        safe = " OR ".join('"' + x.replace('"', '') + '"' for x in terms) or '""'
        rows = c.execute("SELECT title,source,content,rank FROM chunks WHERE chunks MATCH ? ORDER BY rank LIMIT ?", (safe, limit)).fetchall()
    except sqlite3.OperationalError:
        pass
    if not rows:
        rows = c.execute("SELECT title,source,content,0 AS rank FROM chunks").fetchall()
        def score(r):
            low = r["content"].lower()
            return sum(low.count(t) for t in terms if len(t) > 1)
        scored = sorted(((score(r), r) for r in rows), key=lambda x: x[0], reverse=True)
        rows = [r for n, r in scored if n > 0][:limit]
    c.close()
    return [dict(r) for r in rows]


def answer(q: str, limit: int = 5) -> dict[str, Any]:
    hits = query(q, limit)
    if not hits:
        return {"answer": "知识库中没有找到足够证据。请先导入资料，或换一种问法。", "citations": [], "mode": "offline"}
    snippets = [h["content"] for h in hits]
    cited = [{"title": h["title"], "source": h["source"], "snippet": h["content"][:260]} for h in hits]
    api_url = os.getenv("OPENAI_BASE_URL")
    api_key = os.getenv("OPENAI_API_KEY")
    if api_url and api_key:
        try:
            payload = {"model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"), "messages": [{"role": "system", "content": "仅根据给定资料回答，并在句末用[1]等引用。资料：" + "\n".join(f"[{i+1}] {s}" for i, s in enumerate(snippets))}, {"role": "user", "content": q}], "temperature": 0.1}
            req = urllib.request.Request(api_url.rstrip("/") + "/chat/completions", json.dumps(payload).encode(), {"Content-Type": "application/json", "Authorization": "Bearer " + api_key})
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read())
            return {"answer": data["choices"][0]["message"]["content"], "citations": cited, "mode": "llm"}
        except Exception:
            pass
    return {"answer": "根据知识库检索到的相关资料：\n\n" + "\n\n".join(f"[{i+1}] {s}" for i, s in enumerate(snippets)), "citations": cited, "mode": "offline"}


def seed() -> None:
    if not db().execute("SELECT 1 FROM documents LIMIT 1").fetchone():
        index_document("学习资料示例", "data/sample.md", (ROOT / "data" / "sample.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    seed()
    print(json.dumps(answer("什么是检索增强生成？"), ensure_ascii=False, indent=2))
