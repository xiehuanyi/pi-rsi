#!/usr/bin/env python3
"""Publish pi-rsi experiments to the static research blog (pocketplay-blog project).

    scripts/publish_blog.py --blog ../pocketplay-blog experiments/kag-grok-45 experiments/kag-grok-46 \
        --compare grok46-vs-grok45=experiments/kag-grok-46,experiments/kag-grok-45 --deploy

Per experiment it writes
  <blog>/public/rsi/runs/<exp>/            interactive tree (index.html + data.js + tree.js; no inline scripts, CSP-safe)
  <blog>/public/files/rsi/runs/<exp>/      REPORT.md, INSIGHTS.md, DEADENDS.md, tree.md, rsi.toml, nodes/<id>/*.md
  <blog>/content/rsi/experiments/<exp>/index.md   summary page in the blog's navigation
Comparisons go to <blog>/public/rsi/compare/<name>/ plus content/rsi/analysis/<name>/index.md.
Runner transcripts and prompts are not published.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from pi_rsi.config import load_experiment  # noqa: E402
from pi_rsi.tree import Tree  # noqa: E402
from pi_rsi.render import render_bundle  # noqa: E402
from pi_rsi.util import fmt_score, human_duration, read_text, read_json  # noqa: E402
import compare as cmp  # noqa: E402

NODE_DOCS = ["HYPOTHESIS.md", "HANDOFF.md", "SUMMARY.md", "PROGRESS.md", "FAILURE.md", "proposals.json"]


def md_escape(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def publish_experiment(blog: Path, exp_dir: Path) -> dict:
    cfg = load_experiment(exp_dir)
    tree = Tree.load(cfg.tree_path)
    name = cfg.name
    run_dir = blog / "public" / "rsi" / "runs" / name
    files_dir = blog / "public" / "files" / "rsi" / "runs" / name
    render_bundle(cfg, tree, run_dir, title=f"{name} · search tree", back_link=f"/rsi/experiments/{name}/")
    if files_dir.exists():
        shutil.rmtree(files_dir)
    files_dir.mkdir(parents=True)
    for f in ["REPORT.md", "INSIGHTS.md", "DEADENDS.md", "tree.md", "rsi.toml", "final.json", "costs.json"]:
        if (exp_dir / f).exists():
            shutil.copy2(exp_dir / f, files_dir / f)
    for nd in sorted((exp_dir / "nodes").glob("*")):
        if not nd.is_dir():
            continue
        dst = files_dir / "nodes" / nd.name
        for doc in NODE_DOCS:
            if (nd / doc).exists():
                dst.mkdir(parents=True, exist_ok=True)
                shutil.copy2(nd / doc, dst / doc)
        for m in (nd / "eval").glob("metrics.*.json") if (nd / "eval").exists() else []:
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copy2(m, dst / m.name)

    best = tree.best()
    root = tree.get("root")
    final = read_json(exp_dir / "final.json", {}) or {}
    state = read_json(exp_dir / "state.json", {}) or {}
    costs = read_json(exp_dir / "costs.json", {}) or {}
    better = "lower" if not cfg.task.higher_is_better else "higher"
    lines = [f"# {name}", "",
             f"{cfg.task.name} · worker {cfg.runner.kind}:{cfg.runner.model} ({cfg.runner.effort}) · "
             f"{'finished' if state.get('status') == 'finished' else state.get('status', 'unknown')}"
             f"{' (' + str(final.get('stop_reason')) + ')' if final.get('stop_reason') else ''}", "",
             f"[打开交互式搜索树](/rsi/runs/{name}/) · [REPORT.md](/files/rsi/runs/{name}/REPORT.md) · "
             f"[INSIGHTS.md](/files/rsi/runs/{name}/INSIGHTS.md) · [DEADENDS.md](/files/rsi/runs/{name}/DEADENDS.md) · "
             f"[rsi.toml](/files/rsi/runs/{name}/rsi.toml)", "",
             "## 结果", "",
             "| 项目 | 值 |", "|---|---|",
             f"| 指标 | `{cfg.task.score_key}`，{better} is better |",
             f"| baseline（root） | {fmt_score(root.score)} |",
             f"| 最佳节点（{cfg.task.official_seedset}） | {fmt_score(best.score) if best else '-'}（`{best.id if best else '-'}`） |"]
    if "best_final_score" in final:
        lines.append(f"| 最佳节点（{cfg.task.final_seedset}，held-out） | {fmt_score(final['best_final_score'])}"
                     f"{' vs baseline ' + fmt_score(final.get('root_final_score')) if final.get('root_final_score') is not None else ''} |")
    for k, v in (cfg.task.reference_scores or {}).items():
        lines.append(f"| 参考 {k} | {fmt_score(v)} |")
    done = [n for n in tree.non_root() if n.status == "done"]
    failed = [n for n in tree.non_root() if n.status == "failed"]
    lines.append(f"| 节点 完成/失败 | {len(done)}/{len(failed)} |")
    lines.append(f"| 搜索参数 | width_root {cfg.search.width_root}, width {cfg.search.width}, depth {cfg.search.depth}, max_nodes {cfg.search.max_nodes}, parallel {cfg.search.max_parallel}, patience {cfg.search.patience} |")
    if final.get("elapsed_s"):
        lines.append(f"| 总耗时 | {human_duration(final['elapsed_s'])} |")
    if costs:
        tot = sum(c.get('cost_usd', 0) for c in costs.values())
        tin = sum(c.get('input_tokens', 0) for c in costs.values()); tout = sum(c.get('output_tokens', 0) for c in costs.values())
        lines.append(f"| token 输入/输出 | {tin:,} / {tout:,}（CLI 估算成本 ${tot:.2f}） |")
    lines += ["", "## 最佳路径", ""]
    if best:
        for n in tree.ancestors(best.id) + [best]:
            lines.append(f"- `{n.id}` {fmt_score(n.score)} — **{md_escape(n.title)}**：{md_escape(n.summary)}")
    lines += ["", "## 所有节点", "", "| id | parent | 深度 | 状态 | 分数 | Δparent | 假设 | 用时 | 文件 |", "|---|---|---|---|---|---|---|---|---|"]
    for n in sorted(tree.nodes.values(), key=lambda n: (n.id != "root", n.id)):
        docs = []
        for doc in ("HANDOFF.md", "SUMMARY.md", "PROGRESS.md", "FAILURE.md"):
            if (files_dir / "nodes" / n.id / doc).exists():
                docs.append(f"[{doc.split('.')[0].lower()}](/files/rsi/runs/{name}/nodes/{n.id}/{doc})")
        lines.append(f"| {n.id} | {n.parent or '-'} | {n.depth} | {n.verdict or n.status} | {fmt_score(n.score)} | {fmt_score(n.delta_parent)} | "
                     f"{md_escape(n.title)} | {human_duration(n.duration_s)} | {' '.join(docs)} |")
    ins = read_text(exp_dir / "INSIGHTS.md").strip().splitlines()
    ins = [l for l in ins if l.startswith("- ")]
    de = [l for l in read_text(exp_dir / "DEADENDS.md").strip().splitlines() if l.startswith("- ")]
    lines += ["", "## Insights（审计员从各节点核实后记录）", ""] + (ins or ["- （无）"])
    lines += ["", "## Dead ends", ""] + (de or ["- （无）"]) + [""]
    page = blog / "content" / "rsi" / "experiments" / name / "index.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("\n".join(lines), encoding="utf-8")
    return {"name": name, "best": best.score if best else None, "root": root.score, "task": cfg.task.name,
            "model": f"{cfg.runner.model} ({cfg.runner.effort})", "final": final}


def publish_compare(blog: Path, cname: str, exps: list[Path]) -> None:
    out = blog / "public" / "rsi" / "compare" / cname
    cmp.write_bundle(exps, out, title=cname)
    data = [cmp.load(e) for e in exps]
    lines = [f"# {cname}", "", f"[打开交互式对比页](/rsi/compare/{cname}/)", "",
             "| 实验 | worker | baseline | 最佳（validation） | 最佳（held-out） | 节点 完成/失败 | 停止 | 总耗时 | token 输入/输出 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for d in data:
        f = d["final"]
        lines.append(f"| [{d['name']}](/rsi/experiments/{d['name']}/) | {d['runner']} | {fmt_score(d['root'])} | {fmt_score(d['best'])} ({d['best_id']}) | "
                     f"{fmt_score(f.get('best_final_score'))} | {d['n_done']}/{d['n_failed']} | {f.get('stop_reason') or d['state'].get('status')} | "
                     f"{human_duration(d['elapsed'])} | {d['tokens_in']:,}/{d['tokens_out']:,} |")
    lines.append("")
    for d in data:
        lines.append(f"### {d['name']} 节点顺序")
        for c in d["curve"]:
            lines.append(f"- `{c['id']}` {c['status']} {fmt_score(c['score'])}（best so far {fmt_score(c['best'])}，{human_duration(c['t'])}）：{md_escape(c['title'])}")
        lines.append("")
    page = blog / "content" / "rsi" / "analysis" / cname / "index.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("exps", nargs="*")
    ap.add_argument("--blog", required=True)
    ap.add_argument("--compare", action="append", default=[], help="name=expA,expB[,...]")
    ap.add_argument("--deploy", action="store_true")
    a = ap.parse_args()
    blog = Path(a.blog).resolve()
    for e in a.exps:
        info = publish_experiment(blog, Path(e).resolve())
        print(f"published experiment page: {info['name']} best={fmt_score(info['best'])} root={fmt_score(info['root'])}")
    for c in a.compare:
        cname, rest = c.split("=", 1)
        publish_compare(blog, cname, [Path(x).resolve() for x in rest.split(",")])
        print(f"published comparison: {cname}")
    if a.deploy:
        r = subprocess.run(["bash", "deploy.sh"], cwd=str(blog))
        return r.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
