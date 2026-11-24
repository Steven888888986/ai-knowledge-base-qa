"""Independent numeric lookup acceptance using isolated SQLite and headless Edge.

Run: py -3 docs/evidence/numeric-lookup-ui.py
Optional runner: .runtime/ui-test/playwright. No production database or history
is opened. No human review is submitted. All browser windows remain headless.
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
LONG_TERM = "314159265358979323846264338327950288419716939937510" * 6
sys.path[:0] = [str(ROOT), str(ROOT / ".runtime/ui-test")]
os.environ["KBQA_LLM_ENABLED"] = "0"
os.environ["KBQA_EMBEDDINGS_ENABLED"] = "0"

report = {
    "scope": "temporary SQLite, bundled seed plus synthetic fixtures, localhost HTTP, headless Edge",
    "human_reviews_submitted": 0,
    "checks": [],
}


def checked(name, detail=None):
    report["checks"].append({"name": name, "detail": detail, "passed": True})


def http(base, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(base + path, data=data, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def expected(app, term):
    connection = app.db()
    try:
        return [dict(row) for row in connection.execute(
            "SELECT id,title,source,content FROM documents WHERE instr(content, ?) > 0 ORDER BY id", (term,)
        )]
    finally:
        connection.close()


def assert_lookup(response, term, rows):
    assert response["mode"] == "lookup", response
    assert response["refused"] is False and response["citations"] == []
    assert response["query_id"] is None and response["auto_review"] is None
    lookup = response["lookup"]
    assert lookup["term"] == term
    assert lookup["matched_documents"] == len(rows)
    assert len(lookup["matches"]) == len(rows)
    assert {item["document_id"] for item in lookup["matches"]} == {row["id"] for row in rows}
    assert {item["source"] for item in lookup["matches"]} == {row["source"] for row in rows}
    for item in lookup["matches"]:
        assert set(("title", "source", "snippet", "document_id", "chunk_id", "page")) <= item.keys()
        assert term in item["snippet"], item


def seed_synthetic(app):
    app.seed()
    for index in range(12):
        app.index_document(f"独立查找资料 {index:02d}", f"fixture://numeric-{index:02d}",
                           f"该资料的批次是 2024，容量为 12，各有 2 份；编号零值为 000。段落名称为样本 {index:02d}。")
    app.index_pages("长前缀命中", "fixture://late-hit", [(1, "此前页面只有文字。" * 100),
                   (7, "很长的前缀只有文字。" * 100 + "这里末尾首次出现 2，前面不含任何数字。")])
    app.index_document("安全文本片段", "fixture://xss", '<img src=x onerror="window.numericXss=1"> 2 <script>window.numericXss=1</script>')
    app.index_document("只有标题 2", "fixture://metadata-2", "正文不包含任何阿拉伯数字。")
    app.index_document("星槎协议阶段", "fixture://normal-question", "星槎协议有 2 个阶段。第一个阶段叫对齐，第二个阶段叫确认。星槎协议用于演示问答恢复。")
    app.index_document("跨片段长数字", "fixture://cross-chunk", "甲" * 200 + LONG_TERM + "乙" * 100)


async def browser_checks(base, rows):
    from playwright.async_api import async_playwright, expect

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="msedge", headless=True)
        report["browser"] = {"engine": "Microsoft Edge", "version": browser.version, "headless": True}
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
            sizes = await page.evaluate("""() => ({width: innerWidth, scroll: document.documentElement.scrollWidth,
                body: document.body.scrollWidth})""")
            assert sizes["scroll"] <= sizes["width"] and sizes["body"] <= sizes["width"], sizes
            checked(name, sizes)

        first = await ask("星槎协议有几个阶段？")
        assert first["mode"] != "lookup" and first["citations"] and first["query_id"] is not None
        assert first["metrics"]["total_questions"] == 1
        await expect(page.locator("#review-current")).to_be_visible()
        await expect(page.locator("#review-current")).to_be_enabled()
        checked("ordinary QA creates one reviewable QA event")

        await page.locator("#question").fill(" 2 ")
        await expect(page.locator("#ask-label")).to_have_text("查找内容")
        await expect(page.locator("#retrieval-mode")).to_be_disabled()
        lookup = await ask(" 2 ")
        assert_lookup(lookup, "2", rows)
        assert lookup["metrics"] == first["metrics"]
        await expect(page.locator("#answer-heading")).to_have_text("内容查找结果")
        await expect(page.locator("#answer-mode")).to_have_text("内容查找")
        await expect(page.locator("#evidence-heading")).to_have_text("匹配文档")
        await expect(page.locator("#citation-count")).to_have_text(str(len(rows)))
        await expect(page.locator("#citations details")).to_have_count(len(rows))
        listed = await page.locator("#citations .citation-title").all_text_contents()
        assert sorted(listed) == sorted(row["title"] for row in rows)
        await expect(page.locator("#review-current")).to_be_hidden()
        await expect(page.locator("#review-current")).to_be_disabled()
        await page.locator("#review-current").dispatch_event("click")
        await expect(page.locator("#review-dialog")).not_to_be_visible()
        await expect(page.locator("#metrics-summary")).to_contain_text("累计 1 次问答")
        report["ui_lookup"] = lookup
        checked("all matching document sources listed, including more than top-K", {"count": len(rows), "titles": listed})
        checked("lookup hides/disables stale review target and preserves QA metrics")

        late = page.locator("#citations details").filter(has=page.get_by_text("长前缀命中", exact=True))
        await late.locator("summary").click()
        await expect(late.locator(".citation-snippet mark")).to_have_count(1)
        await expect(late.locator(".citation-snippet mark")).to_have_text("2")
        await expect(late.locator(".citation-meta")).to_contain_text("第 7 页")
        await late.locator(".source-button").click()
        await expect(page.locator("#source-dialog")).to_be_visible()
        await expect(page.locator("#source-title")).to_have_text("长前缀命中")
        await expect(page.locator("#source-content .focused-source mark")).to_have_text("2")
        await no_overflow("1440 source dialog has no horizontal page overflow")
        await page.locator('[data-close="source-dialog"]').first.click()
        checked("late body match is visible in snippet, highlights digit, opens correct page/chunk")

        xss = page.locator("#citations details").filter(has=page.get_by_text("安全文本片段", exact=True))
        await xss.locator("summary").click()
        await expect(xss.locator(".citation-snippet")).to_contain_text('<img src=x onerror="window.numericXss=1">')
        assert await xss.locator(".citation-snippet img, .citation-snippet script").count() == 0
        assert await page.evaluate("window.numericXss === undefined")
        await xss.locator(".source-button").click()
        await expect(page.locator("#source-title")).to_have_text("安全文本片段")
        assert await page.locator("#source-content img, #source-content script").count() == 0
        await expect(page.locator("#source-content")).to_contain_text("<script>window.numericXss=1</script>")
        assert await page.evaluate("window.numericXss === undefined")
        await page.locator('[data-close="source-dialog"]').first.click()
        checked("XSS-looking snippets and full text render as literal text without DOM injection")
        await no_overflow("1440 lookup has no horizontal page overflow")
        await page.screenshot(path=str(EVIDENCE / "numeric-lookup-desktop.png"), full_page=True)

        await page.set_viewport_size({"width": 375, "height": 812})
        await no_overflow("375 lookup has no horizontal page overflow")
        await page.screenshot(path=str(EVIDENCE / "numeric-lookup-mobile.png"), full_page=True)
        await late.locator(".source-button").click()
        await expect(page.locator("#source-title")).to_have_text("长前缀命中")
        await no_overflow("375 source dialog has no horizontal page overflow")
        await page.screenshot(path=str(EVIDENCE / "numeric-lookup-source-mobile.png"), full_page=True)
        await page.locator('[data-close="source-dialog"]').first.click()

        empty = await ask("999999999999")
        assert_lookup(empty, "999999999999", [])
        assert empty["metrics"] == first["metrics"]
        await expect(page.locator("#citation-count")).to_have_text("0")
        await expect(page.locator("#citations details")).to_have_count(0)
        await expect(page.locator("#citations .evidence-empty")).to_be_visible()
        await expect(page.locator("#answer-mode")).to_have_text("内容查找")
        assert "拒答" not in await page.locator("#answer").inner_text()
        await page.screenshot(path=str(EVIDENCE / "numeric-lookup-empty-mobile.png"), full_page=True)
        checked("zero matches has lookup empty state, no refusal or QA metric increment")

        crossed = await ask(LONG_TERM)
        assert crossed["mode"] == "lookup" and crossed["lookup"]["matched_documents"] == 1
        assert crossed["lookup"]["matches"][0]["chunk_id"] is None
        cross_card = page.locator("#citations details").first
        await cross_card.locator("summary").click()
        await expect(cross_card.locator(".citation-snippet mark")).to_have_text(LONG_TERM)
        await cross_card.locator(".source-button").click()
        await expect(page.locator("#source-title")).to_have_text("跨片段长数字")
        await expect(page.locator("#source-content mark")).to_have_text(LONG_TERM)
        await no_overflow("375 long digit source has no horizontal page overflow")
        await page.locator('[data-close="source-dialog"]').first.click()
        checked("numeric term crossing chunks is found in full document and highlighted whole on opening")

        await page.locator("#question").fill("星槎协议有 2 个阶段吗？")
        await expect(page.locator("#retrieval-mode")).to_be_enabled()
        await expect(page.locator("#ask-label")).to_have_text("检索并回答")
        final = await ask("星槎协议有 2 个阶段吗？")
        assert final["mode"] != "lookup" and final["citations"] and final["query_id"] != first["query_id"]
        assert final["metrics"]["total_questions"] == 2
        assert final["metrics"]["reviewed_questions"] == 0
        await expect(page.locator("#answer-heading")).to_have_text("知识库回答")
        await expect(page.locator("#evidence-heading")).to_have_text("引用证据")
        await expect(page.locator("#review-current")).to_be_visible()
        await expect(page.locator("#review-current")).to_be_enabled()
        await expect(page.locator("#citations .citation-title").first).to_have_text(final["citations"][0]["title"])
        await page.locator("#answer .citation-jump").first.click()
        await expect(page.locator("#citations details").first).to_have_attribute("open", "")
        await no_overflow("375 restored QA has no horizontal page overflow")
        await page.screenshot(path=str(EVIDENCE / "numeric-lookup-restored-qa-mobile.png"), full_page=True)
        checked("complete question containing digits restores QA headings, cited source, citation jump, and QA count")
        history = http(base, "/api/history")["history"]
        assert len(history) == 2 and all(item["review"] is None for item in history)
        assert all(item["response"]["mode"] != "lookup" for item in history)
        checked("isolated history contains only two QA events and zero human reviews")
        report["final_metrics"] = final["metrics"]
        report["javascript_errors"] = errors
        assert not errors, errors
        checked("no browser JavaScript errors")
        await browser.close()


def main():
    with tempfile.TemporaryDirectory(prefix="kbqa-numeric-acceptance-") as temporary:
        os.environ["KBQA_DB"] = str(Path(temporary) / "acceptance.sqlite3")
        import app
        import auto_eval
        import server

        seed_synthetic(app)
        rows = expected(app, "2")
        assert len(rows) > 8
        report["fixture"] = {"matching_documents_for_2": len(rows), "database": "isolated temporary SQLite", "production_history_accessed": False}
        service = server.Server(("127.0.0.1", 0), server.Handler)
        worker = threading.Thread(target=service.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{service.server_address[1]}"
        try:
            original_metrics = http(base, "/api/metrics")
            api_results = []
            with ExitStack() as stack:
                forbidden = [stack.enter_context(patch.object(module, name, side_effect=AssertionError(f"lookup called {name}")))
                             for module, name in ((app, "query"), (app, "embed_text"), (auto_eval, "evaluate"))]
                for term, limit, mode in [(" 2 ", 1, "vector"), ("2", 8, "hybrid"), ("12", 5, "bm25"),
                                          ("2024", 5, "hybrid"), ("0", 5, "hybrid"), ("000", 5, "hybrid"),
                                          ("999999999999", 5, "hybrid"), (LONG_TERM, 1, "hybrid")]:
                    response = http(base, "/api/query", {"question": term, "limit": limit, "retrieval_mode": mode})
                    assert_lookup(response, term.strip(), expected(app, term.strip()))
                    assert response["metrics"] == original_metrics
                    api_results.append({"input": term, "limit": limit, "retrieval_mode": mode, "response": response})
                assert all(mock.call_count == 0 for mock in forbidden)
            report["api_results"] = api_results
            checked("HTTP lookup follows body substring semantics, trims ASCII digits, preserves leading zeros")
            checked("lookup independent of top-K and retrieval mode; retrieval, embeddings and evaluator never invoked")
            checked("HTTP numeric lookups do not alter QA metrics or create history")
            assert http(base, "/api/history")["history"] == []
            asyncio.run(browser_checks(base, rows))
            report["passed"] = True
        finally:
            service.shutdown()
            service.server_close()
            worker.join(timeout=3)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        report["passed"] = False
        report["failure"] = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
        raise
    finally:
        (EVIDENCE / "numeric-lookup-ui.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"passed": report.get("passed"), "checks": len(report["checks"])}, ensure_ascii=False))
