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
- [x] `rsi new-task`: clarification phase (profile → questions with defaults → builder agent → harness verification).
      Built `st-auto` from the Spaceship data unattended (`--yes`); the interactive terminal path needs a human test.
- [x] Human async intervention: experiment-level `HUMAN.md` via `rsi continue --note`; node-level `HUMAN.md` read by the next worker.
- [ ] pi runner in production: test with a real provider (API key or pi `/login`), custom compaction that reloads
      PROGRESS.md instead of summarizing.
- [ ] Reviewer pass on code quality before a node is accepted (norms: module size, determinism, no eval edits).
- [x] Submission etiquette: `hooks.max_submissions` cap + `SUBMISSIONS.md` ledger (`rsi submit`).

## logistics agents (extract what humans should not babysit)

- [x] ops agent (`rsi ops`): tool-using, fixes environments/evaluators, auto-called after two consecutive evaluator failures.
- [x] writer (`rsi write`): narrative for the blog page; publisher (`scripts/publish_blog.py`).
- [x] data agent: part of `rsi new-task` (download, group-aware hidden split, leakage notes in NEWTASK.md).
- [x] submitter: `rsi submit` with cap and ledger (holdout vs LB per submission). CV/LB correlation summary still manual.
- [x] infra sentinel: `rsi sentinel` (disk, GPUs, dead orchestrators, orphans, stale worktrees), `--interval` for a timer.
- [x] harness-repair agent: `rsi repair <exp>` collects crashes, ops agent fixes on `repair/<ts>` with a test; human merges.

## long-horizon / expensive experiments (parked)

- [x] Job queue with GPU assignment; official evaluation runs as a job; the worker session is woken for an analysis
      pass when the job finishes (`pi_rsi/jobs.py`, `tests/test_jobs.sh`).
- [x] Evaluation ladder (smoke → proxy → full) with `final_top_k` promotion; `max_gpu_hours` budget. Priority = gain / cost: not yet.
- [x] Curve-based early termination (NaN, stall, timeout, below-incumbent at the same step) in the daemon.
- [x] Checkpoint/resume contract (`--resume`, `job_resumable`); one automatic resubmission after a failure.
- [ ] Proxy-to-full rank transfer checks (two or three budget scales) before trusting the ladder.
- [ ] Test task on a real GPU: fixed-time-budget small LM training on the 3090 (1-3 h full, 5-10 min proxy), then a Kaggle
      GPU task. `tasks/toy-longjob` (CPU) is the machinery test only.
- [ ] Sparse-reward tasks such as ARC-AGI-2 fine-tuning: only after the ladder and secondary metrics exist.

## self-improvement (the "rsi" part, parked until the above is boring)

- [ ] Run the same task pack with harness variants (prompts, scheduler parameters) and compare; harness commit is
      already recorded in `tree.json`.
- [ ] Let an agent propose harness changes as nodes of a meta-experiment whose evaluator is a fixed benchmark run.
