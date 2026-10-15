"""Frozen, paired-seat multi-opponent win/draw/loss evaluation for Kaggriculture.

Copied into each generated task pack. The selection score is mean(win + 0.5*draw);
money and action counts are diagnostics. Seed-level blocks keep paired seats/opponents
together for uncertainty estimates. This fixed pool is not a model of the live ladder.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.metadata
import importlib.util
import json
import multiprocessing as mp
import os
from pathlib import Path
import statistics
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_agent(path, name):
    path = Path(path).resolve()
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    fn = getattr(module, "agent")
    if not callable(fn):
        raise ValueError("agent entry point is not callable")
    return fn


def outcome(me_status, opp_status, money, opp_money):
    if opp_status != "DONE":
        raise ValueError("frozen opponent failed; this game is not valid selection evidence")
    if me_status != "DONE":
        return 0.0
    return 1.0 if money > opp_money else (0.5 if money == opp_money else 0.0)


def summarize(rows, protocol, seedset):
    if not rows:
        raise ValueError("empty evaluation")
    values = [r["value"] for r in rows]
    seeds = sorted({r["seed"] for r in rows})
    blocks = [statistics.mean(r["value"] for r in rows if r["seed"] == seed) for seed in seeds]
    opponents = sorted({r["opponent"] for r in rows})
    by_opponent = {}
    for opponent in opponents:
        group = [r for r in rows if r["opponent"] == opponent]
        by_opponent[opponent] = {
            "wins": sum(r["value"] == 1 for r in group),
            "draws": sum(r["value"] == 0.5 for r in group),
            "losses": sum(r["value"] == 0 for r in group),
            "score": statistics.mean(r["value"] for r in group),
            "money": statistics.mean(r["money"] for r in group),
            "margin": statistics.mean(r["money"] - r["opp_money"] for r in group),
            "errors": sum(r["status"] != "DONE" for r in group),
        }
    return {
        "score": statistics.mean(values), "score_transform": "mean", "protocol_id": protocol["id"],
        "seedset": seedset, "metric": "mean_win_plus_half_draw",
        "scope": "fixed archived-controller pool; not a live-ladder rating estimate",
        "n_games": len(rows), "n_seed_blocks": len(seeds),
        "wins": sum(x == 1 for x in values), "draws": sum(x == 0.5 for x in values),
        "losses": sum(x == 0 for x in values), "errors": sum(r["status"] != "DONE" for r in rows),
        "score_std": statistics.stdev(blocks) if len(blocks) > 1 else 0,
        "score_sem": statistics.stdev(blocks) / len(blocks) ** 0.5 if len(blocks) > 1 else 0,
        "mean_money": statistics.mean(r["money"] for r in rows),
        "mean_margin": statistics.mean(r["money"] - r["opp_money"] for r in rows),
        "worst_opponent_score": min(g["score"] for g in by_opponent.values()),
        "max_action_s": max(r["max_action_s"] for r in rows),
        "per_opponent": by_opponent,
        "per_item": [{"id": f"{protocol['id']}:{seed}", "value": value}
                     for seed, value in zip(seeds, blocks)],
        "per_seed": rows,
    }


def _play(job):
    candidate_dir, opponent_path, opponent, seed, seat = job
    from kaggle_environments import make
    start = time.monotonic()
    rec = {"seed": seed, "seat": seat, "opponent": opponent, "status": "ERROR",
           "opp_status": "UNKNOWN", "money": 0.0, "opp_money": 0.0, "value": 0.0,
           "max_action_s": 0.0, "requested_actions": {}, "error": ""}
    try:
        other = load_agent(opponent_path, "fixed_opponent")
        fn = load_agent(Path(candidate_dir) / "agent.py", "candidate")

        def measured(obs):
            t0 = time.monotonic()
            action = fn(obs)
            rec["max_action_s"] = max(rec["max_action_s"], time.monotonic() - t0)
            for a in [action.get("farmer", []), *action.get("hands", []), *action.get("market", [])]:
                if isinstance(a, list) and a:
                    key = str(a[0])
                    rec["requested_actions"][key] = rec["requested_actions"].get(key, 0) + 1
            return action

        env = make("kaggriculture", configuration={"seed": seed, "episodeSteps": 720}, debug=False)
        env.run([measured, other] if seat == 0 else [other, measured])
        final = env.steps[-1]
        farms = final[0]["observation"]["farms"]
        rec.update(status=final[seat]["status"], opp_status=final[1 - seat]["status"],
                   money=float(farms[seat]["money"]), opp_money=float(farms[1 - seat]["money"]))
        rec["value"] = outcome(rec["status"], rec["opp_status"], rec["money"], rec["opp_money"])
        if rec["status"] != "DONE":
            rec["error"] = "candidate failed during game"
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"
        rec["trace"] = traceback.format_exc()[-1800:]
    rec["elapsed_s"] = time.monotonic() - start
    return rec


def verify(protocol, agent_dir):
    if importlib.metadata.version("kaggle-environments") != protocol["environment_version"]:
        raise ValueError("environment version differs from the frozen protocol")
    engine = importlib.metadata.distribution("kaggle-environments").locate_file(
        "kaggle_environments/envs/kaggriculture/kaggriculture.py")
    if digest(engine) != protocol["engine_sha256"]:
        raise ValueError("environment source differs from the frozen protocol")
    for relative, expected in protocol["opponent_files"].items():
        if digest(HERE / relative) != expected:
            raise ValueError(f"frozen opponent changed: {relative}")
    if digest(agent_dir / "docs" / "v45_base.py") != protocol["baseline_sha256"]:
        raise ValueError("archived baseline changed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent-dir", default=None)
    ap.add_argument("--seedset", default="quick", choices=["smoke", "quick", "validation", "confirmation"])
    ap.add_argument("--out", default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    agent_dir = Path(a.agent_dir).resolve() if a.agent_dir else HERE.parent
    out = Path(a.out) if a.out else agent_dir / f"metrics.{a.seedset}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    protocol = json.loads((HERE / "protocol.json").read_text())
    start = time.monotonic()
    try:
        verify(protocol, agent_dir)
        # Import once before fork; agents themselves are fresh in every game process.
        with open(os.devnull, "w") as null, contextlib.redirect_stdout(null):
            import kaggle_environments
        jobs = [(str(agent_dir), str(HERE / p), name, seed, seat)
                for name, p in protocol["opponents"].items()
                for seed in protocol["seeds"][a.seedset] for seat in (0, 1)]
        ctx = mp.get_context("fork")
        with ctx.Pool(max(1, min(a.workers, len(jobs))), maxtasksperchild=1) as pool:
            rows = pool.map_async(_play, jobs, chunksize=1).get(timeout=1100)
        bad_opponents = [r for r in rows if r["opp_status"] != "DONE"]
        if bad_opponents:
            raise ValueError("opponent/environment/load failure: " + json.dumps(bad_opponents[:2]))
        metrics = summarize(rows, protocol, a.seedset)
        metrics["elapsed_s"] = time.monotonic() - start
        metrics["candidate_files"] = {
            str(p.relative_to(agent_dir)): digest(p) for p in sorted(agent_dir.rglob("*.py"))
            if p.relative_to(agent_dir).parts[0] not in ("eval", "docs", "runs", ".venv")}
        out.write_text(json.dumps(metrics, indent=2) + "\n")
        if not a.quiet:
            print(json.dumps({k: v for k, v in metrics.items() if k not in ("per_seed", "candidate_files")}, indent=2))
        return 0
    except Exception as e:
        out.write_text(json.dumps({"score": None, "error": str(e), "seedset": a.seedset,
                                   "protocol_id": protocol["id"]}, indent=2) + "\n")
        print(str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
