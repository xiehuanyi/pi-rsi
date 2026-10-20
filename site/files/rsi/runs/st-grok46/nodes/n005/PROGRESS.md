# Progress n005 — Surname and cabin occupancy counts

## Plan
- Read parent n001 LightGBM + cabin/group pipeline (commit b42f6f6).
- Record untouched quick-set score as the starting point.
- Add two numeric features only, computed independently on each frame (train vs predict):
  1. SurnameFreq: last-name frequency in the current frame from `Name`.
  2. CabinOccupancy: number of passengers sharing the same Cabin string in the current frame.
- Missing names (~160) and missing cabins: do not lump NA into one fake family/cabin; treat occupancy as 1.
- Do not one-hot surnames. Do not change the model, imputation, or other features.
- Re-run quick eval and report vs parent 0.80331.

## Data notes (full public train.csv, n=6954)
- Missing Name=160, missing Cabin=164. All non-null names are two tokens.
- 2090 unique surnames; freq mean 3.25, max 17. SurnameFreq != GroupSize on 5839 rows (surnames span groups).
- Cabin occupancy 1–8; corr with GroupSize 0.873; != GroupSize on 1227 rows (groups split across cabins / missing cabin).
- Cabins with >1 group: 0 in this file (so per-frame occupancy should not leak across the group fold cut).
- Mixed-name groups: 200 of 4977.
- Transport rate: solo cabin 0.45 vs occ 2–4 ~0.59–0.61; surname freq weakly inverse.

## 2026-09-10 — untouched parent baseline (quick)

Command:
`~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python eval/eval.py --seedset quick --python ~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python`

Expect ~0.80331 from n001. Running now.

Result: **quick 0.80331** folds=[0.79134, 0.80659, 0.81772, 0.80638, 0.7945] elapsed=10.1s. Matches n001.

## 2026-09-10 — add SurnameFreq + CabinOccupancy

Changed `src/features.py` only:
- `NUM_FEATURES` += SurnameFreq, CabinOccupancy
- `_frame_count`: value_counts on current frame, NA keys -> 1
- `_raw`: last token of Name; Cabin string occupancy

Sanity: missing names/cabins get 1; shared surnames get different counts on train vs predict frames; no one-hot.

Commit then re-run quick eval.

## 2026-09-10 — both features (quick, eval.py)

**quick 0.80374** folds=[0.78708, 0.81734, 0.81628, 0.80203, 0.79595] score_std=0.01169 score_sem=0.00523 n=6954 elapsed=10.8s.

Delta vs untouched parent quick 0.80331: **+0.00043**. Fold signs mixed (2/5 up). Fold std rose 0.00947 → 0.01169. Noise, not progress.

## Same-fold ablation (in-process, seed 20260910, matches eval folds)

| variant | mean | std | folds | vs neither | n_up |
| neither (parent) | 0.80331 | 0.00947 | [0.79134, 0.80659, 0.81772, 0.80638, 0.7945] | 0 | 0/5 |
| surname only | 0.80603 | 0.01180 | [0.79063, 0.82235, 0.81556, 0.80566, 0.79595] | +0.00272 | 2/5 |
| cabin only | 0.80818 | 0.00793 | [0.80057, 0.80946, 0.82205, 0.80856, 0.80029] | +0.00488 | 5/5 |
| both | 0.80374 | 0.01169 | [0.78708, 0.81734, 0.81628, 0.80203, 0.79595] | +0.00043 | 2/5 |

Mechanism: global last-name frequency spans unrelated groups (corr with GroupSize only 0.35; max freq 17). LightGBM spends splits on it (importance 856, near spend logs) and it cancels cabin occupancy. CabinOccupancy != GroupSize on 1227 rows (groups split across cabins); solo cabin transport 0.45 vs occ 2–4 ~0.59. No multi-group cabins in this file.

Decision: drop SurnameFreq, ship CabinOccupancy only. Global surname count is a dead end; within-group surname size is a later hypothesis.

## 2026-09-10 — cabin occupancy only (quick)

Re-run eval.py after removing SurnameFreq.

Result: **quick 0.80818** folds=[0.80057, 0.80946, 0.82205, 0.80856, 0.80029] score_std=0.00793 score_sem=0.00355 n=6954 elapsed=10.7s.

Delta vs parent quick 0.80331: **+0.00487**. All 5 folds up. Fold std fell 0.00947 → 0.00793.

Matches the in-process cabin-only ablation. Shipped. Final commit `c84451444a39741e5e9f84e84468a387d52c431b`.

Writing HANDOFF.md and proposals.json.
