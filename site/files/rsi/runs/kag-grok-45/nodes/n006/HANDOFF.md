# Handoff n006: Fertilize melons for age-8 max yield (refuted)
## Hypothesis
Buy fertilizer via BUY_PRODUCT and FERTILIZE melon plants so the doubled watering bonus hits yield cap 6 by age 8 instead of 10, then harvest early and replant for an extra melon wave before day 30 while keeping the ~16-tile / price≥180 caps.

## What I did
- Unit-tested env yield/harvest: fertilize at age 5 + daily water reaches yield 6 at age 8, but `HARVEST` is a no-op until `first_yield_day=10`.
- Implemented BUY_PRODUCT FERTILIZER, shed PICKUP, FERTILIZE on melons at age 5–6 in `src/farm_ops.py` / `src/market.py` / `agent.py` (commits `a833ccd`, `ce18bf9`).
- Measured fert-with-harvest-clamped-to-10, then literal age-8 harvest attempts on quick.
- Reverted agent to parent n004 melon loop (no fertilizer) as final code (`d53f99b`) after both fert variants lost money.

## Result
- Untouched parent quick: score 37637.3 (`eval/eval.py --seedset quick`).
- Fert + harvest at 10 (no cycle gain): quick score 33820.5 (−~3.8k).
- Fert + literal age-8 harvest: quick score 6975.0 (HARVEST no-ops waste bandwidth).
- Final (reverted parent): quick 37637.3; validation 36891.8 (`eval/eval.py --seedset validation`) — matches n004, no improvement.
- Final git commit: `d53f99ba66ac3b13ff0b29fba5aa100a34b73d7e`.

## Mechanism
Melon’s bonus window lets fertilizer reach max yield two days early, but the environment still refuses harvest before age 10. Fertilizer therefore cannot create a third melon cohort; it only spends ~$100/plant plus pickup/fertilize actions that displace watering and replanting. Attempting harvest at 8 turns those actions into silent no-ops for two days and collapses the farm.

## Dead ends
- BUY_PRODUCT + FERTILIZE melons while still harvesting at 10: quick 33820.5 < 37637 — pure cost.
- Same fert path with harvest age 8 (hypothesis literal): quick 6975 — env no-ops starve the loop.
- Goose-sourced fertilizer was not tried; it cannot bypass `first_yield_day` either.

## Next hypotheses
1. Demand-timed / drip selling: sell melon in small lots across turns (hold near I0) while carrots fund ops; raise realized melon $/unit vs dumping a full shed order after synchronized harvest.
2. Stagger melon plant cohorts (e.g. two waves of ~8 tiles offset by ~5–8 days) so sales and watering peaks do not coincide; may keep price higher and smooth hand bandwidth without changing the 16-tile total cap.
3. Opportunistic wheat fertilizer only if somehow relevant later — skip for melons; instead explore tomato/strawberry ongoing crops only if a separate node wants a different crop mix (not a melon-fert retry).

## Open questions
- How much of the post-harvest melon price crash is from selling the full shed in one order vs total season volume past I0?
- Does staggering plant days under the same 16-tile cap beat drip-selling a synchronized wave?
- Is there any crop where fertilizer’s early cap actually unlocks an extra cycle given that crop’s `first_yield_day` (melon is not one)?
