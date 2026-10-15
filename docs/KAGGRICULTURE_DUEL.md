# Kaggriculture outcome trial

The September 13 pilot changes the local selection objective from mean money against starter
to mean(win + 0.5 * draw) against four fixed archived controllers. Money remains diagnostic.
The environment is pinned to kaggle-environments 1.32.7 and its engine-source hash.

The pool contains our archived V45, V47, berry-completion controller, and the pi-rsi melon winner.
The starting candidate is archived V45 plus the previously corroborated animal-overlay procurement
repair. The older repair improved money on one synthetic opponent family without improving outcomes;
it is retained infrastructure, not a new research contribution.

All opponents have separate import namespaces and fresh per-game state. Their source hashes,
provenance, and transformed-file hashes are frozen in the generated protocol manifest. A full-game
check compared the original berry package with its namespaced copy on seed 1103 against starter:
action-sequence hashes and final rewards matched exactly. This checks that transformation on that
trajectory; it does not establish the opponent's coverage of the live population.

## Protocol

- Smoke: 1 seed × 2 seats × 4 opponents = 8 games.
- Development: 2 seeds × 2 seats × 4 opponents = 16 games.
- Local selection: 6 distinct seeds × 2 seats × 4 opponents = 48 games.
- Confirmation: 12 new seeds × 2 seats × 4 opponents = 96 games per locked controller.
- Candidate errors count as losses. Opponent/environment failures invalidate the evaluation.
- Seed-level blocks keep both seats and all opponents together for paired uncertainty.
- Requested action counters are labeled requested; they do not count accepted operations.

The controller pool is correlated and incomplete. Historical outcome trends informed its selection
before this run. New confirmation seeds test transfer within this same pool; they do not establish
live-ladder performance or clear the older competition project's opponent-calibration gate.
This pilot does not change that project's production entry point or submit to Kaggle.

## Reproduce

Create a new local task pack from the existing user-owned controller archive:

    python3 scripts/create_duel_task.py --archive /path/to/Kaggriculture --out experiments/_tasks/kaggriculture-duel-v1

The factory requires the original Kaggriculture task's pinned virtualenv, the two archived controller
files, berry deployment archive, prior procurement repair sources, and pi-rsi's existing melon n008
worktree. It refuses to overwrite a task. Generated code/data stay in the local experiments directory;
the generic factory and evaluator are versioned in the harness.

Initialize a memory-enabled run with that task path. The pilot uses four non-root nodes, two concurrent
workers, 10-minute initial worker budgets, and a 30-minute coordinator search budget. Handoff rescue
and already-running work may finish afterward. Reflection runs after two new records.

Historical knowledge is explicitly imported as a transferred hypothesis source. No old mean-money
score is directly compared to the new outcome score. A code-inspection note about zero-inventory
handling was added at 08:44:52 UTC, after n001/n002 dispatch; those saved prompts did not contain it.
Later planner/worker prompts can use it. Exact prompts and memory snapshots record this boundary.

After all nodes finish:

    python3 scripts/duel_delivery.py experiments/kag-duel-memory-20260913

This locks the local-selection winner before confirmation, records exact candidate hashes, evaluates
baseline and candidate on the reserved seeds, computes an exact two-sided paired sign-flip test over
seed blocks, and packages a main.py tarball. Corroboration requires positive mean outcome gain,
p <= 0.05 under seed-block exchangeability, no per-opponent aggregate regression, and no candidate
errors. Results failing this rule remain inconclusive or worse. Selecting multiple candidates on these
confirmation results would invalidate this interpretation.

The package gets a full self-play check through the official environment's file loader. This is a
local compatibility check, not a Kaggle service certification. The delivery command never submits.
Confirmation artifacts live outside node evidence, and the research wiki does not automatically
ingest them. A different candidate cannot reuse an already-locked confirmation through this command.

## Artifacts

The pilot directory is experiments/kag-duel-memory-20260913. It contains the search tree, exact worker
prompts, hypotheses, progress/handoffs, official local metrics, memory revisions, and coordinator log.
OPPONENT_PARITY.json records the import-parity check. delivery/ stores the locked candidate,
paired comparison, package manifest, self-play result, and readable RESULTS.md.
