// pi-rsi tree view. Expects window.__RSI_DATA__ (see render.py).
const D = window.__RSI_DATA__;
const byId = Object.fromEntries(D.nodes.map(n => [n.id, n]));
const fmt = x => (x === null || x === undefined) ? '-' : (Math.abs(x) >= 1000 ? Math.round(x).toLocaleString() : (+x).toPrecision(4));
const esc = s => String(s ?? '').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const cls = n => n.status === 'running' || n.status === 'evaluating' ? 'running' : n.status === 'planned' ? 'planned' : (n.verdict || n.status);
const color = n => ({improved:'var(--ok)',no_change:'var(--plan)',worse:'var(--warn)',failed:'var(--bad)',running:'var(--run)',planned:'transparent',baseline:'#444'})[cls(n)] || 'var(--plan)';

document.getElementById('title').textContent = `pi-rsi · ${D.experiment} · ${D.task}`;
const st = D.state || {};
document.getElementById('subtitle').textContent = `worker ${D.runner} · utility ${D.utility} · search w0=${D.search.width_root} w=${D.search.width} d=${D.search.depth} max=${D.search.max_nodes} par=${D.search.max_parallel} patience=${D.search.patience} · ${st.status || ''} ${st.stop_reason ? '(' + st.stop_reason + ')' : ''} · rendered ${D.generated_at}`;
const best = D.best ? byId[D.best] : null;
const finished = D.nodes.filter(n => n.id !== 'root' && (n.status === 'done' || n.status === 'failed'));
const kp = [['baseline ' + D.score_key, fmt(D.root_score)], ['best', best ? `${fmt(best.score)} (${best.id})` : '-'],
  ['nodes done/failed', `${D.nodes.filter(n=>n.status==='done'&&n.id!=='root').length}/${D.nodes.filter(n=>n.status==='failed').length}`],
  ['in flight', D.nodes.filter(n=>['planned','running','evaluating'].includes(n.status)).length]];
if (D.final && D.final.best_final_score !== undefined) kp.push(['held-out best vs base', `${fmt(D.final.best_final_score)} vs ${fmt(D.final.root_final_score)}`]);
for (const [k,v] of Object.entries(D.reference_scores || {})) kp.push(['ref ' + k, fmt(v)]);
const cost = Object.values(D.costs || {}).reduce((a,c)=>a+(c.cost_usd||0),0);
if (cost) kp.push(['api cost est.', '$' + cost.toFixed(2)]);
document.getElementById('kpis').innerHTML = kp.map(([l,v]) => `<div class="kpi"><div class="l">${esc(l)}</div><div class="v">${esc(v)}</div></div>`).join('');

// tree ---------------------------------------------------------------
const W = 150, H = 54, GX = 40, GY = 90;
const xs = D.nodes.map(n => n.x), maxX = Math.max(0, ...xs), maxY = Math.max(0, ...D.nodes.map(n => n.y));
const svg = document.getElementById('tree');
const width = (maxX + 1) * (W + GX) + GX, height = (maxY + 1) * (H + GY) + 20;
svg.setAttribute('width', width); svg.setAttribute('height', height);
const px = n => GX/2 + n.x * (W + GX), py = n => 10 + n.y * (H + GY);
let parts = [];
for (const n of D.nodes) if (n.parent && byId[n.parent]) {
  const p = byId[n.parent];
  parts.push(`<path class="edge" d="M${px(p)+W/2},${py(p)+H} C${px(p)+W/2},${py(p)+H+GY/2} ${px(n)+W/2},${py(n)-GY/2} ${px(n)+W/2},${py(n)}"/>`);
}
for (const n of D.nodes) {
  const isBest = best && n.id === best.id;
  const stroke = isBest ? 'var(--gold)' : 'var(--line)';
  const dash = n.status === 'planned' ? 'stroke-dasharray="5,4"' : '';
  const label = n.id === 'root' ? 'baseline' : (n.title.length > 22 ? n.title.slice(0,21) + '…' : n.title);
  const s2 = n.status === 'running' ? 'running' : n.status === 'evaluating' ? 'evaluating' : n.status === 'planned' ? 'planned' : `${fmt(n.score)}${n.delta_parent != null ? ' (' + (n.delta_parent>0?'+':'') + fmt(n.delta_parent) + ')' : ''}`;
  parts.push(`<g class="node" data-id="${n.id}" transform="translate(${px(n)},${py(n)})"><rect width="${W}" height="${H}" rx="8" fill="var(--panel)" stroke="${stroke}" ${dash}/>` +
    `<rect x="0" y="0" width="8" height="${H}" rx="4" fill="${color(n)}"/>` +
    `<text x="14" y="18" font-weight="600">${esc(n.id)}${isBest ? ' ★' : ''}${n.retry_of ? ' ↻' : ''}</text>` +
    `<text x="14" y="34" style="font-size:11px">${esc(label)}</text>` +
    `<text x="14" y="48" style="font-size:11px;fill:var(--muted)">${esc(s2)}</text></g>`);
}
svg.innerHTML = parts.join('');
svg.querySelectorAll('.node').forEach(g => g.addEventListener('click', () => select(g.dataset.id)));

// detail ----------------------------------------------------------------
let tab = 'summary';
function select(id) {
  svg.querySelectorAll('.node').forEach(g => g.classList.toggle('sel', g.dataset.id === id));
  const n = byId[id]; if (!n) return;
  const docs = n.docs || {};
  const tabs = [['summary','summary'],['handoff','handoff'],['progress','progress tail'],['metrics','metrics'],['hypothesis','hypothesis'],['proposals','proposals'],['failure','failure']];
  const body = {
    summary: (n.summary || '(no summary yet)') + (n.audit && n.audit.claim_check ? `\n\nclaim check: ${n.audit.claim_check.consistent ? 'consistent' : 'MISMATCH'} — ${n.audit.claim_check.note || ''}` : '') + (docs.human ? `\n\nHuman note:\n${docs.human}` : ''),
    handoff: docs.handoff || '(no handoff)', progress: docs.progress_tail || '(no progress log)',
    metrics: JSON.stringify(n.metrics || {}, null, 1), hypothesis: docs.hypothesis || n.hypothesis,
    proposals: (n.proposals || []).map((p,i) => `${(n.proposals_used||[]).includes(i) ? '[used]' : '[open]'} ${p.title} (${p.type})\n  ${p.hypothesis}\n  gain: ${p.expected_gain}; risk: ${p.risk}`).join('\n\n') || '(none)',
    failure: (docs.failure || n.failure || '(none)') + (n.diagnosis && n.diagnosis.cause ? `\n\ndiagnosis: ${JSON.stringify(n.diagnosis, null, 1)}` : ''),
  };
  const u = n.usage || {};
  document.getElementById('detail').innerHTML =
    `<div><b>${esc(n.id)}</b> <span class="tag ${cls(n)}">${esc(n.status === 'done' ? (n.verdict || 'done') : n.status)}</span> ${n.retry_of ? '<span class="tag">retry of ' + esc(n.retry_of) + '</span>' : ''} · depth ${n.depth} · parent ${esc(n.parent || '-')}</div>` +
    `<div style="margin:6px 0"><b>${esc(n.title)}</b></div>` +
    `<div class="muted">score ${fmt(n.score)} · Δparent ${fmt(n.delta_parent)} · Δbest-at-finish ${fmt(n.delta_best)} · quick(worker) ${fmt(n.quick_score)} · commit ${esc((n.commit||'').slice(0,8))} · ${esc(n.duration_fmt)} · turns ${n.worker && n.worker.turns != null ? n.worker.turns : '-'} · tools ${n.worker && n.worker.tool_calls != null ? n.worker.tool_calls : '-'} · tokens in/out ${u.input_tokens ?? u.input ?? '-'}/${u.output_tokens ?? u.output ?? '-'}${n.cost_usd ? ' · $' + n.cost_usd.toFixed(2) : ''}</div>` +
    `<div class="tabs">${tabs.map(([k,l]) => `<button data-t="${k}" class="${k===tab?'on':''}">${l}</button>`).join('')}</div><pre id="dbody">${esc(body[tab])}</pre>`;
  document.querySelectorAll('#detail .tabs button').forEach(b => b.addEventListener('click', () => { tab = b.dataset.t; select(id); }));
}

// chart -----------------------------------------------------------------
(function(){
  const c = document.getElementById('chart'); const Wc = c.clientWidth || 600, Hc = 220, m = {l:56,r:16,t:12,b:26};
  const seq = finished.slice().sort((a,b) => (a.finished_at||'').localeCompare(b.finished_at||''));
  const pts = seq.map((n,i) => ({i, n}));
  const vals = pts.filter(p=>p.n.score!=null).map(p=>p.n.score).concat([D.root_score]).concat(Object.values(D.reference_scores||{})).filter(v=>v!=null);
  if (!vals.length) { c.innerHTML = '<text x="10" y="20" class="muted">no finished nodes yet</text>'; return; }
  let lo = Math.min(...vals), hi = Math.max(...vals); if (hi === lo) { hi = lo + 1; }
  const pad = (hi-lo)*0.08; lo -= pad; hi += pad;
  const X = i => m.l + (pts.length > 1 ? i/(pts.length-1) : 0.5) * (Wc-m.l-m.r), Y = v => m.t + (1-(v-lo)/(hi-lo))*(Hc-m.t-m.b);
  let s = '';
  for (let k=0;k<5;k++){ const v = lo + (hi-lo)*k/4; s += `<line x1="${m.l}" x2="${Wc-m.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/><text x="${m.l-6}" y="${Y(v)+4}" text-anchor="end" style="font-size:11px;fill:var(--muted)">${fmt(v)}</text>`; }
  const refs = Object.assign({baseline: D.root_score}, D.reference_scores||{});
  for (const [k,v] of Object.entries(refs)) if (v!=null && v>=lo && v<=hi) s += `<line x1="${m.l}" x2="${Wc-m.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--gold)" stroke-dasharray="4,4"/><text x="${Wc-m.r}" y="${Y(v)-3}" text-anchor="end" style="font-size:11px;fill:var(--gold)">${esc(k)} ${fmt(v)}</text>`;
  let bestSoFar = null; const bl = [];
  for (const p of pts) { if (p.n.score!=null && (bestSoFar==null || (D.higher_is_better ? p.n.score>bestSoFar : p.n.score<bestSoFar))) bestSoFar = p.n.score; if (bestSoFar!=null) bl.push(`${X(p.i)},${Y(bestSoFar)}`); }
  if (bl.length) s += `<polyline points="${bl.join(' ')}" fill="none" stroke="var(--accent)" stroke-width="2"/>`;
  for (const p of pts) { if (p.n.score==null) { s += `<text x="${X(p.i)}" y="${Hc-m.b+14}" text-anchor="middle" style="fill:var(--bad);font-size:11px">✕</text>`; continue; }
    s += `<circle cx="${X(p.i)}" cy="${Y(p.n.score)}" r="4" fill="${color(p.n)}" stroke="var(--panel)"><title>${esc(p.n.id)} ${fmt(p.n.score)} ${esc(p.n.title)}</title></circle><text x="${X(p.i)}" y="${Hc-m.b+14}" text-anchor="middle" style="font-size:10px;fill:var(--muted)">${esc(p.n.id)}</text>`; }
  c.innerHTML = s;
})();

// insights / table --------------------------------------------------------
const idt = document.getElementById('idtext'); idt.textContent = D.insights || '(none)';
document.querySelectorAll('.tabs button[data-t="insights"],.tabs button[data-t="deadends"]').forEach(b => b.addEventListener('click', () => {
  b.parentElement.querySelectorAll('button').forEach(x => x.classList.toggle('on', x===b)); idt.textContent = (b.dataset.t === 'insights' ? D.insights : D.deadends) || '(none)'; }));
const rows = D.nodes.map(n => `<tr class="${best && n.id===best.id ? 'best' : ''}"><td><a href="#" data-id="${n.id}">${esc(n.id)}</a></td><td>${esc(n.parent||'-')}</td><td>${n.depth}</td><td><span class="tag ${cls(n)}">${esc(n.status==='done' ? (n.verdict||'done') : n.status)}</span></td><td>${fmt(n.score)}</td><td>${fmt(n.delta_parent)}</td><td>${esc(n.title)}</td><td>${esc(n.duration_fmt)}</td><td>${esc((n.summary||'').slice(0,160))}</td></tr>`);
document.getElementById('table').innerHTML = `<tr><th>id</th><th>parent</th><th>d</th><th>status</th><th>score</th><th>Δparent</th><th>title</th><th>time</th><th>summary</th></tr>` + rows.join('');
document.querySelectorAll('#table a').forEach(a => a.addEventListener('click', e => { e.preventDefault(); select(a.dataset.id); document.getElementById('detail').scrollIntoView({behavior:'smooth'}); }));
if (best) select(best.id); else if (D.nodes.length) select(D.nodes[D.nodes.length-1].id);
