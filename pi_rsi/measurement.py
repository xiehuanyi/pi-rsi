"""Read a completed measurement without invoking an evaluator or training worker."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import gitops
from .evaluator import score_of
from .util import read_json, now_iso

# Task fields that define what an official score means. Operational limits (timeouts, stall and
# early-stop rules, resumability, reporting) decide whether a run finishes, not the value it reports.
PROTOCOL_FIELDS = ("eval_dir", "python", "eval_command", "official_seedset", "higher_is_better", "score_key",
                   "job_enabled", "job_command", "job_gpus", "link_dirs")
EVALUATOR_SUFFIXES = (".py", ".json", ".toml", ".yaml", ".yml", ".cfg", ".ini", ".sh")
_FILE_HASHES: dict[tuple, str] = {}


class ProtocolMismatch(ValueError):
    """A completed measurement belongs to another evaluation protocol: kept on record, not comparable."""


def _file_sha256(path: Path) -> str:
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    if key not in _FILE_HASHES:
        _FILE_HASHES[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    return _FILE_HASHES[key]


def evaluation_protocol(cfg) -> str:
    """Identity of the official evaluation: frozen evaluator files, scoring configuration and
    the declared data/split version (`memory.protocol_id`). Scores are comparable only within one."""
    task = cfg.task
    root = cfg.task_dir / task.eval_dir
    files = {str(p.relative_to(cfg.task_dir)): _file_sha256(p) for p in sorted(root.rglob("*"))
             if p.is_file() and p.suffix in EVALUATOR_SUFFIXES and "__pycache__" not in p.parts}
    fields = {key: getattr(task, key) for key in PROTOCOL_FIELDS}
    fields["official_budget"] = task.job_budgets.get(task.official_seedset) if task.job_enabled else None
    payload = {"task": fields, "evaluator": files, "data_version": cfg.memory.protocol_id}
    return "ep-" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:20]


def metrics_path(cfg, node):
    reference = node.measurement or node.worker.get("evaluation_validated", {})
    if reference.get("metrics_path"):
        return Path(reference["metrics_path"])
    return cfg.nodes_dir / node.id / "eval" / f"metrics.{cfg.task.official_seedset}.json"


def measurement_record(cfg, node, commit, score, *, path=None, protocol=None):
    path = Path(path) if path else metrics_path(cfg, node)
    return {"commit": commit, "score": score, "level": cfg.task.official_seedset,
            "metrics_path": str(path), "validated_at": now_iso(),
            "metrics_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "protocol": protocol or evaluation_protocol(cfg)}


def validated_measurement(orch, node):
    cfg = orch.cfg
    wt = cfg.repo_dir if node.id == "root" else cfg.worktrees_dir / node.id
    identity = node.measurement or node.worker.get("evaluation_validated", {})
    if identity.get("state") == "invalid":
        raise ValueError(f"{node.id}: measurement is quarantined")
    if identity.get("state") == "stale":
        raise ProtocolMismatch(f"{node.id}: {identity.get('stale_reason') or 'measured under another evaluation protocol'}")
    # Records written before protocols were bound are adopted once by Orchestrator.check_protocol.
    if identity.get("protocol") and identity["protocol"] != evaluation_protocol(cfg):
        raise ProtocolMismatch(f"{node.id}: measured under evaluation protocol {identity['protocol']}; "
                               f"the current protocol is {evaluation_protocol(cfg)}")
    if not identity or identity.get("commit") != node.commit or gitops.head(wt) != node.commit:
        raise ValueError(f"{node.id}: evaluated code identity is missing or changed")
    if gitops.git(["status", "--porcelain"], cwd=wt):
        raise ValueError(f"{node.id}: evaluated worktree is no longer clean")
    if identity.get("level", cfg.task.official_seedset) != cfg.task.official_seedset:
        raise ValueError(f"{node.id}: official evaluation level changed")
    path = Path(identity.get("metrics_path", metrics_path(cfg, node)))
    if identity.get("metrics_sha256") and hashlib.sha256(path.read_bytes()).hexdigest() != identity["metrics_sha256"]:
        raise ValueError(f"{node.id}: official metrics file changed since validation")
    metrics = read_json(path)
    score = score_of(cfg, metrics or {})
    if score is None or score != identity.get("score") or score != node.score:
        raise ValueError(f"{node.id}: official measurement differs from the validated record")
    run = Path(metrics.get("_eval", {}).get("run_dir", ""))
    for filename, key in (("model.pt", "model_sha256"), ("predictions.npy", "predictions_sha256")):
        if metrics.get(key):
            artifact = run / filename
            if not artifact.is_file() or hashlib.sha256(artifact.read_bytes()).hexdigest() != metrics[key]:
                raise ValueError(f"{node.id}: {filename} changed since evaluation")
    return metrics


def measurement_identity(node, metrics):
    payload = {"commit": node.commit, "metrics": {k: v for k, v in metrics.items() if k != "_eval"}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
