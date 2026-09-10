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
    payload = json.dumps([{k: v for k, v in d.items() if k != "nodes"} for d in data]).replace("<", "\\u003c")
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>pi-rsi comparison</title>
<style>body{{font:14px system-ui;margin:0;padding:16px;background:#f7f7f5;color:#1c1c1c}}pre{{background:#fff;border:1px solid #ddd;padding:10px;white-space:pre-wrap}}
svg text{{font:12px system-ui}}</style></head><body><h2>pi-rsi comparison</h2><svg id="c" width="900" height="320"></svg><pre>{md.replace('<','&lt;')}</pre>
<script>const D={payload};const svg=document.getElementById('c');const W=900,H=320,m={{l:70,r:20,t:20,b:40}};
const cols=['#2f6fde','#d98a1f','#2e9e5b','#d64545'];let all=[];D.forEach(d=>{{all.push(d.root);d.curve.forEach(c=>{{if(c.score!=null)all.push(c.score)}});Object.values(d.reference||{{}}).forEach(v=>all.push(v))}});
let lo=Math.min(...all),hi=Math.max(...all);if(hi===lo)hi=lo+1;const pad=(hi-lo)*.08;lo-=pad;hi+=pad;const N=Math.max(...D.map(d=>d.curve.length),1);
const X=i=>m.l+i/N*(W-m.l-m.r),Y=v=>m.t+(1-(v-lo)/(hi-lo))*(H-m.t-m.b);let s='';
for(let k=0;k<5;k++){{const v=lo+(hi-lo)*k/4;s+=`<line x1="${{m.l}}" x2="${{W-m.r}}" y1="${{Y(v)}}" y2="${{Y(v)}}" stroke="#ddd"/><text x="${{m.l-6}}" y="${{Y(v)+4}}" text-anchor="end">${{Math.round(v).toLocaleString()}}</text>`}}
D.forEach((d,j)=>{{const pts=[[X(0),Y(d.root)]];d.curve.forEach((c,i)=>{{pts.push([X(i+1),Y(c.best)])}});s+=`<polyline fill="none" stroke="${{cols[j%4]}}" stroke-width="2" points="${{pts.map(p=>p.join(',')).join(' ')}}"/>`;
d.curve.forEach((c,i)=>{{if(c.score!=null)s+=`<circle cx="${{X(i+1)}}" cy="${{Y(c.score)}}" r="4" fill="${{c.status==='done'?cols[j%4]:'#d64545'}}"><title>${{d.name}} ${{c.id}} ${{Math.round(c.score)}} ${{c.title}}</title></circle>`;else s+=`<text x="${{X(i+1)}}" y="${{H-m.b+14}}" fill="#d64545" text-anchor="middle">✕</text>`}});
s+=`<text x="${{m.l+10}}" y="${{m.t+14+16*j}}" fill="${{cols[j%4]}}" font-weight="600">${{d.name}} (${{d.runner}})</text>`}});
s+=`<text x="${{W/2}}" y="${{H-6}}" text-anchor="middle">finished nodes (in order); line = best so far, dots = node score</text>`;svg.innerHTML=s;</script></body></html>"""


if __name__ == "__main__":
    sys.exit(main())
