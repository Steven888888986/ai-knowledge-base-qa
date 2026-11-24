(() => {
  const $ = selector => document.querySelector(selector);
  const records = new Map();
  let currentId = null;
  let editing = null;
  let opening = false;
  let saving = false;
  let metricsVersion = 0;
  const node = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };
  async function request(path, options) {
    const response = await fetch(path, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '请求失败，请重试。');
    return data;
  }
  const percent = (value, empty) => value == null ? empty : `${(value * 100).toFixed(1)}%`;
  function renderMetrics(data, message = '') {
    metricsVersion += 1;
    const empty = data.pending_questions ? '待评估' : data.total_questions ? '无样本' : '—';
    $('#metric-recall').textContent = percent(data.recall.value, empty);
    $('#metric-recall-count').textContent = data.recall.total ? `${data.recall.hits} / ${data.recall.total} 个可回答问题命中来源` : '暂无可回答样本';
    $('#metric-citations').textContent = percent(data.citation_accuracy.value, empty);
    $('#metric-citations-count').textContent = data.citation_accuracy.total ? `${data.citation_accuracy.correct} / ${data.citation_accuracy.total} 条引用判为正确` : '暂无引用样本';
    $('#metric-refusal').textContent = percent(data.refusal_rate.value, '—');
    $('#metric-refusal-count').textContent = `${data.refused_questions} / ${data.total_questions} 次完成问答`;
    $('#metrics-summary').textContent = `${message}累计 ${data.total_questions} 次问答 · 模型估算 ${data.model_evaluated_questions || 0} 次 · 规则估算 ${data.rule_evaluated_questions || 0} 次 · 人工核验 ${data.reviewed_questions} 次${data.pending_questions ? ` · 待评估 ${data.pending_questions} 次` : ''}`;
    $('#metrics-error').hidden = true;
  }
  async function refreshMetrics() {
    const version = ++metricsVersion;
    try {
      const data = await request('/api/metrics');
      if (version === metricsVersion) renderMetrics(data);
    }
    catch (error) {
      if (version !== metricsVersion) return;
      $('#metrics-error').textContent = `统计读取失败：${error.message}`;
      $('#metrics-error').hidden = false;
      $('#metrics-summary').textContent = '暂时无法更新统计';
    }
  }
  async function openHistory() {
    const dialog = $('#history-dialog');
    if (!dialog.open) dialog.showModal();
    $('#history-status').textContent = '正在读取问答记录…';
    $('#query-history').replaceChildren();
    try {
      const { history } = await request('/api/history');
      $('#history-status').textContent = history.length ? '选择一条记录查看原回答并核验。' : '还没有问答记录，先提出一个问题吧。';
      history.forEach(item => {
        records.set(item.id, item);
        const article = node('article', 'history-item');
        const content = node('div');
        content.append(node('h3', '', item.question));
        const time = new Date(item.created_at);
        const when = Number.isNaN(time.getTime()) ? item.created_at : time.toLocaleString('zh-CN', { hour12: false });
        const evaluation = item.review ? '已人工核验' : item.auto_review ? (item.auto_review.method === 'local-model' ? '模型自动估算' : '规则自动估算') : '待评估';
        content.append(node('p', '', `${when} · ${item.response.refused ? '已拒答' : '已回答'} · ${evaluation}`));
        const button = node('button', 'button secondary', item.review ? '查看并修改核验' : '查看并核验');
        button.type = 'button';
        button.addEventListener('click', () => openReview(item));
        article.append(content, button);
        $('#query-history').append(article);
      });
    } catch (error) { $('#history-status').textContent = `记录读取失败：${error.message}`; }
  }
  function setReviewStatus(message, error = false) {
    const status = $('#review-status');
    status.textContent = message;
    status.classList.toggle('error', error);
    if (error) status.focus();
  }
  function updateSourceVisibility() {
    const answerable = $('#review-answerable').value === 'yes';
    $('#review-sources-field').hidden = !answerable;
    $('#review-sources-field').disabled = !answerable;
  }
  async function openReview(item) {
    if (opening || saving) return;
    opening = true;
    try {
      // The complete library lets a reviewer choose a relevant source missed by retrieval.
      let documents = [];
      let libraryUnavailable = false;
      try { documents = (await request('/api/documents')).documents; }
      catch (_) { libraryUnavailable = true; }
      editing = item;
      $('#review-form').reset();
      $('#review-question').textContent = item.question;
      $('#review-answer').textContent = item.response.answer;
      const auto = item.auto_review;
      const scopeNames = { 'full-library': '全部知识片段', 'candidate-pool': '有限候选片段', 'saved-retrieval': '当次保存的检索片段' };
      $('#review-auto').textContent = auto ? `自动估算（${auto.method === 'local-model' ? '本地模型' : '词项规则回退'}）：${auto.answerable ? '有资料可回答' : '未找到足够资料'}。参考来源：${auto.expected_sources.join('、') || '无'}。评估范围：${scopeNames[auto.scope?.kind] || '已保存证据'}。${auto.reason || ''} 下方仅保存你明确提交的人工判断。` : '本次尚无自动评估，可在下方人工核验。';
      $('#review-answerable').value = item.review ? (item.review.answerable ? 'yes' : 'no') : '';
      setReviewStatus(libraryUnavailable ? '当前资料列表读取失败，仍可根据保存的片段核验或手动填写来源。' : '');
      const hits = item.response.retrieval?.hits || [];
      const hitList = $('#review-hits'); hitList.replaceChildren();
      hits.slice(0, 3).forEach((hit, index) => {
        const part = node('article', 'review-evidence');
        part.append(node('h3', '', `${index + 1}. ${hit.title || hit.source}`), node('p', 'review-source', hit.source), node('p', 'review-snippet', hit.content));
        hitList.append(part);
      });
      if (!hits.length) hitList.append(node('p', 'review-help', '当次未返回检索候选。'));
      const sources = new Map(documents.map(doc => [doc.source, doc.title]));
      for (const hit of hits) sources.set(hit.source, hit.title || hit.source);
      for (const citation of item.response.citations || []) sources.set(citation.source, citation.title || citation.source);
      for (const source of auto?.expected_sources || []) if (!sources.has(source)) sources.set(source, source);
      for (const source of item.review?.expected_sources || []) if (!sources.has(source)) sources.set(source, source);
      const sourceList = $('#review-sources'); sourceList.replaceChildren();
      for (const [source, title] of sources) {
        const label = node('label', 'review-source-option');
        const checkbox = node('input'); checkbox.type = 'checkbox'; checkbox.value = source;
        checkbox.checked = (item.review?.expected_sources || []).includes(source);
        const text = node('span'); text.append(node('strong', '', title), node('small', '', source));
        label.append(checkbox, text); sourceList.append(label);
      }
      if (!sources.size) sourceList.append(node('p', 'review-help', '没有可列出的来源，可在下方手动填写。'));
      updateSourceVisibility();
      const citations = $('#review-citations'); citations.replaceChildren();
      for (const citation of item.response.citations || []) {
        const article = node('article', 'review-evidence');
        article.append(node('h3', '', `[${citation.id}] ${citation.title || citation.source}`));
        article.append(node('p', 'review-source', `${citation.source}${citation.page ? ` · 第 ${citation.page} 页` : ''}`));
        article.append(node('p', 'review-snippet', citation.snippet));
        const autoVerdict = auto?.citation_verdicts?.[String(citation.id)];
        article.append(node('p', 'review-help', autoVerdict == null ? '尚无自动判断' : `自动估算：${autoVerdict ? '正确' : '错误'}，可在下方修正。`));
        const label = node('label', 'form-label', `引用 [${citation.id}] 是否准确支持答案？`);
        const select = node('select'); select.id = `citation-verdict-${citation.id}`; select.dataset.citationId = String(citation.id); label.htmlFor = select.id;
        for (const [value, text] of [['', autoVerdict == null ? '暂不判断' : '保留自动估算'], ['correct', '正确：来源及原文支持对应回答'], ['incorrect', '错误：来源不符或不支持对应回答']]) {
          const option = node('option', '', text); option.value = value; select.append(option);
        }
        const verdict = item.review?.citation_verdicts?.[String(citation.id)];
        select.value = verdict === true ? 'correct' : verdict === false ? 'incorrect' : '';
        article.append(label, select); citations.append(article);
      }
      if (!item.response.citations?.length) citations.append(node('p', 'review-help', '本次没有引用，不纳入引用准确率的分母。'));
      $('#history-dialog').close();
      $('#review-dialog').showModal();
    } finally { opening = false; }
  }
  $('#open-history').addEventListener('click', openHistory);
  $('#review-current').addEventListener('click', () => {
    const item = records.get(currentId);
    if (item) openReview(item);
  });
  $('#review-answerable').addEventListener('change', updateSourceVisibility);
  $('#review-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (!editing) return;
    const item = editing;
    const answerable = $('#review-answerable').value === 'yes';
    const expectedSources = answerable ? [...new Set([
      ...Array.from(document.querySelectorAll('#review-sources input:checked'), input => input.value),
      ...$('#review-extra-sources').value.split('\n').map(line => line.trim()).filter(Boolean)
    ])] : [];
    if (answerable && !expectedSources.length) { setReviewStatus('请选择至少一个正确来源，或在输入框中填写未列出的来源。', true); return; }
    const verdicts = {};
    document.querySelectorAll('#review-citations select').forEach(select => {
      if (select.value) verdicts[select.dataset.citationId] = select.value === 'correct';
    });
    const button = $('#save-review'); button.disabled = true; button.textContent = '正在保存…';
    saving = true;
    setReviewStatus('');
    const version = metricsVersion;
    try {
      const data = await request(`/api/history/${item.id}/review`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answerable, expected_sources: expectedSources, citation_verdicts: verdicts })
      });
      item.review = data.review; records.set(item.id, item);
      if (version === metricsVersion) renderMetrics(data.metrics, '核验已保存。');
      else refreshMetrics();
      if (currentId === item.id) $('#review-current').textContent = '修改本次核验';
      $('#review-dialog').close();
    } catch (error) {
      if ($('#review-dialog').open) setReviewStatus(`保存失败：${error.message}`, true);
      else {
        $('#metrics-error').textContent = `核验保存失败：${error.message}，请重新打开记录重试。`;
        $('#metrics-error').hidden = false;
      }
    }
    finally { saving = false; button.disabled = false; button.textContent = '保存核验并更新指标'; }
  });
  window.addEventListener('kbqa:answer', event => {
    const { question, response } = event.detail;
    if (response.query_id == null) { refreshMetrics(); return; }
    currentId = response.query_id;
    records.set(currentId, { id: currentId, question, response, created_at: new Date().toISOString(), review: null, auto_review: response.auto_review });
    $('#review-current').hidden = false; $('#review-current').textContent = '人工核验 / 修正';
    if (response.metrics) renderMetrics(response.metrics);
    else refreshMetrics();
    if (response.evaluation_warning) {
      $('#metrics-error').textContent = response.evaluation_warning;
      $('#metrics-error').hidden = false;
    }
  });
  window.addEventListener('focus', refreshMetrics);
  refreshMetrics();
})();
