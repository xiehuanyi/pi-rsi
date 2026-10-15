"""Task objective: the default research prompts stay unchanged; competition tasks get the score-first playbook."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pi_rsi import prompts as P
from pi_rsi.config import TaskCfg, load_experiment, load_task_cfg, write_experiment_toml
from pi_rsi.memory_prompts import reflection_prompt
from pi_rsi.orchestrator import Orchestrator
from pi_rsi.tree import Node
from pi_rsi.util import atomic_write_json

from test_research_loop import make_cfg

PLAYBOOK = "Competition mode: climb the official score"
RESEARCH_RIGOR = "A numerical improvement or heuristic noise floor is not a meaningful discovery."
ABLATION_RULE = "At least one proposal should be a discriminating ablation"


class ObjectiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = make_cfg(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def prompts(self, objective):
        self.cfg.task.objective = objective
        orch = Orchestrator(self.cfg, verbose=False)
        orch.tree.nodes["root"] = Node("root", None, 0, "baseline", "", status="done", score=0.5, commit="c0")
        node = Node("n001", "root", 1, "an idea", "do the idea", status="running")
        orch.tree.nodes["n001"] = node
        self.cfg.research.enabled = False  # workers propose next steps only in the legacy scheduler
        worker = P.worker_prompt(self.cfg, orch.tree, node, self.cfg.dir / "wt")
        self.cfg.research.enabled = True
        research_worker = P.worker_prompt(self.cfg, orch.tree, node, self.cfg.dir / "wt")
        self.assertNotIn("proposals.json", research_worker)
        self.assertEqual(PLAYBOOK in research_worker, objective == "competition")
        snapshot = orch.research._snapshot(orch.scheduler)
        cycle = orch.research._new_cycle()
        atomic_write_json(cycle / "snapshot.json", snapshot)
        think = orch.research._review_prompt(snapshot, cycle, "fixture review")
        reflect, _ = reflection_prompt(orch.memory, orch.memory.state(), [])
        return worker, think, reflect

    def test_research_objective_keeps_mechanism_first_prompts(self):
        worker, think, reflect = self.prompts("research")
        self.assertIn(ABLATION_RULE, worker)
        self.assertIn(RESEARCH_RIGOR, think)
        for text in (worker, think, reflect):
            self.assertNotIn(PLAYBOOK, text)
            self.assertNotIn("OBJECTIVE: competition", text)

    def test_competition_objective_injects_score_first_playbook(self):
        worker, think, reflect = self.prompts("competition")
        self.assertIn(PLAYBOOK, worker)
        self.assertIn("Rank proposals by expected official-score gain", worker)
        self.assertNotIn(ABLATION_RULE, worker)
        self.assertIn(PLAYBOOK, think)
        self.assertIn("Judge candidates by expected official-score gain", think)
        self.assertNotIn(RESEARCH_RIGOR, think)
        self.assertIn("OBJECTIVE: competition", reflect)
        for text in (worker, think):
            self.assertNotIn("$objective_block", text)
            self.assertNotIn("$proposal_rule", text)

    def test_objective_does_not_change_wiki_or_evaluation_identity(self):
        from pi_rsi.memory import ResearchMemory
        from pi_rsi.monitor import evaluation_identity
        import subprocess
        subprocess.run(["git", "init", "-q", str(self.cfg.dir)], check=True)
        subprocess.run(["git", "-C", str(self.cfg.dir), "-c", "user.name=t", "-c", "user.email=t@t",
                        "commit", "-q", "--allow-empty", "-m", "init"], check=True)
        ids = {}
        for objective in ("research", "competition"):
            self.cfg.task.objective = objective
            ids[objective] = (ResearchMemory(self.cfg).protocol,
                              json.dumps(evaluation_identity(self.cfg, self.cfg.dir, ["x"]), sort_keys=True))
        self.assertEqual(ids["research"], ids["competition"])

    def test_objective_is_validated_and_round_trips_through_toml(self):
        with self.assertRaises(ValueError):
            TaskCfg(objective="leaderboard")
        task = Path(self.cfg.task.dir)
        (task / "task.toml").write_text('name = "fixture"\n[task]\nobjective = "competition"\n')
        self.assertTrue(load_task_cfg(task).competition)
        self.cfg.task.objective = "competition"
        write_experiment_toml(self.cfg)
        self.assertEqual(load_experiment(self.cfg.dir).task.objective, "competition")


if __name__ == "__main__":
    unittest.main()
