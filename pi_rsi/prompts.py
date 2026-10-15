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
from .memory import research_context

_DIR = Path(__file__).parent / "prompts"


def template(name: str) -> Template:
    return Template((_DIR / f"{name}.md").read_text(encoding="utf-8"))


def render(name: str, **kw: Any) -> str:
    return template(name).safe_substitute({k: ("" if v is None else str(v)) for k, v in kw.items()})


def direction(cfg: ExperimentCfg) -> str:
    return "higher is better" if cfg.task.higher_is_better else "lower is better"


def task_brief(cfg: ExperimentCfg) -> str:
    return read_text(cfg.task_dir / cfg.task.brief, "(no task brief)")


def objective_block(cfg: ExperimentCfg) -> str:
    """The competition playbook for score-first tasks; empty for the default research objective."""
    return "\n" + (_DIR / "competition.md").read_text(encoding="utf-8") + "\n" if cfg.task.competition else ""


def proposal_rule(cfg: ExperimentCfg) -> str:
    if cfg.task.competition:
        return ("Rank proposals by expected official-score gain per hour of work. Propose an ablation only when its "
                "answer decides between two high-value directions or explains a regression.")
    return "At least one proposal should be a discriminating ablation when a material mechanism remains uncertain."


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
    if parent and parent.id != "root" and cfg.research.enabled:
        pd = node_dir(cfg, parent.id)
        parent_handoff = (f"### What `{parent.id}` built (IMPLEMENTATION.md)\n"
                          + read_text(pd / "IMPLEMENTATION.md", "(no implementation record)")
                          + f"\n\n### What its official result means (HANDOFF.md)\n"
                          + read_text(pd / "HANDOFF.md", "(no result analysis; see its summary above)"))
    elif parent and parent.id != "root":
        parent_handoff = read_text(node_dir(cfg, parent.id) / "HANDOFF.md", "(parent left no handoff; see its summary above)")
    elif parent and parent.id == "root":
        parent_handoff = "(parent is the root baseline; there is no handoff. Baseline metrics excerpt:)\n" + \
            json.dumps({k: v for k, v in parent.metrics.items() if not k.startswith("_") and k != "per_seed"}, indent=1)[:2000]
    best = tree.best()
    root = tree.get("root")
    advice_block = ""
    if node.advice:
        advice_block = (f"\n# Advice from the failure diagnoser (this is a retry, attempt {node.attempt})\n{node.advice}\n"
                        "This attempt belongs to the SAME hypothesis. Existing TUNING.jsonl is cumulative: "
                        "do not erase previous fits, reset the tuning allowance, or count inherited artifacts as new observations.\n")
    human_block = ""
    hn = "\n\n".join(t for t in (read_text(cfg.dir / "HUMAN.md").strip(), read_text(node_dir(cfg, node.id) / "HUMAN.md").strip()) if t)
    if hn:
        human_block = f"\n# Note from the human reviewer\n{hn}\n"
    prop = node.worker.get("proposal", {}) if node.worker else {}
    kw = dict(
        task_brief=task_brief(cfg), branch=node.branch, worktree=str(worktree), node_id=node.id, depth=node.depth,
        parent_id=node.parent, parent_score=fmt_score(parent.score if parent else None),
        best_score=fmt_score(best.score if best else None), best_id=best.id if best else "-",
        root_score=fmt_score(root.score), node_dir=str(node_dir(cfg, node.id)),
        minutes=cfg.runner.node_timeout_s // 60, max_turns=cfg.runner.max_turns, score_key=cfg.task.score_key,
        direction=direction(cfg), official_seedset=cfg.task.official_seedset, advice_block=advice_block,
        human_block=human_block, title=node.title, hypothesis=node.hypothesis, kind=node.kind,
        expected_gain=prop.get("expected_gain", "unknown"), risk=prop.get("risk", "unknown"),
        path_block=_path_block(cfg, tree, node), parent_handoff=parent_handoff,
        insights=read_text(cfg.insights_path, "(none yet)")[-4000:] if cfg.memory.enabled else read_text(cfg.insights_path, "(none yet)"),
        deadends=read_text(cfg.deadends_path, "(none yet)")[-4000:] if cfg.memory.enabled else read_text(cfg.deadends_path, "(none yet)"),
        research_memory=read_text(node_dir(cfg, node.id) / "MEMORY.md") if cfg.memory.enabled else "",
        quick_cmd=_quick_cmd(cfg),
        val_rule=_val_rule(cfg),
        research_plan=(read_text(Path(node.worker["research"]["think_path"]))[:18000]
                       if node.worker.get("research", {}).get("think_path") else "(legacy/retry: use the hypothesis above)"),
        tuning_budget=json.dumps(node.worker.get("research", {}).get("tuning_budget", {})),
        code_rules=("`agent.py` stays the entry point exposing `agent(obs)`; helpers go in `src/`."
                    if (cfg.repo_dir / "agent.py").exists() else
                    "Preserve the entry points/interfaces specified in TASK.md; helpers go in `src/`."),
        entry_files="the current `agent.py`" if (cfg.repo_dir / "agent.py").exists() else "the task's current entry-point code",
        objective_block=objective_block(cfg), proposal_rule=proposal_rule(cfg),
        notes_file="IMPLEMENTATION.md" if cfg.research.enabled else "HANDOFF.md",
    )
    mode = "research" if cfg.research.enabled else "legacy"
    kw["context_block"] = render(f"worker_context_{mode}", **kw)
    kw["deliverables"] = render(f"worker_deliverables_{mode}", **kw)
    if cfg.research.enabled:
        kw["deliverables"] += render("worker_delivery", **kw)
    return render("worker", **kw)


def _quick_cmd(cfg: ExperimentCfg) -> str:
    if cfg.task.job_enabled:
        from .evaluator import job_command
        return " ".join(job_command(cfg, cfg.task.quick_seedset, f"runs/{cfg.task.quick_seedset}"))
    return cfg.task.worker_eval_command.format(seedset=cfg.task.quick_seedset, python=_python(cfg))


def _val_rule(cfg: ExperimentCfg) -> str:
    if cfg.task.job_enabled:
        return (f"The official `{cfg.task.official_seedset}` run (budget {cfg.task.job_budgets.get(cfg.task.official_seedset)}) is "
                f"submitted to the job queue by the harness after you finish; do not run it yourself. When it completes you will "
                f"be woken up in this same session to update the handoff with its result.")
    cmd = cfg.task.worker_val_command
    if cmd is None:
        cmd = cfg.task.worker_eval_command
    if cmd == "":
        return (f"The official `{cfg.task.official_seedset}` score is computed on data you cannot see; do not try to find it. "
                f"Report your quick-set numbers and say they are quick-set numbers.")
    val_cmd = cmd.format(seedset=cfg.task.official_seedset, python=_python(cfg))
    return f"Before finishing, run the official seed set once: `{val_cmd}`."


def planner_root_prompt(cfg: ExperimentCfg, tree: Tree, k: int) -> str:
    root = tree.get("root")
    starter = ""
    for p in sorted(cfg.repo_dir.glob("*.py")) + sorted((cfg.repo_dir / "src").glob("*.py")):
        starter += f"\n### {p.relative_to(cfg.repo_dir)}\n```python\n{read_text(p)[:6000]}\n```\n"
    docs = ""
    for d in cfg.task.docs:
        docs += f"\n### {d}\n{read_text(cfg.task_dir / d)[:12000]}\n"
    human = read_text(cfg.dir / "HUMAN.md").strip()
    brief = task_brief(cfg) + (f"\n\n# Note from the human reviewer\n{human}\n" if human else "")
    return render("planner_root", k=k, minutes=cfg.runner.node_timeout_s // 60, task_brief=brief + objective_block(cfg),
                  root_score=fmt_score(root.score), score_key=cfg.task.score_key, direction=direction(cfg),
                  root_metrics=json.dumps({k: v for k, v in root.metrics.items() if not k.startswith("_") and k != "per_seed"}, indent=1)[:2000],
                  starter_code=starter or "(no starter code found)", docs_excerpt=docs or "(no docs)",
                  research_memory=research_context(cfg, brief))


def planner_child_prompt(cfg: ExperimentCfg, tree: Tree, parent: Node, k: int) -> str:
    best = tree.best()
    root = tree.get("root")
    sib = []
    for c in tree.children(parent.id):
        sib.append(f"- `{c.id}` [{c.status}/{c.verdict or '-'}] score {fmt_score(c.score)}: {c.title} — {c.summary[:300]}")
    human = read_text(cfg.dir / "HUMAN.md").strip()
    brief = task_brief(cfg) + (f"\n\n# Note from the human reviewer\n{human}\n" if human else "")
    return render("planner_child", k=k, minutes=cfg.runner.node_timeout_s // 60, task_brief=brief + objective_block(cfg),
                  parent_id=parent.id, parent_score=fmt_score(parent.score), best_score=fmt_score(best.score if best else None),
                  root_score=fmt_score(root.score),
                  parent_handoff=read_text(node_dir(cfg, parent.id) / "HANDOFF.md", parent.summary or "(no handoff)"),
                  siblings="\n".join(sib) or "(none)",
                  insights=read_text(cfg.insights_path, "(none yet)")[-4000:] if cfg.memory.enabled else read_text(cfg.insights_path, "(none yet)"),
                  deadends=read_text(cfg.deadends_path, "(none yet)")[-4000:] if cfg.memory.enabled else read_text(cfg.deadends_path, "(none yet)"),
                  queued=json.dumps([p for i, p in enumerate(parent.proposals) if i not in parent.proposals_used], ensure_ascii=False),
                  research_memory=research_context(cfg, parent.title + " " + parent.hypothesis))


def auditor_prompt(cfg: ExperimentCfg, tree: Tree, node: Node, metrics: dict, gitlog: str, diffstat: str, noise: float,
                   assessment: dict | None = None) -> str:
    nd = node_dir(cfg, node.id)
    parent = tree.get(node.parent) if node.parent else None
    m = {k: v for k, v in metrics.items() if k != "per_seed"}
    if assessment is not None:  # research mode: the harness judges, the wiki keeps cross-node knowledge
        rules = (f'- "verdict": copy the harness verdict "{assessment["verdict"]}" (delta {fmt_score(assessment["signed_delta"])}, '
                 f'threshold {fmt_score(assessment["threshold"])}, method {assessment["method"]}). Do not apply or state a '
                 'threshold of your own, in the verdict or the summary.\n'
                 '- "insights" and "deadends": empty lists; cross-node knowledge is kept in the research wiki.')
        handoff = ("## Implementation record (worker, before the official result)\n"
                   + read_text(nd / "IMPLEMENTATION.md", "(no implementation record written)")[:6000]
                   + "\n\n## Result analysis (research lead, after the official result)\n"
                   + read_text(nd / "HANDOFF.md", "(no analysis written)")[:6000])
    else:
        rules = ('- "verdict": one of "improved" | "no_change" | "worse" | "failed", judged on the official score versus the '
                 f"parent's official score ({fmt_score(parent.score if parent else None)}). Treat |delta| below "
                 f'{fmt_score(noise)} as no_change.\n'
                 '- "insights": list of 0-3 short general facts supported by the evidence and reusable by future nodes, each '
                 'with the mechanism (why). Empty list if none.\n'
                 '- "deadends": list of 0-3 short statements of what was shown not to work, each with the evidence. '
                 'Empty list if none.')
        handoff = read_text(nd / "HANDOFF.md", "(no handoff written)")[:8000]
    return render("auditor", node_id=node.id, judgement_rules=rules,
                  score_key=cfg.task.score_key, direction=direction(cfg), official_seedset=cfg.task.official_seedset,
                  title=node.title, hypothesis=node.hypothesis, metrics=json.dumps(m, indent=1)[:4000],
                  handoff=handoff,
                  progress=tail_text(nd / "PROGRESS.md", 120, 8000) or "(no progress log)",
                  gitlog=gitlog + (("\n\nPRIVACY FLAG: the worker's tool calls touched a private/ path: " + node.worker.get("privacy_flag")) if node.worker.get("privacy_flag") else ""),
                  diffstat=diffstat)


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
                    "research_question": {"type": "string"},
                    "prediction": {"type": "string"},
                    "falsifier": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
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
