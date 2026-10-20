# Progress n014 — Group-consistent missing imputation

## Plan
- Parent is n005 (CabinOccupancy on raw Cabin, LightGBM). Untouched quick target: 0.80818.
- n004 already shipped unique-only group fill + deck→planet without occupancy; official validation did not beat n001. This node tests the interaction: fill Cabin from unique group-mates, then recompute CabinOccupancy so the ~164 missing-cabin rows are not stuck at occupancy 1.
- Per-frame only (train and predict separately). Unique-only fill (do not majority-vote mixed groups). Hard A/B/C/T→Europa, G→Earth. Do not map F/D/E.
- Keep LightGBM, GroupSize, CabinOccupancy. Ablate occupancy-after-fill vs occupancy-before-fill (and Destination fill, known risk).
- Ignore moves smaller than fold std (~0.008) unless all five folds move the same way.

## 2026-09-10 — starting
Reading parent `src/features.py` and n004 `src/impute.py`. Next: data notes on fill coverage, then untouched parent quick via eval.py.

## 2026-09-10 — untouched parent quick

Command:
`~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python eval/eval.py --seedset quick --python ~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python`

**quick 0.80818** folds=[0.80057, 0.80946, 0.82205, 0.80856, 0.80029] n=6954 elapsed=10.5s. Matches n005 shipped.

## Data notes (full public train.csv, n=6954)
- Missing: HomePlanet 152, Cabin 164, Destination 140. Groups 4977; singleton rows 3860 (55.5%).
- HomePlanet is constant in every group (0 mixed). Unique-fill: 152→85; deck map A/B/C/T→Europa, G→Earth: 85→49. Remaining NA decks: F 33, E 9, D 3, missing deck 4.
- Cabin mixed in 340 groups. Unique-fill covers 73 of 164 missing cabins (91 remain, mostly singletons / mixed-cabin groups).
- Destination mixed in 558 groups; unique-fill 140→98. Known noise risk.
- Side unique-fill: 164→80 (Side is shared even when cabin strings differ). Deck unique-fill: 164→91.
- Occupancy on filled Cabin changes 226 rows (the 73 filled passengers plus their cabin-mates). Orig-missing occupancy mean 1.0 → 1.93; 91 stay at 1.
- occ != GroupSize: 1227 before fill, 1001 after.

Implementing unique-only per-frame fill + deck→planet + occupancy after Cabin fill.

## 2026-09-10 — implement and sanity-check

Sanity on full train.csv:
- HomePlanet NA 152→49, Deck 164→91, Side 164→80, Destination 140→98. Matches n004 coverage.
- Occupancy after vs before fill: 226 rows change. occ==1: 4412 (was 4525).
- Train/predict occupancy computed separately (no concat).
- `fill_shared=False` restores parent missingness (HomePlanet 152, Deck 164).

Commit, then same-fold ablation (parent / occ-before / occ-after / no-destination / no-occupancy) and eval.py quick on the shipped occupancy-after config.

## 2026-09-10 — shipped fill + occupancy-after (eval.py quick)

**quick 0.80460** folds=[0.79347, 0.80516, 0.81844, 0.80566, 0.80029] score_std=0.00819 score_sem=0.00366 n=6954 elapsed=11.3s.

Delta vs untouched parent quick 0.80818: **−0.00358**. Fold deltas: −0.00710, −0.00430, −0.00361, −0.00290, 0. Four down, one tied, none up. Below fold std (~0.008) but directionally worse. Not the hypothesized +0.005–0.010.

## Same-fold ablation (in-process, seed 20260910)

| variant | mean | std | vs parent | n_up | folds |
| parent_no_fill | 0.80818 | 0.00793 | 0 | 0/5 | [0.80057, 0.80946, 0.82205, 0.80856, 0.80029] |
| fill_occ_before | 0.80530 | 0.00807 | −0.00288 | 1/5 | [0.79773, 0.80802, 0.81988, 0.79985, 0.80101] |
| fill_occ_after (shipped) | 0.80460 | 0.00819 | −0.00358 | 0/5 | [0.79347, 0.80516, 0.81844, 0.80566, 0.80029] |
| fill_occ_after_nodest | 0.80617 | 0.00676 | −0.00202 | 1/5 | [0.79915, 0.80802, 0.81844, 0.80276, 0.80246] |
| fill_no_occ | 0.80732 | 0.00812 | −0.00086 | 2/5 | [0.79702, 0.81232, 0.81988, 0.80638, 0.80101] |

Notes:
- `parent_no_fill` matches eval.py untouched 0.80818 fold-for-fold.
- `fill_occ_after` matches eval.py shipped 0.80460 fold-for-fold.
- `fill_no_occ` 0.80732 matches n004's group-fill-without-occupancy quick exactly.
- Occupancy-after is slightly worse than occupancy-before. Destination unique-fill slightly worse than skipping Destination. Every fill variant is below occupancy-only parent.
- Do not stack more location NA-fill on this occupancy model. n004 official already failed to beat n001; this node fails to beat n005 on quick.

Shipped the hypothesized occupancy-after config (do not silently revert). Final commit `8fcf5bdc0a38c50cec314dd978e18a95df724ceb`.

Writing HANDOFF.md and proposals.json.
