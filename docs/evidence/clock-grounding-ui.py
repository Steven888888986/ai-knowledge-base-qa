"""Calendar grounding acceptance with real Qwen, temporary SQLite and headless Edge.

Run: py -3 docs/evidence/clock-grounding-ui.py
The final cross-year case fixes only the clock; model output is never mocked.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import traceback
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence"
sys.path[:0] = [str(ROOT), str(ROOT / ".runtime/ui-test")]
BEIJING = timezone(timedelta(hours=8), "Asia/Shanghai")
report = {"actual_model_used": True, "model_output_mocked": False,
          "production_database_accessed": False, "checks": []}


def checked(name, detail=None):
    report["checks"].append({"name": name, "passed": True, "detail": detail})


async def verify(base, metrics):
    from playwright.async_api import async_playwright, expect

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="msedge", headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 1100}, reduced_motion="reduce")
        page.set_default_timeout(240000)
        report["browser"] = {"name": "Microsoft Edge", "version": browser.version, "headless": True}
        errors, general_requests = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: general_requests.append(request.url) if request.url.endswith("/api/generate") else None)
        await page.goto(base)
        await expect(page.locator("#metrics-summary")).to_contain_text("累计 0 次问答")

        async def ask(question):
            await page.locator("#question").fill(question)
            async with page.expect_response(lambda response: response.url.endswith("/api/query")) as pending:
                await page.locator("#ask").click()
            response = await pending.value
            assert response.ok
            await expect(page.locator("#ask")).to_be_enabled()
            return await response.json()

        async def generate():
            async with page.expect_response(lambda response: response.url.endswith("/api/generate")) as pending:
                await page.locator("#generation-yes").click()
            response = await pending.value
            assert response.ok
            data = await response.json()
            await expect(page.locator("#generation-answer")).to_have_text(data["answer"])
            return data

        supported = await ask("什么是 RAG？")
        assert not supported["refused"] and supported["citations"]
        await expect(page.locator("#generation-dialog")).to_be_hidden()
        checked("grounded question answers normally without general-generation prompt")

        refused = await ask("今天星期几")
        assert refused["refused"] and refused["citations"] == []
        await expect(page.locator("#generation-dialog")).to_be_visible()
        await expect(page.locator("#metric-refusal")).to_have_text("50.0%")
        assert metrics.summary()["refusal_rate"] == {"value": 0.5, "refused": 1, "total": 2}
        before_history, before_metrics = metrics.history(), metrics.summary()
        now = datetime.now(BEIJING)
        generated = await generate()
        expected_weekday = "一二三四五六日"[now.weekday()]
        assert re.search(r"(?:星期|周|礼拜)" + expected_weekday, generated["answer"]), generated
        assert generated["mode"] == "llm-general" and generated["citations"] == []
        assert metrics.history() == before_history and metrics.summary() == before_metrics
        await expect(page.locator("#answer-mode")).to_have_text("缺少证据")
        await expect(page.locator("#citations details")).to_have_count(0)
        await page.locator("#generation-status").focus()
        await page.screenshot(path=str(EVIDENCE / "clock-grounding-result.png"), full_page=True)
        report["current_clock_case"] = {"clock_source": "actual system clock", "beijing_now": now.isoformat(),
                                        "expected_weekday": "星期" + expected_weekday,
                                        "refused": refused, "generated": generated}
        checked("actual clock weekday generated after consent; original refusal and all metrics preserved")

        await ask("今天星期几")
        before_history, before_metrics = metrics.history(), metrics.summary()
        calls_before = len(general_requests)
        await page.locator("#generation-no").click()
        await expect(page.locator("#generation-dialog")).to_be_hidden()
        await expect(page.locator("#question")).to_be_focused()
        await page.wait_for_load_state("networkidle")
        assert len(general_requests) == calls_before
        assert metrics.history() == before_history and metrics.summary() == before_metrics
        checked("No dismisses the prompt without generation or statistics changes")

        await ask("1+1")
        before_history, before_metrics = metrics.history(), metrics.summary()
        arithmetic = await generate()
        assert "2" in arithmetic["answer"] and not re.search(r"日期|星期|\d{4}年", arithmetic["answer"]), arithmetic
        assert arithmetic["citations"] == []
        assert metrics.history() == before_history and metrics.summary() == before_metrics
        report["non_calendar_case"] = arithmetic
        checked("ordinary arithmetic still returns 2 rather than an irrelevant calendar answer")
        assert not errors, errors
        report["javascript_errors"] = errors
        report["general_http_requests"] = len(general_requests)
        report["final_metrics"] = metrics.summary()
        checked("no browser JavaScript errors")
        await browser.close()


def main():
    with tempfile.TemporaryDirectory(prefix="kbqa-calendar-ui-") as temporary:
        os.environ.update(KBQA_DB=str(Path(temporary) / "isolated.sqlite3"), KBQA_LLM_ENABLED="1", KBQA_EMBEDDINGS_ENABLED="1")
        import app
        import metrics
        import server

        report["model"] = app.model_status()
        assert report["model"]["available"], "Start the configured model before running this acceptance"
        app.index_document("RAG 测试资料", "fixture://rag", "RAG 是检索增强生成。先检索与问题有关的资料，再将资料作为上下文交给模型生成回答。")
        with server.Server(("127.0.0.1", 0), server.Handler) as service:
            worker = threading.Thread(target=service.serve_forever, daemon=True)
            worker.start()
            try:
                asyncio.run(verify(f"http://127.0.0.1:{service.server_port}", metrics))
                fixed = datetime(2026, 12, 31, 16, 0, tzinfo=timezone.utc)
                with patch.object(app, "datetime") as clock:
                    clock.now.side_effect = lambda zone: fixed.astimezone(zone)
                    result = app.generate("今天的日期和星期几？")
                assert re.search(r"2027[年/-]0?1[月/-]0?1", result["answer"]), result
                assert re.search(r"(?:星期|周|礼拜)五", result["answer"]), result
                report["cross_year_case"] = {"clock_source": "fixed test clock only; actual model output", "fixed_utc": fixed.isoformat(), "response": result}
                checked("real model uses supplied Beijing calendar across UTC midnight and year rollover")
                report["passed"] = True
            finally:
                service.shutdown()
                worker.join(timeout=3)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        report.update(passed=False, failure={"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()})
        raise
    finally:
        (EVIDENCE / "clock-grounding-ui.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"passed": report.get("passed"), "checks": len(report["checks"])}))
