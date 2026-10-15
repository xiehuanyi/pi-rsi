"""The pi runner keeps every session inside the harness: no user extensions (background tasks, subagents)."""
import unittest
from pathlib import Path

from pi_rsi.runner.pi import PiRunner


class PiCommandTests(unittest.TestCase):
    def test_sessions_disable_user_extensions(self):
        r = PiRunner("openai-codex/gpt-6-luna", "low")
        for cmd in (r.build_agent_cmd(Path("p"), Path("."), 10, Path("s")),
                    r.build_json_cmd(Path("p"), Path("."), None, Path("s"))):
            self.assertIn("--no-extensions", cmd)


if __name__ == "__main__":
    unittest.main()
