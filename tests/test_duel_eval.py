"""Outcome scoring contract: ties, failures, paired uncertainty, and import isolation."""
import tempfile
import unittest
from pathlib import Path

from pi_rsi.duel_eval import load_agent, outcome, summarize


class DuelEvaluationTests(unittest.TestCase):
    def test_outcomes_ignore_margin_and_candidate_errors_lose(self):
        self.assertEqual(outcome("DONE", "DONE", 100, 99), 1)
        self.assertEqual(outcome("DONE", "DONE", 100000, 99), 1)
        self.assertEqual(outcome("DONE", "DONE", 100, 100), 0.5)
        self.assertEqual(outcome("ERROR", "DONE", 100000, 99), 0)
        with self.assertRaises(ValueError):
            outcome("DONE", "ERROR", 100, 0)

    def test_paired_blocks_keep_seats_and_opponents_together(self):
        rows = []
        for seed in (1, 2):
            for opp in ("strong", "weak"):
                for seat in (0, 1):
                    value = (1.0 if opp == "weak" else 0.0) if seed == 1 else 0.5
                    rows.append({"seed": seed, "seat": seat, "opponent": opp, "value": value,
                                 "money": 10, "opp_money": 10, "status": "DONE", "max_action_s": 0.1})
        result = summarize(rows, {"id": "panel-v1"}, "validation")
        self.assertEqual(result["score"], 0.5)
        self.assertEqual(result["per_item"], [{"id": "panel-v1:1", "value": 0.5},
                                             {"id": "panel-v1:2", "value": 0.5}])
        self.assertEqual(result["score_sem"], 0)
        self.assertEqual(result["per_opponent"]["strong"]["score"], 0.25)
        self.assertEqual(result["n_games"], 8)

    def test_fresh_state_and_dataclasses_supported(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "agent.py"
            path.write_text("from dataclasses import dataclass\n"
                            "@dataclass\nclass State:\n    value:int=0\n"
                            "state=State()\ndef agent(obs):\n"
                            "    state.value+=1\n    return state.value\n")
            first = load_agent(path, "duel_test_a")
            second = load_agent(path, "duel_test_b")
            self.assertEqual(first({}), 1)
            self.assertEqual(first({}), 2)
            self.assertEqual(second({}), 1)


if __name__ == "__main__":
    unittest.main()
