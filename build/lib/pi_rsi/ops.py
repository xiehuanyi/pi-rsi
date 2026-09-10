"""Logistics agents: the ops agent (tool-using, fixes infrastructure) and the writer (narrative for humans)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import prompts as P
from .evaluator import eval_command
from .runner import make_runner
from .util import now_iso, read_text, tail_text, atomic_write_text, parse_json_loose

ROOT = Path(__file__).resolve().parents[1]


def run_ops(orch, problem: str, evidence: str, max_turns: int = 40, timeout_s: int = 1500) -> dict[str, Any]:
    cfg = orch.cfg
    ops_dir = cfg.dir / "ops" / now_iso().replace(":", "")
    ops_dir.mkdir(parents=True, exist_ok=True)
    verify = " ".join(eval_command(cfg, cfg.repo_dir, cfg.task.quick_seedset, ops_dir / "verify.metrics.json"))
    prompt = P.render("ops", problem=problem, evidence=evidence[-20000:], root=str(ROOT), exp_dir=str(cfg.dir),
                      task_dir=str(cfg.task_dir), eval_command=cfg.task.eval_command, verify_command=verify, ops_dir=str(ops_dir))
    runner = make_runner(cfg.ops.kind or cfg.runner.kind, cfg.ops.model or cfg.runner.model, cfg.ops.effort or cfg.runner.effort)
    orch.log("ops_start", problem=problem[:200], dir=str(ops_dir))
    res = runner.run_agent(prompt, cwd=ROOT, log_path=ops_dir / "runner.jsonl", max_turns=max_turns, timeout_s=timeout_s,
                           idle_timeout_s=600)
    orch.add_cost("ops", res)
    verdict: dict[str, Any] = {"fixed": False, "retry_failed_nodes": False, "summary": res.error or "no verdict"}
    m = re.search(r"OPS_RESULT:\s*(\{.*\})", res.final_text or "", re.S)
    if m:
        try:
            verdict.update(parse_json_loose(m.group(1)))
        except ValueError:
            pass
    verdict.update(ok=res.ok, duration_s=round(res.duration_s, 1), dir=str(ops_dir), ops_md=read_text(ops_dir / "OPS.md")[:4000])
    atomic_write_text(ops_dir / "verdict.json", json.dumps(verdict, indent=1, ensure_ascii=False))
    orch.log("ops_end", fixed=verdict.get("fixed"), retry=verdict.get("retry_failed_nodes"), summary=str(verdict.get("summary"))[:200])
    return verdict


def write_narrative(orch, language: str = "Chinese") -> str:
    cfg = orch.cfg
    best = orch.tree.best()
    prompt = P.render("writer", language=language, report=read_text(cfg.dir / "REPORT.md")[:12000],
                      insights=read_text(cfg.insights_path)[:6000], deadends=read_text(cfg.deadends_path)[:4000],
                      best_handoff=read_text(cfg.nodes_dir / (best.id if best else "root") / "HANDOFF.md")[:6000] if best else "(none)")
    log_dir = cfg.nodes_dir / "_utility"
    log_dir.mkdir(parents=True, exist_ok=True)
    data, res = orch.utility_runner.ask_json(prompt, cwd=cfg.dir, log_path=log_dir / f"writer.{now_iso().replace(':', '')}.jsonl",
                                             schema=None, timeout_s=cfg.utility.timeout_s)
    orch.add_cost("utility", res)
    text = res.final_text.strip() if res.final_text else ""
    if isinstance(data, dict) and data.get("narrative"):
        text = str(data["narrative"])
    if text:
        atomic_write_text(cfg.dir / "NARRATIVE.md", text + "\n")
        orch.log("narrative_written", chars=len(text))
    else:
        orch.log("narrative_failed", error=res.error)
    return text
