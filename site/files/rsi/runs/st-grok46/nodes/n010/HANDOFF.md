# Handoff n010: Group size, cabin side, within-group sharing

## Hypothesis
Keep n002 cryo-imputed spends and depth-3 HGB. Add X-only features computed independently on each file: group id = PassengerId prefix gggg; GroupSize; IsAlone; cabin side P/S/Missing; whether a last name is shared inside the group; whether HomePlanet/Destination/Deck/CryoSleep are uniform among non-missing groupmates (nunique==1 and at least two observations). Never target-encode Transported. Expected +0.01 to +0.02 quick accuracy; if mean gain stayed under 0.007 or fold std blew up from noisy modes / last-name double-counting, fall back to side-only.

## What I did
- `src/features.py`: `parse_side`, `parse_group_id`, `parse_last_name`, `add_group_features` (per-file, no Transported). Missing last names get unique keys so they do not share. Sharing flags require two agreeing non-missing groupmates.
- `FeatureBuilder` runs `add_group_features` after `apply_cryo_spend_rules` on train and predict independently. Side joined the existing planet/destination/deck one-hots. Numeric extras: GroupSize, IsAlone, SharesLastName, SharedHomePlanet, SharedDestination, SharedDeck, SharedCryoSleep.
- Integer FamilyInGroup and global LastNameSize were not added (n006/n007 dead ends; this node's risk note).
- `train.py`: still `ShallowHGBModel`; docstring only.
- No group-mode fill of HomePlanet/Destination/Deck (n004).

## Result
- Untouched parent quick (`eval/eval.py --seedset quick`): score 0.79655, folds=[0.78495, 0.80229, 0.80476, 0.79985, 0.79088], score_std=0.00745, n=6954, elapsed=18.2s.
- Full group+side+sharing quick (same command): score 0.80449, folds=[0.78637, 0.80802, 0.80836, 0.81001, 0.8097], score_std=0.00909, score_sem=0.00407, n=6954, elapsed=22.6s. Gain +0.00794 vs parent quick. All five folds up.
- validation: not computed here (harness-only). Parent official validation was 0.8125.
- Local same-fold ablations (eval.py seed 20260910, not official `eval.py` writes): side_only 0.80304 std 0.00822 Δ+0.00650; GroupSize+Side 0.80262 std 0.00822 Δ+0.00607; full 0.80449 std 0.00909. Side-only missed the 0.007 bar; dropping SharesLastName raised std to 0.01011 and cut the mean to 0.80334. Shipped the full set.
- Final git commit: `16b80ec35e96195a1b9c2db372696cbb4fe67dc4`.

## Mechanism
Cabin side is a row-wise location the parent never encoded: on train.csv transported is 0.449 (P) vs 0.548 (S) vs 0.482 (missing). Groups are never mixed on side or HomePlanet, so SharedHomePlanet is almost “not alone.” GroupSize is non-monotonic (alone 0.452, size 3–4 around 0.59, size 8 0.394). Deck-sharing is the strongest share flag (shared-deck rows 0.604 vs mixed-deck 0.460). Destination and CryoSleep are often mixed; those flags mark uniform vs mixed booking groups. SharesLastName is a within-group family bit, not a global surname count (FamilyInGroup still equals GroupSize on 86% of rows, so the integer was skipped). Depth-3 HGB uses side against the existing cryo/spend/deck splits. Ablation: side carries most of the +0.008; sharing + last-name add the rest; GroupSize on top of side did not help this shallow HGB.

## Dead ends
- Side-only (local same folds): 0.80304 vs parent 0.79655, Δ+0.00650, below the 0.007 bar; std 0.00822 still above parent 0.00745.
- GroupSize+IsAlone+Side without sharing/last-name: 0.80262, slightly worse than side-only. IsAlone is redundant with GroupSize (identical scores).
- Dropping SharesLastName from the full set: 0.80334 std 0.01011 — last-name binary is not the integer FamilyInGroup dead end, but it is not a variance reducer.
- Sharing flags without GroupSize: 0.80118 Δ+0.00463.
- Fold std did not drop (0.00745 → 0.00909). Fold 0 barely moved. Did not revert to side-only because the full mean met 0.007, every fold improved, and subsets were worse. Hidden validation may still treat the extra share flags as noise (n004–n007 pattern).

## Next hypotheses
- Luxury vs essential spend plus IsChild (Age<13 never spends) on top of these group/side features: Spa/VRDeck/RoomService vs FoodCourt/ShoppingMall, plus spend shares. n008 saw luxury-share corr −0.446 vs −0.275 for raw luxury spend on another lineage.
- Swap depth-3 HGB for LightGBM or CatBoost on the same cryo + group/side features. n001 landed in the 0.80–0.81 band with GBDT + GroupSize/Deck/Side; this lineage still uses a shallow sklearn HGB that did not use GroupSize once Side was present.
- VIP plus structured HomePlanet/Deck map (A/B/C/T→Europa, G→Earth; do not majority-guess F) without unique-only Destination fill. VIP is still unused here; n004’s dest fill was not the driver.

## Open questions
- Does quick +0.00794 hold on hidden validation, or do the share flags fail like n004 location fill / n005–n007 surname counts?
- SharedHomePlanet is nearly not-alone; worth dropping on a later ablate if validation is flat.
- Can a deeper booster use the non-monotonic GroupSize (size 8 is worse than alone) that depth-3 HGB ignored once Side was in?
