#!/usr/bin/env python3
"""Regression tests for scheduler planner-exhaustion handling (bug #3)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pi_rsi.config import SearchCfg
from pi_rsi.scheduler import PLANNER_EXHAUSTED, Scheduler
from pi_rsi.tree import Node, Tree


def _proposal(title: str) -> dict:
    return {"title": title, "hypothesis": f"try {title}", "type": "idea"}


class FakeUtility:
    def __init__(self, by_parent=None, default=None):
        self.by_parent = by_parent or {}
        self.default = default if default is not None else []
        self.calls: list[str] = []

    def plan_children(self, parent, n):
        self.calls.append(parent.id)
        if parent.id in self.by_parent:
            val = self.by_parent[parent.id]
            return val() if callable(val) else val
        return self.default() if callable(self.default) else self.default


class TestSchedulerExhaustion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tree_path = Path(self.tmp.name) / "tree.json"
        self.tree = Tree(self.tree_path, meta={"higher_is_better": True})
        self.cfg = SimpleNamespace(
            search=SearchCfg(width_root=2, width=2, depth=4, max_nodes=20, max_retries=1, patience=99),
            nodes_dir=Path(self.tmp.name),
        )
        self.utility = FakeUtility()
        self.orch = SimpleNamespace(cfg=self.cfg, tree=self.tree, utility=self.utility, log=lambda *a, **k: None)
        self.sched = Scheduler(self.orch)

    def tearDown(self):
        self.tmp.cleanup()

    def _add(self, **kw) -> Node:
        defaults = dict(parent=None, depth=0, title="n", hypothesis="", status="done", score=0.0)
        defaults.update(kw)
        node = Node(**defaults)
        self.tree.add(node)
        # keep new_id() from colliding with pre-seeded n001/n002/...
        if node.id.startswith("n") and node.id[1:].isdigit():
            self.tree._counter = max(self.tree._counter, int(node.id[1:]))
        return node

    def _two_done_branches(self, *, high_proposals=None, high_used=None, low_proposals=None, low_used=None):
        """Root filled to width_root; two scored children, higher-is-better so n001 is picked first."""
        self._add(id="root", parent=None, depth=0, title="root", score=0.0)
        n001 = self._add(id="n001", parent="root", depth=1, title="high", score=10.0,
                         proposals=list(high_proposals or []), proposals_used=list(high_used or []))
        n002 = self._add(id="n002", parent="root", depth=1, title="low", score=5.0,
                         proposals=list(low_proposals or []), proposals_used=list(low_used or []))
        return n001, n002

    def test_empty_planner_skips_to_other_valid_branch(self):
        n001, n002 = self._two_done_branches(low_proposals=[_proposal("from-low")])
        self.utility.by_parent["n001"] = []
        self.assertTrue(self.sched.expandable(n001))
        self.assertTrue(self.sched.expandable(n002))

        node = self.sched.next_node()
        self.assertIsNotNone(node)
        self.assertEqual(node.parent, "n002")
        self.assertEqual(node.title, "from-low")
        self.assertEqual(self.utility.calls, ["n001"])
        self.assertTrue(self.sched.planner_exhausted(n001))
        self.assertFalse(self.sched.expandable(n001))
        self.assertIn(PLANNER_EXHAUSTED, n001.proposals_used)

        # further scheduling must not re-call the planner on the exhausted parent
        node2 = self.sched.next_node()
        self.assertIsNone(node2)  # n002 width still open but its one proposal is used; planner default is empty
        self.assertEqual(self.utility.calls.count("n001"), 1)

    def test_all_exhausted_returns_none_without_unbounded_planner(self):
        n001, n002 = self._two_done_branches()
        self.utility.default = []

        node = self.sched.next_node()
        self.assertIsNone(node)
        self.assertTrue(self.sched.planner_exhausted(n001))
        self.assertTrue(self.sched.planner_exhausted(n002))
        self.assertFalse(self.sched.expandable(n001))
        self.assertFalse(self.sched.expandable(n002))
        self.assertIsNone(self.sched.pick_parent())
        first_calls = list(self.utility.calls)
        self.assertEqual(sorted(first_calls), ["n001", "n002"])

        for _ in range(8):
            self.assertIsNone(self.sched.next_node())
        self.assertEqual(self.utility.calls, first_calls)

    def test_exhaustion_marker_honored(self):
        n001, n002 = self._two_done_branches(
            high_used=[PLANNER_EXHAUSTED],
            low_proposals=[_proposal("from-low")],
        )
        self.assertFalse(self.sched.expandable(n001))
        self.assertTrue(self.sched.expandable(n002))
        self.assertEqual(self.sched.pick_parent().id, "n002")

        node = self.sched.next_node()
        self.assertIsNotNone(node)
        self.assertEqual(node.parent, "n002")
        self.assertEqual(self.utility.calls, [])  # marked parent is never planned again

        # only the marked node remains expandable-looking besides width: still not expandable
        n002.proposals_used = list(n002.proposals_used) + [PLANNER_EXHAUSTED]
        self.tree.update(n002, proposals_used=n002.proposals_used)
        self.assertFalse(self.sched.expandable(n002))
        self.assertIsNone(self.sched.pick_parent())
        self.assertIsNone(self.sched.next_node())
        self.assertEqual(self.utility.calls, [])


if __name__ == "__main__":
    unittest.main()
