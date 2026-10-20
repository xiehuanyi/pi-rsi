# Handoff n005: Surname and cabin occupancy counts
## Hypothesis
Add two numeric features only: (1) last-name frequency in the current frame from Name, (2) number of passengers sharing the same Cabin string. Do not one-hot surnames. Families and cabin-mates often share Transported; the parent model only has GroupSize, which misses mixed-name groups and groups split across cabins. Counts are computed independently on train vs predict so occupancy cannot leak across the group-aware fold cut. Missing names/cabins are occupancy 1 (do not lump NA into one fake key).
## What I did
- Left the CLI contract in `train.py` and did not change `src/model.py`, `eval/`, or `docs/`.
- In `src/features.py`: added `_frame_count` (per-frame `value_counts`, NA to 1) and `CabinOccupancy` on the raw Cabin string. First also added `SurnameFreq` (last token of Name).
- Same-fold ablation (eval seed 20260910) of neither / surname / occupancy / both. Global surname frequency cancelled occupancy, so the shipped model keeps occupancy and drops surname.
## Result
- Untouched parent quick: score **0.80331** (folds [0.79134, 0.80659, 0.81772, 0.80638, 0.7945], score_std=0.00947, n=6954, elapsed=10.1s).
- Both features (eval.py): score **0.80374** (folds [0.78708, 0.81734, 0.81628, 0.80203, 0.79595], score_std=0.01169, n=6954, elapsed=10.8s). Delta **+0.00043**, 2/5 folds up.
- Same-fold ablation (in-process, same folds as eval.py): neither 0.80331; surname only 0.80603 (2/5 up, +0.00272); cabin only 0.80818 (5/5 up, +0.00488); both 0.80374 (2/5 up, +0.00043).
- Shipped cabin occupancy only, eval.py quick: score **0.80818** (folds [0.80057, 0.80946, 0.82205, 0.80856, 0.80029], score_std=0.00793, score_sem=0.00355, n=6954, elapsed=10.7s). Delta vs parent quick: **+0.00487**. All five folds moved up; fold std fell.
- Command: `~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python eval/eval.py --seedset quick --python ~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python`
- These are quick-set numbers. Official validation is computed by the harness on a hidden holdout.
- Final git commit: `c84451444a39741e5e9f84e84468a387d52c431b`
## Mechanism
GroupSize counts booking-group members, not who actually shares a cabin. In public train, no cabin spans two groups, but 1227 rows have CabinOccupancy not equal to GroupSize because groups split across cabins or have missing Cabin. Solo cabins transport at 0.45; occupancy 2-4 at about 0.59-0.61. A per-frame cabin-string count lets trees split "sharing a room" separately from "booked together." Global last-name frequency does not: 2090 surnames, max freq 17, corr with GroupSize only 0.35, because common names span unrelated groups. LightGBM spent many splits on SurnameFreq (importance about 856, near the spend logs) and the extra noise cancelled occupancy. Missing Cabin treated as occupancy 1 is correct; treating all NA cabins as one room would be a fake shared cabin.
## Dead ends
- Global last-name frequency as a numeric count: eval.py both-features 0.80374 vs parent 0.80331; surname-only same-fold 0.80603 with mixed fold signs (2/5 up) and higher fold std (0.01180). Do not one-hot surnames and do not retry frame-wide surname counts.
## Next hypotheses
- Group-consistent missing imputation: fill HomePlanet/Cabin/Destination from group-mates (and deck to planet rules) inside each frame. 164 missing cabins are currently occupancy 1; filling them should also make CabinOccupancy more accurate.
- Within-group family size, not global surname frequency: count of group-mates sharing the last name (or nunique surnames in the group). 200 of 4977 groups are mixed-name; that is the leftover family signal GroupSize and occupancy miss.
- Spend mix + leftover CryoSleep NA: luxury (Spa+VRDeck) vs food/shopping shares, and impute CryoSleep=True when total spend is 0 and the flag is still missing after the spender-to-awake rule.
## Open questions
- Cabin occupancy is correlated 0.87 with GroupSize. If the hidden holdout has a different cabin-sharing mix, the +0.005 quick lift may shrink; ablate occupancy if validation lags.
- Group-filling missing Cabin will change occupancy on about 164 rows; run occupancy with and without that fill rather than assuming they add.
- Integer GroupId (booking order) is still unablated; if validation lags quick, drop GroupId before touching occupancy.
