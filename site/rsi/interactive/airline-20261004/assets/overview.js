const rsiLang=document.documentElement.lang.startsWith("zh")?"zh":"en";
const rsiText={"研究搜索树": "Research search tree", "曲线图例": "Chart legend", "支持和反对证据与所选知识条目的关系": "Supporting and opposing evidence for the selected entry", "pi-rsi · 航空满意度实验": "pi-rsi · airline satisfaction", "验证 AUC 的变化": "Validation AUC progression", "搜索分支": "Search branches", "历史最佳": "Best so far", "各节点评测": "Node measurements", "实验运行中": "Running", "× 失败　◇ 评测后仍在分析": "× Failed　◇ Processing", "★ 最高分节点　× 失败节点　◇ 处理中　连线表示从哪个节点继续实验": "★ Highest score　× Failed　◇ Processing · Edges show code ancestry", "研究 Wiki · 知识与证据": "Research Wiki · knowledge and evidence", "知识条目": "Knowledge entry", "证据关系": "Evidence relationships", "支持证据": "Supporting evidence", "反对证据": "Opposing evidence", "当前条目": "Selected entry", "实线：支持　虚线：反对 · 证据条目数不代表独立重复次数": "Solid: support · Dashed: opposition · Record counts are not independent replications", "适用范围、其他解释与下一步验证": "Scope, alternatives and next test", "知识版本与结论变化": "Published revisions and belief changes", "发布版本": "Published revision", "研究议程与尚未解决的问题": "Research agenda and open questions", "图表暂未加载": "Chart unavailable", "暂无有效评测": "No valid measurement", " · 已分配 ": " · Allocated ", " 个节点 · ": " nodes · ", " 完成 / ": " done / ", " 失败 / ": " failed / ", " 处理中 · Wiki 待处理 ": " pending completion · Wiki pending ", " · 相对基线 ": " · versus baseline ", "基线": "Baseline", "本地验证 AUC": "Local validation AUC", "研究节点编号": "Research node number", "节点位置 ": "Node position ", "历史最佳 ": "Best so far ", "相邻有效评测插值 ": "Interpolation between valid scores ", "最近节点 ": "Nearest node ", "观察": "Observation", "假设": "Hypothesis", "经验": "Experience", "获证据支持": "Supported", "待验证": "Untested", "证据混合": "Mixed evidence", "被反驳": "Refuted", "已被替代": "Superseded", " 条知识 · ": " entries · ", " 条证据记录 · ": " evidence records · ", " 个发布版本 · ": " published revisions · ", "（沙特时间）": " (Riyadh time)", "知识版本与结论变化（": "Published revisions and belief changes (", " 个版本）": " revisions)", "无": "None", "实验记录": "Experiment record", "文档记录": "Documentation record", " 条 · ": " entries · ", " 项更新": " changes", "（当前）": " (current)", "无有效分数": "No valid score", " · 测量状态 ": " · Measurement ", "有效": "valid", "不可用": "unavailable", "失效": "invalid", "未记录": "not recorded", "打开原文来源": "Open original source", "记录身份与哈希": "Record identity and hashes", "原始记录 SHA-256：": "Raw packet SHA-256: ", "代码提交：": "Code commit: ", "来源文本 SHA-256：": "Source text SHA-256: ", "无记录": "No records", "文档 ": "Document ", "证据：": " evidence: ", "支持": "Support", "反对": "Opposition", " · 支持 ": " · Supports ", " / 反对 ": " / Opposes ", "适用范围": "Scope", "其他解释": "Alternative explanations", "下一步区分性验证": "Next discriminating test", "查看被替代的条目": "View predecessor entry", "新增": "New", "本版本没有记录条目状态更新。": "No recorded entry-status changes in this revision.", "研究动机": "Motivation", "方法与判断依据": "Method and interpretation", "开放问题": "Open questions", "下一步实验": "Next experiments", "已完成": "Done", "失败": "Failed", "实验中": "Running", "结果分析中": "Analyzing", "评测中": "Evaluating", "待运行": "Planned", "待恢复": "Completion pending", "基线到第 ": "Baseline through node ", " 个节点的搜索分支；带星号的是最高分节点": " search branches; the star marks the highest score", "验证 AUC 从 ": "Validation AUC from ", " 提高到 ": " to ", "。失败节点不计入历史最佳，未完成节点只显示暂定评测。": ". Failed nodes do not improve the incumbent; incomplete nodes display provisional measurements only."};
function tr(s){return rsiLang==="zh"?s:(rsiText[s]||s);}
if(rsiLang==='en'){
window.__RSI_BLOG_DATA__.nodes.forEach(n=>{n.label=n.title_en||n.label;n.state=tr(n.state);n.note=n.note_en||n.note;});
window.__RSI_BLOG_DATA__.status='Archived snapshot';
window.__RSI_BLOG_DATA__.timestamp=window.__RSI_BLOG_DATA__.timestamp.replace('（沙特时间）',' (Riyadh time)').replace(' 月 ','/').replace(' 日 ',' ');
}

(() => {
  const root=document.getElementById('pi-rsi-oct04');
  const data=window.__RSI_BLOG_DATA__;
  const nodes=data.nodes, byId=new Map(nodes.map(n=>[n.id,n]));
  const chart=root.querySelector('#rsi-chart'), tree=root.querySelector('#rsi-tree');
  const detail=root.querySelector('#rsi-detail'), tooltip=root.querySelector('#rsi-tooltip');
  if (!window.d3 || !nodes.length) { chart.textContent=tr("图表暂未加载"); return; }
  const saved=window.openai?.widgetState;
  let selected=byId.has(saved?.privateContent?.selected)?saved.privateContent.selected:data.best;
  let visible={best:saved?.privateContent?.visible?.best!==false,scores:saved?.privateContent?.visible?.scores!==false};
  let pinned=false;
  const base=byId.get('root').score;
  const scoreText=n=>n.score===null?tr("暂无有效评测"):n.score.toFixed(7);
  const deltaText=v=>(v>=0?'+':'')+v.toFixed(7);
  root.querySelector('#rsi-snapshot').textContent=data.timestamp+' · '+data.status+tr(" · 已分配 ")+data.used+' / '+data.limit+tr(" 个节点 · ")+data.done+tr(" 完成 / ")+data.failed+tr(" 失败 / ")+data.active+tr(" 处理中 · Wiki 待处理 ")+data.pending;
  function save() {
    if (!window.openai?.setWidgetState) return;
    window.openai.setWidgetState({modelContent:{experiment:data.experiment,selectedNode:selected,score:byId.get(selected).score,snapshot:data.timestamp},privateContent:{selected,visible}}).catch(()=>{});
  }
  function ancestry(id) { const ids=new Set(); while (byId.has(id)) { ids.add(id); id=byId.get(id).parent; } return ids; }
  function showDetail() {
    const n=byId.get(selected); detail.replaceChildren();
    const title=document.createElement('div'); title.className='rsi-detail-title'; title.textContent=n.id+' · '+n.label;
    const value=document.createElement('div'); value.className="pp-num";
    value.textContent=n.state+' · AUC '+scoreText(n)+(n.score!==null?tr(" · 相对基线 ")+deltaText(n.score-base):'');
    const note=document.createElement('div'); note.className="pp-small"; note.textContent=n.note;
    detail.append(title,value,note);
    tree.querySelectorAll('button[data-node]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.node===selected)));
    chart.querySelectorAll('[data-selected-ring]').forEach(el=>el.setAttribute('visibility',el.dataset.node===selected?'visible':'hidden'));
  }
  function select(id,remember=true) { if(!byId.has(id))return; selected=id; showDetail(); if(remember)save(); }
  function addNodeButton(n,parent) {
    const b=document.createElement('button'); b.type='button'; b.className="pp-chip pp-small"; b.dataset.node=n.id;
    b.textContent=(n.id==='root'?tr("基线"):n.id)+(n.id===data.best?' ★':n.status==='failed'?' ×':n.status!=='done'?' ◇':'');
    b.setAttribute('aria-label',n.id+' '+n.label+'，'+n.state+'，'+scoreText(n));
    b.setAttribute('data-tooltip',n.label); b.setAttribute('aria-pressed',String(n.id===selected));
    b.addEventListener('click',()=>select(n.id)); parent.append(b);
  }
  function drawTree() {
    tree.replaceChildren(); const w=tree.getBoundingClientRect().width;
    const hierarchy=d3.stratify().id(n=>n.id).parentId(n=>n.parent)(nodes);
    if(w<610) {
      tree.style.height='auto';
      hierarchy.eachBefore(d=>{const row=document.createElement('div');row.className='rsi-mobile-row';row.style.paddingLeft=(d.depth*13)+'px';
        addNodeButton(d.data,row);if(d.parent){const p=document.createElement('span');p.className="rsi-parent pp-small";p.textContent='← '+(d.parent.id==='root'?tr("基线"):d.parent.id);row.append(p);}tree.append(row);});
      return;
    }
    const h=Math.max(430,nodes.length*23);tree.style.height=h+'px';
    d3.tree().size([h-60,w-110])(hierarchy);
    const svg=d3.select(tree).append('svg').attr('class','rsi-branches').attr('width',w).attr('height',h).attr('viewBox',`0 0 ${w} ${h}`).attr('role','img').attr('aria-label',tr("基线到第 ")+data.used+tr(" 个节点的搜索分支；带星号的是最高分节点"));
    const bestPath=ancestry(data.best);
    svg.append('g').attr('transform','translate(50,30)').selectAll('path').data(hierarchy.links()).join('path')
      .attr('d',d3.linkHorizontal().x(d=>d.y).y(d=>d.x)).attr('fill','none').attr('stroke',d=>bestPath.has(d.target.id)?'var(--viz-series-1)':'var(--border)').attr('stroke-width',1.5);
    hierarchy.each(d=>{const wrap=document.createElement('div');wrap.className='rsi-node';wrap.style.left=(d.y+50)+'px';wrap.style.top=(d.x+30)+'px';addNodeButton(d.data,wrap);tree.append(wrap);});
  }
  function labelLayout(svg) {
    const labels=svg.selectAll('.axis text,.axis-title,.value-label').nodes().map(el=>({el,box:el.getBBox()}));
    const boxes=labels.map(({el})=>({el,box:el.getBoundingClientRect()}));
    boxes.filter(x=>x.el.classList.contains('value-label')).forEach(a=>{
      if(boxes.some(b=>b.el!==a.el&&a.box.left<b.box.right+4&&a.box.right+4>b.box.left&&a.box.top<b.box.bottom+4&&a.box.bottom+4>b.box.top))a.el.remove();
    });
  }
  function drawChart() {
    chart.replaceChildren(); tooltip.hidden=true;
    const w=chart.getBoundingClientRect().width,h=320;
    const m={left:76,right:14,top:32,bottom:66},right=w-m.right,bottom=h-m.bottom;
    const observations=nodes.filter(n=>n.score!==null&&n.valid).map(n=>({x:n.order,y:n.score,n}));
    const [yl,yh]=d3.extent(observations,d=>d.y),yp=(yh-yl)*0.18||Math.abs(yl)*0.001;
    const [xl,xh]=d3.extent(nodes,d=>d.order),xp=Math.max((xh-xl)*0.025,0.5);
    const x=d3.scaleLinear().domain([xl-xp,xh+xp]).range([m.left+5,right-5]);
    const y=d3.scaleLinear().domain([yl-yp,yh+yp]).range([bottom-5,m.top+5]);
    let record=base;const best=nodes.map(n=>{if(n.status==='done'&&n.valid)record=Math.max(record,n.score);return{x:n.order,y:record,n};});
    const svg=d3.select(chart).append('svg').attr('class','rsi-plot').attr('viewBox',`0 0 ${w} ${h}`).attr('width',w).attr('height',h).attr('role','img').attr('aria-label',tr("验证 AUC 从 ")+base.toFixed(7)+tr(" 提高到 ")+byId.get(data.best).score.toFixed(7)+tr("。失败节点不计入历史最佳，未完成节点只显示暂定评测。"));
    svg.append('rect').attr('data-chart-frame','').attr('x',m.left).attr('y',m.top).attr('width',right-m.left).attr('height',bottom-m.top).attr('fill','none').attr('stroke','var(--border)');
    const ticks=y.ticks(4);
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1',m.left).attr('x2',right).attr('y1',d=>y(d)).attr('y2',d=>y(d)).attr('stroke','var(--border)');
    svg.append('g').attr('class','axis').attr('transform',`translate(${m.left},0)`).call(d3.axisLeft(y).tickValues(ticks).tickFormat(d3.format('.4f')).tickSize(0).tickPadding(9)).call(g=>g.select('.domain').remove());
    const xt=w<=360?[0,6,12,18]:[0,3,6,9,12,15,18];
    svg.append('g').attr('class','axis').attr('transform',`translate(0,${bottom})`).call(d3.axisBottom(x).tickValues(xt.filter(v=>v<=xh)).tickFormat(d=>d===0?tr("基线"):String(d)).tickSize(0).tickPadding(8)).call(g=>g.select('.domain').remove());
    svg.append('text').attr('class','axis-title').attr('data-axis','y').attr('x',m.left).attr('y',15).text(tr("本地验证 AUC"));
    svg.append('text').attr('class','axis-title').attr('data-axis','x').attr('x',(m.left+right)/2).attr('y',h-8).attr('text-anchor','middle').text(tr("研究节点编号"));
    svg.append('line').attr('x1',m.left).attr('x2',right).attr('y1',y(base)).attr('y2',y(base)).attr('stroke','var(--muted-foreground)').attr('stroke-dasharray','3 4');
    const bestLayer=svg.append('g').attr('visibility',visible.best?'visible':'hidden');
    bestLayer.append('path').datum(best).attr('d',d3.line().x(d=>x(d.x)).y(d=>y(d.y)).curve(d3.curveStepAfter)).attr('fill','none').attr('stroke','var(--viz-series-1)').attr('stroke-width',2);
    const scoresLayer=svg.append('g').attr('visibility',visible.scores?'visible':'hidden');
    scoresLayer.selectAll('path').data(observations).join('path').attr('transform',d=>`translate(${x(d.x)},${y(d.y)})`)
      .attr('d',d=>d3.symbol().type(d.n.status==='done'?d3.symbolCircle:d3.symbolDiamond).size(45)())
      .attr('fill',d=>d.n.status==='done'?'var(--viz-series-2)':'var(--background)').attr('stroke','var(--viz-series-2)').attr('stroke-width',1.5);
    svg.append('g').selectAll('circle').data(observations).join('circle').attr('data-selected-ring','').attr('data-node',d=>d.n.id).attr('cx',d=>x(d.x)).attr('cy',d=>y(d.y)).attr('r',8).attr('fill','none').attr('stroke','var(--foreground)').attr('visibility',d=>d.n.id===selected?'visible':'hidden');
    nodes.filter(n=>n.status==='failed').forEach(n=>svg.append('text').attr('x',x(n.order)).attr('y',bottom+41).attr('text-anchor','middle').text('× '+n.id));
    const bn=byId.get(data.best);
    bestLayer.append('text').attr('class','value-label').attr('x',x(bn.order)-5).attr('y',y(bn.score)-11).attr('text-anchor','end').text(bn.id+' · '+bn.score.toFixed(7));
    const guide=svg.append('line').attr('data-chart-hover-guide','').attr('y1',m.top).attr('y2',bottom).attr('stroke','var(--muted-foreground)').attr('visibility','hidden');
    const hoverBest=svg.append('circle').attr('data-chart-hover-marker','best').attr('r',4).attr('fill','var(--viz-series-1)').attr('visibility','hidden');
    const hoverScore=svg.append('circle').attr('data-chart-hover-marker','scores').attr('r',4).attr('fill','var(--viz-series-2)').attr('visibility','hidden');
    function interpolate(values,v,step) {
      const i=d3.bisector(d=>d.x).right(values,v)-1,a=values[Math.max(0,i)],b=values[Math.min(values.length-1,i+1)];
      if(step||a.x===b.x)return a.y;
      return a.y+(b.y-a.y)*(v-a.x)/(b.x-a.x);
    }
    function hover(event) {
      const [px]=d3.pointer(event,svg.node()),v=Math.max(xl,Math.min(xh,x.invert(px))),gx=x(v);
      guide.attr('x1',gx).attr('x2',gx).attr('visibility','visible');
      const nearest=nodes[d3.bisector(d=>d.order).center(nodes,v)];
      const b=interpolate(best,v,true),s=interpolate(observations,v,false);
      hoverBest.attr('cx',gx).attr('cy',y(b)).attr('visibility',visible.best?'visible':'hidden');
      hoverScore.attr('cx',gx).attr('cy',y(s)).attr('visibility',visible.scores?'visible':'hidden');
      tooltip.replaceChildren(); const lines=[tr("节点位置 ")+v.toFixed(1)];
      if(visible.best)lines.push(tr("历史最佳 ")+b.toFixed(7));
      if(visible.scores)lines.push(tr("相邻有效评测插值 ")+s.toFixed(7));
      lines.push(tr("最近节点 ")+nearest.id+' · '+nearest.state);
      lines.forEach(t=>{const el=document.createElement('div');el.textContent=t;tooltip.append(el);});tooltip.hidden=false;
      const rr=root.getBoundingClientRect(),cr=chart.getBoundingClientRect();
      const tw=tooltip.getBoundingClientRect().width;
      tooltip.style.left=Math.max(0,Math.min(w-tw,px+10))+'px';tooltip.style.top=(cr.top-rr.top+m.top+8)+'px';
    }
    svg.append('rect').attr('data-chart-hit','').attr('data-chart-hover-overlay','cross-series').attr('x',m.left).attr('y',m.top).attr('width',right-m.left).attr('height',bottom-m.top).attr('fill','transparent').attr('class','cursor-interaction')
      .on('pointermove',e=>{if(!pinned)hover(e);}).on('pointerleave',()=>{if(!pinned){tooltip.hidden=true;guide.attr('visibility','hidden');hoverBest.attr('visibility','hidden');hoverScore.attr('visibility','hidden');}})
      .on('click',e=>{const [px]=d3.pointer(e,svg.node()),v=x.invert(px),n=nodes[d3.bisector(d=>d.order).center(nodes,v)];select(n.id);pinned=e.pointerType==='touch'?!pinned:false;hover(e);});
    labelLayout(svg);
  }
  root.querySelectorAll('button[data-series]').forEach(b=>{b.setAttribute('aria-pressed',String(visible[b.dataset.series]));b.addEventListener('click',()=>{visible[b.dataset.series]=!visible[b.dataset.series];b.setAttribute('aria-pressed',String(visible[b.dataset.series]));pinned=false;drawChart();save();});});
  const observer=new ResizeObserver(()=>{tree.style.height='';drawChart();drawTree();showDetail();});observer.observe(chart);
  window.addEventListener('openai:set_globals',event=>{const s=event.detail?.globals?.widgetState;if(!s?.privateContent)return;const p=s.privateContent;if(byId.has(p.selected))selected=p.selected;if(p.visible)visible={best:p.visible.best!==false,scores:p.visible.scores!==false};root.querySelectorAll('button[data-series]').forEach(b=>b.setAttribute('aria-pressed',String(visible[b.dataset.series])));drawChart();showDetail();});
  drawChart();drawTree();showDetail();
})();
