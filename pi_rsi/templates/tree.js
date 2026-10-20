// Offline search explorer. No network, dependencies, or execution of node documents.
(() => {
  'use strict';
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const scored = node => finite(node.score) && (node.measurement && Object.keys(node.measurement).length ?
    node.measurement.state === 'validated' : node.worker?.evaluation_validated ?
    node.worker.evaluation_validated.score === node.score && node.worker.evaluation_validated.commit === node.commit : node.status === 'done');
  const better = (a, b, higher) => b == null || (higher ? a > b : a < b);
  const fmt = value => !finite(value) ? '—' : new Intl.NumberFormat('en-US', {maximumSignificantDigits: 5}).format(value);
  const signed = value => !finite(value) ? '—' : `${value > 0 ? '+' : ''}${fmt(value)}`;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const date = value => typeof value === 'string' && Number.isFinite(Date.parse(value)) ? Date.parse(value) : null;
  const duration = seconds => !finite(seconds) ? '—' : seconds < 60 ? `${Math.round(seconds)}s` : seconds < 3600 ? `${(seconds / 60).toFixed(1)}m` : `${(seconds / 3600).toFixed(1)}h`;
  function completionOrder(a, b) {
    return ((a.finished_order || 0) - (b.finished_order || 0)) || String(a.finished_at || '').localeCompare(String(b.finished_at || '')) || a.id.localeCompare(b.id);
  }
  function bestNode(nodes, higher) {
    return nodes.reduce((best, node) => scored(node) && better(node.score, best?.score, higher) ? node : best, null);
  }
  function ancestry(id, byId) {
    const ids = new Set();
    while (id && byId[id] && !ids.has(id)) { ids.add(id); id = byId[id].parent; }
    return ids;
  }
  function chartSeries(data, axis = 'nodes') {
    const nodes = data.nodes || [];
    const root = nodes.find(n => n.id === 'root');
    const baseline = root ? (scored(root) ? root.score : null) : (finite(data.root_score) ? data.root_score : null);
    const finished = nodes.filter(n => n.id !== 'root' && ['done', 'failed', 'incomplete'].includes(n.status)).sort(completionOrder);
    const candidates = [date(data.experiment_started_at), ...nodes.flatMap(n => [date(n.created_at), date(n.started_at)])].filter(x => x != null);
    const start = date(data.experiment_started_at) ?? (candidates.length ? Math.min(...candidates) : null);
    const timeAvailable = start != null && finished.length > 0 && finished.every(n => date(n.finished_at) != null && date(n.finished_at) >= start);
    const time = axis === 'time' && timeAvailable;
    const points = finished.map((n, i) => ({node: n, x: time ? (date(n.finished_at) - start) / 1000 : i + 1, score: scored(n) ? n.score : null}));
    // Chart time is chronological, completion order remains authoritative for the node-count axis.
    if (time) points.sort((a, b) => a.x - b.x || completionOrder(a.node, b.node));
    let best = baseline;
    for (const point of points) {
      if (point.score != null && better(point.score, best, data.higher_is_better)) best = point.score;
      point.best = best;
    }
    return {baseline, points, timeAvailable, axis: time ? 'time' : 'nodes'};
  }
  // Pure helpers also run in Node regression tests; the browser remains a single-file bundle.
  if (typeof module !== 'undefined' && module.exports) module.exports = {finite, scored, bestNode, ancestry, completionOrder, chartSeries};
  if (typeof document === 'undefined') return;

  const D = window.__RSI_DATA__ || {nodes: []};
  D.nodes = D.nodes || [];
  const byId = Object.fromEntries(D.nodes.map(n => [n.id, n]));
  const best = bestNode(D.nodes, D.higher_is_better);
  const root = byId.root;
  const bestPath = ancestry(best?.id, byId);
  const $ = id => document.getElementById(id);
  const status = node => ['running', 'evaluating', 'analyzing', 'waiting', 'incomplete', 'planned', 'failed', 'abandoned'].includes(node.status) ? node.status : (node.verdict || node.status);
  const statusClass = node => ['analyzing', 'waiting'].includes(status(node)) ? 'evaluating' : ['running', 'evaluating', 'incomplete', 'planned', 'failed', 'abandoned', 'improved', 'worse', 'no_change', 'baseline', 'done'].includes(status(node)) ? status(node) : 'done';
  const color = node => ({running: 'var(--run)', evaluating: 'var(--eval)', incomplete: 'var(--warn)', planned: 'var(--plan)', failed: 'var(--bad)', abandoned: 'var(--muted)', improved: 'var(--ok)', worse: 'var(--warn)', baseline: 'var(--muted)'})[statusClass(node)] || 'var(--plan)';
  const badge = node => `<span class="tag ${statusClass(node)}">${escape(status(node) === 'incomplete' ? 'notes pending' : status(node).replaceAll('_', ' '))}</span>`;
  let selectedId = best?.id || D.nodes[0]?.id;
  let detailTab = 'overview';
  let axis = 'nodes';
  let showReferences = false;

  $('title').textContent = D.experiment || 'Search explorer';
  $('subtitle').textContent = `${D.task || 'Research task'} · ${D.score_key || 'score'} ${D.higher_is_better ? '↑ higher is better' : '↓ lower is better'} · worker ${D.runner || '—'} · snapshot ${D.generated_at || '—'}`;
  $('run-status').textContent = `${D.state?.status || 'snapshot'}${D.state?.stop_reason ? ' · ' + D.state.stop_reason.replaceAll('_', ' ') : ''}`;
  $('run-status').dataset.status = D.state?.status || 'snapshot';
  const waiting = D.waiting_questions || [];
  if (waiting.length) {
    const box = $('attention');
    const head = document.createElement('strong');
    head.textContent = `Waiting for you: ${waiting.length} question${waiting.length > 1 ? 's' : ''} in setup/QUESTIONS.md (the run continues meanwhile)`;
    const list = document.createElement('ul');
    for (const q of waiting) {
      const li = document.createElement('li');
      li.textContent = `${q.id} (${q.importance || '?'}): ${q.question}`;
      list.appendChild(li);
    }
    box.replaceChildren(head, list);
    box.hidden = false;
  }
  const gain = scored(root || {}) && best ? (best.score - root.score) * (D.higher_is_better ? 1 : -1) : null;
  const running = D.nodes.filter(n => ['running', 'evaluating', 'analyzing', 'waiting'].includes(n.status)).length;
  const done = D.nodes.filter(n => n.id !== 'root' && n.status === 'done').length;
  const failed = D.nodes.filter(n => n.status === 'failed').length;
  const incomplete = D.nodes.filter(n => n.status === 'incomplete').length;
  const cost = Object.values(D.costs || {}).reduce((sum, c) => sum + (finite(c.cost_usd) ? c.cost_usd : 0), 0);
  const kpis = [
    ['Baseline', scored(root || {}) ? fmt(root.score) : '—', D.official_seedset || 'official evaluation'],
    ['Best measured score', best ? fmt(best.score) : '—', best ? `${best.id} · ${signed(gain)} gain vs baseline` : 'Waiting for a valid result'],
    ['Hypotheses', `${D.nodes.filter(n => n.id !== 'root' && n.status !== 'abandoned').length} / ${D.search?.max_nodes ?? '—'}`, `${done} completed · ${incomplete} notes pending · ${failed} execution failures · ${running} active`],
    ['Execution attempts', `${D.execution_attempts ?? '—'} / ${D.search?.max_attempts ?? '—'}`, `Retries stay within the same hypothesis · width ${D.search?.width_policy || 'bounded'}`],
  ];
  if (finite(D.final?.best_final_score)) kpis.push([
    'Separate eval · ' + (D.final_seedset || 'final'), fmt(D.final.best_final_score),
    `${D.final.best_by_final || D.final.best || 'Candidate not recorded'}${finite(D.final.root_final_score) ? ' · baseline ' + fmt(D.final.root_final_score) : ''} · not the search score`,
  ]);
  if (cost > 0) kpis.push(['API cost estimate', '$' + cost.toFixed(2), 'Workers + utility calls; not compute cost']);
  $('kpis').innerHTML = kpis.map(([label, value, note]) => `<div class="kpi"><div class="l">${escape(label)}</div><div class="v">${escape(value)}</div><div class="sub">${escape(note)}</div></div>`).join('');

  // Theme preference is optional: file:// browsers can deny localStorage.
  try { const saved = localStorage.getItem('rsi-theme'); if (['light', 'dark'].includes(saved)) document.documentElement.dataset.theme = saved; } catch (_) { /* offline private mode */ }
  function syncTheme() {
    const dark = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    $('theme-toggle').setAttribute('aria-pressed', String(dark));
    $('theme-toggle').title = dark ? 'Switch to light theme' : 'Switch to dark theme';
    $('theme-toggle').setAttribute('aria-label', $('theme-toggle').title);
  }
  $('theme-toggle').addEventListener('click', () => {
    const dark = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.dataset.theme = dark ? 'light' : 'dark';
    try { localStorage.setItem('rsi-theme', document.documentElement.dataset.theme); } catch (_) { /* optional */ }
    syncTheme();
  });
  syncTheme();

  // Tree camera: viewBox-based pan/zoom keeps SVG text sharp, including offline exports.
  const svg = $('tree'), viewport = $('treewrap');
  const NW = 220, NH = 104, GX = 40, GY = 70;
  const px = n => 30 + (finite(n.x) ? n.x : 0) * (NW + GX);
  const py = n => 30 + (finite(n.y) ? n.y : n.depth || 0) * (NH + GY);
  const worldW = Math.max(280, ...D.nodes.map(n => px(n) + NW + 30));
  const worldH = Math.max(164, ...D.nodes.map(n => py(n) + NH + 30));
  let camera = {x: 0, y: 0, w: worldW, h: worldH};
  const viewSize = () => ({w: Math.max(viewport.clientWidth, 200), h: Math.max(viewport.clientHeight, 200)});
  function applyCamera() {
    svg.setAttribute('viewBox', `${camera.x} ${camera.y} ${camera.w} ${camera.h}`);
    $('zoom-label').textContent = `${Math.round(viewSize().w / camera.w * 100)}%`;
  }
  function fitTree() {
    const {w, h} = viewSize();
    camera.w = Math.max(worldW, worldH * w / h, w);
    camera.h = camera.w * h / w;
    camera.x = (worldW - camera.w) / 2;
    camera.y = (worldH - camera.h) / 2;
    applyCamera();
  }
  function worldPoint(clientX, clientY) {
    const point = svg.createSVGPoint(); point.x = clientX; point.y = clientY;
    const matrix = svg.getScreenCTM();
    return matrix ? point.matrixTransform(matrix.inverse()) : {x: camera.x + camera.w / 2, y: camera.y + camera.h / 2};
  }
  function zoom(factor, anchor = {x: camera.x + camera.w / 2, y: camera.y + camera.h / 2}) {
    const {w, h} = viewSize();
    const nextW = Math.max(w / 2.5, Math.min(Math.max(worldW, worldH * w / h, w) * 4, camera.w / factor));
    const ratio = nextW / camera.w;
    camera.x = anchor.x - (anchor.x - camera.x) * ratio;
    camera.y = anchor.y - (anchor.y - camera.y) * ratio;
    camera.w = nextW; camera.h = nextW * h / w;
    applyCamera();
  }
  function focusNode(id) {
    const node = byId[id]; if (!node) return;
    const {w, h} = viewSize();
    camera.w = Math.max(w, NW * 2.3); camera.h = camera.w * h / w;
    camera.x = px(node) + NW / 2 - camera.w / 2;
    camera.y = py(node) + NH / 2 - camera.h / 2;
    applyCamera();
  }
  const shorten = (value, max) => { const chars = Array.from(value || ''); return chars.length > max ? chars.slice(0, max - 1).join('') + '…' : chars.join(''); };
  svg.setAttribute('width', '100%'); svg.setAttribute('height', '100%');
  svg.setAttribute('aria-label', 'Experiment search tree. Select a node to inspect; drag to pan and scroll to zoom.');
  let markup = '';
  for (const node of D.nodes) {
    const parent = byId[node.parent]; if (!parent) continue;
    markup += `<path class="edge${bestPath.has(node.id) && bestPath.has(parent.id) ? ' best-path' : ''}" data-child="${escape(node.id)}" d="M${px(parent) + NW / 2},${py(parent) + NH} C${px(parent) + NW / 2},${py(parent) + NH + GY / 2} ${px(node) + NW / 2},${py(node) - GY / 2} ${px(node) + NW / 2},${py(node)}"/>`;
  }
  for (const node of D.nodes) {
    const nodeBest = node.id === best?.id;
    const measured = scored(node);
    const label = measured ? fmt(node.score) : node.status === 'done' ? 'No valid score' : node.status;
    markup += `<g class="node ${statusClass(node)}${bestPath.has(node.id) ? ' best-path' : ''}" data-id="${escape(node.id)}" transform="translate(${px(node)},${py(node)})" tabindex="0" role="button" aria-label="${escape(`${node.id}: ${node.title}. ${node.status}. ${measured ? 'Score ' + fmt(node.score) : ''}`)}" aria-pressed="false">` +
      `<title>${escape(node.title)}${node.retry_of ? ' · Retry of ' + escape(node.retry_of) : ''}</title><rect class="node-card" width="${NW}" height="${NH}" rx="12" fill="var(--panel)" stroke="${nodeBest ? 'var(--gold)' : 'var(--line)'}"/>` +
      `<circle class="status-dot" cx="17" cy="19" r="4" fill="${color(node)}"/><text class="node-id" x="29" y="23">${escape(node.id)}${node.retry_of ? ' ↻' : ''}</text>` +
      `<text x="${NW - 12}" y="23" text-anchor="end" class="node-meta">${nodeBest ? '★ BEST' : escape(status(node).replaceAll('_', ' '))}</text>` +
      `<text class="node-title" x="13" y="46">${escape(shorten(node.title || 'Baseline', 29))}</text>` +
      `<text class="node-score" x="13" y="72">${escape(label)}</text>` +
      `<text class="node-meta" x="13" y="92">${measured && finite(node.delta_parent) ? 'Δ parent ' + escape(signed(node.delta_parent)) : node.id === 'root' ? 'Baseline · official evaluation' : 'depth ' + node.depth}${node.retry_of ? ' · retry ' + escape(node.retry_of) : ''}</text></g>`;
  }
  if (!D.nodes.length) markup = '<text x="30" y="60" class="muted">No experiments yet. The baseline will appear here.</text>';
  svg.innerHTML = markup;
  svg.querySelectorAll('.node').forEach(element => {
    element.addEventListener('click', event => { if (!suppressClick) select(element.dataset.id); });
    element.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(element.dataset.id); }
    });
  });
  let drag = null, suppressClick = false;
  svg.addEventListener('pointerdown', event => {
    if (event.button !== 0 || !event.isPrimary) return;
    drag = {id: event.pointerId, x: event.clientX, y: event.clientY, camera: {...camera}, moved: false};
  });
  svg.addEventListener('pointermove', event => {
    if (!drag || event.pointerId !== drag.id) return;
    const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < 4) return;
    if (!drag.moved) { svg.setPointerCapture(event.pointerId); drag.moved = true; }
    suppressClick = true; viewport.classList.add('dragging');
    camera.x = drag.camera.x - dx * drag.camera.w / viewSize().w;
    camera.y = drag.camera.y - dy * drag.camera.h / viewSize().h;
    applyCamera();
  });
  function endDrag(event) {
    if (!drag || event.pointerId !== drag.id) return;
    if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
    drag = null; viewport.classList.remove('dragging');
    setTimeout(() => { suppressClick = false; }, 0);
  }
  window.addEventListener('pointerup', endDrag);
  window.addEventListener('pointercancel', endDrag);
  svg.addEventListener('wheel', event => {
    event.preventDefault(); zoom(Math.exp(-Math.max(-100, Math.min(100, event.deltaY)) * 0.004), worldPoint(event.clientX, event.clientY));
  }, {passive: false});
  $('zoom-in').addEventListener('click', () => zoom(1.25));
  $('zoom-out').addEventListener('click', () => zoom(0.8));
  $('fit-tree').addEventListener('click', fitTree);
  $('focus-best').disabled = !best;
  $('focus-best').addEventListener('click', () => { if (best) { select(best.id); focusNode(best.id); } });

  // Inspector: hypothesis -> observed change/result -> next experiment. Raw evidence stays one tab away.
  const section = (title, body) => `<section class="detail-section"><h3>${escape(title)}</h3>${body}</section>`;
  const prose = text => `<div class="prose">${escape(text || 'Not recorded yet.')}</div>`;
  const metric = (label, value, extra = '') => `<div class="metric"><div class="label">${escape(label)}</div><div class="value ${extra}">${escape(value)}</div></div>`;
  function overview(node) {
    const parent = byId[node.parent];
    const docs = node.docs || {};
    const result = node.summary || (node.status === 'failed' ? node.failure : 'The official result and audit will appear when this experiment finishes.');
    let html = section('Hypothesis', prose(node.hypothesis || docs.hypothesis));
    html += section('Observed result', prose(result));
    const gitSection = (docs.summary_md || '').split('## Git log')[1] || '';
    const blocks = [...gitSection.matchAll(/```[^\n]*\n([\s\S]*?)```/g)].map(m => m[1].trim());
    if (blocks.length) html += section('Code changes', blocks.map(block => `<pre>${escape(block)}</pre>`).join(''));
    if (parent) html += section('Compared with parent', `<div class="detail-grid">${metric(parent.id + ' official', scored(parent) ? fmt(parent.score) : '—')}${metric('This node official', scored(node) ? fmt(node.score) : '—')}${metric('Gain vs parent', scored(node) ? signed(node.delta_parent) : '—', scored(node) && node.delta_parent > 0 ? 'positive' : scored(node) && node.delta_parent < 0 ? 'negative' : '')}${metric('Gain vs best at finish', scored(node) ? signed(node.delta_best) : '—')}</div><p class="muted">Positive gain means better for this task. A numerical gain is not a claim of statistical significance.</p>`);
    if (node.audit?.claim_check) html += section('Claim check', `<span class="pill">${node.audit.claim_check.consistent ? 'Consistent with evidence' : 'Claim mismatch'}</span>${prose(node.audit.claim_check.note)}`);
    const proposals = node.proposals || [];
    html += section('Next hypotheses', proposals.length ? proposals.map((proposal, i) => `<div class="proposal"><div><span class="pill">${(node.proposals_used || []).includes(i) ? 'Explored' : 'Proposed'}</span> <strong>${escape(proposal.title)}</strong></div>${prose(proposal.hypothesis)}${proposal.risk ? '<p class="muted">Risk: ' + escape(proposal.risk) + '</p>' : ''}</div>`).join('') : '<p class="muted">No next hypothesis recorded.</p>');
    if ((node.proposals_used || []).includes(-1)) html += '<p class="muted">Planner exhausted this branch.</p>';
    if (docs.human) html += section('Human note', prose(docs.human));
    return html;
  }
  function select(id) {
    const node = byId[id]; if (!node) return;
    if (selectedId !== id) $('detail').closest('.inspector').scrollTop = 0;
    selectedId = id;
    $('detail').classList.remove('empty');
    const ancestors = ancestry(id, byId);
    svg.querySelectorAll('.node').forEach(element => {
      element.classList.toggle('selected', element.dataset.id === id);
      element.classList.toggle('ancestor', ancestors.has(element.dataset.id));
      element.setAttribute('aria-pressed', String(element.dataset.id === id));
    });
    svg.querySelectorAll('.edge').forEach(element => element.classList.toggle('ancestor', ancestors.has(element.dataset.child) && ancestors.has(byId[element.dataset.child]?.parent)));
    const docs = node.docs || {};
    const tabs = [['overview', 'Overview'], ['handoff', 'Handoff'], ['progress', 'Progress'], ['evidence', 'Evidence']];
    if (docs.thinking) tabs.splice(1, 0, ['thinking', 'Decision']);
    if (docs.analysis) tabs.splice(2, 0, ['analysis', 'Result analysis']);
    if (docs.implementation) tabs.splice(tabs.findIndex(([key]) => key === 'handoff'), 0, ['implementation', 'Implementation']);
    if (docs.next) tabs.splice(tabs.findIndex(([key]) => key === 'handoff') + 1, 0, ['next', 'Next step']);
    if (node.failure || docs.failure || node.status === 'failed') tabs.push(['failure', 'Failure']);
    if (!tabs.some(([key]) => key === detailTab)) detailTab = 'overview';
    const evidence = {node: node.id, commit: node.commit, official_seedset: D.official_seedset || 'official', metric: D.score_key, higher_is_better: D.higher_is_better, metrics: node.metrics || {}, usage: node.usage || {}};
    const body = ['thinking', 'implementation', 'analysis', 'next'].includes(detailTab) ? `<pre>${escape(docs[detailTab] || '')}</pre>` : detailTab === 'overview' ? overview(node) : detailTab === 'handoff' ? `<pre>${escape(docs.handoff || 'No handoff recorded.')}</pre>` : detailTab === 'progress' ? `<pre>${escape(docs.progress_tail || 'No progress log recorded.')}</pre>` : detailTab === 'failure' ? `<pre>${escape(docs.failure || node.failure || '')}</pre>${section('Diagnosis', prose(node.diagnosis?.cause))}${section('Retry advice', prose(node.diagnosis?.advice))}` : `<pre>${escape(JSON.stringify(evidence, null, 2))}</pre>`;
    $('detail').innerHTML = `<div class="detail-heading"><span class="pill">${escape(id)}</span> ${badge(node)}${node.id === best?.id ? ' <span class="pill">★ Best official score</span>' : ''}</div><h3 class="detail-title">${escape(node.title)}</h3><div class="detail-meta">Depth ${escape(node.depth)}${node.parent ? ' · parent <button class="inline-link" data-parent="' + escape(node.parent) + '">' + escape(node.parent) + '</button>' : ''}${node.retry_of ? ' · retry of ' + escape(node.retry_of) : ''}</div>` +
      `<div class="detail-grid">${metric((D.official_seedset || 'Official') + ' · ' + (D.score_key || 'score'), scored(node) ? fmt(node.score) : '—')}${metric('Worker-reported quick', fmt(node.quick_score))}${metric('Node elapsed', duration(node.duration_s))}${metric('Code commit', node.commit ? node.commit.slice(0, 10) : 'Not committed')}</div>` +
      `<div class="tabs" role="tablist" aria-label="Node evidence">${tabs.map(([key, label]) => `<button type="button" role="tab" id="detail-tab-${key}" aria-controls="detail-body" aria-selected="${key === detailTab}" class="${key === detailTab ? 'on' : ''}" data-tab="${key}">${label}</button>`).join('')}</div><div id="detail-body" role="tabpanel" aria-labelledby="detail-tab-${detailTab}">${body}</div>`;
    $('detail').querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => { detailTab = button.dataset.tab; select(id); $('detail').querySelector(`[data-tab="${detailTab}"]`).focus({preventScroll: true}); }));
    $('detail').querySelector('[data-parent]')?.addEventListener('click', () => { select(node.parent); focusNode(node.parent); });
    document.querySelectorAll('#table tr[data-id]').forEach(row => row.classList.toggle('active-row', row.dataset.id === id));
    $('chart').querySelectorAll('[data-node]').forEach(point => point.classList.toggle('selected-point', point.dataset.node === id));
  }

  function revealInspector() {
    $('detail').closest('.inspector').scrollIntoView({block: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
  }

  // Progress chart. Only completed, finite official scores can improve the incumbent.
  const refs = Object.entries(D.reference_scores || {}).filter(([, value]) => finite(value));
  if (refs.length) {
    const label = document.createElement('label'); label.className = 'reference-toggle';
    const input = document.createElement('input'); input.type = 'checkbox'; input.id = 'show-references';
    input.addEventListener('change', () => { showReferences = input.checked; drawChart(); });
    label.append(input, document.createTextNode(' Show references')); $('chart-controls').append(label);
  }
  function drawChart() {
    const chart = $('chart');
    const series = chartSeries(D, axis);
    axis = series.axis;
    $('chart-controls').querySelectorAll('[data-axis]').forEach(button => {
      button.classList.toggle('on', button.dataset.axis === axis);
      button.setAttribute('aria-pressed', String(button.dataset.axis === axis));
      if (button.dataset.axis === 'time') { button.disabled = !series.timeAvailable; button.title = series.timeAvailable ? 'Elapsed wall-clock time from experiment start, including gaps' : 'Requires valid start and completion timestamps'; }
    });
    const values = [series.baseline, ...series.points.map(p => p.score), ...(showReferences ? refs.map(([, value]) => value) : [])].filter(finite);
    const width = Math.max(320, chart.clientWidth || 600), height = 260, m = {l: 75, r: 22, t: 24, b: 46};
    chart.setAttribute('viewBox', `0 0 ${width} ${height}`);
    chart.setAttribute('aria-label', `Official scores and best-so-far by ${axis === 'time' ? 'elapsed wall-clock time' : 'completed experiments'}. ${D.higher_is_better ? 'Higher' : 'Lower'} is better.`);
    $('chart-note').textContent = `${D.higher_is_better ? 'Higher' : 'Lower'} is better · line: best official score, including baseline · dots: completed experiments · ×: failed / invalid result${axis === 'time' ? ' · wall time includes idle and restart gaps' : ''}`;
    if (!values.length) { chart.innerHTML = '<text x="24" y="100" class="muted">No valid official scores yet.</text>'; return; }
    let low = Math.min(...values), high = Math.max(...values);
    const pad = (high - low || Math.abs(high) * 0.1 || 1) * 0.12;
    low -= pad; high += pad;
    const maxX = Math.max(axis === 'time' ? 1 : 1, ...series.points.map(p => p.x));
    const X = value => m.l + value / maxX * (width - m.l - m.r);
    const Y = value => m.t + (high - value) / (high - low) * (height - m.t - m.b);
    let html = '';
    for (let i = 0; i < 5; i++) {
      const value = low + (high - low) * i / 4;
      html += `<line class="chart-grid" x1="${m.l}" x2="${width - m.r}" y1="${Y(value)}" y2="${Y(value)}" stroke="var(--line)"/><text x="${m.l - 10}" y="${Y(value) + 4}" text-anchor="end" class="chart-label">${escape(fmt(value))}</text>`;
    }
    const ticks = axis === 'nodes' ? Math.min(5, maxX) : 5;
    for (let i = 0; i <= ticks; i++) {
      const value = axis === 'nodes' ? Math.round(maxX * i / ticks) : maxX * i / ticks;
      html += `<text x="${X(value)}" y="${height - 23}" text-anchor="middle" class="chart-label">${axis === 'time' ? duration(value) : value === 0 ? 'baseline' : value}</text>`;
    }
    if (series.baseline != null) html += `<line class="baseline-line" x1="${X(0)}" x2="${X(maxX)}" y1="${Y(series.baseline)}" y2="${Y(series.baseline)}" stroke="var(--muted)" stroke-dasharray="5 5"/><title>Baseline ${fmt(series.baseline)}</title>`;
    if (showReferences) for (const [label, value] of refs) html += `<line x1="${X(0)}" x2="${X(maxX)}" y1="${Y(value)}" y2="${Y(value)}" stroke="var(--gold)" stroke-dasharray="3 5"/><text x="${X(maxX)}" y="${Y(value) - 5}" text-anchor="end" class="chart-label">${escape(label)} ${fmt(value)}</text>`;
    let previous = series.baseline;
    let path = previous != null ? `M${X(0)},${Y(previous)}` : '';
    for (const point of series.points) {
      if (previous != null) path += ` H${X(point.x)}`;
      if (point.best != null) path += previous == null ? ` M${X(point.x)},${Y(point.best)}` : ` V${Y(point.best)}`;
      previous = point.best;
    }
    if (!series.points.length && previous != null) path += ` H${X(maxX)}`;
    if (path) html += `<path class="best-curve" d="${path}" fill="none" stroke="var(--accent)" stroke-width="2.5"/>`;
    for (const point of series.points) {
      const node = point.node, y = point.score == null ? height - m.b + 4 : Y(point.score);
      const label = `${node.id} · ${node.title} · ${point.score == null ? node.status + ': no valid official score' : fmt(point.score)}`;
      html += `<g class="chart-point${node.id === selectedId ? ' selected-point' : ''}" data-node="${escape(node.id)}" tabindex="0" role="button" aria-label="${escape(label)}"><title>${escape(label)}</title><circle class="hit-target" cx="${X(point.x)}" cy="${y}" r="12" fill="transparent"/>`;
      html += point.score == null ? `<text x="${X(point.x)}" y="${y + 4}" text-anchor="middle" fill="var(--bad)">×</text>` : `<circle class="score-dot" cx="${X(point.x)}" cy="${y}" r="4.5" fill="${color(node)}" stroke="var(--panel)" stroke-width="1.5"/>`;
      html += '</g>';
    }
    chart.innerHTML = html;
    chart.querySelectorAll('[data-node]').forEach(point => {
      const activate = () => { select(point.dataset.node); focusNode(point.dataset.node); revealInspector(); };
      point.addEventListener('click', activate);
      point.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activate(); } });
    });
  }
  $('chart-controls').querySelectorAll('[data-axis]').forEach(button => button.addEventListener('click', () => { axis = button.dataset.axis; drawChart(); }));

  function drawTable() {
    const query = $('node-search').value.trim().toLowerCase(), filter = $('status-filter').value;
    const nodes = D.nodes.filter(node => (!filter || filter === 'all' || node.status === filter) && `${node.id} ${node.title || ''} ${node.hypothesis || ''}`.toLowerCase().includes(query));
    $('table').innerHTML = '<thead><tr><th scope="col">Experiment</th><th scope="col">Status / audit</th><th scope="col">Official score</th><th scope="col">Gain vs parent</th><th scope="col">Elapsed</th><th scope="col">Parent</th></tr></thead><tbody>' + nodes.map(node => `<tr data-id="${escape(node.id)}" class="${node.id === selectedId ? 'active-row' : ''}"><td><button class="node-link" data-select="${escape(node.id)}">${escape(node.id)}${node.id === best?.id ? ' ★' : ''}</button><div class="table-title">${escape(node.title)}</div></td><td>${badge(node)}</td><td>${scored(node) ? fmt(node.score) : '—'}</td><td class="${scored(node) && node.delta_parent > 0 ? 'positive' : scored(node) && node.delta_parent < 0 ? 'negative' : ''}">${scored(node) ? signed(node.delta_parent) : '—'}</td><td>${duration(node.duration_s)}</td><td>${escape(node.parent || '—')}${node.retry_of ? '<div class="muted">retry ' + escape(node.retry_of) + '</div>' : ''}</td></tr>`).join('') + (nodes.length ? '' : '<tr><td colspan="6" class="empty">No experiments match these filters.</td></tr>') + '</tbody>';
    $('table').querySelectorAll('[data-select]').forEach(button => button.addEventListener('click', () => { select(button.dataset.select); focusNode(button.dataset.select); revealInspector(); }));
  }
  $('node-search').addEventListener('input', drawTable);
  $('status-filter').addEventListener('change', drawTable);
  $('idtext').textContent = D.insights || 'No insights recorded yet.';
  document.querySelectorAll('button[data-t]').forEach(button => button.addEventListener('click', () => {
    button.parentElement.querySelectorAll('button').forEach(other => { other.classList.toggle('on', other === button); other.setAttribute('aria-pressed', String(other === button)); });
    $('idtext').textContent = D[button.dataset.t] || 'No notes recorded yet.';
  }));
  drawTable();
  if (selectedId) select(selectedId); else $('detail').innerHTML = '<div class="empty">Select an experiment once the baseline is available.</div>';
  drawChart(); fitTree();
  let resizeFrame;
  const observer = new ResizeObserver(() => {
    cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(() => {
      const centerY = camera.y + camera.h / 2, {w, h} = viewSize();
      camera.h = camera.w * h / w; camera.y = centerY - camera.h / 2;
      applyCamera(); drawChart();
    });
  });
  observer.observe(viewport); observer.observe($('chart').parentElement);
})();
