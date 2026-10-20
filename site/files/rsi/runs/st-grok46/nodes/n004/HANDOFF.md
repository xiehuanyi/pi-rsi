# Handoff n004: Group-consistent missing imputation
## Hypothesis
HomePlanet, Cabin (hence deck/num/side), and often Destination are shared inside a passenger group. After parsing PassengerId groups, fill those fields from non-missing group-mates within the current frame (train and predict separately so CV groups cannot leak). Also apply the almost-hard deck→planet map (A/B/C/T→Europa, G→Earth; F is Earth or Mars so not mapped to a single planet). Keep the current LightGBM and other features. This should cut the ~150 missing HomePlanet/Cabin rows that the booster currently sees as NA.
## What I did
- Left the CLI contract in `train.py` (`--train/--predict/--out`, columns `PassengerId,Transported`). LightGBM hyperparameters unchanged (`src/model.py`).
- Added `src/impute.py`: `fill_unique_per_group` (fill NA only when the group has exactly one distinct known value), `impute_raw_shared_fields` for HomePlanet/Cabin/Destination, hard `DECK_TO_PLANET` (A/B/C/T→Europa, G→Earth).
- Updated `FeatureBuilder._raw` in `src/features.py`: per-frame raw fill, then unique-fill parsed Deck/Side/CabinNum, then deck→planet, then a second HomePlanet group fill (a G-mate can label an F-mate). Train and predict are transformed separately.
- Did not fill F/D/E to a single planet. Did not concatenate train+predict. Did not modify `eval/` or `docs/`.
- Ablated Destination unique-fill (known risk) on the same quick seed set; it was slightly worse, so Destination fill stayed in.
## Result
- Untouched parent quick: score **0.80331** (folds [0.79134, 0.80659, 0.81772, 0.80638, 0.7945], n=6954, elapsed 10.0s).
- Group-consistent imputation quick: score **0.80732** (folds [0.79702, 0.81232, 0.81988, 0.80638, 0.80101], score_std=0.00812, score_sem=0.00363, n=6954, elapsed 11.4s).
- Command: `~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python eval/eval.py --seedset quick --python ~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python`
- Delta vs this node's untouched quick: **+0.00401**. Fold deltas vs parent: +0.00568, +0.00573, +0.00216, 0, +0.00651 (four up, one tied, none down). Below fold std (~0.008), so treat as a small consistent lift, not a clear jump.
- Ablation without Destination fill: quick **0.80674** (folds [0.79631, 0.81734, 0.81916, 0.80348, 0.7974]); fold 3 dropped vs parent. Not shipped.
- On labeled `data/train.csv`, missingness after fill: HomePlanet 152→49, Destination 140→98, Deck 164→91, Side 80 (Side is constant even in mixed-cabin groups).
- Final git commit: `8b05a0e07ece91bb5fe598e6503e4650723da977`
## Mechanism
Planet is literally constant inside a group (0 mixed-planet groups in train). Cabin is shared in about 70% of multi-groups; Side is shared in all of them. A/B/C/T always map to Europa and G always to Earth, including singletons who have no mates. Filling those values removes an NA bucket that mixed Earth-G passengers with Europa-B/C passengers and with people who simply forgot to log a cabin. LightGBM can then split on the same deck/planet/side rules as the observed majority. About 55% of passengers are singletons, so they only benefit from the deck map, not from mates. Destination is mixed in half of multi-groups; unique-only fill changes few rows and did not move the score beyond noise.
## Dead ends
- Skipping Destination unique-fill: quick 0.80674 vs 0.80732 with it; one fold worse than parent. Unique-only Destination fill is not the driver and is not harmful enough to drop.
- Did not hard-map deck F to Earth (Earth 1296 vs Mars 876 on F). Remaining 49 missing HomePlanet rows are mostly F; assigning Earth would be a majority guess, not an almost-hard rule.
## Next hypotheses
- Surname and cabin occupancy: last-name group size and passengers-sharing-a-cabin as numeric counts; families often share outcomes, and occupancy is not in the current feature set.
- Remaining CryoSleep NA: impute True when total amenity spend is 0 (the flag is still missing after forcing spenders awake), and add luxury (Spa+VRDeck) vs food/shopping spend shares.
- Resolve leftover F-deck HomePlanet with last name or spend mix (Earth vs Mars), not a global Earth default; only ~49 train rows remain missing after this node.
## Open questions
- +0.004 is smaller than fold std (~0.008). If official validation does not move, treat this as noise and do not stack more NA-filling on location fields.
- Does integer GroupId still overfit sequential structure in `data/train.csv`? If validation lags quick, ablate GroupId first (open from n001).
- Remaining F-deck / singleton-missing-cabin rows may be better left as NA than weakly imputed.
