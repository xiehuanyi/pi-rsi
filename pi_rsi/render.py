"""Render tree.json (+ node documents) into a self-contained tree.html and a tree.md for humans."""
from __future__ import annotations

import copy
import datetime as dt
import html
import json
import math
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .config import ExperimentCfg
from .tree import Tree, Node
from .util import atomic_write_text, read_text, tail_text, fmt_score, human_duration, now_iso, read_json

_TEMPLATE = Path(__file__).parent / "templates" / "tree.html"
_TREE_JS = Path(__file__).parent / "templates" / "tree.js"
_FORBIDDEN_HREF_SCHEMES = {"javascript", "data", "vbscript"}


def _snapshot_tree(tree: Tree) -> Tree:
    """Deep-copy nodes/meta under `tree.lock` so layout/best/payload stay consistent while workers mutate."""
    with tree.lock:
        snap = Tree(tree.path, meta=copy.deepcopy(tree.meta or {}))
        snap._counter = tree._counter
        snap.nodes = {nid: Node.from_dict(n.to_dict()) for nid, n in tree.nodes.items()}
        return snap


def _valid_time(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.strip())
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc).isoformat()
    except (ValueError, OverflowError):
        return None


def _experiment_started_at(tree: Tree) -> str | None:
    """Stable experiment start. `state.started_at` resets on resume, so it is not used."""
    meta = _valid_time((tree.meta or {}).get("created_at"))
    if meta:
        return meta
    times: list[str] = []
    root = tree.nodes.get("root")
    if root is not None:
        for raw in (root.started_at, root.created_at):
            t = _valid_time(raw)
            if t:
                times.append(t)
    for n in tree.nodes.values():
        for raw in (n.created_at, n.started_at):
            t = _valid_time(raw)
            if t:
                times.append(t)
    return min(times) if times else None


def _sanitize(value: Any) -> Any:
    """Replace non-finite floats with None so the payload is valid JSON (and valid JS)."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v) for v in value]
    return value


def _safe_href(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    scheme = (urlsplit(raw).scheme or "").strip().lower()
    if not scheme and ":" in raw:
        scheme = raw.split(":", 1)[0].strip().lower()
    if scheme in _FORBIDDEN_HREF_SCHEMES:
        return ""
    return html.escape(raw, quote=True)


def layout(tree: Tree) -> dict[str, tuple[float, float]]:
    """Simple tidy layout: y = depth, x = order of leaves (each subtree centered over its leaves)."""
    pos: dict[str, tuple[float, float]] = {}
    counter = [0]

    def place(nid: str) -> float:
        if nid in pos:
            return pos[nid][0]
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
    for n in tree.nodes.values():  # orphans / disconnected subtrees
        if n.id not in pos:
            place(n.id)
    return pos


def node_docs(cfg: ExperimentCfg, n: Node) -> dict[str, str]:
    nd = cfg.nodes_dir / n.id
    research = n.worker.get("research", {})
    think = Path(research["think_path"]).resolve() if research.get("think_path") else None
    return {
        "hypothesis": read_text(nd / "HYPOTHESIS.md"),
        "handoff": read_text(nd / "HANDOFF.md"),
        "summary_md": read_text(nd / "SUMMARY.md"),
        "progress_tail": tail_text(nd / "PROGRESS.md", 80, 6000),
        "failure": read_text(nd / "FAILURE.md"),
        "human": read_text(nd / "HUMAN.md"),
        "heartbeat": read_text(nd / "heartbeat"),
        "thinking": read_text(think) if think and think.is_relative_to((cfg.dir / "cycles").resolve()) else "",
        "analysis": read_text(nd / "analysis.json"),
        "next": read_text(nd / "NEXT.md"),
    }


def build_data(cfg: ExperimentCfg, tree: Tree, costs: dict, state: dict) -> dict[str, Any]:
    snap = _snapshot_tree(tree)
    from .execution import ExecutionStore
    executions = ExecutionStore(cfg)
    physical = list(snap.nodes.values())
    canonical = snap.hypotheses()
    representatives = {n.hypothesis_key: n.id for n in canonical}
    aliases = {n.id: representatives.get(n.hypothesis_key, n.id) for n in physical}
    records = [executions.read(n) for n in physical]
    snap.nodes = {n.id: n for n in canonical}
    for n in canonical:
        n.parent = aliases.get(n.parent, n.parent)
    pos = layout(snap)
    nodes = []
    for n in sorted(snap.nodes.values(), key=lambda n: (n.id != "root", n.id)):
        d = n.to_dict()
        d["x"], d["y"] = pos.get(n.id, (0, n.depth))
        d["docs"] = node_docs(cfg, n)
        d["score_fmt"] = fmt_score(n.score)
        d["duration_fmt"] = human_duration(n.duration_s)
        d["legacy_attempt_nodes"] = [old.id for old in physical if old.hypothesis_key == n.hypothesis_key and old.id != n.id]
        d["executions"] = [record for record in records if record["hypothesis_id"] == n.hypothesis_key]
        nodes.append(d)
    best = snap.best()
    final = json.loads(read_text(cfg.dir / "final.json") or "{}")
    from .memory import ResearchMemory
    memory = ResearchMemory(cfg)
    wiki = memory.state()
    closing = read_json(cfg.dir / "closing_knowledge.json", {}) or {}
    if closing.get("closing_only"):
        # Display terminal knowledge without exposing confirmation to planner recall.
        wiki = closing
    wiki_notes = [f"Revision: {wiki['revision'] or 'uncompiled'}", "",
                  "Raw sources → generated knowledge → navigation index", ""]
    if closing.get("closing_only"):
        wiki_notes += ["Closed-study knowledge includes final expert confirmation; search memory remains separate.", ""]
    if wiki["agenda"]:
        wiki_notes += ["What changed", wiki["agenda"].get("what_changed", ""), "",
                       "Open questions", *wiki["agenda"].get("open_questions", []), ""]
    for claim in wiki["claims"].values():
        wiki_notes += [f"{claim['id']} [{claim['kind']} / {claim['status']}]", claim["statement"],
                       "Scope: " + claim["scope"], "Supports: " + ", ".join(claim["supports"]),
                       "Opposes: " + ", ".join(claim["opposes"]),
                       "Next test: " + claim["next_test"], ""]
    monitors = [{"node": p.parent.parent.name, **(read_json(p, {}) or {})}
                for p in sorted(cfg.nodes_dir.glob("*/eval/*.monitor.json"))]
    return {
        "generated_at": now_iso(),
        "experiment": cfg.name,
        "task": cfg.task.name,
        "score_key": cfg.task.score_key,
        "higher_is_better": cfg.task.higher_is_better,
        "official_seedset": cfg.task.official_seedset,
        "final_seedset": cfg.task.final_seedset,
        "experiment_started_at": _experiment_started_at(snap),
        "runner": f"{cfg.runner.kind}:{cfg.runner.model} ({cfg.runner.effort})",
        "utility": f"{cfg.utility.kind}:{cfg.utility.model} ({cfg.utility.effort})",
        "search": {"width_root": cfg.search.width_root, "width": cfg.search.width, "depth": cfg.search.depth,
                   "max_nodes": cfg.search.max_nodes,
                   "width_policy": "advisory" if cfg.research.enabled else "bounded",
                   "max_attempts": cfg.search.max_attempts if cfg.search.max_attempts is not None else cfg.search.max_nodes*(cfg.search.max_retries+1),
                   "max_parallel": 1 if cfg.research.enabled else cfg.search.max_parallel,
                   "patience": cfg.search.patience},
        "execution_attempts": len({(r['hypothesis_id'],a['ordinal']) for r in records if r['node_id']!='root' for a in r['attempts']}),
        "reference_scores": cfg.task.reference_scores,
        "best": best.id if best else None,
        "waiting_questions": _waiting(cfg),
        "root_score": snap.get("root").score if "root" in snap.nodes else None,
        "state": state,
        "final": final,
        "costs": costs,
        "insights": read_text(cfg.insights_path),
        "deadends": read_text(cfg.deadends_path),
        "wiki": "\n".join(wiki_notes),
        "knowledge": {"revision": wiki["revision"], "claims": list(wiki["claims"].values()),
                      "changes": wiki.get("changes", []), "agenda": wiki["agenda"]},
        "task_monitor": monitors,
        "monitor_notes": "\n\n".join(f"{m['node']}: {m.get('state')} · task {m.get('job')} · "
                           f"model wakes {m.get('wake_count', 0)} · {m.get('reason', '')}" for m in monitors),
        "research_loop": {"enabled": cfg.research.enabled, "decision": snap.meta.get("research_decision", {}),
                          "stop": snap.meta.get("research_stop"), "error": snap.meta.get("research_error")},
        "maintainer": f"{cfg.maintainer.kind}:{cfg.maintainer.model}" if cfg.maintainer.enabled else f"{cfg.utility.kind}:{cfg.utility.model}",
        "nodes": nodes,
    }


def _payload(data: dict[str, Any]) -> str:
    return (json.dumps(_sanitize(data), ensure_ascii=False, allow_nan=False)
            .replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def render_html(data: dict[str, Any], external: bool = False, title: str | None = None, back_link: str = "") -> str:
    """Self-contained page by default; with external=True the page references data.js and tree.js next to it
    (needed where a Content-Security-Policy forbids inline scripts, e.g. the blog)."""
    tpl = _TEMPLATE.read_text(encoding="utf-8")
    title = title or f"{data['experiment']} · {data['task']} search tree"
    if external:
        scripts = '<script src="data.js"></script>\n<script src="tree.js"></script>'
    else:
        scripts = f"<script>window.__RSI_DATA__ = {_payload(data)};</script>\n<script>\n{_TREE_JS.read_text(encoding='utf-8')}\n</script>"
    href = _safe_href(back_link)
    back = f'<div class="sub" style="margin-bottom:6px"><a href="{href}">← RSI notes</a></div>' if href else ""
    replacements = {"__TITLE__": html.escape(title, quote=True), "__SCRIPTS__": scripts, "__BACK__": back}
    return re.sub(r"__TITLE__|__SCRIPTS__|__BACK__", lambda match: replacements[match.group()], tpl)


def render_bundle(cfg: ExperimentCfg, tree: Tree, out_dir: Path, title: str | None = None, back_link: str = "") -> None:
    """Write index.html + data.js + tree.js (CSP-safe, no inline scripts) for static hosting."""
    data = build_data(cfg, tree, read_json(cfg.dir / "costs.json", {}) or {}, read_json(cfg.dir / "state.json", {}) or {})
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "index.html", render_html(data, external=True, title=title, back_link=back_link))
    atomic_write_text(out_dir / "data.js", "window.__RSI_DATA__ = " + _payload(data) + ";\n")
    atomic_write_text(out_dir / "tree.js", _TREE_JS.read_text(encoding="utf-8"))


def _waiting(cfg: ExperimentCfg) -> list[dict]:
    from .setup import waiting_questions
    try:
        return waiting_questions(cfg.dir)
    except (OSError, ValueError):
        return []


def render_md(cfg: ExperimentCfg, tree: Tree, data: dict[str, Any]) -> str:
    best = tree.best()
    lines = [f"# {cfg.name} — tree ({data['generated_at']})", "",
             f"worker {data['runner']}; best `{best.id if best else '-'}` = {fmt_score(best.score if best else None)}; "
             f"baseline {fmt_score(data['root_score'])}; state {data['state'].get('status')} {data['state'].get('stop_reason') or ''}", ""]
    if data.get("waiting_questions"):
        lines += ["## Waiting for the human", "",
                  f"Answer in `setup/QUESTIONS.md` with `rsi setup {cfg.dir} --answer <id>=<choice>`; the run continues meanwhile.", ""]
        lines += [f"- `{q['id']}` ({q['importance'] or '?'}): {q['question']}" for q in data["waiting_questions"]]
        lines.append("")

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
    snap = _snapshot_tree(tree)
    data = build_data(cfg, snap, costs or {}, state or {})
    atomic_write_text(cfg.dir / "tree.html", render_html(data))
    atomic_write_text(cfg.dir / "tree.md", render_md(cfg, snap, data))
