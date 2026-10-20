"""Proxy alignment: what the official evaluation measures, how good the development and forecast proxies
are, and the harness fixes found by the CASMI26 newflow audit (2026-10-15)."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from pi_rsi import gitops, proxy
from pi_rsi.runner import make_runner
from pi_rsi.setup import _section, waiting_questions
from pi_rsi.tree import Node, Tree
from pi_rsi.util import atomic_write_json
from pi_rsi.worker import _check_tuning_budget, _delivery, tuning_trials


def rows(path, *items):
    path.write_text("".join(json.dumps(x) + "\n" for x in items))
    return path


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def repo(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("fixture\n")
    gitops.init_repo(root)
    return root


class TuningTrialTests(unittest.TestCase):
    def test_reruns_events_and_reregistrations_are_not_extra_trials(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            # n004: four trials plus a correction row
            self.assertEqual(tuning_trials(rows(d / "a", *[{"trial": i} for i in (1, 2)],
                                                {"trial": 2, "event": "pre-fitting command correction"},
                                                *[{"trial": i} for i in (3, 4)])), 4)
            # n016: trial 2 attempted three times
            self.assertEqual(tuning_trials(rows(d / "b", {"trial": 1}, {"trial": 2}, {"trial": 2, "attempt": 2},
                                                {"trial": 2, "attempt": 3}, *[{"trial": i} for i in (3, 4, 5, 6)])), 6)
            # n019: a failure event and re-registrations of unexecuted trials
            self.assertEqual(tuning_trials(rows(d / "c", *[{"trial": i} for i in range(1, 7)],
                                                {"event": "trial_failed", "trial": 2},
                                                *[{"trial": i, "supersedes_unexecuted_registration": True}
                                                  for i in (3, 4, 5, 6)])), 6)
            # rows without a number each count; garbage lines are ignored
            (d / "e").write_text('{"configuration": "a"}\n{"configuration": "b"}\nnot json\n')
            self.assertEqual(tuning_trials(d / "e"), 2)

    def test_an_overrun_is_a_recorded_deviation_not_a_failure(self):
        with tempfile.TemporaryDirectory() as d:
            nd = Path(d)
            rows(nd / "TUNING.jsonl", *[{"trial": i} for i in range(1, 5)])
            node = Node("n001", "root", 1, "t", "h", worker={"research": {"tuning_budget": {"max_trials": 3}}})
            tree = Mock(update=lambda n, **c: [setattr(n, k, v) for k, v in c.items()])
            orch = SimpleNamespace(tree=tree, log=Mock())
            deviation = _check_tuning_budget(orch, node, nd)
            self.assertIn("4 distinct trials", deviation)
            self.assertEqual(node.worker["protocol_deviation"], deviation)
            orch.log.assert_called_once()
            self.assertEqual(_check_tuning_budget(orch, node, nd), deviation)
            orch.log.assert_called_once()  # recorded once, not on every verification
            node.worker["research"]["tuning_budget"]["max_trials"] = 4
            self.assertIsNone(_check_tuning_budget(orch, node, nd))


class WorktreeTests(unittest.TestCase):
    def test_prune_removes_large_ignored_files_only(self):
        with tempfile.TemporaryDirectory() as d:
            wt = repo(Path(d) / "wt")
            (wt / ".gitignore").write_text("runs/\ndata\n")
            (wt / "code.py").write_text("x = 1\n" * 100)
            gitops.commit_all(wt, "code")
            (wt / "runs" / "pilot").mkdir(parents=True)
            (wt / "runs" / "pilot" / "features.f16").write_bytes(b"0" * 5000)
            (wt / "runs" / "small.log").write_text("ok")
            outside = Path(d) / "big.bin"
            outside.write_bytes(b"1" * 5000)
            os.symlink(outside, wt / "data")
            removed = gitops.prune_ignored(wt, 1000)
            self.assertEqual(removed, [("runs/pilot/features.f16", 5000)])
            self.assertTrue((wt / "runs" / "small.log").exists())
            self.assertTrue(outside.exists() and (wt / "data").is_symlink())
            self.assertTrue((wt / "code.py").exists())


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.wt = repo(root / "wt")
        (self.wt / "model.py").write_text("ENABLED = False\n")
        self.base = gitops.commit_all(self.wt, "parent") or gitops.head(self.wt)
        (self.wt / "model.py").write_text("ENABLED = True\n")
        (self.wt / "component.py").write_text("def score(): return 1\n")
        self.active = gitops.commit_all(self.wt, "component on")
        (self.wt / "model.py").write_text("ENABLED = False\n")
        (self.wt / "gate_report.md").write_text("dev gates failed\n")
        self.off = gitops.commit_all(self.wt, "switch off after dev gates")
        self.nd = root / "node"
        self.nd.mkdir()
        self.node = Node("n009", "n007", 1, "t", "h", commit=self.off, worker={})
        updates = lambda n, **c: [setattr(n, k, v) for k, v in c.items()]
        self.orch = SimpleNamespace(cfg=SimpleNamespace(research=SimpleNamespace(measure_active=True)),
                                    tree=Mock(update=updates), log=Mock())

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_component_delivered_off_is_measured_on(self):
        atomic_write_json(self.nd / "DELIVERY.json", {"component": "off", "active_commit": self.active,
                                                      "dev_delta": 0.004, "dev_sem": 0.003, "reason": "class-2 fell"})
        commit = _delivery(self.orch, self.node, self.nd, self.wt, self.base)
        self.assertEqual(commit, gitops.head(self.wt))
        self.assertEqual(self.node.commit, commit)
        self.assertEqual((self.wt / "model.py").read_text(), "ENABLED = True\n")
        self.assertFalse((self.wt / "gate_report.md").exists())  # exactly the active tree
        self.assertEqual(git(self.wt, "rev-parse", f"{commit}^{{tree}}"), git(self.wt, "rev-parse", f"{self.active}^{{tree}}"))
        self.assertEqual(git(self.wt, "status", "--porcelain"), "")
        record = self.node.worker["delivery"]
        self.assertEqual((record["measured"], record["active_commit"], record["worker_commit"], record["dev_delta"]),
                         ("active", self.active, self.off, 0.004))

    def test_off_without_a_valid_active_commit_measures_the_delivery(self):
        atomic_write_json(self.nd / "DELIVERY.json", {"component": "off", "active_commit": "deadbeef"})
        self.assertEqual(_delivery(self.orch, self.node, self.nd, self.wt, self.base), self.off)
        self.assertEqual(self.node.worker["delivery"]["measured"], "delivered")
        self.assertIn("not on this branch", self.node.worker["delivery"]["note"])
        self.assertEqual((self.wt / "model.py").read_text(), "ENABLED = False\n")

    def test_on_none_undeclared_and_disabled_policy_measure_the_delivery(self):
        for data, expected in (({"component": "on"}, "on"), ({"component": "none"}, "none"), (None, "undeclared")):
            (self.nd / "DELIVERY.json").unlink(missing_ok=True)
            if data:
                atomic_write_json(self.nd / "DELIVERY.json", data)
            self.assertEqual(_delivery(self.orch, self.node, self.nd, self.wt, self.base), self.off)
            self.assertEqual(self.node.worker["delivery"]["component"], expected)
        self.orch.cfg.research.measure_active = False
        atomic_write_json(self.nd / "DELIVERY.json", {"component": "off", "active_commit": self.active})
        self.assertEqual(_delivery(self.orch, self.node, self.nd, self.wt, self.base), self.off)


class LedgerTests(unittest.TestCase):
    def tree(self, root):
        tree = Tree(root / "tree.json")
        tree.add(Node("root", None, 0, "baseline", "", status="done", score=0.30,
                      metrics={"submission_sha256": "a"}))
        specs = [  # id, parent, score, sha, delivery, forecast
            ("n001", "root", 0.35, "b", {"component": "on", "dev_delta": 0.04}, 0.03),
            ("n002", "n001", 0.35, "b", {"component": "off", "dev_delta": 0.002}, 0.005),
            ("n003", "n001", 0.34, "c", {"component": "off", "measured": "active", "dev_delta": 0.003}, 0.004),
            ("n004", "n001", 0.35, "b", {"component": "none"}, 0.006)]
        for i, (nid, parent, score, sha, delivery, forecast) in enumerate(specs, 1):
            p = tree.nodes[parent]
            tree.add(Node(nid, parent, p.depth + 1, nid, "", status="done", score=score, finished_order=i,
                          delta_parent=round(score - p.score, 6), metrics={"submission_sha256": sha},
                          worker={"delivery": delivery, "proposal": {"expected_delta": forecast}}))
        return tree

    def test_ledger_counts_unchanged_outputs_agreement_and_forecast_misses(self):
        with tempfile.TemporaryDirectory() as d:
            data = proxy.ledger(self.tree(Path(d)))
            s = data["summary"]
            self.assertEqual(s["measured"], 4)
            self.assertEqual(s["unchanged"], ["n002", "n004"])
            self.assertEqual(s["measured_switched_on"], ["n003"])
            self.assertEqual((s["dev_official_pairs"], s["dev_official_sign_agreement"]), (2, 1))
            self.assertEqual((s["forecasts"], s["forecast_misses"], s["forecast_miss_streak"]), (4, 3, 3))

    def test_observations_reach_the_ledger_views(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            cfg = SimpleNamespace(dir=d, name="fixture")
            with self.assertRaises(ValueError):
                proxy.add_observation(d, "  ")
            proxy.add_observation(d, "Kaggle public LB of the n001 notebook", node="n001",
                                  metric="kaggle_public_lb", value=0.228)
            with (d / proxy.OBSERVATIONS).open("a") as f:
                f.write("garbage\n")
            self.assertEqual(len(proxy.observations(d)), 1)
            tree = self.tree(d)
            text = proxy.context(cfg, tree)
            self.assertIn("kaggle_public_lb 0.228", text)
            self.assertIn("Official output identical to the parent", text)
            proxy.write(cfg, tree)
            self.assertIn("| n003 | n001 |", (d / "PROXY.md").read_text())
            self.assertEqual(json.loads((d / "proxy.json").read_text())["observations"][0]["value"], 0.228)


class SetupViewTests(unittest.TestCase):
    def test_proxy_validity_section_and_waiting_questions(self):
        review = "# Review\n## Proxy validity\nClasses are balanced locally.\n### Dev level\n296 queries.\n## Risks\nx\n"
        self.assertEqual(_section(review, "Proxy validity"), "Classes are balanced locally.\n### Dev level\n296 queries.")
        self.assertEqual(_section(review, "Missing"), "")
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.assertEqual(waiting_questions(d), [])
            atomic_write_json(d / "setup" / "setup.json", {"questions": [
                {"id": "a", "question": "decided?", "importance": "routine"},
                {"id": "k002_setup", "question": "evaluate disabled nodes?", "importance": "critical"}],
                "decisions": {"a": {"answer": "yes"}}})
            self.assertEqual([q["id"] for q in waiting_questions(d)], ["k002_setup"])


class RunnerTests(unittest.TestCase):
    def test_exit_zero_after_an_api_error_is_a_failure(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            script = d / "agent.py"
            script.write_text("#!/usr/bin/env python3\nimport json\n"
                              "print(json.dumps({'type': 'end', 'stopReason': 'error'}))\n")
            script.chmod(0o755)
            res = make_runner("script", str(script), "low").run_agent("hi", cwd=d, log_path=d / "log.jsonl",
                                                                     max_turns=1, timeout_s=30, idle_timeout_s=30)
            self.assertEqual(res.exit_code, 0)
            self.assertFalse(res.ok)
            self.assertEqual(res.error, "model API error after retries")


class SkippedEvaluationTests(unittest.TestCase):
    """A node that declares no new component gets no official evaluation, and a restart never measures it."""

    def setUp(self):
        from tests.test_research_loop import make_cfg
        from pi_rsi.orchestrator import Orchestrator
        self.Orchestrator = Orchestrator
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = make_cfg(Path(self.tmp.name))
        self.cfg.memory.enabled = False
        self.cfg.search.root_eval = False
        self.orch = Orchestrator(self.cfg, verbose=False)
        self.orch.ensure_root()
        root = self.orch.tree.get("root")
        self.orch.tree.update(root, score=1.0, metrics={"score": 1.0})
        self.node = self.orch.tree.add(Node("n001", "root", 1, "diagnostic", "Measure headroom only.", kind="debug",
                                            status="planned", base_commit=root.commit,
                                            worker={"research": {"tuning_budget": {"seconds": 30, "max_trials": 2}}}))
        self.orch.tree._counter = 1
        self.nd = self.cfg.nodes_dir / "n001"

        def implement(prompt, cwd, **kw):
            Path(kw["log_path"]).write_text('{"type": "end"}\n')
            (Path(cwd) / "diagnostic.py").write_text("print('headroom report')\n")
            self.nd.mkdir(parents=True, exist_ok=True)
            (self.nd / "IMPLEMENTATION.md").write_text("# Implementation n001\n## What I built\nA diagnostic only.\n")
            atomic_write_json(self.nd / "DELIVERY.json", {"component": "none", "reason": "diagnostic only"})
            return SimpleNamespace(ok=True, exit_code=0, error="", duration_s=1.0, num_turns=1, tool_calls=1,
                                   cost_usd=0.0, session_id=None, usage={})
        self.orch.worker_runner = Mock(run_agent=Mock(side_effect=implement))
        self.orch.research.analyze = Mock()
        self.orch.utility.audit = Mock(side_effect=AssertionError("no LLM audit without an official result"))
        self.orch.utility.diagnose = Mock(side_effect=AssertionError("no failure diagnosis"))

    def tearDown(self):
        self.tmp.cleanup()

    def run_node(self, orch, node):
        from unittest.mock import patch
        from pi_rsi.worker import run_node
        with patch("pi_rsi.worker.run_eval", side_effect=AssertionError("must not evaluate")):
            run_node(orch, node)

    def test_no_component_is_documented_without_an_official_evaluation(self):
        self.run_node(self.orch, self.node)
        node = self.node
        self.assertEqual((node.status, node.verdict, node.score), ("done", "not_measured", None), node.failure)
        self.assertIsNone(self.orch.research.analyze.call_args.args[1])  # analysed without official metrics
        journal = self.orch.executions.read(node)
        self.assertEqual(journal["measurement"]["state"], "skipped")
        self.assertEqual(journal["documentation"]["state"], "complete")
        self.assertEqual(json.loads((self.nd / "eval" / "comparison.json").read_text())["verdict"], "not_measured")
        self.assertFalse(self.orch.scheduler.expandable(node))
        self.assertEqual(self.orch.tree.best_id(), "root")
        self.assertEqual(self.orch.scheduler.consecutive_without_best(), 0)  # depth-1 nodes never count as stalls
        self.assertIn("evaluation_skipped", self.cfg.events_path.read_text())
        self.assertIn("n001", proxy.ledger(self.orch.tree)["summary"]["not_measured"])
        with self.assertRaises(ValueError):
            self.orch.executions.begin_attempt(node)

    def test_restart_during_documentation_resumes_only_the_documentation(self):
        self.orch.research.analyze.side_effect = RuntimeError("analysis service unavailable")
        self.run_node(self.orch, self.node)
        self.assertEqual(self.node.status, "incomplete")
        restarted = self.Orchestrator(self.cfg, verbose=False)
        node = restarted.tree.get("n001")
        self.assertEqual(node.measurement["state"], "skipped")
        restarted.recover()
        self.assertEqual(node.status, "planned")
        self.assertTrue(node.worker["resume_postprocess"])
        restarted.research.analyze = Mock()
        restarted.utility.audit = Mock(side_effect=AssertionError("no LLM audit without an official result"))
        restarted.worker_runner = Mock(run_agent=Mock(side_effect=AssertionError("must not implement again")))
        self.run_node(restarted, node)
        self.assertEqual((node.status, node.verdict), ("done", "not_measured"), node.failure)
        self.assertEqual(restarted.research.analyze.call_count, 1)
        self.assertEqual(len(restarted.executions.read(node)["attempts"]), 1)

    def test_policy_off_measures_as_before(self):
        self.cfg.research.skip_unmeasured = False
        self.orch.utility.diagnose = Mock(return_value={"retry": False, "cause": "evaluator stub", "advice": ""})
        from unittest.mock import patch
        from pi_rsi.worker import run_node
        # The official evaluation is submitted first (begin_eval) and collected afterwards (run_eval).
        with patch("pi_rsi.worker.begin_eval", side_effect=RuntimeError("evaluator reached")), \
                patch("pi_rsi.worker.run_eval", side_effect=RuntimeError("evaluator reached")):
            run_node(self.orch, self.node)
        self.assertIn("evaluator reached", self.node.failure)


class JobDaemonTests(unittest.TestCase):
    def test_idle_daemon_exits(self):
        from pi_rsi import jobs
        with tempfile.TemporaryDirectory() as d:
            old = {k: os.environ.get(k) for k in ("RSI_JOBS_DIR", "RSI_JOBD_IDLE_EXIT_S")}
            os.environ.update(RSI_JOBS_DIR=d, RSI_JOBD_IDLE_EXIT_S="0.5")
            try:
                done = threading.Event()
                t = threading.Thread(target=lambda: (jobs.run_daemon([], poll_s=0.05), done.set()), daemon=True)
                started = time.monotonic()
                t.start()
                self.assertTrue(done.wait(10), "idle daemon did not exit")
                self.assertLess(time.monotonic() - started, 10)
                self.assertFalse(jobs.daemon_alive())
            finally:
                for k, v in old.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
