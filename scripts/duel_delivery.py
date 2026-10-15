#!/usr/bin/env python3
"""Lock one local-selection winner, compare on new seed blocks, and package without submitting."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import copy
from fractions import Fraction
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pi_rsi.config import load_experiment, load_task_cfg
from pi_rsi.evaluator import run_eval, _python
from pi_rsi.tree import Tree
from pi_rsi.util import atomic_write_json, atomic_write_text, now_iso, read_json


def files_for_delivery(candidate):
    files = [candidate / "agent.py"]
    for name in ("src", "docs"):
        files += [p for p in (candidate / name).rglob("*") if p.is_file()
                  and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    for name in ("config.toml", "config.json", "policy.json"):
        if (candidate / name).is_file():
            files.append(candidate / name)
    for p in files:
        if not p.resolve().is_relative_to(candidate.resolve()):
            raise ValueError(f"external file in deliverable: {p}")
    return sorted(set(files))


def identity(candidate):
    return {str(p.relative_to(candidate)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files_for_delivery(candidate)}


def paired_compare(baseline, candidate):
    if baseline["protocol_id"] != candidate["protocol_id"]:
        raise ValueError("incompatible protocols")
    base = {r["id"]: r["value"] for r in baseline["per_item"]}
    cand = {r["id"]: r["value"] for r in candidate["per_item"]}
    if base.keys() != cand.keys() or not base:
        raise ValueError("confirmation seed blocks do not match")
    diffs = [cand[k] - base[k] for k in sorted(base)]
    # Duel outcomes lie on a small rational lattice. Count attainable sums instead
    # of enumerating 2**n assignments, retaining the exact randomization test.
    fractions = [Fraction(d).limit_denominator(1000000) for d in diffs]
    if any(abs(float(q) - d) > 1e-12 for q, d in zip(fractions, diffs)):
        raise ValueError("seed-block scores do not fit the outcome lattice")
    denominator = math.lcm(*(q.denominator for q in fractions))
    weights = [q.numerator * (denominator // q.denominator) for q in fractions]
    distribution = Counter({0: 1})
    for weight in weights:
        updated = Counter()
        for total, count in distribution.items():
            updated[total + weight] += count
            updated[total - weight] += count
        distribution = updated
        if len(distribution) > 200000:
            raise ValueError("outcome lattice too large for exact comparison")
    observed = abs(sum(weights))
    p = sum(count for total, count in distribution.items() if abs(total) >= observed) / (2 ** len(weights))
    per_opponent = {name: candidate["per_opponent"][name]["score"] - v["score"]
                    for name, v in baseline["per_opponent"].items()}
    delta = statistics.mean(diffs)
    corroborated = delta > 0 and p <= 0.05 and min(per_opponent.values()) >= 0 and not candidate["errors"]
    return {"delta": delta, "seed_block_deltas": diffs, "exact_two_sided_sign_flip_p": p,
            "per_opponent_delta": per_opponent, "n_blocks": len(diffs),
            "decision": "locally_corroborated" if corroborated else ("worse" if delta < 0 else "inconclusive"),
            "scope": "one locked candidate on new seeds; same archived pool, no live-ladder promotion",
            "test_assumption": "paired candidate/baseline label exchangeability at the independent seed-block level"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("experiment", type=Path)
    ap.add_argument("--confirmation-task", type=Path,
                    help="private task pack, loaded only after search has finished")
    a = ap.parse_args()
    cfg = load_experiment(a.experiment)
    tree = Tree.load(cfg.tree_path)
    if tree.by_status("planned", "running", "evaluating"):
        raise SystemExit("wait for all research nodes before locking a candidate")
    winner = tree.best()
    if winner is None:
        raise SystemExit("no scored candidate")
    candidate = cfg.repo_dir if winner.id == "root" else cfg.worktrees_dir / winner.id
    confirmation_cfg = copy.deepcopy(cfg)
    if a.confirmation_task:
        confirmation_cfg.task = load_task_cfg(a.confirmation_task)
        search_protocol = read_json(cfg.task_dir / "eval/protocol.json")
        confirmation_protocol = read_json(confirmation_cfg.task_dir / "eval/protocol.json")
        for key in ("environment_version", "engine_sha256", "baseline_sha256", "opponents", "opponent_files"):
            if search_protocol[key] != confirmation_protocol[key]:
                raise SystemExit(f"confirmation changes frozen {key}")
        seen = {seed for panel in search_protocol["seeds"].values() for seed in panel}
        held_out = confirmation_protocol["seeds"].get("confirmation", [])
        if not held_out or len(set(held_out)) != len(held_out) or seen.intersection(held_out):
            raise SystemExit("confirmation seeds must be nonempty, unique and disjoint from search")
    dest = cfg.dir / "delivery"
    dest.mkdir(exist_ok=True)
    lock = {"node": winner.id, "commit": winner.commit, "selection_score": winner.score,
            "files": identity(candidate), "baseline_files": identity(cfg.repo_dir),
            "protocol_sha256": hashlib.sha256((cfg.task_dir / "eval/protocol.json").read_bytes()).hexdigest(),
            "confirmation_protocol_sha256": hashlib.sha256((confirmation_cfg.task_dir / "eval/protocol.json").read_bytes()).hexdigest(),
            "locked_at": now_iso(), "confirmation_level": "confirmation"}
    old = read_json(dest / "LOCK.json")
    if old:
        if any(old[k] != lock[k] for k in ("node", "commit", "files", "baseline_files", "protocol_sha256")) or (
                old.get("confirmation_protocol_sha256", old["protocol_sha256"]) != lock["confirmation_protocol_sha256"]):
            raise SystemExit("a different candidate already consumed this confirmation; use a new protocol")
        lock = old
    else:
        atomic_write_json(dest / "LOCK.json", lock)
    # This is separate from node evidence; confirmation must never be ingested back into search.
    base_metrics = read_json(dest / "baseline/metrics.confirmation.json")
    candidate_metrics = read_json(dest / "candidate/metrics.confirmation.json")
    with ThreadPoolExecutor(max_workers=2) as pool:
        base_future = pool.submit(run_eval, confirmation_cfg, cfg.repo_dir, "confirmation", dest / "baseline") if base_metrics is None else None
        cand_future = pool.submit(run_eval, confirmation_cfg, candidate, "confirmation", dest / "candidate") if winner.id != "root" and candidate_metrics is None else None
        if base_future:
            base_metrics = base_future.result()
        if cand_future:
            candidate_metrics = cand_future.result()
    if winner.id == "root":
        candidate_metrics = base_metrics
    expected_protocol = read_json(confirmation_cfg.task_dir / "eval/protocol.json")
    expected_blocks = {f"{expected_protocol['id']}:{s}" for s in expected_protocol["seeds"]["confirmation"]}
    for metrics in (base_metrics, candidate_metrics):
        if metrics.get("protocol_id") != expected_protocol["id"] or {r["id"] for r in metrics["per_item"]} != expected_blocks:
            raise SystemExit("confirmation metrics do not match the locked protocol")
    if identity(candidate) != lock["files"] or identity(cfg.repo_dir) != lock["baseline_files"]:
        raise SystemExit("candidate or baseline changed after lock; do not interpret or package")
    comparison = paired_compare(base_metrics, candidate_metrics)
    atomic_write_json(dest / "comparison.json", comparison)
    stage = dest / "agent"
    stage.mkdir(exist_ok=True)
    for p in files_for_delivery(candidate):
        relative = Path("main.py") if p == candidate / "agent.py" else p.relative_to(candidate)
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
    archive = dest / "submission.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for p in sorted(stage.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                data = p.read_bytes()
                item = tarfile.TarInfo(str(p.relative_to(stage)))
                item.size, item.mode, item.mtime = len(data), 0o644, 0
                tar.addfile(item, io.BytesIO(data))
    # Exercise the official environment's file loader with exactly the staged entry point.
    code = (
        "import json,sys\nfrom kaggle_environments import make\n"
        "e=make('kaggriculture',configuration={'seed':4409},debug=False)\n"
        "e.run([sys.argv[1],sys.argv[1]])\n"
        "r={'statuses':[x['status'] for x in e.steps[-1]],'rewards':[x['reward'] for x in e.steps[-1]]}\n"
        "open(sys.argv[2],'w').write(json.dumps(r))\n"
        "assert r['statuses']==['DONE','DONE'],r\n")
    with (dest / "selfplay.log").open("w") as log:
        subprocess.run([_python(cfg), "-c", code, str(stage / "main.py"), str(dest / "selfplay.json")],
                       cwd=stage, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    atomic_write_json(dest / "manifest.json", {"node": winner.id, "commit": winner.commit,
        "archive": str(archive), "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "protocol_id": candidate_metrics["protocol_id"], "selection_score": winner.score,
        "confirmation_score": candidate_metrics["score"], "comparison": comparison,
        "selfplay": read_json(dest / "selfplay.json"), "submitted": False})
    lines = ["# Kaggriculture outcome trial", "", f"Locked candidate: {winner.id} ({winner.commit}).",
             f"Selection score: {winner.score:.4f}.", "",
             "| Evaluation | Baseline | Candidate |", "|---|---:|---:|",
             f"| Confirmation win + half draw | {base_metrics['score']:.4f} | {candidate_metrics['score']:.4f} |",
             f"| Wins / draws / losses | {base_metrics['wins']}/{base_metrics['draws']}/{base_metrics['losses']} | "
             f"{candidate_metrics['wins']}/{candidate_metrics['draws']}/{candidate_metrics['losses']} |",
             "", f"Decision: {comparison['decision']}; paired seed-block delta {comparison['delta']:+.4f}; "
             f"two-sided exact sign-flip p={comparison['exact_two_sided_sign_flip_p']:.4g}.",
             "", "This is evidence on new seeds against the same frozen, correlated archived pool. "
             "It does not establish live-ladder strength. No external submission was made.",
             "", "[Submission archive](submission.tar.gz) · [Manifest](manifest.json) · [Self-play](selfplay.json)",
             "", "## Per-opponent confirmation",
             "| Opponent | Baseline | Candidate |", "|---|---:|---:|"]
    for name, row in base_metrics["per_opponent"].items():
        lines.append(f"| {name} | {row['score']:.4f} | {candidate_metrics['per_opponent'][name]['score']:.4f} |")
    atomic_write_text(dest / "RESULTS.md", "\n".join(lines) + "\n")
    print(json.dumps({"node": winner.id, "selection": winner.score,
                      "confirmation": candidate_metrics["score"], **comparison, "archive": str(archive)}, indent=2))


if __name__ == "__main__":
    main()
