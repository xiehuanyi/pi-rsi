# pi-rsi — auto-research harness (tree search + handoffs around headless coding agents)

[English](README.md) · [简体中文](README.zh-CN.md)

Status: v0.1, research prototype. Built and tested on one Linux workstation with the Grok CLI and a pinned
[pi](https://github.com/earendil-works/pi) 0.85.1. MIT licensed. Experiment write-ups: https://blog.pocketplay.win/rsi/

## Real experiment: airline satisfaction

A real RTX 2080 Ti search is archived with an offline chart, the full search explorer, aggregate metrics,
and exact baseline/current-best source. It is a preliminary snapshot of a continuing campaign.
Read the [English README](examples/airline-s6e10-2080ti-20261004/README.md) or
[中文 README](examples/airline-s6e10-2080ti-20261004/README.zh-CN.md).

![Airline experiment score progression](examples/airline-s6e10-2080ti-20261004/preview.png)

pi-rsi runs a long-horizon research loop: it takes a task pack (problem statement, starter code, **frozen evaluator**),
grows a search tree of hypotheses, and lets a headless coding agent implement one hypothesis per node in its own git
worktree. Every node ends with a machine-parsed handoff, an official score computed by the harness, and an audited
summary. Utility agents (planner, auditor, diagnoser) are separated from the workers and run as cheap single-turn
structured calls. Nothing in the loop keeps an LLM idle: waiting, timeouts, retries, and crash recovery are plain code.

```
task pack ──► root baseline ──► planner (k hypotheses) ──► worker per node (worktree) ──► official eval ──► auditor
                                     ▲                                                                       │
                                     └──────── scheduler: best-first, width/depth/patience caps ◄────────────┘
```

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
rsi run demo               # resumable; Ctrl-C stops after in-flight nodes finish
rsi status demo
xdg-open ~/.pi-rsi/experiments/demo/tree.html   # re-rendered after every event
```

`rsi run` on an existing experiment resumes it: nodes that were running when the process died are marked failed,
diagnosed, and retried from their last commit. `scripts/supervise.sh <exp dir>` keeps the loop alive across crashes.
`rsi ops <exp> "<problem>"` hands an infrastructure problem to the logistics agent; `rsi write <exp>` produces a
human narrative; `rsi relabel <exp>` recomputes verdicts with the paired noise estimate.

## What a node produces (`experiments/<name>/nodes/<id>/`)

- `HYPOTHESIS.md` — what the node was asked to do (from the parent's proposals or the planner)
- `runner.prompt.md`, `runner.jsonl` — the exact prompt and the raw event stream (heartbeat source)
- `PROGRESS.md` — the worker's append-only log (numbers with seed set), written as it goes
- `HANDOFF.md`, `proposals.json` — mandatory outputs; `proposals.json` feeds the scheduler
- `eval/metrics.validation.json` — the **official** score, computed by the harness with the frozen evaluator
- `SUMMARY.md` — auditor output: verified summary, verdict, claim check against official metrics
- `FAILURE.md` — cause and diagnosis when the node failed; `HUMAN.md` — optional note a human leaves before a retry

Global ledgers: `INSIGHTS.md`, `DEADENDS.md` (every line cites a node), `events.jsonl`, `costs.json`, `REPORT.md`.

## Search control

- Root = baseline (starter code evaluated with the official seed set). The planner proposes `width_root` diverse
  first hypotheses.
- Scheduler: pick the **best-scoring expandable node** (depth < `depth`, fewer than `width` counted children), take
  its next unused proposal; if it has none, the planner proposes new children given its handoff, siblings, insights and
  dead ends. Backtracking is implicit: when the best node is exhausted, the next-best node anywhere gets the slot.
- Stop: `max_nodes`, `patience` (consecutive finished nodes without a new global best), `target_score`,
  `max_wallclock_s`, or exhaustion.
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
  effort maps to pi's thinking level.
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
tests/test_pi_runner.sh   # pi runner against a local mock OpenAI server
```
