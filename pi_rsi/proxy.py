"""How good are the proxies? The official level stands in for the real target, development results stand in
for the official level, and the lead's forecasts stand in for both. This module keeps the evidence on each:
observations of the real target supplied from outside (`rsi observe`) and a ledger, per measured node, of the
development gain the worker reported, the gain the lead forecast and the official gain the harness measured.

The ledger is a view of tree.json; observations.jsonl is the single home of external results."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .util import append_jsonl, as_number, atomic_write_json, atomic_write_text, fmt_score, now_iso

OBSERVATIONS = "observations.jsonl"
MISS_STREAK = 3  # this many forecasts in a row that missed their sign force a full review


# external observations ----------------------------------------------------------------------------------
def add_observation(exp_dir: Path, text: str, *, node: str | None = None, metric: str | None = None,
                    value: float | None = None, source: str = "human") -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("an observation needs a description")
    record = {"at": now_iso(), "text": text[:2000], "node": node or None, "metric": metric or None,
              "value": as_number(value), "source": source}
    append_jsonl(Path(exp_dir) / OBSERVATIONS, record)
    return record


def observations(exp_dir: Path) -> list[dict]:
    path = Path(exp_dir) / OBSERVATIONS
    out = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("text"):
                out.append(row)
    return out


# ledger ----------------------------------------------------------------------------------------------------
def _unchanged(node, parent) -> bool:
    """The delivered output is identical to the parent's: the official evaluation measured nothing new."""
    mine, theirs = (node.metrics or {}), (parent.metrics or {})
    if mine.get("submission_sha256") and theirs.get("submission_sha256"):
        return mine["submission_sha256"] == theirs["submission_sha256"]
    if mine.get("per_item") and theirs.get("per_item"):
        return mine["per_item"] == theirs["per_item"]
    return node.delta_parent == 0


def ledger(tree) -> dict[str, Any]:
    rows = []
    for n in sorted((n for n in tree.nodes.values() if n.id != "root" and n.measurement_valid),
                    key=lambda n: (n.finished_order or 0, n.id)):
        parent = tree.nodes.get(n.parent)
        if parent is None or not parent.measurement_valid:
            continue
        delivery = n.worker.get("delivery") or {}
        comparison = (n.audit or {}).get("comparison") or {}
        rows.append({"node": n.id, "parent": n.parent, "official_delta": n.delta_parent,
                     "noise_band": as_number(comparison.get("noise_band")), "verdict": n.verdict,
                     "unchanged": _unchanged(n, parent),
                     "component": delivery.get("component", "undeclared"), "measured": delivery.get("measured", ""),
                     "dev_delta": as_number(delivery.get("dev_delta")), "dev_sem": as_number(delivery.get("dev_sem")),
                     "forecast": as_number((n.worker.get("proposal") or {}).get("expected_delta"))})
    skipped = sorted((n for n in tree.nodes.values() if (n.measurement or {}).get("state") == "skipped"),
                     key=lambda n: (n.finished_order or 0, n.id))
    return {"rows": rows, "summary": {**_summary(rows), "not_measured": [n.id for n in skipped]}}


def _summary(rows) -> dict[str, Any]:
    informative = [r for r in rows if not r["unchanged"] and r["official_delta"] is not None]
    paired = [r for r in informative if r["dev_delta"] is not None and r["dev_delta"] != 0 and r["official_delta"] != 0]
    agree = sum((r["dev_delta"] > 0) == (r["official_delta"] > 0) for r in paired)
    forecasts = [r for r in rows if r["forecast"] is not None and r["forecast"] > 0 and r["official_delta"] is not None]
    misses = [r for r in forecasts if r["official_delta"] <= 0]
    streak = 0
    for r in reversed(forecasts):
        if r["official_delta"] > 0:
            break
        streak += 1
    ratios = sorted(r["official_delta"] / r["forecast"] for r in forecasts)
    return {"measured": len(rows), "unchanged": [r["node"] for r in rows if r["unchanged"]],
            "measured_switched_on": [r["node"] for r in rows if r["measured"] == "active"],
            "dev_official_pairs": len(paired), "dev_official_sign_agreement": agree,
            "dev_mean": sum(r["dev_delta"] for r in paired) / len(paired) if paired else None,
            "official_mean": sum(r["official_delta"] for r in paired) / len(paired) if paired else None,
            "forecasts": len(forecasts), "forecast_misses": len(misses), "forecast_miss_streak": streak,
            "forecast_median_ratio": ratios[len(ratios) // 2] if ratios else None}


def summary_lines(data: dict, external: list[dict]) -> list[str]:
    s = data["summary"]
    lines = [f"Measured experiments: {s['measured']}. Official output identical to the parent (measured nothing new): "
             f"{len(s['unchanged'])}{' (' + ', '.join(s['unchanged'][-12:]) + ')' if s['unchanged'] else ''}."]
    if s.get("not_measured"):
        lines.append(f"Not officially evaluated (declared no new component): {', '.join(s['not_measured'][-12:])}.")
    if s["measured_switched_on"]:
        lines.append(f"Delivered switched off but measured switched on: {', '.join(s['measured_switched_on'])}.")
    if s["dev_official_pairs"]:
        lines.append(f"Development vs official sign agreement: {s['dev_official_sign_agreement']}/{s['dev_official_pairs']}; "
                     f"mean development gain {fmt_score(s['dev_mean'])} vs mean official gain {fmt_score(s['official_mean'])}.")
    else:
        lines.append("Development vs official agreement: no pair yet (needs DELIVERY.json dev_delta and a changed output).")
    if s["forecasts"]:
        lines.append(f"Forecasts of a positive official gain: {s['forecasts']}; realised <= 0: {s['forecast_misses']} "
                     f"(current streak {s['forecast_miss_streak']}); median realised/forecast {fmt_score(s['forecast_median_ratio'])}.")
    if external:
        lines.append("Results on the real target (external observations; the official level is only a proxy for them):")
        lines += [f"- {o['at'][:10]} {o.get('node') or ''} {o.get('metric') or ''} {'' if o.get('value') is None else o['value']}: "
                  f"{o['text']}".replace("  ", " ") for o in external[-8:]]
    return lines


def context(cfg, tree) -> str:
    """The block the research lead and the course corrector read."""
    data = ledger(tree)
    return "\n".join(["Proxy quality (harness ledger, PROXY.md):", *summary_lines(data, observations(cfg.dir))])


def write(cfg, tree) -> None:
    data = ledger(tree)
    external = observations(cfg.dir)
    atomic_write_json(cfg.dir / "proxy.json", {"generated_at": now_iso(), **data, "observations": external})
    table = ["| node | parent | official Δ | noise | unchanged | component | measured | dev Δ | dev SEM | forecast |",
             "|---|---|---:|---:|---|---|---|---:|---:|---:|"]
    table += [f"| {r['node']} | {r['parent']} | {fmt_score(r['official_delta'])} | {fmt_score(r['noise_band'])} | "
              f"{'yes' if r['unchanged'] else ''} | {r['component']} | {r['measured']} | {fmt_score(r['dev_delta'])} | "
              f"{fmt_score(r['dev_sem'])} | {fmt_score(r['forecast'])} |" for r in data["rows"]]
    atomic_write_text(cfg.dir / "PROXY.md", "\n".join([
        f"# Proxy quality — {cfg.name}", "",
        "Generated from tree.json and observations.jsonl; do not edit. Each score the study uses stands in for the "
        "one above it: development for official, official for the real target.", "",
        *summary_lines(data, external), "", *table, ""]))
