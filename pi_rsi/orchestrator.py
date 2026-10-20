"""The loop: set up the root, schedule nodes, supervise workers, stop, report. No LLM sits idle in this loop;
LLMs are invoked only inside node workers and utility calls."""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path
from typing import Any

from . import gitops
from .agents import Utility
from .config import ExperimentCfg
from .evaluator import run_eval, score_of, EvalError
from .render import render_all
from .runner import make_runner, RunResult
from .scheduler import Scheduler
from .tree import Node, Tree
from .util import append_jsonl, atomic_write_json, atomic_write_text, now_iso, now_ts, read_json, fmt_score, human_duration, read_text, tail_text
from .worker import run_node
from .ops import run_ops, write_narrative
from .memory import ResearchMemory
from .research import ResearchLoop
from .setup import Setup


class Orchestrator:
    def __init__(self, cfg: ExperimentCfg, verbose: bool = True):
        self.cfg = cfg
        self.verbose = verbose
        self.started_ts = now_ts()
        self.worker_runner = make_runner(cfg.runner.kind, cfg.runner.model, cfg.runner.effort, cfg.runner.extra_args)
        self.utility_runner = make_runner(cfg.utility.kind, cfg.utility.model, cfg.utility.effort)
        self.tree = self._load_or_create_tree()
        from .execution import ExecutionStore
        self.executions = ExecutionStore(cfg)
        self.executions.project(self.tree)
        if cfg.research.enabled:
            self.started_ts -= float(self.tree.meta.get("research_elapsed_s", 0))
        self.utility = Utility(self)
        self.scheduler = Scheduler(self)
        self._cost_lock = threading.Lock()
        self.costs = read_json(cfg.dir / "costs.json", {}) or {}
        self.stop_flag = threading.Event()
        self.render_lock = threading.Lock()
        self.memory = ResearchMemory(cfg)
        self.research = ResearchLoop(self)
        self.setup = Setup(self)
        self.maintainer = self.utility
        if cfg.maintainer.enabled:
            m = cfg.maintainer
            self.maintainer = Utility(self, make_runner(m.kind, m.model, m.effort), m, "maintainer")

    # infrastructure ----------------------------------------------------------
    def _load_or_create_tree(self) -> Tree:
        if self.cfg.tree_path.exists():
            return Tree.load(self.cfg.tree_path)
        t = Tree(self.cfg.tree_path, meta={"experiment": self.cfg.name, "task": self.cfg.task.name,
                                           "higher_is_better": self.cfg.task.higher_is_better,
                                           "score_key": self.cfg.task.score_key, "created_at": now_iso(),
                                           "runner": f"{self.cfg.runner.kind}:{self.cfg.runner.model}:{self.cfg.runner.effort}",
                                           "reference_scores": self.cfg.task.reference_scores,
                                           "harness_commit": _harness_commit()})
        t.save()
        return t

    def log(self, event: str, **kw: Any) -> None:
        rec = {"t": now_iso(), "event": event, **kw}
        append_jsonl(self.cfg.events_path, rec)
        if self.verbose:
            extras = " ".join(f"{k}={_short(v)}" for k, v in kw.items())
            print(f"[{rec['t'][11:19]}] {event:<16} {extras}", flush=True)

    def add_cost(self, kind: str, res: RunResult) -> None:
        with self._cost_lock:
            c = self.costs.setdefault(kind, {"calls": 0, "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "seconds": 0.0})
            c["calls"] += 1
            c["cost_usd"] += float(res.cost_usd or 0.0)
            u = res.usage or {}
            c["input_tokens"] += int(u.get("input_tokens", u.get("input", 0)) or 0)
            c["output_tokens"] += int(u.get("output_tokens", u.get("output", 0)) or 0)
            c["seconds"] += float(res.duration_s or 0.0)
            atomic_write_json(self.cfg.dir / "costs.json", self.costs)

    def render(self) -> None:
        with self.render_lock:
            try:
                render_all(self.cfg, self.tree, self.costs, self.state())
            except Exception:
                append_jsonl(self.cfg.events_path, {"t": now_iso(), "event": "render_error", "trace": traceback.format_exc()[-2000:]})

    def state(self) -> dict[str, Any]:
        return {"pid": os.getpid(), "started_at": self.started_ts, "heartbeat": now_ts(), "status": getattr(self, "_status", "running"),
                "stop_reason": getattr(self, "_stop_reason", None), "experiment": self.cfg.name}

    def write_state(self) -> None:
        if self.cfg.research.enabled:
            # Elapsed research time must survive a restart, but tree.json is large and the main loop
            # calls this every few seconds: persist it once a minute and on every status change.
            now, status = now_ts(), getattr(self, "_status", "running")
            saved_at, saved_status = getattr(self, "_elapsed_saved", (0.0, None))
            if now - saved_at >= 60 or status != saved_status:
                self.tree.meta["research_elapsed_s"] = max(0, now - self.started_ts)
                self.tree.save()
                self._elapsed_saved = (now, status)
        atomic_write_json(self.cfg.dir / "state.json", self.state())

    def noise_level(self, metrics: dict | None = None, parent_metrics: dict | None = None) -> float:
        """Two standard errors of the node-vs-parent difference. Paired when both evaluations expose per_item values on
        the same items (same seeds / same holdout rows); otherwise unpaired from the reported SEMs; else 1% of baseline."""
        paired = _paired_noise(metrics or {}, parent_metrics or {})
        if paired is not None:
            return paired
        sems = []
        for m in (metrics or {}, parent_metrics or {}):
            v = m.get("score_sem")
            if isinstance(v, (int, float)) and v > 0:
                sems.append(float(v))
        if sems:
            return 2.0 * sum(v * v for v in sems) ** 0.5
        root = self.tree.get("root")
        return abs(root.score or 1.0) * 0.01

    # root ---------------------------------------------------------------------
    def ensure_root(self) -> None:
        cfg = self.cfg
        if not (cfg.repo_dir / ".git").exists():
            self.log("repo_init", repo=str(cfg.repo_dir))
            _populate_repo(cfg)
            sha = gitops.init_repo(cfg.repo_dir)
            gitops.tag(cfg.repo_dir, "rsi/root", sha)
        if not cfg.insights_path.exists():
            cfg.insights_path.write_text("# Insights (verified across nodes; each line cites the node)\n\n", encoding="utf-8")
        if not cfg.deadends_path.exists():
            cfg.deadends_path.write_text("# Dead ends (do not retry; each line cites the node)\n\n", encoding="utf-8")
        if "root" not in self.tree.nodes:
            from .measurement import evaluation_protocol, measurement_record
            sha = gitops.head(cfg.repo_dir)
            nd = cfg.nodes_dir / "root"
            nd.mkdir(parents=True, exist_ok=True)
            score, metrics, measurement = None, {}, {}
            if cfg.search.root_eval:
                self.log("root_eval", seedset=cfg.task.official_seedset)
                protocol = evaluation_protocol(cfg)
                metrics = run_eval(cfg, cfg.repo_dir, cfg.task.official_seedset, nd / "eval", owner=f"{cfg.name}/root")
                score = score_of(cfg, metrics)
                if score is None:
                    raise EvalError(f"baseline evaluator produced no finite numeric '{cfg.task.score_key}'")
                if evaluation_protocol(cfg) != protocol:
                    raise EvalError("the evaluation protocol changed during the baseline evaluation")
                # The baseline is a measurement like any other: bound to code, metrics file and protocol.
                measurement = {"state": "validated", "delta_best": None, **measurement_record(
                    cfg, None, sha, score, path=nd / "eval" / f"metrics.{cfg.task.official_seedset}.json",
                    protocol=protocol)}
                self.log("root_eval_done", score=score, elapsed_s=metrics.get("_eval", {}).get("elapsed_s"))
            root = Node(id="root", parent=None, depth=0, title="baseline", hypothesis="The untouched starter code.",
                        kind="baseline", status="done", commit=sha, base_commit=sha, score=score,
                        metrics={k: v for k, v in metrics.items() if k != "per_seed"}, finished_at=now_iso(),
                        summary=f"Baseline starter code. Official {cfg.task.score_key}: {fmt_score(score)}.", verdict="baseline",
                        measurement=measurement)
            self.tree.add(root)
            if measurement:
                self.executions.rebind_protocol(root, measurement)
                self.tree.meta["evaluation_protocol"] = measurement["protocol"]
                self.tree.save()
        root = self.tree.get("root")
        self.research_checkpoint()
        if not root.proposals and not self.research.enabled:
            k = cfg.search.width_root
            self.log("planner_root", k=k)
            revision = self.memory.revision
            props = self.utility.plan_root(k)
            if not props:
                raise RuntimeError("root planner returned no proposals")
            self.tree.update(root, proposals=props, proposals_revision=revision)
            self.log("planner_root_done", n=len(props), titles=[p["title"] for p in props])
        self.render()

    # evaluation protocol ------------------------------------------------------
    def check_protocol(self) -> None:
        """Bind official measurements to the evaluation protocol in force.

        A score measured under another evaluator, scoring configuration or declared data version
        stays on record as `stale` but is no longer selection evidence. While the baseline is not
        valid under the current protocol, dispatch stops (`protocol_changed`) and final confirmation
        is deferred; `rsi reeval` re-measures, and restoring the old protocol restores the records."""
        from .measurement import evaluation_protocol, measurement_record, metrics_path
        current = evaluation_protocol(self.cfg)
        meta = self.tree.meta
        if meta.get("evaluation_protocol") == current and not meta.get("protocol_change"):
            return
        changed = {"adopted": [], "stale": [], "restored": []}
        for node in sorted(self.tree.nodes.values(), key=lambda n: n.id):
            measurement = dict(self.executions.read(node)["measurement"] or node.measurement or {})
            if not measurement and node.id == "root" and isinstance(node.score, (int, float)) and node.commit:
                path = metrics_path(self.cfg, node)
                if path.exists() and score_of(self.cfg, read_json(path) or {}) == node.score:
                    measurement = {"state": "validated", "delta_best": None, **measurement_record(
                        self.cfg, node, node.commit, node.score, path=path, protocol=current)}
                    changed["adopted"].append(node.id)
            state, protocol = measurement.get("state"), measurement.get("protocol")
            if state == "validated" and not protocol:
                # Pre-binding record: adopted under the protocol in force at upgrade time.
                measurement["protocol"] = current
                changed["adopted"].append(node.id)
            elif state == "validated" and protocol != current:
                measurement.update(state="stale", stale_reason=(
                    f"measured under evaluation protocol {protocol}; the current protocol is {current}"))
                changed["stale"].append(node.id)
            elif state == "stale" and protocol == current:
                measurement["state"] = "validated"
                measurement.pop("stale_reason", None)
                changed["restored"].append(node.id)
            elif node.id not in changed["adopted"]:
                continue
            self.executions.rebind_protocol(node, measurement)
            with self.tree.lock:
                node.measurement = measurement  # saved once below
            if state == "validated" and measurement["state"] == "stale" and node.status in (
                    "planned", "running", "evaluating", "analyzing"):
                self._park_stale(node)
        self.executions.project(self.tree)
        root = self.tree.nodes.get("root")
        root_comparable = root is None or (root.measurement_valid
                                           and root.measurement.get("protocol", current) == current)
        stale = [n.id for n in self.tree.nodes.values() if n.measurement.get("state") == "stale"]
        previous = meta.get("evaluation_protocol")
        meta["evaluation_protocol"] = current
        if stale and not root_comparable:
            change = meta.get("protocol_change") or {"from": previous, "at": now_iso()}
            if change.get("to") != current:
                meta["protocol_change"] = {**change, "to": current, "stale": stale}
                self.log("protocol_changed", previous=previous, current=current, stale=stale,
                         action="dispatch stopped; re-measure with `rsi reeval` or restore the evaluator")
        elif meta.pop("protocol_change", None):
            self.log("protocol_change_resolved", protocol=current, still_stale=stale)
        if any(changed.values()):
            self.log("protocol_bookkeeping", protocol=current, **changed)
        self.tree.save()

    def _park_stale(self, node: Node) -> None:
        """A stale measurement is neither re-executed nor documented under the new protocol."""
        self.tree.update(node, status="incomplete", finished_at=node.finished_at or now_iso(),
                         failure="measurement is stale: the evaluation protocol changed (rsi reeval re-measures it)",
                         diagnosis={"retry": False, "phase": "protocol"})

    # crash recovery -----------------------------------------------------------
    def recover(self) -> None:
        canonical = self.tree.hypotheses()
        candidates = [n for n in canonical if n.measurement.get("state") != "stale" and (
                      n.status in ("running", "evaluating", "analyzing", "incomplete", "waiting")
                      or (n.status == "failed" and n.measurement_valid and n.diagnosis.get("phase") != "integrity"))]
        for n in candidates:
            self.log("recover_stale", node=n.id, status=n.status)
            nd = self.cfg.nodes_dir / n.id
            wt = self.cfg.worktrees_dir / n.id
            if n.measurement.get("state") == "skipped":
                # Evaluation was deliberately skipped: only its documentation can resume, never the worker or evaluator.
                postprocess = dict(self.executions.read(n)["documentation"])
                postprocess.update(state="pending", attempts={}, pending=True)
                self.executions.document(n, postprocess)
                self.tree.update(n, status="planned", finished_at=None, documentation=postprocess,
                                 worker={**n.worker, "resume_postprocess": True, "resume_evaluation": False,
                                         "postprocess": postprocess})
                self.log("postprocess_resume", node=n.id, phase=postprocess.get("phase", "analysis"), new_experiments=0)
                continue
            if n.measurement_valid:
                from .measurement import validated_measurement, ProtocolMismatch
                try:
                    validated_measurement(self, n)
                except ProtocolMismatch as e:
                    # Not an integrity failure: the record is kept for re-measurement.
                    self.log("recover_protocol_mismatch", node=n.id, error=str(e))
                    continue
                except (ValueError, OSError) as e:
                    self.executions.invalidate(n, str(e))
                    self.tree.update(n, status="failed", failure=f"completed measurement integrity failure: {e}",
                                     measurement={"state": "invalid", "reason": str(e)},
                                     diagnosis={"retry": False, "phase": "integrity"}, finished_at=now_iso(), verdict="failed")
                    self.log("postprocess_recovery_rejected", node=n.id, error=str(e))
                    continue
                postprocess = dict(self.executions.read(n)["documentation"])
                postprocess.update(state="pending", attempts={}, pending=True)
                self.executions.document(n, postprocess)
                self.tree.update(n, status="planned", finished_at=None,
                                 documentation=postprocess,
                                 worker={**n.worker, "resume_postprocess": True, "resume_evaluation": False,
                                         "postprocess": postprocess})
                self.log("postprocess_resume", node=n.id, phase=postprocess.get("phase", "analysis"), new_experiments=0)
                continue
            execution = self.executions.read(n)["execution"]
            waiting = (n.worker.get("waiting") or {}).get("kind")
            if waiting == "worker_job" and n.worker.get("resume_worker") and wt.exists():
                # Its session ended on purpose after `rsi job submit`; the job keeps running in the queue.
                self.tree.update(n, status="waiting")
                self.log("monitor_resume", node=n.id, phase="worker_job")
                continue
            if (execution.get("phase") == "evaluation" or n.status in ("evaluating", "analyzing", "waiting")) and wt.exists():
                if gitops.head(wt) == n.commit and not gitops.git(["status", "--porcelain"], cwd=wt):
                    self.tree.update(n, status="planned", worker={**n.worker, "resume_evaluation": True})
                    self.log("monitor_resume", node=n.id, phase="evaluate/analyze")
                    continue  # preserve the evaluated worktree and wait on its original queue task
            commit = None
            if wt.exists():
                try:
                    commit = gitops.commit_all(wt, f"rsi: recovered uncommitted work of {n.id}") or gitops.head(wt)
                except Exception:
                    commit = None
            diagnosis = {"cause": "The harness process stopped while this node was running.", "retry": True,
                         "advice": "The previous attempt was interrupted by a harness restart, not by a bug in the approach. "
                                   "Read PROGRESS.md of the previous attempt and continue from its last commit."}
            self.tree.update(n, status="failed", failure="harness restarted while node was running", commit=commit,
                             diagnosis=diagnosis, finished_at=now_iso(), verdict="failed",
                             summary="FAILED: harness restarted while running (will retry)")
            self.executions.execution_phase(n, execution.get("phase", "implementation"), state="interrupted", error="controller restarted")
            (nd / "FAILURE.md").write_text("harness restarted while node was running\n", encoding="utf-8")
        for n in self.tree.by_status("planned"):
            # planned nodes are re-launched as they are
            pass

    # main loop ------------------------------------------------------------------
    def research_checkpoint(self, force: bool = False) -> None:
        if not self.memory.enabled or self.stop_flag.is_set():
            return
        try:
            self.memory.sync(self.tree)
            if (self.cfg.search.max_wallclock_s
                    and now_ts() - self.started_ts >= self.cfg.search.max_wallclock_s):
                return  # save evidence, but do not start another model call after the budget
            if self.memory.reflect(self.maintainer, force=force):
                self.log("memory_updated", revision=self.memory.revision, path=str(self.memory.root))
            if self.research.enabled:
                # Research mode keeps one knowledge base: these ledgers are views of the wiki.
                insights, deadends = self.memory.ledger_views()
                atomic_write_text(self.cfg.insights_path, insights)
                atomic_write_text(self.cfg.deadends_path, deadends)
        except Exception as e:
            # A failed synthesis cannot invalidate completed experiments or publish partial knowledge.
            self.log("memory_failed", error=str(e))

    # wake queue ------------------------------------------------------------------
    def node_pending(self, node: Node) -> bool:
        """Is the task a waiting node waits for still queued or running? Polling only; no model is called."""
        from .worker import worker_jobs_pending, eval_pending_for
        if (node.worker.get("waiting") or {}).get("kind") == "worker_job":
            return worker_jobs_pending(self.cfg.nodes_dir / node.id)
        return eval_pending_for(self, node)

    def wake_waiting(self, wakes: dict, pool) -> int:
        """The wake queue: a waiting node whose task ended gets a thread to collect the result, analyse and
        finish (or to resume its worker session after a submitted job). Returns how many were woken."""
        woken = 0
        for n in self.scheduler.waiting():
            if n.id in wakes or self.stop_flag.is_set():
                continue
            try:
                pending = self.node_pending(n)
            except Exception as e:  # let run_node surface the failure on this node instead of polling forever
                self.log("wake_check_failed", node=n.id, error=str(e))
                pending = False
            if pending:
                continue
            self.log("task_wake", node=n.id, kind=(n.worker.get("waiting") or {}).get("kind", "evaluation"),
                     waited_s=_waited_seconds(n))
            wakes[n.id] = pool.submit(self._safe_run_node, n)
            woken += 1
        return woken

    def _heartbeat_loop(self) -> None:
        while not self.stop_flag.is_set() and getattr(self, "_status", "running") != "finished":
            try:
                self.write_state()
            except Exception:
                pass
            time.sleep(30)

    def run(self) -> str:
        with self.executions.controller_lease():
            return self._run()

    def _run(self) -> str:
        cfg = self.cfg
        if self.setup.required() and not self.setup.complete():
            # Nothing runs before the human (or, for routine questions, the proxy) has confirmed the setup.
            self._status, self._stop_reason = "finished", "setup_required"
            self.write_state()
            self.log("setup_required", setup=str(cfg.setup_dir))
            return "setup_required"
        self._status = "running"
        # Explicit resume permits another attempt after a failed THINK call. A scientific
        # stop stays persisted until rsi continue explicitly extends the study.
        self.tree.meta.pop("research_error", None)
        self.executions.migrate(self.tree)
        self.tree.save()
        self.write_state()
        threading.Thread(target=self._heartbeat_loop, daemon=True, name="heartbeat").start()
        self.ensure_root()
        self.check_protocol()
        self.recover()
        s = cfg.search
        futures: dict[str, Future] = {}   # implementations holding a worker slot
        wakes: dict[str, Future] = {}     # woken waiting nodes: collecting a result or resuming after a job
        stop_reason: str | None = None
        parallel = 1 if self.research.enabled else max(1, s.max_parallel)
        # Waiting nodes hold no slot; when their task ends they need a thread of their own.
        workers = parallel + max(1, getattr(s, "max_waiting", 1)) + 1
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="node") as pool:
            # relaunch planned nodes left over from a previous run
            for n in self.tree.by_status("planned"):
                futures[n.id] = pool.submit(self._safe_run_node, n)
            while True:
                for table in (futures, wakes):
                    for nid, f in list(table.items()):
                        if f.done():
                            table.pop(nid)
                self.research_checkpoint(force=self.research.enabled or self.scheduler.consecutive_without_best() >= s.patience)
                try:
                    self.check_protocol()  # an evaluator edited mid-run (e.g. by ops) must not mix scores
                except Exception as e:
                    self.log("protocol_check_failed", error=str(e))
                if self.stop_flag.is_set():
                    stop_reason = "interrupted"
                if stop_reason is None:
                    stop_reason = self.scheduler.stop_reason()
                    if stop_reason:
                        self.log("stop_condition", reason=stop_reason, in_flight=len(futures),
                                 waiting=len(self.scheduler.waiting()))
                if stop_reason is None and not futures and not wakes:
                    self.maybe_run_ops()
                # Results that are already pending are collected even after a budget stop: they were paid for.
                self.wake_waiting(wakes, pool)
                if stop_reason is None:
                    launched = 0
                    while len(futures) < parallel and self.scheduler.can_schedule():
                        node = self.scheduler.next_node()
                        if node is None:
                            break
                        futures[node.id] = pool.submit(self._safe_run_node, node)
                        launched += 1
                    if not futures and not wakes and launched == 0 and not self.scheduler.waiting():
                        stop_reason = ("interrupted" if self.stop_flag.is_set() else self.scheduler.stop_reason()) or (
                            "exhausted" if self.scheduler.can_launch() else "max_nodes")
                        self.log("stop_condition", reason=stop_reason)
                # An interrupt leaves waiting nodes to the next `rsi run`; a budget stop still collects them.
                if stop_reason and not futures and not wakes and (self.stop_flag.is_set() or not self.scheduler.waiting()):
                    break
                self.write_state()
                time.sleep(3.0)
        self._stop_reason = stop_reason
        # Compile remaining search evidence before any final/confirmation evaluation.
        self.research_checkpoint(force=True)
        self._status = "finishing"
        self.write_state()
        self.finish(stop_reason or "unknown")
        self._status = "finished"
        self.write_state()
        self.render()
        return stop_reason or "unknown"

    def maybe_run_ops(self) -> None:
        """Two consecutive evaluator failures with no research cause -> hand the problem to the ops agent once."""
        if not self.cfg.ops.auto:
            return
        recent = self.tree.finished_in_order()[-2:]
        if len(recent) < 2 or not all(n.status == "failed" and (n.failure or "").startswith("official evaluation failed") for n in recent):
            return
        sig = "|".join(sorted(n.id for n in recent))
        if getattr(self, "_ops_done_for", None) == sig:
            return
        self._ops_done_for = sig
        evidence = ""
        for n in recent:
            nd = self.cfg.nodes_dir / n.id
            evidence += f"\n### node {n.id}: {n.failure}\n"
            for f in sorted((nd / "eval").glob("*.log")) if (nd / "eval").exists() else []:
                evidence += f"\n-- {f.name} --\n" + tail_text(f, 60, 6000)
        verdict = run_ops(self, f"Two consecutive nodes failed in the official evaluator: {recent[-1].failure}", evidence,
                          max_turns=self.cfg.ops.max_turns, timeout_s=self.cfg.ops.timeout_s)
        if verdict.get("fixed") and verdict.get("retry_failed_nodes"):
            for n in recent:
                d = dict(n.diagnosis or {})
                d.update(retry=True, advice=(d.get("advice", "") + "\n\nThe evaluator infrastructure was repaired by the ops agent: " + str(verdict.get("summary", ""))))
                self.tree.update(n, diagnosis=d, attempt=min(n.attempt, self.cfg.search.max_retries))

    def _safe_run_node(self, node: Node) -> None:
        try:
            run_node(self, node)
        except Exception:
            self.log("node_crash", node=node.id, trace=traceback.format_exc()[-1500:])
            try:
                self.tree.update(node, status="failed", failure="harness exception (see events.jsonl)", finished_at=now_iso(),
                                 verdict="failed", diagnosis={"retry": False, "cause": "harness exception", "advice": ""})
            except Exception:
                pass

    # finish -------------------------------------------------------------------------
    def finish(self, reason: str) -> None:
        cfg = self.cfg
        best = self.tree.best()
        root = self.tree.get("root")
        final: dict[str, Any] = {"stop_reason": reason, "finished_at": now_iso(), "best": best.id if best else None,
                                 "elapsed_s": round(now_ts() - self.started_ts, 1)}
        prev = read_json(cfg.dir / "final.json", {}) or {}
        # Confirmation depends on the recoverable state of the study, not on which stop
        # condition happened to be checked first (a wall-clock stop can coincide with an
        # incomplete handoff or a failed THINK).
        faults = self.scheduler.pending_faults()
        if self.stop_flag.is_set() or reason == "interrupted":
            faults.append("interrupted")
        if reason in ("research_failed", "postprocess_failed", "runner_broken", "protocol_changed") and reason not in faults:
            faults.append(reason)
        final["faults"] = faults
        deferred = bool(faults)
        if deferred:
            final["note"] = ("Final confirmation deferred because the research controller did not finish normally: "
                             + ", ".join(faults) + ". Resume the experiment to recover before confirmation.")
            self.log("final_eval_deferred", reason=reason, faults=faults)
        elif best is not None and prev.get("best") == best.id and prev.get("best_commit") == best.commit and "best_final_score" in prev:
            final.update({k: prev[k] for k in ("best_final_score", "best_final_metrics", "root_final_score") if k in prev})
            final["best_commit"] = best.commit
            final["note"] = "final evaluation reused: best node unchanged since the previous finish"
            self.log("final_eval_reused", node=best.id)
        elif best is not None and best.id != "root" and cfg.task.final_seedset and _cap_reached(cfg):
            final["note"] = f"final evaluation skipped: submission cap {cfg.hooks.max_submissions} reached (see SUBMISSIONS.md)"
            self.log("final_eval_skipped", reason="submission cap")
        elif best is not None and best.id != "root" and cfg.task.final_seedset:
            final["best_commit"] = best.commit
            wt = cfg.worktrees_dir / best.id
            if wt.exists():
                try:
                    k = max(1, int(cfg.task.final_top_k))
                    ranked = sorted(self.tree.scored(), key=lambda n: (-n.score if self.tree.higher_is_better() else n.score))
                    top = [n for n in ranked if n.id != "root"][:k]
                    ranking = []
                    for n in top:
                        self.log("final_eval", node=n.id, seedset=cfg.task.final_seedset)
                        mm = run_eval(cfg, cfg.worktrees_dir / n.id, cfg.task.final_seedset, cfg.nodes_dir / n.id / "eval", tag="final",
                                      owner=f"{cfg.name}/{n.id}")
                        final_score = score_of(cfg, mm)
                        if final_score is None:
                            raise EvalError(f"final evaluator produced no finite numeric '{cfg.task.score_key}' for {n.id}")
                        ranking.append({"node": n.id, "official": n.score, "final": final_score})
                    final["ranking"] = ranking
                    fb = min(ranking, key=lambda r: (-(r["final"] or -1e18) if self.tree.higher_is_better() else (r["final"] if r["final"] is not None else 1e18)))
                    final["best_by_final"] = fb["node"]
                    m = read_json(cfg.nodes_dir / fb["node"] / "eval" / f"metrics.{cfg.task.final_seedset}.final.json") or {}
                    final["best_final_score"] = fb["final"]
                    final["best_final_metrics"] = {k2: v for k2, v in m.items() if k2 not in ("per_seed", "per_item")}
                    if cfg.task.final_eval_root:
                        rm = run_eval(cfg, cfg.repo_dir, cfg.task.final_seedset, cfg.nodes_dir / "root" / "eval", tag="final")
                        root_final_score = score_of(cfg, rm)
                        if root_final_score is None:
                            raise EvalError(f"final baseline evaluator produced no finite numeric '{cfg.task.score_key}'")
                        final["root_final_score"] = root_final_score
                    self.log("final_eval_done", best=final["best_final_score"], root=final.get("root_final_score"),
                             best_by_final=final.get("best_by_final"))
                except EvalError as e:
                    final["final_eval_error"] = str(e)
                    self.log("final_eval_failed", error=str(e))
        if not deferred and best is not None and best.id == "root" and cfg.task.final_seedset and cfg.task.final_eval_root \
                and "best_final_score" not in final:
            # A baseline that remains best still needs a final confirmation result.
            try:
                rm = run_eval(cfg, cfg.repo_dir, cfg.task.final_seedset, cfg.nodes_dir / "root" / "eval",
                              tag="final", owner=f"{cfg.name}/root")
                final_score = score_of(cfg, rm)
                if final_score is None:
                    raise EvalError("final baseline evaluator produced no finite score")
                final.update(best_commit=best.commit, best_final_score=final_score, root_final_score=final_score,
                             best_final_metrics={k:v for k,v in rm.items() if k not in ("per_seed", "per_item")},
                             note="Baseline remains the selection winner; no candidate superiority was selected.")
            except EvalError as e:
                final["final_eval_error"] = str(e)
        atomic_write_json(cfg.dir / "final.json", final)
        _write_report(self, final)
        if cfg.hooks.narrative:
            try:
                write_narrative(self, cfg.hooks.narrative_language)
            except Exception as e:
                self.log("narrative_failed", error=str(e))
        self.log("finished", reason=reason, best=best.id if best else None, best_score=best.score if best else None)
        if cfg.hooks.on_finish:
            cmd = cfg.hooks.on_finish.format(exp_dir=str(cfg.dir))
            self.log("hook_on_finish", cmd=cmd)
            try:
                import subprocess
                subprocess.run(cmd, shell=True, cwd=str(Path(__file__).resolve().parents[1]), timeout=1800)
            except Exception as e:
                self.log("hook_failed", error=str(e))


def _waited_seconds(node: Node) -> float | None:
    since = (node.worker.get("waiting") or {}).get("since")
    try:
        import datetime as _dt
        return round(now_ts() - _dt.datetime.fromisoformat(since).timestamp(), 1) if since else None
    except (TypeError, ValueError):
        return None


def _paired_noise(m1: dict, m2: dict) -> float | None:
    from .evidence import paired_noise, bootstrap_noise
    value = bootstrap_noise(m1, m2) or paired_noise(m1, m2)
    return value[0] if value is not None else None


def _cap_reached(cfg: ExperimentCfg) -> bool:
    from .logistics import submissions
    return bool(cfg.hooks.max_submissions) and len(submissions(cfg)) >= cfg.hooks.max_submissions


def _harness_commit() -> str:
    try:
        return gitops.git(["rev-parse", "--short", "HEAD"], cwd=Path(__file__).resolve().parents[1], check=False)
    except Exception:
        return ""


def _short(v: Any) -> str:
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    return s if len(s) <= 100 else s[:97] + "..."


def _populate_repo(cfg: ExperimentCfg) -> None:
    repo, task = cfg.repo_dir, cfg.task_dir
    repo.mkdir(parents=True, exist_ok=True)
    starter = task / cfg.task.starter_dir
    if starter.exists():
        shutil.copytree(starter, repo, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".venv"))
    ev = task / cfg.task.eval_dir
    if ev.exists():
        shutil.copytree(ev, repo / "eval", dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    docs = repo / "docs"
    docs.mkdir(exist_ok=True)
    for d in cfg.task.docs:
        src = task / d
        if src.exists():
            shutil.copy2(src, docs / src.name)
    brief = task / cfg.task.brief
    if brief.exists():
        shutil.copy2(brief, repo / "TASK.md")
    gi = repo / ".gitignore"
    if not gi.exists():
        gi.write_text("__pycache__/\n*.pyc\nmetrics*.json\n*.log\n.venv/\nruns/\n" + "".join(f"/{d}\n" for d in cfg.task.link_dirs), encoding="utf-8")
    link_task_dirs(cfg, repo)


def link_task_dirs(cfg: ExperimentCfg, root: Path) -> None:
    """Symlink large read-only task-pack directories (data, models) into a repo or worktree."""
    for d in cfg.task.link_dirs:
        src = cfg.task_dir / d
        dst = root / d
        if src.exists() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.symlink_to(src, target_is_directory=True)


def _write_report(o: Orchestrator, final: dict[str, Any]) -> None:
    cfg, tree = o.cfg, o.tree
    best = tree.best()
    root = tree.get("root")
    lines = [f"# pi-rsi report: {cfg.name}", "",
             f"- task: {cfg.task.name}; metric `{cfg.task.score_key}` ({'higher' if cfg.task.higher_is_better else 'lower'} is better)",
             f"- worker: {cfg.runner.kind}:{cfg.runner.model} ({cfg.runner.effort}); utility: {cfg.utility.kind}:{cfg.utility.model}",
             f"- search: width_root={cfg.search.width_root} width={cfg.search.width} depth={cfg.search.depth} max_nodes={cfg.search.max_nodes} parallel={cfg.search.max_parallel} patience={cfg.search.patience}",
             f"- stop reason: {final.get('stop_reason')}; elapsed {human_duration(final.get('elapsed_s'))}"
             + (f"; pending faults (final confirmation deferred): {', '.join(final['faults'])}" if final.get("faults") else ""),
             f"- baseline (root) official score: {fmt_score(root.score)}",
             f"- best node: `{best.id if best else '-'}` official score {fmt_score(best.score if best else None)}",
             ]
    if "best_final_score" in final:
        lines.append(f"- held-out `{cfg.task.final_seedset}` seed set: best {fmt_score(final['best_final_score'])} vs baseline {fmt_score(final.get('root_final_score'))}")
    if cfg.task.reference_scores:
        lines.append("- reference scores: " + ", ".join(f"{k} {fmt_score(v)}" for k, v in cfg.task.reference_scores.items()))
    costs = o.costs
    if costs:
        lines.append("- cost: " + "; ".join(f"{k}: {v['calls']} calls, ${v['cost_usd']:.2f}, {human_duration(v['seconds'])}" for k, v in costs.items()))
    lines += ["", "## Best path", ""]
    if best:
        for n in tree.ancestors(best.id) + [best]:
            lines.append(f"- `{n.id}` {fmt_score(n.score)} — {n.title}: {n.summary}")
    lines += ["", "## All nodes", "", "| id | parent | depth | status | verdict | score | Δparent | title | duration |", "|---|---|---|---|---|---|---|---|---|"]
    for n in sorted(tree.nodes.values(), key=lambda n: (n.id != "root", n.id)):
        lines.append(f"| {n.id} | {n.parent or '-'} | {n.depth} | {n.status} | {n.verdict or '-'} | {fmt_score(n.score)} | {fmt_score(n.delta_parent)} | {n.title} | {human_duration(n.duration_s)} |")
    lines += ["", "## Insights", "", read_text(cfg.insights_path).strip() or "(none)", "", "## Dead ends", "",
              read_text(cfg.deadends_path).strip() or "(none)", ""]
    (cfg.dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
