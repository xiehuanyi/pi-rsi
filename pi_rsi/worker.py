"""Run one node end to end: worktree -> worker session -> commit -> guard -> official eval -> audit."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from . import gitops
from . import prompts as P
from .evaluator import run_eval, score_of, EvalError, queued_eval, begin_eval, eval_pending
from .tree import Node
from .util import (now_iso, read_json, read_text, append_text, atomic_write_json, atomic_write_text, tail_text,
                   fmt_score, now_ts, as_number)
from .measurement import (measurement_record, measurement_identity, validated_measurement, metrics_path,
                          evaluation_protocol, ProtocolMismatch)

FROZEN_PATHS = ["eval/", "docs/"]
WORKTREE_CACHE_BYTES = 256 << 20  # ignored files this large are pruned when a node is finished


class NodeFailure(Exception):
    pass


class CompletionFailure(Exception):
    def __init__(self, phase, cause):
        self.phase = phase
        super().__init__(f"{phase} incomplete: {cause}")


def run_node(orch, node: Node) -> None:
    cfg, tree = orch.cfg, orch.tree
    nd = cfg.nodes_dir / node.id
    nd.mkdir(parents=True, exist_ok=True)
    parent = tree.get(node.parent)
    worktree = cfg.worktrees_dir / node.id
    branch = f"node/{node.id}"
    base = node.base_commit or parent.commit
    t0 = time.time()
    phase = "implementation"
    hb = nd / "heartbeat"

    def on_event(ev):
        try:
            hb.write_text(str(ev["t"]))
        except OSError:
            pass

    try:
        orch.executions.project(tree)
        journal = orch.executions.read(node)
        if journal["measurement"].get("state") == "stale":
            # Measured under another evaluation protocol: neither re-executed nor documented
            # under the new one. `rsi reeval` re-measures it.
            orch.log("stale_measurement_not_rerun", node=node.id)
            if node.status in ("planned", "running", "evaluating", "analyzing", "waiting"):
                orch._park_stale(node)
            return
        if journal["measurement"].get("state") == "skipped":
            # Evaluation was deliberately skipped (no new component): as durable a boundary as a
            # validated measurement; only the documentation can resume.
            if journal["documentation"].get("state") == "complete":
                return
            orch.log("postprocess_resume", node=node.id)
            _finish_measurement(orch, node, None, nd, worktree, t0)
            return
        if node.measurement_valid or journal["measurement"].get("state") == "validated":
            # A completed measurement is a durable boundary: never enter the worker
            # or evaluator again merely because its documentation needs recovery.
            metrics = validated_measurement(orch, node)
            _check_tuning_budget(orch, node, nd)
            if journal["documentation"].get("state") == "complete":
                return  # repeated delivery of a completed task is idempotent
            orch.log("postprocess_resume", node=node.id)
            _finish_measurement(orch, node, metrics, nd, worktree, t0)
            return
        resume_eval = node.worker.get("resume_evaluation") and worktree.exists()
        resume_worker = not resume_eval and node.worker.get("resume_worker") and worktree.exists()
        if resume_eval:
            from .runner import RunResult
            commit = node.commit
            if gitops.head(worktree) != commit or gitops.git(["status", "--porcelain"], cwd=worktree):
                raise NodeFailure("monitored implementation changed before resume")
            res = RunResult(ok=True, exit_code=0, session_id=node.worker.get("session_id"))
            budget = node.worker.get("research", {}).get("tuning_budget", {})
            orch.log("monitor_wait_resume", node=node.id)
        else:
            if resume_worker:
                # The session ended on purpose after `rsi job submit`; its jobs have finished.
                res, attempt_dir = _resume_after_jobs(orch, node, nd, worktree, on_event)
            else:
                if node.worker.get("resume_implementation") and worktree.exists():
                    # Same hypothesis, a new execution attempt. Preserve all previous
                    # notes and Git commits instead of allocating another tree node.
                    archive = nd / "attempts" / f"a{node.attempt - 1:03d}"
                    archive.mkdir(parents=True, exist_ok=True)
                    for name in ("HANDOFF.md", "IMPLEMENTATION.md", "PROGRESS.md", "FAILURE.md", "TUNING.jsonl", "proposals.json"):
                        source = nd / name
                        if source.exists() and not (archive / name).exists():
                            (archive / name).write_bytes(source.read_bytes())
                else:
                    gitops.add_worktree(cfg.repo_dir, worktree, branch, base)
                record = orch.executions.begin_attempt(node)
                attempt = record["attempts"][-1]
                from .orchestrator import link_task_dirs
                link_task_dirs(cfg, worktree)
                tree.update(node, status="running", attempt=attempt["ordinal"], started_at=now_iso(), branch=branch, base_commit=base,
                            worker={**node.worker, "kind": cfg.runner.kind, "model": cfg.runner.model, "effort": cfg.runner.effort,
                                    "job_rounds": 0})
                atomic_write_text(nd / "HYPOTHESIS.md", f"# {node.title}\n\n{node.hypothesis}\n\n"
                                  f"type: {node.kind}\nparent: {node.parent}\nbase commit: {base}\n")
                orch.log("node_start", node=node.id, parent=node.parent, title=node.title, base=gitops.short(base))
                orch.render()

                # 1. worker session --------------------------------------------------
                if cfg.memory.enabled:
                    try:
                        info = orch.memory.snapshot(node)
                    except (OSError, ValueError, KeyError) as e:
                        orch.log("memory_failed", node=node.id, error=str(e))
                        info = {"revision": "", "error": str(e)}
                        atomic_write_text(nd / "MEMORY.md", "Research memory unavailable; use original experiment evidence.")
                    tree.update(node, worker={**node.worker, "memory": info})
                prompt = P.worker_prompt(cfg, tree, node, worktree)
                budget = node.worker.get("research", {}).get("tuning_budget", {})
                total_seconds = budget.get("seconds", cfg.runner.node_timeout_s)
                timeout = min(cfg.runner.node_timeout_s, total_seconds - orch.executions.worker_seconds(node))
                if timeout <= 0:
                    raise NodeFailure("implementation budget exhausted for this hypothesis")
                attempt_dir = nd / "attempts" / attempt["id"]
                attempt_dir.mkdir(parents=True, exist_ok=True)
                res = orch.worker_runner.run_agent(prompt, cwd=worktree, log_path=attempt_dir / "runner.jsonl", max_turns=cfg.runner.max_turns,
                                                   timeout_s=timeout, idle_timeout_s=cfg.runner.idle_timeout_s,
                                                   on_event=on_event)
            orch.add_cost("worker", res)
            orch.executions.worker_finished(node, res.duration_s)
            orch.log("worker_end", node=node.id, ok=res.ok, error=res.error, duration_s=round(res.duration_s, 1),
                     turns=res.num_turns, tool_calls=res.tool_calls, cost_usd=res.cost_usd, session=res.session_id)
            usage = dict(res.usage)
            cost = res.cost_usd
            worker_info = {**node.worker, "session_id": res.session_id or node.worker.get("session_id"), "runner_ok": res.ok,
                           "runner_error": res.error, "turns": res.num_turns, "tool_calls": res.tool_calls}
            # Latest-run log is a compatibility view; attempt logs remain permanent.
            log = Path(getattr(res, "log_path", "") or attempt_dir / "runner.jsonl")
            if log.exists():
                (nd / "runner.jsonl").write_bytes(log.read_bytes())
            prompt_copy = log.with_name(log.stem + ".prompt.md")
            if prompt_copy.exists():
                (nd / "runner.prompt.md").write_bytes(prompt_copy.read_bytes())
            worker_info["privacy_flag"] = _privacy_flag(log)

            # 2. commit whatever is there ---------------------------------------
            commit = gitops.commit_all(worktree, f"rsi: end of node {node.id} (auto-commit)") or gitops.head(worktree)
            tree.update(node, commit=commit, usage=usage, cost_usd=cost, worker=worker_info)

            # 2b. jobs the worker handed to the queue (`rsi job submit`): wait for them without this thread ----
            pending = worker_jobs(nd, pending_only=True)
            if pending:
                rounds = node.worker.get("job_rounds", 0) + 1
                if rounds > cfg.runner.max_job_rounds:
                    raise NodeFailure(f"the worker submitted jobs in {rounds} rounds; the cap is {cfg.runner.max_job_rounds}")
                orch.executions.execution_phase(node, "implementation", state="waiting")
                tree.update(node, status="waiting", worker={**node.worker, "resume_worker": True, "job_rounds": rounds,
                            "waiting": {"kind": "worker_job", "since": now_iso(), "jobs": [j["job"] for j in pending]}})
                orch.log("worker_job_wait", node=node.id, jobs=[j["job"] for j in pending], rounds=rounds)
                orch.render()
                return  # the controller's wake queue resumes this session when the jobs end

            # 3. handoff rescue --------------------------------------------------
            notes = nd / notes_file(cfg)
            if not notes.exists() and res.session_id and hasattr(orch.worker_runner, "resume_agent"):
                orch.log("handoff_rescue", node=node.id)
                wanted = (f"{notes}" if cfg.research.enabled else f"{nd}/HANDOFF.md and {nd}/proposals.json")
                rescue_prompt = (f"Your session was cut off by the budget. Do not change code. Write {wanted} "
                                 f"now, following the schemas from your instructions, using only numbers "
                                 f"you actually observed (see {nd}/PROGRESS.md). Then stop.")
                r2 = orch.worker_runner.resume_agent(res.session_id, rescue_prompt, cwd=worktree, log_path=nd / "runner.rescue.jsonl",
                                                     max_turns=8, timeout_s=600, idle_timeout_s=300)
                orch.add_cost("worker", r2)
                c2 = gitops.commit_all(worktree, f"rsi: after handoff rescue {node.id}")
                if c2:
                    commit = c2
                    tree.update(node, commit=commit)

            # 4. nothing produced by an abnormal session -> failure, not a silent no-change node
            if not res.ok and commit == base and not notes.exists():
                raise NodeFailure(f"worker ended abnormally ({res.error}) without producing any change")

            # 5. frozen-path guard ---------------------------------------------
            touched = gitops.changed_paths(worktree, base, "HEAD", FROZEN_PATHS)
            if touched:
                raise NodeFailure(f"modified frozen paths: {touched[:5]}")

            # 6. what is measured: the switched-on component, not a fallback ------
            if cfg.research.enabled:
                commit = _delivery(orch, node, nd, worktree, base)

        _check_tuning_budget(orch, node, nd)
        if (cfg.research.enabled and cfg.research.skip_unmeasured
                and node.worker.get("delivery", {}).get("component") == "none"):
            # 7. no new component: no official evaluation, the parent's result stands -------
            measurement = {"state": "skipped", "commit": node.commit, "at": now_iso(),
                           "reason": "the worker declared that this node delivers no new component (DELIVERY.json)"}
            orch.executions.measured(node, measurement)
            tree.update(node, measurement=measurement, status="analyzing")
            orch.log("evaluation_skipped", node=node.id, reason=node.worker["delivery"].get("reason", "")[:300])
            _finish_measurement(orch, node, None, nd, worktree, t0)
            return
        # 7. official evaluation -----------------------------------------------
        phase = "evaluation"
        orch.executions.execution_phase(node, phase)
        tree.update(node, status="evaluating")
        orch.render()
        incumbent = _incumbent(orch)
        protocol = evaluation_protocol(cfg)
        try:
            if queued_eval(cfg):
                # Submit and let go of this thread: the controller's wake queue resumes the node when the task
                # ends. A restarted controller re-attaches to the same job (same code, command and protocol).
                pending = begin_eval(cfg, worktree, cfg.task.official_seedset, nd / "eval", owner=f"{cfg.name}/{node.id}",
                                     incumbent_path=incumbent, resume=bool(resume_eval))
                if pending:
                    orch.executions.execution_phase(node, phase, state="waiting")
                    tree.update(node, status="waiting", worker={**node.worker, "resume_evaluation": True,
                                "waiting": {"kind": "evaluation", "since": now_iso()}})
                    orch.log("eval_submitted", node=node.id, seedset=cfg.task.official_seedset)
                    orch.render()
                    return
                resume_eval = True  # the task has already ended: collect its result
            # A restarted controller continues the persisted evaluation (same job, same attempt).
            metrics = run_eval(cfg, worktree, cfg.task.official_seedset, nd / "eval", owner=f"{cfg.name}/{node.id}",
                               incumbent_path=incumbent, resume=bool(resume_eval))
        except EvalError as e:
            raise NodeFailure(f"official evaluation failed: {e}")
        score = score_of(cfg, metrics)
        if score is None:
            raise NodeFailure(f"evaluator produced no finite numeric '{cfg.task.score_key}' in metrics")
        if evaluation_protocol(cfg) != protocol:
            raise NodeFailure("the evaluation protocol changed during the official evaluation; "
                              "the result cannot be attributed to either protocol")
        quick = read_json(worktree / "metrics.quick.json") or read_json(worktree / "runs" / cfg.task.quick_seedset / "metrics.json") or {}
        quick_score = quick.get(cfg.task.score_key)
        proposals = [] if cfg.research.enabled else _load_proposals(nd / "proposals.json")
        delta_parent = (score - parent.score) if parent.score is not None else None
        if not tree.higher_is_better():
            delta_parent = -delta_parent if delta_parent is not None else None
        marker = measurement_record(cfg, node, commit, score, protocol=protocol)
        with tree.lock:
            previous = tree.best_excluding(node.id)
            delta_best = (score - previous.score) * (1 if tree.higher_is_better() else -1) if previous else None
            measurement = {"state": "validated", **marker, "delta_best": delta_best,
                           "previous_incumbent": previous.id if previous else None}
            orch.executions.measured(node, measurement)
            tree.update(node, score=score, measurement=measurement, delta_best=delta_best,
                        metrics={k: v for k, v in metrics.items() if k != "per_seed"},
                    quick_score=quick_score, proposals=proposals, delta_parent=delta_parent,
                    worker={**node.worker, "evaluation_validated": marker, "waiting": None},
                    proposals_revision=node.worker.get("memory", {}).get("revision", ""))
        orch.log("eval_done", node=node.id, score=score, delta_parent=delta_parent,
                 elapsed_s=metrics.get("_eval", {}).get("elapsed_s"))

        _finish_measurement(orch, node, metrics, nd, worktree, t0)
    except CompletionFailure as e:
        _incomplete(orch, node, e, nd, t0)
    except ProtocolMismatch as e:  # measured under another protocol: retained, never invalidated or rerun
        _incomplete(orch, node, CompletionFailure("measurement", e), nd, t0)
    except NodeFailure as e:
        _fail(orch, node, str(e), nd, worktree, t0, phase=phase)
    except Exception as e:  # harness bug or infra failure: record, do not crash the loop
        import traceback
        append_text(nd / "harness_error.log", traceback.format_exc())
        _fail(orch, node, f"harness error: {type(e).__name__}: {e}", nd, worktree, t0, phase=phase)
    finally:
        orch.render()


def _incumbent(orch):
    """Curve of the best node so far, for early termination of a queued training run."""
    cfg, tree = orch.cfg, orch.tree
    best_now = tree.best()
    if cfg.task.job_enabled and best_now is not None:
        return cfg.nodes_dir / best_now.id / "eval" / f"run.{cfg.task.official_seedset}" / "metrics.jsonl"
    return None


def eval_pending_for(orch, node):
    """Poll a waiting node's official evaluation (see evaluator.eval_pending); no model is called."""
    cfg = orch.cfg
    return eval_pending(cfg, cfg.worktrees_dir / node.id, cfg.task.official_seedset, cfg.nodes_dir / node.id / "eval",
                        owner=f"{cfg.name}/{node.id}", incumbent_path=_incumbent(orch))


def worker_jobs(nd: Path, pending_only: bool = False) -> list[dict]:
    """Jobs the worker registered with `rsi job submit` (nodes/<id>/jobs/*.json), with their queue state."""
    from . import jobs
    out = []
    for path in sorted((nd / "jobs").glob("*.json")) if (nd / "jobs").is_dir() else []:
        record = read_json(path, {}) or {}
        try:
            job = jobs.Job.load(record["job"])
            state = {"status": job.status, "reason": job.reason, "duration_s": job.duration_s, "exit_code": job.exit_code,
                     "log": str(jobs.jobs_dir() / "logs" / f"{job.id}.log")}
        except (KeyError, FileNotFoundError):
            state = {"status": "missing", "reason": "job record not found in the queue"}
        if pending_only and state["status"] not in ("queued", "running"):
            continue
        out.append({**record, **state})
    return out


def worker_jobs_pending(nd: Path) -> bool:
    pending = worker_jobs(nd, pending_only=True)
    if pending:
        from . import jobs
        jobs.ensure_daemon()  # a poll keeps the queue alive exactly as a blocking wait would
    return bool(pending)


def _resume_after_jobs(orch, node, nd, worktree, on_event):
    """Wake the worker's own session once the jobs it submitted have ended, with a bounded budget."""
    cfg, tree = orch.cfg, orch.tree
    session_id = node.worker.get("session_id")
    if not session_id or not hasattr(orch.worker_runner, "resume_agent"):
        raise NodeFailure("the worker submitted jobs but its session cannot be resumed")
    finished = worker_jobs(nd)
    orch.executions.execution_phase(node, "implementation")
    tree.update(node, status="running", worker={**node.worker, "resume_worker": False, "waiting": None})
    record = orch.executions.read(node)
    attempt_dir = nd / "attempts" / (record.get("active_attempt") or f"a{node.attempt:03d}")
    attempt_dir.mkdir(parents=True, exist_ok=True)
    budget = node.worker.get("research", {}).get("tuning_budget", {})
    total_seconds = budget.get("seconds", cfg.runner.node_timeout_s)
    remaining = total_seconds - orch.executions.worker_seconds(node)
    timeout = max(cfg.runner.resume_min_s, min(cfg.runner.resume_timeout_s, remaining))
    round_no = node.worker.get("job_rounds", 1)
    prompt = P.worker_resume_prompt(cfg, node, finished, timeout)
    orch.log("worker_resume", node=node.id, jobs=[j.get("job") for j in finished],
             statuses=[j.get("status") for j in finished], timeout_s=timeout, round=round_no)
    res = orch.worker_runner.resume_agent(session_id, prompt, cwd=worktree,
                                          log_path=attempt_dir / f"runner.resume{round_no}.jsonl",
                                          max_turns=cfg.runner.max_turns, timeout_s=timeout,
                                          idle_timeout_s=cfg.runner.idle_timeout_s, on_event=on_event)
    return res, attempt_dir

def _delivery(orch, node, nd, worktree, base):
    """Record what the worker says it delivered (DELIVERY.json). A component the worker switched off is
    measured switched on, from the active commit it names: the official level then tests the idea, and the
    choice of the best node by official score, not the worker's development gate, protects the study."""
    cfg, tree = orch.cfg, orch.tree
    data = read_json(nd / "DELIVERY.json")
    data = data if isinstance(data, dict) else {}
    component = data.get("component") if data.get("component") in ("on", "off", "none") else "undeclared"
    record = {"component": component, "reason": str(data.get("reason") or "")[:2000],
              "dev_delta": as_number(data.get("dev_delta")), "dev_sem": as_number(data.get("dev_sem")),
              "measured": "delivered"}
    commit = node.commit
    if component == "off" and cfg.research.measure_active:
        active = str(data.get("active_commit") or "").strip()
        if not gitops.on_branch_between(worktree, base, active):
            record["note"] = "active_commit missing or not on this branch; the delivered commit is measured"
        elif gitops.changed_paths(worktree, base, active, FROZEN_PATHS):
            record["note"] = "active_commit modifies frozen paths; the delivered commit is measured"
        else:
            gitops.restore_tree(worktree, active)
            commit = gitops.commit_all(worktree, f"rsi: measure the switched-on component of {node.id} "
                                                 f"(from {active[:12]}; the worker delivered it off)") or gitops.head(worktree)
            record.update(measured="active", active_commit=active, worker_commit=node.commit)
    tree.update(node, commit=commit, worker={**node.worker, "delivery": record})
    orch.log("delivery", node=node.id, component=component, measured=record["measured"],
             dev_delta=record["dev_delta"], note=record.get("note", ""))
    return commit


def tuning_trials(path):
    """Distinct trials registered in TUNING.jsonl. Event rows (failures, corrections) and reruns or
    re-registrations of a trial number already listed are not extra trials."""
    numbered, unnumbered = set(), 0
    for line in path.read_text().splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or row.get("event"):
            continue
        if row.get("trial") is None:
            unnumbered += 1
        else:
            numbered.add(str(row["trial"]))
    return len(numbered) + unnumbered


def _check_tuning_budget(orch, node, nd):
    """The trial cap is the lead's design, not an integrity rule: an overrun is recorded as a protocol
    deviation for the analysis and audit, and the measurement still counts."""
    maximum = node.worker.get("research", {}).get("tuning_budget", {}).get("max_trials")
    path = nd / "TUNING.jsonl"
    if not maximum or not path.exists():
        return None
    count = tuning_trials(path)
    if count <= maximum:
        return None
    deviation = f"tuning: {count} distinct trials recorded against a cap of {maximum}"
    if node.worker.get("protocol_deviation") != deviation:
        orch.tree.update(node, worker={**node.worker, "protocol_deviation": deviation})
        orch.log("protocol_deviation", node=node.id, detail=deviation)
    return deviation


def _finish_measurement(orch, node, metrics, nd, worktree, t0):
    """Retry failed completion stages on the same node, with no worker/evaluator calls. `metrics` is None
    when the official evaluation was skipped (no new component): nothing is scored and the parent's result stands."""
    cfg, tree = orch.cfg, orch.tree
    parent = tree.get(node.parent)
    measured = metrics is not None
    if measured:
        parent_full = read_json(metrics_path(cfg, parent)) or parent.metrics
        noise = orch.noise_level(metrics, parent_full)
        from .evidence import comparison
        setup = orch.setup if cfg.research.enabled else None
        assessment = comparison(metrics, parent_full, score=node.score, parent_score=parent.score,
                                higher_is_better=tree.higher_is_better(), fallback=noise,
                                calibration=setup.calibration() if setup else None,
                                practical_delta=setup.practical_delta() if setup else 0.0)
    else:
        noise = None
        assessment = {"verdict": "not_measured", "classification": "not_measured",
                      "scope": "No official evaluation: the worker declared that this node delivers no new "
                               "component, so the parent's official result stands and nothing new was scored."}
    deviation = _check_tuning_budget(orch, node, nd)
    if deviation:
        assessment = {**assessment, "protocol_deviation": deviation}
    if node.worker.get("delivery"):
        assessment = {**assessment, "delivery": node.worker["delivery"]}
    if cfg.research.enabled:
        # The single home of the judgement on this result; everything else cites it.
        atomic_write_json(nd / "eval" / "comparison.json", {**assessment, "node": node.id, "parent": parent.id})
    identity = measurement_identity(node, metrics or {})
    state = dict(orch.executions.read(node)["documentation"])
    state.setdefault("attempts", {})
    state.setdefault("failures", [])
    research = getattr(orch, "research", None)
    gitlog = gitops.log_oneline(worktree, node.base_commit)
    diffstat = gitops.diff_stat(worktree, node.base_commit)

    def save(**changes):
        state.update(changes)
        state.setdefault("state", "pending")
        orch.executions.document(node, state)
        tree.update(node, status="analyzing", documentation=dict(state),
                    worker={**node.worker, "postprocess": dict(state)})

    def start(phase):
        if orch.stop_flag.is_set():
            raise CompletionFailure(phase, "controller interrupted; saved measurement retained")
        attempts = dict(state["attempts"])
        if attempts.get(phase, 0) >= cfg.research.max_stage_retries + 1:
            raise CompletionFailure(phase, "bounded completion retries exhausted")
        attempts[phase] = attempts.get(phase, 0) + 1
        save(state="running", phase=phase, attempts=attempts)

    def verify():
        if measured:
            try:
                validated_measurement(orch, node)
            except ProtocolMismatch as e:  # not an integrity failure; keep the record for re-measurement
                raise CompletionFailure(phase, e) from e
            except (ValueError, OSError) as e:
                raise NodeFailure(f"completed measurement integrity failure: {e}") from e
        _check_tuning_budget(orch, node, nd)

    while True:
        phase = state.get("phase", "analysis")
        try:
            verify()
            if not state.get("analysis_complete"):
                phase = "analysis"
                start(phase)
                if research and research.enabled:
                    orch.log("research_analyze", node=node.id)
                    research.analyze(node, metrics, assessment)
                elif measured and cfg.task.job_enabled and node.worker.get("session_id") and hasattr(orch.worker_runner, "resume_agent"):
                    _analysis_session(orch, node, nd, worktree, node.worker["session_id"], metrics, node.score, parent)
                verify()
                save(analysis_complete=True, phase="audit")
            receipt = read_json(nd / "audit.json", {}) or {}
            audit = receipt.get("audit") if receipt.get("measurement_identity") == identity else None
            if not isinstance(audit, dict) or not isinstance(audit.get("summary"), str) or not audit.get("verdict"):
                phase = "audit"
                start(phase)
                if measured:
                    audit = orch.utility.audit(node, metrics, gitlog, diffstat, noise, assessment if cfg.research.enabled else None)
                else:  # nothing official to check a claim against
                    reason = (node.worker.get("delivery") or {}).get("reason", "")
                    interpretation = (node.worker.get("analysis") or {}).get("interpretation", "")
                    audit = {"summary": f"Not officially evaluated: no new component delivered. {reason} {interpretation}".strip()[:1500],
                             "verdict": "not_measured", "claim_check": {"consistent": True, "note": "no official result"}}
                if not isinstance(audit, dict) or not isinstance(audit.get("summary"), str) or not audit.get("verdict"):
                    raise ValueError("audit requires a summary and verdict")
                if cfg.research.enabled:
                    # The harness owns the verdict; cross-node knowledge belongs to the wiki.
                    audit.update(verdict=assessment["verdict"], insights=[], deadends=[])
                atomic_write_json(nd / "audit.json", {"measurement_identity": identity, "audit": audit})
            audit = {**audit, "comparison": assessment}  # tree projection; eval/comparison.json is the source
            verify()
            phase = "publish"
            start(phase)
            gitops.tag(cfg.repo_dir, f"rsi/{node.id}", node.commit)
            _record_audit(orch, node, audit, gitlog, diffstat)
            state.update(state="complete", phase="complete", pending=False, completed_at=now_iso())
            orch.executions.document(node, state)
            tree.complete(node, duration_s=round(time.time() - t0, 1), summary=audit["summary"],
                          verdict=audit["verdict"], audit=audit, failure=None, diagnosis={},
                          documentation=dict(state),
                          worker={**node.worker, "postprocess": state, "resume_postprocess": False,
                                  "resume_evaluation": False})
            orch.log("node_done", node=node.id, score=node.score, delta_best=node.delta_best,
                     verdict=audit["verdict"], title=node.title)
            _prune_worktree(orch, node, nd, worktree)
            if cfg.research.enabled:
                try:
                    from . import proxy
                    proxy.write(cfg, tree)
                except Exception as e:  # a view of the tree; never changes the node's outcome
                    orch.log("proxy_ledger_failed", node=node.id, error=str(e))
            return
        except (NodeFailure, CompletionFailure):
            raise
        except Exception as e:
            failures = state["failures"] + [{"at": now_iso(), "phase": phase, "error": str(e)}]
            save(phase=phase, failures=failures, pending=True)
            if orch.stop_flag.is_set() or state["attempts"].get(phase, 0) >= cfg.research.max_stage_retries + 1:
                raise CompletionFailure(phase, e) from e
            orch.log("postprocess_retry", node=node.id, phase=phase, error=str(e), new_experiments=0)


def _incomplete(orch, node, failure, nd, t0):
    """Keep measured results separate from an unfinished explanation or publication."""
    documentation = {**orch.executions.read(node)["documentation"], "state": "needs_attention",
                     "phase": failure.phase, "pending": True, "error": str(failure)}
    orch.executions.document(node, documentation)
    orch.tree.update(node, status="incomplete", documentation=documentation,
                     failure=str(failure), diagnosis={"retry": False, "phase": failure.phase},
                     finished_at=now_iso(), duration_s=round(time.time() - t0, 1), verdict="pending",
                     summary=f"Official score {fmt_score(node.score)} measured; {failure.phase} remains incomplete.",
                     worker={**node.worker, "resume_postprocess": True,
                             "postprocess": {**node.worker.get("postprocess", {}), "phase": failure.phase, "pending": True}})
    atomic_write_text(nd / "FAILURE.md", f"# Completion pending {node.id}\n\n{failure}\n\n"
                      "The official measurement is retained. Resume only its incomplete completion stage; "
                      "do not rerun implementation, training or evaluation.\n")
    orch.log("postprocess_incomplete", node=node.id, phase=failure.phase, score=node.score, new_experiments=0)


def _fail(orch, node: Node, failure: str, nd: Path, worktree: Path, t0: float, *, phase="implementation") -> None:
    tree = orch.tree
    runner_tail = tail_text(nd / "runner.jsonl", 60, 12000)
    try:
        gitstatus = gitops.git(["status", "--short"], cwd=worktree, check=False) if worktree.exists() else "(no worktree)"
        gitlog = gitops.log_oneline(worktree, node.base_commit or "HEAD~0") if worktree.exists() else ""
    except Exception:
        gitstatus, gitlog = "(unavailable)", ""
    if node.worker.get("evaluation_validated"):
        # Integrity/budget failures after scoring must never authorize a replacement
        # experiment under the guise of recovering its documentation.
        diagnosis = {"retry": False, "phase": "integrity", "cause": failure, "advice": ""}
        orch.executions.invalidate(node, failure)
        node.measurement = {"state": "invalid", "reason": failure}
    else:
        diagnosis = orch.utility.diagnose(node, failure, runner_tail, gitstatus + "\n" + gitlog)
        diagnosis["phase"] = phase
        orch.executions.execution_phase(node, phase, state="failed", error=failure)
    tree.update(node, status="failed", failure=failure, diagnosis=diagnosis, finished_at=now_iso(),
                duration_s=round(time.time() - t0, 1), verdict="failed",
                summary=f"FAILED: {failure[:160]} — {diagnosis.get('cause', '')[:200]}",
                worker={**node.worker, "resume_evaluation": False, "resume_worker": False, "waiting": None})
    atomic_write_text(nd / "FAILURE.md", f"# Failure {node.id}\n\n{failure}\n\n## Diagnosis\n{json.dumps(diagnosis, indent=1)}\n")
    orch.log("node_failed", node=node.id, failure=failure, retry=diagnosis.get("retry"), cause=diagnosis.get("cause"))
    if not diagnosis.get("retry"):  # a retry reuses this worktree and may reuse its caches
        _prune_worktree(orch, node, nd, worktree)


def _prune_worktree(orch, node, nd, worktree):
    """A finished node keeps its code and small files; large ignored caches go (n004 left 13 GB of features)."""
    try:
        removed = gitops.prune_ignored(worktree, WORKTREE_CACHE_BYTES)
    except Exception as e:  # cleanup never decides a node's outcome
        orch.log("worktree_prune_failed", node=node.id, error=str(e))
        return
    if removed:
        atomic_write_json(nd / "worktree_pruned.json", {"at": now_iso(), "min_bytes": WORKTREE_CACHE_BYTES,
                                                        "files": [{"path": p, "bytes": b} for p, b in removed]})
        orch.log("worktree_pruned", node=node.id, files=len(removed), bytes=sum(b for _, b in removed))


def notes_file(cfg) -> str:
    """What the implementation worker writes: research mode separates its record from the analysis."""
    return "IMPLEMENTATION.md" if cfg.research.enabled else "HANDOFF.md"


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
    best = orch.tree.best_excluding(node.id)
    delta_best = node.delta_best
    if delta_best is None and best is not None and best.score is not None and node.score is not None:
        delta_best = (node.score - best.score) * (1 if orch.tree.higher_is_better() else -1)
    lines = [f"# Summary {node.id}: {node.title}", "", audit["summary"], "",
             f"- official {cfg.task.score_key}: {fmt_score(node.score)} (delta vs parent {fmt_score(node.delta_parent)}, vs best {fmt_score(delta_best)})",
             f"- verdict: {audit['verdict']}", f"- commit: {gitops.short(node.commit)}",
             f"- claim check: {'consistent' if audit['claim_check'].get('consistent') else 'MISMATCH'} — {audit['claim_check'].get('note', '')}",
             "", "## Git log", "```", gitlog or "(no commits)", "```", "```", diffstat, "```"]
    atomic_write_text(nd / "SUMMARY.md", "\n".join(lines) + "\n")
    for ins in audit.get("insights", []) or []:
        line = f"- {ins.strip()} [{node.id}, score {fmt_score(node.score)}]\n"
        if line not in read_text(cfg.insights_path):
            append_text(cfg.insights_path, line)
    for de in audit.get("deadends", []) or []:
        line = f"- {de.strip()} [{node.id}]\n"
        if line not in read_text(cfg.deadends_path):
            append_text(cfg.deadends_path, line)


def _analysis_session(orch, node: Node, nd: Path, worktree: Path, session_id: str, metrics: dict, score: float, parent: Node) -> None:
    """Job mode: wake the worker's session once the official run finished so the handoff reflects the real result."""
    cfg, tree = orch.cfg, orch.tree
    best = tree.best()
    root = tree.get("root")
    run_dir = Path(metrics.get("_eval", {}).get("run_dir", ""))
    curve_lines = []
    if run_dir and (run_dir / "metrics.jsonl").exists():
        pts = [l for l in (run_dir / "metrics.jsonl").read_text().splitlines() if l.strip()]
        step = max(1, len(pts) // 12)
        curve_lines = pts[::step][:12] + ([pts[-1]] if pts and pts[-1] not in pts[::step][:12] else [])
    from .prompts import render, direction
    prompt = render("analysis", level=cfg.task.official_seedset, node_id=node.id, score_key=cfg.task.score_key,
                    direction=direction(cfg), score=fmt_score(score), parent_score=fmt_score(parent.score),
                    best_score=fmt_score(best.score if best else None), root_score=fmt_score(root.score),
                    run_summary=json.dumps({k: v for k, v in metrics.items() if k not in ("per_item", "per_seed", "_eval")})[:1500],
                    curve="\n".join(curve_lines) or "(no curve)", node_dir=str(nd))
    orch.log("analysis_start", node=node.id)
    r = orch.worker_runner.resume_agent(session_id, prompt, cwd=worktree, log_path=nd / "runner.analysis.jsonl", max_turns=10,
                                        timeout_s=900, idle_timeout_s=300)
    orch.add_cost("worker", r)
    orch.log("analysis_end", node=node.id, ok=r.ok, error=r.error, duration_s=round(r.duration_s, 1))


def _privacy_flag(log_path: Path) -> str:
    """Flag tool calls that touch a private/ directory (hidden labels). Reads only tool inputs, not outputs."""
    hits = []
    try:
        for line in open(log_path, encoding="utf-8", errors="replace"):
            if '"tool_call"' not in line and '"tool_execution_start"' not in line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            raw = json.dumps(d.get("rawInput") or d.get("args") or {})
            if "private/" in raw or "/private" in raw:
                hits.append(raw[:160])
    except FileNotFoundError:
        pass
    return "; ".join(hits[:3])
