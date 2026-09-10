"""Run one node end to end: worktree -> worker session -> commit -> guard -> official eval -> audit."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from . import gitops
from . import prompts as P
from .evaluator import run_eval, score_of, EvalError
from .tree import Node
from .util import now_iso, read_json, read_text, append_text, atomic_write_text, tail_text, fmt_score, now_ts

FROZEN_PATHS = ["eval/", "docs/"]


class NodeFailure(Exception):
    pass


def run_node(orch, node: Node) -> None:
    cfg, tree = orch.cfg, orch.tree
    nd = cfg.nodes_dir / node.id
    nd.mkdir(parents=True, exist_ok=True)
    parent = tree.get(node.parent)
    worktree = cfg.worktrees_dir / node.id
    branch = f"node/{node.id}"
    base = node.base_commit or parent.commit
    t0 = time.time()
    try:
        gitops.add_worktree(cfg.repo_dir, worktree, branch, base)
        tree.update(node, status="running", started_at=now_iso(), branch=branch, base_commit=base,
                    worker={**node.worker, "kind": cfg.runner.kind, "model": cfg.runner.model, "effort": cfg.runner.effort})
        atomic_write_text(nd / "HYPOTHESIS.md", f"# {node.title}\n\n{node.hypothesis}\n\n"
                          f"type: {node.kind}\nparent: {node.parent}\nbase commit: {base}\n")
        orch.log("node_start", node=node.id, parent=node.parent, title=node.title, base=gitops.short(base))
        orch.render()

        # 1. worker session --------------------------------------------------
        prompt = P.worker_prompt(cfg, tree, node, worktree)
        hb = nd / "heartbeat"

        def on_event(ev):
            try:
                hb.write_text(str(ev["t"]))
            except OSError:
                pass

        res = orch.worker_runner.run_agent(prompt, cwd=worktree, log_path=nd / "runner.jsonl", max_turns=cfg.runner.max_turns,
                                           timeout_s=cfg.runner.node_timeout_s, idle_timeout_s=cfg.runner.idle_timeout_s,
                                           on_event=on_event)
        orch.add_cost("worker", res)
        orch.log("worker_end", node=node.id, ok=res.ok, error=res.error, duration_s=round(res.duration_s, 1),
                 turns=res.num_turns, tool_calls=res.tool_calls, cost_usd=res.cost_usd, session=res.session_id)
        usage = dict(res.usage)
        cost = res.cost_usd
        worker_info = {**node.worker, "session_id": res.session_id, "runner_ok": res.ok, "runner_error": res.error,
                       "turns": res.num_turns, "tool_calls": res.tool_calls}

        # 2. commit whatever is there ---------------------------------------
        commit = gitops.commit_all(worktree, f"rsi: end of node {node.id} (auto-commit)") or gitops.head(worktree)
        tree.update(node, commit=commit, usage=usage, cost_usd=cost, worker=worker_info)

        # 3. handoff rescue --------------------------------------------------
        if not (nd / "HANDOFF.md").exists() and res.session_id and hasattr(orch.worker_runner, "resume_agent"):
            orch.log("handoff_rescue", node=node.id)
            rescue_prompt = (f"Your session was cut off by the budget. Do not change code. Write {nd}/HANDOFF.md and "
                             f"{nd}/proposals.json now, following the schemas from your instructions, using only numbers "
                             f"you actually observed (see {nd}/PROGRESS.md). Then stop.")
            r2 = orch.worker_runner.resume_agent(res.session_id, rescue_prompt, cwd=worktree, log_path=nd / "runner.rescue.jsonl",
                                                 max_turns=8, timeout_s=600, idle_timeout_s=300)
            orch.add_cost("worker", r2)
            c2 = gitops.commit_all(worktree, f"rsi: after handoff rescue {node.id}")
            if c2:
                commit = c2
                tree.update(node, commit=commit)

        # 4. frozen-path guard ---------------------------------------------
        touched = gitops.changed_paths(worktree, base, "HEAD", FROZEN_PATHS)
        if touched:
            raise NodeFailure(f"modified frozen paths: {touched[:5]}")

        # 5. official evaluation -----------------------------------------------
        tree.update(node, status="evaluating")
        orch.render()
        try:
            metrics = run_eval(cfg, worktree, cfg.task.official_seedset, nd / "eval")
        except EvalError as e:
            raise NodeFailure(f"official evaluation failed: {e}")
        score = score_of(cfg, metrics)
        if score is None:
            raise NodeFailure(f"evaluator produced no '{cfg.task.score_key}' in metrics")
        quick = read_json(worktree / "metrics.quick.json") or {}
        quick_score = quick.get(cfg.task.score_key)
        proposals = _load_proposals(nd / "proposals.json")
        gitlog = gitops.log_oneline(worktree, base)
        diffstat = gitops.diff_stat(worktree, base)
        best_before = tree.best()
        delta_parent = (score - parent.score) if parent.score is not None else None
        delta_best = (score - best_before.score) if (best_before and best_before.score is not None) else None
        if not tree.higher_is_better():
            delta_parent = -delta_parent if delta_parent is not None else None
            delta_best = -delta_best if delta_best is not None else None
        tree.update(node, score=score, metrics={k: v for k, v in metrics.items() if k != "per_seed"},
                    quick_score=quick_score, proposals=proposals, delta_parent=delta_parent, delta_best=delta_best)
        orch.log("eval_done", node=node.id, score=score, delta_parent=delta_parent, delta_best=delta_best,
                 elapsed_s=metrics.get("_eval", {}).get("elapsed_s"))

        # 6. audit -------------------------------------------------------------
        noise = orch.noise_level()
        audit = orch.utility.audit(node, metrics, gitlog, diffstat, noise)
        _record_audit(orch, node, audit, gitlog, diffstat)
        gitops.tag(cfg.repo_dir, f"rsi/{node.id}", commit)
        tree.update(node, status="done", finished_at=now_iso(), duration_s=round(time.time() - t0, 1),
                    summary=audit["summary"], verdict=audit["verdict"], audit=audit)
        orch.log("node_done", node=node.id, score=score, verdict=audit["verdict"], title=node.title)
    except NodeFailure as e:
        _fail(orch, node, str(e), nd, worktree, t0)
    except Exception as e:  # harness bug or infra failure: record, do not crash the loop
        import traceback
        append_text(nd / "harness_error.log", traceback.format_exc())
        _fail(orch, node, f"harness error: {type(e).__name__}: {e}", nd, worktree, t0)
    finally:
        orch.render()


def _fail(orch, node: Node, failure: str, nd: Path, worktree: Path, t0: float) -> None:
    tree = orch.tree
    runner_tail = tail_text(nd / "runner.jsonl", 60, 12000)
    try:
        gitstatus = gitops.git(["status", "--short"], cwd=worktree, check=False) if worktree.exists() else "(no worktree)"
        gitlog = gitops.log_oneline(worktree, node.base_commit or "HEAD~0") if worktree.exists() else ""
    except Exception:
        gitstatus, gitlog = "(unavailable)", ""
    diagnosis = orch.utility.diagnose(node, failure, runner_tail, gitstatus + "\n" + gitlog)
    tree.update(node, status="failed", failure=failure, diagnosis=diagnosis, finished_at=now_iso(),
                duration_s=round(time.time() - t0, 1), verdict="failed",
                summary=f"FAILED: {failure[:160]} — {diagnosis.get('cause', '')[:200]}")
    atomic_write_text(nd / "FAILURE.md", f"# Failure {node.id}\n\n{failure}\n\n## Diagnosis\n{json.dumps(diagnosis, indent=1)}\n")
    orch.log("node_failed", node=node.id, failure=failure, retry=diagnosis.get("retry"), cause=diagnosis.get("cause"))


def _load_proposals(path: Path) -> list[dict[str, Any]]:
    from .agents import _clean_proposals
    data = read_json(path)
    if data is None:
        return []
    try:
        return _clean_proposals(data)[:3]
    except Exception:
        return []


def _record_audit(orch, node: Node, audit: dict, gitlog: str, diffstat: str) -> None:
    cfg = orch.cfg
    nd = cfg.nodes_dir / node.id
    lines = [f"# Summary {node.id}: {node.title}", "", audit["summary"], "",
             f"- official {cfg.task.score_key}: {fmt_score(node.score)} (delta vs parent {fmt_score(node.delta_parent)}, vs best {fmt_score(node.delta_best)})",
             f"- verdict: {audit['verdict']}", f"- commit: {gitops.short(node.commit)}",
             f"- claim check: {'consistent' if audit['claim_check'].get('consistent') else 'MISMATCH'} — {audit['claim_check'].get('note', '')}",
             "", "## Git log", "```", gitlog or "(no commits)", "```", "```", diffstat, "```"]
    atomic_write_text(nd / "SUMMARY.md", "\n".join(lines) + "\n")
    for ins in audit.get("insights", []) or []:
        append_text(cfg.insights_path, f"- {ins.strip()} [{node.id}, score {fmt_score(node.score)}]\n")
    for de in audit.get("deadends", []) or []:
        append_text(cfg.deadends_path, f"- {de.strip()} [{node.id}]\n")
