# n002 progress

Hypothesis: CryoSleep-consistent spend imputation + rules (keep simple model; fix domain leak that CryoSleep passengers have zero amenity spend; impute CryoSleep from spend; ZeroSpend/HasAnySpend flags; HomePlanet/Destination/Cabin-deck one-hots).

## 2026-09-10 start
- Worktree on `node/n002`, parent root official score 0.7717.
- Baseline: logistic regression on log1p spend + TotalSpend + Age + CryoSleep (fillna median). No planet/cabin/deck; missing CryoSleep treated as median (not domain-imputed); CryoSleep=True spends filled as 0 independently of the flag.
- Data (train.csv, n=6954): CryoSleep=True always has zero amenity spend (0/2422 with any spend). Cryo=False all-zero spend is rare (416) and transported at 0.596 vs 0.296 for spenders. Cryo=NA: 100 with spend (transported 0.30, like awake) and 86 all-zero (transported 0.71, like cryo). HasAnySpend is strongly aligned with the label (False 0.776 vs True 0.296).
- Untouched quick CV: score 0.76335, folds=[0.74947, 0.76504, 0.76369, 0.76432, 0.77424], score_std=0.00794, n=6954. Parent official validation=0.7717.
- Implemented: `apply_cryo_spend_rules` + `FeatureBuilder` in `src/features.py`; `train.py` uses LogisticRegression. Commit `c5b27c1`.
- Cryo+one-hot LR quick (eval.py): score 0.76910, folds=[0.75231, 0.78152, 0.76297, 0.7694, 0.77931], std=0.01075. Gain +0.00575 vs untouched 0.76335 — below fold std, not enough.
- Local same-fold probe (seed 20260910, not eval.py): LR C insensitive (~0.769). Shallow HGB d3/i120=0.79397, d3/i200 lr0.06=0.79655, d4/i150=0.80061. LR coefs: TotalSpend/VRDeck/Spa/RoomService negative, CryoSleep and FoodCourt/Europa positive; ZeroSpend/HasAnySpend cancel (±0.187). Linear model cannot split cryo x spend x deck.
- Switching train.py to ShallowHGBModel(max_depth=3, max_iter=200, learning_rate=0.06, random_state=0). Depth 3 chosen over 4 for lower fold std (0.007 vs 0.010).
- Official quick CV (eval.py) HGB+cryo+cats: score 0.79655, folds=[0.78495, 0.80229, 0.80476, 0.79985, 0.79088], std=0.00745, n=6954, elapsed=42.5s. vs untouched 0.76335, +0.03320.
- Local same-fold probes (seed 20260910, not eval.py): HGB on original baseline columns 0.79255; HGB + cryo rules without planet/deck 0.79382; current 0.79655. Cryo rules add ~0.001–0.004 on HGB (inside fold std). Most of the jump is the booster, which the hypothesis allowed.
- log1p fill-0 vs raw fill-0 identical 0.79655; raw keeping non-cryo spend NaNs 0.79828 (noise). Stop iterating.
- Final commit `acb8299a6d5141f8489ff9dd2b2c339e7a4047e6`. Writing HANDOFF.md and proposals.json.
