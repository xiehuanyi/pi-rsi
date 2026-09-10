"""Small shared helpers: atomic JSON, timestamps, jsonl logging, subprocess."""
from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

_LOCK = threading.RLock()


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def now_ts() -> float:
    return _dt.datetime.now(_dt.timezone.utc).timestamp()


def read_json(path: Path, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def atomic_write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_text(path, json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=False) + "\n")


def append_jsonl(path: Path, obj: Any) -> None:
    with _LOCK:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def append_text(path: Path, text: str) -> None:
    with _LOCK:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)


def read_text(path: Path, default: str = "") -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return default


def tail_text(path: Path, max_lines: int = 200, max_chars: int = 20000) -> str:
    text = read_text(path)
    lines = text.splitlines()[-max_lines:]
    out = "\n".join(lines)
    return out[-max_chars:]


def run_cmd(cmd: list[str] | str, cwd: Path | None = None, timeout: float | None = None,
            env: dict | None = None, check: bool = False) -> subprocess.CompletedProcess:
    shell = isinstance(cmd, str)
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, shell=shell, capture_output=True,
                          text=True, timeout=timeout, env=env, check=check)


def strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        first_nl = t.find("\n")
        t = t[first_nl + 1:] if first_nl != -1 else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def parse_json_loose(text: str) -> Any:
    """Parse JSON from model output: tolerate code fences and leading/trailing prose."""
    t = strip_code_fence(text)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    # find first { or [ and matching end
    for opener, closer in (("{", "}"), ("[", "]")):
        i = t.find(opener)
        j = t.rfind(closer)
        if i != -1 and j != -1 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("no JSON found in model output")


def fmt_score(x: Any) -> str:
    if x is None:
        return "-"
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return str(x)
    if abs(xf) >= 1000:
        return f"{xf:,.0f}"
    return f"{xf:.4g}"


def human_duration(s: float | None) -> str:
    if s is None:
        return "-"
    s = int(s)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"
