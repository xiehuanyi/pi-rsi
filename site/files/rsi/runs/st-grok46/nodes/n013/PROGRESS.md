# Progress n013: F-deck leftover HomePlanet from spend mix

## Plan
1. Read current pipeline (n009 parent) and confirm leftover HomePlanet NA after unique-group fill + A/B/C/T/G deck map.
2. Measure amenity-mix (LuxuryShare) and last-name separation of known F-deck Earth vs Mars.
3. Fit a tiny LightGBM-free rule/classifier on known F-deck rows; apply only to leftover F-deck NA. Leave E/D/missing-cabin NA as NA. Do not hard-map all F to Earth.
4. Record untouched parent quick score, then ship the fill and re-run `--seedset quick`.

## Status
Starting. Code is parent n009: unique-group fill, hard A/B/C/T/G deck→planet, cryo zero-spend True, LuxuryShare/FoodShoppingShare, LightGBM.

## Untouched parent quick
Command: `.venv/bin/python eval/eval.py --seedset quick --python .venv/bin/python`
quick: score **0.80718** (folds [0.79773, 0.8159, 0.81124, 0.80783, 0.80318], n=6954, elapsed 11.2s). Matches n009 handoff.

## Analysis (data/train.csv, after n004 unique-group + A/B/C/T/G deck map)
- HomePlanet NA: raw 152 → unique-group 85 → deck map+group 49. Leftover by deck: F 33, E 9, missing-cabin 4, D 3.
- Known F: Earth 1304 / Mars 895 (never Europa). F spenders: Earth luxury mean 0.401 vs Mars 0.147; Mars room-service share 0.492 vs Earth 0.200.
- F zero-spend: 19 Earth vs 490 Mars — zeros look like Mars, not a global F→Earth majority.
- Luxury-only threshold on known F spenders is worse than majority Earth (~0.55 vs 0.76). Luxury-only on all known F (zeros→Mars) reaches ~0.71.
- Tiny LR on luxury share + room-service share + zero-spend, 5-fold on known F: **0.840**. Zero-spend coef strongly Mars; luxury strongly Earth.
- Last names among known F: 1087 surnames, 0 mixed-planet. Group-LOO last-name→planet acc **1.0** (coverage 0.685). 21/33 leftover F have a unique F-deck surname map (13 Earth, 8 Mars).
- test.csv leftover F: 16 (plus E 9, D 5, missing 1).

## Implementation
`src/impute.py`: `fill_f_deck_homeplanet` — unique last-name→Earth/Mars among known F in the frame, then LogisticRegression on luxury share, room-service share, zero-spend for remaining leftover F. Applied only where Deck==F and HomePlanet still NA. E/D/missing-cabin left NA. Not a bulk F→Earth map.
`src/features.py`: call it after group fill + hard deck map.

Sanity: train leftover F 33→0 (23 Earth, 10 Mars); non-F leftover stay NA (features HomePlanet NA 15). test leftover F 16 filled; remaining NA 14. CLI `train.py` writes PassengerId,Transported.

## Official quick (last-name + spend-mix LR)
quick: score **0.80660** (folds [0.79915, 0.81304, 0.81052, 0.80638, 0.80391], score_std=0.00489, score_sem=0.00219, n=6954, elapsed 11.1s).
Delta vs parent **−0.00058**. Fold deltas: +0.00142, −0.00286, −0.00072, −0.00145, +0.00073.

## Worker same-fold ablation (group split seed 20260910, not official eval.py)
- none (parent-like): **0.80718** folds [0.79773, 0.8159, 0.81124, 0.80783, 0.80318]
- last-name only: **0.80475** (Δ −0.00243) — unique F-deck surname→planet hurts despite 1.0 LOO planet acc
- spend-mix LR only: **0.80760** (Δ +0.00042)
- both (first ship): **0.80660** (matches official quick)

Last name is the drag. Dropping it; shipping spend-mix LR only (the titled hypothesis). Re-running official quick.

## Official quick (spend-mix LR only, shipped)
quick: score **0.80760** (folds [0.80057, 0.81519, 0.8098, 0.81001, 0.80246], score_std=0.00537, score_sem=0.0024, n=6954, elapsed 11.0s).
Delta vs parent **+0.00042**. Fold deltas: +0.00284, −0.00071, −0.00144, +0.00218, −0.00072. Inside fold noise; no change.
Train leftover F 33 filled; remaining HomePlanet NA 16 (E/D/missing-cabin).
Commit: `15411ee95a396d7001694b8c1434a13dde6768d5`

## Finish
Wrote HANDOFF.md and proposals.json. Shipped spend-mix-only leftover F fill. Last-name planet map is a dead end on this node.
