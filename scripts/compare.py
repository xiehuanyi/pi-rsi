#!/usr/bin/env python3
"""Compare several pi-rsi experiments: markdown table + best-so-far curves (self-contained HTML).
Usage: scripts/compare.py experiments/a experiments/b [--out compare.html]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pi_rsi.util import fmt_score, human_duration  # noqa: E402


def load(exp: Path) -> dict:
    tree = json.loads((exp / "tree.json").read_text())
    nodes = {n["id"]: n for n in tree["nodes"]}
    final = json.loads((exp / "final.json").read_text()) if (exp / "final.json").exists() else {}
    costs = json.loads((exp / "costs.json").read_text()) if (exp / "costs.json").exists() else {}
    state = json.loads((exp / "state.json").read_text()) if (exp / "state.json").exists() else {}
    hib = tree["meta"].get("higher_is_better", True)
    finished = sorted([n for n in nodes.values() if n["id"] != "root" and n.get("finished_at")], key=lambda n: n["finished_at"])
    curve, best = [], nodes["root"]["score"]
    for n in finished:
        s = n.get("score")
        if s is not None and n["status"] == "done" and (best is None or (s > best if hib else s < best)):
            best = s
        curve.append({"id": n["id"], "score": s, "best": best, "status": n["status"], "title": n["title"],
                      "t": n.get("duration_s"), "finished_at": n["finished_at"]})
    done = [n for n in finished if n["status"] == "done"]
    failed = [n for n in finished if n["status"] == "failed"]
    elapsed = None
    if finished and nodes.get("root", {}).get("finished_at"):
        pass
    tot_cost = sum(c.get("cost_usd", 0) for c in costs.values())
    tot_in = sum(c.get("input_tokens", 0) for c in costs.values())
    tot_out = sum(c.get("output_tokens", 0) for c in costs.values())
    return {"name": tree["meta"].get("experiment", exp.name), "runner": tree["meta"].get("runner", ""), "root": nodes["root"]["score"],
            "best": best, "best_id": tree.get("best"), "final": final, "n_done": len(done), "n_failed": len(failed),
            "state": state, "curve": curve, "cost": tot_cost, "tokens_in": tot_in, "tokens_out": tot_out,
            "worker_seconds": costs.get("worker", {}).get("seconds", 0), "elapsed": final.get("elapsed_s"),
            "reference": tree["meta"].get("reference_scores", {}), "nodes": nodes}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("exps", nargs="+")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    data = [load(Path(e)) for e in a.exps]
    lines = ["| experiment | worker | baseline | best (validation) | best (held-out test) | nodes done/failed | stop | wall-clock | worker time | tokens in/out | cost est. |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for d in data:
        f = d["final"]
        lines.append(f"| {d['name']} | {d['runner']} | {fmt_score(d['root'])} | {fmt_score(d['best'])} ({d['best_id']}) | "
                     f"{fmt_score(f.get('best_final_score'))} vs {fmt_score(f.get('root_final_score'))} | {d['n_done']}/{d['n_failed']} | "
                     f"{f.get('stop_reason') or d['state'].get('status')} | {human_duration(d['elapsed'])} | {human_duration(d['worker_seconds'])} | "
                     f"{d['tokens_in']:,}/{d['tokens_out']:,} | ${d['cost']:.2f} |")
    lines.append("")
    for d in data:
        lines.append(f"### {d['name']} — node sequence (finish order)")
        for c in d["curve"]:
            lines.append(f"- `{c['id']}` {c['status']} score {fmt_score(c['score'])} (best so far {fmt_score(c['best'])}, {human_duration(c['t'])}): {c['title']}")
        lines.append("")
    md = "\n".join(lines)
    print(md)
    if a.out:
        html = _html(data, md)
        Path(a.out).write_text(html, encoding="utf-8")
        print(f"\nwrote {a.out}")
    return 0


def _html(data: list[dict], md: str) -> str:
    """Self-contained comparison page (same visual system as tree.html): KPI tiles per run, best-so-far curves,
    node sequences side by side."""
    payload = json.dumps([{k: v for k, v in d.items() if k != "nodes"} for d in data], ensure_ascii=False).replace("<", "\\u003c")
    names = " vs ".join(d["name"] for d in data)
    return """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__NAMES__</title>
<style>
:root{--bg:#f7f7f5;--fg:#1c1c1c;--muted:#6b6b6b;--panel:#ffffff;--line:#d9d9d4;--accent:#2f6fde;--ok:#2e9e5b;--warn:#d98a1f;--bad:#d64545;--gold:#c9a227;--code:#f0f0ec;--s0:#2f6fde;--s1:#d98a1f;--s2:#2e9e5b;--s3:#8a4fd6}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#15161a;--fg:#ececec;--muted:#9aa0a6;--panel:#1f2126;--line:#33363d;--code:#26282e}}
:root[data-theme="dark"]{--bg:#15161a;--fg:#ececec;--muted:#9aa0a6;--panel:#1f2126;--line:#33363d;--code:#26282e}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding-inline:16px;padding-block:14px;font-variant-numeric:tabular-nums}
h1{font-size:19px;margin:0 0 2px;text-wrap:balance}.sub{color:var(--muted);font-size:13px;margin-bottom:12px}
.runs{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.run{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px;border-top:4px solid var(--c)}
.run h2{font-size:15px;margin:0 0 2px}.run .m{color:var(--muted);font-size:12px;margin-bottom:8px}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.kpi .l{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.04em}.kpi .v{font-size:17px;font-weight:600}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px;margin-top:12px;min-width:0}
.panel h3{font-size:13px;margin:0 0 8px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.04em}
svg text{font:12px system-ui,sans-serif;fill:var(--fg)}
.seq{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
ol{margin:0;padding-left:20px}li{margin:3px 0}
.tag{display:inline-block;min-width:64px;text-align:right;font-weight:600}
.up{color:var(--ok)}.down{color:var(--warn)}.fail{color:var(--bad)}
.tablewrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:12px}th,td{border-bottom:1px solid var(--line);padding:4px 6px;text-align:left}th{color:var(--muted)}
</style></head><body>
<h1 id="h"></h1><div class="sub" id="sub"></div>
<div class="runs" id="runs"></div>
<div class="panel"><h3>Best so far by finished node</h3><svg id="c" width="100%" height="300"></svg></div>
<div class="panel"><h3>Node sequences (finish order)</h3><div class="seq" id="seq"></div></div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);const cols=['var(--s0)','var(--s1)','var(--s2)','var(--s3)'];
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
</script></body></html>""".replace("__NAMES__", names.replace("<", "&lt;")).replace("__DATA__", payload)


if __name__ == "__main__":
    sys.exit(main())
