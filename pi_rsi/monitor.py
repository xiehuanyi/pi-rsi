"""Durable task monitor. Polling, process recovery and waiting never invoke a model."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import jobs
from .util import atomic_write_json, now_iso, read_json


class TaskMonitor:
    def __init__(self, path: Path):
        self.path = path

    def save(self, **changes):
        record = read_json(self.path, {}) or {}
        record.update(changes, checked_at=now_iso())
        atomic_write_json(self.path, record)
        return record

    @staticmethod
    def fingerprint(identity):
        return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()

    def last_attempt(self, identity, aliases=None):
        """(attempt ordinal, job) recorded for this evaluation, or (0, None) for another/no evaluation.

        `aliases` maps legacy fingerprints (records that hashed each attempt's own command) to their
        attempt, so an evaluation that is in flight across an upgrade is still recognized."""
        record = read_json(self.path, {}) or {}
        recorded = record.get("identity")
        if recorded == self.fingerprint(identity):
            attempt = int(record.get("attempt", 0))
        elif recorded in (aliases or {}):
            attempt = aliases[recorded]
        else:
            return 0, None
        try:
            return attempt, jobs.Job.load(record["job"]) if record.get("job") else None
        except FileNotFoundError:
            return attempt, None

    def submit(self, cmd, cwd, *, identity, attempt=0, aliases=None, **options):
        fingerprint = self.fingerprint(identity)
        aliases = aliases or {}
        record = read_json(self.path, {}) or {}
        same = record.get("identity") == fingerprint or record.get("identity") in aliases
        if same and record.get("job"):
            try:
                job = jobs.Job.load(record["job"])
            except FileNotFoundError:
                job = None
            if job is not None and job.status in ("queued", "running", "done"):
                result = Path(job.result_path)
                if record.get("result_sha256") and (not result.exists() or
                        hashlib.sha256(result.read_bytes()).hexdigest() != record["result_sha256"]):
                    raise RuntimeError("completed task result changed after monitor validation")
                if record.get("identity") != fingerprint:  # normalize a legacy per-attempt record
                    self.save(identity=fingerprint, attempt=aliases[record["identity"]])
                return job  # whatever attempt it is: never duplicate a live or finished evaluation
        if record.get("job") and not same:
            try:
                old = jobs.Job.load(record["job"])
                if old.status in ("queued", "running"):
                    raise RuntimeError("cannot replace a still-active monitored task")
            except FileNotFoundError:
                pass
        # Keep attempt history; a bounded caller decides whether a terminal failure is retried.
        history = record.get("attempts", [])
        if record.get("job"):
            history = history + [{"job": record["job"], "state": record.get("state"),
                                  "identity": record.get("identity"), "attempt": record.get("attempt")}]
        jobs.ensure_daemon()
        result = Path(options["result_path"]) if options.get("result_path") else None
        if result and result.exists():
            # A retry must not accept a stale success file from an earlier attempt.
            archive = result.with_name(result.name + ".previous." + record.get("job", "unmonitored"))
            if archive.exists():
                archive = archive.with_name(archive.name + "." + hashlib.sha256(result.read_bytes()).hexdigest()[:12])
            result.replace(archive)
        job = jobs.submit(cmd, cwd, **options)
        atomic_write_json(self.path, {"identity": fingerprint, "job": job.id, "attempt": attempt, "state": "queued",
            "created_at": now_iso(), "attempts": history, "wake_count": 0, "wake_ready": False})
        return job

    def attempt(self, default=0):
        return int((read_json(self.path, {}) or {}).get("attempt", default))

    def wait(self, job_id):
        # Reuse queued/running/completed jobs after controller restarts.
        jobs.ensure_daemon()
        job = jobs.wait(job_id, on_progress=lambda j: self.save(
            state=j.status, pid=j.pid, last_step=j.last_step, last_value=j.last_value))
        self.save(state=job.status, exit_code=job.exit_code, reason=job.reason,
                  finished_at=job.ended_at, wake_ready=False)
        return job

    def validated(self, result_path):
        record = read_json(self.path, {}) or {}
        job = jobs.Job.load(record["job"])
        if job.status != "done":
            raise RuntimeError("a non-completed task cannot wake the research agent")
        self.save(state="validated", wake_ready=True,
                  result_sha256=hashlib.sha256(Path(result_path).read_bytes()).hexdigest())

    def begin_analysis(self):
        record = read_json(self.path, {}) or {}
        if not record.get("wake_ready") or record.get("state") not in ("validated", "analyzing", "consumed"):
            raise RuntimeError("task must finish and pass result validation before waking a model")
        self.save(state="analyzing", wake_count=record.get("wake_count", 0) + 1,
                  model_woken_at=now_iso())

    def consumed(self):
        self.save(state="consumed", analysis_completed_at=now_iso())


def evaluation_identity(cfg, worktree, cmd):
    from .gitops import head
    import dataclasses
    files = {str(p.relative_to(cfg.task_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted((cfg.task_dir / cfg.task.eval_dir).rglob("*"))
             if p.is_file() and p.suffix in (".py", ".json", ".toml")}
    task = {k: v for k, v in dataclasses.asdict(cfg.task).items() if k != "objective"}  # prompts only
    return {"code": head(worktree), "cmd": cmd, "task": task,
            "evaluator": files, "data_version": cfg.memory.protocol_id}
