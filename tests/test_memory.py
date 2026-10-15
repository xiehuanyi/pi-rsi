"""Research-memory regression tests: provenance, counterevidence, recovery, and decisions."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pi_rsi.config import (ExperimentCfg, MemoryCfg, SearchCfg, TaskCfg, RunnerCfg, UtilityCfg,
                           HooksCfg, OpsCfg, load_experiment, write_experiment_toml)
from pi_rsi.memory import ResearchMemory
from pi_rsi.scheduler import Scheduler
from pi_rsi.tree import Node, Tree
from pi_rsi.util import atomic_write_json


def agenda():
    return {"motivation": "Explain why far-edge coverage degrades.",
            "method": "Test local assignment against unrestricted matching.",
            "what_changed": "Both crowding and travel remain plausible.",
            "open_questions": ["Which mechanism dominates?"],
            "next_experiments": ["Hold routing fixed and ablate assignment."]}


def claim(eid, **kw):
    c = {"id": "spatial-assignment", "title": "Conditional spatial assignment",
         "kind": "hypothesis", "status": "supported", "statement": "Assignment may help coverage.",
         "scope": "50 tiles, 9 actors, unchanged travel policy", "next_test": "Ablate assignment only.",
         "supports": [eid], "opposes": [], "alternatives": ["Travel policy explains the gain."]}
    c.update(kw)
    return c


class FakeUtility:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def _ask(self, *args):
        self.calls += 1
        return self.response() if callable(self.response) else copy.deepcopy(self.response)


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        task = self.base / "task"
        (task / "eval").mkdir(parents=True)
        (task / "eval" / "eval.py").write_text("# fixed evaluator")
        (task / "TASK.md").write_text("Find a conditional explanation for spatial coverage.")
        self.cfg = ExperimentCfg("one", self.base / "runs" / "one", TaskCfg(name="farm", dir=str(task)),
                                 memory=MemoryCfg(reflect_every=1))
        self.cfg.dir.mkdir(parents=True)
        self.tree = Tree(self.cfg.tree_path)
        self.mem = ResearchMemory(self.cfg)

    def tearDown(self):
        self.tmp.cleanup()

    def node(self, name="n001", score=1.0, **kw):
        n = Node(name, "root", 1, "spatial assignment", "Hold routing fixed.", status="done",
                 score=score, commit="abc123", metrics={"score": score}, **kw)
        self.tree.add(n)
        nd = self.cfg.nodes_dir / name
        nd.mkdir(parents=True)
        (nd / "HANDOFF.md").write_text("Worker interpretation: assignment explains the score.")
        atomic_write_json(nd / "eval" / "metrics.validation.json", {"score": score, "seed": 101})
        atomic_write_json(nd / "eval" / "metrics.test.final.json", {"SECRET_FINAL": 9999})
        return n

    def publish(self):
        self.mem.sync(self.tree)
        eid = self.mem.pending()[0]["id"]
        u = FakeUtility({"claims": [claim(eid)], "agenda": agenda()})
        self.assertTrue(self.mem.reflect(u, force=True))
        return eid

    def test_config_roundtrip_and_legacy_opt_in(self):
        write_experiment_toml(self.cfg)
        self.assertTrue(load_experiment(self.cfg.dir).memory.enabled)
        path = self.cfg.dir / "rsi.toml"
        path.write_text(path.read_text().split("[memory]")[0])
        self.assertFalse(load_experiment(self.cfg.dir).memory.enabled)
        with self.assertRaises(ValueError):
            MemoryCfg(reflect_every=0)

    def test_evidence_is_idempotent_versioned_and_excludes_final(self):
        n = self.node()
        self.mem.sync(self.tree)
        first = self.mem.packets()[0]
        first_path = self.mem.root / "raw" / (first["id"] + ".json")
        before = first_path.read_bytes()
        ResearchMemory(self.cfg).sync(self.tree)
        self.assertEqual(len(self.mem.packets()), 1)
        self.assertNotIn("SECRET_FINAL", json.dumps(first))
        self.tree.update(n, score=2, metrics={"score": 2})
        atomic_write_json(self.cfg.nodes_dir / n.id / "eval" / "metrics.validation.json", {"score": 2})
        self.mem.sync(self.tree)
        self.assertEqual(len(self.mem.packets()), 2)
        self.assertEqual(first_path.read_bytes(), before)

    def test_cross_run_sharing_and_protocol_isolation(self):
        self.node()
        self.publish()
        cfg2 = copy.deepcopy(self.cfg)
        cfg2.dir = self.base / "runs" / "two"
        cfg2.dir.mkdir()
        second = ResearchMemory(cfg2)
        self.assertEqual(second.revision, self.mem.revision)
        t2 = Tree(cfg2.tree_path)
        t2.add(Node("n001", "root", 1, "different run", "", status="done", score=3))
        second.sync(t2)
        self.assertEqual(len(self.mem.packets()), 2)  # same node ID, different run
        cfg2.memory.protocol_id = "different-data-v2"
        self.assertEqual(ResearchMemory(cfg2).revision, "")

    def test_opposing_evidence_survives_updates_and_snapshot_is_frozen(self):
        n = self.node()
        eid = self.publish()
        self.mem.snapshot(n)
        before = (self.cfg.nodes_dir / n.id / "MEMORY.md").read_bytes()
        self.node("n002", score=0)
        self.mem.sync(self.tree)
        opposing = self.mem.pending()[0]["id"]
        u = FakeUtility({"claims": [claim(eid, supports=[], opposes=[opposing], status="refuted")],
                         "agenda": agenda()})
        self.assertTrue(self.mem.reflect(u, force=True))
        c = self.mem.state()["claims"]["spatial-assignment"]
        self.assertEqual(c["status"], "mixed")
        self.assertEqual(c["supports"], [eid])
        self.assertIn("retained as mixed", self.mem.state()["agenda"]["what_changed"])
        self.assertIn(opposing, self.mem.context("spatial assignment"))
        self.assertEqual((self.cfg.nodes_dir / n.id / "MEMORY.md").read_bytes(), before)
        self.assertLessEqual(len(self.mem.context("spatial assignment")), self.cfg.memory.context_chars)
        self.assertEqual(len(list((self.mem.root / "revisions").iterdir())), 2)
        wiki = self.mem.root / "revisions" / self.mem.revision / "wiki" / "spatial-assignment.md"
        self.assertTrue((wiki.parent / "../../../raw" / (eid + ".json")).resolve().exists())

    def test_long_agenda_is_cut_and_misspelled_evidence_is_repaired(self):
        self.node()
        self.mem.sync(self.tree)
        eid = self.mem.pending()[0]["id"]
        long_agenda = {**agenda(), "open_questions": [f"question {i}" for i in range(9)]}
        u = FakeUtility({"claims": [claim(eid[:-1])], "agenda": long_agenda})  # a truncated evidence ID
        self.assertTrue(self.mem.reflect(u, force=True))
        state = self.mem.state()
        self.assertEqual(state["agenda"]["open_questions"], [f"question {i}" for i in range(6)])
        self.assertEqual(state["claims"]["spatial-assignment"]["supports"], [eid])
        self.assertEqual(u.calls, 1)

    def test_invalid_reflection_does_not_publish_or_consume(self):
        self.node()
        self.mem.sync(self.tree)
        u = FakeUtility({"claims": [claim("e-invented")], "agenda": agenda()})
        with self.assertRaises(ValueError):
            self.mem.reflect(u, force=True)
        self.assertEqual(self.mem.revision, "")
        self.assertEqual(len(self.mem.pending()), 1)
        self.assertFalse(self.mem.reflect(u, force=True))
        self.assertEqual(u.calls, 2)  # the draft plus one bounded repair told why it was rejected

    def test_scope_rewrite_gets_one_bounded_repair_before_publication(self):
        self.node();eid=self.publish()
        original=self.mem.state()['claims']['spatial-assignment']['scope']
        self.node('n002',score=2);self.mem.sync(self.tree)
        newest=self.mem.pending()[0]['id']
        drafts=iter([
            {'claims':[claim(newest,scope=original+'.')],'agenda':agenda()},
            {'claims':[claim(newest,scope=original)],'agenda':agenda()}])
        utility=FakeUtility(lambda:next(drafts))
        self.assertTrue(self.mem.reflect(utility,force=True))
        self.assertEqual(utility.calls,2)
        self.assertEqual(self.mem.state()['claims']['spatial-assignment']['scope'],original)
        self.assertEqual(self.mem.pending(),[])

    def test_unsafe_id_and_unscoped_claim_are_rejected(self):
        self.node()
        self.mem.sync(self.tree)
        eid = self.mem.pending()[0]["id"]
        for changes in ({"id": "../escape"}, {"scope": ""}, {"status": "refuted", "opposes": []}):
            with self.assertRaises(ValueError):
                self.mem._validate({"claims": [claim(eid, **changes)], "agenda": agenda()},
                                   self.mem.state(), self.mem.pending(), set())

    def test_stale_compiler_cannot_overwrite_newer_revision(self):
        self.node()
        self.mem.sync(self.tree)
        eid = self.mem.pending()[0]["id"]
        result = {"claims": [claim(eid)], "agenda": agenda()}
        other = ResearchMemory(self.cfg)

        def race():
            self.assertTrue(other.reflect(FakeUtility(result), force=True))
            return result

        self.assertFalse(self.mem.reflect(FakeUtility(race), force=True))
        self.assertEqual(self.mem.revision, other.revision)
        self.assertEqual(len(list((self.mem.root / "revisions").iterdir())), 1)

    def test_review_revises_interpretation_without_new_evidence(self):
        self.node()
        eid = self.publish()
        consumed = self.mem.state()["consumed"]
        result = {"claims": [claim(eid, status="untested")], "agenda": agenda()}
        self.assertTrue(self.mem.reflect(FakeUtility(result), force=True, review=True))
        self.assertEqual(self.mem.state()["consumed"], consumed)
        self.assertEqual(len(self.mem.packets()), 1)
        self.assertEqual(self.mem.state()["claims"]["spatial-assignment"]["status"], "untested")

    def test_source_ingestion_and_disabled_memory(self):
        source = self.base / "paper.md"
        source.write_text("Author reports an association, not a causal experiment.")
        eid = self.mem.ingest(source, "Paper, section 3")
        self.assertEqual(self.mem.ingest(source, "Paper, section 3"), eid)
        self.assertEqual(self.mem.packets()[0]["kind"], "source")
        self.cfg.memory.enabled = False
        disabled = ResearchMemory(self.cfg)
        self.assertEqual(disabled.context("paper"), "")
        self.assertEqual(disabled.sync(self.tree), 0)

    def test_end_to_end_workers_retries_and_compilation(self):
        from pi_rsi.orchestrator import Orchestrator
        task = self.cfg.task_dir
        (task / "starter").mkdir()
        (task / "starter" / "agent.py").write_text("def agent(obs):\n    return {}\n")
        (task / "eval" / "eval.py").write_text(
            "import argparse, json, runpy\n"
            "from pathlib import Path\n"
            "p=argparse.ArgumentParser()\n"
            "p.add_argument('--agent-dir');p.add_argument('--seedset');p.add_argument('--out')\n"
            "a=p.parse_args();runpy.run_path(str(Path(a.agent_dir)/'agent.py'))\n"
            "Path(a.out).write_text(json.dumps({'score':1.0}))\n")
        fake = str(Path(__file__).parent / "fake_agent.py")
        self.cfg.runner = RunnerCfg(kind="script", model=fake, node_timeout_s=30)
        self.cfg.utility = UtilityCfg(kind="script", model=fake, timeout_s=30)
        self.cfg.search = SearchCfg(width_root=2, width=1, depth=2, max_nodes=4,
                                    max_parallel=2, patience=10)
        self.cfg.task.final_seedset = ""
        self.cfg.hooks = HooksCfg(narrative=False)
        self.cfg.ops = OpsCfg(auto=False)
        self.cfg.research.enabled = False  # this regression exercises the original scheduler
        self.cfg.maintainer.enabled = False
        self.cfg.memory.reflect_every = 3
        orch = Orchestrator(self.cfg, verbose=False)
        reason = orch.run()
        self.assertEqual(reason, "max_nodes")
        self.assertTrue(any(n.attempt > 1 for n in orch.tree.non_root()))
        self.assertFalse(any(n.retry_of for n in orch.tree.non_root()))
        self.assertTrue(orch.memory.revision)
        self.assertEqual(orch.memory.pending(), [])
        events = [json.loads(s) for s in self.cfg.events_path.read_text().splitlines()]
        self.assertFalse([e for e in events if e["event"] == "memory_failed"])
        for n in orch.tree.non_root():
            self.assertTrue((self.cfg.nodes_dir / n.id / "memory.json").exists())
            prompt = (self.cfg.nodes_dir / n.id / "runner.prompt.md").read_text()
            self.assertNotIn("$research_memory", prompt)
            self.assertIn("Research memory", prompt)


class ResearchSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tree = Tree(Path(self.tmp.name) / "tree.json")
        self.cfg = SimpleNamespace(
            search=SearchCfg(width_root=2, max_nodes=20, patience=4),
            memory=MemoryCfg(research_every=1, patience_grace=2), nodes_dir=Path(self.tmp.name))
        self.memory = SimpleNamespace(enabled=True, revision="v2")
        self.calls = []
        self.utility = SimpleNamespace(plan_children=self.plan)
        self.orch = SimpleNamespace(cfg=self.cfg, tree=self.tree, memory=self.memory,
                                    utility=self.utility, log=lambda *a, **k: None)
        self.scheduler = Scheduler(self.orch)
        self.add("root", None, 0, 0)
        self.add("n001", "root", 1, 10)
        self.add("n002", "root", 1, 5)

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, nid, parent, depth, score):
        n = Node(nid, parent, depth, nid, "", status="done", score=score, proposals_revision="v2",
                 proposals=[self.proposal("ablate" if nid == "n002" else "idea")])
        self.tree.add(n)
        self.tree._counter = max(self.tree._counter, int(nid[1:]) if nid != "root" else 0)
        return n

    def proposal(self, kind="ablate"):
        return {"title": "new test", "hypothesis": "Compare explanations.", "type": kind,
                "research_question": "Is travel the cause?", "prediction": "Fewer walks.",
                "falsifier": "No walk-count difference."}

    def plan(self, parent, k):
        self.calls.append(parent.id)
        return [self.proposal()]

    def test_research_slot_can_choose_lower_scoring_branch(self):
        n = self.scheduler.next_node()
        self.assertEqual(n.parent, "n002")
        self.assertEqual(n.kind, "ablate")
        self.assertEqual(self.calls, [])

    def test_stale_queued_proposal_is_replanned_and_history_retained(self):
        parent = self.tree.get("n002")
        parent.proposals_revision = "v1"
        old = parent.proposals[0]
        n = self.scheduler.next_node()
        self.assertEqual(self.calls, ["n002"])
        self.assertEqual(parent.proposals[0], old)
        self.assertIn(0, parent.proposals_used)
        self.assertEqual(parent.proposals_revision, "v2")
        self.assertEqual(n.parent, parent.id)

    def test_exhausted_planner_reopens_after_new_evidence(self):
        n = self.tree.get("n002")
        n.proposals_used = [0, -1]
        n.proposals_revision = "v1"
        self.assertTrue(self.scheduler.expandable(n))
        n.proposals_revision = "v2"
        self.assertFalse(self.scheduler.expandable(n))

    def test_patience_grace_is_bounded_and_never_overrides_node_budget(self):
        for i in range(3, 8):
            n = self.add(f"n{i:03d}", "n001", 2, 1)
            self.tree.update(n, finished_at=f"2026-09-13T00:00:{i:02d}", delta_best=-9)
        self.assertIsNone(self.scheduler.stop_reason())
        n = self.add("n008", "n001", 2, 1)
        self.tree.update(n, finished_at="2026-09-13T00:00:08", delta_best=-9)
        self.assertEqual(self.scheduler.stop_reason(), "patience")
        self.cfg.search.max_nodes = 1
        self.assertEqual(self.scheduler.stop_reason(), "max_nodes")


if __name__ == "__main__":
    unittest.main()
