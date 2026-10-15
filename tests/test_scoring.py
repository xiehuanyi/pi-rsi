"""LLM-free score validation and concurrent completion regressions."""
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pi_rsi.evaluator import score_of
from pi_rsi.scheduler import Scheduler
from pi_rsi.tree import Node, Tree


class ScoreTests(unittest.TestCase):
    def test_only_finite_numeric_scores(self):
        cfg = SimpleNamespace(task=SimpleNamespace(score_key="score"))
        for value in (None, True, False, "bad", [], {}, float("nan"),
                      float("inf"), -float("inf"), "NaN", "Infinity", "-Infinity", 10 ** 400):
            with self.subTest(value=str(value)[:40]):
                self.assertIsNone(score_of(cfg, {"score": value}))
        for value in (0, -1, 1.5, "2.5"):
            self.assertEqual(score_of(cfg, {"score": value}), float(value))
        self.assertIsNone(score_of(cfg, {}))


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tree = Tree(Path(self.tmp.name) / "tree.json")
        self.tree.add(Node("root", None, 0, "baseline", "", status="done", score=0))

    def node(self, node_id, score):
        node = Node(node_id, "root", 2, node_id, "", status="evaluating", score=score)
        self.tree.add(node)
        return node

    def test_later_worse_completion_is_not_a_new_best(self):
        slow = self.node("n001", 5)
        fast = self.node("n002", 10)
        # Both scores exist before either audit finishes. Neither is published yet.
        self.assertEqual(self.tree.best_id(), "root")
        with patch("pi_rsi.tree.now_iso", return_value="2026-01-01T00:00:00+00:00"):
            self.tree.complete(fast)
            self.tree.complete(slow)
        self.assertEqual(fast.delta_best, 10)
        self.assertEqual(slow.delta_best, -5)
        self.assertEqual(self.tree.best_id(), fast.id)
        self.assertEqual([n.id for n in self.tree.finished_in_order()], [fast.id, slow.id])
        loaded = Tree.load(self.tree.path)
        self.assertEqual([n.id for n in loaded.finished_in_order()], [fast.id, slow.id])
        scheduler = Scheduler(SimpleNamespace(cfg=SimpleNamespace(), tree=loaded))
        self.assertEqual(scheduler.consecutive_without_best(), 1)

    def test_lower_is_better(self):
        self.tree.meta["higher_is_better"] = False
        fast = self.node("n002", -10)
        slow = self.node("n001", -5)
        self.tree.complete(fast)
        self.tree.complete(slow)
        self.assertEqual(fast.delta_best, 10)
        self.assertEqual(slow.delta_best, -5)

    def test_parallel_publication_has_one_serial_completion_order(self):
        nodes = [self.node(f"n{i:03}", i) for i in range(1, 9)]
        barrier = threading.Barrier(len(nodes))
        errors = []
        def finish(node):
            try:
                barrier.wait(timeout=5)
                self.tree.complete(node)
            except Exception as exc:
                errors.append(exc)
        threads = [threading.Thread(target=finish, args=(node,)) for node in nodes]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
        self.assertFalse(errors)
        best = 0
        for node in self.tree.finished_in_order():
            self.assertEqual(node.delta_best, node.score - best)
            best = max(best, node.score)
        self.assertEqual(len({n.finished_order for n in nodes}), len(nodes))

    def test_legacy_nodes_sort_before_new_completions(self):
        legacy = self.node("n003", 3)
        legacy.status = "done"
        legacy.finished_at = "2026-01-01T00:00:00+00:00"
        fresh = self.node("n001", 4)
        self.tree.complete(fresh)
        self.assertEqual(self.tree.finished_in_order(), [legacy, fresh])


if __name__ == "__main__":
    unittest.main()
