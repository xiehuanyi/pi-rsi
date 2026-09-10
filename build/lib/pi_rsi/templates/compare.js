// pi-rsi comparison view. Expects window.__RSI_CMP__.
const D=window.__RSI_CMP__;const cols=['var(--s0)','var(--s1)','var(--s2)','var(--s3)'];
const fmt=x=>(x==null)?'-':Math.round(x).toLocaleString();const esc=s=>String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const dur=s=>s==null?'-':(s<3600?Math.round(s/60)+'m':Math.floor(s/3600)+'h'+String(Math.round((s%3600)/60)).padStart(2,'0'));
document.getElementById('h').textContent='pi-rsi · '+D.map(d=>d.name).join(' vs ');
document.getElementById('sub').textContent='Same task pack, seeds, budget and utility model; only the worker model differs. Official score = mean final money on the validation seeds; held-out = test seeds never seen during the search.';
document.getElementById('runs').innerHTML=D.map((d,j)=>{const f=d.final||{};const k=[['baseline',fmt(d.root)],['best (validation)',fmt(d.best)+' · '+(d.best_id||'')],['held-out test',fmt(f.best_final_score)],['nodes done / failed',d.n_done+' / '+d.n_failed],['stop',f.stop_reason||d.state.status||'-'],['wall-clock',dur(d.elapsed)],['worker time',dur(d.worker_seconds)],['tokens in / out',(d.tokens_in/1e6).toFixed(2)+'M / '+(d.tokens_out/1e3).toFixed(0)+'k'],['est. API cost','$'+d.cost.toFixed(2)]];
return `<div class="run" style="--c:${cols[j%4]}"><h2>${esc(d.name)}</h2><div class="m">worker ${esc(d.runner)}</div><div class="kpis">${k.map(([l,v])=>`<div class="kpi"><div class="l">${l}</div><div class="v">${esc(v)}</div></div>`).join('')}</div></div>`}).join('');
(function(){const c=document.getElementById('c');const W=c.clientWidth||900,H=300,m={l:64,r:20,t:16,b:44};c.setAttribute('viewBox',`0 0 ${W} ${H}`);
let all=[];D.forEach(d=>{all.push(d.root);d.curve.forEach(x=>{if(x.score!=null)all.push(x.score)})});const refs=Object.assign({},...D.map(d=>d.reference||{}));
let lo=Math.min(...all),hi=Math.max(...all);if(hi===lo)hi=lo+1;const pad=(hi-lo)*.1;lo-=pad;hi+=pad;const N=Math.max(...D.map(d=>d.curve.length),1);
const X=i=>m.l+i/N*(W-m.l-m.r),Y=v=>m.t+(1-(v-lo)/(hi-lo))*(H-m.t-m.b);let s='';
for(let k=0;k<5;k++){const v=lo+(hi-lo)*k/4;s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/><text x="${m.l-8}" y="${Y(v)+4}" text-anchor="end" style="fill:var(--muted);font-size:11px">${fmt(v)}</text>`}
s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${Y(D[0].root)}" y2="${Y(D[0].root)}" stroke="var(--gold)" stroke-dasharray="4,4"/><text x="${W-m.r}" y="${Y(D[0].root)-4}" text-anchor="end" style="fill:var(--gold);font-size:11px">baseline ${fmt(D[0].root)}</text>`;
D.forEach((d,j)=>{const pts=[[X(0),Y(d.root)]];d.curve.forEach((x,i)=>pts.push([X(i+1),Y(x.best)]));s+=`<polyline fill="none" stroke="${cols[j%4]}" stroke-width="2.5" points="${pts.map(p=>p.join(',')).join(' ')}"/>`;
d.curve.forEach((x,i)=>{if(x.score!=null)s+=`<circle cx="${X(i+1)}" cy="${Y(x.score)}" r="4.5" fill="${x.status==='done'?cols[j%4]:'var(--bad)'}" stroke="var(--panel)" stroke-width="1.5"><title>${esc(d.name)} ${esc(x.id)} ${fmt(x.score)} — ${esc(x.title)}</title></circle>`;else s+=`<text x="${X(i+1)}" y="${H-m.b+16}" text-anchor="middle" style="fill:var(--bad)">✕</text>`});
s+=`<text x="${m.l+12}" y="${m.t+16+18*j}" style="fill:${cols[j%4]};font-weight:600">${esc(d.name)} · ${esc(d.runner)} · best ${fmt(d.best)}</text>`});
for(let i=0;i<=N;i++)s+=`<text x="${X(i)}" y="${H-m.b+16}" text-anchor="middle" style="fill:var(--muted);font-size:11px">${i}</text>`;
s+=`<text x="${(m.l+W-m.r)/2}" y="${H-8}" text-anchor="middle" style="fill:var(--muted);font-size:11px">finished nodes in order · line = best so far · dot = that node's official score</text>`;
const refv=Object.values(refs)[0];if(refv!=null)s+=`<text x="${W-m.r}" y="${m.t+12}" text-anchor="end" style="fill:var(--gold);font-size:11px">reference ${esc(Object.keys(refs)[0])} ${fmt(refv)} (off scale)</text>`;
c.innerHTML=s})();
document.getElementById('seq').innerHTML=D.map((d,j)=>`<div><h2 style="font-size:14px;margin:0 0 6px;color:${cols[j%4]}">${esc(d.name)}</h2><ol>${d.curve.map(x=>{const cls=x.status!=='done'?'fail':(x.score>=x.best-1e-9&&x.score!=null&&x.score===x.best?'up':'down');return `<li><span class="tag ${cls}">${x.status==='done'?fmt(x.score):'failed'}</span> <code>${esc(x.id)}</code> ${esc(x.title)} <span style="color:var(--muted)">· ${dur(x.t)}</span></li>`}).join('')}</ol></div>`).join('');

