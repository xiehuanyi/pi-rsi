"""Grok CLI (xAI 'Grok Build') headless runner. Uses the official CLI so the user's subscription login applies."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from .base import Runner


class GrokRunner(Runner):
    kind = "grok"

    def __init__(self, model: str, effort: str = "high", extra_args: list[str] | None = None):
        super().__init__(model, effort, extra_args)
        self.binary = os.environ.get("RSI_GROK_BIN") or shutil.which("grok") or "grok"

    def _common(self, cwd: Path) -> list[str]:
        return [self.binary, "--always-approve", "--no-subagents", "--disable-web-search", "--no-plan",
                "--verbatim", "-m", self.model, "--reasoning-effort", self.effort, "--cwd", str(cwd), *self.extra_args]

    def new_session_id(self) -> str | None:
        import uuid
        return str(uuid.uuid4())

    def build_agent_cmd(self, prompt_file: Path, cwd: Path, max_turns: int, session_dir: Path,
                        session_id: str | None = None) -> list[str]:
        cmd = [*self._common(cwd), "--prompt-file", str(prompt_file), "--output-format", "streaming-json",
               "--max-turns", str(max_turns)]
        if session_id:
            cmd += ["--session-id", session_id]
        return cmd

    def build_resume_cmd(self, session_id: str, prompt_file: Path, cwd: Path, max_turns: int, session_dir: Path) -> list[str]:
        return [*self._common(cwd), "--resume", session_id, "--prompt-file", str(prompt_file), "--output-format",
                "streaming-json", "--max-turns", str(max_turns)]

    def build_json_cmd(self, prompt_file: Path, cwd: Path, schema: dict | None, session_dir: Path) -> list[str]:
        cmd = [*self._common(cwd), "--prompt-file", str(prompt_file), "--output-format", "json", "--tools", "",
               "--max-turns", "1"]
        if schema:
            cmd += ["--json-schema", json.dumps(schema)]
        return cmd

    def env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.setdefault("GROK_NO_UPDATE_CHECK", "1")
        return env

    def parse_event(self, line: str, state: dict[str, Any]) -> None:
        line = line.strip()
        if not line.startswith("{"):
            return
        d = json.loads(line)
        t = d.get("type")
        if t == "text":
            state["text_parts"].append(d.get("data", ""))
        elif t == "tool_call":
            state["tool_calls"] += 1
        elif t == "end":
            state["stop_reason"] = d.get("stopReason", "")
            state["session_id"] = d.get("sessionId")
            state["usage"] = d.get("usage", {}) or {}
            state["num_turns"] = d.get("num_turns")
            state["cost_usd"] = d.get("total_cost_usd")
            if d.get("structuredOutput") is not None:
                state["structured"] = d["structuredOutput"]
        elif "stopReason" in d and "text" in d:  # --output-format json (single object)
            state["final_text"] = d.get("text", "")
            state["stop_reason"] = d.get("stopReason", "")
            state["session_id"] = d.get("sessionId")
            state["usage"] = d.get("usage", {}) or {}
            state["num_turns"] = d.get("num_turns")
            state["cost_usd"] = d.get("total_cost_usd")
            if d.get("structuredOutput") is not None:
                state["structured"] = d["structuredOutput"]
