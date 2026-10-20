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


class TestPriorityScheduling(unittest.TestCase):
    """Parent choice = exploit + explore + information; depth rounds exploit, breadth rounds explore."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tree = Tree(Path(self.tmp.name) / "tree.json", meta={"higher_is_better": True})
        self.cfg = SimpleNamespace(
            search=SearchCfg(width_root=2, width=5, depth=4, max_nodes=20, max_retries=1, patience=4, breadth_after=1),
            nodes_dir=Path(self.tmp.name))
        self.utility = FakeUtility()
        self.orch = SimpleNamespace(cfg=self.cfg, tree=self.tree, utility=self.utility, log=lambda *a, **k: None)
        self.sched = Scheduler(self.orch)

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, nid, parent, depth, score, *, order, status="done", proposals=None):
        node = Node(nid, parent, depth, nid, "", status=status, score=score, finished_order=order,
                    finished_at=f"2026-10-20T00:00:{order:02d}", proposals=list(proposals or []))
        self.tree.add(node)
        self.tree._counter = max(self.tree._counter, int(nid[1:]) if nid != "root" else 0)
        return node

    def explored_best_and_fresh_sibling(self):
        """n001 is the best but its three children all failed; n002 scored lower and was never expanded."""
        self.add("root", None, 0, 0.0, order=0)
        self.add("n001", "root", 1, 10.0, order=1, proposals=[_proposal("from-high")])
        self.add("n002", "root", 1, 5.0, order=2, proposals=[_proposal("from-low")])
        for i in (3, 4, 5):
            self.add(f"n00{i}", "n001", 2, None, order=i, status="failed")

    def test_breadth_round_leaves_the_exhausted_best_for_an_unexplored_branch(self):
        self.explored_best_and_fresh_sibling()
        self.assertEqual(self.sched.phase(), "breadth")  # three results without a new best
        ranking = self.sched.priorities("breadth")
        self.assertGreater(ranking["n002"]["total"], ranking["n001"]["total"])
        self.assertEqual((ranking["n001"]["explored"], ranking["n001"]["fail"]), (3, 1.0))
        self.assertGreater(ranking["n002"]["novelty"], 0)  # results arrived since n002 was last touched
        node = self.sched.next_node()
        self.assertEqual((node.parent, node.title), ("n002", "from-low"))
        self.assertEqual(node.worker["dispatch"]["phase"], "breadth")

    def test_depth_round_follows_the_best_branch(self):
        self.explored_best_and_fresh_sibling()
        self.cfg.search.breadth_after = 99
        self.assertEqual(self.sched.phase(), "depth")
        ranking = self.sched.priorities("depth")
        self.assertGreater(ranking["n001"]["total"], ranking["n002"]["total"])
        node = self.sched.next_node()
        self.assertEqual((node.parent, node.worker["dispatch"]["phase"]), ("n001", "depth"))

    def test_best_descendant_outranks_its_explored_parent_in_a_depth_round(self):
        self.add("root", None, 0, 0.0, order=0)
        self.add("n001", "root", 1, 10.0, order=1, proposals=[_proposal("a")])
        self.add("n002", "root", 1, 5.0, order=2, proposals=[_proposal("b")])
        self.add("n003", "n001", 2, 12.0, order=3, proposals=[_proposal("c")])
        self.cfg.search.breadth_after = 99
        order = [n.id for n, _ in self.sched.ranked("depth")]
        self.assertEqual(order[0], "n003")   # same subtree best as n001, nothing explored below it yet

    def test_equal_scores_fall_back_to_breadth_first(self):
        self.add("root", None, 0, 0.0, order=0)
        self.add("n001", "root", 1, 5.0, order=1, proposals=[_proposal("a")])
        self.add("n002", "root", 1, 5.0, order=2, proposals=[_proposal("b")])
        self.add("n003", "n001", 2, 4.0, order=3, proposals=[_proposal("c")])
        self.cfg.search.breadth_after = 99
        self.assertEqual(self.sched.ranked("depth")[0][0].id, "n002")  # fewer explored descendants wins the tie

    def test_phase_alternates_every_k_nodes_or_adapts_to_a_stall(self):
        self.add("root", None, 0, 0.0, order=0)
        self.add("n001", "root", 1, 10.0, order=1)
        self.add("n002", "root", 1, 5.0, order=2)
        self.cfg.search.phase_k = 1
        self.assertEqual(self.sched.phase(), "depth")      # 2 launched // 1 is even
        self.add("n003", "n001", 2, 1.0, order=3)
        self.assertEqual(self.sched.phase(), "breadth")    # 3 launched
        self.cfg.search.phase_k = 0
        self.cfg.search.breadth_after = 2
        self.assertEqual(self.sched.phase(), "depth")      # one stalled result below depth 1
        n = self.add("n004", "n001", 2, 1.0, order=4)
        self.assertEqual(self.sched.phase(), "breadth")    # two
        self.tree.update(n, delta_best=1.0)
        self.assertEqual(self.sched.phase(), "depth")      # a new best resets the stall
        self.cfg.search.phase_adaptive = False
        self.tree.update(n, delta_best=None)
        self.assertEqual(self.sched.phase(), "depth")


if __name__ == "__main__":
    unittest.main()
