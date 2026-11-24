"""Check expression grounding in a temporary seeded database; never use real history.

Run with --output PATH to save this run without replacing historical evidence.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path)
args = parser.parse_args()
os.environ["KBQA_LLM_ENABLED"] = "0"
os.environ["KBQA_EMBEDDINGS_ENABLED"] = "0"
sys.path.insert(0, str(ROOT))

with tempfile.TemporaryDirectory(prefix="kbqa-expression-repro-") as temporary:
    os.environ["KBQA_DB"] = str(Path(temporary) / "isolated.sqlite3")
    import app
    from retrieval import terms

    app.seed()
    connection = app.db()
    rows = [dict(row) for row in connection.execute("SELECT id,title,source,content FROM documents ORDER BY id")]
    connection.close()
    matches = [row["source"] for row in rows if "1+1" in re.sub(r"\s+", "", row["content"])]
    response = app.answer("1+1")
    report = {"scope": "temporary SQLite, bundled seed, offline embeddings and generation; no real database or history read",
              "question": "1+1", "tokens": terms("1+1"), "exact_expression_sources": matches,
              "response": response}
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"exact_expression_sources": matches, "mode": response["mode"], "refused": response["refused"],
                      "citations": [{"title": item["title"], "source": item["source"]} for item in response["citations"]]}, ensure_ascii=False))
