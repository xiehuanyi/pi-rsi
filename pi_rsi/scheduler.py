"""Best-first scheduler with depth/width caps. Backtracking is implicit: when the best node is exhausted (all
width slots used) or too deep, the next-best expandable node anywhere in the tree gets the slot."""
from __future__ import annotations

from typing import Any

from .tree import Node, Tree
from .util import now_iso, now_ts

# Compatible sentinel stored in Node.proposals_used when the planner yields nothing
# further for this parent. Persisted trees already use -1 this way.
PLANNER_EXHAUSTED = -1


class Scheduler:
    def __init__(self, orch):
        self.o = orch
        self.cfg = orch.cfg
        self.tree: Tree = orch.tree

    # helpers ---------------------------------------------------------------
    @property
    def memory_revision(self) -> str:
        memory = getattr(self.o, "memory", None)
        return memory.revision if memory and memory.enabled else ""

    def research_turn(self) -> bool:
        memory = getattr(self.o, "memory", None)
        if not memory or not memory.enabled:
            return False
        every = self.cfg.memory.research_every
        return bool(every and ((self.launched_count() + 1) % every == 0
                              or self.consecutive_without_best() >= self.cfg.search.patience))

    @staticmethod
    def discriminating(prop: dict) -> bool:
        return (prop.get("type") in ("ablate", "debug") and bool(prop.get("research_question"))
                and bool(prop.get("prediction")) and bool(prop.get("falsifier")))

    def cap(self, node: Node) -> int:
        return self.cfg.search.width_root if node.id == "root" else self.cfg.search.width

    def will_retry(self, n: Node) -> bool:
        if n.status != "failed":
            return False
        if n.worker.get("evaluation_validated"):
            return False  # completion/integrity recovery must never create another experiment
        if any(m.retry_of == n.id for m in self.tree.nodes.values()):
            return False  # already retried
        journal = getattr(self.o, "executions", None)
        seconds = n.worker.get("research", {}).get("tuning_budget", {}).get("seconds", self.cfg.runner.node_timeout_s) if journal else None
        return (bool(n.diagnosis.get("retry")) and n.attempt <= self.cfg.search.max_retries
                and self.execution_count() + self.reserved_attempts() < self.attempt_limit()
                and (not journal or journal.worker_seconds(n) < seconds))

    def counted_children(self, node: Node) -> list[Node]:
        return [child for child in self.tree.hypotheses() if child.parent in self.tree.nodes
                and self.tree.get(child.parent).hypothesis_key == node.hypothesis_key]

    def planner_exhausted(self, node: Node) -> bool:
        return (PLANNER_EXHAUSTED in node.proposals_used
                and (not self.memory_revision or node.proposals_revision == self.memory_revision))

    def expandable(self, node: Node) -> bool:
        research = getattr(self.o, "research", None)
        if research and research.enabled:
            return node.measurement_valid and bool(node.commit) and node.depth < self.cfg.search.depth
        return (node.measurement_valid and node.depth < self.cfg.search.depth
                and len(self.counted_children(node)) < self.cap(node) and not self.planner_exhausted(node))

    def _mark_planner_exhausted(self, parent: Node, revision: str | None = None) -> None:
        used = list(range(len(parent.proposals)))
        if PLANNER_EXHAUSTED not in used:
            used.append(PLANNER_EXHAUSTED)
        self.tree.update(parent, proposals_used=used,
                         proposals_revision=self.memory_revision if revision is None else revision)

    def _unused_indices(self, parent: Node) -> list[int]:
        return [i for i in range(len(parent.proposals)) if i not in parent.proposals_used]

    def in_flight(self) -> list[Node]:
        return self.tree.by_status("planned", "running", "evaluating", "analyzing")

    def launched_count(self) -> int:
        return len({n.hypothesis_key for n in self.tree.non_root() if n.status != "abandoned"})

    def execution_count(self) -> int:
        journal = getattr(self.o, "executions", None)
        if journal:
            return journal.attempt_count(self.tree)
        return sum(max(n.attempt for n in self.tree.non_root() if n.hypothesis_key == key)
                   for key in {n.hypothesis_key for n in self.tree.non_root() if n.status != "abandoned"})

    def attempt_limit(self) -> int:
        value = getattr(self.cfg.search, "max_attempts", None)
        return value if value is not None else self.cfg.search.max_nodes * (self.cfg.search.max_retries + 1)

    def reserved_attempts(self) -> int:
        return sum(n.status == "planned" and not n.measurement_valid and not n.worker.get("resume_evaluation")
                   for n in self.tree.hypotheses() if n.id != "root")

    def can_schedule(self) -> bool:
        return self.can_launch() or any(self.will_retry(n) for n in self.tree.hypotheses())

    def consecutive_without_best(self) -> int:
        """Consecutive finished nodes (finish order) without a new global best. The root's own candidates (depth 1)
        are the breadth-first exploration layer and never count: siblings of the best finishing later are not stalls."""
        k = 0
        since = self.tree.meta.get("continue_from") or ""
        for n in reversed(self.tree.finished_in_order()):
            if since and (n.finished_at or "") < since:
                break  # nodes before the last `rsi continue` do not count as stalls
            if n.status == "done" and n.delta_best is not None and n.delta_best > 0:
                break
            if n.depth <= 1:
                continue
            if n.status in ("done", "failed"):
                k += 1
        return k

    def runner_broken(self) -> bool:
        """Three consecutive quick abnormal endings without any output means the agent runtime itself is broken."""
        k = 0
        for n in reversed(self.tree.finished_in_order()):
            if n.status == "failed" and (n.failure or "").startswith("worker ended abnormally") and (n.duration_s or 0) < 90:
                k += 1
                if k >= 3:
                    return True
                continue
            if n.status in ("done", "failed"):
                break
        return False

    # stop conditions ----------------------------------------------------------
    # Two independent questions: why dispatch stops (stop_reason) and what still needs
    # recovery before a final confirmation is allowed (pending_faults). A budget stop
    # must not hide a pending fault, and a fault must not be relabelled as a budget stop.
    def stop_reason(self) -> str | None:
        s = self.cfg.search
        if self.tree.meta.get("protocol_change"):
            return "protocol_changed"  # scores from two evaluation protocols are not comparable
        best = self.tree.best()
        if s.target_score is not None and best is not None and self.tree.better(best.score, s.target_score):
            return "target_reached"
        if s.max_wallclock_s and (now_ts() - self.o.started_ts) >= s.max_wallclock_s:
            return "wallclock"
        if s.max_gpu_hours and self.cfg.task.job_enabled:
            from .jobs import gpu_seconds
            if gpu_seconds(self.cfg.name + "/") / 3600.0 > s.max_gpu_hours:
                return "gpu_hours"
        if any(n.status == "incomplete" for n in self.tree.hypotheses()):
            return "postprocess_failed"  # resume the saved node; do not think around a missing handoff
        finished = [n for n in self.tree.hypotheses() if n.id != "root"
                    and n.status in ("done", "failed") and not self.will_retry(n)]
        if len(finished) >= s.max_nodes:
            return "max_nodes"
        if self.execution_count() >= self.attempt_limit() and not self.in_flight():
            return "max_attempts"
        if self.runner_broken():
            return "runner_broken"
        research = getattr(self.o, "research", None)
        if research and research.enabled:
            if self.tree.meta.get("research_error"):
                return "research_failed"
            if self.tree.meta.get("research_stop"):
                return "research_saturated"
            return None  # a score plateau is input to thinking, not automatic task completion
        memory = getattr(self.o, "memory", None)
        grace = self.cfg.memory.patience_grace if memory and memory.enabled else 0
        if self.consecutive_without_best() >= s.patience + grace:
            return "patience"
        return None

    def pending_faults(self) -> list[str]:
        """Recoverable conditions that block final confirmation, whatever stopped dispatch."""
        faults = []
        if self.tree.meta.get("protocol_change"):
            faults.append("protocol_changed")
        hypotheses = self.tree.hypotheses()
        if any(n.status == "incomplete" for n in hypotheses):
            faults.append("postprocess_failed")
        if any(n.status in ("planned", "running", "evaluating", "analyzing") for n in hypotheses):
            faults.append("unfinished_nodes")
        if self.tree.meta.get("research_error"):
            faults.append("research_failed")
        if self.runner_broken():
            faults.append("runner_broken")
        return faults

    def can_launch(self) -> bool:
        return (self.launched_count() < self.cfg.search.max_nodes
                and self.execution_count() + self.reserved_attempts() < self.attempt_limit())

    # node creation -------------------------------------------------------------
    def pick_parent(self) -> Node | None:
        cands = [n for n in self.tree.nodes.values() if self.expandable(n)]
        if not cands:
            return None
        # a human may pin the next expansions to one node (`rsi continue --from n004`)
        focus = self.tree.meta.get("focus")
        if focus:
            fn = self.tree.nodes.get(focus)
            if fn is not None and self.expandable(fn):
                return fn
        # breadth first at the root: every root candidate is launched before any deeper expansion
        root = self.tree.nodes.get("root")
        if root is not None and root in cands:
            return root
        if self.research_turn():
            research = [n for n in cands if any(self.discriminating(n.proposals[i])
                                               for i in self._unused_indices(n))]
            if research:
                cands = research
        hib = self.tree.higher_is_better()
        cands.sort(key=lambda n: ((-n.score if hib else n.score), n.depth, n.id))
        return cands[0]

    def next_node(self) -> Node | None:
        """Create and persist the next planned node, or return None if nothing can be scheduled right now."""
        with self.tree.lock:
            research = getattr(self.o, "research", None)
            if research and research.enabled and self.in_flight():
                return None
            # retries first: they are cheap to decide and keep the tree honest
            for n in self.tree.hypotheses():
                if self.will_retry(n):
                    return self._make_retry(n)
        if research and research.enabled:
            return research.next_node(self)
        # Skip planner-exhausted parents and try the next expandable node instead of
        # returning None (which would make the orchestrator stop the whole search).
        while True:
            with self.tree.lock:
                parent = self.pick_parent()
                if parent is None:
                    return None
                unused = self._unused_indices(parent)
                need = self.cap(parent) - len(self.counted_children(parent))
            revision = self.memory_revision
            stale = bool(revision and parent.proposals_revision != revision)
            if not unused or stale:
                # planner call happens outside the tree lock (it is an LLM call)
                try:
                    props = self.o.utility.plan_children(parent, max(1, need))
                except Exception as e:
                    self.o.log("planner_failed", parent=parent.id, error=str(e))
                    props = []
                with self.tree.lock:
                    if not props:
                        self._mark_planner_exhausted(parent, revision)
                        continue
                    # Keep historical proposals and their indices; retire only the unused queue.
                    used = list(range(len(parent.proposals))) if stale else [
                        i for i in parent.proposals_used if i != PLANNER_EXHAUSTED]
                    self.tree.update(parent, proposals=parent.proposals + props,
                                     proposals_used=used, proposals_revision=revision)
                    unused = self._unused_indices(parent)
                    if not unused:
                        self._mark_planner_exhausted(parent, revision)
                        continue
            with self.tree.lock:
                unused = self._unused_indices(parent)
                if not unused or not self.expandable(parent):
                    if not unused and not self.planner_exhausted(parent):
                        self._mark_planner_exhausted(parent)
                    continue
                i = unused[0]
                if self.research_turn():
                    i = next((j for j in unused if self.discriminating(parent.proposals[j])), i)
                prop = parent.proposals[i]
                self.tree.update(parent, proposals_used=parent.proposals_used + [i])
                node = Node(id=self.tree.new_id(), parent=parent.id, depth=parent.depth + 1, title=prop["title"],
                            hypothesis=prop["hypothesis"], kind=prop.get("type", "idea"), base_commit=parent.commit,
                            worker={"proposal": prop})
                self.tree.add(node)
                self.o.log("node_planned", node=node.id, parent=parent.id, title=node.title, kind=node.kind)
                return node

    def _make_retry(self, failed: Node) -> Node:
        advice = failed.diagnosis.get("advice", "")
        advice += (f"\n\nThis is a retry of execution attempt {failed.attempt} of the SAME hypothesis `{failed.hypothesis_key}`. "
                   f"Read its saved notes at `{self.cfg.nodes_dir / failed.id}`. Continue from its existing code; "
                   "do not count this recovery as a new research approach.")
        self.tree.update(failed, status="planned", attempt=failed.attempt + 1, finished_at=None,
                         advice=advice, worker={**failed.worker, "resume_implementation": True})
        self.o.log("execution_retry", node=failed.id, hypothesis=failed.hypothesis_key,
                   attempt=failed.attempt, new_hypotheses=0)
        return failed
