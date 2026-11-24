"""Optional headless Edge E2E; isolated database, no production QA records.

Install optional runner: py -3 -m pip install --target .runtime/ui-test playwright
Run from repository root: py -3 docs/evidence/live-metrics-ui.py
The deliberately changed human verdicts below test aggregation, not factual quality.
"""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.runtime/ui-test'))
from playwright.async_api import async_playwright, expect


async def verify(base):
    evidence = ROOT / 'docs/evidence'
    checks = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel='msedge', headless=True)
        page = await browser.new_page(viewport={'width': 1440, 'height': 1100}, reduced_motion='reduce')
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(base)
        await expect(page.locator('#metrics-summary')).to_contain_text('累计 0 次问答')
        await expect(page.locator('#metric-recall')).to_have_text('待核验')
        await expect(page.locator('#metric-citations')).to_have_text('待核验')
        await expect(page.locator('#metric-refusal')).to_have_text('—')
        checks.append('empty denominators display pending/dash, never invented percentages')

        async def ask(question):
            await page.locator('#question').fill(question)
            async with page.expect_response(lambda response: response.url.endswith('/api/query') and response.request.method == 'POST') as pending:
                await page.locator('#ask').click()
            response = await pending.value
            assert response.ok
            await expect(page.locator('#ask')).to_be_enabled()
            return await response.json()

        first = await ask('什么是 RAG？')
        assert not first['refused'] and first['citations']
        await expect(page.locator('#metric-refusal')).to_have_text('0.0%')
        await expect(page.locator('#metric-recall')).to_have_text('待核验')
        second = await ask('今天上海的天气怎么样？')
        assert second['refused']
        await expect(page.locator('#metric-refusal')).to_have_text('50.0%')
        checks.append('two actual HTTP questions update refusal rate from 0% to 50%; quality remains pending')

        await page.locator('#open-history').click()
        first_row = page.locator('.history-item').filter(has=page.get_by_role('heading', name='什么是 RAG？', exact=True)).last
        await first_row.get_by_role('button').click()
        await page.locator('#review-answerable').select_option('yes')
        await page.locator('#save-review').click()
        await expect(page.locator('#review-status')).to_contain_text('请选择至少一个正确来源')
        await page.locator('#review-sources input').first.check()
        await page.locator('#review-citations select').first.select_option('incorrect')
        await page.locator('#save-review').click()
        await expect(page.locator('#review-dialog')).not_to_be_visible()
        await expect(page.locator('#metric-recall')).to_have_text('100.0%')
        await expect(page.locator('#metric-citations')).to_have_text('0.0%')
        checks.append('missing gold source is rejected; submitted human incorrect citation produces 0/1')

        await page.locator('#open-history').click()
        await first_row.get_by_role('button').click()
        await expect(page.locator('#review-citations select').first).to_have_value('incorrect')
        await page.locator('#review-citations select').first.select_option('correct')
        await page.locator('#save-review').click()
        await expect(page.locator('#metric-citations')).to_have_text('100.0%')
        await expect(page.locator('#metric-citations-count')).to_contain_text('1 / 1')
        checks.append('editing an old verdict replaces it: 0/1 -> 1/1, without duplicate samples')

        captured = asyncio.Event()
        release = asyncio.Event()
        delivered = asyncio.Event()
        async def delayed_metrics(route):
            old = await route.fetch()
            captured.set()
            await release.wait()
            await route.fulfill(response=old)
            delivered.set()
        await page.route('**/api/metrics', delayed_metrics)
        await page.evaluate("window.dispatchEvent(new Event('focus'))")
        await asyncio.wait_for(captured.wait(), 10)
        third = await ask('什么是 RAG？')
        assert not third['refused']
        release.set()
        await asyncio.wait_for(delivered.wait(), 10)
        await expect(page.locator('#metric-refusal')).to_have_text('33.3%')
        await page.unroute('**/api/metrics', delayed_metrics)
        await page.locator('#review-current').click()
        await page.locator('#review-answerable').select_option('yes')
        await page.locator('#review-extra-sources').fill('test://source-not-retrieved')
        await page.locator('#review-citations select').first.select_option('incorrect')
        await page.locator('#save-review').click()
        await expect(page.locator('#metric-recall')).to_have_text('50.0%')
        await expect(page.locator('#metric-citations')).to_have_text('50.0%')
        await expect(page.locator('#metric-refusal')).to_have_text('33.3%')
        checks.append('late old GET cannot overwrite newer question metrics; a simulated missed-source label lowers recall to 1/2')

        await page.reload()
        await expect(page.locator('#metrics-summary')).to_contain_text('累计 3 次问答')
        await expect(page.locator('#metric-recall')).to_have_text('50.0%')
        await expect(page.locator('#metric-citations')).to_have_text('50.0%')
        await expect(page.locator('#metric-refusal')).to_have_text('33.3%')
        await page.screenshot(path=str(evidence / 'live-metrics-desktop.png'), full_page=True)
        checks.append('page reload retains 3 questions and saved human reviews')

        await page.set_viewport_size({'width': 375, 'height': 812})
        assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        await page.screenshot(path=str(evidence / 'live-metrics-mobile.png'), full_page=True)
        await page.locator('#open-history').click()
        await first_row.get_by_role('button').click()
        await expect(page.locator('#review-dialog')).to_be_visible()
        assert await page.locator('#review-dialog').evaluate('(element) => element.scrollWidth <= element.clientWidth')
        await page.screenshot(path=str(evidence / 'live-metrics-review-mobile.png'))
        checks.append('375px viewport and review dialog have no horizontal overflow')
        assert not errors, errors
        state = await (await page.request.get(base + '/api/metrics')).json()
        report = {'passed': True, 'environment': 'headless Microsoft Edge; isolated SQLite; both models disabled',
                  'note': 'Human verdicts are scripted test inputs, including intentionally incorrect/missing-source verdicts; not production quality scores.',
                  'checks': checks, 'final_metrics': state, 'page_errors': errors}
        (evidence / 'live-metrics-ui.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2))
        await browser.close()


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='kbqa-ui-metrics-') as temporary:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = dict(os.environ, KBQA_DB=str(Path(temporary) / 'ui.sqlite3'), KBQA_PORT=str(port),
                   KBQA_LLM_ENABLED='0', KBQA_EMBEDDINGS_ENABLED='0')
        process = subprocess.Popen([sys.executable, 'server.py'], cwd=ROOT, env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        base = f'http://127.0.0.1:{port}'
        try:
            for attempt in range(50):
                try:
                    with urllib.request.urlopen(base + '/api/health', timeout=1):
                        break
                except OSError:
                    time.sleep(.1)
            asyncio.run(verify(base))
        finally:
            process.terminate()
            process.wait(timeout=10)
