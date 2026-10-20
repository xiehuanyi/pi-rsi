(() => {
  const D = window.__RSI_CASMI__;
  if (!D || !window.d3) return;
  const zh = document.documentElement.lang.startsWith('zh');
  const T = (en, z) => (zh ? z : en);
  const CAT = {
    best: T('new best', '新最佳'), chg: T('changed, no gain', '有变化但未提升'),
    same: T('output identical to parent', '输出与父节点相同'), fail: T('failed', '失败'),
    run: T('running', '运行中'), root: T('baseline', '基线')
  };
  const fmt = v => (v === null || v === undefined ? '—' : v.toFixed(4));
  const sgn = v => (v === null || v === undefined ? '—' : (v > 0 ? '+' : v < 0 ? '−' : '±') + Math.abs(v).toFixed(4));
  const byId = Object.fromEntries(D.nodes.map(n => [n.id, n]));
  const lastId = D.nodes.filter(n => n.id !== 'root').map(n => n.id).sort().pop();
  const onPath = new Set();
  for (let p = lastId; p; p = byId[p].parent) onPath.add(p);

  function tooltip(box) {
    const tip = document.createElement('div');
    tip.className = 'casmi-tip';
    tip.setAttribute('role', 'status');
    box.appendChild(tip);
    return {
      show(event, n) {
        tip.replaceChildren();
        const h = document.createElement('div');
        h.className = 'casmi-tip__title';
        h.textContent = `${n.id} · ${n.title}`;
        const m = document.createElement('div');
        m.className = 'casmi-tip__meta';
        const label = n.id === D.best ? T('current best', '当前最佳') : CAT[n.cat];
        m.textContent = `${T('score', '分数')} ${fmt(n.score)} · Δ ${T('parent', '父节点')} ${sgn(n.delta)} · ${label}`;
        const s = document.createElement('div');
        s.textContent = n.summary;
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
    const y = d3.scaleLinear().domain([0.34, 0.425]).range([H - m.b, m.t]);
    const svg = d3.select(box).append('svg').attr('viewBox', [0, 0, W, H]).attr('class', 'casmi-svg')
      .attr('role', 'img').attr('aria-label', T('Official score of each node in finish order', '按完成顺序排列的各节点官方分数'));
    svg.append('g').attr('class', 'casmi-grid').selectAll('line').data(y.ticks(5)).join('line')
      .attr('x1', m.l).attr('x2', W - m.r).attr('y1', d => y(d)).attr('y2', d => y(d));
    svg.append('g').attr('class', 'casmi-axis').attr('transform', `translate(${m.l},0)`)
      .call(d3.axisLeft(y).ticks(5).tickFormat(d3.format('.3f')).tickSize(0)).call(g => g.select('.domain').remove());
    svg.append('g').attr('class', 'casmi-axis').attr('transform', `translate(0,${H - m.b})`)
      .call(d3.axisBottom(x).tickValues(rows.map(n => n.id).filter((_, i) => i % 3 === 0)).tickSize(0))
      .call(g => g.select('.domain').remove());
    let best = D.baseline;
    const steps = rows.map(n => { if (n.score !== null && n.score > best) best = n.score; return [n.id, best]; });
    svg.append('path').attr('class', 'casmi-best')
      .attr('d', d3.line().curve(d3.curveStepAfter).x(d => x(d[0]) + x.bandwidth() / 2).y(d => y(d[1]))(steps));
    D.marks.forEach((mk, k) => {
      const i = rows.findIndex(n => n.id === mk.after);
      if (i < 0 || i + 1 >= rows.length) return;
      const px = (x(rows[i].id) + x(rows[i + 1].id) + x.bandwidth()) / 2;
      const right = px > W - 110;
      svg.append('line').attr('class', 'casmi-mark').attr('x1', px).attr('x2', px).attr('y1', m.t).attr('y2', H - m.b);
      svg.append('text').attr('class', 'casmi-mark-label').attr('text-anchor', right ? 'end' : 'start')
        .attr('x', right ? px - 4 : px + 4).attr('y', m.t + 10 + (k % 2) * 13).text(mk.label[zh ? 1 : 0]);
    });
    const shape = { best: d3.symbolCircle, same: d3.symbolDiamond, chg: d3.symbolTriangle, fail: d3.symbolCross, run: d3.symbolCircle };
    const tip = tooltip(box);
    svg.append('g').selectAll('path').data(rows).join('path')
      .attr('class', n => `casmi-pt casmi-c-${n.cat}`)
      .attr('transform', n => `translate(${x(n.id) + x.bandwidth() / 2},${y(n.score ?? 0.347)})${n.cat === 'fail' ? ' rotate(45)' : ''}`)
      .attr('d', n => d3.symbol(shape[n.cat] || d3.symbolCircle, n.cat === 'best' ? 90 : 60)())
      .attr('tabindex', 0)
      .on('mousemove focus click', (e, n) => tip.show(e, n)).on('mouseleave blur', () => tip.hide());
  }

  function mindmap(box) {
    const root = d3.stratify().id(n => n.id).parentId(n => n.parent)(D.nodes).sort((a, b) => d3.ascending(a.id, b.id));
    const DX = 58, DY = 26;
    d3.tree().nodeSize([DY, DX])(root);
    let x0 = Infinity, x1 = -Infinity;
    root.each(d => { x0 = Math.min(x0, d.x); x1 = Math.max(x1, d.x); });
    const svg = d3.select(box).append('svg').attr('class', 'casmi-svg casmi-map')
      .attr('viewBox', [-28, x0 - 26, root.height * DX + 64, x1 - x0 + 44])
      .attr('role', 'img').attr('aria-label', T('Search tree from the baseline to the latest node', '从基线到最新节点的搜索树'));
    svg.append('g').selectAll('path').data(root.links()).join('path')
      .attr('class', l => 'casmi-link' + (onPath.has(l.target.id) ? ' is-path' : ''))
      .attr('d', d3.linkHorizontal().x(d => d.y).y(d => d.x));
    const tip = tooltip(box);
    const g = svg.append('g').selectAll('g').data(root.descendants()).join('g')
      .attr('class', d => `casmi-node casmi-c-${d.data.cat}` + (onPath.has(d.id) ? ' is-path' : ''))
      .attr('transform', d => `translate(${d.y},${d.x})`).attr('tabindex', 0)
      .on('mousemove focus click', (e, d) => tip.show(e, d.data)).on('mouseleave blur', () => tip.hide());
    g.append('rect').attr('x', -22).attr('y', -9.5).attr('width', 44).attr('height', 19).attr('rx', 9.5);
    g.append('text').attr('text-anchor', 'middle').attr('dy', '0.35em').text(d => d.id);
    g.filter(d => d.id === D.best).append('path').attr('class', 'casmi-star')
      .attr('transform', 'translate(21,-12)').attr('d', d3.symbol(d3.symbolStar, 150)());
  }

  const c = document.getElementById('casmi-chart');
  const t = document.getElementById('casmi-tree');
  if (c) chart(c);
  if (t) mindmap(t);
})();
