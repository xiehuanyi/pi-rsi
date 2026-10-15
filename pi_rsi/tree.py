"""Search tree: nodes, persistence, and queries. The scheduler and orchestrator mutate it under `Tree.lock`."""
from __future__ import annotations

import threading
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

from .util import atomic_write_json, read_json, now_iso

STATUS_ORDER = ["planned", "running", "evaluating", "analyzing", "incomplete", "done", "failed", "abandoned"]


@dataclass
class Node:
    id: str
    parent: str | None
    depth: int
    title: str
    hypothesis: str
    kind: str = "idea"                 # idea | debug | ablate | scale | baseline | retry
    status: str = "planned"
    created_at: str = field(default_factory=now_iso)
    started_at: str | None = None
    finished_at: str | None = None
    finished_order: int = 0             # persisted completion order; timestamps have only second precision
    branch: str | None = None
    base_commit: str | None = None
    commit: str | None = None
    score: float | None = None          # official score (harness-run evaluator, official seedset)
    metrics: dict[str, Any] = field(default_factory=dict)
    quick_score: float | None = None    # last quick-set score claimed by the worker (from its own eval run)
    delta_parent: float | None = None
    delta_best: float | None = None     # vs global best at the time the node finished
    proposals: list[dict[str, Any]] = field(default_factory=list)   # child hypotheses from the handoff/planner
    proposals_used: list[int] = field(default_factory=list)
    proposals_revision: str = ""       # wiki revision used to generate/review unused proposals
    attempt: int = 1
    retry_of: str | None = None
    failure: str | None = None
    diagnosis: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    verdict: str = ""                   # improved | no_change | worse | failed
    audit: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    cost_usd: float | None = None
    duration_s: float | None = None
    worker: dict[str, Any] = field(default_factory=dict)   # runner kind/model/effort used
    advice: str = ""                    # prepended to the worker prompt (from diagnoser on retries)
    human_note: str = ""                # async human comments (read from nodes/<id>/HUMAN.md)
    hypothesis_id: str | None = None    # stable scientific identity; old retry nodes share it
    measurement: dict[str, Any] = field(default_factory=dict)
    documentation: dict[str, Any] = field(default_factory=dict)

    @property
    def hypothesis_key(self):
        return self.hypothesis_id or self.id

    @property
    def measurement_valid(self):
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
            return False
        try:
            if not math.isfinite(self.score):
                return False
        except OverflowError:
            return False
        if self.measurement:
            return self.measurement.get("state") == "validated" and self.measurement.get("score", self.score) == self.score
        marker = self.worker.get("evaluation_validated", {})
        if marker:
            return marker.get("score") == self.score and marker.get("commit") == self.commit
        return self.status == "done"  # compatibility for pre-journal trees and baseline fixtures

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Node":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


class Tree:
    def __init__(self, path: Path, meta: dict[str, Any] | None = None):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.nodes: dict[str, Node] = {}
        self.meta: dict[str, Any] = meta or {}
        self._counter = 0

    # persistence ---------------------------------------------------------
    @classmethod
    def load(cls, path: Path) -> "Tree":
        data = read_json(path)
        if data is None:
            raise FileNotFoundError(path)
        t = cls(path, data.get("meta", {}))
        for nd in data.get("nodes", []):
            n = Node.from_dict(nd)
            t.nodes[n.id] = n
        t._counter = int(data.get("counter", len(t.nodes)))
        for n in t.nodes.values():
            previous, seen = n, set()
            while previous.retry_of in t.nodes and previous.id not in seen:
                seen.add(previous.id)
                previous = t.nodes[previous.retry_of]
            n.hypothesis_id = n.hypothesis_id or previous.hypothesis_key
            if not n.measurement and n.worker.get("evaluation_validated"):
                n.measurement = {"state": "validated", **n.worker["evaluation_validated"]}
            if not n.documentation and n.worker.get("postprocess"):
                n.documentation = dict(n.worker["postprocess"])
        return t

    def save(self) -> None:
        with self.lock:
            if self.path.exists() and self.meta.get("schema_version", 1) < 3:
                backup = self.path.with_name("tree.before-schema-v3.json")
                if not backup.exists():
                    backup.write_bytes(self.path.read_bytes())
            self.meta["schema_version"] = 3
            order = sorted(self.nodes.values(), key=lambda n: (n.id != "root", n.id))
            atomic_write_json(self.path, {
                "meta": self.meta,
                "counter": self._counter,
                "updated_at": now_iso(),
                "best": self.best_id(),
                "nodes": [n.to_dict() for n in order],
            })

    # construction --------------------------------------------------------
    def new_id(self) -> str:
        with self.lock:
            self._counter += 1
            return f"n{self._counter:03d}"

    def add(self, node: Node) -> Node:
        with self.lock:
            previous = self.nodes.get(node.retry_of)
            node.hypothesis_id = node.hypothesis_id or (previous.hypothesis_key if previous else node.id)
            self.nodes[node.id] = node
            self.save()
            return node

    def get(self, node_id: str) -> Node:
        return self.nodes[node_id]

    def children(self, node_id: str) -> list[Node]:
        return sorted((n for n in self.nodes.values() if n.parent == node_id), key=lambda n: n.id)

    def ancestors(self, node_id: str) -> list[Node]:
        """Path root -> parent (excluding the node itself)."""
        out = []
        cur = self.nodes[node_id].parent
        while cur is not None:
            n = self.nodes[cur]
            out.append(n)
            cur = n.parent
        return list(reversed(out))

    # queries -------------------------------------------------------------
    def higher_is_better(self) -> bool:
        return bool(self.meta.get("higher_is_better", True))

    def better(self, a: float | None, b: float | None) -> bool:
        """True if a is strictly better than b."""
        if a is None:
            return False
        if b is None:
            return True
        return a > b if self.higher_is_better() else a < b

    def scored(self) -> list[Node]:
        return [n for n in self.nodes.values() if n.measurement_valid]

    def best_excluding(self, node_id):
        candidates = [n for n in self.scored() if n.id != node_id]
        if not candidates:
            return None
        return (max if self.higher_is_better() else min)(candidates, key=lambda n: n.score)

    def hypotheses(self) -> list[Node]:
        """Canonical views; legacy execution-retry nodes remain addressable as provenance."""
        groups = {}
        for node in self.nodes.values():
            if node.status == "abandoned":
                continue
            groups.setdefault(node.hypothesis_key, []).append(node)
        direction = 1 if self.higher_is_better() else -1
        return [max(nodes, key=lambda n: (n.measurement_valid,
                                        direction * n.score if n.measurement_valid else float("-inf"),
                                        n.attempt, n.finished_order, n.id))
                for nodes in groups.values()]

    def best(self) -> Node | None:
        best = None
        for n in self.scored():
            if best is None or self.better(n.score, best.score):
                best = n
        return best

    def best_id(self) -> str | None:
        b = self.best()
        return b.id if b else None

    def by_status(self, *statuses: str) -> list[Node]:
        return sorted((n for n in self.nodes.values() if n.status in statuses), key=lambda n: n.id)

    def non_root(self) -> list[Node]:
        return [n for n in self.nodes.values() if n.id != "root"]

    def finished_in_order(self) -> list[Node]:
        return sorted((n for n in self.non_root() if n.finished_at), key=lambda n: (n.finished_order, n.finished_at))

    def complete(self, node: Node, **changes: Any) -> Node:
        """Publish a scored node and its improvement atomically, after slow auditing has finished."""
        with self.lock:
            if node.measurement_valid:
                delta = node.delta_best
            elif node.score is None:  # documented without an official measurement
                delta = None
            else:
                best = self.best_excluding(node.id)
                delta = node.score - best.score if best is not None and best.score is not None else None
                if delta is not None and not self.higher_is_better():
                    delta = -delta
            return self.update(node, **changes, status="done", delta_best=delta, finished_at=now_iso())

    def update(self, node: Node, **changes: Any) -> Node:
        with self.lock:
            if changes.get("status") in ("done", "failed", "incomplete") and changes["status"] != node.status:
                changes["finished_order"] = max((n.finished_order for n in self.nodes.values()), default=0) + 1
            for k, v in changes.items():
                setattr(node, k, v)
            self.save()
            return node
