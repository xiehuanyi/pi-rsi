"""Script runner for harness tests: `model` is an executable run in the worktree with the prompt path in env.
No LLM involved. The script may print JSON lines; a final line {"type":"end", ...} is optional."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .base import Runner


class ScriptRunner(Runner):
    kind = "script"

    def build_agent_cmd(self, prompt_file: Path, cwd: Path, max_turns: int, session_dir: Path,
                        session_id: str | None = None) -> list[str]:
        return [self.model, str(prompt_file), "agent"]

    def build_resume_cmd(self, session_id: str, prompt_file: Path, cwd: Path, max_turns: int, session_dir: Path) -> list[str]:
        return [self.model, str(prompt_file), "resume"]

    def build_json_cmd(self, prompt_file: Path, cwd: Path, schema: dict | None, session_dir: Path) -> list[str]:
        return [self.model, str(prompt_file), "json"]

    def env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["RSI_SCRIPT_EFFORT"] = self.effort
        return env

    def parse_event(self, line: str, state: dict[str, Any]) -> None:
        line = line.strip()
        if not line.startswith("{"):
            state["text_parts"].append(line + "\n")
            return
        d = json.loads(line)
        if d.get("type") == "end":
            state["stop_reason"] = d.get("stopReason", "end_turn")
            state["structured"] = d.get("structuredOutput")
            state["usage"] = d.get("usage", {})
        elif d.get("type") == "text":
            state["text_parts"].append(d.get("data", ""))
