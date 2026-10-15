"""Natural-language research decisions and analyses, structured by a small model.

The research lead writes prose. A cheap extractor (the maintainer model, GPT-6 Luna by
default) copies it into the fields the harness executes and audits. Fields that decide what
runs (action, parent node, budget) are checked against the text and the tree. Audit fields
(evidence links, references, predictions, alternatives) are repaired or dropped with a
warning; they never stop a study.
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path
from urllib.parse import urlsplit

from .agents import _clean_proposals
from .util import as_number

ASSESSMENT = ("goal_progress", "result_analysis", "reference_search", "uncertainty", "belief_revisions")
ANALYSIS_LISTS = ("observations", "belief_revisions", "competing_explanations", "limitations")
LIST_ITEMS, ITEM_CHARS, TEXT_CHARS = 12, 2000, 6000

_STR = {"type": "string"}
_LIST = {"type": "array", "items": _STR}
DECISION_SCHEMA = {"type": "object", "properties": {
    "action": {"type": "string", "enum": ["continue", "stop", "review"]},
    "action_quote": _STR, "parent": {"type": ["string", "null"]},
    "title": _STR, "hypothesis": _STR,
    "type": {"type": "string", "enum": ["idea", "debug", "ablate", "scale"]},
    **{k: _STR for k in ("research_question", "prediction", "falsifier", "expected_gain", "risk", "rationale", "reason")},
    "evidence": _LIST,
    "expected_delta": {"type": ["number", "null"]},
    "reenters_paused": {"type": "boolean"}, "paused_match": {"type": ["string", "null"]}, "paused_evidence": _STR,
    "budget": {"type": "object", "properties": {"seconds": {"type": ["integer", "null"]},
                                                "max_trials": {"type": ["integer", "null"]}}},
    "alternatives": {"type": "array", "items": {"type": "object", "properties": {
        "title": _STR, "parent": {"type": ["string", "null"]}, "why_not": _STR}}},
    "references": {"type": "array", "items": {"type": "object", "properties": {
        "title": _STR, "url": _STR, "source_path": _STR}}},
    "saturation_checks": _LIST},
    "required": ["action", "action_quote"]}

ANALYSIS_SCHEMA = {"type": "object", "properties": {
    **{key: _LIST for key in ANALYSIS_LISTS},
    **{key: _STR for key in ("interpretation", "noise_assessment", "result_quote")}},
    "required": ["observations", "result_quote"]}


def _words(text):
    return re.sub(r"[\W_]+", " ", text or "").strip().lower()


def grounded(quote, text):
    """Is `quote` copied from `text`? Markdown, punctuation and an elided middle are tolerated."""
    parts = [_words(p) for p in re.split(r"\.\.\.|…", quote or "")]
    parts = [p for p in parts if p]
    body = f" {_words(text)} "
    return bool(parts) and sum(len(p) for p in parts) >= 4 and all(f" {p} " in body for p in parts)


def mentions(text, node_id):
    return bool(node_id) and re.search(rf"(?<![\w-]){re.escape(node_id)}(?![\w-])", text or "") is not None


def _str(value, limit=TEXT_CHARS):
    return value.strip()[:limit] if isinstance(value, str) else ""


def _str_list(value, limit=LIST_ITEMS):
    items = [_str(x, ITEM_CHARS) for x in value] if isinstance(value, list) else []
    return [x for x in items if x][:limit]


def _ids_block(snapshot, limit=8000):
    ids = list(snapshot.get("known_claims", [])) + list(snapshot.get("known_evidence", []))
    out = ", ".join(ids)
    return out if len(out) <= limit else out[:limit] + f" … ({len(ids)} IDs; the full list is in the snapshot)"


# decisions ---------------------------------------------------------------------------

def decision_prompt(text, snapshot, rejection="", paused=()):
    parents = ", ".join(p["id"] for p in snapshot["parents"])
    paused_block = "\n".join(f"- {p}" for p in paused) or "(none)"
    retry = (f"\nYOUR PREVIOUS EXTRACTION WAS REJECTED: {rejection}\nFix exactly that. If the text itself does not "
             "contain the missing information, use action \"review\" instead of guessing.\n") if rejection else ""
    return f"""You structure a research lead's written decision for the pi-rsi harness.
Copy, do not decide. Every field must come from the decision text below; do not add ideas, numbers,
node IDs or sources it does not contain. Use "" or [] when the text is silent.
- action: "continue" when the text commits to one next experiment, "stop" when it concludes the study
  should end, "review" when it asks for a broader review or does not commit to either.
- action_quote: the sentence of the text that states this choice, copied word for word.
- parent: the node ID the chosen experiment builds on, exactly as written in the text (e.g. n027 or root).
- title (at most 12 words) and hypothesis: what the worker should implement and test, faithful to the text.
- type: idea, debug, ablate or scale. research_question, prediction, falsifier, expected_gain, risk,
  rationale, reason: as the text states them.
- evidence: claim, evidence or node IDs the text relies on, as written. When the text clearly means
  one of the KNOWN IDS below but misspells it, give the known spelling.
- expected_delta: the change of the official aggregate score the text forecasts for this experiment, as one
  number in the metric's units (the midpoint when it gives a range); null when it states no number.
- reenters_paused: true only when the chosen experiment does what one of the PAUSED DIRECTIONS below pauses
  (the same method or a variant of it); false when it is unrelated or carries out the precondition or
  diagnostic a pause asks for first ("until ...", "first ..."). paused_match: for true, that direction
  copied from the list, else null. paused_evidence: the new evidence the text gives for re-entering it, or "".
- budget: seconds and max_trials only when the text states them, else null.
- alternatives: other options the text considered, with why_not.
- references: only sources given with a title, an http(s) URL and a saved excerpt path (sources/...).
- saturation_checks: for stop, the completion or saturation criteria the text says it checked.
{retry}
ELIGIBLE PARENT NODES: {parents}
PAUSED DIRECTIONS:
{paused_block}
KNOWN IDS: {_ids_block(snapshot)}
DECISION TEXT
<<<
{text}
>>>
Return only the JSON object."""


def from_extraction(data, text):
    """Map extractor output to a harness decision. Raises ValueError when it is not grounded."""
    if not isinstance(data, dict):
        raise ValueError("extractor returned no JSON object")
    action = data.get("action")
    if action not in ("continue", "stop", "review"):
        raise ValueError("action must be continue, stop or review")
    if not grounded(data.get("action_quote"), text):
        raise ValueError("action_quote is not copied from the decision text")
    if action == "review":
        return {"action": "review"}
    reason = _str(data.get("reason")) or _str(data.get("rationale"))
    out = {"action": action, "reason": reason,
           "assessment": {k: "" for k in ASSESSMENT},
           "saturation_checks": _str_list(data.get("saturation_checks")),
           "references": [r for r in data.get("references") or [] if isinstance(r, dict)][:8],
           "alternatives": [{"title": _str(a.get("title"), 300), "parent": a.get("parent"),
                             "why_not": _str(a.get("why_not"), ITEM_CHARS)}
                            for a in data.get("alternatives") or [] if isinstance(a, dict) and _str(a.get("title"))][:8],
           "candidates": [], "selected": None}
    if action == "continue":
        parent = _str(data.get("parent"), 64)
        if not mentions(text, parent):
            raise ValueError(f"parent {parent or '(none)'} is not a node ID written in the decision text")
        budget = data.get("budget") if isinstance(data.get("budget"), dict) else {}
        out["candidates"] = [{"id": "selected", "parent": parent,
            "title": _str(data.get("title"), 120), "hypothesis": _str(data.get("hypothesis")),
            "type": data.get("type") or "idea",
            **{k: _str(data.get(k)) for k in ("expected_gain", "risk", "research_question", "prediction",
                                             "falsifier", "rationale")},
            "evidence_ids": _str_list(data.get("evidence"), 40),
            "expected_delta": as_number(data.get("expected_delta")),
            "paused_match": (_str(data.get("paused_match"), ITEM_CHARS) or "a paused direction")
                            if data.get("reenters_paused") is True else None,
            "paused_evidence": _str(data.get("paused_evidence")),
            "budget": {"seconds": budget.get("seconds"), "max_trials": budget.get("max_trials")}}]
        out["selected"] = "selected"
    return out


def _reference(ref, cycle):
    title, url = _str(ref.get("title"), 500), _str(ref.get("url"), 2000)
    if not title or urlsplit(url).scheme not in ("https", "http") or not urlsplit(url).netloc:
        raise ValueError("needs a title and an http(s) URL")
    path = (cycle / _str(ref.get("source_path"), 500)).resolve()
    if not path.is_relative_to((cycle / "sources").resolve()) or not path.is_file():
        raise ValueError("excerpt must exist inside this cycle's sources directory")
    if not path.read_text(encoding="utf-8").strip() or path.stat().st_size > 200000:
        raise ValueError("excerpt is empty or oversized")
    return {"title": title, "url": url, "source_path": str(path)}


def _budget(value, limit, name, notes):
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if type(value) is not int or value < 1:
        notes.append(f"{name} not stated; using the limit {limit}")
        return limit
    if value > limit:
        notes.append(f"{name} {value} clamped to the limit {limit}")
        return limit
    return value


def _candidate(item, snapshot, eligible, known):
    """One executable candidate and its soft-repair notes. ValueError makes it non-executable."""
    if not isinstance(item, dict):
        raise ValueError("candidate is not an object")
    cleaned = _clean_proposals([item])
    if not cleaned:
        raise ValueError("candidate needs a title and a hypothesis")
    prop, notes = cleaned[0], []
    prop["expected_delta"] = as_number(item.get("expected_delta"))
    prop["paused_match"] = _str(item.get("paused_match"), ITEM_CHARS) or None
    prop["paused_evidence"] = _str(item.get("paused_evidence"))
    parent = item.get("parent")
    if parent not in eligible:
        raise ValueError(f"parent {parent!r} is not an eligible node")
    if snapshot.get("focus") in eligible and parent != snapshot["focus"]:
        raise ValueError("candidate must respect the human focus node")
    if len(prop["hypothesis"]) > TEXT_CHARS:
        prop["hypothesis"] = prop["hypothesis"][:TEXT_CHARS]
        notes.append("hypothesis clipped; the worker also reads the full decision text")
    evidence = []
    for ref in prop["evidence_ids"]:
        if ref not in known:
            close = difflib.get_close_matches(ref, list(known), n=1, cutoff=0.85)
            notes.append(f"evidence {ref!r} read as {close[0]!r}" if close else f"unknown evidence {ref!r} dropped")
            ref = close[0] if close else None
        if ref and ref not in evidence:
            evidence.append(ref)
    prop["evidence_ids"] = evidence
    for key in ("research_question", "prediction", "falsifier"):
        prop[key] = prop[key][:TEXT_CHARS]
        if not prop[key]:
            notes.append(f"no {key} stated")
    budget = item.get("budget") if isinstance(item.get("budget"), dict) else {}
    return {**prop, "parent": parent, "rationale": _str(item.get("rationale")),
            "budget": {"seconds": _budget(budget.get("seconds"), snapshot["worker_seconds"], "budget seconds", notes),
                       "max_trials": _budget(budget.get("max_trials"), snapshot["max_tuning_trials"], "tuning trials", notes)}}, notes


def _course_ids(cycle):
    try:
        folder = Path(cycle).parent.parent / "course"
        return {d.name for d in folder.iterdir() if d.is_dir()} if folder.is_dir() else set()
    except (TypeError, OSError):
        return set()


def validate(data, snapshot, cycle, max_candidates):
    """Hard checks on what runs; audit fields are repaired or dropped with a warning.

    Accepts extracted decisions and plans saved by earlier harness versions. Idempotent:
    validating its own output returns the same plan."""
    if not isinstance(data, dict) or data.get("action") not in ("continue", "stop"):
        raise ValueError("research decision must continue or stop")
    action, warnings = data["action"], []
    out = {"action": action, "reason": _str(data.get("reason")) or "(no reason stated)"}
    assessment = data.get("assessment") if isinstance(data.get("assessment"), dict) else {}
    out["assessment"] = {k: _str(assessment.get(k)) for k in ASSESSMENT}
    out["saturation_checks"] = _str_list(data.get("saturation_checks"))
    out["references"] = []
    for ref in data.get("references") or []:
        try:
            out["references"].append(_reference(ref if isinstance(ref, dict) else {}, cycle))
        except (ValueError, OSError) as e:
            label = ref.get("url", "") if isinstance(ref, dict) else ref
            warnings.append(f"reference {str(label)[:120]!r} dropped: {e}")
    selected = data.get("selected") if action == "continue" else None
    eligible = {p["id"] for p in snapshot["parents"]}
    known = set(snapshot.get("known_evidence", [])) | set(snapshot.get("known_claims", []))
    # Node and course-correction IDs name measured results and reviews; they are citable evidence too.
    known |= {n["id"] for n in snapshot.get("history", []) if isinstance(n, dict) and n.get("id")}
    known |= _course_ids(cycle)
    candidates, excluded, ids, hypotheses = [], [], set(), set()
    for item in data.get("candidates") or []:
        cid = _str(item.get("id"), 64) if isinstance(item, dict) else ""
        try:
            prop, notes = _candidate(item, snapshot, eligible, known)
            if not cid or cid in ids or (prop["parent"], prop["hypothesis"]) in hypotheses:
                raise ValueError("candidate is missing an ID or duplicates another")
        except ValueError as e:
            if cid and cid == selected:
                raise ValueError(f"selected candidate: {e}") from None
            excluded.append({"id": cid, "parent": item.get("parent") if isinstance(item, dict) else None,
                             "title": _str(item.get("title"), 120) if isinstance(item, dict) else "",
                             "reason": f"Not executable: {e}"})
            continue
        warnings += [f"candidate {cid}: {note}" for note in notes
                     if cid == selected or note.startswith(("evidence", "unknown evidence"))]
        ids.add(cid)
        hypotheses.add((prop["parent"], prop["hypothesis"]))
        candidates.append({**prop, "id": cid})
    if len(candidates) > max_candidates:
        keep = [c for c in candidates if c["id"] == selected][:1]
        keep += [c for c in candidates if c["id"] != selected][:max_candidates - len(keep)]
        warnings.append(f"{len(candidates) - len(keep)} extra candidates not recorded")
        candidates = [c for c in candidates if c in keep]
    alternatives = [a for a in data.get("alternatives") or [] if isinstance(a, dict)][:8]
    if action == "continue":
        if selected not in ids:
            raise ValueError("continue requires one executable selected candidate")
        if len(candidates) < 2 and not alternatives:
            warnings.append("no alternative was compared")
    elif not out["saturation_checks"]:
        raise ValueError("stop requires checked completion/saturation criteria")
    out.update(candidates=candidates, selected=selected)
    if alternatives:
        out["alternatives"] = alternatives
    if excluded:
        out["excluded_candidates"] = excluded
    elif data.get("excluded_candidates"):
        out["excluded_candidates"] = data["excluded_candidates"]
    warnings = list(dict.fromkeys(list(data.get("warnings") or []) + warnings))
    if warnings:
        out["warnings"] = warnings
    return out


# result analyses ---------------------------------------------------------------------
# A node's handoff looks back (what was measured and what it means); next steps live in NEXT.md
# and are structured as a decision. analysis.json is the structured view of the handoff only.

def analysis_prompt(handoff, rejection=""):
    retry = f"\nYOUR PREVIOUS EXTRACTION WAS REJECTED: {rejection}\nFix exactly that.\n" if rejection else ""
    return f"""You structure a research lead's written result analysis for the pi-rsi harness.
Copy, do not decide. Take every field from the handoff below; do not add observations, numbers or
conclusions it does not contain. Merge related points so each list has at most {LIST_ITEMS} items.
- observations: measured outcomes with their numbers as written (official and quick kept apart).
- interpretation, noise_assessment, belief_revisions, competing_explanations, limitations: as the
  handoff states them.
- result_quote: one sentence of its Result section, copied word for word.
{retry}
HANDOFF
<<<
{handoff}
>>>
Return only the JSON object."""


def analysis_from_extraction(data, handoff):
    if not isinstance(data, dict):
        raise ValueError("extractor returned no JSON object")
    result = handoff.split("## Result", 1)[-1].split("\n## ", 1)[0]
    if not grounded(data.get("result_quote"), result):
        raise ValueError("result_quote is not copied from the Result section")
    out = {key: _str_list(data.get(key)) for key in ANALYSIS_LISTS}
    if not out["observations"]:
        raise ValueError("analysis requires measured observations")
    out.update({key: _str(data.get(key)) for key in ("interpretation", "noise_assessment")})
    return out

