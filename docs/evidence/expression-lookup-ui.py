"""Expression grounding and expanded numeric passages: isolated HTTP + headless Edge.

Run: py -3 docs/evidence/expression-lookup-ui.py
Uses .runtime/ui-test/playwright, a temporary SQLite and no production history.
No human review is submitted. No visible application window is launched.
"""
import asyncio
from contextlib import ExitStack
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import traceback
from unittest.mock import patch
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence"
sys.path[:0] = [str(ROOT), str(ROOT / ".runtime/ui-test")]
os.environ["KBQA_LLM_ENABLED"] = "0"
os.environ["KBQA_EMBEDDINGS_ENABLED"] = "0"
report = {"scope": "temporary SQLite, seed and synthetic documents, isolated localhost, headless Microsoft Edge",
          "production_database_accessed": False, "human_reviews_submitted": 0, "checks": []}


def checked(name, detail=None):
    report["checks"].append({"name": name, "passed": True, "detail": detail})


def http(base, path, payload=None):
    request = Request(base + path, data=json.dumps(payload).encode() if payload is not None else None,
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def matches_in_database(app, term):
    connection = app.db()
    try:
        return [dict(row) for row in connection.execute(
            "SELECT id,title,source FROM documents WHERE instr(content,?)>0 ORDER BY id", (term,))]
    finally:
        connection.close()


def assert_lookup(response, term, rows):
    assert response["mode"] == "lookup" and response["refused"] is False and response["citations"] == []
    assert response["query_id"] is None and response["auto_review"] is None
    lookup = response["lookup"]
    assert lookup["term"] == term and lookup["matched_documents"] == len(rows)
    assert len(lookup["matches"]) == len(rows)
    assert {item["document_id"] for item in lookup["matches"]} == {row["id"] for row in rows}
    for match in lookup["matches"]:
        assert match["passages"]
        for passage in match["passages"]:
            assert term in passage["snippet"]
            assert {"snippet", "chunk_id", "page"} <= passage.keys()


def prepare(app):
    app.seed()
    for index in range(11):
        app.index_document(f"独立数字资料 {index}", f"fixture://expanded-{index}", "批次是 2024，容量为 12，各有 2 份。")
    app.index_pages("同文档三处匹配", "fixture://multiple", [
        (3, "首处标记：2。" + "甲" * 800 + "中间标记：12。"),
        (7, "乙" * 650 + "末处标记：2024。")])
    app.index_document("安全文本", "fixture://xss", '<img src=x onerror="window.expressionXss=1">2<script>window.expressionXss=1</script>')
    app.index_document("只有标题数字 2", "fixture://metadata-2", "正文没有阿拉伯数字。")


async def verify(base, app, auto_eval):
    from playwright.async_api import async_playwright, expect

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="msedge", headless=True)
        report["browser"] = {"name": "Microsoft Edge", "version": browser.version, "headless": True}
        page = await browser.new_page(viewport={"width": 1440, "height": 1100}, reduced_motion="reduce")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(base)
        await expect(page.locator("#metrics-summary")).to_contain_text("累计 0 次问答")

        async def ask(question):
            await page.locator("#question").fill(question)
            async with page.expect_response(lambda response: response.url.endswith("/api/query") and response.request.method == "POST") as pending:
                await page.locator("#ask").click()
            response = await pending.value
            assert response.ok
            await expect(page.locator("#ask")).to_be_enabled()
            return await response.json()

        async def no_overflow(name):
            sizes = await page.evaluate("() => ({viewport: innerWidth, page: document.documentElement.scrollWidth, body: document.body.scrollWidth})")
            assert sizes["page"] <= sizes["viewport"] and sizes["body"] <= sizes["viewport"], sizes
            checked(name, sizes)

        absent = await ask("1+1")
        assert absent["refused"] is True and absent["citations"] == [] and absent["mode"] == "refusal"
        await expect(page.locator("#citations details")).to_have_count(0)
        await expect(page.locator("#answer-mode")).to_have_text("缺少证据")
        await page.screenshot(path=str(EVIDENCE / "expression-lookup-refusal-desktop.png"), full_page=True)
        report["expression_without_evidence"] = absent
        checked("expression without matching evidence refuses with zero citations")

        http(base, "/api/ingest", {"title": "只有练习题", "source": "fixture://exercise", "content": "练习：计算1+1。"})
        exercise = await ask("1+1")
        assert exercise["refused"] is True and exercise["citations"] == []
        report["expression_mentioned_without_result"] = exercise
        checked("expression mentioned as an unsolved exercise still refuses with zero citations")

        http(base, "/api/ingest", {"title": "带结果的加法", "source": "fixture://addition", "content": "加法例题给出的结果是 1 + 1 = 2。"})
        supported = await ask("1+1")
        assert supported["refused"] is False and supported["citations"]
        assert {item["source"] for item in supported["citations"]} == {"fixture://addition"}
        assert supported["metrics"]["total_questions"] == 3
        report["expression_with_result"] = supported
        checked("expression with spaced complete equation cites only its actual source")
        await expect(page.locator("#review-current")).to_be_visible()

        rows = matches_in_database(app, "2")
        assert len(rows) > 8
        numeric_results = []
        with ExitStack() as stack:
            forbidden = [stack.enter_context(patch.object(module, name, side_effect=AssertionError(f"lookup called {name}")))
                         for module, name in ((app, "query"), (app, "embed_text"), (auto_eval, "evaluate"))]
            for question, limit, mode in [(" 2 ", 1, "vector"), ("2", 8, "hybrid"), ("2024", 5, "bm25")]:
                response = http(base, "/api/query", {"question": question, "limit": limit, "retrieval_mode": mode})
                assert_lookup(response, question.strip(), matches_in_database(app, question.strip()))
                assert response["metrics"] == supported["metrics"]
                numeric_results.append(response)
            assert all(mock.call_count == 0 for mock in forbidden)
        report["numeric_http"] = numeric_results
        checked("numeric HTTP lookup returns every body match independently of top-K, embeddings, LLM and evaluator")

        lookup = await ask("2")
        assert_lookup(lookup, "2", rows)
        assert lookup["metrics"] == supported["metrics"]
        await expect(page.locator(".evidence-panel")).to_be_hidden()
        await expect(page.locator("#lookup-results")).to_be_visible()
        await expect(page.locator("#answer-card #citations > article.lookup-document")).to_have_count(len(rows))
        await expect(page.locator("#citations details")).to_have_count(0)
        count_passages = sum(len(match["passages"]) for match in lookup["lookup"]["matches"])
        await expect(page.locator("#citations .lookup-passage")).to_have_count(count_passages)
        for passage in await page.locator("#citations .lookup-passage").all():
            await expect(passage).to_be_visible()
            assert await passage.locator("mark.lookup-match").count() > 0
        for row in rows:
            await expect(page.locator("#citations")).to_contain_text(row["title"])
            await expect(page.locator("#citations")).to_contain_text(row["source"])
        assert await page.locator("#lookup-results").evaluate("node => node.previousElementSibling.id === 'answer'")
        await expect(page.locator("#review-current")).to_be_hidden()
        await expect(page.locator("#review-current")).to_be_disabled()
        await page.locator("#review-current").dispatch_event("click")
        await expect(page.locator("#review-dialog")).not_to_be_visible()
        report["expanded_lookup"] = lookup
        checked("all document passages appear below answer without expanding a disclosure", {"documents": len(rows), "passages": count_passages})
        checked("lookup retains QA metrics and clears the earlier QA review target")

        multiple = page.locator("article.lookup-document").filter(has_text="同文档三处匹配")
        for marker in ("首处标记：2", "中间标记：12", "末处标记：2024"):
            await expect(multiple).to_contain_text(marker)
        final_passage = multiple.locator(".lookup-passage").filter(has_text="末处标记：2024").first
        await expect(final_passage).to_contain_text("第 7 页")
        await final_passage.locator(".source-button").click()
        await expect(page.locator("#source-title")).to_have_text("同文档三处匹配")
        await expect(page.locator("#source-content .focused-source")).to_contain_text("末处标记：2024")
        assert await page.locator("#source-content .focused-source mark").count() > 0
        await page.locator('[data-close="source-dialog"]').first.click()
        checked("distant matches in one document are all visible and each source button opens the right page/chunk")

        xss = page.locator("article.lookup-document").filter(has_text="安全文本")
        await expect(xss).to_contain_text('<img src=x onerror="window.expressionXss=1">')
        assert await xss.locator("img,script").count() == 0
        assert await page.evaluate("window.expressionXss === undefined")
        checked("XSS-like matching text stays literal, highlighted text")
        await no_overflow("1440 expanded lookup has no horizontal overflow")
        await page.screenshot(path=str(EVIDENCE / "expression-lookup-desktop.png"), full_page=True)
        await page.set_viewport_size({"width": 375, "height": 812})
        await no_overflow("375 expanded lookup has no horizontal overflow")
        await page.screenshot(path=str(EVIDENCE / "expression-lookup-mobile.png"), full_page=True)
        await final_passage.locator(".source-button").click()
        await expect(page.locator("#source-title")).to_have_text("同文档三处匹配")
        await no_overflow("375 source dialog has no horizontal overflow")
        await page.screenshot(path=str(EVIDENCE / "expression-lookup-source-mobile.png"))
        await page.locator('[data-close="source-dialog"]').first.click()

        empty = await ask("999999999999")
        assert_lookup(empty, "999999999999", [])
        assert empty["metrics"] == supported["metrics"]
        await expect(page.locator("#lookup-results .evidence-empty")).to_be_visible()
        await expect(page.locator(".evidence-panel")).to_be_hidden()
        await expect(page.locator("#answer-mode")).to_have_text("内容查找")
        await page.screenshot(path=str(EVIDENCE / "expression-lookup-empty-mobile.png"), full_page=True)
        checked("zero-result numeric lookup displays its empty state without adding a QA event")

        restored = await ask("什么是 RAG？")
        assert restored["mode"] != "lookup" and restored["citations"]
        assert restored["metrics"]["total_questions"] == 4
        await expect(page.locator("#answer-heading")).to_have_text("知识库回答")
        await expect(page.locator("#lookup-results")).to_be_hidden()
        await expect(page.locator(".evidence-panel")).to_be_visible()
        await expect(page.locator(".evidence-panel #evidence-heading")).to_have_text("引用证据")
        await expect(page.locator("#review-current")).to_be_visible()
        await expect(page.locator("#review-current")).to_be_enabled()
        await page.locator("#answer .citation-jump").first.click()
        await expect(page.locator(".evidence-panel #citations details").first).to_have_attribute("open", "")
        await no_overflow("375 restored QA has no horizontal overflow")
        await page.screenshot(path=str(EVIDENCE / "expression-lookup-restored-qa-mobile.png"), full_page=True)
        history = http(base, "/api/history")["history"]
        assert len(history) == 4 and all(item["review"] is None and item["response"]["mode"] != "lookup" for item in history)
        checked("ordinary QA restores the right citation panel, citation jump and QA counting")
        checked("isolated history contains four QA events and no human reviews or lookup events")
        report["final_metrics"] = restored["metrics"]
        report["javascript_errors"] = errors
        assert not errors, errors
        checked("no browser JavaScript errors")
        await browser.close()


def main():
    with tempfile.TemporaryDirectory(prefix="kbqa-expression-acceptance-") as temporary:
        os.environ["KBQA_DB"] = str(Path(temporary) / "isolated.sqlite3")
        import app
        import auto_eval
        import server

        prepare(app)
        enabled_results = []
        for content, should_refuse in [(None, True), ("练习：计算1+1。", True), ("结果：1 + 1 = 2。", False)]:
            if content is not None:
                app.index_document("模型启用时的算式核验", "fixture://model-enabled-expression", content)
            with patch.dict(os.environ, {"KBQA_LLM_ENABLED": "1", "KBQA_EMBEDDINGS_ENABLED": "1"}), \
                    patch.object(app.urllib.request, "urlopen", side_effect=AssertionError("expression used a model endpoint")) as network:
                response = app.answer("1+1")
                assert response["refused"] is should_refuse
                assert bool(response["citations"]) is not should_refuse
                assert network.call_count == 0
            enabled_results.append({"content": content, "response": response, "model_endpoint_calls": network.call_count})
        for document in app.list_documents():
            if document["source"] == "fixture://model-enabled-expression":
                app.delete_document(document["id"])
        report["models_enabled_expression_cases"] = enabled_results
        checked("pure expression grounding stays deterministic with generation and embeddings enabled; zero model endpoint calls")
        service = server.Server(("127.0.0.1", 0), server.Handler)
        worker = threading.Thread(target=service.serve_forever, daemon=True)
        worker.start()
        try:
            asyncio.run(verify(f"http://127.0.0.1:{service.server_address[1]}", app, auto_eval))
            report["passed"] = True
        finally:
            service.shutdown()
            service.server_close()
            worker.join(timeout=3)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        report.update(passed=False, failure={"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()})
        raise
    finally:
        (EVIDENCE / "expression-lookup-ui.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"passed": report.get("passed"), "checks": len(report["checks"])}))
