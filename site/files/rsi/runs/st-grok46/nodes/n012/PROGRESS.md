# n012 progress

## Setup
- Worktree `node/n012` at parent commit `5469a860e21c8013e79cc6d8f0a52c0ce7f78653` (n009: CryoSleep remaining NA + spend mix).
- Hypothesis: ablate integer `GroupId` from `NUM_FEATURES`. Keep GroupSize, Deck/Side, spend columns. Do not add features or retune trees.
- `GroupId` is only in `src/features.py` (`NUM_FEATURES` and `_raw`).

## 2026-09-10 — untouched parent quick (before any code change)
Running eval/eval.py --seedset quick on the n009 code as shipped.

Result (seedset=quick, metrics.quick.json):
- score **0.80718**
- folds [0.79773, 0.8159, 0.81124, 0.80783, 0.80318]
- score_std=0.0063, score_sem=0.00282, n=6954, elapsed_s=11.0
- Matches n009 shipped quick exactly. Baseline for this ablation.

## 2026-09-10 — ablation: drop GroupId
Change: remove `GroupId` from `NUM_FEATURES` and stop writing it in `_raw`. Still compute the gggg group key for GroupSize and unique group-mate fills. No new features. LightGBM hyperparameters in `src/model.py` unchanged.

About to run eval/eval.py --seedset quick on the ablated code.

Result (seedset=quick, metrics.quick.json, commit 742b6bbb6e9f85bebafc6b95fc91bf540beb6aa6):
- score **0.80761**
- folds [0.7956, 0.81805, 0.81628, 0.80348, 0.80463]
- score_std=0.00842, score_sem=0.00377, n=6954, elapsed_s=11.4
- Delta vs untouched parent quick 0.80718: **+0.00043**
- Fold deltas vs parent: −0.00213, +0.00215, +0.00504, −0.00435, +0.00145 (three up, two down)
- Fold std 0.0063 → 0.00842. Treat as no change on quick (below fold std).

Command: `~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python eval/eval.py --seedset quick --python ~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python`

## Mechanism diagnostics (not official eval; train on data/train.csv)
- Parent-like model (GroupId added back only for this probe): CabinNum 2220 splits, GroupId 2158, Age 1874. Matches n009 claim.
- Ablated model: CabinNum 3054, Age 2041, log_TotalSpend 1537. GroupId splits moved mostly onto CabinNum.
- corr(GroupId, CabinNum)=0.6813; corr(GroupId, Transported)=0.0225; corr(CabinNum, Transported)=−0.0453
- Consecutive groups same Deck=0.2445 (≈ independent, majority F=0.355 so sum p^2 ~0.24); same Side=0.4862 (~chance). GroupId is not a nearby-deck proxy.
- HomePlanet NA after n004 fills still 49: F=33, E=9, NA cabin=4, D=3. Earth vs Mars luxury share among spenders: 0.406 vs 0.145.

Shipped ablation as specified. Did not retune trees. Did not add features.

