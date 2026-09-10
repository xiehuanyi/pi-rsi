"""Runner: a headless coding-agent process (grok CLI or pi) supervised with wall-clock and idle timeouts.

Every runner writes the raw event stream to `log_path` (JSONL) and reports progress through `on_event`
so the orchestrator can keep a heartbeat without an LLM in the loop.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class RunResult:
    ok: bool
    exit_code: int | None
    final_text: str = ""
    stop_reason: str = ""
    timed_out: bool = False
    idle_killed: bool = False
    duration_s: float = 0.0
    usage: dict[str, Any] = field(default_factory=dict)
    cost_usd: float | None = None
    session_id: str | None = None
    num_turns: int | None = None
    tool_calls: int = 0
    structured: Any = None
    error: str = ""
    log_path: str = ""


class Runner:
    kind = "base"

    def __init__(self, model: str, effort: str = "high", extra_args: list[str] | None = None):
        self.model = model
        self.effort = effort
        self.extra_args = list(extra_args or [])

    # subclasses implement these ---------------------------------------
    def build_agent_cmd(self, prompt_file: Path, cwd: Path, max_turns: int, session_dir: Path,
                        session_id: str | None = None) -> list[str]:
        raise NotImplementedError

    def new_session_id(self) -> str | None:
        """Runners that can pre-assign a session id return one so a killed session can still be resumed."""
        return None

    def build_json_cmd(self, prompt_file: Path, cwd: Path, schema: dict | None, session_dir: Path) -> list[str]:
        raise NotImplementedError

    def build_resume_cmd(self, session_id: str, prompt_file: Path, cwd: Path, max_turns: int, session_dir: Path) -> list[str]:
        raise NotImplementedError

    def parse_event(self, line: str, state: dict[str, Any]) -> None:
        """Update `state` (final_text, usage, stop_reason, session_id, tool_calls, structured, num_turns)."""
        raise NotImplementedError

    def env(self) -> dict[str, str]:
        return dict(os.environ)

    # shared supervision ---------------------------------------------------
    def _supervise(self, cmd: list[str], cwd: Path, log_path: Path, timeout_s: float, idle_timeout_s: float,
                   on_event: Callable[[dict[str, Any]], None] | None, session_id: str | None = None) -> RunResult:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        state: dict[str, Any] = {"final_text": "", "usage": {}, "stop_reason": "", "session_id": session_id,
                                 "tool_calls": 0, "structured": None, "num_turns": None, "cost_usd": None,
                                 "text_parts": []}
        last_activity = [time.time()]
        start = time.time()
        stderr_path = log_path.with_suffix(".stderr")
        with open(log_path, "a", encoding="utf-8") as log, open(stderr_path, "a", encoding="utf-8") as errf:
            log.write(json.dumps({"rsi": "start", "cmd": cmd, "cwd": str(cwd), "t": start}) + "\n")
            log.flush()
            try:
                proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=errf, stdin=subprocess.DEVNULL,
                                        text=True, encoding="utf-8", errors="replace", env=self.env(),
                                        start_new_session=True, bufsize=1)
            except FileNotFoundError as e:
                return RunResult(ok=False, exit_code=None, error=f"runner binary not found: {e}", log_path=str(log_path))

            whole: list[str] = []

            def reader():
                assert proc.stdout is not None
                for line in proc.stdout:
                    last_activity[0] = time.time()
                    whole.append(line)
                    log.write(line if line.endswith("\n") else line + "\n")
                    log.flush()
                    try:
                        self.parse_event(line, state)
                    except Exception:  # multi-line JSON (pretty-printed) is handled after exit
                        pass
                    if on_event:
                        try:
                            on_event({"t": time.time(), "state": state})
                        except Exception:
                            pass

            th = threading.Thread(target=reader, daemon=True)
            th.start()
            timed_out = idle_killed = False
            while proc.poll() is None:
                time.sleep(1.0)
                now = time.time()
                if now - start > timeout_s:
                    timed_out = True
                    self._kill(proc)
                    break
                if now - last_activity[0] > idle_timeout_s:
                    idle_killed = True
                    self._kill(proc)
                    break
            th.join(timeout=30)
            exit_code = proc.poll()
            duration = time.time() - start
            if not state["stop_reason"] and state["structured"] is None:
                # --output-format json prints one pretty-printed object: parse the whole stream at once
                try:
                    obj = json.loads("".join(whole))
                    if isinstance(obj, dict):
                        self.parse_event(json.dumps(obj), state)
                except Exception:
                    pass
            log.write(json.dumps({"rsi": "end", "exit_code": exit_code, "timed_out": timed_out,
                                  "idle_killed": idle_killed, "duration_s": duration}) + "\n")
        final_text = state["final_text"] or "".join(state["text_parts"])
        ok = (exit_code == 0) and not timed_out and not idle_killed
        return RunResult(ok=ok, exit_code=exit_code, final_text=final_text, stop_reason=state["stop_reason"],
                         timed_out=timed_out, idle_killed=idle_killed, duration_s=duration, usage=state["usage"],
                         cost_usd=state["cost_usd"], session_id=state["session_id"], num_turns=state["num_turns"],
                         tool_calls=state["tool_calls"], structured=state["structured"], log_path=str(log_path),
                         error=("timeout" if timed_out else "idle" if idle_killed else ("" if exit_code == 0 else f"exit {exit_code}")))

    @staticmethod
    def _kill(proc: subprocess.Popen) -> None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        for _ in range(15):
            if proc.poll() is not None:
                return
            time.sleep(1)
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    # public API -----------------------------------------------------------
    def run_agent(self, prompt: str, cwd: Path, log_path: Path, *, max_turns: int, timeout_s: float,
                  idle_timeout_s: float, on_event: Callable | None = None) -> RunResult:
        session_dir = log_path.parent / "sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        prompt_file = log_path.parent / (log_path.stem + ".prompt.md")
        prompt_file.write_text(prompt, encoding="utf-8")
        sid = self.new_session_id()
        cmd = self.build_agent_cmd(prompt_file, cwd, max_turns, session_dir, sid)
        return self._supervise(cmd, cwd, log_path, timeout_s, idle_timeout_s, on_event, session_id=sid)

    def resume_agent(self, session_id: str, prompt: str, cwd: Path, log_path: Path, *, max_turns: int, timeout_s: float,
                     idle_timeout_s: float, on_event: Callable | None = None) -> RunResult:
        session_dir = log_path.parent / "sessions"
        prompt_file = log_path.parent / (log_path.stem + ".prompt.md")
        prompt_file.write_text(prompt, encoding="utf-8")
        cmd = self.build_resume_cmd(session_id, prompt_file, cwd, max_turns, session_dir)
        return self._supervise(cmd, cwd, log_path, timeout_s, idle_timeout_s, on_event)

    def ask_json(self, prompt: str, cwd: Path, log_path: Path, *, schema: dict | None = None,
                 timeout_s: float = 600) -> tuple[Any, RunResult]:
        """Single-turn, no-tools call returning parsed JSON (structured output when the runner supports it)."""
        from ..util import parse_json_loose
        session_dir = log_path.parent / "sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        prompt_file = log_path.parent / (log_path.stem + ".prompt.md")
        prompt_file.write_text(prompt, encoding="utf-8")
        cmd = self.build_json_cmd(prompt_file, cwd, schema, session_dir)
        res = self._supervise(cmd, cwd, log_path, timeout_s, timeout_s, None)
        data = res.structured
        if data is None and res.final_text:
            try:
                data = parse_json_loose(res.final_text)
            except ValueError as e:
                res.error = res.error or f"no JSON in output: {e}"
        if data is None:
            res.ok = False
        return data, res


def make_runner(kind: str, model: str, effort: str, extra_args: list[str] | None = None) -> Runner:
    if kind == "grok":
        from .grok import GrokRunner
        return GrokRunner(model, effort, extra_args)
    if kind == "pi":
        from .pi import PiRunner
        return PiRunner(model, effort, extra_args)
    if kind == "script":
        from .script import ScriptRunner
        return ScriptRunner(model, effort, extra_args)
    raise ValueError(f"unknown runner kind: {kind}")
