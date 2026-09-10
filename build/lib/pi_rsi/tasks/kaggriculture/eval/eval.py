#!/usr/bin/env python3
"""Frozen evaluator for the Kaggriculture task.

Plays the agent in `<agent-dir>/agent.py` against the built-in `starter` opponent on a fixed seed set, both seats
per seed, and reports the mean final money of the agent (the competition reward) plus diagnostics.

    python eval/eval.py --seedset quick            # from inside a worktree (agent-dir = repo root)
    python eval/eval.py --agent-dir /path/to/worktree --seedset validation --out metrics.json

The harness runs its own copy of this file; edits to the in-repo copy do not change official scores.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import multiprocessing as mp
import os
import statistics
import subprocess
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
OPPONENT_DEFAULT = "starter"


def load_agent(agent_dir: Path):
    agent_path = agent_dir / "agent.py"
    if not agent_path.exists():
        raise FileNotFoundError(f"{agent_path} not found")
    if str(agent_dir) not in sys.path:
        sys.path.insert(0, str(agent_dir))
    spec = importlib.util.spec_from_file_location("rsi_agent_module", agent_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    fn = getattr(mod, "agent", None)
    if not callable(fn):
        raise AttributeError("agent.py must define a callable `agent(obs)`")
    return fn


_AGENT = None


def _init_worker(agent_dir: str):
    global _AGENT
    os.environ.setdefault("PYTHONHASHSEED", "0")
    _AGENT = load_agent(Path(agent_dir))


def _play(job):
    seed, seat, opponent = job
    from kaggle_environments import make
    t0 = time.time()
    rec = {"seed": seed, "seat": seat, "money": 0.0, "opp_money": None, "status": "ERROR", "error": "", "elapsed_s": 0.0}
    try:
        env = make("kaggriculture", configuration={"seed": seed}, debug=False)
        players = [_AGENT, opponent] if seat == 0 else [opponent, _AGENT]
        env.run(players)
        last = env.steps[-1]
        me, opp = last[seat], last[1 - seat]
        rec["status"] = me["status"]
        rec["opp_status"] = opp["status"]
        farms = last[0]["observation"].get("farms", [])
        if farms:
            rec["money"] = float(farms[seat]["money"])
            rec["opp_money"] = float(farms[1 - seat]["money"])
        if me["status"] != "DONE":
            rec["money"] = 0.0
            rec["error"] = f"agent status {me['status']}"
            # find the step where the agent errored for the log
            for i, st in enumerate(env.steps):
                if st[seat]["status"] not in ("ACTIVE", "DONE", "INACTIVE"):
                    rec["error"] += f" at step {i}"
                    break
    except Exception as e:  # environment-level failure
        rec["error"] = f"{type(e).__name__}: {e}"
        rec["trace"] = traceback.format_exc()[-1500:]
    rec["elapsed_s"] = round(time.time() - t0, 2)
    return rec


def git_sha(agent_dir: Path) -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=agent_dir, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent-dir", default=None, help="directory containing agent.py (default: parent of eval/)")
    ap.add_argument("--seedset", default="quick")
    ap.add_argument("--seeds", default=None, help="comma-separated explicit seeds (overrides --seedset)")
    ap.add_argument("--opponent", default=OPPONENT_DEFAULT)
    ap.add_argument("--out", default=None, help="metrics json path (default: <agent-dir>/metrics.<seedset>.json)")
    ap.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    agent_dir = Path(a.agent_dir).resolve() if a.agent_dir else HERE.parent
    seedsets = json.loads((HERE / "seedsets.json").read_text())
    if a.seeds:
        seeds = [int(s) for s in a.seeds.split(",") if s.strip()]
        setname = "custom"
    else:
        if a.seedset not in seedsets:
            print(f"unknown seedset {a.seedset}; choose from {sorted(seedsets)}", file=sys.stderr)
            return 2
        seeds = seedsets[a.seedset]
        setname = a.seedset
    out = Path(a.out) if a.out else agent_dir / f"metrics.{setname}.json"

    t0 = time.time()
    try:
        load_agent(agent_dir)  # fail fast with a readable error before spawning workers
    except Exception as e:
        metrics = {"score": 0.0, "error": f"agent failed to load: {type(e).__name__}: {e}", "trace": traceback.format_exc()[-2000:],
                   "seedset": setname, "n_games": 0, "errors": 1}
        out.write_text(json.dumps(metrics, indent=1))
        print(f"AGENT LOAD ERROR: {metrics['error']}", file=sys.stderr)
        return 1

    jobs = [(s, seat, a.opponent) for s in seeds for seat in (0, 1)]
    ctx = mp.get_context("fork")
    with ctx.Pool(processes=max(1, min(a.workers, len(jobs))), initializer=_init_worker, initargs=(str(agent_dir),)) as pool:
        results = pool.map(_play, jobs)

    monies = [r["money"] for r in results]
    margins = [r["money"] - (r["opp_money"] or 0.0) for r in results]
    wins = [1.0 if (r["opp_money"] is not None and r["money"] > r["opp_money"]) else 0.0 for r in results]
    errors = sum(1 for r in results if r["status"] != "DONE")
    n = len(results)
    std = statistics.pstdev(monies) if n > 1 else 0.0
    metrics = {
        "score": round(sum(monies) / n, 2),
        "margin": round(sum(margins) / n, 2),
        "win_rate": round(sum(wins) / n, 3),
        "n_games": n,
        "errors": errors,
        "score_std": round(std, 2),
        "score_sem": round(std / math.sqrt(n), 2) if n else 0.0,
        "min_money": min(monies),
        "max_money": max(monies),
        "seedset": setname,
        "opponent": a.opponent,
        "elapsed_s": round(time.time() - t0, 1),
        "agent_dir": str(agent_dir),
        "git_sha": git_sha(agent_dir),
        "per_seed": results,
        "per_item": [{"id": f"{r['seed']}-{r['seat']}", "value": r["money"]} for r in results],
        "score_transform": "mean",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(metrics, indent=1))
    if not a.quiet:
        print(f"[{setname}] score={metrics['score']:.1f} (mean final money over {n} games, both seats vs {a.opponent}) "
              f"margin={metrics['margin']:.1f} win_rate={metrics['win_rate']:.2f} errors={errors} "
              f"std={std:.1f} elapsed={metrics['elapsed_s']}s -> {out}")
        if errors:
            for r in results:
                if r["status"] != "DONE":
                    print(f"  seed {r['seed']} seat {r['seat']}: {r['error']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
