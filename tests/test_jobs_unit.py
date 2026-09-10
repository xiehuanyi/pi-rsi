#!/usr/bin/env python3
"""Unit checks for the job daemon's kill rules (no processes involved)."""
import json, os, sys, tempfile, time, types
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["RSI_JOBS_DIR"] = tempfile.mkdtemp()
from pi_rsi import jobs

tmp = Path(tempfile.mkdtemp())
inc = tmp / "incumbent.jsonl"
inc.write_text("".join(json.dumps({"step": s, "value": 1.0 / (s + 1)}) + "\n" for s in range(1, 21)))
metrics = tmp / "metrics.jsonl"


def running(job):
    r = jobs._Running(job, types.SimpleNamespace(pid=0, poll=lambda: None))
    return r


def make(**kw):
    return jobs.Job(id="t", cmd=["true"], cwd=str(tmp), metrics_path=str(metrics), incumbent_path=str(inc), **kw)


# 1. early stop: worse than incumbent by >10% for 3 checkpoints after warmup (step >= 6)
job = make(early_stop={"warmup_frac": 0.3, "margin": 0.10, "patience_points": 3, "higher_is_better": False})
r = running(job)
reasons = []
for s in range(1, 21):
    metrics.write_text("".join(json.dumps({"step": k, "value": 2.0 / (k + 1)}) + "\n" for k in range(1, s + 1)))
    r.last_metrics_size = 0
    jobs._update_progress(job, r)
    reasons.append(jobs._should_kill(job, r))
first = next(i + 1 for i, x in enumerate(reasons) if x)
assert first == 8, f"early stop should fire at step 8 (warmup 6 + 3 points), fired at {first}: {reasons}"
assert reasons[first - 1].startswith("early stop"), reasons[first - 1]

# 2. not killed when better than incumbent
job = make(early_stop={"warmup_frac": 0.3, "margin": 0.10, "patience_points": 3, "higher_is_better": False})
r = running(job)
metrics.write_text("".join(json.dumps({"step": k, "value": 0.5 / (k + 1)}) + "\n" for k in range(1, 21)))
jobs._update_progress(job, r)
assert jobs._should_kill(job, r) == ""

# 3. NaN
metrics.write_text(json.dumps({"step": 1, "value": float("nan")}) + "\n")
job = make(); r = running(job); jobs._update_progress(job, r)
assert jobs._should_kill(job, r) == "non-finite metric"

# 4. stall
job = make(stall_s=1); r = running(job); r.last_activity = time.time() - 5
assert jobs._should_kill(job, r).startswith("stalled")

# 5. timeout
job = make(timeout_s=1); r = running(job); r.start = time.time() - 5
assert jobs._should_kill(job, r).startswith("timeout")
print("TEST OK: kill rules (early stop, better-than-incumbent, NaN, stall, timeout)")
