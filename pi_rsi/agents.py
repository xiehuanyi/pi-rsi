"""Utility agents: planner, auditor, diagnoser. Stateless, single-turn, no tools, structured JSON output.
They never touch code; they read files the harness hands them and return JSON. Cheap model by default."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import prompts as P
from .tree import Node
from .util import now_iso, fmt_score


class Utility:
    def __init__(self, orch):
        self.o = orch
        self.cfg = orch.cfg
        self.runner = orch.utility_runner

    def _ask(self, name: str, prompt: str, schema: dict, node_id: str = "_utility") -> Any:
        log_dir = self.cfg.nodes_dir / node_id
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"utility.{name}.{now_iso().replace(':', '')}.jsonl"
        data, res = self.runner.ask_json(prompt, cwd=self.cfg.dir, log_path=log_path, schema=schema,
                                         timeout_s=self.cfg.utility.timeout_s)
        self.o.log("utility", name=name, node=node_id, ok=res.ok, duration_s=round(res.duration_s, 1),
                   cost_usd=res.cost_usd, usage=res.usage, error=res.error)
        self.o.add_cost("utility", res)
        if not res.ok or data is None:
            raise RuntimeError(f"utility {name} failed: {res.error or 'no JSON'} (log {log_path})")
        return data

    # planner ---------------------------------------------------------------
    def plan_root(self, k: int) -> list[dict[str, Any]]:
        data = self._ask("planner_root", P.planner_root_prompt(self.cfg, self.o.tree, k), P.PROPOSALS_SCHEMA, "root")
        return _clean_proposals(data)[:k]

    def plan_children(self, parent: Node, k: int) -> list[dict[str, Any]]:
        data = self._ask("planner_child", P.planner_child_prompt(self.cfg, self.o.tree, parent, k), P.PROPOSALS_SCHEMA, parent.id)
        return _clean_proposals(data)[:k]

    # auditor ---------------------------------------------------------------
    def audit(self, node: Node, metrics: dict, gitlog: str, diffstat: str, noise: float) -> dict[str, Any]:
        try:
            data = self._ask("auditor", P.auditor_prompt(self.cfg, self.o.tree, node, metrics, gitlog, diffstat, noise),
                             P.AUDIT_SCHEMA, node.id)
            if isinstance(data, dict) and "summary" in data:
                data.setdefault("insights", [])
                data.setdefault("deadends", [])
                data.setdefault("claim_check", {"consistent": True, "note": ""})
                return data
        except Exception as e:  # fall back to a mechanical audit
            self.o.log("utility_fallback", name="auditor", node=node.id, error=str(e))
        return self.mechanical_audit(node, metrics, noise)

    def mechanical_audit(self, node: Node, metrics: dict, noise: float) -> dict[str, Any]:
        tree = self.o.tree
        parent = tree.get(node.parent) if node.parent else None
        score = node.score
        verdict = "failed"
        if score is not None and parent is not None and parent.score is not None:
            d = (score - parent.score) if tree.higher_is_better() else (parent.score - score)
            verdict = "improved" if d > noise else ("worse" if d < -noise else "no_change")
        elif score is not None:
            verdict = "no_change"
        summary = f"{node.title}: official {self.cfg.task.score_key} {fmt_score(score)}" + \
                  (f" vs parent {fmt_score(parent.score)}" if parent else "") + f" ({verdict})."
        return {"summary": summary, "verdict": verdict, "insights": [], "deadends": [],
                "claim_check": {"consistent": True, "note": "mechanical audit (utility model unavailable)"}}

    # diagnoser -------------------------------------------------------------
    def diagnose(self, node: Node, failure: str, runner_tail: str, gitstatus: str) -> dict[str, Any]:
        try:
            data = self._ask("diagnoser", P.diagnoser_prompt(self.cfg, node, failure, runner_tail, gitstatus),
                             P.DIAGNOSIS_SCHEMA, node.id)
            if isinstance(data, dict) and "retry" in data:
                return {"cause": str(data.get("cause", "")), "retry": bool(data["retry"]), "advice": str(data.get("advice", ""))}
        except Exception as e:
            self.o.log("utility_fallback", name="diagnoser", node=node.id, error=str(e))
        return {"cause": f"undiagnosed: {failure}", "retry": True,
                "advice": "The previous attempt failed with: " + failure + ". Check git log and the previous PROGRESS.md, "
                          "keep the work small, run the quick evaluation early, and write the handoff before the budget ends."}


def _clean_proposals(data: Any) -> list[dict[str, Any]]:
    items = data.get("proposals", []) if isinstance(data, dict) else data
    out = []
    for it in items or []:
        if not isinstance(it, dict) or not it.get("title") or not it.get("hypothesis"):
            continue
        out.append({
            "title": str(it["title"]).strip()[:120],
            "hypothesis": str(it["hypothesis"]).strip(),
            "type": str(it.get("type", "idea")).strip() if str(it.get("type", "idea")) in ("idea", "debug", "ablate", "scale") else "idea",
            "expected_gain": str(it.get("expected_gain", "")).strip(),
            "risk": str(it.get("risk", "")).strip(),
        })
    return out
