"""Job queue for long-running evaluations (training runs): GPU assignment, timeouts, stall detection,
NaN detection and curve-based early termination against an incumbent. No LLM anywhere in here.

Layout (under jobs_dir(), default <checkout>/jobs or $RSI_HOME/jobs):
  queue/<id>.json   job records (status queued|running|done|failed|killed)
  logs/<id>.log     stdout+stderr of the job
  jobd.json         daemon heartbeat {pid, gpus, started}

A job writes progress to `metrics_path` as JSONL lines {"step": int, "value": float, ...} and its final result to
`result_path` (JSON with the task's score key). `rsi jobd` runs the daemon; `submit()`+`wait()` are the client API.
The orchestrator starts a daemon automatically when none is alive.
"""
from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from .home import in_checkout, REPO, home
from .util import atomic_write_json, read_json, now_iso, now_ts


def jobs_dir() -> Path:
    d = Path(os.environ.get("RSI_JOBS_DIR") or ((REPO / "jobs") if in_checkout() else (home() / "jobs")))
    (d / "queue").mkdir(parents=True, exist_ok=True)
    (d / "logs").mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class Job:
    id: str
    cmd: list[str]
    cwd: str
    owner: str = ""                 # "<experiment>/<node>"
    gpus: int = 0
    priority: int = 0               # higher first
    env: dict[str, str] = field(default_factory=dict)
    timeout_s: int = 3600
    stall_s: int = 600              # no new metrics line for this long -> kill (0 disables)
    metrics_path: str = ""          # JSONL progress stream written by the job
    result_path: str = ""           # final JSON written by the job
    incumbent_path: str = ""        # metrics JSONL of the node to beat (early termination)
    early_stop: dict[str, Any] = field(default_factory=dict)   # {warmup_frac, margin, patience_points, higher_is_better}
    status: str = "queued"
    created_at: str = field(default_factory=now_iso)
    started_at: str | None = None
    ended_at: str | None = None
    exit_code: int | None = None
    pid: int | None = None
    assigned_gpus: list[int] = field(default_factory=list)
    reason: str = ""
    duration_s: float | None = None
    last_step: int | None = None
    last_value: float | None = None

    @property
    def path(self) -> Path:
        return jobs_dir() / "queue" / f"{self.id}.json"

    def save(self) -> None:
        atomic_write_json(self.path, asdict(self))

    @staticmethod
    def load(job_id: str) -> "Job":
        d = read_json(jobs_dir() / "queue" / f"{job_id}.json")
        if d is None:
            raise FileNotFoundError(job_id)
        known = set(Job.__dataclass_fields__)
        return Job(**{k: v for k, v in d.items() if k in known})


# client ------------------------------------------------------------------------
def submit(cmd: list[str], cwd: Path, **kw: Any) -> Job:
    job = Job(id=time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6], cmd=list(cmd), cwd=str(cwd), **kw)
    job.save()
    return job


def wait(job_id: str, poll_s: float = 5.0, on_progress=None) -> Job:
    """Block until the job finishes. If the daemon dies meanwhile, a new one is started; it adopts running jobs."""
    last = None
    checks = 0
    while True:
        job = Job.load(job_id)
        if job.status in ("done", "failed", "killed"):
            return job
        checks += 1
        if checks % 6 == 0 and not daemon_alive():
            ensure_daemon()
        if on_progress and (job.last_step, job.status) != last:
            last = (job.last_step, job.status)
            try:
                on_progress(job)
            except Exception:
                pass
        time.sleep(poll_s)


def cancel(job_id: str) -> None:
    job = Job.load(job_id)
    if job.status == "queued":
        job.status, job.reason, job.ended_at = "killed", "cancelled", now_iso()
        job.save()
    elif job.status == "running" and job.pid:
        try:
            os.killpg(job.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def list_jobs(status: str | None = None) -> list[Job]:
    out = []
    for f in sorted((jobs_dir() / "queue").glob("*.json")):
        try:
            j = Job.load(f.stem)
        except Exception:
            continue
        if status is None or j.status == status:
            out.append(j)
    return out


def gpu_seconds(owner_prefix: str) -> float:
    """Sum of duration × gpus over finished jobs whose owner starts with the prefix (for GPU-hour budgets)."""
    total = 0.0
    for j in list_jobs():
        if j.owner.startswith(owner_prefix) and j.duration_s:
            total += j.duration_s * max(1, j.gpus)
    return total


# daemon --------------------------------------------------------------------------
def daemon_alive() -> bool:
    d = read_json(jobs_dir() / "jobd.json")
    if not d:
        return False
    try:
        os.kill(int(d["pid"]), 0)
    except (OSError, ValueError):
        return False
    return now_ts() - float(d.get("heartbeat", 0)) < 60


def ensure_daemon(gpus: list[int] | None = None) -> None:
    """Start `rsi jobd` in the background if no daemon is alive."""
    if daemon_alive():
        return
    gpus_arg = ",".join(str(g) for g in (gpus if gpus is not None else default_gpus()))
    cmd = [sys.executable, "-m", "pi_rsi.cli", "jobd", "--gpus", gpus_arg]
    log = open(jobs_dir() / "jobd.log", "a")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True, env=env)
    for _ in range(20):
        time.sleep(0.5)
        if daemon_alive():
            return


def default_gpus() -> list[int]:
    env = os.environ.get("RSI_GPUS")
    if env is not None:
        return [int(x) for x in env.split(",") if x.strip()]
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"], capture_output=True, text=True, timeout=10).stdout
        return [int(x) for x in out.split() if x.strip().isdigit()]
    except Exception:
        return []


class _Running:
    def __init__(self, job: Job, proc: subprocess.Popen):
        self.job, self.proc = job, proc
        self.start = time.time()
        self.last_metrics_size = 0
        self.last_activity = time.time()
        self.below_count = 0
        self.incumbent = _load_curve(Path(job.incumbent_path)) if job.incumbent_path else {}


def _load_curve(path: Path) -> dict[int, float]:
    curve: dict[int, float] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
                curve[int(d["step"])] = float(d["value"])
            except Exception:
                continue
    except FileNotFoundError:
        pass
    return curve


def _adopt_orphans(free_gpus: list[int]) -> None:
    """A restarted daemon settles jobs left in `running` by its predecessor: finished result -> done, dead pid -> failed,
    live pid -> keep waiting on it (polled by pid; it is not our child)."""
    for job in list_jobs("running"):
        alive = False
        if job.pid:
            try:
                os.kill(job.pid, 0)
                alive = True
            except OSError:
                alive = False
        if alive:
            print(f"[jobd] adopting live job {job.id} pid {job.pid}", flush=True)
            for g in job.assigned_gpus:
                if g in free_gpus:
                    free_gpus.remove(g)
            continue
        if job.result_path and Path(job.result_path).exists():
            job.status, job.exit_code, job.reason = "done", 0, "adopted: result found after daemon restart"
        else:
            job.status, job.reason = "failed", "daemon restarted while the job was running (no result)"
        job.ended_at = now_iso()
        if job.started_at and not job.duration_s:
            try:
                import datetime as _dt
                t0 = _dt.datetime.fromisoformat(job.started_at).timestamp()
                job.duration_s = round(now_ts() - t0, 1)
            except Exception:
                pass
        job.save()
        print(f"[jobd] settled orphan {job.id}: {job.status} ({job.reason})", flush=True)


def run_daemon(gpus: list[int], max_cpu_jobs: int = 2, poll_s: float = 3.0) -> None:
    d = jobs_dir()
    free_gpus = list(gpus)
    running: dict[str, _Running] = {}
    print(f"[jobd] pid {os.getpid()} gpus {gpus} dir {d}", flush=True)
    _adopt_orphans(free_gpus)
    adopted = {j.id for j in list_jobs("running")}
    while True:
        try:
            _daemon_tick(d, gpus, free_gpus, running, adopted, max_cpu_jobs)
        except Exception as e:  # keep the daemon alive no matter what
            import traceback
            print(f"[jobd] tick error: {e}\n{traceback.format_exc()[-1500:]}", flush=True)
        time.sleep(poll_s)


def _daemon_tick(d: Path, gpus: list[int], free_gpus: list[int], running: dict, adopted: set, max_cpu_jobs: int) -> None:
    if True:
        atomic_write_json(d / "jobd.json", {"pid": os.getpid(), "gpus": gpus, "heartbeat": now_ts(), "running": list(running) + sorted(adopted)})
        # adopted jobs (not our children): poll by pid / result file
        for jid in list(adopted):
            try:
                job = Job.load(jid)
            except FileNotFoundError:
                adopted.discard(jid)
                continue
            alive = False
            try:
                os.kill(int(job.pid), 0)
                alive = True
            except (OSError, TypeError, ValueError):
                pass
            if alive:
                continue
            job.status = "done" if (job.result_path and Path(job.result_path).exists()) else "failed"
            job.reason = job.reason or ("adopted job finished" if job.status == "done" else "adopted job ended without a result")
            job.ended_at = now_iso()
            job.save()
            for g in job.assigned_gpus:
                if g not in free_gpus and g in gpus:
                    free_gpus.append(g)
            adopted.discard(jid)
            print(f"[jobd] {job.status} {jid} (adopted)", flush=True)
        # reap / monitor
        for jid, r in list(running.items()):
            job = r.job
            code = r.proc.poll()
            _update_progress(job, r)
            if code is None:
                kill_reason = _should_kill(job, r)
                if kill_reason:
                    _kill(r.proc)
                    job.reason = kill_reason
                    code = r.proc.wait(timeout=60) if r.proc.poll() is None else r.proc.poll()
                    job.status = "killed"
                else:
                    job.save()
                    continue
            job.exit_code = code
            job.ended_at = now_iso()
            job.duration_s = round(time.time() - r.start, 1)
            if job.status != "killed":
                job.status = "done" if code == 0 else "failed"
                if code != 0 and not job.reason:
                    job.reason = f"exit {code}"
            job.save()
            free_gpus.extend(job.assigned_gpus)
            running.pop(jid)
            print(f"[jobd] {job.status} {jid} {job.owner} {job.reason} ({job.duration_s}s)", flush=True)
        # launch
        queued = sorted(list_jobs("queued"), key=lambda j: (-j.priority, j.created_at))
        cpu_running = sum(1 for r in running.values() if r.job.gpus == 0)
        for job in queued:
            if job.gpus > 0 and len(free_gpus) < job.gpus:
                continue
            if job.gpus == 0 and cpu_running >= max_cpu_jobs:
                continue
            assigned = [free_gpus.pop(0) for _ in range(job.gpus)]
            env = dict(os.environ)
            env.update(job.env)
            env["CUDA_VISIBLE_DEVICES"] = ",".join(str(g) for g in assigned) if assigned else ""
            log = open(d / "logs" / f"{job.id}.log", "a")
            try:
                proc = subprocess.Popen(job.cmd, cwd=job.cwd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                        env=env, start_new_session=True)
            except Exception as e:
                job.status, job.reason, job.ended_at = "failed", f"launch error: {e}", now_iso()
                job.save()
                free_gpus.extend(assigned)
                continue
            job.status, job.started_at, job.pid, job.assigned_gpus = "running", now_iso(), proc.pid, assigned
            job.save()
            running[job.id] = _Running(job, proc)
            if job.gpus == 0:
                cpu_running += 1
            print(f"[jobd] start {job.id} {job.owner} gpus={assigned}", flush=True)


def _update_progress(job: Job, r: _Running) -> None:
    if not job.metrics_path:
        return
    p = Path(job.metrics_path)
    try:
        size = p.stat().st_size
    except FileNotFoundError:
        return
    if size != r.last_metrics_size:
        r.last_metrics_size = size
        r.last_activity = time.time()
        curve = _load_curve(p)
        if curve:
            step = max(curve)
            job.last_step, job.last_value = step, curve[step]


def _should_kill(job: Job, r: _Running) -> str:
    now = time.time()
    if job.timeout_s and now - r.start > job.timeout_s:
        return f"timeout after {job.timeout_s}s"
    if job.stall_s and job.metrics_path and now - r.last_activity > job.stall_s:
        return f"stalled: no progress for {job.stall_s}s"
    if job.last_value is not None and (math.isnan(job.last_value) or math.isinf(job.last_value)):
        return "non-finite metric"
    es = job.early_stop or {}
    if r.incumbent and job.last_step is not None and es:
        hib = bool(es.get("higher_is_better", False))
        warm = int(es.get("warmup_frac", 0.3) * max(r.incumbent))
        margin = float(es.get("margin", 0.05))
        need = int(es.get("patience_points", 3))
        step = job.last_step
        if step >= warm and step in r.incumbent:
            inc, cur = r.incumbent[step], job.last_value
            worse = (cur < inc * (1 - margin)) if hib else (cur > inc * (1 + margin))
            r.below_count = r.below_count + 1 if worse else 0
            if r.below_count >= need:
                return f"early stop: {need} checkpoints worse than incumbent by >{margin:.0%} (step {step}: {cur:.4g} vs {inc:.4g})"
    return ""


def _kill(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(20):
        if proc.poll() is not None:
            return
        time.sleep(0.5)
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
