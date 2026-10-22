(() => {
  const D = window.__RSI_SB__;
  if (!D || !window.d3) return;
  const zh = document.documentElement.lang.startsWith('zh');
  const T = (en, z) => (zh ? z : en);
  const CAT = {
    best: T('new best', '新最佳'), chg: T('changed, no gain', '有变化但未提升'),
    same: T('output identical to parent', '输出与父节点相同'), fail: T('failed', '失败'),
    run: T('running', '运行中'), root: T('baseline', '基线')
  };
  const fmt = v => (v === null || v === undefined ? '—' : v.toFixed(4));
  // delta is parent − node: positive means the node is better (lower is better).
  const sgn = v => (v === null || v === undefined ? '—' : (v > 0 ? '−' : v < 0 ? '+' : '±') + Math.abs(v).toFixed(4));
  const byId = Object.fromEntries(D.nodes.map(n => [n.id, n]));
  const onPath = new Set();
  for (let p = D.best; p; p = byId[p].parent) onPath.add(p);
  const titleOf = n => (zh && n.title_zh ? n.title_zh : n.title);
  const summaryOf = n => (zh && n.summary_zh ? n.summary_zh : n.summary);

  function tooltip(box) {
    const tip = document.createElement('div');
    tip.className = 'sb-tip';
    tip.setAttribute('role', 'status');
    box.appendChild(tip);
    return {
      show(event, n) {
        tip.replaceChildren();
        const h = document.createElement('div');
        h.className = 'sb-tip__title';
        h.textContent = `${n.id} · ${titleOf(n)}`;
        const m = document.createElement('div');
        m.className = 'sb-tip__meta';
        const label = n.id === D.best ? T('current best', '当前最佳') : CAT[n.cat];
        const fin = D.final_level && D.final_level[n.id] !== undefined ? ` · ${T('sealed final', '密封 final')} ${fmt(D.final_level[n.id])}` : '';
        m.textContent = `${T('score', '分数')} ${fmt(n.score)} · Δ ${T('vs parent', '相对父节点')} ${sgn(n.delta)} · ${label}${fin}`;
        const s = document.createElement('div');
        s.textContent = summaryOf(n);
        tip.append(h, m, s);
        const b = box.getBoundingClientRect();
        const cx = (event.clientX ?? b.left + b.width / 2) - b.left;
        const cy = (event.clientY ?? b.top + 40) - b.top;
        tip.classList.add('is-on');
        let x = cx + 14, y = cy + 14;
        if (x + tip.offsetWidth > b.width) x = Math.max(4, cx - tip.offsetWidth - 14);
        if (y + tip.offsetHeight > b.height) y = Math.max(4, cy - tip.offsetHeight - 14);
        tip.style.left = x + 'px';
        tip.style.top = y + 'px';
      },
      hide() { tip.classList.remove('is-on'); }
    };
  }

  function chart(box) {
    const rows = D.nodes.filter(n => n.id !== 'root' && n.cat !== 'run');
    const W = 760, H = 320, m = { t: 22, r: 14, b: 34, l: 52 };
    const x = d3.scaleBand().domain(rows.map(n => n.id)).range([m.l, W - m.r]).padding(0.2);
    const scores = rows.map(n => n.score).filter(v => v !== null);
    const lo = Math.floor(Math.min(...scores) * 200) / 200, hi = Math.ceil(Math.max(D.baseline, ...scores) * 200) / 200;
    const y = d3.scaleLinear().domain([lo, hi]).range([H - m.b, m.t]);
    const svg = d3.select(box).append('svg').attr('viewBox', [0, 0, W, H]).attr('class', 'sb-svg')
      .attr('role', 'img').attr('aria-label', T('Official score of each node in finish order (lower is better)', '按完成顺序排列的各节点官方分数（越低越好）'));
    svg.append('g').attr('class', 'sb-grid').selectAll('line').data(y.ticks(6)).join('line')
      .attr('x1', m.l).attr('x2', W - m.r).attr('y1', d => y(d)).attr('y2', d => y(d));
    svg.append('g').attr('class', 'sb-axis').attr('transform', `translate(${m.l},0)`)
      .call(d3.axisLeft(y).ticks(6).tickFormat(d3.format('.3f')).tickSize(0)).call(g => g.select('.domain').remove());
    svg.append('g').attr('class', 'sb-axis').attr('transform', `translate(0,${H - m.b})`)
      .call(d3.axisBottom(x).tickValues(rows.map(n => n.id).filter((_, i) => i % 3 === 0)).tickSize(0))
      .call(g => g.select('.domain').remove());
    let best = D.baseline;
    const steps = [['__start', best]].concat(rows.map(n => { if (n.score !== null && n.score < best) best = n.score; return [n.id, best]; }));
    const px0 = id => (id === '__start' ? m.l : x(id) + x.bandwidth() / 2);
    svg.append('path').attr('class', 'sb-best')
      .attr('d', d3.line().curve(d3.curveStepAfter).x(d => px0(d[0])).y(d => y(d[1]))(steps));
    (D.marks || []).forEach((mk, k) => {
      const i = rows.findIndex(n => n.id === mk.after);
      if (i < 0 || i + 1 >= rows.length) return;
      const px = (x(rows[i].id) + x(rows[i + 1].id) + x.bandwidth()) / 2;
      const right = px > W - 190;
      svg.append('line').attr('class', 'sb-mark').attr('x1', px).attr('x2', px).attr('y1', m.t).attr('y2', H - m.b);
      svg.append('text').attr('class', 'sb-mark-label').attr('text-anchor', right ? 'end' : 'start')
        .attr('x', right ? px - 4 : px + 4).attr('y', m.t + 10 + (k % 3) * 13).text(mk.label[zh ? 1 : 0]);
    });
    const shape = { best: d3.symbolCircle, same: d3.symbolDiamond, chg: d3.symbolTriangle, fail: d3.symbolCross, run: d3.symbolCircle };
    const tip = tooltip(box);
    svg.append('g').selectAll('path').data(rows).join('path')
      .attr('class', n => `sb-pt sb-c-${n.cat}`)
      .attr('transform', n => `translate(${x(n.id) + x.bandwidth() / 2},${y(n.score ?? hi)})${n.cat === 'fail' ? ' rotate(45)' : ''}`)
      .attr('d', n => d3.symbol(shape[n.cat] || d3.symbolCircle, n.cat === 'best' ? 90 : 60)())
      .attr('tabindex', 0)
      .on('mousemove focus click', (e, n) => tip.show(e, n)).on('mouseleave blur', () => tip.hide());
  }

  function mindmap(box) {
    const root = d3.stratify().id(n => n.id).parentId(n => n.parent)(D.nodes).sort((a, b) => d3.ascending(a.id, b.id));
    const DX = 170, DY = 21;
    d3.tree().nodeSize([DY, DX])(root);
    let x0 = Infinity, x1 = -Infinity;
    root.each(d => { x0 = Math.min(x0, d.x); x1 = Math.max(x1, d.x); });
    const svg = d3.select(box).append('svg').attr('class', 'sb-svg sb-map')
      .attr('viewBox', [-28, x0 - 26, root.height * DX + 64, x1 - x0 + 44])
      .attr('role', 'img').attr('aria-label', T('Search tree from the baseline to the best node', '从基线到最佳节点的搜索树'));
    svg.append('g').selectAll('path').data(root.links()).join('path')
      .attr('class', l => 'sb-link' + (onPath.has(l.target.id) ? ' is-path' : ''))
      .attr('d', d3.linkHorizontal().x(d => d.y).y(d => d.x));
    const tip = tooltip(box);
    const g = svg.append('g').selectAll('g').data(root.descendants()).join('g')
      .attr('class', d => `sb-node sb-c-${d.data.cat}` + (onPath.has(d.id) ? ' is-path' : ''))
      .attr('transform', d => `translate(${d.y},${d.x})`).attr('tabindex', 0)
      .on('mousemove focus click', (e, d) => tip.show(e, d.data)).on('mouseleave blur', () => tip.hide());
    g.append('rect').attr('x', -22).attr('y', -8.5).attr('width', 44).attr('height', 17).attr('rx', 8.5);
    g.append('text').attr('text-anchor', 'middle').attr('dy', '0.35em').text(d => d.id);
    g.filter(d => d.id === D.best).append('path').attr('class', 'sb-star')
      .attr('transform', 'translate(21,-12)').attr('d', d3.symbol(d3.symbolStar, 150)());
  }

  const c = document.getElementById('sb-chart');
  const t = document.getElementById('sb-tree');
  if (c) chart(c);
  if (t) mindmap(t);
})();
