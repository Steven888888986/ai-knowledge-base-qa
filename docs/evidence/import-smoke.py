"""Reproduce PDF bytes + public official webpage ingestion against an isolated DB."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ["KBQA_LLM_ENABLED"] = "0"
os.environ["KBQA_EMBEDDINGS_ENABLED"] = "0"

import app
from ingestion import parse_document
from pypdf import PdfWriter, __version__ as pypdf_version
from pypdf.generic import DictionaryObject, DecodedStreamObject, NameObject
from server import Handler, Server


def pdf_bytes():
    writer = PdfWriter()
    page_texts = [
        "RAG retrieves relevant evidence before generating an answer. Citations identify the source document.",
        "LoRA freezes the pretrained model weights and learns low-rank matrices. This reduces trainable parameters.",
    ]
    font = writer._add_object(DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")}))
    for sentence in page_texts:
        page = writer.add_blank_page(width=900, height=200)
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 10 Tf 30 100 Td ({sentence}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def run():
    evidence_dir = Path(__file__).resolve().parent
    record = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "command": "py -3 docs/evidence/import-smoke.py", "pypdf_version": pypdf_version, "llm_enabled": False, "embeddings_enabled": False, "checks": {}}
    original_database = app.DB_PATH
    with tempfile.TemporaryDirectory(prefix="kbqa-import-smoke-") as temporary:
        app.DB_PATH = Path(temporary) / "isolated.sqlite3"
        record["isolated_database"] = str(app.DB_PATH)
        httpd = Server(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=httpd.serve_forever, daemon=True)
        worker.start()
        base_url = f"http://127.0.0.1:{httpd.server_address[1]}"

        def request(path, payload=None):
            body = json.dumps(payload).encode("utf-8") if payload is not None else None
            req = urllib.request.Request(base_url + path, body, {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as response:
                return {"http_status": response.status, "body": json.loads(response.read())}

        try:
            record["health"] = request("/api/health")
            raw_pdf = pdf_bytes()
            parsed = parse_document("acceptance-two-pages.pdf", raw_pdf)
            record["pdf"] = {"byte_length": len(raw_pdf), "sha256": hashlib.sha256(raw_pdf).hexdigest(), "parsed_pages": parsed}
            assert raw_pdf.startswith(b"%PDF-")
            assert [number for number, text in parsed] == [1, 2]
            assert "LoRA freezes" in parsed[1][1]
            record["checks"]["real_pdf_bytes_parsed"] = True
            record["pdf"]["upload"] = request("/api/upload", {"filename": "acceptance-two-pages.pdf", "content_base64": base64.b64encode(raw_pdf).decode("ascii")})
            assert record["pdf"]["upload"]["http_status"] == 201
            record["pdf"]["question"] = "What does LoRA freeze?"
            record["pdf"]["query"] = request("/api/query", {"question": record["pdf"]["question"], "retrieval_mode": "bm25", "limit": 3})
            pdf_answer = record["pdf"]["query"]["body"]
            assert not pdf_answer["refused"]
            assert pdf_answer["mode"] == "offline"
            assert any(c["source"] == "upload://acceptance-two-pages.pdf" and c["page"] == 2 and "LoRA freezes" in c["snippet"] for c in pdf_answer["citations"])
            record["checks"]["pdf_citation_page_2_and_upload_source"] = True

            url = "https://docs.pytorch.org/tutorials/beginner/basics/intro.html"
            record["web"] = {"requested_url": url, "publisher": "Official PyTorch documentation", "import": request("/api/import-url", {"url": url})}
            assert record["web"]["import"]["http_status"] == 201
            source = record["web"]["import"]["body"]["source"]
            record["web"]["question"] = "What is the FashionMNIST dataset?"
            record["web"]["query"] = request("/api/query", {"question": record["web"]["question"], "retrieval_mode": "bm25", "limit": 3})
            web_answer = record["web"]["query"]["body"]
            assert not web_answer["refused"]
            assert web_answer["mode"] == "offline"
            assert any(c["source"] == source and c["page"] is None and "FashionMNIST" in c["snippet"] for c in web_answer["citations"])
            record["checks"]["public_official_webpage_imported"] = True
            record["checks"]["web_citation_exact_source_and_excerpt"] = True
            record["documents"] = request("/api/documents")
            for answer in (pdf_answer, web_answer):
                for citation in answer["citations"]:
                    document = request(f"/api/documents/{citation['document_id']}")["body"]
                    assert document["document"]["source"] == citation["source"]
                    assert any(chunk["chunk_id"] == citation["chunk_id"] and chunk["page"] == citation["page"] and citation["snippet"] == chunk["content"] for chunk in document["chunks"])
            record["checks"]["all_citations_match_stored_chunks_and_source"] = True
            record["result"] = "PASS"
        except Exception as error:
            record["result"] = "FAIL"
            record["error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=5)
            app.DB_PATH = original_database
            record["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
            output = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
            (evidence_dir / "import-smoke.json").write_text(output, encoding="utf-8")
            print(output)


if __name__ == "__main__":
    run()
