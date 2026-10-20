# Handoff n001: Multi-tile wheat field with daily route

## Hypothesis
Replace the single-tile carrot loop with a deterministic farmer that fills ~20 tiles of the unlocked NW 5×5 with wheat: bulk-buy seeds, spiral/nearest-work routing from the shed, PLANT / WATER / HARVEST (age≥2) / DIG, and SELL shed wheat each turn. Expected large gain (~20–40k) from using the full starting quadrant and wheat’s $/day.

## What I did
- Measured baseline starter on quick: ~3491.
- Implemented modular agent: `agent.py` → `src/policy.py` (`decide`, `choose_farmer`, `build_market`), `src/farm.py` (field geometry + tile classifiers), `src/pathing.py` (`step_toward`, `nearest`).
- Field = 20 tiles nearest shed-adjacent `(4,4)`; priority urgent water > weeds > harvest > plant > bonus water; harvest at age≥2 after one bonus watering when thirsty.
- Iterated field size (8–25), harvest age (2/3/4), plant-gating, serpentine sweepers, and DROP/replant fixes; none beat the first 20-tile age-2 agent on quick.
- Kept the best agent and ran validation.

## Result
- quick: score **8714.8** (was 3491.3 baseline); win_rate 1.00; errors 0; std 628.9
  - command: `eval/eval.py --seedset quick`
- validation: score **8176.7** (parent/root baseline 3586.8); win_rate 1.00; errors 0; std 920.9; margin 4575.3
  - command: `eval/eval.py --seedset validation`
- Final git commit: `cbbf61d7f3b23a29ea854ecf3132c2d8e00149bb`

## Mechanism
Spreading wheat across many NW tiles multiplies throughput vs one carrot tile, and wheat’s low seed cost plus age-2 harvest turns capital quickly. Against `starter` this roughly **2.3×** validation money (8177 vs 3587) with perfect win rate. It did **not** reach 20–40k: one farmer has only 24 actions/day, so a 20-tile field regularly misses watering on synced “urgent” days, plants weed out, and steady-state occupancy stays ~8–12 tiles. Arithmetic ceiling for perfect single-farmer NW wheat is roughly mid-teens of thousands even at good prices; larger scores need more labor and/or richer products.

## Dead ends
- Plant-gating on `urgent_water` (quick 7342) — slowed expansion more than it saved.
- Compact 8–12 tile fields with stricter discipline (quick 6705–8163) — fewer weeds but less total harvest volume than messy 20-tile.
- Age-4 harvest on 10 tiles (quick 8090) — higher yield/harvest but fewer cycles; net below age-2/20.
- Age-3 on 20 tiles (quick 8593) — slight regression vs age-2.
- Full 25-tile NW (quick 8561) — more weeds, no gain.
- Cleaner 15-tile serpentine with replant/DROP fixes (quick 7773) — zero weeds but under-replanting after mass harvest days.

## Next hypotheses
1. **Hire 1–3 cheap hands to co-maintain the NW wheat field** — fib hire costs are $1,$1,$2,…; extra actors break the 24-action ceiling so 20–25 tiles stay watered and filled (expected jump toward 20k+).
2. **After wheat bankroll, diversify into melon/strawberry or animals** — wheat staples fund higher base-price goods once labor covers the field.
3. **BUY_LAND NE ($1k) once money is stable** — doubles plantable area once hands exist to work it.

## Open questions
- Optimal hand count vs wheat-only before switching crops?
- Is age-2 or age-4 better once hands remove the action bottleneck?
- How hard does wheat glut hit price when both seats farm wheat at scale?
