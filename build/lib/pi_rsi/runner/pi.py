"""pi coding agent runner (headless JSON mode). Model is given as provider/model[:thinking]."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .base import Runner

_PKG_ROOT = Path(__file__).resolve().parents[2]


class PiRunner(Runner):
    kind = "pi"

    def __init__(self, model: str, effort: str = "high", extra_args: list[str] | None = None):
        super().__init__(model, effort, extra_args)
        local = _PKG_ROOT / "node_modules" / ".bin" / "pi"
        import shutil
        self.binary = os.environ.get("RSI_PI_BIN") or (str(local) if local.exists() else (shutil.which("pi") or "pi"))

    def _model_arg(self) -> str:
        return f"{self.model}:{self.effort}" if self.effort and ":" not in self.model else self.model

    def _common(self, session_dir: Path) -> list[str]:
        return [self.binary, "--mode", "json", "--model", self._model_arg(), "--session-dir", str(session_dir),
                "--no-skills", "--no-prompt-templates", "--no-context-files", *self.extra_args]

    def build_agent_cmd(self, prompt_file: Path, cwd: Path, max_turns: int, session_dir: Path,
                        session_id: str | None = None) -> list[str]:
        prompt = prompt_file.read_text(encoding="utf-8")
        return [*self._common(session_dir), "--", prompt]

    def build_resume_cmd(self, session_id: str, prompt_file: Path, cwd: Path, max_turns: int, session_dir: Path) -> list[str]:
        prompt = prompt_file.read_text(encoding="utf-8")
        # pi writes one JSONL per session under session_dir; resume the newest one when no id is known
        target = session_id
        files = sorted(session_dir.rglob("*.jsonl"), key=lambda f: f.stat().st_mtime)
        if files and (not session_id or not any(session_id in f.name for f in files)):
            target = str(files[-1])
        return [*self._common(session_dir), "--session", target, "--", prompt]

    def build_json_cmd(self, prompt_file: Path, cwd: Path, schema: dict | None, session_dir: Path) -> list[str]:
        prompt = prompt_file.read_text(encoding="utf-8")
        if schema:
            prompt += "\n\nOutput ONLY a JSON document matching this JSON schema, no prose:\n" + json.dumps(schema)
        return [*self._common(session_dir), "--no-tools", "--", prompt]

    def env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["PI_OFFLINE"] = "1"
        env["PI_SKIP_VERSION_CHECK"] = "1"
        env["PI_TELEMETRY"] = "0"
        return env

    def parse_event(self, line: str, state: dict[str, Any]) -> None:
        line = line.strip()
        if not line.startswith("{"):
            return
        d = json.loads(line)
        t = d.get("type")
        if t == "session":
            state["session_id"] = d.get("id")
        elif t == "tool_execution_start":
            state["tool_calls"] += 1
        elif t == "message_end":
            msg = d.get("message", {})
            if msg.get("role") == "assistant":
                texts = [c.get("text", "") for c in msg.get("content", []) if c.get("type") == "text"]
                if texts:
                    state["final_text"] = "".join(texts)
                if msg.get("usage"):
                    u = msg["usage"]
                    agg = state["usage"]
                    for k in ("input", "output", "cacheRead", "cacheWrite", "totalTokens"):
                        if isinstance(u.get(k), (int, float)):
                            agg[k] = agg.get(k, 0) + u[k]
                    if isinstance(u.get("cost"), dict) and isinstance(u["cost"].get("total"), (int, float)):
                        state["cost_usd"] = (state["cost_usd"] or 0) + u["cost"]["total"]
                if msg.get("stopReason"):
                    state["stop_reason"] = msg["stopReason"]
        elif t == "turn_end":
            state["num_turns"] = (state["num_turns"] or 0) + 1
