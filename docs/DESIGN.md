# pi-rsi design notes (v0.1, 2026-09-10)

## Requirements → implementation

| requirement (from the design discussion) | where |
|---|---|
| deliverable/metric fixed before autonomy | task pack: `TASK.md` + frozen `eval/` + seed sets; root baseline evaluated first |
| width-first then depth-first with caps | `scheduler.py`: `width_root` proposals at root, then best-first expansion with `width`/`depth` caps; `patience` and `max_nodes` as budgets |
| backtracking to a good node | implicit: when the best node is exhausted, the next-best expandable node gets the slot; node = git branch + worktree, so backtracking is a checkout |
| tree maintainer that only summarizes | `agents.py` auditor: stateless single-turn call after each node; verifies numbers against official metrics (claim check), writes `SUMMARY.md`, `INSIGHTS.md`, `DEADENDS.md` |
| compact within node, handoff + fresh context between nodes | each node is a fresh headless session; durable state = files (`PROGRESS.md`, `HANDOFF.md`, `proposals.json`); worker prompt is rebuilt from files |
| code vs memory files separated | code in the worktree (git); notes in `nodes/<id>/` outside the repo; global ledgers in the experiment dir |
| modular code norms, git for everything | worker rules (one hypothesis, commit per step, `src/` modules < 400 lines); harness auto-commits and tags `rsi/<id>` |
| citations for every number | handoff/audit rules: numbers carry seed set + command; audit claim check compares with official metrics |
| task monitor without an idle LLM | orchestrator supervises processes (heartbeat from the event stream, wall-clock and idle kills); evaluator runs are subprocesses |
| external agent on unexpected termination | diagnoser (utility) + retry from the last commit; `rsi run` crash recovery; `scripts/supervise.sh` restarts a dead orchestrator |
| visualization for human review | `tree.html` (tree, node panel, score chart, insights/dead ends, table), `tree.md`, `REPORT.md`; `HUMAN.md` in a node dir is read by the next worker |
| workers vs utility agents | `[runner]` (worker) and `[utility]` (planner/auditor/diagnoser) configured separately; utility calls are cheap, no tools, JSON schema |

## Not built yet (next steps)

1. **Clarification phase** (`rsi new-task`): an interactive session that turns a one-line problem into a task pack —
   asks follow-up questions, offers deliverable/metric options, drafts `TASK.md`, `eval/`, and the starter. Today the
   task pack is written by a human.
2. **Compute scheduler** for GPU tasks: a lock/queue so parallel nodes do not oversubscribe the 3090, plus a
   smoke→small→full evaluation ladder driven by the harness rather than by the worker.
3. **Self-improvement loop**: run the same task pack with harness variants (prompts, scheduler parameters) and compare
   with `scripts/compare.py`; the harness commit is recorded in `tree.json` meta for that purpose.
4. **Reviewer pass** on code quality before a node is accepted (currently only the frozen-path guard and the auditor).
5. **pi runner in production**: works against any pi provider (tested with a mock OpenAI server); needs an API key or a
   pi-supported subscription login. The Grok subscription is only reachable through the official Grok CLI.

## Known limits

- Utility calls and the worker share one CLI login; heavy parallelism can hit subscription rate limits.
- Idle timeout is measured on the agent's event stream; a single silent shell command longer than `idle_timeout_s`
  kills the session (defaults: 420-480 s).
- `patience` counts failed nodes as non-improving; a run of infrastructure failures can stop the search early
  (the `runner_broken` breaker stops it even earlier when the runtime itself is dead).
