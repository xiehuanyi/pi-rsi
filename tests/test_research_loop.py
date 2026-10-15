"""Research decisions, evidence boundaries, and completion-triggered model wakeups."""
from __future__ import annotations

import copy
import json
import os
import signal
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pi_rsi import decision as D
from pi_rsi.config import (ExperimentCfg, TaskCfg, RunnerCfg, UtilityCfg, MaintainerCfg,
                           HooksCfg, OpsCfg, SearchCfg, SetupCfg, load_experiment, write_experiment_toml)
from pi_rsi.evidence import comparison, paired_noise
from pi_rsi.memory import ResearchMemory
from pi_rsi.monitor import TaskMonitor
from pi_rsi.orchestrator import Orchestrator
from pi_rsi.research import _sha as research_sha
from pi_rsi.runner import RunResult
from pi_rsi.tree import Node
from pi_rsi.util import atomic_write_json


def make_cfg(root):
    task = root / "task"
    (task / "eval").mkdir(parents=True)
    (task / "starter").mkdir()
    (task / "TASK.md").write_text("Verify the research loop on a deterministic CPU fixture.")
    (task / "starter" / "agent.py").write_text("def agent(obs):\n    return {}\n")
    (task / "eval" / "eval.py").write_text(
        "import argparse,json,runpy\nfrom pathlib import Path\n"
        "p=argparse.ArgumentParser();p.add_argument('--agent-dir');p.add_argument('--seedset');p.add_argument('--out')\n"
        "a=p.parse_args();runpy.run_path(str(Path(a.agent_dir)/'agent.py'))\n"
        "Path(a.out).write_text(json.dumps({'score':1.0,'per_item':[{'id':i,'value':1.0} for i in range(4)]}))\n")
    fake = str(Path(__file__).parent / "fake_agent.py")
    cfg = ExperimentCfg("fixture", root / "run", TaskCfg(name="fixture", dir=str(task), final_seedset=""),
        runner=RunnerCfg(kind="script", model=fake, node_timeout_s=30),
        utility=UtilityCfg(kind="script", model=fake, timeout_s=30),
        maintainer=MaintainerCfg(kind="script", model=fake, timeout_s=30),
        search=SearchCfg(max_nodes=4, width_root=2, width=1, depth=3, max_parallel=4, patience=1),
        hooks=HooksCfg(narrative=False), ops=OpsCfg(auto=False), setup=SetupCfg(enabled=False, course_k=99))  # setup and course correction have own tests
    cfg.dir.mkdir()
    return cfg


def decision(parent="root", action="continue"):
    """A plan in the format saved by earlier harness versions (THINK.md + decision.json)."""
    candidates = [{"id": str(i), "parent": parent, "title": f"approach {i}",
        "hypothesis": f"implement approach {i}", "type": "ablate", "expected_gain": "unknown",
        "risk": "noise", "research_question": "Which explanation fits?", "prediction": "Measurable change.",
        "falsifier": "No reproducible change.", "evidence_ids": [], "rationale": "Controlled comparison.",
        "budget": {"seconds": 20, "max_trials": 2}} for i in range(2)]
    return {"action": action, "reason": "The measured gap was checked against the task objective.",
        "assessment": {k: "Explicitly assessed within fixture scope." for k in
            ("goal_progress", "result_analysis", "reference_search", "uncertainty", "belief_revisions")},
        "saturation_checks": ["Objective satisfied within this fixture; no further required deliverable."]
                              if action == "stop" else [],
        "references": [], "candidates": candidates if action == "continue" else [],
        "selected": "0" if action == "continue" else None}


def prose(parent="root", action="continue"):
    """What a research lead writes: no JSON."""
    if action == "stop":
        return "Decision: stop. The objective is satisfied within this fixture; no deliverable remains."
    return (f"Decision: continue.\nBuild on {parent} and implement approach 0 as a controlled ablation.\n"
            "I expect a measurable change; no reproducible change would refute it. Approach 1 is less discriminating.")


def extracted(parent="root", action="continue", **changes):
    """What the extractor returns for prose(parent, action)."""
    out = {"action": action, "action_quote": f"Decision: {action}.", "parent": parent if action == "continue" else None,
        "title": "approach 0", "hypothesis": "implement approach 0", "type": "ablate",
        "research_question": "Which explanation fits?", "prediction": "Measurable change.",
        "falsifier": "No reproducible change.", "evidence": [], "budget": {"seconds": 20, "max_trials": 2},
        "alternatives": [{"title": "approach 1", "parent": parent, "why_not": "less discriminating"}],
        "reason": "The measured gap was checked against the task objective.",
        "saturation_checks": ["The objective is satisfied within this fixture."] if action == "stop" else []}
    out.update(changes)
    return out


HANDOFF = ("# Handoff\n## Result\nOfficial fixture score 1.0 on the validation level.\n## Noise assessment\n"
           "No replication.\n## Belief revisions\nNone.\n## Competing explanations\nFixture determinism.\n")


def analysis(**changes):
    out = {"observations": ["Official fixture score 1.0."], "interpretation": "No causal conclusion.",
           "noise_assessment": "No replication.", "belief_revisions": [], "competing_explanations": [],
           "limitations": [], "result_quote": "Official fixture score 1.0 on the validation level."}
    out.update(changes)
    return out


class ResearchDecisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = make_cfg(Path(self.tmp.name))
        self.orch = Orchestrator(self.cfg, verbose=False)
        self.orch.tree.add(Node("root", None, 0, "baseline", "", status="done", score=10, commit="root-code"))

    def tearDown(self):
        self.tmp.cleanup()

    def extractor(self, *responses):
        """The small model: returns the given structured outputs in order."""
        runner = Mock(ask_json=Mock(side_effect=[(r, RunResult(ok=True, exit_code=0)) for r in responses]))
        self.orch.maintainer = SimpleNamespace(runner=runner, call_cfg=SimpleNamespace(timeout_s=30))
        return runner

    def lead(self, text, callback=None, **result):
        """The research lead: writes DECISION.md in prose during a full review."""
        def run(*args, **kwargs):
            (kwargs["cwd"] / "DECISION.md").write_text(text)
            if callback:
                callback()
            return RunResult(**{"ok": True, "exit_code": 0, "session_id": "lead-session", **result})
        self.orch.research.runner = Mock(run_agent=Mock(side_effect=run))
        return self.orch.research.runner

    def finished(self, node_id, parent="root", score=10, depth=1):
        node = self.orch.tree.add(Node(node_id, parent, depth, "branch", "", status="done", score=score,
                                       commit=f"code-{node_id}"))
        self.orch.tree.update(node, status="done", finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
        self.orch.tree._counter = max(self.orch.tree._counter, int(node_id[1:]))
        return node

    def propose(self, node, text):
        path = self.cfg.nodes_dir / node.id / "NEXT.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        self.orch.tree.meta["research_proposal"] = {"node": node.id, "path": str(path)}
        self.orch.tree.meta["research_last_review"] = {"launched": self.orch.scheduler.launched_count(),
                                                       "human": research_sha("")}

    def test_full_review_can_choose_lower_scoring_branch(self):
        for i, score in ((1, 100), (2, 20)):
            self.finished(f"n00{i}", score=score)
        self.lead(prose("n002"))
        self.extractor(extracted("n002"))
        node = self.orch.scheduler.next_node()
        self.assertEqual(node.parent, "n002")
        self.assertEqual(node.worker["research"]["tuning_budget"], {"seconds": 20, "max_trials": 2})
        self.assertEqual(node.worker["research"]["decision_kind"], "review")
        self.assertTrue(node.worker["research"]["think_path"].endswith("DECISION.md"))
        self.assertEqual(self.orch.research.runner.run_agent.call_count, 1)
        self.assertIsNone(self.orch.scheduler.next_node())  # no second implementation while one is pending

    def test_proposal_from_latest_analysis_runs_without_a_full_review(self):
        n001 = self.finished("n001")
        self.propose(n001, prose("n001"))
        self.orch.research.runner = Mock(run_agent=Mock(side_effect=AssertionError("no full review")))
        self.extractor(extracted("n001"))
        node = self.orch.scheduler.next_node()
        self.assertEqual((node.parent, node.worker["research"]["decision_kind"]), ("n001", "proposal"))
        self.assertNotIn("research_proposal", self.orch.tree.meta)
        cycle = self.cfg.dir / "cycles" / node.worker["research"]["cycle"]
        self.assertEqual((cycle / "DECISION.md").read_text(), prose("n001"))

    def test_proposal_reentering_a_paused_direction_goes_to_a_full_review(self):
        n001 = self.finished("n001")
        course = self.cfg.dir / "course" / "k001"
        course.mkdir(parents=True)
        atomic_write_json(course / "course.json", {"paused": ["COCONUT-balanced contrastive variants"]})
        self.propose(n001, prose("n001"))
        lead = self.lead(prose("n001"))
        extractor = self.extractor(extracted("n001", reenters_paused=True,
                                             paused_match="COCONUT-balanced contrastive variants (k001)"),
                                   extracted("n001", expected_delta=0.004, evidence=["n001", "k001", "e-unknown"]))
        node = self.orch.scheduler.next_node()
        self.assertEqual(node.worker["research"]["decision_kind"], "review")
        self.assertEqual(lead.run_agent.call_count, 1)
        self.assertIn("COCONUT-balanced contrastive variants (k001)", extractor.ask_json.call_args_list[0].args[0])
        proposal = node.worker["proposal"]
        self.assertEqual(proposal["expected_delta"], 0.004)
        self.assertEqual(proposal["evidence_ids"], ["n001", "k001"])  # node and course IDs are citable
        events = [json.loads(line)["event"] for line in self.cfg.events_path.read_text().splitlines()]
        self.assertIn("research_paused_reentry", events)

    def test_unmeasured_analysis_says_so_and_cites_no_official_score(self):
        node = self.finished("n001")
        (self.cfg.nodes_dir / "n001").mkdir(parents=True, exist_ok=True)
        quote = "No official result: the diagnostic found headroom in 3 of 64 pools."
        handoff = (f"# Handoff\n## Result\n{quote}\n## Noise assessment\nDevelopment only.\n"
                   "## Belief revisions\nNone.\n")

        def run(prompt, **kw):
            (kw["cwd"] / "HANDOFF.md").write_text(handoff)
            (kw["cwd"] / "NEXT.md").write_text(prose("n001"))
            return RunResult(ok=True, exit_code=0)
        self.orch.research.runner = Mock(run_agent=Mock(side_effect=run))
        self.extractor(analysis(observations=["Headroom in 3 of 64 pools."], result_quote=quote))
        self.orch.research.analyze(node, None, {"verdict": "not_measured"})
        prompt = self.orch.research.runner.run_agent.call_args.args[0]
        self.assertIn("NOT officially evaluated", prompt)
        self.assertIn("Official metrics: none", prompt)
        self.assertIn("No official evaluation", (self.cfg.nodes_dir / "n001" / "HANDOFF.md").read_text())
        self.assertEqual(self.orch.tree.meta["research_proposal"]["node"], "n001")

    def test_unusable_proposal_falls_back_to_a_full_review(self):
        n001 = self.finished("n001")
        self.propose(n001, "Next: something around the best branch.")
        lead = self.lead(prose("n001"))
        ungrounded = extracted("n001", action_quote="Decision: continue.")
        self.extractor(ungrounded, ungrounded, extracted("n001"))
        node = self.orch.scheduler.next_node()
        self.assertEqual(node.worker["research"]["decision_kind"], "review")
        self.assertEqual(lead.run_agent.call_count, 1)
        self.assertTrue(self.orch.tree.meta["research_last_review"]["cycle"])
        events = [json.loads(line)["event"] for line in self.cfg.events_path.read_text().splitlines()]
        self.assertIn("research_proposal_rejected", events)
        self.assertNotIn("research_failed", events)

    def test_proposed_stop_needs_a_full_review(self):
        n001 = self.finished("n001")
        self.propose(n001, prose(action="stop"))
        self.lead(prose("n001"))
        self.extractor(extracted(action="stop"), extracted("n001"))
        node = self.orch.scheduler.next_node()
        self.assertEqual((node.parent, node.worker["research"]["decision_kind"]), ("n001", "review"))
        self.assertNotIn("research_stop", self.orch.tree.meta)

    def test_full_review_is_due_periodically_on_plateaus_and_new_human_direction(self):
        n001 = self.finished("n001")
        self.propose(n001, prose("n001"))
        r, s = self.orch.research, self.orch.scheduler
        snapshot = r._snapshot(s)
        self.assertIsNone(r._review_reason(snapshot, s, r._fresh_proposal()))
        self.assertIn("no usable", r._review_reason(snapshot, s, None))
        self.orch.tree.meta["research_last_review"]["launched"] = -self.cfg.research.review_every
        self.assertIn("since the last full review", r._review_reason(snapshot, s, r._fresh_proposal()))
        self.orch.tree.meta["research_last_review"]["launched"] = 1 - self.cfg.search.patience
        self.assertIn("no new best", r._review_reason({**snapshot, "stall_count": self.cfg.search.patience}, s, {}))
        self.orch.tree.meta["research_last_review"]["launched"] = 1
        self.assertIn("human", r._review_reason({**snapshot, "human": "Focus on calibration."}, s, {}))
        self.finished("n002")  # a newer result supersedes the older proposal
        self.assertIsNone(r._fresh_proposal())

    def test_ambiguous_review_gets_one_clarifying_question(self):
        self.finished("n001")
        lead = self.lead("Decision: continue on the strongest branch with approach 0.")

        def clarify(session_id, prompt, **kwargs):
            self.assertEqual(session_id, "lead-session")
            (kwargs["cwd"] / "DECISION.md").write_text(prose("n001"))
            return RunResult(ok=True, exit_code=0)
        lead.resume_agent = Mock(side_effect=clarify)
        self.extractor(extracted("n001"), extracted("n001"), extracted("n001"))
        node = self.orch.scheduler.next_node()
        self.assertEqual(node.parent, "n001")
        self.assertEqual(lead.resume_agent.call_count, 1)
        cycle = self.cfg.dir / "cycles" / node.worker["research"]["cycle"]
        self.assertIn("strongest branch", (cycle / "DECISION.before_clarify.md").read_text())

    def test_unresolvable_review_is_the_last_resort_failure(self):
        lead = self.lead("I am not sure yet.")
        lead.resume_agent = Mock(return_value=RunResult(ok=True, exit_code=0))
        self.extractor(*[extracted("root", action_quote="Decision: continue.")] * 4)
        self.assertIsNone(self.orch.scheduler.next_node())
        self.assertEqual(self.orch.scheduler.stop_reason(), "research_failed")

    def test_audit_fields_are_repaired_not_fatal(self):
        snapshot = self.orch.research._snapshot(self.orch.scheduler)
        snapshot["known_claims"] = ["n024-depthwise800-repeat-measurement"]
        cycle = self.orch.research._new_cycle()
        d = decision()
        d["candidates"][0].update(evidence_ids=["n024-depthwise-repeat-measurement", "invented-source"])
        d["candidates"][0]["budget"].update(seconds=999)
        d["candidates"][1].update(evidence_ids=["also-invented"])
        out = self.orch.research._validate(d, snapshot, cycle)
        self.assertEqual(out["selected"], "0")
        chosen = out["candidates"][0]
        self.assertEqual(chosen["evidence_ids"], ["n024-depthwise800-repeat-measurement"])
        self.assertEqual(chosen["budget"]["seconds"], self.cfg.runner.node_timeout_s)
        self.assertTrue(any("invented-source" in w for w in out["warnings"]))
        self.assertEqual(self.orch.research._validate(out, snapshot, cycle), out)
        d["selected"] = "missing"
        with self.assertRaises(ValueError):
            self.orch.research._validate(d, snapshot, cycle)
        self.assertEqual(len(self.orch.tree.non_root()), 0)

    def test_unselected_ineligible_alternative_does_not_block_a_valid_choice(self):
        data = decision()
        blocked = copy.deepcopy(data["candidates"][0])
        blocked.update(id="blocked", parent="full-or-missing-parent")
        data["candidates"].append(blocked)
        cycle = self.orch.research._new_cycle()
        snapshot = self.orch.research._snapshot(self.orch.scheduler)
        out = self.orch.research._validate(data, snapshot, cycle)
        self.assertEqual(out["selected"], "0")
        self.assertEqual(out["candidates"], self.orch.research._validate(decision(), snapshot, cycle)["candidates"])
        self.assertEqual(out["excluded_candidates"][0]["parent"], "full-or-missing-parent")
        self.assertEqual(self.orch.research._validate(out, snapshot, cycle), out)
        data["selected"] = "blocked"
        with self.assertRaises(ValueError):
            self.orch.research._validate(data, snapshot, cycle)
        data["selected"] = "0"
        data["candidates"].pop(1)  # a single executable choice is allowed, with a warning
        self.assertIn("no alternative was compared", self.orch.research._validate(data, snapshot, cycle)["warnings"])

    def test_extraction_must_be_copied_from_the_text(self):
        text = prose("n001")
        self.assertEqual(D.from_extraction(extracted("n001"), text)["candidates"][0]["parent"], "n001")
        for bad in (extracted("n001", action_quote="We should continue."), extracted("n002")):
            with self.assertRaises(ValueError):
                D.from_extraction(bad, text)
        self.assertTrue(D.grounded("**Decision:** continue", "Decision: continue.\nmore"))
        self.assertFalse(D.mentions("build on n0010", "n001"))

    def test_saved_plan_repair_preserves_choice_and_requires_unchanged_evidence(self):
        cycle = self.orch.research._new_cycle()
        snapshot = self.orch.research._snapshot(self.orch.scheduler)
        atomic_write_json(cycle / "snapshot.json", snapshot)
        atomic_write_json(cycle / "decision.json", decision())
        (cycle / "THINK.md").write_text("Compared alternatives on this exact evidence snapshot.")
        self.orch.tree.meta["research_error"] = {"cycle": cycle.name, "error": "old validation failure"}
        self.orch.research.runner = Mock(run_agent=Mock(side_effect=AssertionError("no new review")))
        self.assertEqual(self.orch.research.repair_plan(), cycle.name)
        self.assertNotIn("research_error", self.orch.tree.meta)
        self.assertTrue(json.loads((cycle / "repair.json").read_text())["selected_unchanged"])
        node = self.orch.scheduler.next_node()
        self.assertEqual(node.worker["research"]["cycle"], cycle.name)
        self.orch.tree.meta["research_error"] = {"cycle": cycle.name}
        with self.assertRaises(ValueError):
            self.orch.research.repair_plan()

    def test_plan_rejected_by_the_old_harness_is_recovered_on_restart(self):
        cycle = self.orch.research._new_cycle()
        snapshot = self.orch.research._snapshot(self.orch.scheduler)
        plan = decision()
        plan["candidates"][1]["evidence_ids"] = ["misspelled-claim"]  # killed a real 10-hour run
        atomic_write_json(cycle / "snapshot.json", snapshot)
        atomic_write_json(cycle / "decision.json", plan)
        (cycle / "THINK.md").write_text("Compared alternatives.")
        atomic_write_json(cycle / "failure.json", {"error": "candidate cites unknown evidence"})
        self.orch.research.runner = Mock(run_agent=Mock(side_effect=AssertionError("must recover, not decide again")))
        node = self.orch.scheduler.next_node()
        self.assertEqual((node.worker["research"]["cycle"], node.title), (cycle.name, "approach 0"))

    def test_analysis_is_structured_from_prose(self):
        nd = self.cfg.nodes_dir / "n001"
        nd.mkdir(parents=True)
        many = analysis(observations=[f"Measured observation {i}." for i in range(15)])
        self.extractor(analysis(result_quote="No replication."), many)  # not from the Result section
        def convert(raw):
            return D.analysis_from_extraction(raw, HANDOFF)
        _, out = self.orch.research._structured("analysis", lambda r: D.analysis_prompt(HANDOFF, r),
                                                D.ANALYSIS_SCHEMA, convert, nd, completion=True)
        self.assertEqual(len(out["observations"]), 12)
        self.assertNotIn("next_experiments", out)  # next steps live in NEXT.md, not in the node record
        second_prompt = self.orch.maintainer.runner.ask_json.call_args_list[1].args[0]
        self.assertIn("result_quote is not copied", second_prompt)
        self.extractor(analysis(result_quote="Stop now."), analysis(observations=[]))
        with self.assertRaises(ValueError):
            self.orch.research._structured("analysis", lambda r: D.analysis_prompt(HANDOFF, r),
                                           D.ANALYSIS_SCHEMA, convert, nd, completion=True)
        self.assertFalse(self.orch.tree.non_root())

    def test_stop_has_explicit_checks_and_creates_no_worker(self):
        self.lead(prose(action="stop"))
        self.extractor(extracted(action="stop"))
        self.assertIsNone(self.orch.scheduler.next_node())
        self.assertEqual(self.orch.scheduler.stop_reason(), "research_saturated")
        self.assertTrue(self.orch.tree.meta["research_stop"]["checks"])
        self.assertEqual(self.orch.tree.non_root(), [])

    def test_hard_deadline_cannot_be_overridden_by_the_lead(self):
        self.cfg.search.max_wallclock_s = 60
        self.lead(prose(), lambda: setattr(self.orch, "started_ts", time.time() - 61))
        self.extractor(extracted())
        self.assertIsNone(self.orch.scheduler.next_node())
        self.assertEqual(self.orch.scheduler.stop_reason(), "wallclock")
        self.assertEqual(self.orch.tree.non_root(), [])

    def test_failed_review_preserves_search_space(self):
        self.orch.research.runner = Mock(run_agent=Mock(return_value=RunResult(ok=False, exit_code=1, error="offline")))
        self.assertIsNone(self.orch.scheduler.next_node())
        self.assertEqual(self.orch.scheduler.stop_reason(), "research_failed")
        self.assertNotIn(-1, self.orch.tree.get("root").proposals_used)

    def test_completed_plan_survives_session_timeout(self):
        self.lead(prose(), ok=False, exit_code=-15, timed_out=True, error="timeout")
        self.extractor(extracted())
        node = self.orch.scheduler.next_node()
        self.assertIsNotNone(node)
        self.assertNotIn("research_error", self.orch.tree.meta)

    def test_restart_recovers_only_a_valid_plan_against_unchanged_evidence(self):
        cycle=self.orch.research._new_cycle();snapshot=self.orch.research._snapshot(self.orch.scheduler)
        atomic_write_json(cycle/'snapshot.json',snapshot);atomic_write_json(cycle/'decision.json',decision())
        atomic_write_json(cycle/'failure.json',{'error':'timeout'})
        (cycle/'THINK.md').write_text('Completed before supervision stopped the session.')
        self.orch.research.runner=Mock(run_agent=Mock(side_effect=AssertionError('must recover, not call model')))
        node=self.orch.scheduler.next_node()
        self.assertIsNotNone(node)
        self.assertEqual(node.worker['research']['cycle'],cycle.name)

    def test_restart_restructures_a_saved_prose_decision(self):
        cycle = self.orch.research._new_cycle()
        atomic_write_json(cycle / "snapshot.json", self.orch.research._snapshot(self.orch.scheduler))
        atomic_write_json(cycle / "origin.json", {"kind": "review"})
        (cycle / "DECISION.md").write_text(prose())
        self.orch.research.runner = Mock(run_agent=Mock(side_effect=AssertionError("must recover, not call the lead")))
        self.extractor(extracted())
        self.assertEqual(self.orch.scheduler.next_node().worker["research"]["cycle"], cycle.name)

    def test_controller_failure_does_not_unseal_confirmation(self):
        self.cfg.task.final_seedset='full'
        self.cfg.task.final_eval_root=True
        for reason in ('research_failed', 'postprocess_failed'):
            with patch('pi_rsi.orchestrator.run_eval',side_effect=AssertionError('must keep confirmation sealed')):
                self.orch.finish(reason)
            final=json.loads((self.cfg.dir/'final.json').read_text())
            self.assertNotIn('best_final_score',final)
            self.assertIn('deferred',final['note'])

    def test_interrupt_during_review_is_not_mislabeled_exhaustion(self):
        self.cfg.memory.enabled = False
        self.orch.memory.enabled = False
        self.cfg.task.final_seedset = 'full'
        self.lead(prose(), self.orch.stop_flag.set)
        self.extractor(extracted())
        with patch('pi_rsi.orchestrator.run_eval', side_effect=AssertionError('confirmation remains sealed')):
            self.assertEqual(self.orch.run(), 'interrupted')
        self.assertEqual(self.orch.tree.non_root(), [])
        self.assertEqual(json.loads((self.cfg.dir/'final.json').read_text())['stop_reason'], 'interrupted')

    def test_own_source_capture_and_wiki_compilation_do_not_repeat_a_completed_review(self):
        cycle = self.orch.research._new_cycle()
        source = cycle / 'sources/reference.md'
        source.write_text('A bounded methodological source, not a local experiment.')
        data = decision()
        data['references'] = [{'title': 'Reference', 'url': 'https://example.com/method', 'source_path': 'sources/reference.md'}]
        snapshot = self.orch.research._snapshot(self.orch.scheduler)
        out = self.orch.research._validate(data, snapshot, cycle)
        self.orch.research._publish_plan(cycle, snapshot, out, "review")
        self.orch.research.runner = Mock(run_agent=Mock(side_effect=AssertionError('must reuse locked plan')))
        with patch.object(self.orch.memory, 'state', return_value={'revision': 'compiled-after-plan', 'claims': {}}):
            node = self.orch.scheduler.next_node()
        self.assertEqual(node.worker['research']['cycle'], cycle.name)

    def test_source_excerpts_cannot_escape_cycle_directory(self):
        d = decision()
        cycle = self.orch.research._new_cycle()
        d["references"] = [{"title": "source", "url": "https://example.com", "source_path": "../../task/TASK.md"}]
        out = self.orch.research._validate(d, self.orch.research._snapshot(self.orch.scheduler), cycle)
        self.assertEqual(out["references"], [])
        self.assertTrue(any("sources directory" in w for w in out["warnings"]))

    def test_old_runs_opt_in_and_new_default_maintainer_is_luna(self):
        write_experiment_toml(self.cfg)
        self.assertTrue(load_experiment(self.cfg.dir).research.enabled)
        text = (self.cfg.dir / "rsi.toml").read_text().split("[research]", 1)[0]
        (self.cfg.dir / "rsi.toml").write_text(text)
        old = load_experiment(self.cfg.dir)
        self.assertFalse(old.research.enabled)
        self.assertFalse(old.maintainer.enabled)
        self.assertEqual(MaintainerCfg().model, "openai-codex/gpt-6-luna")

    def test_wallclock_accounting_survives_controller_restart(self):
        self.orch.started_ts -= 40
        self.orch.write_state()
        restarted = Orchestrator(self.cfg, verbose=False)
        self.assertGreaterEqual(time.time() - restarted.started_ts, 40)

    def test_reference_search_is_enabled_only_for_research_role(self):
        self.cfg.runner = RunnerCfg(kind="grok", model="grok-4.6")
        orch = Orchestrator(self.cfg, verbose=False)
        self.assertNotIn("--disable-web-search", orch.research.runner._common(self.cfg.dir))
        self.assertIn("--disable-web-search", orch.worker_runner._common(self.cfg.dir))


class EvidenceTests(unittest.TestCase):
    def test_heuristic_floor_cannot_label_a_meaningful_gain(self):
        c = comparison({"score": 100}, {"score": 1}, score=100, parent_score=1,
                       higher_is_better=True, fallback=.01)
        self.assertEqual(c["classification"], "uncertain")

    def test_paired_items_must_be_complete_compatible_and_unique(self):
        a = {"per_item": [{"id": i, "value": 1.0} for i in range(5)]}
        b = copy.deepcopy(a)
        self.assertEqual(paired_noise(a, b), (0, 5))
        b["per_item"].pop()
        self.assertIsNone(paired_noise(a, b))
        b = copy.deepcopy(a); b["per_item"].append(b["per_item"][0])
        self.assertIsNone(paired_noise(a, b))
        b = copy.deepcopy(a); b["split_id"] = "another-split"
        self.assertIsNone(paired_noise(a, b))

    def test_superseded_beliefs_keep_history_and_separate_navigation(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = make_cfg(Path(d)); orch = Orchestrator(cfg, verbose=False); mem = orch.memory
            first = mem._capture({"kind": "source", "title": "old", "text": "old evidence", "protocol": mem.protocol})
            page = {"id": "belief", "title": "Scoped belief", "kind": "hypothesis", "status": "supported",
                    "statement": "A may help.", "scope": "Fixture protocol.", "supports": [first], "opposes": [],
                    "alternatives": [], "next_test": "Controlled repeat."}
            agenda = {"motivation": "Resolve the gap.", "method": "Compare controls.", "what_changed": "Initial evidence.",
                      "open_questions": [], "next_experiments": []}
            mem.reflect(SimpleNamespace(_ask=lambda *args: {"claims": [page], "agenda": agenda}), force=True)
            old_revision = mem.revision
            second = mem._capture({"kind": "source", "title": "new", "text": "new counterevidence", "protocol": mem.protocol})
            predecessor = {**page, "status": "superseded"}
            successor = {**page, "id": "corrected-belief", "status": "refuted", "supports": [], "opposes": [second],
                         "supersedes": "belief", "revision_reason": "The identifying control contradicts the old interpretation."}
            mem.reflect(SimpleNamespace(_ask=lambda *args: {"claims": [predecessor, successor], "agenda": agenda}), force=True)
            state = mem.state()
            self.assertEqual(state["claims"]["belief"]["supports"], [first])
            self.assertEqual(state["claims"]["corrected-belief"]["status"], "refuted")
            self.assertTrue((mem.root / "revisions" / old_revision / "wiki" / "belief.md").exists())
            self.assertTrue((mem.root / "revisions" / mem.revision / "index" / "index.json").exists())
            self.assertTrue((mem.root / "raw" / (first + ".json")).exists())


class MonitorTests(unittest.TestCase):
    def test_running_task_cannot_wake_model_and_resumes_same_job(self):
        from pi_rsi import jobs
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"RSI_JOBS_DIR": d}), \
                patch("pi_rsi.jobs.ensure_daemon"):
            monitor = TaskMonitor(Path(d) / "monitor.json")
            out = Path(d) / "result.json"
            job = monitor.submit(["fixture"], Path(d), identity={"code": "a"}, result_path=str(out))
            job.status = "running"; job.save()
            with self.assertRaises(RuntimeError):
                monitor.begin_analysis()
            same = monitor.submit(["fixture"], Path(d), identity={"code": "a"}, result_path=str(out))
            self.assertEqual(same.id, job.id)
            self.assertEqual(len(jobs.list_jobs()), 1)
            out.write_text('{"score":1}')
            job.status = "done"; job.exit_code = 0; job.save()
            monitor.wait(job.id); monitor.validated(out); monitor.begin_analysis(); monitor.consumed()
            record = json.loads(monitor.path.read_text())
            self.assertEqual(record["state"], "consumed")
            self.assertEqual(record["wake_count"], 1)
            out.write_text('{"score":999}')
            with self.assertRaises(RuntimeError):
                monitor.submit(["fixture"], Path(d), identity={"code": "a"}, result_path=str(out))

    def test_terminal_failure_does_not_validate_or_wake(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"RSI_JOBS_DIR": d}), \
                patch("pi_rsi.jobs.ensure_daemon"):
            monitor = TaskMonitor(Path(d) / "monitor.json")
            job = monitor.submit(["fixture"], Path(d), identity={}, result_path=str(Path(d) / "result"))
            job.status = "failed"; job.save(); monitor.wait(job.id)
            with self.assertRaises(RuntimeError):
                monitor.validated(Path(d) / "result")
            with self.assertRaises(RuntimeError):
                monitor.begin_analysis()


class ResearchIntegrationTests(unittest.TestCase):
    def test_real_cpu_queue_loop_wakes_only_after_completion(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"RSI_JOBS_DIR": str(Path(d) / "jobs"), "RSI_GPUS": ""}):
            cfg = make_cfg(Path(d)); cfg.search.patience = 10
            cfg.setup = SetupCfg(enabled=True, calibration_runs=2, course_k=2)
            orch = Orchestrator(cfg, verbose=False)
            try:
                self.assertEqual(orch.run(), "setup_required")  # nothing runs before a confirmed setup
                self.assertFalse(orch.tree.non_root())
                orch.ensure_root()
                self.assertEqual(orch.setup.run(), "awaiting_human")  # first setup: the human must answer
                self.assertIn("practical_delta", (cfg.setup_dir / "QUESTIONS.md").read_text())
                self.assertEqual(orch.setup.run(accept_recommended=True), "complete")
                setup = json.loads((cfg.setup_dir / "setup.json").read_text())
                self.assertEqual((setup["calibration"]["runs"], setup["calibration"]["band"]), (2, 0.0))
                self.assertEqual(set(setup["decisions"]), {"practical_delta", "review_cadence"})
                self.assertEqual({d["decided_by"] for d in setup["decisions"].values()},
                                 {"human (accepted recommendation)"})
                self.assertFalse((cfg.setup_dir / "QUESTIONS.md").exists())
                self.assertEqual(orch.run(), "max_nodes")
                done = [n for n in orch.tree.non_root() if n.status == "done"]
                self.assertEqual(len(done), cfg.search.max_nodes)
                self.assertTrue(all(n.worker.get("analysis") for n in done))
                for n in done:
                    record = json.loads(next((cfg.nodes_dir / n.id / "eval").glob("*.monitor.json")).read_text())
                    self.assertEqual(record["state"], "consumed")
                    self.assertEqual(record["wake_count"], 1)
                    self.assertLessEqual(record["finished_at"], record["model_woken_at"])
                    self.assertIn("Harness measurement record", (cfg.nodes_dir / n.id / "HANDOFF.md").read_text())
                self.assertTrue(orch.memory.revision)
                self.assertEqual(orch.memory.pending(), [])
                # Replay a controller that died after analysis was committed, before node publication.
                node = done[-1]
                orch.tree.update(node, status="analyzing")
                restarted = Orchestrator(cfg, verbose=False)
                restarted.recover()
                recovered = restarted.tree.get(node.id)
                self.assertEqual(recovered.status, "done")  # journal is authoritative over stale status projection
                restarted.research.runner = Mock(run_agent=Mock(side_effect=AssertionError("must reuse saved analysis")))
                restarted.worker_runner = Mock(run_agent=Mock(side_effect=AssertionError("must preserve evaluated implementation")))
                with patch("pi_rsi.worker.run_eval", side_effect=AssertionError("must reuse measurement, not evaluate")):
                    restarted._safe_run_node(recovered)
                self.assertEqual(recovered.status, "done", recovered.failure)
                record = json.loads(next((cfg.nodes_dir / recovered.id / "eval").glob("*.monitor.json")).read_text())
                self.assertEqual(record["wake_count"], 1)
                self.assertEqual(record["state"], "consumed")
                events = [json.loads(line) for line in cfg.events_path.read_text().splitlines()]
                self.assertFalse([e for e in events if e["event"] in ("research_failed", "memory_failed")])
                # First decision is a full review; then NEXT.md proposals, until two results without
                # progress trigger a course correction, which forces a full review.
                kinds = [n.worker["research"]["decision_kind"] for n in sorted(done, key=lambda n: n.id)]
                self.assertEqual(kinds, ["review", "proposal", "review", "proposal"])
                course = json.loads((cfg.dir / "course" / "k001" / "course.json").read_text())
                self.assertEqual(course["paused"], ["repeating the fixture approach"])
                review = cfg.dir / "cycles" / sorted(done, key=lambda n: n.id)[2].worker["research"]["cycle"]
                self.assertIn("course correction k001", json.loads((review / "origin.json").read_text())["reason"])
                self.assertIn("Next direction:", (review / "research.prompt.md").read_text())
                for n in done:
                    nd = cfg.nodes_dir / n.id
                    self.assertTrue((nd / "IMPLEMENTATION.md").exists())
                    self.assertFalse((nd / "proposals.json").exists())
                    judged = json.loads((nd / "eval" / "comparison.json").read_text())
                    self.assertEqual(n.verdict, judged["verdict"])  # one judgement, copied nowhere else
                    self.assertNotIn("harness_comparison", json.loads((nd / "analysis.json").read_text()))
                self.assertIn("(generated)", cfg.insights_path.read_text())
                self.assertFalse(list((cfg.dir / "cycles").glob("*/THINK.md")))
                self.assertTrue(all((cfg.nodes_dir / n.id / "NEXT.md").exists() for n in done))
                handoffs = [(cfg.nodes_dir / n.id / "HANDOFF.md").read_text() for n in done]
                self.assertFalse([h for h in handoffs if "Next" in h or "Stop or continue" in h])
                self.assertIn("Wiki &amp; revisions", (cfg.dir / "tree.html").read_text())
            finally:
                daemon = Path(d) / "jobs" / "jobd.json"
                if daemon.exists():
                    pid = json.loads(daemon.read_text())["pid"]
                    try:
                        os.killpg(pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass


if __name__ == "__main__":
    unittest.main()
