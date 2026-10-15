"""Setup decisions, the human-proxy's authority, harness verdicts and course correction."""
from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pi_rsi.config import SetupCfg
from pi_rsi.evidence import comparison
from pi_rsi.orchestrator import Orchestrator
from pi_rsi.runner import RunResult
from pi_rsi.tree import Node

from test_research_loop import extracted, make_cfg, prose

REVIEW = ("Risk: budgets are tight.\n"
          "Question: Should the evaluator split change? Options keep or change; I recommend keep.\n"
          "Question: How often should full reviews run? Options 5 or 3; I recommend 5.\n")
QUESTIONS = {"risks": ["Budgets are tight."], "questions": [
    {"id": "split", "question": "Should the evaluator split change?", "options": ["keep", "change"],
     "recommended": "keep", "rationale": "Protocol.", "importance": "critical", "category": "protocol",
     "quote": "Question: Should the evaluator split change? Options keep or change; I recommend keep."},
    {"id": "cadence", "question": "How often should full reviews run?", "options": ["5", "3"],
     "recommended": "5", "rationale": "Cost.", "importance": "routine", "category": "review_frequency",
     "quote": "Question: How often should full reviews run? Options 5 or 3; I recommend 5."}]}


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = make_cfg(Path(self.tmp.name))
        self.cfg.setup = SetupCfg(enabled=True, calibration_runs=0)
        self.orch = Orchestrator(self.cfg, verbose=False)
        self.orch.tree.add(Node("root", None, 0, "baseline", "", status="done", score=10, commit="root-code"))

    def tearDown(self):
        self.tmp.cleanup()

    def agents(self, *extractions, proxy_text="[cadence] answer: 3 because the notes ask for frequent checks.\n"):
        def run(prompt, **kwargs):
            name = "REVIEW.md" if prompt.startswith("You are the setup reviewer") else "PROXY.md"
            (kwargs["cwd"] / name).write_text(REVIEW if name == "REVIEW.md" else proxy_text)
            return RunResult(ok=True, exit_code=0)
        self.orch.research.runner = Mock(run_agent=Mock(side_effect=run))
        runner = Mock(ask_json=Mock(side_effect=[(r, RunResult(ok=True, exit_code=0)) for r in extractions]))
        self.orch.maintainer = SimpleNamespace(runner=runner, call_cfg=SimpleNamespace(timeout_s=30))
        return self.orch.research.runner

    def test_research_run_waits_for_a_confirmed_setup(self):
        self.assertEqual(self.orch.run(), "setup_required")
        self.assertEqual(json.loads((self.cfg.dir / "state.json").read_text())["stop_reason"], "setup_required")
        self.assertFalse(self.orch.tree.non_root())

    def test_first_setup_sends_critical_questions_to_the_human_even_in_yolo(self):
        self.cfg.setup.proxy = True
        cadence = {"answers": [{"id": "cadence", "answer": "3",
                                "quote": "[cadence] answer: 3 because the notes ask for frequent checks."}]}
        self.agents(QUESTIONS, cadence)
        self.assertEqual(self.orch.setup.run(), "awaiting_human")
        state = self.orch.setup.state()
        self.assertEqual(state["decisions"]["cadence"]["decided_by"], "human-proxy")  # routine: proxy may answer
        waiting = (self.cfg.setup_dir / "QUESTIONS.md").read_text()
        self.assertIn("practical_delta", waiting)  # critical harness question
        self.assertIn("split", waiting)            # protocol: human only
        self.assertEqual(self.orch.setup.run(answers={"practical_delta": "0.0002", "split": "keep"}), "complete")
        self.assertEqual(self.orch.setup.practical_delta(), 0.0002)
        self.assertIn("decided by human-proxy", (self.cfg.setup_dir / "SETUP.md").read_text())

    def test_proxy_answers_outside_the_options_are_not_recorded(self):
        self.cfg.setup.proxy = True
        bad = {"answers": [{"id": "cadence", "answer": "7", "quote": "[cadence] answer: 7 because."}]}
        self.agents(QUESTIONS, bad, bad, proxy_text="[cadence] answer: 7 because.\n")
        self.assertEqual(self.orch.setup.run(), "awaiting_human")
        self.assertNotIn("cadence", self.orch.setup.state()["decisions"])
        self.assertIn("cadence", (self.cfg.setup_dir / "QUESTIONS.md").read_text())

    def test_mid_run_questions_respect_authority_and_never_block_the_run(self):
        self.agents(QUESTIONS)
        self.orch.setup.run(accept_recommended=True)
        self.assertTrue(self.orch.setup.complete())
        self.cfg.setup.proxy = True
        proxy = self.agents({"answers": [{"id": "k001_setup", "answer": "3",
                                          "quote": "[k001_setup] answer: 3 because the human wants checks."}]},
                            proxy_text="[k001_setup] answer: 3 because the human wants checks.\n")
        self.orch.setup.raise_question({"id": "k001_setup", "kind": "choice", "question": "Review more often?",
            "options": ["5", "3"], "recommended": "3", "rationale": "Stalled.", "importance": "critical",
            "category": "review_frequency"}, raised_by="k001")
        self.assertEqual(self.orch.setup.state()["decisions"]["k001_setup"]["decided_by"], "human-proxy")
        self.orch.setup.raise_question({"id": "k002_setup", "kind": "choice", "question": "Raise the GPU budget?",
            "options": ["yes", "no"], "recommended": "yes", "rationale": "Stalled.", "importance": "critical",
            "category": "budget_cap"}, raised_by="k002")
        self.assertEqual(proxy.run_agent.call_count, 1)  # the budget cap never goes to the proxy
        self.assertIn("k002_setup", (self.cfg.setup_dir / "QUESTIONS.md").read_text())
        self.assertTrue(self.orch.setup.complete())    # the run continues with the current setup

    def test_calibration_measures_run_to_run_noise(self):
        self.cfg.setup.calibration_runs = 3
        with patch("pi_rsi.evaluator.run_eval", side_effect=[{"score": 10.2}, {"score": 9.8}]) as run_eval:
            cal = self.orch.setup.calibrate()
        self.assertEqual(run_eval.call_count, 2)
        self.assertEqual(cal["samples"], [10, 10.2, 9.8])
        self.assertAlmostEqual(cal["band"], 2 * 2 ** .5 * 0.2)


class VerdictTests(unittest.TestCase):
    def test_threshold_is_the_larger_of_measured_noise_and_practical_minimum(self):
        args = dict(score=10.5, parent_score=10.0, higher_is_better=True, fallback=1.0)
        self.assertEqual(comparison({}, {}, **args)["verdict"], "uncertain")  # heuristic band decides nothing
        calibration = {"band": 0.2, "runs": 3}
        self.assertEqual(comparison({}, {}, calibration=calibration, **args)["verdict"], "improved")
        judged = comparison({}, {}, calibration=calibration, practical_delta=1.0, **args)
        self.assertEqual((judged["verdict"], judged["threshold"]), ("no_change", 1.0))
        self.assertEqual(comparison({}, {}, calibration=calibration, **{**args, "score": 9.0})["verdict"], "worse")


class CourseCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = make_cfg(Path(self.tmp.name))
        self.cfg.search.patience = 2
        self.cfg.setup.course_k = 0  # i.e. search.patience
        self.orch = Orchestrator(self.cfg, verbose=False)
        self.orch.tree.add(Node("root", None, 0, "baseline", "", status="done", score=10, commit="root-code"))
        for i, delta in enumerate((0.5, 0.0, -0.01), 1):
            node = self.orch.tree.add(Node(f"n00{i}", "root", 1, "x", "", status="running", score=10 + delta,
                                           commit=f"c{i}", delta_best=delta))
            self.orch.tree.update(node, status="done", finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
        self.orch.tree._counter = 3

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_gains_beyond_the_threshold_count_as_progress(self):
        self.assertEqual(self.orch.research._stalled(), 2)  # n002, n003 after the n001 gain
        with patch.object(self.orch.setup, "progress_threshold", return_value=1.0):
            self.assertEqual(self.orch.research._stalled(), 3)

    def test_stall_triggers_a_fresh_reviewer_and_a_forced_full_review(self):
        course = ("Diagnosis: three tweaks of one idea.\nPause: tuning the same family, it stopped paying.\n"
                  "Next direction: look at the errors of the best model by segment first.\n")

        def run(prompt, **kwargs):
            if prompt.startswith("You are a fresh reviewer"):
                (kwargs["cwd"] / "COURSE.md").write_text(course)
            else:
                self.assertIn("Next direction: look at the errors", prompt)
                self.assertIn("tuning the same family", prompt)
                (kwargs["cwd"] / "DECISION.md").write_text(prose("n001"))
            return RunResult(ok=True, exit_code=0)
        self.orch.research.runner = Mock(run_agent=Mock(side_effect=run))
        line = "Next direction: look at the errors of the best model by segment first."
        responses = [{"direction": line, "direction_quote": line, "paused": ["tuning the same family"],
                      "setup_change": {"needed": False}}, extracted("n001")]
        self.orch.maintainer = SimpleNamespace(call_cfg=SimpleNamespace(timeout_s=30), runner=Mock(
            ask_json=Mock(side_effect=[(r, RunResult(ok=True, exit_code=0)) for r in responses])))
        node = self.orch.scheduler.next_node()
        self.assertEqual(node.worker["research"]["decision_kind"], "review")
        self.assertEqual(self.orch.research.runner.run_agent.call_count, 2)
        self.assertEqual(self.orch.research._stalled(), 0)  # counting restarts after a correction

    def test_failed_course_correction_does_not_stop_the_study(self):
        self.orch.research.runner = Mock(run_agent=Mock(side_effect=[
            RunResult(ok=False, exit_code=1, error="offline"),
            RunResult(ok=False, exit_code=1, error="offline")]))
        self.assertIsNone(self.orch.scheduler.next_node())
        events = [json.loads(line)["event"] for line in self.cfg.events_path.read_text().splitlines()]
        self.assertIn("course_correction_failed", events)
        self.assertEqual(self.orch.tree.meta["research_last_course"]["course"], "k001")


class SingleHomeTests(unittest.TestCase):
    def test_wiki_owns_insights_and_plans_in_research_mode(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = make_cfg(Path(d))
            orch = Orchestrator(cfg, verbose=False)
            claims = {"a": {"id": "a", "title": "Works", "statement": "Depth helps.", "status": "supported"},
                      "b": {"id": "b", "title": "Fails", "statement": "Bagging hurts.", "status": "refuted"}}
            with patch.object(orch.memory, "state", return_value={"claims": claims, "revision": "r1"}):
                insights, deadends = orch.memory.ledger_views()
            self.assertIn("Works: Depth helps. [wiki: a]", insights)
            self.assertNotIn("Fails", insights)
            self.assertIn("Fails: Bagging hurts. [wiki: b]", deadends)
            self.assertIn("generated", insights)


if __name__ == "__main__":
    unittest.main()
