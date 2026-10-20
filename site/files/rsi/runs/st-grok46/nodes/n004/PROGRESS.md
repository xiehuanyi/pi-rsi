# n004 progress

## Start
- Branch `node/n004` at parent commit `b42f6f6` (n001 LightGBM + cabin/group features).
- Hypothesis: group-consistent missing imputation for HomePlanet/Cabin/Destination + deck→planet map; train and predict filled separately.
- Parent worker quick: 0.80331 (score_std=0.00947). Official validation 0.8177.
- Data (train 6954 rows): HomePlanet missing 152 (group-unique fill 67, 0 conflicts, 85 all-missing); Cabin missing 164 (unique-cabin fill 73, 11 mixed-cabin groups, 80 all-missing); Destination missing 140 (unique fill 42, 18 mixed, 80 all-missing). Side is 100% constant in multi-groups; Deck mixed iff Cabin mixed. Deck→planet hard map: A/B/C/T=Europa, G=Earth. After group+hard map, HomePlanet missing 49 (mostly F). Singletons 55.5%.
- Running untouched parent code on quick seed set as the starting point.

## Untouched quick (parent code)
- Command: `.venv/bin/python eval/eval.py --seedset quick --python .venv/bin/python`
- quick: score **0.80331** folds=[0.79134, 0.80659, 0.81772, 0.80638, 0.7945] score_std from parent 0.00947, n=6954, elapsed=10.0s.
- Matches n001 worker quick exactly.

## Implementation
- Added `src/impute.py`: `fill_unique_per_group`, `impute_raw_shared_fields` (HomePlanet/Cabin/Destination from unique mates in this frame only), hard `DECK_TO_PLANET` A/B/C/T→Europa, G→Earth. F/D/E not mapped to a single planet.
- `FeatureBuilder._raw` now: per-frame raw fill → parse cabin → unique-fill Deck/Side/CabinNum → deck map → second HomePlanet group fill (G-mate can label an F-mate).
- Train-set missing after fill: HomePlanet 152→49, Destination 140→98, Deck 164→91, Side 80. Leak test: mates only in another frame stay NA. Mixed Destination not filled.
- Smoke: `train.py` writes 4277 rows PassengerId,Transported.
- Commit `8b05a0e`. Running quick eval.

## Quick eval with full group fill (planet+cabin+destination+deck map)
- Command: `.venv/bin/python eval/eval.py --seedset quick --python .venv/bin/python`
- quick: score **0.80732** folds=[0.79702, 0.81232, 0.81988, 0.80638, 0.80101] score_std=0.00812 score_sem=0.00363 n=6954 elapsed=11.0s.
- vs untouched 0.80331 folds=[0.79134, 0.80659, 0.81772, 0.80638, 0.7945]: **+0.00401**. Fold deltas: +0.00568, +0.00573, +0.00216, 0, +0.00651. Four folds up, one tied, none down.
- Below fold std (~0.008–0.009) so noisy, but direction is consistent. Expected +0.005–0.010; we landed at the low end.
- Ablating Destination fill next (known risk: Destination mixed in ~half of multi-groups).

## Ablation: no Destination group fill (planet+cabin+deck map only)
- quick: score **0.80674** folds=[0.79631, 0.81734, 0.81916, 0.80348, 0.7974] elapsed=12.0s.
- vs with-Destination 0.80732: **-0.00058**. vs parent: fold 3 dropped (0.80638→0.80348). Unique Destination fill is small but not harmful here.
- Keep Destination unique-fill as in the hypothesis. Restoring SHARED_COLS and re-running quick so metrics.quick.json matches the shipped code.

## Shipped quick (Destination unique-fill restored; reproduced)
- quick: score **0.80732** folds=[0.79702, 0.81232, 0.81988, 0.80638, 0.80101] score_std=0.00812 n=6954 elapsed=11.4s.
- Final commit: `8b05a0e07ece91bb5fe598e6503e4650723da977`
- Writing HANDOFF.md and proposals.json.

