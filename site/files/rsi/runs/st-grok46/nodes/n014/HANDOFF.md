# Handoff n014: Group-consistent missing imputation
## Hypothesis
HomePlanet, Cabin (hence deck/num/side), and often Destination are shared inside a passenger group. After parsing PassengerId groups, fill those fields from non-missing group-mates within the current frame (train and predict separately). Also apply the almost-hard deck-to-planet map (A/B/C/T to Europa, G to Earth). Keep current LightGBM, GroupSize, and CabinOccupancy. Recompute CabinOccupancy after filling Cabin so the 164 missing-cabin rows are not stuck at occupancy 1. Do not concatenate train+predict to fill.
## What I did
- Left the CLI contract in `train.py` and did not change `src/model.py`, `eval/`, or `docs/`.
- Added `src/impute.py`: `fill_unique_per_group` (fill NA only when the group has exactly one distinct known value), `impute_raw_shared_fields` for HomePlanet/Cabin/Destination, hard `DECK_TO_PLANET` (A/B/C/T→Europa, G→Earth; not F/D/E).
- Updated `FeatureBuilder._raw` in `src/features.py`: per-frame unique fill, unique-fill parsed Deck/Side/CabinNum, deck→planet then a second HomePlanet group fill, `CabinOccupancy` counted on the filled Cabin string. Train and predict are transformed separately.
- Constructor flags (`fill_shared`, `fill_destination`, `occupancy_after_fill`, `include_occupancy`) default to the hypothesized shipped config and were used only for same-fold ablation.
- Ablated occupancy-after-fill vs occupancy-before-fill, Destination fill, and occupancy-off on the same quick folds (eval seed 20260910).
## Result
- Untouched parent quick: score **0.80818** (folds [0.80057, 0.80946, 0.82205, 0.80856, 0.80029], score_std=0.00793, n=6954, elapsed=10.5s).
- Group-fill + occupancy-after-fill (eval.py): score **0.80460** (folds [0.79347, 0.80516, 0.81844, 0.80566, 0.80029], score_std=0.00819, score_sem=0.00366, n=6954, elapsed=11.3s). Delta **−0.00358**. Fold deltas −0.00710, −0.00430, −0.00361, −0.00290, 0 (4/5 down, 1 tied, none up).
- Command: `~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python eval/eval.py --seedset quick --python ~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python`
- Same-fold ablation: parent_no_fill 0.80818; fill_occ_before 0.80530 (1/5 up, −0.00288); fill_occ_after 0.80460 (0/5 up, −0.00358, matches eval.py); fill_occ_after_nodest 0.80617 (1/5 up, −0.00202); fill_no_occ 0.80732 (2/5 up, −0.00086; same as n004's fill-without-occupancy quick).
- On labeled `data/train.csv`: HomePlanet NA 152→49, Destination 140→98, Deck 164→91, Side 164→80; 73 of 164 missing cabins uniquely fillable; occupancy changes on 226 rows after fill.
- These are quick-set numbers. Official validation is computed by the harness on a hidden holdout.
- Final git commit: `8fcf5bdc0a38c50cec314dd978e18a95df724ceb`
## Mechanism
Planet is constant inside a group and A/B/C/T/G decks map hard to a planet, so unique-fill plus the deck map really does cut HomePlanet NA (152→49) and Side NA (164→80). That does not raise accuracy on this occupancy model. LightGBM already splits on Deck/Side/GroupSize/CabinOccupancy; turning missing cabin/planet into imputed values removes an NA bucket and, when occupancy is recomputed, also increments occupancy for cabin-mates of the 73 fillable missing-cabin rows (226 rows change). Those reconstructed occupancies are not a cleaner "sharing a room" signal: occupancy-after is the worst occupancy timing, occupancy-before is still below parent, and fill without occupancy only recovers n004's 0.80732, which is still below n005 occupancy-only 0.80818. Destination is mixed in 558 groups; unique-only Destination fill is a small extra drag. About 55% of rows are singletons and gain nothing from mates. Combined with n004's official drop vs n001, location NA-fill is not a lever on top of GroupSize/occupancy.
## Dead ends
- Unique group fill of HomePlanet/Cabin/Destination plus deck→planet, occupancy counted after Cabin fill: eval.py quick 0.80460 vs parent 0.80818; 4/5 folds down, 1 tied. Do not retry this stack.
- Occupancy counted on raw Cabin while still filling location fields: same-fold 0.80530, still below parent (1/5 up). The occupancy-after vs before interaction is real but both lose.
- Skipping Destination unique-fill: same-fold 0.80617 vs 0.80460 with it; still below parent. Destination is not the whole problem.
- Group fill without CabinOccupancy: same-fold 0.80732, matching n004, still below n005 occupancy-only. Fill and occupancy do not add.
## Next hypotheses
- Ablate CabinOccupancy (keep GroupSize and drop the occupancy column). n005 occupancy lifted quick +0.00487 but official validation 0.8097 vs n001 0.8177; this node shows occupancy-after-fill is actively worse than occupancy-off under group fill. Occupancy may be a quick-set artifact.
- Spend mix (luxury Spa+VRDeck vs food/shopping shares) and leftover CryoSleep NA→True when total spend is 0, without more location filling. n008 is the global best with that structure; this occupancy lineage has not tried it. Prefer spend/cryo domain rules over NA-filling planet/cabin.
- Ablate integer GroupId on the occupancy model (no location fill). n012 dropping GroupId was flat on a different parent; n005 still carries sequential gggg, and n001 left it unablated.
## Open questions
- n004 location fill already failed official validation (0.8137 vs n001 0.8177). If this node's official score also lags, treat group-consistent planet/cabin fill as closed on both the n001 and n005 lineages.
- CabinOccupancy helped all five quick folds on n005 and hurt official. If occupancy is the reason n005 lagged n001, dropping it (without group fill) is the higher-leverage next test than any more imputation.
- Remaining 49 HomePlanet NA are mostly deck F (Earth vs Mars). n013 is already testing spend-mix on leftover F; do not majority-map F to Earth.
