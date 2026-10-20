const rsiLang=document.documentElement.lang.startsWith("zh")?"zh":"en";
const rsiText={"研究搜索树": "Research search tree", "曲线图例": "Chart legend", "支持和反对证据与所选知识条目的关系": "Supporting and opposing evidence for the selected entry", "pi-rsi · 航空满意度实验": "pi-rsi · airline satisfaction", "验证 AUC 的变化": "Validation AUC progression", "搜索分支": "Search branches", "历史最佳": "Best so far", "各节点评测": "Node measurements", "实验运行中": "Running", "× 失败　◇ 评测后仍在分析": "× Failed　◇ Processing", "★ 最高分节点　× 失败节点　◇ 处理中　连线表示从哪个节点继续实验": "★ Highest score　× Failed　◇ Processing · Edges show code ancestry", "研究 Wiki · 知识与证据": "Research Wiki · knowledge and evidence", "知识条目": "Knowledge entry", "证据关系": "Evidence relationships", "支持证据": "Supporting evidence", "反对证据": "Opposing evidence", "当前条目": "Selected entry", "实线：支持　虚线：反对 · 证据条目数不代表独立重复次数": "Solid: support · Dashed: opposition · Record counts are not independent replications", "适用范围、其他解释与下一步验证": "Scope, alternatives and next test", "知识版本与结论变化": "Published revisions and belief changes", "发布版本": "Published revision", "研究议程与尚未解决的问题": "Research agenda and open questions", "图表暂未加载": "Chart unavailable", "暂无有效评测": "No valid measurement", " · 已分配 ": " · Allocated ", " 个节点 · ": " nodes · ", " 完成 / ": " done / ", " 失败 / ": " failed / ", " 处理中 · Wiki 待处理 ": " pending completion · Wiki pending ", " · 相对基线 ": " · versus baseline ", "基线": "Baseline", "本地验证 AUC": "Local validation AUC", "研究节点编号": "Research node number", "节点位置 ": "Node position ", "历史最佳 ": "Best so far ", "相邻有效评测插值 ": "Interpolation between valid scores ", "最近节点 ": "Nearest node ", "观察": "Observation", "假设": "Hypothesis", "经验": "Experience", "获证据支持": "Supported", "待验证": "Untested", "证据混合": "Mixed evidence", "被反驳": "Refuted", "已被替代": "Superseded", " 条知识 · ": " entries · ", " 条证据记录 · ": " evidence records · ", " 个发布版本 · ": " published revisions · ", "（沙特时间）": " (Riyadh time)", "知识版本与结论变化（": "Published revisions and belief changes (", " 个版本）": " revisions)", "无": "None", "实验记录": "Experiment record", "文档记录": "Documentation record", " 条 · ": " entries · ", " 项更新": " changes", "（当前）": " (current)", "无有效分数": "No valid score", " · 测量状态 ": " · Measurement ", "有效": "valid", "不可用": "unavailable", "失效": "invalid", "未记录": "not recorded", "打开原文来源": "Open original source", "记录身份与哈希": "Record identity and hashes", "原始记录 SHA-256：": "Raw packet SHA-256: ", "代码提交：": "Code commit: ", "来源文本 SHA-256：": "Source text SHA-256: ", "无记录": "No records", "文档 ": "Document ", "证据：": " evidence: ", "支持": "Support", "反对": "Opposition", " · 支持 ": " · Supports ", " / 反对 ": " / Opposes ", "适用范围": "Scope", "其他解释": "Alternative explanations", "下一步区分性验证": "Next discriminating test", "查看被替代的条目": "View predecessor entry", "新增": "New", "本版本没有记录条目状态更新。": "No recorded entry-status changes in this revision.", "研究动机": "Motivation", "方法与判断依据": "Method and interpretation", "开放问题": "Open questions", "下一步实验": "Next experiments", "已完成": "Done", "失败": "Failed", "实验中": "Running", "结果分析中": "Analyzing", "评测中": "Evaluating", "待运行": "Planned", "待恢复": "Completion pending", "基线到第 ": "Baseline through node ", " 个节点的搜索分支；带星号的是最高分节点": " search branches; the star marks the highest score", "验证 AUC 从 ": "Validation AUC from ", " 提高到 ": " to ", "。失败节点不计入历史最佳，未完成节点只显示暂定评测。": ". Failed nodes do not improve the incumbent; incomplete nodes display provisional measurements only."};
function tr(s){return rsiLang==="zh"?s:(rsiText[s]||s);}

(() => {
  const root=document.getElementById('pi-rsi-wiki-oct04');
  const data=window.__RSI_BLOG_DATA__;
  const claims=new Map(data.claims.map(c=>[c.id,c])), evidence=new Map(data.evidence.map(e=>[e.id,e]));
  const kind={observation:tr("观察"),hypothesis:tr("假设"),experience:tr("经验")};
  const status={supported:tr("获证据支持"),untested:tr("待验证"),mixed:tr("证据混合"),refuted:tr("被反驳"),superseded:tr("已被替代")};
  const sel=root.querySelector('#wk-claim'), rev=root.querySelector('#wk-revision');
  const graph=root.querySelector('#wk-graph'), edges=root.querySelector('#wk-edges');
  const detail=root.querySelector('#wk-evidence-detail');
  const prior=window.openai?.widgetState?.privateContent;
  let current=claims.has(prior?.claim)?prior.claim:(claims.has('n010-depth8-l2-3-practical-retention')?'n010-depth8-l2-3-practical-retention':data.claims[0].id);
  let chosenEvidence=null;
  const date=s=>s?new Intl.DateTimeFormat(rsiLang==='zh'?'zh-CN':'en-GB',{timeZone:'Asia/Riyadh',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(s)):'';
  root.querySelector('#wk-summary').textContent=data.claims.length+tr(" 条知识 · ")+data.evidence.length+tr(" 条证据记录 · ")+data.history.length+tr(" 个发布版本 · ")+date(data.updated_at)+tr("（沙特时间）");
  root.querySelector('#wk-history-label').textContent=tr("知识版本与结论变化（")+data.history.length+tr(" 个版本）");
  function element(tag,text,className) {const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;}
  function save() {if(window.openai?.setWidgetState)window.openai.setWidgetState({modelContent:{wikiRevision:data.revision,claim:current,evidence:chosenEvidence},privateContent:{claim:current,revision:rev.value,evidence:chosenEvidence}}).catch(()=>{});}
  for(const type of ['observation','hypothesis','experience']) {
    const group=element('optgroup');group.label=kind[type];
    data.claims.filter(c=>c.kind===type).forEach(c=>{const option=element('option',c.title+' · '+status[c.status]);option.value=c.id;group.append(option);});sel.append(group);
  }
  data.history.forEach((h,i)=>{const option=element('option',date(h.updated_at)+' · '+h.claim_count+tr(" 条 · ")+h.changes.length+tr(" 项更新")+(i===0?tr("（当前）"):''));option.value=h.revision;rev.append(option);});
  if(data.history.some(h=>h.revision===prior?.revision))rev.value=prior.revision;
  function section(container,label,text) {const s=element('div',undefined,'wk-section');s.append(element('div',label,'wk-title'));if(Array.isArray(text)){const list=element('ul');text.forEach(t=>list.append(element('li',t)));s.append(list);}else s.append(element('div',text||tr("无")));container.append(s);}
  function showEvidence(id,remember=true) {
    const e=evidence.get(id);chosenEvidence=id;detail.replaceChildren();
    detail.append(element('div',(e.kind==='experiment'?tr("实验记录"):tr("文档记录"))+' · '+(e.node||e.title),'wk-title'));
    if(e.kind==='experiment') {
      const score=e.score===null||e.score===undefined?tr("无有效分数"):Number(e.score).toFixed(10);
      detail.append(element('div','AUC '+score+tr(" · 测量状态 ")+({validated:tr("有效"),unavailable:tr("不可用"),invalid:tr("失效")}[e.measurement_status]||e.measurement_status||tr("未记录")),"pp-num"));
      detail.append(element('div',e.title));
    } else if(e.source_url) {
      const a=element('a',tr("打开原文来源"));a.href=e.source_url;a.target='_blank';a.rel='noopener noreferrer';detail.append(a);
    }
    detail.append(element('div',e.id,"pp-small"));
    const hashes=element('details');hashes.append(element('summary',tr("记录身份与哈希")));
    hashes.append(element('div',tr("原始记录 SHA-256：")+e.packet_sha256,"pp-small"));
    if(e.commit)hashes.append(element('div',tr("代码提交：")+e.commit,"pp-small"));
    if(e.sha256)hashes.append(element('div',tr("来源文本 SHA-256：")+e.sha256,"pp-small"));detail.append(hashes);
    graph.querySelectorAll('button[data-evidence]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.evidence===id)));if(remember)save();
  }
  function sourceButtons(ids,target,role) {
    target.replaceChildren();if(!ids.length){target.append(element('span',tr("无记录"),"pp-small pp-muted"));return;}
    ids.forEach(id=>{const e=evidence.get(id);const b=element('button',e.node||tr("文档 ")+(data.evidence.indexOf(e)+1),"pp-chip pp-small");b.type='button';b.dataset.evidence=id;b.dataset.relation=role;b.setAttribute('data-tooltip',e.title);b.setAttribute('aria-label',role+tr("证据：")+e.title);b.setAttribute('aria-pressed','false');b.addEventListener('click',()=>showEvidence(id));target.append(b);});
  }
  function drawEdges() {
    edges.replaceChildren();const rect=graph.getBoundingClientRect();edges.setAttribute('viewBox',`0 0 ${rect.width} ${rect.height}`);
    const ns='http://www.w3.org/2000/svg',center=graph.querySelector('.wk-center').getBoundingClientRect(),vertical=getComputedStyle(graph).gridTemplateColumns.split(' ').length===1;
    graph.querySelectorAll('button[data-relation]').forEach(b=>{
      const br=b.getBoundingClientRect(),opposed=b.dataset.relation===tr("反对");let a,z;
      if(vertical){a=[br.left+br.width/2-rect.left,opposed?br.top-rect.top:br.bottom-rect.top];z=[center.left+center.width/2-rect.left,opposed?center.bottom-rect.top:center.top-rect.top];}
      else{a=[opposed?br.left-rect.left:br.right-rect.left,br.top+br.height/2-rect.top];z=[opposed?center.right-rect.left:center.left-rect.left,center.top+center.height/2-rect.top];}
      const p=document.createElementNS(ns,'path');const mid=vertical?(a[1]+z[1])/2:(a[0]+z[0])/2;
      p.setAttribute('d',vertical?`M${a[0]},${a[1]} C${a[0]},${mid} ${z[0]},${mid} ${z[0]},${z[1]}`:`M${a[0]},${a[1]} C${mid},${a[1]} ${mid},${z[1]} ${z[0]},${z[1]}`);
      p.setAttribute('fill','none');p.setAttribute('stroke',opposed?'var(--viz-series-2)':'var(--viz-series-1)');p.setAttribute('stroke-width','1.5');if(opposed)p.setAttribute('stroke-dasharray','4 4');edges.append(p);
    });
  }
  function showClaim() {
    sel.value=current;const c=claims.get(current),pane=root.querySelector('#wk-claim-detail');pane.replaceChildren();sel.setAttribute('data-tooltip',c.title);
    pane.append(element('div',c.title,'wk-title'));pane.append(element('div',kind[c.kind]+' · '+status[c.status]+tr(" · 支持 ")+c.supports.length+tr(" / 反对 ")+c.opposes.length,"pp-small"));pane.append(element('div',c.statement));
    root.querySelector('#wk-center-status').textContent=status[c.status];
    sourceButtons(c.supports,root.querySelector('#wk-supports'),tr("支持"));sourceButtons(c.opposes,root.querySelector('#wk-opposes'),tr("反对"));
    detail.replaceChildren();chosenEvidence=null;
    const scope=root.querySelector('#wk-scope');scope.replaceChildren();section(scope,tr("适用范围"),c.scope);section(scope,tr("其他解释"),c.alternatives);section(scope,tr("下一步区分性验证"),c.next_test);
    if(c.supersedes&&claims.has(c.supersedes)){const b=element('button',tr("查看被替代的条目"),"pp-chip");b.type='button';b.addEventListener('click',()=>{current=c.supersedes;showClaim();save();});scope.append(b);}
    requestAnimationFrame(drawEdges);
  }
  function showHistory() {
    const h=data.history.find(h=>h.revision===rev.value),pane=root.querySelector('#wk-history');pane.replaceChildren();
    pane.append(element('div',h.revision,"pp-small"));pane.append(element('div',h.what_changed));
    h.changes.forEach(change=>{const s=element('div',undefined,'wk-version-change');
      const b=element('button',claims.get(change.claim)?.title||change.claim,"pp-chip pp-small");b.type='button';b.disabled=!claims.has(change.claim);b.addEventListener('click',()=>{current=change.claim;showClaim();save();});s.append(b);
      s.append(element('div',(status[change.before]||tr("新增"))+' → '+(status[change.after]||change.after),'wk-title'));
      if(change.reason!==h.what_changed)s.append(element('div',change.reason));pane.append(s);});
    if(!h.changes.length)pane.append(element('div',tr("本版本没有记录条目状态更新。"),"pp-small"));
  }
  const agenda=root.querySelector('#wk-agenda');for(const [key,label] of [['motivation',tr("研究动机")],['method',tr("方法与判断依据")],['open_questions',tr("开放问题")],['next_experiments',tr("下一步实验")]])section(agenda,label,data.agenda[key]);
  sel.addEventListener('change',()=>{current=sel.value;showClaim();save();});rev.addEventListener('change',()=>{showHistory();save();});
  window.addEventListener('openai:set_globals',event=>{const s=event.detail?.globals?.widgetState?.privateContent;if(!s)return;if(claims.has(s.claim)&&s.claim!==current){current=s.claim;showClaim();}if(evidence.has(s.evidence)&&s.evidence!==chosenEvidence)showEvidence(s.evidence,false);if(s.revision!==rev.value&&data.history.some(h=>h.revision===s.revision)){rev.value=s.revision;showHistory();}});
  new ResizeObserver(drawEdges).observe(graph);showClaim();showHistory();if(evidence.has(prior?.evidence))showEvidence(prior.evidence,false);
})();
