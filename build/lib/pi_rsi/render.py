"""Render tree.json (+ node documents) into a self-contained tree.html and a tree.md for humans."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import ExperimentCfg
from .tree import Tree, Node
from .util import atomic_write_text, read_text, tail_text, fmt_score, human_duration, now_iso, read_json

_TEMPLATE = Path(__file__).parent / "templates" / "tree.html"
_TREE_JS = Path(__file__).parent / "templates" / "tree.js"


def layout(tree: Tree) -> dict[str, tuple[float, float]]:
    """Simple tidy layout: y = depth, x = order of leaves (each subtree centered over its leaves)."""
    pos: dict[str, tuple[float, float]] = {}
    counter = [0]

    def place(nid: str) -> float:
        kids = tree.children(nid)
        if not kids:
            x = float(counter[0])
            counter[0] += 1
        else:
            xs = [place(k.id) for k in kids]
            x = (min(xs) + max(xs)) / 2
        pos[nid] = (x, float(tree.nodes[nid].depth))
        return x

    if "root" in tree.nodes:
        place("root")
    for n in tree.nodes.values():  # orphans (should not happen)
        pos.setdefault(n.id, (float(counter[0]), float(n.depth)))
    return pos


def node_docs(cfg: ExperimentCfg, n: Node) -> dict[str, str]:
    nd = cfg.nodes_dir / n.id
    return {
        "hypothesis": read_text(nd / "HYPOTHESIS.md"),
        "handoff": read_text(nd / "HANDOFF.md"),
        "summary_md": read_text(nd / "SUMMARY.md"),
        "progress_tail": tail_text(nd / "PROGRESS.md", 80, 6000),
        "failure": read_text(nd / "FAILURE.md"),
        "human": read_text(nd / "HUMAN.md"),
        "heartbeat": read_text(nd / "heartbeat"),
    }


def build_data(cfg: ExperimentCfg, tree: Tree, costs: dict, state: dict) -> dict[str, Any]:
    pos = layout(tree)
    nodes = []
    for n in sorted(tree.nodes.values(), key=lambda n: (n.id != "root", n.id)):
        d = n.to_dict()
        d["x"], d["y"] = pos.get(n.id, (0, n.depth))
        d["docs"] = node_docs(cfg, n)
        d["score_fmt"] = fmt_score(n.score)
        d["duration_fmt"] = human_duration(n.duration_s)
        nodes.append(d)
    best = tree.best()
    final = json.loads(read_text(cfg.dir / "final.json") or "{}")
    return {
        "generated_at": now_iso(),
        "experiment": cfg.name,
        "task": cfg.task.name,
        "score_key": cfg.task.score_key,
        "higher_is_better": cfg.task.higher_is_better,
        "runner": f"{cfg.runner.kind}:{cfg.runner.model} ({cfg.runner.effort})",
        "utility": f"{cfg.utility.kind}:{cfg.utility.model} ({cfg.utility.effort})",
        "search": {"width_root": cfg.search.width_root, "width": cfg.search.width, "depth": cfg.search.depth,
                   "max_nodes": cfg.search.max_nodes, "max_parallel": cfg.search.max_parallel, "patience": cfg.search.patience},
        "reference_scores": cfg.task.reference_scores,
        "best": best.id if best else None,
        "root_score": tree.get("root").score if "root" in tree.nodes else None,
        "state": state,
        "final": final,
        "costs": costs,
        "insights": read_text(cfg.insights_path),
        "deadends": read_text(cfg.deadends_path),
        "nodes": nodes,
    }


def _payload(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def render_html(data: dict[str, Any], external: bool = False, title: str | None = None, back_link: str = "") -> str:
    """Self-contained page by default; with external=True the page references data.js and tree.js next to it
    (needed where a Content-Security-Policy forbids inline scripts, e.g. the blog)."""
    tpl = _TEMPLATE.read_text(encoding="utf-8")
    title = title or f"{data['experiment']} · {data['task']} search tree"
    if external:
        scripts = '<script src="data.js"></script>\n<script src="tree.js"></script>'
    else:
        scripts = f"<script>window.__RSI_DATA__ = {_payload(data)};</script>\n<script>\n{_TREE_JS.read_text(encoding='utf-8')}\n</script>"
    back = f'<div class="sub" style="margin-bottom:6px"><a href="{back_link}">← RSI notes</a></div>' if back_link else ""
    return tpl.replace("__TITLE__", title.replace("<", "&lt;")).replace("__SCRIPTS__", scripts).replace("__BACK__", back)


def render_bundle(cfg: ExperimentCfg, tree: Tree, out_dir: Path, title: str | None = None, back_link: str = "") -> None:
    """Write index.html + data.js + tree.js (CSP-safe, no inline scripts) for static hosting."""
    data = build_data(cfg, tree, read_json(cfg.dir / "costs.json", {}) or {}, read_json(cfg.dir / "state.json", {}) or {})
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "index.html", render_html(data, external=True, title=title, back_link=back_link))
    atomic_write_text(out_dir / "data.js", "window.__RSI_DATA__ = " + _payload(data) + ";\n")
    atomic_write_text(out_dir / "tree.js", _TREE_JS.read_text(encoding="utf-8"))


def render_md(cfg: ExperimentCfg, tree: Tree, data: dict[str, Any]) -> str:
    best = tree.best()
    lines = [f"# {cfg.name} — tree ({data['generated_at']})", "",
             f"worker {data['runner']}; best `{best.id if best else '-'}` = {fmt_score(best.score if best else None)}; "
             f"baseline {fmt_score(data['root_score'])}; state {data['state'].get('status')} {data['state'].get('stop_reason') or ''}", ""]

    def walk(nid: str, indent: int):
        n = tree.nodes[nid]
        mark = " ★" if best and nid == best.id else ""
        lines.append(f"{'  ' * indent}- `{n.id}`{mark} [{n.status}/{n.verdict or '-'}] {fmt_score(n.score)} "
                     f"(Δp {fmt_score(n.delta_parent)}) **{n.title}** — {n.summary}")
        for c in tree.children(nid):
            walk(c.id, indent + 1)

    if "root" in tree.nodes:
        walk("root", 0)
    lines += ["", "## Insights", "", data["insights"].strip() or "(none)", "", "## Dead ends", "", data["deadends"].strip() or "(none)", ""]
    return "\n".join(lines)


def render_all(cfg: ExperimentCfg, tree: Tree, costs: dict | None = None, state: dict | None = None) -> None:
    data = build_data(cfg, tree, costs or {}, state or {})
    atomic_write_text(cfg.dir / "tree.html", render_html(data))
    atomic_write_text(cfg.dir / "tree.md", render_md(cfg, tree, data))
