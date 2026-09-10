"""Prompt assembly from templates in pi_rsi/prompts/*.md (string.Template, $placeholders)."""
from __future__ import annotations

import json
from pathlib import Path
from string import Template
from typing import Any

from .config import ExperimentCfg
from .evaluator import _python
from .tree import Node, Tree
from .util import read_text, fmt_score, tail_text

_DIR = Path(__file__).parent / "prompts"


def template(name: str) -> Template:
    return Template((_DIR / f"{name}.md").read_text(encoding="utf-8"))


def render(name: str, **kw: Any) -> str:
    return template(name).safe_substitute({k: ("" if v is None else str(v)) for k, v in kw.items()})


def direction(cfg: ExperimentCfg) -> str:
    return "higher is better" if cfg.task.higher_is_better else "lower is better"


def task_brief(cfg: ExperimentCfg) -> str:
    return read_text(cfg.task_dir / cfg.task.brief, "(no task brief)")


def node_dir(cfg: ExperimentCfg, node_id: str) -> Path:
    return cfg.nodes_dir / node_id


def _path_block(cfg: ExperimentCfg, tree: Tree, node: Node) -> str:
    lines = []
    for a in tree.ancestors(node.id):
        s = a.summary or a.title
        lines.append(f"- `{a.id}` (score {fmt_score(a.score)}, {a.verdict or a.status}): {a.title} — {s}")
    return "\n".join(lines) if lines else "- (root)"


def worker_prompt(cfg: ExperimentCfg, tree: Tree, node: Node, worktree: Path) -> str:
    parent = tree.get(node.parent) if node.parent else None
    parent_handoff = "(root: no parent handoff; start from the baseline code)"
    if parent and parent.id != "root":
        parent_handoff = read_text(node_dir(cfg, parent.id) / "HANDOFF.md", "(parent left no handoff; see its summary above)")
    elif parent and parent.id == "root":
        parent_handoff = "(parent is the root baseline; there is no handoff. Baseline metrics excerpt:)\n" + \
            json.dumps({k: v for k, v in parent.metrics.items() if not k.startswith("_") and k != "per_seed"}, indent=1)[:2000]
    best = tree.best()
    root = tree.get("root")
    advice_block = ""
    if node.advice:
        advice_block = f"\n# Advice from the failure diagnoser (this is a retry, attempt {node.attempt})\n{node.advice}\n"
    human_block = ""
    hn = read_text(node_dir(cfg, node.id) / "HUMAN.md").strip()
    if hn:
        human_block = f"\n# Note from the human reviewer\n{hn}\n"
    prop = node.worker.get("proposal", {}) if node.worker else {}
    return render(
        "worker",
        task_brief=task_brief(cfg), branch=node.branch, worktree=str(worktree), node_id=node.id, depth=node.depth,
        parent_id=node.parent, parent_score=fmt_score(parent.score if parent else None),
        best_score=fmt_score(best.score if best else None), best_id=best.id if best else "-",
        root_score=fmt_score(root.score), node_dir=str(node_dir(cfg, node.id)),
        minutes=cfg.runner.node_timeout_s // 60, max_turns=cfg.runner.max_turns, score_key=cfg.task.score_key,
        direction=direction(cfg), official_seedset=cfg.task.official_seedset, advice_block=advice_block,
        human_block=human_block, title=node.title, hypothesis=node.hypothesis, kind=node.kind,
        expected_gain=prop.get("expected_gain", "unknown"), risk=prop.get("risk", "unknown"),
        path_block=_path_block(cfg, tree, node), parent_handoff=parent_handoff,
        insights=read_text(cfg.insights_path, "(none yet)"), deadends=read_text(cfg.deadends_path, "(none yet)"),
        quick_cmd=cfg.task.worker_eval_command.format(seedset=cfg.task.quick_seedset, python=_python(cfg)),
        val_cmd=cfg.task.worker_eval_command.format(seedset=cfg.task.official_seedset, python=_python(cfg)),
    )


def planner_root_prompt(cfg: ExperimentCfg, tree: Tree, k: int) -> str:
    root = tree.get("root")
    starter = ""
    for p in sorted(cfg.repo_dir.glob("*.py")) + sorted((cfg.repo_dir / "src").glob("*.py")):
        starter += f"\n### {p.relative_to(cfg.repo_dir)}\n```python\n{read_text(p)[:6000]}\n```\n"
    docs = ""
    for d in cfg.task.docs:
        docs += f"\n### {d}\n{read_text(cfg.task_dir / d)[:12000]}\n"
    return render("planner_root", k=k, minutes=cfg.runner.node_timeout_s // 60, task_brief=task_brief(cfg),
                  root_score=fmt_score(root.score), score_key=cfg.task.score_key, direction=direction(cfg),
                  root_metrics=json.dumps({k: v for k, v in root.metrics.items() if not k.startswith("_") and k != "per_seed"}, indent=1)[:2000],
                  starter_code=starter or "(no starter code found)", docs_excerpt=docs or "(no docs)")


def planner_child_prompt(cfg: ExperimentCfg, tree: Tree, parent: Node, k: int) -> str:
    best = tree.best()
    root = tree.get("root")
    sib = []
    for c in tree.children(parent.id):
        sib.append(f"- `{c.id}` [{c.status}/{c.verdict or '-'}] score {fmt_score(c.score)}: {c.title} — {c.summary[:300]}")
    return render("planner_child", k=k, minutes=cfg.runner.node_timeout_s // 60, task_brief=task_brief(cfg),
                  parent_id=parent.id, parent_score=fmt_score(parent.score), best_score=fmt_score(best.score if best else None),
                  root_score=fmt_score(root.score),
                  parent_handoff=read_text(node_dir(cfg, parent.id) / "HANDOFF.md", parent.summary or "(no handoff)"),
                  siblings="\n".join(sib) or "(none)", insights=read_text(cfg.insights_path, "(none yet)"),
                  deadends=read_text(cfg.deadends_path, "(none yet)"))


def auditor_prompt(cfg: ExperimentCfg, tree: Tree, node: Node, metrics: dict, gitlog: str, diffstat: str, noise: float) -> str:
    nd = node_dir(cfg, node.id)
    parent = tree.get(node.parent) if node.parent else None
    m = {k: v for k, v in metrics.items() if k != "per_seed"}
    return render("auditor", node_id=node.id, parent_score=fmt_score(parent.score if parent else None), noise=fmt_score(noise),
                  score_key=cfg.task.score_key, direction=direction(cfg), official_seedset=cfg.task.official_seedset,
                  title=node.title, hypothesis=node.hypothesis, metrics=json.dumps(m, indent=1)[:4000],
                  handoff=read_text(nd / "HANDOFF.md", "(no handoff written)")[:8000],
                  progress=tail_text(nd / "PROGRESS.md", 120, 8000) or "(no progress log)", gitlog=gitlog, diffstat=diffstat)


def diagnoser_prompt(cfg: ExperimentCfg, node: Node, failure: str, runner_tail: str, gitstatus: str) -> str:
    nd = node_dir(cfg, node.id)
    return render("diagnoser", node_id=node.id, failure=failure, title=node.title, hypothesis=node.hypothesis,
                  runner_tail=runner_tail[-12000:], progress=tail_text(nd / "PROGRESS.md", 80, 6000) or "(none)",
                  gitstatus=gitstatus)


PROPOSALS_SCHEMA = {
    "type": "object",
    "properties": {
        "proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "hypothesis": {"type": "string"},
                    "type": {"type": "string", "enum": ["idea", "debug", "ablate", "scale"]},
                    "expected_gain": {"type": "string"},
                    "risk": {"type": "string"},
                },
                "required": ["title", "hypothesis", "type", "expected_gain", "risk"],
            },
        }
    },
    "required": ["proposals"],
}

AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "verdict": {"type": "string", "enum": ["improved", "no_change", "worse", "failed"]},
        "insights": {"type": "array", "items": {"type": "string"}},
        "deadends": {"type": "array", "items": {"type": "string"}},
        "claim_check": {
            "type": "object",
            "properties": {"consistent": {"type": "boolean"}, "note": {"type": "string"}},
            "required": ["consistent", "note"],
        },
    },
    "required": ["summary", "verdict", "insights", "deadends", "claim_check"],
}

DIAGNOSIS_SCHEMA = {
    "type": "object",
    "properties": {"cause": {"type": "string"}, "retry": {"type": "boolean"}, "advice": {"type": "string"}},
    "required": ["cause", "retry", "advice"],
}
