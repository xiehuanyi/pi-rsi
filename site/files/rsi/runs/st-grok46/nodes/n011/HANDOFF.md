# Handoff n011: Luxury vs essential spend sums + IsChild

## Hypothesis
Replace the five log1p amenity columns with LuxurySpend=log1p(RoomService+Spa+VRDeck) and EssentialSpend=log1p(FoodCourt+ShoppingMall), plus IsChild=(Age<13) and maybe AgeBin. Luxury amenities have large negative linear weights and essential amenities positive ones; Age<13 never spends (n=641, transported 0.68). A depth-3 tree should split that composition more cleanly if the sums are explicit. Keep CryoSleep rules unchanged. Ablate sums-only vs sums+raw; gains below fold std (~0.007) are noise.

## What I did
- Confirmed on `data/train.csv`: Age<13 n=641, any spend>0 = 0, min spending age = 13; log1p(Luxury) corr with Transported = −0.5519 vs individual luxury logs ≈ −0.34 to −0.36.
- `src/features.py`: `apply_cryo_spend_rules` unchanged. `FeatureBuilder` now writes log1p LuxurySpend / EssentialSpend / TotalSpend and IsChild (observed Age<13; missing Age is not a child). Dropped the five raw amenity logs. No AgeBin in the shipped set.
- `train.py`: same `FeatureBuilder` + `ShallowHGBModel`; docstring only.
- Ablations used the same group folds as eval.py (seed 20260910).

## Result
- Command: `eval/eval.py --seedset quick` with the task venv python.
- Parent n002 worker quick (reproduced locally as `parent_raw` on the same folds): score 0.79655, folds=[0.78495, 0.80229, 0.80476, 0.79985, 0.79088], std=0.00745.
- Final shipped pipeline quick: score 0.80045, folds=[0.78637, 0.80158, 0.80331, 0.80566, 0.80535], std=0.00719, sem=0.00322, n=6954, elapsed=7.3s. Gain +0.00390 vs parent quick, below fold std.
- validation: not computed here (harness-only). Parent official validation was 0.8125.
- Final git commit: `2d1615eb55ebfa8fd9262d37554c438bb761b5b2`.
- Local same-fold probes (not metrics.quick.json): sums-only 0.80045; sums+raw 0.79918 (std 0.00977); adding IsChild or AgeBin left every fold identical to the matching sums config; dropping TotalSpend 0.79859. LR: parent_raw 0.76910 → sums_only 0.78635 (+0.01725); still well below HGB.

## Mechanism
Luxury vs essential is a real composition axis: among spenders the two shares are perfect negatives and luxury share corr with Transported is −0.504. Replacing five collinear log spends with two sums lets a depth-3 HGB put almost all spend splits on LuxurySpend (full-train permutation importance +0.207) and EssentialSpend (+0.042). That cleans the tree but barely moves accuracy — the five raw logs already encoded the same split, so the extra 0.004 sits inside fold noise (fold 4 +0.014, folds 1–2 slightly down). IsChild is a true domain fact (children never spend and transport at 0.68) but ZeroSpend+Age already give the booster that cut; permutation importance on IsChild is +0.00014 and fold scores match sums-only exactly. Linear models *do* harvest the sums (+0.017 LR) because they cannot split the five logs into luxury vs food; we still ship HGB because 0.800 > 0.786.

## Dead ends
- sums+raw (keep five logs and the two sums): local 0.79918, std 0.00977, fold 0 0.77999. Collinear; do not add the raw amenity logs back.
- IsChild on top of Age under depth-3 HGB: identical folds to the same spend set without it. AgeBin (0–4 on 13/18/25/40 cuts) likewise identical. Do not expect a shallow tree to use these once Age and ZeroSpend exist.
- Dropping TotalSpend once Luxury+Essential are present: local 0.79859, slightly worse. Keep TotalSpend.
- Switching the shipped model to LR to harvest the +0.017 composition lift: LR sums_only 0.78635 still far below HGB 0.80045.

## Next hypotheses
- GroupSize and cabin side P/S on this pipeline (no surname counts, no within-group target stats). Side is 0.45 vs 0.55 transported; this lineage still has only row-wise spend/planet/deck. Expected +0.01 to +0.02.
- More tree capacity (LightGBM or deeper HGB) on the current luxury/essential columns. Depth-3 HGB already treats LuxurySpend as the dominant split but accuracy barely moved; n001 reached worker quick 0.80331 with LightGBM+group/cabin. Expected +0.003 to +0.008 if depth 3 is the bottleneck; watch fold std (depth-4 HGB on n002 was 0.010).
- Structured HomePlanet/Deck fill (A/B/C↔Europa, G↔Earth) after cryo rules. n004 did not beat its parent on a LightGBM lineage; on this Missing-dummy HGB it is still a small, noisy lever (+0.003 to +0.008 at best).

## Open questions
- Will hidden validation move given a +0.004 quick gain inside fold std? LuxurySpend importance is real; accuracy may still be flat.
- Sibling n010 is testing GroupSize/side/sharing on parent n002 without these sums. If both land, compose sums with side+GroupSize only — not the failed global surname / FamilyInGroup / CabinOccupancy extras.
- Spend *shares* (Luxury/Total) vs these *sums*: n008 shares helped LightGBM; n009 shares+five logs did not. Do not stack shares on top of LuxurySpend+EssentialSpend+TotalSpend without an ablation; they are nearly determined by the two sums.
