"""Consent-based general generation: isolated HTTP and headless Edge acceptance.

Run: py -3 docs/evidence/generation-fallback-ui.py
Uses temporary SQLite and a controlled OpenAI-compatible HTTP fixture. Outputs
from that fixture are synthetic, not evidence of actual model quality. The real
model smoke test is recorded separately. Never reads production query history.
"""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence"
sys.path[:0] = [str(ROOT), str(ROOT / ".runtime/ui-test")]
report = {"scope": "temporary SQLite; controlled model HTTP fixture; headless Edge",
          "production_database_accessed": False, "actual_model_used": False,
          "human_reviews_submitted": 0, "checks": []}


def checked(name, detail=None):
    report["checks"].append({"name": name, "passed": True, "detail": detail})


def http(base, path, payload=None):
    request = Request(base + path, data=json.dumps(payload).encode() if payload is not None else None,
                      headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=15) as response:
            return response.status, json.load(response)
    except HTTPError as response:
        return response.code, json.load(response)


class ModelFixture(BaseHTTPRequestHandler):
    general_calls = []
    action = "success"
    entered = threading.Event()
    release = threading.Event()

    def reply(self, body, status=200):
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        self.reply({"data": [{"id": "fixture-model"}]})

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        user = payload["messages"][-1]["content"]
        if payload.get("response_format"):
            evaluation = json.loads(user)
            relevant = "RAG" in evaluation["question"]
            sources = [row["source"] for row in evaluation["evidence"] if "RAG" in row["text"]]
            output = json.dumps({"answerable": relevant and bool(sources),
                                 "expected_sources": sources[:1] if relevant else [],
                                 "citation_verdicts": {row["id"]: relevant for row in evaluation["citations"]},
                                 "reason": "受控验收服务的合成评估，不代表真实模型判断。"}, ensure_ascii=False)
        elif user.startswith("<evidence>"):
            output = "RAG 先检索证据，再根据证据生成回答。[1]"
        else:
            self.general_calls.append(payload)
            action = self.action
            self.entered.set()
            if action == "hold":
                self.release.wait(15)
            if action == "error":
                self.reply({"error": "controlled model unavailable"}, 503)
                return
            output = ('<img src=x onerror="window.generationXss=1">\n'
                      '<script>window.generationXss=1</script>\n仅为纯文本验收 [1]') if action == "xss" else "1 + 1 = 2。这是受控验收模型的示例输出。"
        self.reply({"choices": [{"message": {"content": output}}]})

    def log_message(self, *args):
        pass


async def verify(base):
    from playwright.async_api import async_playwright, expect

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="msedge", headless=True)
        report["browser"] = {"name": "Microsoft Edge", "version": browser.version, "headless": True}
        page = await browser.new_page(viewport={"width": 1440, "height": 1100}, reduced_motion="reduce")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(base)
        await expect(page.locator("#metrics-summary")).to_contain_text("累计 0 次问答")
        dialog = page.locator("#generation-dialog")

        async def ask(question):
            await page.locator("#question").fill(question)
            async with page.expect_response(lambda response: response.url.endswith("/api/query") and response.request.method == "POST") as pending:
                await page.locator("#ask").click()
            response = await pending.value
            assert response.ok
            await expect(page.locator("#ask")).to_be_enabled()
            return await response.json()

        def snapshot():
            return {"metrics": http(base, "/api/metrics")[1], "history": http(base, "/api/history")[1]}

        async def no_overflow(name):
            bounds = await page.evaluate("() => ({viewport: innerWidth, page: document.documentElement.scrollWidth, body: document.body.scrollWidth})")
            assert bounds["page"] <= bounds["viewport"] and bounds["body"] <= bounds["viewport"], bounds
            if await dialog.is_visible():
                dimensions = await dialog.evaluate("node => ({width: node.clientWidth, content: node.scrollWidth, height: node.clientHeight, contentHeight: node.scrollHeight, top: node.getBoundingClientRect().top, bottom: node.getBoundingClientRect().bottom})")
                assert dimensions["content"] <= dimensions["width"] and dimensions["top"] >= 0
                bounds["dialog"] = dimensions
            checked(name, bounds)

        known = await ask("什么是 RAG？")
        assert not known["refused"] and known["citations"] and known["mode"] == "llm"
        await expect(dialog).not_to_be_visible()
        await expect(page.locator("#generation-card")).not_to_be_visible()
        assert not ModelFixture.general_calls
        checked("supported QA uses grounded generation and citations without offering general generation")

        absent = await ask("1+1")
        assert absent["refused"] and not absent["citations"]
        await expect(dialog).to_be_visible()
        await expect(page.locator("#metric-refusal")).to_have_text("50.0%")
        await expect(page.locator("#metric-refusal-count")).to_contain_text("1 / 2")
        await expect(page.locator("#generation-question")).to_contain_text("1+1")
        await expect(page.locator("#generation-no")).to_be_focused()
        assert not ModelFixture.general_calls
        before = snapshot()
        await no_overflow("1440 confirmation dialog fits viewport")
        await page.screenshot(path=str(EVIDENCE / "generation-fallback-dialog-desktop.png"))
        focus_order = []
        for _ in range(5):
            await page.keyboard.press("Tab")
            focus = await page.evaluate("() => ({tag: document.activeElement.tagName, id: document.activeElement.id, inside: document.querySelector('#generation-dialog').contains(document.activeElement), modal: document.querySelector('#generation-dialog').matches(':modal')})")
            # Native dialogs can move focus to browser chrome (body reported),
            # but must not activate background page controls.
            assert focus["modal"] and (focus["inside"] or focus["tag"] == "BODY"), focus
            focus_order.append(focus)
        report["modal_tab_order"] = focus_order
        await page.locator("#generation-no").click()
        await expect(dialog).not_to_be_visible()
        await expect(page.locator("#question")).to_be_focused()
        assert not ModelFixture.general_calls and snapshot() == before
        checked("refusal is counted before consent; No closes dialog, restores focus and never generates")

        await ask("1+1")
        before = snapshot()
        await expect(dialog).to_be_visible()
        await page.keyboard.press("Escape")
        await expect(dialog).not_to_be_visible()
        assert not ModelFixture.general_calls and snapshot() == before
        checked("Escape cancels without generation or additional statistics")

        for action in ("close button", "backdrop"):
            await ask("1+1")
            before = snapshot()
            await expect(dialog).to_be_visible()
            if action == "close button":
                await page.locator('#generation-dialog button[aria-label="取消大模型生成"]').click()
            else:
                await page.mouse.click(5, 5)
            await expect(dialog).not_to_be_visible()
            assert not ModelFixture.general_calls and snapshot() == before
        checked("close button and backdrop both act as No without requesting generation")

        accepted = await ask("1+1")
        before = snapshot()
        ModelFixture.action = "hold"
        ModelFixture.entered.clear()
        ModelFixture.release.clear()
        async with page.expect_response(lambda response: response.url.endswith("/api/generate")) as pending:
            await page.locator("#generation-yes").click()
            assert await asyncio.to_thread(ModelFixture.entered.wait, 5)
            await page.locator("#generation-yes").dispatch_event("click")
            await expect(page.locator("#cancel-generation")).to_be_visible()
            await expect(page.locator("#generation-card")).to_have_attribute("aria-busy", "true")
            assert len(ModelFixture.general_calls) == 1
            ModelFixture.release.set()
        response = await pending.value
        generated = await response.json()
        assert response.ok and generated["query_id"] == accepted["query_id"]
        assert generated["mode"] == "llm-general" and generated["citations"] == []
        await expect(page.locator("#generation-answer")).to_contain_text("1 + 1 = 2")
        await expect(page.locator("#generation-meta")).to_contain_text("fixture-model")
        await expect(page.locator("#generation-card")).to_contain_text("知识库")
        await expect(page.locator("#answer-mode")).to_have_text("缺少证据")
        await expect(page.locator("#citations details")).to_have_count(0)
        assert snapshot() == before
        await no_overflow("1440 separate general result fits viewport")
        await page.evaluate("window.scrollTo(0, 0)")
        await page.screenshot(path=str(EVIDENCE / "generation-fallback-result-desktop.png"), full_page=True)
        await page.set_viewport_size({"width": 375, "height": 812})
        await no_overflow("375 general result fits viewport")
        await page.evaluate("window.scrollTo(0, 0)")
        await page.screenshot(path=str(EVIDENCE / "generation-fallback-result-mobile.png"), full_page=True)
        await page.set_viewport_size({"width": 1440, "height": 1100})
        checked("Yes performs one general model call; separate uncited result preserves original refusal, history and metrics")

        await page.locator("#review-current").click()
        await expect(page.locator("#review-answer")).to_contain_text("没有找到足够证据")
        await page.locator('[data-close="review-dialog"]').first.click()
        checked("manual review remains attached to the original knowledge-base refusal")

        lookup_before = snapshot()
        numeric = await ask("2")
        assert numeric["mode"] == "lookup" and numeric["query_id"] is None
        await expect(dialog).not_to_be_visible()
        await expect(page.locator("#generation-card")).not_to_be_visible()
        await expect(page.locator("#citations article.lookup-document")).to_have_count(2)
        assert snapshot() == lookup_before
        await ask("999999")
        await expect(dialog).not_to_be_visible()
        assert snapshot() == lookup_before
        checked("numeric match and zero-match lookup remain separate, clear old generation and never prompt or change statistics")

        await ask("1+1")
        before = snapshot()
        ModelFixture.action = "error"
        async with page.expect_response(lambda response: response.url.endswith("/api/generate")) as pending:
            await page.locator("#generation-yes").click()
        response = await pending.value
        assert response.status == 503
        await expect(page.locator("#generation-status")).to_contain_text("失败")
        await expect(page.locator("#retry-generation")).to_be_visible()
        assert snapshot() == before
        ModelFixture.action = "xss"
        async with page.expect_response(lambda response: response.url.endswith("/api/generate")) as pending:
            await page.locator("#retry-generation").click()
        assert (await pending.value).ok
        await expect(page.locator("#generation-answer")).to_contain_text('<img src=x onerror="window.generationXss=1">')
        assert await page.locator("#generation-answer img,#generation-answer script,#generation-answer button").count() == 0
        assert await page.evaluate("window.generationXss === undefined")
        assert snapshot() == before
        checked("model failure is explicit and retry succeeds without history changes; generated HTML and bracket numbers stay plain text")

        await page.set_viewport_size({"width": 375, "height": 812})
        await no_overflow("375 literal HTML-like output wraps without overflow")
        await ask("1+1")
        await expect(dialog).to_be_visible()
        await no_overflow("375 consent dialog fits viewport")
        await page.screenshot(path=str(EVIDENCE / "generation-fallback-dialog-mobile.png"))
        for selector in ("#generation-no", "#generation-yes"):
            box = await page.locator(selector).bounding_box()
            assert box["height"] >= 44 and box["width"] >= 44, box
        await page.set_viewport_size({"width": 812, "height": 375})
        await no_overflow("812 by 375 landscape dialog fits viewport")
        await page.keyboard.press("Escape")

        await page.set_viewport_size({"width": 1440, "height": 1100})
        await ask("1+1")
        before = snapshot()
        ModelFixture.action = "hold"
        ModelFixture.entered.clear()
        ModelFixture.release.clear()
        await page.locator("#generation-yes").click()
        assert await asyncio.to_thread(ModelFixture.entered.wait, 5)
        await page.locator("#cancel-generation").click()
        await expect(page.locator("#generation-status")).to_contain_text("停止")
        ModelFixture.release.set()
        await page.wait_for_load_state("networkidle")
        await expect(page.locator("#generation-answer")).not_to_contain_text("1 + 1 = 2")
        assert snapshot() == before
        checked("stopping a pending general response keeps the original QA and does not display its late result")

        ModelFixture.entered.clear()
        ModelFixture.release.clear()
        await page.locator("#retry-generation").click()
        assert await asyncio.to_thread(ModelFixture.entered.wait, 5)
        restored = await ask("什么是 RAG？")
        ModelFixture.release.set()
        await page.wait_for_load_state("networkidle")
        await expect(page.locator("#generation-card")).not_to_be_visible()
        await expect(dialog).not_to_be_visible()
        await expect(page.locator("#answer-mode")).to_have_text("本地模型 + 检索")
        assert not restored["refused"] and restored["citations"]
        checked("new knowledge-base question cancels pending general generation and restores normal cited results")

        status, rejected = http(base, "/api/generate", {"query_id": absent["query_id"], "confirmed": False})
        assert status == 400 and "error" in rejected
        status, rejected = http(base, "/api/generate", {"query_id": known["query_id"], "confirmed": True})
        assert status in (400, 409) and "error" in rejected
        status, rejected = http(base, "/api/generate", {"query_id": 999999, "confirmed": True})
        assert status == 404 and "error" in rejected
        checked("HTTP rejects missing consent, supported QA and nonexistent query ids")
        before = snapshot()
        count = len(ModelFixture.general_calls)
        os.environ["KBQA_LLM_ENABLED"] = "0"
        status, disabled = http(base, "/api/generate", {"query_id": absent["query_id"], "confirmed": True})
        os.environ["KBQA_LLM_ENABLED"] = "1"
        assert status == 503 and "关闭" in disabled["error"]
        assert len(ModelFixture.general_calls) == count and snapshot() == before
        checked("disabled generation returns an explicit service error without contacting the model or changing statistics")
        report["final_metrics"] = snapshot()["metrics"]
        report["general_model_calls"] = len(ModelFixture.general_calls)
        report["javascript_errors"] = errors
        assert not errors, errors
        checked("no browser JavaScript errors")
        await browser.close()


def main():
    with tempfile.TemporaryDirectory(prefix="kbqa-generation-fallback-") as temporary:
        model = ThreadingHTTPServer(("127.0.0.1", 0), ModelFixture)
        model.daemon_threads = True
        model_worker = threading.Thread(target=model.serve_forever, daemon=True)
        model_worker.start()
        os.environ.update(KBQA_DB=str(Path(temporary) / "isolated.sqlite3"), KBQA_LLM_ENABLED="1",
                          KBQA_EMBEDDINGS_ENABLED="0", OPENAI_MODEL="fixture-model",
                          OPENAI_BASE_URL=f"http://127.0.0.1:{model.server_address[1]}/v1")
        import app
        import server

        app.index_document("RAG 测试资料", "fixture://rag", "RAG 先检索证据，再根据证据生成回答。")
        app.index_document("数字甲", "fixture://number-a", "数字 2 出现在第一份资料。")
        app.index_document("数字乙", "fixture://number-b", "数字 2 也出现在第二份资料。")
        service = server.Server(("127.0.0.1", 0), server.Handler)
        worker = threading.Thread(target=service.serve_forever, daemon=True)
        worker.start()
        try:
            asyncio.run(verify(f"http://127.0.0.1:{service.server_address[1]}"))
            report["passed"] = True
        finally:
            ModelFixture.release.set()
            service.shutdown()
            service.server_close()
            model.shutdown()
            model.server_close()
            worker.join(timeout=3)
            model_worker.join(timeout=3)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        report.update(passed=False, failure={"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()})
        raise
    finally:
        (EVIDENCE / "generation-fallback-ui.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"passed": report.get("passed"), "checks": len(report["checks"])}))
