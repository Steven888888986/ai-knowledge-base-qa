"""Recheck numeric input on temporary seed data without overwriting baseline.

The checked-in numeric-lookup-repro.json records the pre-fix failure. To save a
new run explicitly: py -3 docs/evidence/numeric-lookup-repro.py --output PATH
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
os.environ["KBQA_LLM_ENABLED"] = "0"
os.environ["KBQA_EMBEDDINGS_ENABLED"] = "0"
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path)
args = parser.parse_args()

with tempfile.TemporaryDirectory(prefix="kbqa-numeric-repro-") as temporary:
    os.environ["KBQA_DB"] = str(Path(temporary) / "isolated.sqlite3")
    import app

    app.seed()
    connection = app.db()
    documents = [dict(row) for row in connection.execute(
        "SELECT id,title,source FROM documents WHERE instr(content, ?) > 0 ORDER BY id", ("2",)
    )]
    connection.close()
    response = app.answer("2")
    result = {
        "scope": "fresh bundled seed only; isolated temporary SQLite; no production history read",
        "input": "2",
        "matching_document_count": len(documents),
        "matching_documents": documents,
        "returned_citation_count": len(response["citations"]),
        "returned_citations": response["citations"],
        "retrieved_hit_count": len(response.get("retrieval", {}).get("hits", [])),
        "mode": response["mode"],
        "lookup": response.get("lookup"),
    }
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"matching_documents": len(documents), "returned_citations": len(response["citations"]),
                      "returned_lookup_documents": response.get("lookup", {}).get("matched_documents"), "mode": response["mode"]}))
