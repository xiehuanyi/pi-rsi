# Handoff n002: CryoSleep-consistent spend imputation + shallow HGB

## Hypothesis
CryoSleep passengers cannot spend on amenities (zero exceptions in labeled data). Impute missing CryoSleep from spend (any spend>0 → False; all NaN/0 → True), zero spends when CryoSleep=True, add ZeroSpend/HasAnySpend flags, one-hot HomePlanet/Destination/Cabin-deck, and fit LogisticRegression or a shallow HistGradientBoostingClassifier. Expected +0.015 to +0.03 by fixing label-aligned missingness that the baseline treats as independent noise.

## What I did
- `src/features.py`: `apply_cryo_spend_rules` (row-wise; no fitted stats) and `FeatureBuilder` (train-only age median and dummy columns). Flags: ZeroSpend, HasAnySpend, CryoMissing. One-hots: HomePlanet, Destination, Deck.
- `src/model.py`: kept `LogisticModel`; added `ShallowHGBModel` (max_depth=3, max_iter=200, learning_rate=0.06, l2=1.0, random_state=0).
- `train.py`: `FeatureBuilder` + `ShallowHGBModel`. CLI unchanged.

## Result
- Command: `eval/eval.py --seedset quick` with the task venv python.
- Untouched baseline quick: score 0.76335, folds=[0.74947, 0.76504, 0.76369, 0.76432, 0.77424], std=0.00794, n=6954.
- Cryo rules + planet/deck one-hots + LogisticRegression quick: score 0.76910, folds=[0.75231, 0.78152, 0.76297, 0.7694, 0.77931], std=0.01075. Gain +0.00575 vs baseline, below fold std.
- Final (cryo rules + one-hots + depth-3 HGB) quick: score 0.79655, folds=[0.78495, 0.80229, 0.80476, 0.79985, 0.79088], std=0.00745, n=6954, elapsed=42.5s. Gain +0.03320 vs untouched quick.
- validation: not computed here (harness-only). Parent official validation was 0.7717.
- Final git commit: `acb8299a6d5141f8489ff9dd2b2c339e7a4047e6`.
- Local group-fold probes using eval.py's seed 20260910 (not written to metrics.quick.json): HGB on original baseline columns 0.79255; HGB + cryo rules without planet/deck 0.79382; current pipeline 0.79655. Depth-4 HGB 0.80061 with higher fold std (0.010).

## Mechanism
CryoSleep=True has literally zero amenity spend (0/2422). Missing CryoSleep splits cleanly: 100 with any spend (transported 0.30, like awake spenders) vs 86 all-zero (transported 0.71, like cryo). Awake zero-spend is rare (416) and transported at 0.60. A linear model already sees log-spend≈0 together with CryoSleep, so hard imputation and flags only moved LR by +0.006 (noise). The same features under a depth-3 booster recover the allowed +0.03, mostly because trees split spend against planet/deck; the cryo rules themselves add only ~0.001–0.004 on top of HGB on the old columns, inside fold noise. Delivered pipeline uses HGB because the hypothesis named it as the alternative when LR saturates.

## Dead ends
- LogisticRegression on the cryo-imputed + one-hot features: quick 0.76910 vs 0.76335; C in {0.5,1,2} did not matter. Do not expect linear models to harvest this domain constraint.
- Raw vs log1p spends under HGB: both 0.79655.
- Leaving non-cryo spend NaNs for HGB missing-value handling: local 0.79828, +0.00173 vs 0.79655, inside std.
- Depth 4 / 150 iter: local 0.80061 but std 0.010 vs 0.007 at depth 3; not used.

## Next hypotheses
- Group size, cabin side, and within-group sharing (PassengerId gggg, Cabin side P/S). Groups share cabins and outcomes; side is 0.45 vs 0.55 transported. Row-wise cryo/spend features ignore this. Expected +0.01 to +0.02.
- Luxury vs essential spend plus IsChild (Age<13 never spends). Spa/VRDeck/RoomService have large negative LR coefficients; FoodCourt/ShoppingMall positive. Expected +0.005 to +0.01.
- Structured HomePlanet/Deck imputation (A/B/C↔Europa, G↔Earth, D/F often Mars) and VIP. Missing planet/deck is not MCAR. Expected +0.003 to +0.008.

## Open questions
- On hidden validation, is 0.79655 vs ~0.793 HGB-on-baseline distinguishable? Cryo rules may be optional once boosting is in.
- Cabin side was excluded to stay on-hypothesis; it is the cheapest unused binary.
- Group-target leakage: any group-level target statistic must be nested inside the same group folds the evaluator uses.
