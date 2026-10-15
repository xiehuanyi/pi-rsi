"""Transient utility failures must not reset the timeout or disappear from accounting."""
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from pi_rsi.agents import Utility
from pi_rsi.runner import RunResult
from pi_rsi.runner.grok import GrokRunner


class UtilityRetryTests(unittest.TestCase):
    def make_utility(self, path, responses):
        runner = Mock()
        runner.ask_json.side_effect = responses
        orch = SimpleNamespace(cfg=SimpleNamespace(nodes_dir=path / "nodes", dir=path,
                                utility=SimpleNamespace(timeout_s=60)), utility_runner=runner,
                                log=Mock(), add_cost=Mock(), stop_flag=threading.Event())
        return Utility(orch), orch

    def test_retry_keeps_first_failure_cost_and_remaining_timeout(self):
        with tempfile.TemporaryDirectory() as d:
            failed = RunResult(ok=False, exit_code=1, error="max turns reached", duration_s=10)
            passed = RunResult(ok=True, exit_code=0, duration_s=5)
            utility, orch = self.make_utility(Path(d), [(None, failed), ({"ok": True}, passed)])
            with patch("pi_rsi.agents.time.monotonic", side_effect=[0, 0, 10]):
                self.assertEqual(utility._ask("test", "prompt", {}), {"ok": True})
            calls = orch.utility_runner.ask_json.call_args_list
            self.assertEqual([c.kwargs["timeout_s"] for c in calls], [60, 50])
            self.assertNotEqual(calls[0].kwargs["log_path"], calls[1].kwargs["log_path"])
            self.assertEqual(orch.add_cost.call_count, 2)

    def test_timeout_does_not_get_a_fresh_retry_budget(self):
        with tempfile.TemporaryDirectory() as d:
            failed = RunResult(ok=False, exit_code=1, timed_out=True)
            utility, orch = self.make_utility(Path(d), [(None, failed)])
            with patch("pi_rsi.agents.time.monotonic", side_effect=[0, 0, 61]):
                with self.assertRaises(RuntimeError):
                    utility._ask("test", "prompt", {})
            self.assertEqual(orch.utility_runner.ask_json.call_count, 1)

    def test_retries_bounded_and_interrupt_respected(self):
        with tempfile.TemporaryDirectory() as d:
            failed = RunResult(ok=False, exit_code=1)
            utility, orch = self.make_utility(Path(d), [(None, failed), (None, failed)])
            with self.assertRaises(RuntimeError):
                utility._ask("test", "prompt", {})
            self.assertEqual(orch.utility_runner.ask_json.call_count, 2)
            utility, orch = self.make_utility(Path(d), [(None, failed)])
            orch.stop_flag.set()
            with self.assertRaises(RuntimeError):
                utility._ask("test", "prompt", {})
            self.assertEqual(orch.utility_runner.ask_json.call_count, 1)

    def test_grok_structured_output_has_bounded_internal_turns_and_no_tools(self):
        cmd = GrokRunner("grok-4.5").build_json_cmd(Path("prompt"), Path("."), {}, Path("."))
        self.assertEqual(cmd[cmd.index("--max-turns") + 1], "3")
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")


if __name__ == "__main__":
    unittest.main()
