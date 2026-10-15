"""Protect the comparison's isolation, held-out panel, immutable plan and locking gate."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

from pi_rsi.config import ExperimentCfg, TaskCfg, write_experiment_toml, load_experiment
from pi_rsi.util import atomic_write_json, read_json

spec = importlib.util.spec_from_file_location("campaign", Path(__file__).resolve().parents[1] / "scripts/memory_campaign.py")
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)


class CampaignTests(unittest.TestCase):
    def test_panels_disjoint_and_reproducible(self):
        old = [1, 10001, 4409]
        panel = campaign.seeded_panels(old)
        self.assertEqual(panel, campaign.seeded_panels(old))
        groups = [panel[r][s] for r in ("r1", "r2") for s in ("smoke", "quick", "validation")]
        groups.append(panel["confirmation"])
        flat = sum(groups, [])
        self.assertEqual(len(flat), 82)
        self.assertEqual(len(set(flat)), 82)
        self.assertFalse(set(flat) & set(old))
        self.assertEqual(len(panel["confirmation"]), 48)

    def test_protocol_does_not_mutate_prior_or_expose_old_paths(self):
        old = {"id": "old", "sources": {"x": {"path": "/other/run", "sha256": "abc"}}, "seeds": {"confirmation": [1]}}
        before = copy.deepcopy(old)
        new = campaign.protocol_with_seeds(old, {"confirmation": []}, "search")
        self.assertEqual(old, before)
        self.assertNotEqual(new["id"], old["id"])
        self.assertNotIn("path", new["sources"]["x"])
        self.assertEqual(new["sources"]["x"]["sha256"], "abc")

    def test_initialize_has_balanced_budgets_and_empty_independent_wikis(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            task = base / "task"
            for name in ("starter", "docs", "eval", ".venv"):
                (task / name).mkdir(parents=True)
            (task / "TASK.md").write_text("test task")
            (task / "task.toml").write_text("[task]\nname='test'\n")
            (task / "eval/eval.py").write_text("pass\n")
            atomic_write_json(task / "eval/protocol.json", {"id": "old", "seeds": {"quick": [1], "confirmation": [2]}})
            template = base / "template"
            template.mkdir()
            write_experiment_toml(ExperimentCfg("test", template, TaskCfg(dir=str(task))))
            dest = base / "campaign"
            plan = campaign.initialize(dest, template)
            campaign.verify_frozen(dest, plan)
            configs = [load_experiment(Path(r["path"])) for r in plan["runs"]]
            self.assertEqual(len(configs), 6)
            self.assertEqual(len({c.memory.path for c in configs}), 6)
            self.assertFalse((dest / "wikis").exists())
            self.assertEqual({c.search.max_nodes for c in configs}, {24})
            self.assertEqual({c.search.max_wallclock_s for c in configs}, {21600})
            self.assertEqual({c.memory.patience_grace for c in configs}, {0})
            for run, cfg in zip(plan["runs"], configs):
                self.assertEqual(cfg.memory.enabled, run["arm"] != "A")
                self.assertEqual(cfg.memory.research_every, 3 if run["arm"] == "C" else 0)
                self.assertEqual(read_json(cfg.task_dir / "eval/protocol.json")["seeds"]["confirmation"], [])
            with self.assertRaisesRegex(ValueError, "all six runs"):
                campaign.lock_candidates(dest, plan)
            self.assertFalse((dest / "LOCK.json").exists())
            changed = configs[0].task_dir / "eval/eval.py"
            changed.write_text("changed\n")
            with self.assertRaisesRegex(ValueError, "frozen files changed"):
                campaign.verify_frozen(dest, plan)
            with self.assertRaisesRegex(ValueError, "already exists"):
                campaign.initialize(dest, template)

    def test_token_count_includes_utility_and_rescue(self):
        self.assertEqual(campaign.tokens({"worker": {"input_tokens": 7, "output_tokens": 3},
                                          "utility": {"input_tokens": 8, "output_tokens": 2},
                                          "rescue": {"input_tokens": 6, "output_tokens": 1}}), 27)


if __name__ == "__main__":
    unittest.main()
