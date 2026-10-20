"""Execution journal, independent of hypotheses and immutable measurements.

A hypothesis owns execution attempts. Implementation/evaluation recovery starts a
new attempt on that hypothesis; documentation recovery never starts an attempt.
The legacy Node.status/worker fields are compatibility projections, not admission
or measurement authority.
"""
from __future__ import annotations

import copy
import fcntl
from contextlib import contextmanager
from pathlib import Path

from .util import atomic_write_json, now_iso, read_json


class ExecutionStore:
    def __init__(self, cfg):
        self.cfg = cfg
        self.root = cfg.dir / "executions"

    def path(self, node):
        return self.root / f"{node.id}.json"

    def read(self, node):
        saved = read_json(self.path(node))
        if saved is not None:
            return saved
        if self.path(node).exists():
            raise ValueError(f"{node.id}: execution journal is unreadable; refusing to guess or rerun")
        measured = node.measurement_valid
        post = copy.deepcopy(node.documentation or node.worker.get("postprocess", {}))
        if node.status == "done":
            post.update(state="complete", phase="complete", analysis_complete=True, pending=False)
        elif measured and node.status in ("failed", "incomplete"):
            post.update(state="needs_attention", pending=True, phase=post.get("phase", "analysis"))
        state = "completed" if measured else ("failed" if node.status == "failed" else "pending")
        attempt = {"id": f"a{node.attempt:03d}", "ordinal": node.attempt, "source_node": node.id,
                   "state": state, "phase": "complete" if measured else "implementation",
                   "commit": node.commit, "started_at": node.started_at, "ended_at": node.finished_at,
                   "error": None if measured else node.failure}
        measurement = copy.deepcopy(node.measurement)
        if not measurement and node.worker.get("evaluation_validated"):
            measurement = {"state": "validated", **node.worker["evaluation_validated"]}
        return {"schema_version": 2, "node_id": node.id, "hypothesis_id": node.hypothesis_key,
                "attempts": [attempt] if node.id != "root" and node.status != "planned" else [],
                "active_attempt": attempt["id"] if node.id != "root" and node.status != "planned" else None,
                "execution": {"state": state, "phase": attempt["phase"]},
                "measurement": measurement, "documentation": post}

    @contextmanager
    def _locked(self, node):
        self.root.mkdir(parents=True, exist_ok=True)
        with self.path(node).with_suffix(".lock").open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    @contextmanager
    def controller_lease(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / ".controller.lock").open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as e:
                raise RuntimeError("another controller owns this experiment") from e
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def change(self, node, mutate):
        with self._locked(node):
            record = self.read(node)
            mutate(record)
            record["updated_at"] = now_iso()
            atomic_write_json(self.path(node), record)
            return record

    def migrate(self, tree):
        for node in tree.nodes.values():
            if not self.path(node).exists():
                self.change(node, lambda record: None)
        self.project(tree)
        for node in tree.nodes.values():
            record = self.read(node)
            if record["measurement"].get("state") == "validated" and "delta_best" not in record["measurement"]:
                self.change(node, lambda data, value=node.delta_best: data["measurement"].update(delta_best=value))

    def project(self, tree):
        """Rehydrate the tree's read model after a crash between journal/tree writes."""
        with tree.lock:
            self._project(tree)

    def _project(self, tree):
        for node in tree.nodes.values():
            record = read_json(self.path(node))
            if not record:
                continue
            node.documentation = copy.deepcopy(record["documentation"])
            measurement = record["measurement"]
            if measurement:
                node.measurement = copy.deepcopy(measurement)
            if measurement.get("state") == "validated":
                node.score = measurement["score"]
                node.commit = measurement["commit"]
                node.worker["evaluation_validated"] = {k: v for k, v in measurement.items() if k != "state"}
                if "delta_best" in measurement:
                    node.delta_best = measurement["delta_best"]
                elif node.delta_best is None:
                    previous = tree.best_excluding(node.id)
                    if previous:
                        node.delta_best = (node.score - previous.score) * (1 if tree.higher_is_better() else -1)
            execution, docs = record["execution"], record["documentation"]
            if measurement.get("state") == "invalid":
                node.status = "failed"
                node.diagnosis = {"retry": False, "phase": "integrity"}
            elif execution["state"] == "waiting":
                node.status = "waiting"  # its task is queued or running; no worker thread is attached
            elif execution["state"] == "running":
                node.status = "evaluating" if execution["phase"] == "evaluation" else "running"
            elif execution["state"] in ("failed", "interrupted"):
                node.status = "failed"
                node.failure = execution.get("error") or node.failure
                if not node.diagnosis:
                    node.diagnosis = {"retry": True, "phase": execution["phase"], "cause": node.failure or "Execution interrupted."}
            elif measurement.get("state") in ("validated", "skipped"):
                node.status = ("done" if docs.get("state") == "complete" else
                               "incomplete" if docs.get("state") == "needs_attention" else "analyzing")
                if docs.get("state") == "complete":
                    receipt = read_json(self.cfg.nodes_dir / node.id / "audit.json", {}) or {}
                    if isinstance(receipt.get("audit"), dict):
                        node.audit = receipt["audit"]
                        node.summary = node.audit.get("summary", node.summary)
                        node.verdict = node.audit.get("verdict", node.verdict)
                    node.finished_at = docs.get("completed_at") or node.finished_at

    def worker_seconds(self, node):
        return sum(a.get("worker_seconds", 0) for a in self.read(node)["attempts"])

    def worker_finished(self, node, seconds):
        def update(record):
            active = next(a for a in record["attempts"] if a["id"] == record["active_attempt"])
            # A session resumed after a submitted job adds to the same attempt's time.
            active["worker_seconds"] = active.get("worker_seconds", 0) + seconds
        return self.change(node, update)

    def begin_attempt(self, node):
        def begin(record):
            if record["measurement"].get("state") in ("validated", "stale", "skipped") or node.measurement_valid:
                raise ValueError("a measured hypothesis cannot start another execution attempt")
            if max([0, *[a["ordinal"] for a in record["attempts"]]]) >= self.cfg.search.max_retries + 1:
                raise ValueError("execution-attempt budget exhausted for this hypothesis")
            ordinal = max([node.attempt - 1, *[a["ordinal"] for a in record["attempts"]]]) + 1
            attempt = {"id": f"a{ordinal:03d}", "ordinal": ordinal, "source_node": node.id,
                       "state": "running", "phase": "implementation", "started_at": now_iso(),
                       "ended_at": None, "commit": node.commit, "error": None}
            record["attempts"].append(attempt)
            record["active_attempt"] = attempt["id"]
            record["execution"] = {"state": "running", "phase": "implementation"}
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / ".admission.lock").open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            records = [read_json(p) for p in self.root.glob("*.json")]
            used = len({(r["hypothesis_id"], a["ordinal"]) for r in records if r["node_id"] != "root" for a in r["attempts"]})
            limit = self.cfg.search.max_attempts if self.cfg.search.max_attempts is not None else self.cfg.search.max_nodes * (self.cfg.search.max_retries + 1)
            if used >= limit:
                raise ValueError("total execution-attempt budget exhausted")
            return self.change(node, begin)

    def execution_phase(self, node, phase, *, state="running", error=None):
        def update(record):
            record["execution"] = {"state": state, "phase": phase, "error": error}
            active = next((a for a in record["attempts"] if a["id"] == record["active_attempt"]), None)
            if active:
                active.update(phase=phase, state=state, commit=node.commit, error=error)
                if state in ("completed", "failed", "interrupted"):
                    active["ended_at"] = now_iso()
        return self.change(node, update)

    def measured(self, node, measurement):
        def update(record):
            previous = record["measurement"]
            if previous.get("state") == "validated" and previous != measurement:
                raise ValueError("validated measurement cannot be replaced by execution recovery")
            record["measurement"] = copy.deepcopy(measurement)
            record["execution"] = {"state": "completed", "phase": "measurement"}
            active = next((a for a in record["attempts"] if a["id"] == record["active_attempt"]), None)
            if active:
                active.update(state="completed", phase="measurement", commit=node.commit, ended_at=now_iso())
            record["documentation"].setdefault("state", "pending")
        return self.change(node, update)

    def document(self, node, documentation):
        return self.change(node, lambda record: record.update(documentation=copy.deepcopy(documentation)))

    def revise_measurement(self, node, measurement):
        """Explicit reevaluation only; preserve the old scientific record, not a recovery retry."""
        def update(record):
            record.setdefault("measurement_history", []).append(copy.deepcopy(record["measurement"]))
            record["measurement"] = copy.deepcopy(measurement)
            record["documentation"] = {"state": "pending", "phase": "analysis", "pending": True, "attempts": {}}
        return self.change(node, update)

    def invalidate(self, node, reason):
        return self.change(node, lambda record: record.update(measurement={"state": "invalid", "reason": reason}))

    def rebind_protocol(self, node, measurement):
        """Protocol bookkeeping only: adopt a legacy record, mark it stale or restore it.
        The measured score and artifacts never change here (re-measurement is `revise_measurement`)."""
        def update(record):
            previous = record["measurement"]
            if previous and any(previous.get(k) != measurement.get(k) for k in ("score", "commit", "metrics_sha256")):
                raise ValueError("protocol bookkeeping cannot change a measured result")
            record["measurement"] = copy.deepcopy(measurement)
        return self.change(node, update)

    def attempt_count(self, tree):
        # Legacy retry nodes remain as provenance, but share a logical hypothesis.
        identities = {(record["hypothesis_id"], a["ordinal"])
                      for node in tree.non_root() if node.status != "abandoned"
                      for record in [self.read(node)] for a in record["attempts"]}
        return len(identities)
