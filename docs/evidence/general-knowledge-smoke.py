"""Cross-domain HTTP and UI smoke checks using isolated databases.

Requires running local Qwen/BGE and optional .runtime/ui-test playwright.
Run: py -3 docs/evidence/general-knowledge-smoke.py
The examples test integration and evidence routing, not exhaustive domain quality.
"""
import asyncio
from contextlib import contextmanager
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
EVIDENCE = ROOT / 'docs/evidence'
sys.path.insert(0, str(ROOT / '.runtime/ui-test'))
from playwright.async_api import async_playwright, expect

# Questions are fixed against the documented starter cards, not generated answers.
CASES = [
    ('天文', '地球为什么会出现四季？', 'example://general-astronomy-seasons.md', '倾斜'),
    ('经济', '什么是机会成本？', 'example://general-economics-opportunity-cost.md', '替代'),
    ('编程', 'Python 列表和元组有什么区别？', 'example://general-programming-python.md', '元组'),
    ('数学', '指数运算中 2 的三次方是多少？', 'example://general-math-exponents.md', '8'),
    ('统计', '均值和中位数有什么区别？', 'example://general-statistics-center.md', '中位数'),
    ('物理', '质量不变时，牛顿第二定律怎样联系合力和加速度？', 'example://general-physics-newton.md', '加速度'),
    ('生物', '光合作用利用哪些原料并释放什么气体？', 'example://general-biology-photosynthesis.md', '氧气'),
    ('食品安全', '食品安全五要点包括哪些？', 'example://general-life-food-safety.md', '清洁'),
]


def request(base, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    operation = urllib.request.Request(base + path, data=data,
                                      headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(operation, timeout=90) as response:
        return json.load(response)


@contextmanager
def service(models):
    with tempfile.TemporaryDirectory(prefix='kbqa-general-smoke-') as temporary:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = dict(os.environ, KBQA_DB=str(Path(temporary) / 'smoke.sqlite3'), KBQA_PORT=str(port),
                   KBQA_LLM_ENABLED='1' if models else '0', KBQA_EMBEDDINGS_ENABLED='1' if models else '0')
        process = subprocess.Popen([sys.executable, 'server.py'], cwd=ROOT, env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        base = f'http://127.0.0.1:{port}'
        try:
            for attempt in range(300):
                if process.poll() is not None:
                    raise RuntimeError('Temporary service exited during initialization')
                try:
                    health = request(base, '/api/health')
                    break
                except OSError:
                    time.sleep(.2)
            else:
                raise TimeoutError('Temporary service failed to start')
            yield base, health
        finally:
            process.terminate()
            process.wait(timeout=10)


def answer_case(base, case, models):
    domain, question, source, evidence_word = case
    result = request(base, '/api/query', {'question': question, 'retrieval_mode': 'hybrid'})
    assert not result['refused'], (domain, result)
    assert any(citation['source'] == source and evidence_word in citation['snippet']
               for citation in result['citations']), (domain, result)
    assert result['auto_review'] is not None
    assert result['metrics']['pending_questions'] == 0
    if models:
        assert result['mode'] == 'llm', (domain, result['mode'])
        assert result['auto_review']['method'] == 'local-model', (domain, result['auto_review'])
    else:
        assert result['mode'] == 'offline'
        assert result['auto_review']['method'] == 'lexical-fallback'
    return {'domain': domain, 'question': question, 'expected_source': source, 'response': result}


async def verify_ui(base, document_count):
    errors = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel='msedge', headless=True)
        page = await browser.new_page(viewport={'width': 1440, 'height': 1100}, reduced_motion='reduce')
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(base)
        title = await page.title()
        assert '通用' in title
        await expect(page.locator('#docs')).to_have_text(str(document_count))
        suggestions = await page.locator('.suggestions button').all_text_contents()
        assert suggestions[:3] == [case[1] for case in CASES[:3]]
        async with page.expect_response(lambda response: response.url.endswith('/api/query'), timeout=90000) as pending:
            await page.locator('.suggestions button').first.click()
        response = await pending.value
        assert response.ok
        answer = await response.json()
        assert not answer['refused'] and answer['mode'] == 'llm'
        assert any(citation['source'] == CASES[0][2] for citation in answer['citations'])
        await expect(page.locator('#ask')).to_be_enabled()
        for selector, key in [('#metric-recall', 'recall'), ('#metric-citations', 'citation_accuracy'),
                              ('#metric-refusal', 'refusal_rate')]:
            value = answer['metrics'][key]['value']
            assert value is not None, (key, answer['metrics'])
            await expect(page.locator(selector)).to_have_text(f'{value * 100:.1f}%')
        await expect(page.locator('#metrics-summary')).to_contain_text(f"累计 {answer['metrics']['total_questions']} 次问答")
        assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        await page.screenshot(path=str(EVIDENCE / 'general-knowledge-desktop.png'))
        await page.set_viewport_size({'width': 375, 'height': 812})
        assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        await page.screenshot(path=str(EVIDENCE / 'general-knowledge-mobile.png'), full_page=True)
        assert not errors, errors
        await browser.close()
        return {'title': title, 'document_count': document_count, 'suggestions': suggestions,
                'question': CASES[0][1], 'metrics': answer['metrics'], 'page_errors': errors,
                'checks': ['desktop general-domain title and document list', 'real browser answer updates metrics',
                           '1440px and 375px layouts have no horizontal overflow']}


def main():
    assert len(CASES) >= 8, 'Configure at least eight documented domain questions'
    expected_documents = 1 + len(list((ROOT / 'data/knowledge').glob('*.md')))
    report = {'environment': 'isolated SQLite databases and localhost HTTP; no user records',
              'scope': 'Starter-card integration smoke checks; not exhaustive all-domain quality evaluation',
              'metric_validation_scope': 'Checks automatic assessment availability, aggregation and UI/API consistency; displayed percentages are model estimates, not independently verified quality scores.'}
    with service(False) as (base, health):
        report['offline_health'] = health
        report['offline_cases'] = [answer_case(base, case, False) for case in CASES]
        unknown = request(base, '/api/query', {'question': '我的银行卡密码是多少？'})
        assert unknown['refused'] and not unknown['citations']
        report['unknown_question'] = unknown
        report['offline_document_count'] = len(request(base, '/api/documents')['documents'])
        assert report['offline_document_count'] == expected_documents
    with service(True) as (base, health):
        assert health['model']['available'] and health['embedding_mode']['available'], health
        report['model_health'] = health
        report['model_cases'] = [answer_case(base, case, True) for case in CASES[:3]]
        report['existing_ai_regression'] = answer_case(
            base, ('AI', '什么是 RAG？', 'data/sample.md', 'RAG'), True)
        count = len(request(base, '/api/documents')['documents'])
        assert count == expected_documents
        report['ui'] = asyncio.run(verify_ui(base, count))
    report['passed'] = True
    (EVIDENCE / 'general-knowledge-smoke.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'offline_cases': len(report['offline_cases']),
                      'model_cases': len(report['model_cases']), 'existing_ai_regression': True,
                      'documents': count, 'ui': report['ui']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
