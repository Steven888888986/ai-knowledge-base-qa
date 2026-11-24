(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const api = async (path, options = {}) => {
    const response = await fetch(path, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || data.detail || `请求失败 (${response.status})`);
    return data;
  };
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const state = { controller: null, sourceId: null, docMap: new Map() };
  const status = $('#service-status');
  const warning = $('#model-warning');
  const answer = $('#answer');
  const citations = $('#citations');
  const queryStatus = $('#query-status');
  const isLookup = value => /^[0-9]+$/.test(value.trim());

  function updateQuestionMode() {
    const lookup = isLookup($('#question').value);
    $('#ask-label').textContent = lookup ? '查找内容' : '检索并回答';
    $('#retrieval-mode').disabled = lookup || Boolean(state.controller);
    $('#question-hint').textContent = lookup ? 'Enter 查找 · 按原文内容匹配全部文档，不计入问答统计' : 'Enter 发送 · Shift + Enter 换行 · 纯数字（如 2、2024）可查找原文内容';
  }
  function setResultMode(lookup) {
    $('#answer-heading').textContent = lookup ? '内容查找结果' : '知识库回答';
    $('#evidence-heading').textContent = lookup ? '匹配文档' : '引用证据';
    $('.results-grid').setAttribute('aria-label', lookup ? '内容查找结果' : '问答结果');
    $('.results-grid').classList.toggle('lookup-mode', lookup);
    const target = lookup ? $('#lookup-results') : $('.evidence-panel');
    target.append($('#evidence-heading').parentElement, citations);
    $('#lookup-results').hidden = !lookup;
    $('.evidence-panel').hidden = lookup;
    $('#answer-footer').textContent = lookup ? '已列出全部匹配文档及匹配原文，可查看文档全文。本次查找不计入问答统计。' : '请结合右侧引用核对回答，模型可能出现理解偏差。';
  }
  function appendHighlighted(node, value, term = '') {
    const text = String(value);
    if (!term) { node.append(document.createTextNode(text)); return; }
    const parts = text.split(term);
    parts.forEach((part, index) => {
      if (index) node.append(el('mark', 'lookup-match', term));
      node.append(document.createTextNode(part));
    });
  }

  function setModelStatus(text, kind = 'ready') {
    status.className = `service-status ${kind}`;
    $('#model-status').textContent = text;
  }
  function setFormStatus(node, text, error = false) {
    node.textContent = text;
    node.classList.toggle('error', error);
  }
  async function refreshStatus() {
    try {
      const [health, stats] = await Promise.all([api('/api/health'), api('/api/stats')]);
      const model = health.model || stats.model || {};
      if (model.available) setModelStatus(`本地模型已连接 · ${model.name || 'ready'}`);
      else setModelStatus(`离线检索 · ${model.name || '本地模型未启动'}`, 'warning');
      $('#docs').textContent = stats.documents ?? 0;
      $('#chunks').textContent = stats.chunks ?? 0;
      $('#retrieval-description').textContent = health.retrieval || (stats.embedding_mode ? `检索向量：${stats.embedding_mode}` : 'BM25 关键词与向量混合检索');
      if (!model.available) {
        warning.textContent = '本地问答模型尚未连接。当前仍可检索知识库并查看引用；回答将以离线检索结果呈现。请先启动本地模型服务后再使用生成问答。';
        warning.hidden = false;
      } else {
        warning.hidden = true;
      }
    } catch (error) {
      setModelStatus('无法连接问答服务', 'error');
      warning.textContent = `暂时无法读取服务状态：${error.message}`;
      warning.hidden = false;
    }
  }
  async function refreshDocuments() {
    const list = $('#document-list');
    const errorNode = $('#library-error');
    $('#refresh').disabled = true;
    errorNode.hidden = true;
    try {
      const result = await api('/api/documents');
      const docs = result.documents || [];
      state.docMap = new Map(docs.map(doc => [String(doc.id), doc]));
      list.replaceChildren();
      if (!docs.length) {
        list.append(el('p', 'muted', '还没有资料。导入文件或网页后即可开始提问。'));
      } else {
        docs.forEach(doc => {
          const button = el('button', 'document-item');
          button.type = 'button';
          button.setAttribute('aria-label', `查看 ${doc.title || doc.source || '文档'}`);
          const iconWrap = el('span', 'document-icon');
          const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
          icon.setAttribute('class', 'icon'); icon.setAttribute('aria-hidden', 'true');
          const use = document.createElementNS('http://www.w3.org/2000/svg', 'use'); use.setAttribute('href', '#i-file'); icon.append(use); iconWrap.append(icon);
          const info = el('span', 'document-text');
          info.append(el('span', 'document-title', doc.title || doc.source || '未命名资料'));
          const detail = [doc.kind || '文档', `${doc.chunks ?? 0} 个片段`];
          if (doc.pages) detail.push(`${doc.pages} 页`);
          info.append(el('span', 'document-meta', detail.join(' · ')));
          button.append(iconWrap, info);
          button.addEventListener('click', () => openDocument(doc.id));
          list.append(button);
        });
      }
      await refreshStatus();
    } catch (error) {
      errorNode.textContent = `无法读取知识库：${error.message}`;
      errorNode.hidden = false;
      list.replaceChildren(el('p', 'muted', '连接知识库服务失败。'));
    } finally {
      $('#refresh').disabled = false;
    }
  }

  function markAnswerEmpty(message, hint = '请检查问题或调整检索方式后重试。') {
    answer.className = 'answer-body empty';
    answer.replaceChildren();
    const iconWrap = el('div', 'empty-mark');
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); svg.setAttribute('class', 'icon'); svg.setAttribute('aria-hidden', 'true');
    const use = document.createElementNS('http://www.w3.org/2000/svg', 'use'); use.setAttribute('href', '#i-spark'); svg.append(use); iconWrap.append(svg);
    answer.append(iconWrap, el('h3', '', message), el('p', '', hint));
  }
  function buildCitation(item, index) {
    const details = el('details', 'citation');
    const summary = document.createElement('summary');
    summary.append(el('span', 'citation-number', `[${index + 1}]`));
    const heading = el('span', 'citation-heading');
    heading.append(el('span', 'citation-title', item.title || item.source || '来源资料'));
    const meta = [item.source];
    if (item.page) meta.push(`第 ${item.page} 页`);
    if (item.chunk_id) meta.push(`片段 ${item.chunk_id}`);
    heading.append(el('span', 'citation-meta', meta.filter(Boolean).join(' · ')));
    summary.append(heading, el('span', 'citation-chevron', '›'));
    const snippet = el('p', 'citation-snippet', item.snippet || item.content || '没有返回原文片段。');
    details.append(summary, snippet);
    if (item.document_id !== undefined && item.document_id !== null) {
      const open = el('button', 'source-button', '查看文档原文');
      open.type = 'button';
      open.addEventListener('click', () => openDocument(item.document_id, item.chunk_id));
      details.append(open);
    }
    return details;
  }
  function buildLookupDocument(item, index, term) {
    const article = el('article', 'lookup-document');
    article.append(el('h3', '', `${index + 1}. ${item.title || item.source || '来源资料'}`), el('p', 'citation-meta', item.source || ''));
    const passages = item.passages?.length ? item.passages : [item];
    passages.forEach((passage, passageIndex) => {
      const section = el('div', 'lookup-passage');
      const meta = [`匹配原文 ${passageIndex + 1}`];
      if (passage.page) meta.push(`第 ${passage.page} 页`);
      if (passage.chunk_id) meta.push(`片段 ${passage.chunk_id}`);
      section.append(el('p', 'citation-meta', meta.join(' · ')));
      const snippet = el('p', 'citation-snippet');
      appendHighlighted(snippet, passage.snippet || passage.content || '没有返回原文片段。', term);
      section.append(snippet);
      if (item.document_id != null) {
        const open = el('button', 'source-button', '查看文档原文');
        open.type = 'button';
        open.addEventListener('click', () => openDocument(item.document_id, passage.chunk_id, term));
        section.append(open);
      }
      article.append(section);
    });
    return article;
  }
  function addAnswerWithCitationLinks(text, usedCitations) {
    answer.className = 'answer-body';
    answer.replaceChildren();
    const sourceText = String(text || '没有生成回答。');
    const re = /\[(\d+)\]/g;
    let cursor = 0;
    let match;
    while ((match = re.exec(sourceText))) {
      if (match.index > cursor) answer.append(document.createTextNode(sourceText.slice(cursor, match.index)));
      const number = Number(match[1]);
      if (number > 0 && number <= usedCitations.length) {
        const jump = el('button', 'citation-jump', match[0]);
        jump.type = 'button'; jump.setAttribute('aria-label', `展开第 ${number} 条引用`);
        jump.addEventListener('click', () => {
          const target = citations.children[number - 1];
          if (target) { target.open = true; target.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
        });
        answer.append(jump);
      } else answer.append(document.createTextNode(match[0]));
      cursor = re.lastIndex;
    }
    if (cursor < sourceText.length) answer.append(document.createTextNode(sourceText.slice(cursor)));
  }
  function renderQuery(data) {
    const lookup = data.mode === 'lookup';
    setResultMode(lookup);
    const refs = data.citations || [];
    citations.replaceChildren();
    if (lookup) {
      const { term, matches = [], matched_documents = matches.length } = data.lookup;
      answer.className = 'answer-body';
      answer.textContent = data.answer;
      $('#citation-count').textContent = matched_documents;
      if (!matches.length) citations.append(el('p', 'evidence-empty', `未找到包含“${term}”的文档。请尝试其他数字，或先导入相关资料。`));
      else matches.forEach((match, index) => citations.append(buildLookupDocument(match, index, term)));
    } else {
      addAnswerWithCitationLinks(data.answer, refs);
      $('#citation-count').textContent = refs.length;
      if (!refs.length) citations.append(el('p', 'evidence-empty', data.refused ? '没有找到足够证据。请先导入相关资料，或换一种问法。' : '本次回答没有关联到可展示的引用。'));
      else refs.forEach((ref, index) => citations.append(buildCitation(ref, index)));
    }
    const badge = $('#answer-mode');
    const modeName = lookup ? '内容查找' : data.mode === 'llm' ? '本地模型 + 检索' : data.mode === 'refusal' || data.refused ? '缺少证据' : '离线检索';
    badge.textContent = modeName;
    badge.className = `badge ${data.mode === 'llm' ? 'llm' : data.refused ? 'refusal' : ''}`;
    $('#answer-footer').hidden = false;
    $('#elapsed').textContent = data.elapsed_ms != null ? `用时 ${(data.elapsed_ms / 1000).toFixed(1)} 秒` : '';
    $('#answer-card').setAttribute('aria-busy', 'false');
    if (data.warning) {
      warning.textContent = data.warning;
      warning.hidden = false;
    }
    queryStatus.hidden = true;
  }
  async function submitQuestion(question) {
    const clean = question.trim();
    if (!clean || state.controller) return;
    const lookup = isLookup(clean);
    const controller = new AbortController();
    state.controller = controller;
    updateQuestionMode();
    setResultMode(lookup);
    window.dispatchEvent(new CustomEvent('kbqa:query-start'));
    const started = performance.now();
    $('#ask').disabled = true;
    $('#cancel-query').hidden = false;
    $('#answer-card').setAttribute('aria-busy', 'true');
    $('#answer-mode').className = 'badge';
    $('#answer-mode').textContent = lookup ? '正在查找' : '正在检索';
    $('#answer-footer').hidden = true;
    $('#citation-count').textContent = '0';
    $('#elapsed').textContent = '';
    queryStatus.className = 'query-status'; queryStatus.textContent = lookup ? `正在查找原文内容包含“${clean}”的全部文档。` : '正在搜索知识库、生成回答并自动评估来源与引用。'; queryStatus.hidden = false;
    answer.className = 'answer-body'; answer.textContent = lookup ? '正在查找匹配文档…' : '正在检索资料并生成回答…';
    citations.replaceChildren(el('p', 'evidence-empty', lookup ? '正在查找匹配原文…' : '正在查找相关来源…'));
    try {
      const data = await api('/api/query', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: clean, retrieval_mode: $('#retrieval-mode').value, limit: 5 }), signal: controller.signal });
      renderQuery(data);
      window.dispatchEvent(new CustomEvent('kbqa:answer', { detail: { question: clean, response: data } }));
      if (data.mode === 'llm') setModelStatus(`本地模型已连接 · ${data.model || 'ready'}`);
      else if (data.warning) setModelStatus('离线模式 · 请检查模型', 'warning');
    } catch (error) {
      if (error.name === 'AbortError') {
        queryStatus.className = 'query-status'; queryStatus.textContent = lookup ? '已停止等待内容查找。' : '已停止等待。模型计算可能仍会在服务端继续。'; queryStatus.hidden = false;
        markAnswerEmpty('已停止等待', lookup ? '可以重新查找数字或输入完整问题。' : undefined);
      } else {
        queryStatus.className = 'query-status error'; queryStatus.textContent = `请求失败：${error.message}`; queryStatus.hidden = false;
        markAnswerEmpty(lookup ? '这次没有拿到查找结果' : '这次没有拿到回答', lookup ? '请检查连接后重新查找。' : undefined);
      }
      $('#answer-mode').textContent = lookup ? '内容查找' : '问答未完成';
      citations.replaceChildren(el('p', 'evidence-empty', lookup ? '当前没有可展示的匹配文档。' : '当前没有可展示的引用。'));
      $('#citation-count').textContent = '0'; $('#answer-footer').hidden = true;
      $('#answer-card').setAttribute('aria-busy', 'false');
    } finally {
      $('#elapsed').textContent ||= `用时 ${((performance.now() - started) / 1000).toFixed(1)} 秒`;
      if (state.controller === controller) state.controller = null;
      $('#ask').disabled = false; $('#cancel-query').hidden = true;
      updateQuestionMode();
    }
  }

  async function openDocument(id, focusChunkId, term = '') {
    const dialog = $('#source-dialog');
    state.sourceId = id;
    $('#source-title').textContent = state.docMap.get(String(id))?.title || '原文资料';
    $('#source-meta').textContent = '正在读取文档…';
    $('#source-content').replaceChildren();
    setFormStatus($('#source-status'), '');
    $('#delete-document').disabled = true;
    if (!dialog.open) dialog.showModal();
    try {
      const data = await api(`/api/documents/${encodeURIComponent(id)}`);
      const doc = data.document || {};
      $('#source-title').textContent = doc.title || doc.source || '原文资料';
      $('#source-meta').textContent = [doc.source, doc.kind, doc.pages ? `${doc.pages} 页` : null].filter(Boolean).join(' · ');
      const container = $('#source-content');
      const chunks = data.chunks || [];
      if (chunks.length && !(term && focusChunkId == null)) {
        chunks.forEach((chunk, i) => {
          const section = el('section', 'source-chunk');
          section.dataset.chunkId = String(chunk.chunk_id ?? '');
          const parts = [];
          if (chunk.page) parts.push(`第 ${chunk.page} 页`);
          if (chunk.chunk_id) parts.push(`片段 ${chunk.chunk_id}`);
          section.append(el('span', 'source-chunk-title', parts.join(' · ') || `片段 ${i + 1}`));
          const content = el('p');
          appendHighlighted(content, chunk.content || '', term);
          section.append(content);
          container.append(section);
        });
      } else {
        const content = el('p');
        appendHighlighted(content, doc.content || '此文档没有可显示的提取文本。', term);
        container.append(content);
      }
      if (focusChunkId != null) {
        const match = [...container.children].find(child => child.dataset.chunkId === String(focusChunkId));
        if (match) { match.scrollIntoView({ block: 'center' }); match.classList.add('focused-source'); }
      }
      $('#delete-document').disabled = false;
    } catch (error) {
      $('#source-meta').textContent = '';
      $('#source-content').replaceChildren(el('p', '', `无法打开原文：${error.message}`));
      setFormStatus($('#source-status'), error.message, true);
    }
  }
  async function deleteDocument() {
    if (state.sourceId == null || !window.confirm('删除这份资料及其检索片段？')) return;
    const button = $('#delete-document'); button.disabled = true;
    try {
      await api(`/api/documents/${encodeURIComponent(state.sourceId)}`, { method: 'DELETE' });
      $('#source-dialog').close();
      await refreshDocuments();
      queryStatus.className = 'query-status'; queryStatus.textContent = '资料已删除。'; queryStatus.hidden = false;
    } catch (error) {
      setFormStatus($('#source-status'), `删除失败：${error.message}`, true); button.disabled = false;
    }
  }
  function toBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error('无法读取所选文件。'));
      reader.onload = () => resolve(String(reader.result).split(',', 2)[1]);
      reader.readAsDataURL(file);
    });
  }
  function setBusy(button, busy, idleText, busyText) {
    button.disabled = busy;
    if (!button.dataset.idleText) button.dataset.idleText = idleText;
    button.textContent = busy ? busyText : button.dataset.idleText;
  }

  $('#question-form').addEventListener('submit', event => { event.preventDefault(); submitQuestion($('#question').value); });
  $('#question').addEventListener('input', updateQuestionMode);
  $('#question').addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); $('#question-form').requestSubmit(); }
  });
  $('#cancel-query').addEventListener('click', () => state.controller?.abort());
  document.querySelectorAll('.suggestions button').forEach(button => button.addEventListener('click', () => {
    $('#question').value = button.textContent; $('#question').focus(); submitQuestion(button.textContent);
  }));
  $('#open-import').addEventListener('click', () => { setFormStatus($('#import-status'), ''); $('#import-dialog').showModal(); });
  $('#refresh').addEventListener('click', refreshDocuments);
  $('#delete-document').addEventListener('click', deleteDocument);
  document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => $(`#${button.dataset.close}`).close()));
  document.querySelectorAll('dialog').forEach(dialog => dialog.addEventListener('click', event => {
    if (event.target === dialog) dialog.close();
  }));
  $('#upload-form').addEventListener('submit', async event => {
    event.preventDefault();
    const file = $('#file-input').files[0]; if (!file) return;
    const button = $('#upload-submit'); setBusy(button, true, '上传并索引', '正在上传与索引…');
    setFormStatus($('#import-status'), '正在读取文件并建立索引…');
    try {
      if (file.size > 10 * 1024 * 1024) throw new Error('文件超过 10 MB 限制。');
      const content_base64 = await toBase64(file);
      const result = await api('/api/upload', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ filename: file.name, content_base64 }) });
      setFormStatus($('#import-status'), `导入完成：${result.chunks ?? result.document?.chunks ?? ''} 个片段。`);
      $('#upload-form').reset(); await refreshDocuments();
    } catch (error) { setFormStatus($('#import-status'), `导入失败：${error.message}`, true); }
    finally { button.disabled = false; button.textContent = button.dataset.idleText; }
  });
  $('#url-form').addEventListener('submit', async event => {
    event.preventDefault(); const button = $('#url-submit'); setBusy(button, true, '导入网页', '正在读取网页…');
    setFormStatus($('#import-status'), '正在读取网页并建立索引…');
    try {
      const result = await api('/api/import-url', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: $('#url-input').value.trim() }) });
      setFormStatus($('#import-status'), `网页导入完成：${result.chunks ?? result.document?.chunks ?? ''} 个片段。`);
      $('#url-form').reset(); await refreshDocuments();
    } catch (error) { setFormStatus($('#import-status'), `网页导入失败：${error.message}`, true); }
    finally { button.disabled = false; button.textContent = button.dataset.idleText; }
  });
  $('#retrieval-mode').addEventListener('change', event => {
    const descriptions = { hybrid: '关键词与向量融合检索 / RRF', bm25: 'BM25 关键词检索（消融）', vector: '向量相似度检索（消融）' };
    $('#retrieval-description').textContent = descriptions[event.target.value];
  });
  refreshDocuments();
})();
