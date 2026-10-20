# Progress n001: Gradient boosting + cabin/group features

## Plan
1. Read baseline code/docs (done).
2. Run untouched `quick` eval as starting point.
3. Replace logistic regression with LightGBM; add cabin deck/num/side, group id/size, categoricals, log1p spends, Age median + CryoSleep-from-spend imputation.
4. Re-run `quick` eval; commit if the gain is real vs fold std.
5. Write HANDOFF.md and proposals.json.

## Notes
- Entry point is `train.py` (no `agent.py` in this task).
- Parent/root official validation score: 0.7717. Baseline is logistic regression on spend + age + CryoSleep.
- Hypothesis expects ~0.80–0.81 on a solid tabular GBDT setup.

## 2026-09-10 start
Read `docs/DATA.md`, `TASK.md`, `train.py`, `src/features.py`, `src/model.py`. Worktree is clean at `8d0b51e`. About to run baseline quick eval.

## Baseline quick (untouched logistic regression)
Command: `eval/eval.py --seedset quick` with the task venv python.
- quick: score **0.76335**, n=6954, folds=[0.74947, 0.76504, 0.76369, 0.76432, 0.77424], elapsed=5.6s
- Parent official validation was 0.7717 (different seed set; do not compare directly).

## Implementation
Replaced logistic regression with LightGBM (500 trees, lr=0.05, seed=42, n_jobs=1).
Features in `src/features.py`:
- Cabin -> Deck / CabinNum / Side
- PassengerId -> GroupId (int) + GroupSize
- native pandas categoricals: HomePlanet, Destination, Deck, Side, CryoSleep, VIP
- log1p spends + log1p TotalSpend + Age (train median)
- CryoSleep forced False when any spend > 0

Smoke test: train 6954 x 16, test 4277 x 16, CryoSleep NA after spend rule = 86 (100 spenders filled). Commit `b42f6f6`.

## Quick eval of LightGBM (first attempt)
Command: `eval/eval.py --seedset quick` with the task venv python.
- quick: score **0.80331**, n=6954, folds=[0.79134, 0.80659, 0.81772, 0.80638, 0.7945], score_std=0.00947, score_sem=0.00424, elapsed=10.4s
- vs untouched logistic quick 0.76335: **+0.03996**. Every fold beat the baseline's best fold (0.77424). Gain is well above fold std.
- Matches the hypothesized jump into the 0.80–0.81 band. Not iterating further on this node (one hypothesis; extra knobs would be a new node).

## Stop
Hypothesis confirmed on quick. Writing HANDOFF.md and proposals.json. Final commit `b42f6f6b1e8be385ac191fc21090a04c9aee5fff`.
