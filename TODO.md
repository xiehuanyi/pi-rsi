# TODO

Ordered by what makes the short-job version solid first. Long-horizon items are parked at the end on purpose.

## v0.1.x — short jobs (now)

- [ ] Publish to PyPI (`uv build` works; needs a token) so `uv tool install pi-rsi` / `pipx install pi-rsi` work without git.
- [ ] Second and third simple tasks: Kaggle `spaceship-titanic` (binary classification, submit) and the live Playground
      Series (`playground-series-s6e9`, submit); both need the competition rules accepted on the website once.
- [ ] Repeat runs (≥3 per model) before claiming any model ranking; report run-to-run variance in the comparison page.
- [ ] Auditor verdicts: use the paired noise estimate in the auditor prompt (done in code; prompt wording still says
      "|delta| below noise"). Add a per-task noise floor.
- [ ] Sparse-reward support: lexicographic scores (primary + secondary metric) in the scheduler; breadth-first when all
      candidates tie.
- [ ] `rsi new-task`: interactive clarification phase (agent asks follow-ups, offers deliverable/metric options,
      drafts `TASK.md`, evaluator and starter) instead of hand-written task packs.
- [ ] Human async intervention: `HUMAN.md` in a node dir is read by the next worker (exists), add `rsi note <exp> <node>`.
- [ ] pi runner in production: test with a real provider (API key or pi `/login`), custom compaction that reloads
      PROGRESS.md instead of summarizing.
- [ ] Reviewer pass on code quality before a node is accepted (norms: module size, determinism, no eval edits).
- [ ] Submission etiquette: cap Kaggle submissions per experiment; keep the LB as verification, never as the search signal.

## logistics agents (extract what humans should not babysit)

- [x] ops agent (`rsi ops`): tool-using, fixes environments/evaluators, auto-called after two consecutive evaluator failures.
- [x] writer (`rsi write`): narrative for the blog page; publisher (`scripts/publish_blog.py`).
- [ ] data agent: downloads/splits competition data, builds the hidden holdout, documents leakage risks.
- [ ] submitter agent: manages Kaggle submissions, daily limits, LB tracking and CV/LB correlation notes.
- [ ] infra sentinel: disk/GPU/CPU pressure, orphaned processes, stale worktrees; runs on a timer, no LLM unless needed.
- [ ] harness-repair agent: when the harness itself throws (events.jsonl `node_crash`), open a fix branch with a test.

## long-horizon / expensive experiments (parked)

- [ ] Job queue with GPU assignment and a `submitted → running_job → analyzing` node lifecycle (worker submits,
      session ends; an analysis session is woken when the job finishes).
- [ ] Evaluation ladder (smoke → proxy → full) with promotion rules; budgets in GPU-hours; priority = gain / cost.
- [ ] Curve-based early termination (NaN, stall, below-incumbent at the same step) without an LLM in the loop.
- [ ] Checkpoint/resume contract for task packs; idempotent job restarts.
- [ ] Proxy-to-full rank transfer checks (two or three budget scales) before trusting the ladder.
- [ ] Test task: fixed-time-budget small LM training on the 3090 (1-3 h full, 5-10 min proxy), then a real Kaggle GPU task.
- [ ] Sparse-reward tasks such as ARC-AGI-2 fine-tuning: only after the ladder and secondary metrics exist.

## self-improvement (the "rsi" part, parked until the above is boring)

- [ ] Run the same task pack with harness variants (prompts, scheduler parameters) and compare; harness commit is
      already recorded in `tree.json`.
- [ ] Let an agent propose harness changes as nodes of a meta-experiment whose evaluator is a fixed benchmark run.
