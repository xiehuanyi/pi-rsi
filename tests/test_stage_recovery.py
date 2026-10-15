"""Completed experiments must never be rerun to repair their notes or audit."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from pi_rsi import gitops
from pi_rsi.measurement import measurement_record
from pi_rsi.orchestrator import Orchestrator
from pi_rsi.tree import Node
from pi_rsi.util import atomic_write_json
from pi_rsi.worker import run_node
from tests.test_research_loop import make_cfg


class StageRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = make_cfg(Path(self.tmp.name))
        self.cfg.memory.enabled = False
        self.cfg.search.root_eval = False
        self.cfg.search.max_nodes = 1  # recovery must work even in the last allocated slot
        self.orch = Orchestrator(self.cfg, verbose=False)
        self.orch.ensure_root()
        root = self.orch.tree.get("root")
        self.orch.tree.update(root, score=1.0, metrics={"score": 1.0})
        self.wt = self.cfg.worktrees_dir / "n001"
        gitops.add_worktree(self.cfg.repo_dir, self.wt, "node/n001", root.commit)
        (self.wt / "agent.py").write_text("def agent(obs):\n    return {'candidate': 1}\n")
        commit = gitops.commit_all(self.wt, "candidate")
        self.node = Node("n001", "root", 1, "candidate", "A fixed artifact.",
                         status="analyzing", commit=commit, base_commit=root.commit, score=1.2)
        self.orch.tree.add(self.node)
        self.orch.tree._counter = 1
        self.nd = self.cfg.nodes_dir / self.node.id
        run = self.nd / "eval/run.validation"
        run.mkdir(parents=True)
        (run / "model.pt").write_bytes(b"frozen checkpoint")
        (run / "predictions.npy").write_bytes(b"frozen predictions")
        metrics = {"score": 1.2, "model_sha256": hashlib.sha256((run / "model.pt").read_bytes()).hexdigest(),
                   "predictions_sha256": hashlib.sha256((run / "predictions.npy").read_bytes()).hexdigest(),
                   "_eval": {"run_dir": str(run)}}
        self.metrics_path = self.nd / "eval/metrics.validation.json"
        atomic_write_json(self.metrics_path, metrics)
        self.node.worker = {"evaluation_validated": measurement_record(self.cfg, self.node, commit, 1.2),
                            "resume_postprocess": True}
        self.orch.tree.save()
        self.audit = {"summary": "Scoped measured gain.", "verdict": "improved",
                      "claim_check": {"consistent": True, "note": ""},
                      "insights": ["A scoped observation."], "deadends": []}
        self.orch.utility.audit = Mock(return_value=self.audit)
        self.orch.utility.diagnose = Mock(side_effect=AssertionError("no implementation retry diagnosis"))
        self.orch.research.analyze = Mock()
        self.orch.worker_runner = Mock(run_agent=Mock(side_effect=AssertionError("must not implement/train")))
        self.before = {p: p.read_bytes() for p in [self.metrics_path, run / "model.pt", run / "predictions.npy"]}

    def tearDown(self):
        self.tmp.cleanup()

    def assert_scientific_artifacts_unchanged(self):
        for path, content in self.before.items():
            self.assertEqual(path.read_bytes(), content, str(path))
        self.assertEqual(len(self.orch.tree.non_root()), 1)
        self.orch.worker_runner.run_agent.assert_not_called()
        self.orch.utility.diagnose.assert_not_called()

    def test_analysis_audit_and_publish_recover_on_same_node(self):
        self.orch.research.analyze.side_effect = [ValueError("invalid research observations"), None]
        self.orch.utility.audit.side_effect = [ValueError("invalid audit format"), self.audit]
        tag = gitops.tag
        calls = []

        def fail_once(*args, **kwargs):
            calls.append(args)
            if len(calls) == 1:
                raise OSError("temporary publication failure")
            return tag(*args, **kwargs)

        with patch("pi_rsi.worker.run_eval", side_effect=AssertionError("must not score/train")), \
                patch("pi_rsi.worker.gitops.tag", side_effect=fail_once):
            run_node(self.orch, self.node)
        self.assertEqual(self.node.status, "done", self.node.failure)
        self.assertEqual(self.node.worker["postprocess"]["attempts"], {"analysis": 2, "audit": 2, "publish": 2})
        self.assertEqual(self.orch.research.analyze.call_count, 2)
        self.assertEqual(self.orch.utility.audit.call_count, 2)
        self.assertEqual(self.orch.scheduler.launched_count(), 1)
        self.assert_scientific_artifacts_unchanged()
        events = [json.loads(line) for line in self.cfg.events_path.read_text().splitlines()]
        self.assertEqual(len([e for e in events if e["event"] == "postprocess_retry"]), 3)
        self.assertFalse([e for e in events if e["event"] in ("node_retry", "node_start", "eval_done")])

    def test_exhausted_analysis_is_incomplete_and_explicit_resume_does_not_remeasure(self):
        self.orch.research.analyze.side_effect = RuntimeError("analysis service unavailable")
        with patch("pi_rsi.worker.run_eval", side_effect=AssertionError("must not score/train")):
            run_node(self.orch, self.node)
        self.assertEqual(self.node.status, "incomplete")
        self.assertEqual(self.node.score, 1.2)
        self.assertEqual(self.orch.research.analyze.call_count, 2)
        self.assertEqual(self.orch.scheduler.stop_reason(), "postprocess_failed")
        self.assertFalse(self.orch.scheduler.will_retry(self.node))
        self.assertEqual(self.orch.tree.best_id(), "n001")  # valid measurement survives missing notes
        self.assert_scientific_artifacts_unchanged()
        restarted = Orchestrator(self.cfg, verbose=False)
        restarted.recover()
        node = restarted.tree.get("n001")
        self.assertEqual(node.status, "planned")
        self.assertTrue(node.worker["resume_postprocess"])
        restarted.research.analyze = Mock()
        restarted.utility.audit = Mock(return_value=self.audit)
        restarted.worker_runner = self.orch.worker_runner
        with patch("pi_rsi.worker.run_eval", side_effect=AssertionError("must not score/train")):
            run_node(restarted, node)
        self.assertEqual(node.status, "done", node.failure)
        self.assertEqual(len(restarted.tree.non_root()), 1)
        self.assert_scientific_artifacts_unchanged()

    def test_crash_after_audit_reuses_completed_stages(self):
        with patch("pi_rsi.worker._record_audit", side_effect=KeyboardInterrupt("simulated crash")), \
                patch("pi_rsi.worker.run_eval", side_effect=AssertionError("must not score/train")):
            with self.assertRaises(KeyboardInterrupt):
                run_node(self.orch, self.node)
        self.assertTrue((self.nd / "audit.json").exists())
        restarted = Orchestrator(self.cfg, verbose=False)
        restarted.recover()
        restarted.research.analyze = Mock(side_effect=AssertionError("reuse completed analysis"))
        restarted.utility.audit = Mock(side_effect=AssertionError("reuse completed audit"))
        restarted.worker_runner = self.orch.worker_runner
        node = restarted.tree.get("n001")
        with patch("pi_rsi.worker.run_eval", side_effect=AssertionError("must not score/train")):
            run_node(restarted, node)
        self.assertEqual(node.status, "done", node.failure)
        self.assert_scientific_artifacts_unchanged()

    def test_changed_measurement_is_rejected_without_replacement_experiment(self):
        metrics = json.loads(self.metrics_path.read_text())
        metrics["score_sem"] = .123  # same scalar, changed evidence must still be rejected
        atomic_write_json(self.metrics_path, metrics)
        self.node.status = "incomplete"
        self.orch.tree.save()
        restarted = Orchestrator(self.cfg, verbose=False)
        restarted.recover()
        node = restarted.tree.get("n001")
        self.assertEqual(node.status, "failed")
        self.assertEqual(node.diagnosis["phase"], "integrity")
        self.assertFalse(restarted.scheduler.will_retry(node))
        self.assertEqual(len(restarted.tree.non_root()), 1)
        self.orch.worker_runner.run_agent.assert_not_called()

    def test_analysis_cannot_change_the_evaluated_implementation(self):
        self.orch.research.analyze.side_effect = lambda *args: (self.wt / "agent.py").write_text("changed")
        with patch("pi_rsi.worker.run_eval", side_effect=AssertionError("must not score/train")):
            run_node(self.orch, self.node)
        self.assertEqual(self.node.status, "failed")
        self.assertEqual(self.node.diagnosis["phase"], "integrity")
        self.assertEqual(self.orch.research.analyze.call_count, 1)
        self.assertFalse(self.orch.scheduler.will_retry(self.node))
        self.assertEqual(len(self.orch.tree.non_root()), 1)


if __name__ == "__main__":
    unittest.main()
