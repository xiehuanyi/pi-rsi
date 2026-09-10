"""Search tree: nodes, persistence, and queries. The scheduler and orchestrator mutate it under `Tree.lock`."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

from .util import atomic_write_json, read_json, now_iso

STATUS_ORDER = ["planned", "running", "evaluating", "done", "failed", "abandoned"]


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
        return t

    def save(self) -> None:
        with self.lock:
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
        return [n for n in self.nodes.values() if n.score is not None and n.status == "done"]

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
        return sorted((n for n in self.non_root() if n.finished_at), key=lambda n: n.finished_at)

    def update(self, node: Node, **changes: Any) -> Node:
        with self.lock:
            for k, v in changes.items():
                setattr(node, k, v)
            self.save()
            return node
