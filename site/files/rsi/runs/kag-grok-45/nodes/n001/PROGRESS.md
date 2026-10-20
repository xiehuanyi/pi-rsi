# Progress n001: Multi-tile wheat field

## Plan
1. Read docs + baseline agent; measure quick score of untouched code
2. Implement NW 5x5 wheat plant/water/harvest loop with bulk seed buys
3. Iterate on quick seedset; then validation
4. Handoff + proposals

## Log
- Baseline quick (untouched starter carrot): score=3491.3, errors=0, std=77.4, elapsed=4.7s
- First wheat field agent (20 tiles, harvest>=2, spiral from shed): quick score=8714.8 win_rate=1.00 errors=0 std=628.9 (was 3491). Below 20-40k target — diagnosing utilization.
- Diagnosis: ~8-9 plants survive; 6-8 weeds; synced every-other-day watering days overflow 24 turns; DROP-after-harvest on (4,4) blocks replant; local PLANT can race urgents.
- Tried smaller fields (8/10/12/15/16), age-3/age-4 harvest, plant-gating, route sweepers, replant/DROP fixes: all scored **worse** than first agent on quick (6705–8593).
- Best config remains first agent: 20 shed-nearest tiles, harvest at age>=2 with one bonus water, nearest-work priority (urgent water > weeds > harvest > plant > bonus water).
- Restored best agent. quick=8714.8; validation=8176.7; win_rate=1.00; errors=0. Final commit cbbf61d.
- Ceiling note: single-farmer wheat on NW alone tops out ~10–18k even if perfect (25 tiles × yield2–4); 20–40k needs hands and/or higher-value crops / land.
