# pi-rsi — auto-research harness

[English](README.md) · [简体中文](README.zh-CN.md)

Status: v0.1, research prototype. Built and tested on one Linux workstation with the Grok CLI and a pinned
[pi](https://github.com/earendil-works/pi) 0.85.1. MIT licensed. Experiment write-ups: https://blog.pocketplay.win/rsi/

## Overview

pi-rsi turns a task pack—problem, starter code and **frozen evaluator**—into a persistent research tree.
Agents choose and implement hypotheses in isolated Git worktrees; the harness records official measurements,
audits the result and retains the handoff for the next decision. Budgets, waiting and recovery are controller responsibilities.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/pi-rsi-overview-en-dark.svg">
  <img src="docs/assets/pi-rsi-overview-en-light.svg" alt="pi-rsi research loop: frozen task and baseline, choose a hypothesis, implement and evaluate, review evidence and feed the next decision; inset shows one research node">
</picture>

New experiments use a **sequential research loop over the search tree**: implement one approach with a
tuning budget, wait on its external task monitor, analyze the official result, and propose the next
experiment in the same pass. A full review of the whole tree (with reference reading) runs first, every
`research.review_every` experiments, on plateaus, on new human direction and before any stop. The research
lead writes prose only; a separate **GPT-6 Luna** structures it (decisions, analyses) for the harness to
validate, and maintains the three-layer research wiki (immutable raw sources, generated knowledge,
navigation index) and visualization explanations.
Existing experiments opt in with `rsi research enable <experiment>`. See [research loop and task monitor](docs/RESEARCH_LOOP.md).

The Wiki and task-monitor extensions shown here describe the development research runtime used by the airline example below.

## Case study: when the researcher picks a biased proxy (CASMI26, 2026-10)

A 4-day run on the Kaggle CASMI26 MS/MS-to-structure task stalled for 19 nodes at a local MRR of 0.404. An audit
found the research lead had turned the competition playbook's "never give back a won segment" into a development
gate: every class and source had to improve on both seeds, on a dev set where one segment had 14 molecules. Workers
therefore shipped new components switched off, and 22 of 31 official evaluations measured outputs identical to
their parent. The fix lives in the harness, not in per-run notes: the playbook now optimizes the official aggregate,
workers declare what they deliver (`DELIVERY.json`), switched-off components are measured switched on, a `PROXY.md`
ledger tracks how development, forecast and official deltas agree, and `rsi observe` feeds results on the real target
(e.g. the Kaggle leaderboard) back to the lead. Two nodes after the playbook change, the run found its first new best
in 20 nodes (0.4185, +0.0146). Write-up with the interactive score chart and search tree:
[English](https://blog.pocketplay.win/en/blog/pi-rsi-casmi26-proxy-alignment-20261015/) ·
[中文](https://blog.pocketplay.win/zh/blog/pi-rsi-casmi26-proxy-alignment-20261015/).
Details: [research loop, section "Proxy 的质量"](docs/RESEARCH_LOOP.md).

## Real experiment: airline satisfaction

A real RTX 2080 Ti search is archived with an offline chart, the full search explorer, aggregate metrics,
and exact baseline/current-best source. It is a preliminary snapshot of a continuing campaign.
The offline [research Wiki](examples/airline-s6e10-2080ti-20261004/wiki.html) links knowledge entries to
supporting/opposing evidence and published belief revisions.
Live on the blog: [experiment overview](https://blog.pocketplay.win/rsi/interactive/airline-20261004/en/),
[full search tree](https://blog.pocketplay.win/rsi/interactive/airline-20261004/en/tree/),
[research Wiki](https://blog.pocketplay.win/rsi/interactive/airline-20261004/en/wiki/).
Read the [English README](examples/airline-s6e10-2080ti-20261004/README.md) or
[中文 README](examples/airline-s6e10-2080ti-20261004/README.zh-CN.md).

![Airline experiment score progression](examples/airline-s6e10-2080ti-20261004/preview.png)

## Layout

| path | what |
|---|---|
| `rsi` | CLI launcher for a checkout: `./rsi task|init|run|status|render|eval|ops|write|relabel` |
| `pi_rsi/orchestrator.py` | the loop: root setup, scheduling, supervision, stop, final report |
| `pi_rsi/scheduler.py` | best-first parent choice, width/depth caps, retries, stop conditions |
| `pi_rsi/worker.py` | one node end to end: worktree → session → commit → guard → eval → audit |
| `pi_rsi/agents.py` | planner / auditor / diagnoser (structured JSON, no tools) |
| `pi_rsi/ops.py` | logistics agents: ops (tool-using, fixes environments/evaluators) and writer (narrative) |
| `pi_rsi/home.py` | `RSI_HOME` layout for installed use; bundled task packs live in `pi_rsi/tasks/` |
| `pi_rsi/runner/` | agent runtimes: `grok` (official Grok CLI), `pi` (pinned pi, JSON mode), `script` (tests) |
| `pi_rsi/evaluator.py` | runs the task pack's frozen evaluator against a worktree |
| `pi_rsi/prompts/*.md` | worker, planner, auditor, diagnoser prompt templates |
| `pi_rsi/render.py` + `templates/tree.html` | self-contained tree visualization, `tree.md`, `REPORT.md` |
| `tasks/<name>/` | task packs (`task.toml`, `TASK.md`, `starter/`, `eval/`, `docs/`); symlink to `pi_rsi/tasks/` |
| `experiments/<name>/` | one directory per run (gitignored): `rsi.toml`, `tree.json`, `nodes/`, `worktrees/`, `repo/` |
| `tests/` | `test_loop.sh` (LLM-free end-to-end), `test_pi_runner.sh` (pi against a mock provider) |
| `scripts/supervise.sh` | external watchdog that restarts a dead orchestrator |
| `scripts/compare.py`, `scripts/publish_blog.py` | cross-experiment comparison; publishing pages to a static blog |
| `bin/pi`, `package.json` | pinned pi 0.85.1; wrapper disables update checks and telemetry |

## Install

```bash
uv tool install git+https://github.com/xiehuanyi/pi-rsi      # or: pipx install git+https://github.com/xiehuanyi/pi-rsi
rsi task list                                                 # bundled task packs
rsi task install kaggriculture                                # creates ~/.pi-rsi/tasks/kaggriculture with its own venv
```

Installed this way, experiments live under `~/.pi-rsi/experiments/` (override with `RSI_HOME`). Inside a git checkout,
`./rsi` uses the checkout's `tasks/` and `experiments/` instead, and the pinned pi from `package.json`
(`npm install --ignore-scripts`). Agent runtimes are external: the `grok` CLI (logged in), or `pi`
(`npm i -g @earendil-works/pi-coding-agent@0.85.1`, then `pi` + `/login` or an API key).

## Quick start

```bash
rsi init demo --task kaggriculture --runner grok --model grok-4.6 --effort high \
    --utility-model grok-4.5 --utility-effort low --width-root 3 --width 2 --depth 4 --max-nodes 10 --parallel 2
rsi setup demo             # noise calibration, setup review, you answer the critical questions (--yolo: a proxy answers routine ones)
rsi run demo               # resumable; Ctrl-C stops after in-flight nodes finish
rsi status demo
xdg-open ~/.pi-rsi/experiments/demo/tree.html   # re-rendered after every event
```

`rsi run` on an existing experiment resumes it: nodes that were running when the process died are marked failed,
diagnosed, and retried from their last commit. `scripts/supervise.sh <exp dir>` keeps the loop alive across crashes.

More commands:

| command | what |
|---|---|
| `rsi setup <exp> [--answer id=value] [--accept-recommended] [--yolo]` | required before a research run: baseline repeats measure noise, a reviewer agent raises risks and questions, the human (or, for routine and mid-run questions, a human-proxy) decides; `setup/setup.json` owns thresholds and budgets |
| `rsi new-task <name> "<problem>" --data <dir\|kaggle:slug>` | clarification phase: data profile, questions with defaults, a builder agent writes the task pack, the harness verifies the evaluator on the starter |
| `rsi continue <exp> --max-nodes +N [--from n004] [--note "..."]` | extend a finished run: more budget, stall counter reset, optional focus node and a note every worker/planner sees |
| `rsi observe <exp> "<what>" [--node n007] [--metric kaggle_public_lb] [--value 0.228]` | record a result on the real target (e.g. a leaderboard score); the research lead and course corrector see it next to `PROXY.md`, the ledger of how development, forecast and official deltas agree |
| `rsi submit <exp> [--node n008]` | final-level evaluation (e.g. Kaggle submission) with a per-experiment cap and `SUBMISSIONS.md` ledger |
| `rsi ops <exp> "<problem>"` | logistics agent with tools: fixes environments, data prep, evaluator bugs; auto-called after two consecutive evaluator failures |
| `rsi write <exp>` / `rsi report <exp>` / `rsi relabel <exp>` / `rsi reeval <exp>` | narrative for humans; rebuild REPORT.md; recompute verdicts with paired noise; re-run the official evaluator on every node |
| `rsi sentinel [--interval 600] [--kill-orphans] [--prune]` | infra check without an LLM: disk, GPUs, dead orchestrators, orphan processes, stale worktrees |
| `rsi repair <exp>` | harness self-repair: an ops agent fixes recorded harness crashes on a `repair/<ts>` git branch with a test; a human merges |
| `rsi jobd` / `rsi jobs` | job queue daemon and listing (job mode, below) |

## Search explorer

Open an experiment's `tree.html` for an offline, self-contained view: pan/zoom the search tree, follow the best
path, inspect hypotheses/results/code-change summaries, and compare official progress by completed nodes or wall
clock. The searchable ledger and score curve select the same node as the tree. Baselines participate in the best
curve; failed/invalid scores never improve it. Final-level results remain separate from the search score.

`rsi render <experiment>` rebuilds the snapshot; refresh the browser to see updates. Dark/light themes and narrow
screens are supported. Embedded logs are **not automatically anonymized**—review before sharing.
See [visualization guide and tests](docs/VISUALIZATION.md).

## Job mode (long-running evaluations)

Task packs with `job_enabled = true` send every official evaluation through a queue (`rsi jobd`, started automatically)
that assigns GPUs (`CUDA_VISIBLE_DEVICES`), enforces `job_timeout_s`, kills stalled runs (no new curve point for
`job_stall_s`), kills NaN runs, and early-stops runs whose curve is worse than the incumbent's by `margin` for
`patience_points` checkpoints after `warmup_frac`. Jobs write `metrics.jsonl` (`{"step","value"}` per checkpoint) and
`metrics.json` (final score); `job_resumable = true` re-submits a failed job once with `--resume`. Early stopping
counts distinct checkpoints, not daemon polls. Each queue has exactly one daemon (`jobd.lock`); jobs are claimed and
launched atomically, and a restarted daemon adopts live jobs under the same timeout/stall/NaN/early-stop limits (PIDs
are identity-checked before any signal). The attempt number lives in the task monitor, so a restarted controller
waits on the running `--resume` attempt instead of resubmitting attempt 0. Levels replace seed
sets (`job_budgets = { smoke = ..., proxy = ..., full = ... }`): workers iterate on `smoke`, the official score is
`proxy`, and the top `final_top_k` nodes get a `full` run at the end. After the official job the worker's session is
woken once (analysis session) to fold the real result into its handoff. `search.max_gpu_hours` caps the run.
`tasks/toy-longjob` exercises all of this on CPU in a few minutes (`tests/test_jobs.sh`).

## What a node produces (`experiments/<name>/nodes/<id>/`)

- `HYPOTHESIS.md` — what the node was asked to do (from the parent's proposals or the planner)
- `runner.prompt.md`, `runner.jsonl` — the exact prompt and the raw event stream (heartbeat source)
- `PROGRESS.md` — the worker's append-only log (numbers with seed set), written as it goes
- `HANDOFF.md`, `proposals.json` — mandatory outputs; `proposals.json` feeds the scheduler
- `eval/metrics.validation.json` — the **official** score, computed by the harness with the frozen evaluator
- `SUMMARY.md` — auditor output: verified summary, verdict, claim check against official metrics
- `FAILURE.md` — cause and diagnosis when the node failed; `HUMAN.md` — optional note a human leaves before a retry

Global ledgers: `INSIGHTS.md`, `DEADENDS.md` (every line cites a node), `events.jsonl`, `costs.json`, `REPORT.md`.

## Research memory

New runs also maintain a shared, versioned research wiki: immutable experimental evidence, scoped
observations/hypotheses/experience, supporting and opposing evidence, and an evolving motivation/method
agenda. Workers receive a saved memory snapshot. New knowledge triggers review of unused proposals;
bounded research slots prioritize discriminating ablations alongside score improvement.

Existing runs opt in with `rsi memory enable <exp>`, then `rsi memory sync <exp>` and
`rsi memory reflect <exp>`. Import paper excerpts/notes with `rsi memory ingest <exp> --source <file>`.
Use `--no-memory` at initialization for a control run. See [configuration, evidence boundaries, and
validation](docs/RESEARCH_MEMORY.md). Reflections use the configured utility model; no wiki plugin is required.

## Search control

- Root = baseline (starter code evaluated with the official seed set). The planner proposes `width_root` diverse
  first hypotheses.
- Scheduler: pick the **best-scoring expandable node** (depth < `depth`, fewer than `width` counted children), take
  its next unused proposal; if it has none, the planner proposes new children given its handoff, siblings, insights and
  dead ends. Backtracking is implicit: when the best node is exhausted, the next-best node anywhere gets the slot.
- Stop: `max_nodes`, `patience` (consecutive finished nodes without a new global best), `target_score`,
  `max_wallclock_s`, or exhaustion. Why dispatch stopped and what still needs recovery are separate: an incomplete
  handoff, a failed research decision, unfinished nodes, a broken runner or an interrupt defer the final confirmation even when a
  budget stop came first (`final.json` lists them under `faults`; `rsi run` recovers, then confirms).
- Official scores are bound to the evaluation protocol (evaluator files, scoring config, official level/budget,
  `memory.protocol_id`). If it changes, older scores stay on record as `stale` but stop being selection evidence;
  dispatch stops with `protocol_changed` until `rsi reeval` re-measures the baseline (or the evaluator is restored).
- Failed nodes (crash, timeout without usable work, evaluator failure, edits under `eval/`) are diagnosed; a retry with
  the diagnoser's advice starts from the failed node's last commit (`max_retries`).
- Sessions killed at the budget get a **handoff rescue**: the same session is resumed once with a short instruction to
  write `HANDOFF.md` and `proposals.json` only.

## Runners and models

- `grok`: the official Grok CLI in headless mode (`--prompt-file`, `--output-format streaming-json`,
  `--json-schema` for utility calls, pre-assigned `--session-id` so a killed session can be resumed). It uses the
  subscription login of the CLI. The CLI's proxy rejects other clients, so pi cannot talk to the subscription directly.
- `pi`: pinned pi in `--mode json` with any provider pi supports (API keys or pi's own `/login` subscriptions). Add
  custom OpenAI/Anthropic-compatible providers via `~/.pi/agent/models.json`. Model string is `provider/model`,
  effort maps to pi's thinking level. Prompts go to pi on stdin (one argv string is capped at 128 KiB on Linux).
- `script`: an executable stand-in for tests.

Worker and utility runners are configured independently (`[runner]`, `[utility]` in `rsi.toml`).

## Task packs

`tasks/<name>/task.toml` declares the brief, docs, starter directory, evaluator command and seed sets. The evaluator
must write a JSON file with the score key; `quick` seeds are for the worker's iteration, `validation` seeds give the
official node score, `test` seeds are held out for the final report. The harness copies `eval/` and `docs/` into each
repo for the worker's convenience but always scores with its own frozen copy, and any commit touching those paths
fails the node.

`tasks/kaggriculture`: Kaggle's farming-sim competition environment (CPU only, ~2 s per game, deterministic seeds).
Baseline starter ≈ 3,590; a strong hand-engineered agent ≈ 138,000 on the validation seeds. First results
(grok-4.6 vs grok-4.5, one run each, same budget): 24,614 vs 37,329 on validation seeds after 10 and 8 nodes.

## Requirements

- Linux, Python 3.11+, Node 22 (for the pinned pi), git, `uv` or `pip`.
- An agent runtime: the `grok` CLI logged in with a subscription, or any pi-supported provider.

## Tests

```bash
tests/test_loop.sh        # whole loop with a fake agent: planner, failure, diagnoser, retry, audit, report (~1 min)
tests/test_jobs.sh        # job mode: queue daemon, curves, analysis session, top-k final (~3 min, CPU)
tests/test_jobs_unit.py   # daemon kill rules: early stop, NaN, stall, timeout
tests/test_pi_runner.sh   # pi runner against a local mock OpenAI server (incl. a >300 KB prompt via stdin)
python3 -m unittest discover -s tests -p 'test_*.py'   # unit/integration suite; test_unattended.py covers long-run
                          # failure modes: prompt size, protocol changes, budget-vs-fault stops, daemon restarts,
                          # evaluation resume, wiki retries
```
