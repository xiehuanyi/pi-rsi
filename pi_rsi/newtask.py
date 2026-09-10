"""`rsi new-task`: the clarification phase. Problem statement -> data profile -> questions to the human -> confirmed
decisions -> a builder agent writes and verifies a task pack -> the harness re-verifies the evaluator on the starter."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import prompts as P
from .config import load_task_cfg, ExperimentCfg, RunnerCfg, UtilityCfg, SearchCfg
from .home import tasks_dir
from .runner import make_runner
from .util import now_iso, parse_json_loose, read_text, atomic_write_text


CLARIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "understanding": {"type": "string"},
        "deliverable_options": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "title": {"type": "string"}, "description": {"type": "string"}}, "required": ["id", "title", "description"]}},
        "metric_options": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "name": {"type": "string"}, "direction": {"type": "string", "enum": ["higher", "lower"]},
            "rationale": {"type": "string"}}, "required": ["id", "name", "direction", "rationale"]}},
        "protocol": {"type": "object", "properties": {"quick": {"type": "string"}, "validation": {"type": "string"}, "final": {"type": "string"}},
                     "required": ["quick", "validation", "final"]},
        "questions": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "question": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}},
            "default": {"type": "string"}}, "required": ["id", "question", "options", "default"]}},
        "risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["understanding", "deliverable_options", "metric_options", "protocol", "questions", "risks"],
}


def fetch_data(task_dir: Path, data: str | None) -> Path | None:
    raw = task_dir / "data" / "raw"
    if not data:
        return None
    raw.mkdir(parents=True, exist_ok=True)
    if data.startswith("kaggle:"):
        comp = data.split(":", 1)[1]
        subprocess.run(["kaggle", "competitions", "download", "-c", comp, "-p", str(raw)], check=True)
        for z in raw.glob("*.zip"):
            subprocess.run(["unzip", "-oq", str(z), "-d", str(raw)], check=True)
        (task_dir / "data" / "SOURCE.md").write_text(f"kaggle competition: {comp}\n")
    else:
        src = Path(data).expanduser().resolve()
        if src.is_dir():
            shutil.copytree(src, raw, dirs_exist_ok=True)
        else:
            shutil.copy2(src, raw / src.name)
        (task_dir / "data" / "SOURCE.md").write_text(f"copied from: {src}\n")
    return raw


def profile_data(raw: Path | None, max_chars: int = 6000) -> str:
    if raw is None or not raw.exists():
        return "(no data provided)"
    lines = []
    for f in sorted(raw.rglob("*")):
        if f.is_dir() or f.suffix == ".zip":
            continue
        rel = f.relative_to(raw)
        size = f.stat().st_size
        lines.append(f"- {rel} ({size/1024:.0f} KB)")
        if f.suffix.lower() in (".csv", ".tsv") and size < 500_000_000:
            try:
                import csv
                with open(f, newline="", encoding="utf-8", errors="replace") as fh:
                    reader = csv.reader(fh, delimiter="\t" if f.suffix.lower() == ".tsv" else ",")
                    header = next(reader)
                    rows = [next(reader) for _ in range(3)]
                    n = 3 + sum(1 for _ in reader)
                lines.append(f"  rows={n} cols={len(header)}")
                lines.append("  columns: " + ", ".join(header[:60]) + (" ..." if len(header) > 60 else ""))
                for r in rows:
                    lines.append("  sample: " + ", ".join(x[:24] for x in r[:20]))
            except Exception as e:
                lines.append(f"  (could not parse: {e})")
        elif f.suffix.lower() in (".txt", ".md", ".json") and size < 200_000:
            lines.append("  head: " + read_text(f)[:600].replace("\n", " | "))
    out = "\n".join(lines)
    return out[:max_chars] + ("\n...(truncated)" if len(out) > max_chars else "")


def ask_human(clar: dict[str, Any], answers: dict[str, str] | None, yes: bool) -> dict[str, Any]:
    """Interactive Q&A on the terminal unless answers are given or --yes accepts the defaults."""
    answers = dict(answers or {})
    decisions: dict[str, Any] = {}

    def choose(key: str, prompt: str, options: list[str], default: str) -> str:
        if key in answers:
            return answers[key]
        if yes or not sys.stdin.isatty():
            return default
        print(f"\n{prompt}")
        for i, o in enumerate(options, 1):
            print(f"  {i}. {o}{'   (default)' if o == default else ''}")
        raw = input("> ").strip()
        if not raw:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        return raw

    print("\n== understanding ==\n" + clar["understanding"])
    print("\n== protocol ==\n" + "\n".join(f"- {k}: {v}" for k, v in clar["protocol"].items()))
    if clar.get("risks"):
        print("\n== risks ==\n" + "\n".join(f"- {r}" for r in clar["risks"]))
    d_opts = [f"{o['id']}: {o['title']} — {o['description']}" for o in clar["deliverable_options"]]
    decisions["deliverable"] = choose("deliverable", "Deliverable?", d_opts, d_opts[0])
    m_opts = [f"{o['id']}: {o['name']} ({o['direction']} is better) — {o['rationale']}" for o in clar["metric_options"]]
    decisions["metric"] = choose("metric", "Metric?", m_opts, m_opts[0])
    for q in clar["questions"]:
        decisions[q["id"]] = choose(q["id"], q["question"], list(q["options"]), q["default"])
    decisions["protocol"] = clar["protocol"]
    return decisions


def new_task(name: str, problem: str, data: str | None, runner_kind: str, model: str, effort: str, utility_model: str,
             utility_effort: str, yes: bool = False, answers: dict[str, str] | None = None, max_turns: int = 120,
             timeout_s: int = 3600) -> Path:
    task_dir = tasks_dir() / name
    if (task_dir / "task.toml").exists():
        raise FileExistsError(f"task pack already exists: {task_dir}")
    task_dir.mkdir(parents=True, exist_ok=True)
    log_dir = task_dir / "_newtask"
    log_dir.mkdir(exist_ok=True)
    raw = fetch_data(task_dir, data)
    profile = profile_data(raw)
    atomic_write_text(log_dir / "profile.md", profile)

    utility = make_runner(runner_kind, utility_model, utility_effort)
    clar, res = utility.ask_json(P.render("newtask_clarify", problem=problem, profile=profile), cwd=task_dir,
                                 log_path=log_dir / "clarify.jsonl", schema=CLARIFY_SCHEMA, timeout_s=600)
    if not res.ok or not isinstance(clar, dict):
        raise RuntimeError(f"clarification call failed: {res.error}")
    atomic_write_text(log_dir / "clarify.json", json.dumps(clar, indent=1, ensure_ascii=False))
    decisions = ask_human(clar, answers, yes)
    atomic_write_text(log_dir / "decisions.json", json.dumps(decisions, indent=1, ensure_ascii=False))
    print("\n== building the task pack (this takes a while) ==")

    builder = make_runner(runner_kind, model, effort)
    prompt = P.render("newtask_build", problem=problem, decisions=json.dumps(decisions, indent=1, ensure_ascii=False),
                      profile=profile, task_dir=str(task_dir), task_name=name)
    for attempt in range(2):
        r = builder.run_agent(prompt, cwd=task_dir, log_path=log_dir / f"build{attempt}.jsonl", max_turns=max_turns,
                              timeout_s=timeout_s, idle_timeout_s=600)
        m = re.search(r"NEWTASK_RESULT:\s*(\{.*\})", r.final_text or "", re.S)
        result = {}
        if m:
            try:
                result = parse_json_loose(m.group(1))
            except ValueError:
                pass
        ok, err = verify_pack(task_dir)
        if ok:
            break
        print(f"verification failed: {err}")
        prompt = (f"The task pack in {task_dir} failed the harness verification: {err}\n\nFix it. Re-run setup and both "
                  f"evaluator levels on the starter, then finish with the NEWTASK_RESULT line again.")
    else:
        raise RuntimeError("task pack verification failed twice; see " + str(log_dir))
    summary = [f"# new-task {name}", "", f"created {now_iso()}", "", "## Problem", problem, "", "## Decisions", "```json",
               json.dumps(decisions, indent=1, ensure_ascii=False), "```", "", "## Builder result", "```json",
               json.dumps(result, indent=1, ensure_ascii=False), "```", "", "## Harness verification", err or "ok", ""]
    atomic_write_text(task_dir / "NEWTASK.md", "\n".join(summary))
    print(f"\ntask pack ready: {task_dir}\nnext: rsi init <exp> --task {name} ...")
    return task_dir


def verify_pack(task_dir: Path) -> tuple[bool, str]:
    """Load task.toml and run the evaluator on the starter for the quick and official levels through the harness."""
    from .evaluator import run_eval, score_of
    try:
        task = load_task_cfg(task_dir)
    except Exception as e:
        return False, f"task.toml invalid: {e}"
    for req in ("TASK.md", "eval", "starter"):
        if not (task_dir / req).exists():
            return False, f"missing {req}"
    cfg = ExperimentCfg(name="_verify", dir=task_dir / "_newtask" / "verify", task=task, runner=RunnerCfg(), utility=UtilityCfg(), search=SearchCfg())
    cfg.dir.mkdir(parents=True, exist_ok=True)
    msgs = []
    for level in (task.quick_seedset, task.official_seedset):
        try:
            m = run_eval(cfg, task_dir / task.starter_dir, level, cfg.dir)
            s = score_of(cfg, m)
            if s is None:
                return False, f"{level}: evaluator wrote no '{task.score_key}'"
            msgs.append(f"{level}: starter {task.score_key} = {s}")
        except Exception as e:
            return False, f"{level}: {e}"
    return True, "; ".join(msgs)
