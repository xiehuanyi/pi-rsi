"""Logistics that need no LLM most of the time: the submitter (final-level evaluations with a cap and a ledger),
the infra sentinel (disk, GPU, orphans, stale worktrees) and the harness repair entry point (an ops agent on a branch)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .config import ExperimentCfg
from .home import REPO
from .util import now_iso, read_json, append_text, fmt_score, human_duration, tail_text


# submitter ---------------------------------------------------------------------------------------
def submissions(cfg: ExperimentCfg) -> list[dict[str, Any]]:
    out = []
    for m in sorted(cfg.nodes_dir.glob(f"*/eval/metrics.{cfg.task.final_seedset}*.json")):
        d = read_json(m) or {}
        if d.get("score") is None:
            continue
        out.append({"node": m.parent.parent.name, "file": str(m), "score": d["score"], "time": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(m.stat().st_mtime))})
    return out


def submit(cfg: ExperimentCfg, tree, node_id: str | None, max_submissions: int, tag: str = "manual") -> dict[str, Any]:
    from .evaluator import run_eval, score_of
    done = submissions(cfg)
    if max_submissions and len(done) >= max_submissions:
        raise RuntimeError(f"submission cap reached ({len(done)}/{max_submissions}); raise hooks.max_submissions to continue")
    node = tree.get(node_id) if node_id else tree.best()
    if node is None or node.id == "root":
        raise RuntimeError("no node to submit")
    wt = cfg.worktrees_dir / node.id
    m = run_eval(cfg, wt, cfg.task.final_seedset, cfg.nodes_dir / node.id / "eval", tag=tag, owner=f"{cfg.name}/{node.id}")
    s = score_of(cfg, m)
    row = {"time": now_iso(), "node": node.id, "official": node.score, "final": s, "commit": (node.commit or "")[:8], "tag": tag}
    ledger = cfg.dir / "SUBMISSIONS.md"
    if not ledger.exists():
        append_text(ledger, f"# Submissions ({cfg.task.final_seedset})\n\n| time | node | official ({cfg.task.official_seedset}) | final | commit | tag |\n|---|---|---|---|---|---|\n")
    append_text(ledger, f"| {row['time']} | {row['node']} | {fmt_score(row['official'])} | {fmt_score(row['final'])} | {row['commit']} | {tag} |\n")
    return row


# sentinel ------------------------------------------------------------------------------------------
def sentinel(experiments_root: Path, prune: bool = False, kill_orphans: bool = False) -> dict[str, Any]:
    report: dict[str, Any] = {"time": now_iso(), "warnings": []}
    st = shutil.disk_usage(experiments_root)
    report["disk"] = {"free_gb": round(st.free / 1e9, 1), "free_pct": round(100 * st.free / st.total, 1)}
    if report["disk"]["free_pct"] < 5:
        report["warnings"].append(f"disk nearly full: {report['disk']['free_gb']} GB free")
    try:
        q = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,memory.total,utilization.gpu", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=10).stdout
        report["gpus"] = [dict(zip(("index", "mem_used_mb", "mem_total_mb", "util_pct"), [int(x) for x in l.split(",")])) for l in q.strip().splitlines() if l.strip()]
    except Exception:
        report["gpus"] = []
    # experiments: status, size, live processes
    exps = []
    finished_dirs = []
    for exp in sorted(p for p in experiments_root.iterdir() if (p / "rsi.toml").exists()):
        state = read_json(exp / "state.json", {}) or {}
        alive = False
        if state.get("pid"):
            try:
                os.kill(int(state["pid"]), 0)
                alive = time.time() - float(state.get("heartbeat", 0)) < 300
            except OSError:
                alive = False
        size = sum(f.stat().st_size for f in exp.rglob("*") if f.is_file()) / 1e6
        exps.append({"name": exp.name, "status": state.get("status"), "alive": alive, "size_mb": round(size, 1)})
        if state.get("status") == "finished" or (state.get("status") in ("running", "finishing") and not alive):
            finished_dirs.append(exp)
        if state.get("status") in ("running", "finishing") and not alive:
            report["warnings"].append(f"{exp.name}: state says {state.get('status')} but no live orchestrator (crashed?) -> `rsi run` resumes it")
    report["experiments"] = exps
    # orphans: agent/evaluator processes whose cwd is inside a finished experiment's worktrees
    orphans = []
    for pid in (p for p in os.listdir("/proc") if p.isdigit()):
        try:
            cwd = os.readlink(f"/proc/{pid}/cwd")
            cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        for exp in finished_dirs:
            if cwd.startswith(str(exp / "worktrees")) and ("grok" in cmd or "eval.py" in cmd or "train.py" in cmd):
                orphans.append({"pid": int(pid), "cwd": cwd, "cmd": cmd[:120]})
    report["orphans"] = orphans
    if orphans:
        report["warnings"].append(f"{len(orphans)} orphan process(es) in finished experiments" + (" (killed)" if kill_orphans else " (use --kill-orphans)"))
        if kill_orphans:
            for o in orphans:
                try:
                    os.kill(o["pid"], 15)
                except OSError:
                    pass
    # stale worktrees of finished experiments (keep the best path and root)
    pruned = []
    if prune:
        from .tree import Tree
        from . import gitops
        for exp in finished_dirs:
            try:
                tree = Tree.load(exp / "tree.json")
            except Exception:
                continue
            best = tree.best()
            keep = {n.id for n in (tree.ancestors(best.id) + [best])} if best else set()
            for wt in (exp / "worktrees").glob("n*"):
                if wt.name not in keep:
                    gitops.remove_worktree(exp / "repo", wt, branch=None)
                    pruned.append(f"{exp.name}/{wt.name}")
    report["pruned_worktrees"] = pruned
    append_text(experiments_root / "sentinel.log", json.dumps(report, ensure_ascii=False) + "\n")
    return report


# harness repair ------------------------------------------------------------------------------------
def collect_crashes(cfg: ExperimentCfg, limit: int = 3) -> str:
    out = []
    for line in tail_text(cfg.events_path, 400, 200000).splitlines():
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("event") in ("node_crash", "render_error", "hook_failed", "narrative_failed"):
            out.append(json.dumps(d)[:3000])
    for f in sorted(cfg.nodes_dir.glob("*/harness_error.log"))[-limit:]:
        out.append(f"--- {f} ---\n" + tail_text(f, 60, 6000))
    return "\n".join(out[-limit * 2:]) or "(no harness crashes recorded)"


def repair(orch, evidence: str, branch: str | None = None) -> dict[str, Any]:
    from .ops import run_ops
    from . import gitops
    branch = branch or f"repair/{time.strftime('%Y%m%dT%H%M%S')}"
    gitops.git(["checkout", "-q", "-b", branch], cwd=REPO)
    problem = ("The harness itself (pi_rsi/ in the checkout) raised exceptions during a run. Find the root cause in the harness "
               "code, fix it, add or extend a test under tests/ that would have caught it, and make `tests/test_loop.sh` pass. "
               f"You are on git branch {branch}; commit your fix there. Do not touch experiment data.")
    v = run_ops(orch, problem, evidence, max_turns=orch.cfg.ops.max_turns, timeout_s=orch.cfg.ops.timeout_s)
    v["branch"] = branch
    v["diffstat"] = gitops.git(["diff", "--stat", "main", branch], cwd=REPO, check=False)
    return v
