"""Best-first scheduler with depth/width caps. Backtracking is implicit: when the best node is exhausted (all
width slots used) or too deep, the next-best expandable node anywhere in the tree gets the slot."""
from __future__ import annotations

from typing import Any

from .tree import Node, Tree
from .util import now_iso, now_ts


class Scheduler:
    def __init__(self, orch):
        self.o = orch
        self.cfg = orch.cfg
        self.tree: Tree = orch.tree

    # helpers ---------------------------------------------------------------
    def cap(self, node: Node) -> int:
        return self.cfg.search.width_root if node.id == "root" else self.cfg.search.width

    def will_retry(self, n: Node) -> bool:
        if n.status != "failed":
            return False
        if any(m.retry_of == n.id for m in self.tree.nodes.values()):
            return False  # already retried
        return bool(n.diagnosis.get("retry")) and n.attempt <= self.cfg.search.max_retries

    def counted_children(self, node: Node) -> list[Node]:
        out = []
        for c in self.tree.children(node.id):
            if c.status == "abandoned":
                continue
            if c.status == "failed" and (self.will_retry(c) or any(m.retry_of == c.id for m in self.tree.nodes.values())):
                continue  # the retry (existing or pending) represents this slot
            out.append(c)
        return out

    def expandable(self, node: Node) -> bool:
        return (node.status == "done" and node.score is not None and node.depth < self.cfg.search.depth
                and len(self.counted_children(node)) < self.cap(node))

    def in_flight(self) -> list[Node]:
        return self.tree.by_status("planned", "running", "evaluating")

    def launched_count(self) -> int:
        return len([n for n in self.tree.non_root() if n.status != "abandoned"])

    def consecutive_without_best(self) -> int:
        k = 0
        for n in reversed(self.tree.finished_in_order()):
            if n.status == "done" and n.delta_best is not None and n.delta_best > 0:
                break
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
    def stop_reason(self) -> str | None:
        s = self.cfg.search
        best = self.tree.best()
        if s.target_score is not None and best is not None and self.tree.better(best.score, s.target_score):
            return "target_reached"
        if s.max_wallclock_s and (now_ts() - self.o.started_ts) > s.max_wallclock_s:
            return "wallclock"
        finished = [n for n in self.tree.non_root() if n.status in ("done", "failed") and not self.will_retry(n)]
        if len(finished) >= s.max_nodes:
            return "max_nodes"
        if self.runner_broken():
            return "runner_broken"
        if self.consecutive_without_best() >= s.patience:
            return "patience"
        return None

    def can_launch(self) -> bool:
        return self.launched_count() < self.cfg.search.max_nodes

    # node creation -------------------------------------------------------------
    def pick_parent(self) -> Node | None:
        cands = [n for n in self.tree.nodes.values() if self.expandable(n)]
        if not cands:
            return None
        hib = self.tree.higher_is_better()
        cands.sort(key=lambda n: ((-n.score if hib else n.score), n.depth, n.id))
        return cands[0]

    def next_node(self) -> Node | None:
        """Create and persist the next planned node, or return None if nothing can be scheduled right now."""
        with self.tree.lock:
            # retries first: they are cheap to decide and keep the tree honest
            for n in list(self.tree.nodes.values()):
                if self.will_retry(n):
                    return self._make_retry(n)
            parent = self.pick_parent()
            if parent is None:
                return None
            unused = [i for i in range(len(parent.proposals)) if i not in parent.proposals_used]
            need = self.cap(parent) - len(self.counted_children(parent))
        if not unused:
            # planner call happens outside the tree lock (it is an LLM call)
            try:
                props = self.o.utility.plan_children(parent, max(1, need))
            except Exception as e:
                self.o.log("planner_failed", parent=parent.id, error=str(e))
                props = []
            with self.tree.lock:
                if not props:  # mark parent as exhausted so we do not loop on it
                    self.tree.update(parent, proposals_used=list(range(len(parent.proposals))) + [-1])
                    return None
                self.tree.update(parent, proposals=parent.proposals + props)
                unused = [i for i in range(len(parent.proposals)) if i not in parent.proposals_used]
                if not unused:
                    return None
        with self.tree.lock:
            unused = [i for i in range(len(parent.proposals)) if i not in parent.proposals_used]
            if not unused or not self.expandable(parent):
                return None
            i = unused[0]
            prop = parent.proposals[i]
            self.tree.update(parent, proposals_used=parent.proposals_used + [i])
            node = Node(id=self.tree.new_id(), parent=parent.id, depth=parent.depth + 1, title=prop["title"],
                        hypothesis=prop["hypothesis"], kind=prop.get("type", "idea"), base_commit=parent.commit,
                        worker={"proposal": prop})
            self.tree.add(node)
            self.o.log("node_planned", node=node.id, parent=parent.id, title=node.title, kind=node.kind)
            return node

    def _make_retry(self, failed: Node) -> Node:
        parent = self.tree.get(failed.parent)
        base = failed.commit if failed.commit and failed.commit != failed.base_commit else (failed.base_commit or parent.commit)
        advice = failed.diagnosis.get("advice", "")
        advice += (f"\n\nThe previous attempt was node `{failed.id}`; its notes are in `{self.cfg.nodes_dir / failed.id}` "
                   f"(PROGRESS.md, FAILURE.md). Its last commit is your starting point.")
        node = Node(id=self.tree.new_id(), parent=failed.parent, depth=failed.depth, title=failed.title,
                    hypothesis=failed.hypothesis, kind=failed.kind, base_commit=base, attempt=failed.attempt + 1,
                    retry_of=failed.id, advice=advice, worker={"proposal": failed.worker.get("proposal", {})})
        self.tree.add(node)
        self.o.log("node_retry", node=node.id, retry_of=failed.id, attempt=node.attempt)
        return node
