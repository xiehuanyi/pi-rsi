"""Job queue for long-running evaluations (training runs): GPU assignment, timeouts, stall detection,
NaN detection and curve-based early termination against an incumbent. No LLM anywhere in here.

Layout (under jobs_dir(), default <checkout>/jobs or $RSI_HOME/jobs):
  queue/<id>.json   job records (status queued|running|done|failed|killed)
  logs/<id>.log     stdout+stderr of the job
  jobd.json         daemon heartbeat {pid, gpus, started}
  jobd.lock         held by the one live daemon (flock; released by the kernel when it dies)
  queue.lock        serializes job state transitions (claim/launch, cancel)

A job writes progress to `metrics_path` as JSONL lines {"step": int, "value": float, ...} and its final result to
`result_path` (JSON with the task's score key). `rsi jobd` runs the daemon; `submit()`+`wait()` are the client API.
The orchestrator starts a daemon automatically when none is alive.
"""
from __future__ import annotations

import fcntl
import json
import math
import os
import signal
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
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
    proc_identity: str = ""         # boot id + process start time: guards against PID reuse after restarts

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
    with _queue_lock():  # cannot interleave with the daemon claiming this job
        job = Job.load(job_id)
        if job.status == "queued":
            job.status, job.reason, job.ended_at = "killed", "cancelled", now_iso()
            job.save()
            return
    if job.status == "running" and _alive(job):  # never signal a recycled PID
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


# locks and process identity ----------------------------------------------------------
def _try_flock(path: Path) -> int | None:
    """Exclusive non-blocking flock; returns the descriptor while held, None if someone else holds it."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o666)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BlockingIOError:
        os.close(fd)
        return None


def _release(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


@contextmanager
def _flock(path: Path):
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o666)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        _release(fd)


def _queue_lock():
    return _flock(jobs_dir() / "queue.lock")


def _stat_fields(pid) -> list[str]:
    """/proc/<pid>/stat fields after the command name (index 0 = state, 3 = session id, 19 = start time)."""
    stat = Path(f"/proc/{int(pid)}/stat").read_text()
    return stat[stat.rfind(")") + 2:].split()


def _proc_identity(pid) -> str:
    """Boot id + start time of a live, non-zombie process, "" when gone. A recycled PID differs."""
    try:
        fields = _stat_fields(pid)
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except (OSError, ValueError, TypeError):
        return ""
    return "" if not fields or fields[0] in ("Z", "X") else f"{boot}:{fields[19]}"


def _alive(job: Job) -> bool:
    """True while the job's own process runs, not merely some process that inherited its PID."""
    if not job.pid:
        return False
    try:
        os.kill(int(job.pid), 0)
    except PermissionError:
        pass
    except (OSError, ValueError, TypeError):
        return False
    if job.proc_identity:
        return _proc_identity(job.pid) == job.proc_identity
    # Records from before proc_identity: every job leads its own session in its own cwd.
    try:
        fields = _stat_fields(job.pid)
        return (fields[0] not in ("Z", "X") and int(fields[3]) == int(job.pid)
                and Path(os.readlink(f"/proc/{int(job.pid)}/cwd")).resolve() == Path(job.cwd).resolve())
    except (OSError, ValueError, IndexError):
        return not Path("/proc").is_dir()


def _iso_ts(value: str | None) -> float | None:
    try:
        import datetime as _dt
        return _dt.datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return None


# daemon --------------------------------------------------------------------------
def _legacy_daemon_alive(d: Path) -> bool:
    """A daemon started before the single-instance lock existed: fresh heartbeat from a live jobd."""
    record = read_json(d / "jobd.json")
    try:
        pid = int(record["pid"])
        if pid == os.getpid() or now_ts() - float(record.get("heartbeat", 0)) >= 60:
            return False
        os.kill(pid, 0)
        return b"jobd" in Path(f"/proc/{pid}/cmdline").read_bytes()
    except (OSError, ValueError, KeyError, TypeError):
        return False


def daemon_alive() -> bool:
    d = jobs_dir()
    fd = _try_flock(d / "jobd.lock")
    if fd is None:
        return True  # the single-instance lock is held by a live daemon
    _release(fd)
    return _legacy_daemon_alive(d)


def ensure_daemon(gpus: list[int] | None = None) -> None:
    """Start `rsi jobd` in the background if no daemon is alive. Concurrent callers spawn at most one
    (spawn lock), and a surplus daemon would exit on the single-instance lock anyway."""
    if daemon_alive():
        return
    d = jobs_dir()
    with _flock(d / "jobd.spawn.lock"):
        if daemon_alive():
            return  # another caller started it while we waited
        gpus_arg = ",".join(str(g) for g in (gpus if gpus is not None else default_gpus()))
        cmd = [sys.executable, "-m", "pi_rsi.cli", "jobd", "--gpus", gpus_arg]
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        with open(d / "jobd.log", "a") as log:
            subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             start_new_session=True, env=env)
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
    """A supervised job: our child (`proc`) or a live process adopted from a previous daemon (`proc=None`).
    Both are held to the same limits (timeout, stall, non-finite metric, early stop)."""

    def __init__(self, job: Job, proc: subprocess.Popen | None = None):
        self.job, self.proc = job, proc
        now = time.time()
        self.start = now if proc is not None else (_iso_ts(job.started_at) or now)
        self.last_metrics_size = 0
        self.last_activity = now if proc is not None else self.start
        self.curve: dict[int, float] = {}
        self.incumbent = _load_curve(Path(job.incumbent_path)) if job.incumbent_path else {}
        if proc is None and job.metrics_path:
            # Continue supervision from the job's real progress, not from the adoption moment.
            try:
                stat = Path(job.metrics_path).stat()
                self.last_activity = max(self.start, stat.st_mtime)
                self.last_metrics_size = stat.st_size
                self.curve = _load_curve(Path(job.metrics_path))
            except FileNotFoundError:
                pass

    def poll(self) -> int | None:
        """Exit code, None while running. An adopted process is not our child: -1 once it is gone."""
        if self.proc is not None:
            return self.proc.poll()
        return None if _alive(self.job) else -1

    def kill(self) -> None:
        if self.proc is not None:
            _kill(self.proc)
            return
        for sig, wait_s in ((signal.SIGTERM, 10), (signal.SIGKILL, 5)):
            if not _alive(self.job):  # identity-checked: never signal a recycled PID
                return
            try:
                os.killpg(int(self.job.pid), sig)  # jobs start their own session: pgid == pid
            except ProcessLookupError:
                return
            deadline = time.time() + wait_s
            while time.time() < deadline and _alive(self.job):
                time.sleep(0.5)


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


def _adopt_orphans(gpus: list[int], free_gpus: list[int]) -> dict[str, _Running]:
    """A restarted daemon settles jobs left `running` by its predecessor: a live original process is
    adopted and supervised like a child; otherwise the result file decides done/failed."""
    adopted: dict[str, _Running] = {}
    for job in list_jobs("running"):
        if _alive(job):
            print(f"[jobd] adopting live job {job.id} pid {job.pid}", flush=True)
            for g in job.assigned_gpus:
                if g in free_gpus:
                    free_gpus.remove(g)
            adopted[job.id] = _Running(job)
            continue
        if job.result_path and Path(job.result_path).exists():
            job.status, job.exit_code, job.reason = "done", 0, "adopted: result found after daemon restart"
        else:
            job.status, job.reason = "failed", "daemon restarted while the job was running (no result)"
        job.ended_at = now_iso()
        if job.started_at and not job.duration_s and _iso_ts(job.started_at):
            job.duration_s = round(now_ts() - _iso_ts(job.started_at), 1)
        job.save()
        print(f"[jobd] settled orphan {job.id}: {job.status} ({job.reason})", flush=True)
    return adopted


def run_daemon(gpus: list[int], max_cpu_jobs: int = 2, poll_s: float = 3.0) -> None:
    d = jobs_dir()
    lock = None
    for _ in range(10):  # a liveness probe holds the lock only for an instant
        lock = _try_flock(d / "jobd.lock")
        if lock is not None:
            break
        time.sleep(0.3)
    if lock is None:
        print(f"[jobd] pid {os.getpid()}: another daemon holds {d / 'jobd.lock'}; exiting", flush=True)
        return
    if _legacy_daemon_alive(d):
        print(f"[jobd] pid {os.getpid()}: a daemon without the single-instance lock still serves {d}; exiting", flush=True)
        _release(lock)
        return
    free_gpus = list(gpus)
    print(f"[jobd] pid {os.getpid()} gpus {gpus} dir {d}", flush=True)
    running = _adopt_orphans(gpus, free_gpus)
    # An idle daemon exits (a finished campaign's jobd used to linger for days holding its GPU list);
    # submit and wait() start a new one when work arrives.
    idle_exit_s = float(os.environ.get("RSI_JOBD_IDLE_EXIT_S", 6 * 3600))
    last_busy = now_ts()
    while True:
        try:
            if _daemon_tick(d, gpus, free_gpus, running, max_cpu_jobs):
                last_busy = now_ts()
        except Exception as e:  # keep the daemon alive no matter what
            import traceback
            print(f"[jobd] tick error: {e}\n{traceback.format_exc()[-1500:]}", flush=True)
            last_busy = now_ts()
        if idle_exit_s > 0 and now_ts() - last_busy > idle_exit_s and not running:
            print(f"[jobd] pid {os.getpid()}: idle for {idle_exit_s:.0f}s; exiting", flush=True)
            _release(lock)
            return
        time.sleep(poll_s)


def _daemon_tick(d: Path, gpus: list[int], free_gpus: list[int], running: dict, max_cpu_jobs: int) -> bool:
    """One reap/launch pass; True while any job is running or queued."""
    atomic_write_json(d / "jobd.json", {"pid": os.getpid(), "gpus": gpus, "heartbeat": now_ts(), "running": sorted(running)})
    # reap / monitor (children and adopted processes alike)
    for jid, r in list(running.items()):
        job = r.job
        code = r.poll()
        _update_progress(job, r)
        if code is None:
            kill_reason = _should_kill(job, r)
            if not kill_reason:
                job.save()
                continue
            r.kill()
            job.status, job.reason = "killed", kill_reason
            code = r.proc.wait(timeout=60) if r.proc is not None and r.proc.poll() is None else r.poll()
        _finish(job, r, code, gpus, free_gpus)
        running.pop(jid)
        print(f"[jobd] {job.status} {jid} {job.owner} {job.reason} ({job.duration_s}s)"
              f"{' (adopted)' if r.proc is None else ''}", flush=True)
    # launch
    queued = sorted(list_jobs("queued"), key=lambda j: (-j.priority, j.created_at))
    cpu_running = sum(1 for r in running.values() if r.job.gpus == 0)
    for job in queued:
        if job.gpus > 0 and len(free_gpus) < job.gpus:
            continue
        if job.gpus == 0 and cpu_running >= max_cpu_jobs:
            continue
        r = _launch(d, job.id, free_gpus)
        if r is None:
            continue
        running[job.id] = r
        if r.job.gpus == 0:
            cpu_running += 1
    return bool(running or queued)


def _launch(d: Path, job_id: str, free_gpus: list[int]) -> _Running | None:
    """Claim a queued job and start it in one transition under the queue lock, so a concurrent
    cancel() or a second daemon can never start the same job twice."""
    with _queue_lock():
        try:
            job = Job.load(job_id)
        except FileNotFoundError:
            return None
        if job.status != "queued" or len(free_gpus) < job.gpus:
            return None
        assigned = [free_gpus.pop(0) for _ in range(job.gpus)]
        env = dict(os.environ)
        env.update(job.env)
        env["CUDA_VISIBLE_DEVICES"] = ",".join(str(g) for g in assigned) if assigned else ""
        env["RSI_JOB_ID"] = job.id
        try:
            with open(d / "logs" / f"{job.id}.log", "a") as log:
                proc = subprocess.Popen(job.cmd, cwd=job.cwd, stdout=log, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, env=env, start_new_session=True)
        except Exception as e:
            job.status, job.reason, job.ended_at = "failed", f"launch error: {e}", now_iso()
            job.save()
            free_gpus.extend(assigned)
            return None
        job.status, job.started_at, job.pid, job.assigned_gpus = "running", now_iso(), proc.pid, assigned
        job.proc_identity = _proc_identity(proc.pid)
        job.save()
    print(f"[jobd] start {job.id} {job.owner} gpus={assigned}", flush=True)
    return _Running(job, proc)


def _finish(job: Job, r: _Running, code: int | None, gpus: list[int], free_gpus: list[int]) -> None:
    job.ended_at = now_iso()
    job.duration_s = round(time.time() - r.start, 1)
    if r.proc is not None:
        job.exit_code = code
        if job.status != "killed":
            job.status = "done" if code == 0 else "failed"
            if code != 0 and not job.reason:
                job.reason = f"exit {code}"
    elif job.status != "killed":
        # Not our child: its exit status is unknowable, so the result file decides.
        done = bool(job.result_path) and Path(job.result_path).exists()
        job.status, job.exit_code = ("done", 0) if done else ("failed", None)
        job.reason = job.reason or ("adopted job finished" if done else "adopted job ended without a result")
    job.save()
    for g in job.assigned_gpus:
        if g in gpus and g not in free_gpus:
            free_gpus.append(g)


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
        r.curve = _load_curve(p)
    if r.curve:
        step = max(r.curve)
        job.last_step, job.last_value = step, r.curve[step]


def _should_kill(job: Job, r: _Running) -> str:
    now = time.time()
    if job.timeout_s and now - r.start > job.timeout_s:
        return f"timeout after {job.timeout_s}s"
    if job.stall_s and job.metrics_path and now - r.last_activity > job.stall_s:
        return f"stalled: no progress for {job.stall_s}s"
    if job.last_value is not None and (math.isnan(job.last_value) or math.isinf(job.last_value)):
        return "non-finite metric"
    return _early_stop_reason(job, r)


def _early_stop_reason(job: Job, r: _Running) -> str:
    """`patience_points` consecutive checkpoints (distinct steps) after warmup that trail the incumbent by
    more than `margin`. Computed from the curve itself, so polling one checkpoint repeatedly never counts
    it twice, and an adopted job is judged exactly like a child."""
    es = job.early_stop or {}
    if not (es and r.incumbent and r.curve):
        return ""
    hib = bool(es.get("higher_is_better", False))
    warm = int(es.get("warmup_frac", 0.3) * max(r.incumbent))
    margin = float(es.get("margin", 0.05))
    need = int(es.get("patience_points", 3))
    streak, last = 0, None
    for step in sorted(s for s in r.curve if s >= warm and s in r.incumbent):
        inc, cur = r.incumbent[step], r.curve[step]
        worse = (cur < inc * (1 - margin)) if hib else (cur > inc * (1 + margin))
        streak = streak + 1 if worse else 0
        last = (step, cur, inc)
    if need > 0 and streak >= need:
        step, cur, inc = last
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
