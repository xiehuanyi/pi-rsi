"""Experiment setup: settle what later decisions depend on before the search starts.

1. Checks (code): the baseline is evaluated `setup.calibration_runs` times; the spread of those
   scores is the measured run-to-run noise band.
2. Review (research model, read-only tools): risks and questions in prose (setup/REVIEW.md); the
   maintainer model structures the questions.
3. Decisions: the human answers. With `setup.proxy` (yolo), a human-proxy agent may answer routine
   questions and questions raised mid-run within its authority. The first setup always asks the
   human every critical or human-only question.

setup/setup.json is the single home of these decisions; SETUP.md is a generated view of it.
"""
from __future__ import annotations

import math
import statistics
from pathlib import Path

from . import decision as D
from .util import atomic_write_json, atomic_write_text, now_iso, read_json, read_text

# What a human-proxy may decide (reversible, within bounds) versus what only the human may decide.
PROXY_CATEGORIES = ("threshold", "noise", "review_frequency", "budget_allocation", "method_direction", "stop_criteria")
HUMAN_CATEGORIES = ("protocol", "budget_cap", "final_holdout", "external", "data_deletion", "other")

_STR = {"type": "string"}
QUESTIONS_SCHEMA = {"type": "object", "properties": {
    "risks": {"type": "array", "items": _STR},
    "questions": {"type": "array", "items": {"type": "object", "properties": {
        "id": _STR, "question": _STR, "options": {"type": "array", "items": _STR}, "recommended": _STR,
        "rationale": _STR, "importance": {"type": "string", "enum": ["critical", "routine"]},
        "category": {"type": "string", "enum": [*PROXY_CATEGORIES, *HUMAN_CATEGORIES]}, "quote": _STR}}}},
    "required": ["risks", "questions"]}
ANSWERS_SCHEMA = {"type": "object", "properties": {"answers": {"type": "array", "items": {
    "type": "object", "properties": {"id": _STR, "answer": _STR, "quote": _STR}}}}, "required": ["answers"]}


def waiting_questions(exp_dir):
    """Questions in setup/setup.json that nobody has answered yet (the run goes on without them)."""
    state = read_json(Path(exp_dir) / "setup" / "setup.json", {}) or {}
    decided = state.get("decisions") or {}
    return [{"id": q.get("id", ""), "importance": q.get("importance", ""), "question": q.get("question", ""),
             "recommended": q.get("recommended", ""), "raised_by": q.get("raised_by", "")}
            for q in state.get("questions", []) if isinstance(q, dict) and q.get("id") not in decided]


class Setup:
    def __init__(self, orch):
        self.o, self.cfg = orch, orch.cfg
        self.dir = self.cfg.setup_dir
        self.path = self.dir / "setup.json"

    # state ------------------------------------------------------------------------------
    def required(self):
        return self.cfg.research.enabled and self.cfg.setup.enabled

    def state(self):
        return read_json(self.path, {}) or {"questions": [], "decisions": {}, "log": [], "completed_at": None}

    def save(self, state):
        self.dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.path, state)
        self.render(state)

    def complete(self):
        return bool(self.state().get("completed_at"))

    def practical_delta(self):
        answer = self.state()["decisions"].get("practical_delta", {}).get("answer")
        try:
            value = float(answer)
        except (TypeError, ValueError):
            return 0.0
        return value if math.isfinite(value) and value >= 0 else 0.0

    def calibration(self):
        cal = self.state().get("calibration") or {}
        return cal if isinstance(cal.get("band"), (int, float)) else None

    def progress_threshold(self):
        """Smallest gain over the best result that counts as progress (course correction)."""
        cal = self.calibration()
        return max(self.practical_delta(), cal["band"] if cal else 0.0)

    def summary(self, limit=6000):
        text = read_text(self.dir / "SETUP.md").strip()
        return text[:limit] if text else "(no setup recorded)"

    # 1. checks -----------------------------------------------------------------------------
    def calibrate(self):
        from .evaluator import run_eval, score_of
        cfg, root = self.cfg, self.o.tree.get("root")
        samples = [root.score] if root.score is not None else []
        level = cfg.task.official_seedset
        for i in range(1, cfg.setup.calibration_runs):
            self.o.log("setup_calibration", run=i + 1, of=cfg.setup.calibration_runs)
            metrics = run_eval(cfg, cfg.repo_dir, level, cfg.nodes_dir / "root" / "eval", tag=f"calib{i}",
                               owner=f"{cfg.name}/setup")
            samples.append(score_of(cfg, metrics))
        sd = statistics.stdev(samples) if len(samples) >= 2 else None
        calibration = {"method": "baseline_repeats", "level": level, "runs": len(samples), "samples": samples,
                       "sd": sd, "band": 2 * math.sqrt(2) * sd if sd is not None else None, "at": now_iso(),
                       "limitations": "Same code, same seed and same rows: run-to-run noise only. Seed and "
                                      "sampling variation are not covered."}
        state = self.state()
        state["calibration"] = calibration
        self.save(state)
        self.o.log("setup_calibrated", band=calibration["band"], samples=samples)
        return calibration

    # 2. review ------------------------------------------------------------------------------
    def _standard_questions(self, calibration):
        band = (calibration or {}).get("band")
        measured = (f"The measured run-to-run noise band is {band:.6g} ({calibration['runs']} baseline runs)."
                    if band is not None else "Run-to-run noise was not measured.")
        options = ["0"] + ([f"{band:.2g}", f"{2 * band:.2g}"] if band else [])
        return [{"id": "practical_delta", "kind": "number", "importance": "critical", "category": "threshold",
                 "source": "harness", "options": list(dict.fromkeys(options)), "recommended": "0",
                 "question": f"Smallest official {self.cfg.task.score_key} gain worth adopting (practical threshold)? "
                             "A result counts as an improvement only above the larger of this and the noise band.",
                 "rationale": measured + " 0 means any gain above the noise band counts; set more when small gains "
                              "are not worth extra complexity."}]

    def _review_prompt(self):
        cfg = self.cfg
        return f"""You are the setup reviewer of pi-rsi, before an automated research study starts.
Find what could make the study's results misleading or wasted, and the decisions a human must make
first. Inspect the task pack ({cfg.task_dir}: brief, docs, evaluator code, task.toml), the experiment
configuration ({cfg.dir / 'rsi.toml'}), human notes ({cfg.dir / 'HUMAN.md'}), the baseline result in
{cfg.nodes_dir / 'root'} and the noise calibration in {self.path}. Read only; change nothing.
Check: leakage or split problems, whether the metric and validation level fit the goal, whether the
measured noise is small relative to plausible gains, whether time/GPU budgets fit the evaluation,
hardware assumptions, and anything sealed that must stay sealed.

Write {self.dir / 'REVIEW.md'} in prose (no JSON):
- a section headed exactly "## Proxy validity". The official level only stands in for the real goal (for a
  competition: the hidden leaderboard). List each way it differs from the real target (population and
  segment mix, candidate or label space, data available at prediction time, metric details), the direction
  in which each difference probably biases local scores, and how the study can watch it (a segment to report,
  or a result on the real target that the human adds with `rsi observe`). Then the development level the
  workers tune on: its size, and whether comparisons on its segments have the power to decide anything;
- the risks you found, most serious first;
- then the questions the human should answer before the search. For each: the question, the options,
  your recommended answer and why, whether it is critical (wrong answer would invalidate or waste the
  study) or routine, and its category: one of {', '.join(PROXY_CATEGORIES + HUMAN_CATEGORIES)}.
Do not ask about the practical improvement threshold; the harness always asks that. Ask nothing
whose answer is already fixed by the task pack or the human notes. Reply REVIEW_READY when saved."""

    def review(self):
        """The reviewer's questions, structured; on failure the human still gets REVIEW.md and the standard ones."""
        research = self.o.research
        self.dir.mkdir(parents=True, exist_ok=True)
        timeout = research._remaining(self.cfg.research.timeout_s, completion=True)
        self.o.log("setup_review")
        res = research.runner.run_agent(self._review_prompt(), cwd=self.dir, log_path=self.dir / "review.jsonl",
                                        max_turns=self.cfg.research.max_turns, timeout_s=timeout,
                                        idle_timeout_s=self.cfg.research.idle_timeout_s)
        self.o.add_cost("setup", res)
        text = read_text(self.dir / "REVIEW.md").strip()
        validity = _section(text, "Proxy validity")
        if validity:
            state = self.state()
            state["proxy_validity"] = validity[:4000]
            self.save(state)
        if not text:
            return [], [], [f"setup reviewer wrote no REVIEW.md ({res.error or 'no output'})"]

        def convert(raw):
            if not isinstance(raw, dict) or not isinstance(raw.get("questions"), list):
                raise ValueError("extractor returned no question list")
            questions = []
            for q in raw["questions"]:
                if not isinstance(q, dict) or not D.grounded(q.get("quote"), text):
                    raise ValueError(f"question {str((q or {}).get('id'))!r} quote is not copied from REVIEW.md")
                category = q.get("category") if q.get("category") in PROXY_CATEGORIES + HUMAN_CATEGORIES else "other"
                questions.append({"id": D._str(q.get("id"), 64) or f"q{len(questions) + 1}", "kind": "choice",
                    "question": D._str(q.get("question"), 1000), "options": D._str_list(q.get("options"), 6),
                    "recommended": D._str(q.get("recommended"), 500), "rationale": D._str(q.get("rationale"), 2000),
                    "importance": "critical" if category in HUMAN_CATEGORIES else q.get("importance", "critical"),
                    "category": category, "source": "reviewer"})
            return questions, D._str_list(raw.get("risks"))

        try:
            _, (questions, risks) = research._structured("setup_questions", lambda r: _questions_prompt(text, r),
                                                         QUESTIONS_SCHEMA, convert, self.dir, completion=True)
            return [q for q in questions if q["question"] and q["id"] != "practical_delta"], risks, []
        except ValueError as e:
            return [], [], [f"review questions could not be structured ({e}); read REVIEW.md"]

    # 3. decisions -------------------------------------------------------------------------------
    def route(self, question, first):
        if question.get("category") in HUMAN_CATEGORIES:
            return "human"
        if first and question.get("importance") == "critical":
            return "human"  # even in yolo mode, the human confirms important questions of the first setup
        return "proxy" if self.cfg.setup.proxy else "human"

    def _decide(self, state, question, answer, decided_by, rationale=""):
        answer = str(answer).strip()
        if question.get("kind") == "number":
            value = float(answer)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{question['id']} needs a non-negative number")
        record = {"answer": answer, "decided_by": decided_by, "rationale": rationale, "at": now_iso(),
                  "question": question["question"]}
        state["decisions"][question["id"]] = record
        state["log"].append({"id": question["id"], **record})
        self.o.log("setup_decision", id=question["id"], answer=answer, decided_by=decided_by)

    def pending(self, state=None):
        state = state or self.state()
        return [q for q in state["questions"] if q["id"] not in state["decisions"]]

    def run(self, *, answers=None, accept_recommended=False, ask=None):
        """Advance the setup; returns 'complete' or 'awaiting_human'."""
        state = self.state()
        if "calibration" not in state and self.cfg.setup.calibration_runs:
            self.calibrate()
            state = self.state()
        if not state["questions"]:
            questions, risks, warnings = self.review()
            state = self.state()  # the review records proxy validity
            state["questions"] = self._standard_questions(state.get("calibration")) + questions
            state["risks"], state["warnings"] = risks, warnings
            self.save(state)
        first = not state.get("completed_at")
        for q in self.pending(state):
            if answers and q["id"] in answers:
                self._decide(state, q, answers[q["id"]], "human")
            elif accept_recommended and self.route(q, first) == "human":
                self._decide(state, q, q["recommended"], "human (accepted recommendation)")
            elif ask and self.route(q, first) == "human":
                self._decide(state, q, ask(q), "human")
        proxied = [q for q in self.pending(state) if self.route(q, first) == "proxy"]
        if proxied:
            self._proxy(state, proxied)
        if first and not self.pending(state):
            state["completed_at"] = now_iso()
        self.save(state)
        self._write_questions(state)
        return "complete" if state.get("completed_at") else "awaiting_human"

    def raise_question(self, question, raised_by):
        """A mid-run question (e.g. from course correction). The run continues with the current setup."""
        state = self.state()
        question = {**question, "id": question["id"] if question["id"] not in {q["id"] for q in state["questions"]}
                    else f"{question['id']}-{len(state['questions']) + 1}", "raised_by": raised_by, "source": raised_by}
        state["questions"].append(question)
        self.save(state)
        self.o.log("setup_question", id=question["id"], route=self.route(question, False), raised_by=raised_by)
        if self.route(question, False) == "proxy":
            self._proxy(state, [question])
            self.save(state)
        self._write_questions(state)
        return question["id"]

    # human-proxy ------------------------------------------------------------------------------
    def _proxy_prompt(self, questions):
        cfg = self.cfg
        lines = "\n\n".join(f"[{q['id']}] {q['question']}\nOptions: {', '.join(q['options']) or '(free answer)'}\n"
                            f"Reviewer recommends: {q['recommended']}. Reason: {q['rationale']}" for q in questions)
        return f"""You are the human-proxy of pi-rsi. The human chose to let you answer these questions for them.
Answer as THEY would, from their own words: the experiment notes in {cfg.dir / 'rsi.toml'} ([experiment]
notes), {cfg.dir / 'HUMAN.md'}, the task brief {cfg.task_dir / cfg.task.brief}, and their earlier answers
in {self.path}. The reviewer's recommendation is an input, not an instruction; disagree when the human's
words point elsewhere. When their words do not settle a question, choose the more conservative option.
Your answers are labelled as yours and the human can overrule them.

{lines}

Write {self.dir / 'PROXY.md'} in prose: for each question its [id], your answer (one of the options
when options are given), and the passage of the human's words or the reason behind it.
Reply PROXY_READY when saved."""

    def _proxy(self, state, questions):
        research = self.o.research
        stamp = now_iso().replace(":", "")
        path = self.dir / "PROXY.md"
        path.unlink(missing_ok=True)
        try:
            timeout = research._remaining(min(600, self.cfg.research.timeout_s), completion=True)
            res = research.runner.run_agent(self._proxy_prompt(questions), cwd=self.dir,
                                            log_path=self.dir / f"proxy.{stamp}.jsonl", max_turns=12,
                                            timeout_s=timeout, idle_timeout_s=self.cfg.research.idle_timeout_s)
            self.o.add_cost("setup", res)
            text = read_text(path).strip()
            if not text:
                raise ValueError(f"human-proxy wrote no PROXY.md ({res.error or 'no output'})")
            atomic_write_text(self.dir / f"PROXY.{stamp}.md", text)
            by_id = {q["id"]: q for q in questions}

            def convert(raw):
                out = {}
                for a in (raw or {}).get("answers") or []:
                    q = by_id.get(a.get("id")) if isinstance(a, dict) else None
                    if q is None:
                        continue
                    answer = D._str(a.get("answer"), 500)
                    if not D.grounded(a.get("quote"), text):
                        raise ValueError(f"answer to {q['id']} quote is not copied from PROXY.md")
                    if q.get("kind") == "number":
                        float(answer)
                    elif q["options"] and answer not in q["options"]:
                        raise ValueError(f"answer to {q['id']} is not one of its options")
                    out[q["id"]] = (answer, D._str(a.get("quote"), 1000))
                return out

            _, answers = research._structured("proxy_answers", lambda r: _answers_prompt(text, questions, r),
                                              ANSWERS_SCHEMA, convert, self.dir, completion=True)
        except (ValueError, RuntimeError) as e:
            self.o.log("setup_proxy_failed", error=str(e), questions=[q["id"] for q in questions])
            return
        for qid, (answer, quote) in answers.items():
            self._decide(state, by_id[qid], answer, "human-proxy", quote)

    # views ------------------------------------------------------------------------------------
    def _write_questions(self, state):
        waiting = self.pending(state)  # the proxy has already answered what it may and could
        path = self.dir / "QUESTIONS.md"
        if not waiting:
            path.unlink(missing_ok=True)
            return
        lines = ["# Questions for the human", "",
                 f"Answer with `rsi setup {self.cfg.dir} --answer <id>=<value>` (repeatable), or "
                 f"`--accept-recommended`. Reasons and risks: {self.dir / 'REVIEW.md'}.", ""]
        for q in waiting:
            lines += [f"## {q['id']} ({q['importance']}, {q['category']})", q["question"], "",
                      f"Options: {', '.join(q['options']) or '(free answer)'}",
                      f"Recommended: {q['recommended']} — {q['rationale']}", ""]
        atomic_write_text(path, "\n".join(lines))

    def render(self, state):
        cal = state.get("calibration") or {}
        lines = ["# Setup", "", "Generated from setup/setup.json; do not edit. These decisions bind the study:",
                 "only a new setup decision changes them.", "", "## Noise calibration"]
        if cal:
            lines.append(f"Baseline evaluated {cal.get('runs')} times at `{cal.get('level')}`: "
                         f"{', '.join(f'{s:.6g}' for s in cal.get('samples', []) if s is not None)}. "
                         f"Noise band (2 sigma of a difference): "
                         f"{cal['band']:.6g}." if cal.get("band") is not None else "Fewer than two runs: no band.")
            lines.append(cal.get("limitations", ""))
        else:
            lines.append("Not measured.")
        if state.get("proxy_validity"):
            lines += ["", "## Proxy validity (setup review)", "How the official level differs from the real target; "
                      "results on the real target are in observations.jsonl / PROXY.md.", "", state["proxy_validity"]]
        lines += ["", "## Decisions"]
        for q in state.get("questions", []):
            d = state.get("decisions", {}).get(q["id"])
            lines.append(f"- **{q['id']}**: {q['question']}")
            lines.append(f"  - {'answer: ' + d['answer'] + ' (decided by ' + d['decided_by'] + ')' if d else 'pending'}")
        for heading, key in (("Risks found by the reviewer", "risks"), ("Warnings", "warnings")):
            if state.get(key):
                lines += ["", f"## {heading}", *["- " + x for x in state[key]]]
        self.dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(self.dir / "SETUP.md", "\n".join(lines) + "\n")


def _section(markdown, heading):
    """The body of a `## heading` section, up to the next heading of the same or higher level."""
    lines, body, inside = markdown.splitlines(), [], False
    for line in lines:
        if line.strip().lstrip("#").strip().lower() == heading.lower() and line.lstrip().startswith("#"):
            inside = True
            continue
        if inside and line.lstrip().startswith("#") and len(line) - len(line.lstrip("#")) <= 2:
            break
        if inside:
            body.append(line)
    return "\n".join(body).strip()


def _questions_prompt(text, rejection=""):
    retry = f"\nYOUR PREVIOUS EXTRACTION WAS REJECTED: {rejection}\nFix exactly that.\n" if rejection else ""
    return f"""You structure a setup review for the pi-rsi harness.
Copy, do not decide. Take the risks and every question from the review below; add nothing.
For each question: a short id (snake_case), the question, its options, the recommended answer, the
rationale, importance (critical or routine, as the review states; critical when unclear), category
(one of {', '.join(PROXY_CATEGORIES + HUMAN_CATEGORIES)}; other when unclear), and quote: the sentence
of the review that asks it, copied word for word.
{retry}
REVIEW
<<<
{text}
>>>
Return only the JSON object."""


def _answers_prompt(text, questions, rejection=""):
    retry = f"\nYOUR PREVIOUS EXTRACTION WAS REJECTED: {rejection}\nFix exactly that.\n" if rejection else ""
    ids = "\n".join(f"- {q['id']}: options {', '.join(q['options']) or '(free answer)'}" for q in questions)
    return f"""You structure the human-proxy's answers for the pi-rsi harness.
Copy, do not decide. For each question the text answers: its id, the answer exactly as one of the
options (or the free answer as written), and quote: the sentence of the text that gives it, word for
word. Skip questions the text does not answer.
QUESTIONS
{ids}
{retry}
ANSWERS TEXT
<<<
{text}
>>>
Return only the JSON object."""
