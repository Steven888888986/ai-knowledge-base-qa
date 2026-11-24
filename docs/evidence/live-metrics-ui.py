"""Automatic-metrics headless Edge E2E; isolated database, no production records.

Install optional runner: py -3 -m pip install --target .runtime/ui-test playwright
Run from repository root: py -3 docs/evidence/live-metrics-ui.py
Outputs use auto-metrics-*; earlier live-metrics-* evidence remains untouched.
The deliberately changed human verdicts test aggregation, not factual quality.
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
    snapshots = {}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel='msedge', headless=True)
        page = await browser.new_page(viewport={'width': 1440, 'height': 1100}, reduced_motion='reduce')
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(base)
        await expect(page.locator('#metrics-summary')).to_contain_text('累计 0 次问答')
        await expect(page.locator('#metric-recall')).to_have_text('—')
        await expect(page.locator('#metric-citations')).to_have_text('—')
        await expect(page.locator('#metric-refusal')).to_have_text('—')
        checks.append('no questions: all three cards show a dash, never invented percentages')

        async def expect_metrics(metrics):
            for selector, key in [('#metric-recall', 'recall'), ('#metric-citations', 'citation_accuracy'), ('#metric-refusal', 'refusal_rate')]:
                value = metrics[key]['value']
                if value is not None:
                    await expect(page.locator(selector)).to_have_text(f'{value * 100:.1f}%')
            await expect(page.locator('#metrics-summary')).to_contain_text(f"累计 {metrics['total_questions']} 次问答")

        async def save_review():
            async with page.expect_response(lambda response: '/api/history/' in response.url and response.url.endswith('/review') and response.request.method == 'POST') as pending:
                await page.locator('#save-review').click()
            response = await pending.value
            assert response.ok
            data = await response.json()
            await expect(page.locator('#review-dialog')).not_to_be_visible()
            await expect_metrics(data['metrics'])
            return data['metrics']

        async def set_citations(verdict):
            selects = await page.locator('#review-citations select').all()
            assert selects
            for select in selects:
                await select.select_option(verdict)

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
        assert first['auto_review']['answerable'] is True
        assert first['metrics']['recall']['value'] is not None
        assert first['metrics']['citation_accuracy']['value'] is not None
        assert first['metrics']['rule_evaluated_questions'] == 1
        assert first['metrics']['reviewed_questions'] == 0
        await expect_metrics(first['metrics'])
        await expect(page.locator('.metrics-panel')).to_contain_text('自动估算')
        await expect(page.locator('#metrics-summary')).to_contain_text('规则估算 1 次')
        snapshots['after_first_automatic_answer'] = first['metrics']
        await page.screenshot(path=str(evidence / 'auto-metrics-after-question.png'), full_page=True)
        history = await (await page.request.get(base + '/api/history')).json()
        assert history['history'][0]['review'] is None
        assert history['history'][0]['auto_review'] == first['auto_review']
        checks.append('offline RAG answer immediately provides explicitly labelled automatic recall and citation estimates without a human review')

        second = await ask('今天上海的天气怎么样？')
        assert second['refused']
        assert second['auto_review']['answerable'] is False
        assert second['metrics']['refusal_rate']['value'] == .5
        assert second['metrics']['rule_evaluated_questions'] == 2
        assert second['metrics']['pending_questions'] == 0
        await expect_metrics(second['metrics'])
        snapshots['after_second_automatic_answer'] = second['metrics']
        checks.append('two HTTP questions are automatically assessed with both models disabled; refusal rate changes from 0% to 50%')

        await page.locator('#open-history').click()
        first_row = page.locator('.history-item').filter(has=page.get_by_role('heading', name='什么是 RAG？', exact=True)).last
        await first_row.get_by_role('button').click()
        await expect(page.locator('#review-auto')).to_be_visible()
        await expect(page.locator('#review-answerable')).to_have_value('')
        await page.locator('#review-answerable').select_option('yes')
        await page.locator('#save-review').click()
        await expect(page.locator('#review-status')).to_contain_text('请选择至少一个正确来源')
        gold_source = first['retrieval']['hits'][0]['source']
        for checkbox in await page.locator('#review-sources input').all():
            await checkbox.set_checked(await checkbox.input_value() == gold_source)
        await set_citations('incorrect')
        incorrect = await save_review()
        citation_count = len(first['citations'])
        assert incorrect['recall']['value'] == 1
        assert incorrect['citation_accuracy']['correct'] == 0
        assert incorrect['citation_accuracy']['total'] == citation_count
        assert incorrect['reviewed_questions'] == 1
        assert incorrect['total_questions'] == 2
        snapshots['after_human_incorrect_override'] = incorrect
        checks.append('automatic suggestions are separate from unfilled human review; missing source is rejected; human incorrect votes override automatic estimates to 0/N')

        await page.locator('#open-history').click()
        await first_row.get_by_role('button').click()
        await expect(page.locator('#review-citations select').first).to_have_value('incorrect')
        await set_citations('correct')
        corrected = await save_review()
        assert corrected['citation_accuracy']['correct'] == citation_count
        assert corrected['citation_accuracy']['total'] == citation_count
        assert corrected['reviewed_questions'] == 1
        assert corrected['total_questions'] == 2
        snapshots['after_human_correction'] = corrected
        checks.append('correcting human votes replaces 0/N with N/N; question and citation denominators do not grow')

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
        async with page.expect_event('requestfinished', predicate=lambda request: request.url.endswith('/api/metrics')):
            release.set()
            await asyncio.wait_for(delivered.wait(), 10)
        await page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => resolve()))')
        await expect_metrics(third['metrics'])
        assert third['metrics']['total_questions'] == 3
        assert third['metrics']['rule_evaluated_questions'] == 3
        await page.unroute('**/api/metrics', delayed_metrics)
        await page.locator('#review-current').click()
        await page.locator('#review-answerable').select_option('yes')
        await page.locator('#review-extra-sources').fill('test://source-not-retrieved')
        await set_citations('incorrect')
        mixed = await save_review()
        assert mixed['recall']['hits'] == 1 and mixed['recall']['total'] == 2
        assert mixed['citation_accuracy']['correct'] == citation_count
        assert mixed['citation_accuracy']['total'] == citation_count + len(third['citations'])
        assert mixed['refusal_rate']['value'] == 1 / 3
        snapshots['after_missed_source_override'] = mixed
        checks.append('late old GET cannot overwrite newer question metrics; a simulated missed-source label lowers recall to 1/2')

        await page.reload()
        await expect_metrics(mixed)
        persisted = await (await page.request.get(base + '/api/history')).json()
        assert len(persisted['history']) == 3
        assert all(item['auto_review'] is not None for item in persisted['history'])
        assert sum(item['review'] is not None for item in persisted['history']) == 2
        await page.screenshot(path=str(evidence / 'auto-metrics-desktop.png'), full_page=True)
        checks.append('page reload retains all 3 automatic assessments and 2 human overrides')

        await page.set_viewport_size({'width': 375, 'height': 812})
        assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        await page.screenshot(path=str(evidence / 'auto-metrics-mobile.png'), full_page=True)
        await page.locator('#open-history').click()
        await first_row.get_by_role('button').click()
        await expect(page.locator('#review-dialog')).to_be_visible()
        assert await page.locator('#review-dialog').evaluate('(element) => element.scrollWidth <= element.clientWidth')
        await page.screenshot(path=str(evidence / 'auto-metrics-review-mobile.png'))
        checks.append('375px viewport and review dialog have no horizontal overflow')

        review_captured = asyncio.Event()
        release_review = asyncio.Event()
        async def delayed_review(route):
            old = await route.fetch()
            review_captured.set()
            await release_review.wait()
            await route.fulfill(response=old)
        await page.route('**/api/history/*/review', delayed_review)
        await page.locator('#save-review').click()
        await asyncio.wait_for(review_captured.wait(), 10)
        await page.locator('[data-close="review-dialog"]').first.click()
        fourth = await ask('什么是 RAG？')
        assert fourth['metrics']['total_questions'] == 4
        await expect_metrics(fourth['metrics'])
        async with page.expect_response(lambda response: response.url.endswith('/api/metrics')) as refreshed:
            async with page.expect_event('requestfinished', predicate=lambda request: request.url.endswith('/review')):
                release_review.set()
        latest_response = await refreshed.value
        assert latest_response.ok
        latest = await latest_response.json()
        assert latest['total_questions'] == 4
        await expect_metrics(latest)
        await page.unroute('**/api/history/*/review', delayed_review)
        snapshots['after_late_review_response'] = latest
        checks.append('a delayed human-review POST response cannot replace the newer fourth-answer metrics; a fresh GET retains all 4 questions')

        assert not errors, errors
        state = await (await page.request.get(base + '/api/metrics')).json()
        report = {'passed': True, 'environment': 'headless Microsoft Edge; isolated SQLite; both models disabled',
                  'note': 'Automatic estimates use offline rules. Human verdicts are scripted test inputs, including intentionally incorrect/missing-source votes; these are not production quality scores. Desktop/mobile screenshots show the 3-question state before the final delayed-review regression adds question 4.',
                  'checks': checks, 'metric_snapshots': snapshots, 'final_metrics': state, 'page_errors': errors}
        (evidence / 'auto-metrics-ui.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
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
            # This aggregation regression deliberately uses one fixed AI document.
            # Multi-domain seed content is verified separately, not mixed into its denominators.
            with urllib.request.urlopen(base + '/api/documents') as response:
                documents = json.load(response)['documents']
            for document in documents:
                if document['source'] != 'data/sample.md':
                    request = urllib.request.Request(base + f"/api/documents/{document['id']}", method='DELETE')
                    with urllib.request.urlopen(request):
                        pass
            asyncio.run(verify(base))
        finally:
            process.terminate()
            process.wait(timeout=10)
