# pi-rsi report: kag-grok-45

- task: kaggriculture; metric `score` (higher is better)
- worker: grok:grok-4.5 (high); utility: grok:grok-4.5
- search: width_root=3 width=2 depth=4 max_nodes=10 parallel=2 patience=4
- stop reason: patience; elapsed 1h00m
- baseline (root) official score: 3,587
- best node: `n008` official score 37,329
- held-out `test` seed set: best 35,748 vs baseline 3,589
- reference scores: user_v45_tape 138,283
- cost: utility: 9 calls, $0.12, 2m53s; worker: 8 calls, $3.40, 1h44m

## Best path

- `root` 3,587 — baseline: Baseline starter code. Official score: 3,587.
- `n002` 9,085 — Cheap daily hired hands for parallel farm ops: Daily hired hands (TARGET=6) plus partitioned NW carrot farming raised official validation score from 3587 to 9084.59 (margin 5887.97, win_rate 1.0, 32 games, 0 errors). Worker quick best was 11690.2. Water-before-harvest and no mid-day shed hauls were the key tunings; more/fewer hands and seed stockpiling underperformed on quick.
- `n004` 36,892 — Parallel melon (or melon+carrot) loop: Switched the parallel hired-hand farm to melon primary with harvest at age 10, capped at 16 live melon tiles and a price≥180 plant/buy gate that falls back to carrot. Official validation score 36891.84 (margin 33510.31, win_rate 1.0, n=32, errors 0) vs parent 9085 (~+27.8k). Worker quick peaked at 37637.3 under the same knobs.
- `n005` 36,584 — Buy NE land under melon tile cap: Added day≥10 BUY_LAND for NE ($1000) with MELON_MAX_TILES=16 and TARGET_HANDS=6; new tiles meant for carrots. Official validation score 36583.72 (margin 33230.41, win_rate 1.0, n=32, errors 0) vs parent 36892 — about −308. Worker quick-set peaked ~38867 with a money gate, but that variant also lost on validation. Labor left ~20–30 tiles empty.
- `n008` 37,329 — Quadrant-local hand partition: Quadrant-local row-band ownership after NE unlock (NW_UNIT_COUNT=3, TARGET_HANDS=6, melon cap 16) raised official validation score to 37329.44 from parent 36584 (+745), win_rate 1.0, 0 errors, n=32. Contiguous bands beat within-quad modulo; NW=2 was stronger on worker quick (39528.8) but weaker on validation (37039.4).

## All nodes

| id | parent | depth | status | verdict | score | Δparent | title | duration |
|---|---|---|---|---|---|---|---|---|
| root | - | 0 | done | baseline | 3,587 | - | baseline | - |
| n001 | root | 1 | done | improved | 8,177 | 4,590 | Multi-tile wheat field with daily route | 19m01s |
| n002 | root | 1 | done | improved | 9,085 | 5,498 | Cheap daily hired hands for parallel farm ops | 13m17s |
| n003 | n002 | 2 | done | worse | 8,229 | -855.2 | Buy NE land, extend hand farm | 28m25s |
| n004 | n002 | 2 | done | improved | 36,892 | 27,807 | Parallel melon (or melon+carrot) loop | 12m04s |
| n005 | n004 | 3 | done | worse | 36,584 | -308.1 | Buy NE land under melon tile cap | 11m50s |
| n006 | n004 | 3 | done | no_change | 36,892 | 0 | Fertilize melons for age-8 max yield | 7m36s |
| n007 | n005 | 4 | done | worse | 36,405 | -178.5 | More hands after NE unlock | 6m08s |
| n008 | n005 | 4 | done | improved | 37,329 | 745.7 | Quadrant-local hand partition | 10m13s |

## Insights

# Insights (verified across nodes; each line cites the node)

- Cheap daily HIRE multiplies tile-actions so the same carrot loop can fill all NW tiles instead of one, lifting mean money ~2.5× because hire cost (~20/day for 6) is tiny vs crop revenue. [n002, score 9,085]
- On carrot max-yield day, WATER before HARVEST captures the final bonus unit (yield 3 vs 2); harvest-first left money on the table. [n002, score 9,085]
- Mid-day DROP hauls to the shed steal harvest/replant turns; EOD drop plus morning sell preserves field bandwidth. [n002, score 9,085]
- Spreading cheap fast wheat over many NW tiles multiplies throughput vs one carrot tile because seed cost is low and age-2 harvest recycles capital quickly. [n001, score 8,177]
- A single farmer’s ~24 actions/day caps utilization: synced watering days leave weeds and ~8–12 live plants, so NW wheat alone tops out well below 20–40k. [n001, score 8,177]
- On quick, a messy 20-tile age-2 nearest-work policy beat cleaner smaller fields and slower harvest ages because harvest volume outweighed weed losses. [n001, score 8,177]
- Capping high-value low-demand crops (melon) below full-field waves preserves sale price because shop demand is tiny and above_target oversupply floors at $1. [n004, score 36,892]
- Price-gated carrot fallback on remaining tiles earns during the long melon cycle and after glut without seeding melon into a crashed market. [n004, score 36,892]
- Opportunistic shed-adjacent DROP beats mid-day inventory hauls because haul turns displace watering/harvest/replant. [n004, score 36,892]
- Doubling same-crop carrot acreage does not double revenue: market T≈450 is sized for one 5×5 field, so a second field floods inventory and crashes price (~$21 → ~$5 by day 29 on seed-0). [n003, score 8,229]
- With NE unlocked, more hands still hurt (quick: 6→8657, 8→6668, 10→4055), matching the prior hire-economics finding. [n003, score 8,229]
- Delaying BUY_LAND (thresh 7k–12k) only approaches the no-land baseline and never beats it—acreage expansion itself is the loss, not just early timing. [n003, score 8,229]
- Land expansion under a fixed hand count fails when long-cycle melons already consume watering bandwidth: empties persist and pathing across non-contiguous plots dilutes carrot gains below the $1000 unlock cost. [n005, score 36,584]
- Keeping a hard melon tile cap when unlocking land prevents a price-floor glut; the remaining limit is labor coverage, not melon overplanting. [n005, score 36,584]
- Melon cycle revenue still dominates: delaying melon replant to force carrot fill crashes mean money far more than extra carrots recover. [n005, score 36,584]
- Under board-index % n_units ownership, extra hands after NE do not fill empties for net money: more units further scatter tiles across non-contiguous NW+NE, so pathing and unfinished seed cycles dominate the cheap hire cost. [n007, score 36,405]
- Hire count alone is not the post-NE bandwidth gate; labor assignment/partition likely is—melon watering (16 long-cycle tiles) dilutes rather than carrot fill improving when units increase. [n007, score 36,405]
- Melon HARVEST is gated by first_yield_day=10 even when fertilizer + watering reach yield 6 at age 8, so fertilizer cannot shorten the melon cycle. [n006, score 36,892]
- Without a cycle speedup, fertilizer purchase plus pickup/fertilize actions cost money and displace watering/replanting, lowering score. [n006, score 36,892]
- After NE unlock, contiguous within-quadrant row bands outperform flat or local modulo ownership because they keep pathing inside one 5×5 and cut shed-gap travel. [n008, score 37,329]
- Quick-best staffing (more NE hands) can under-serve NW melon watering on validation; a modest NW crew (3 of 7) transferred better than NW=2. [n008, score 37,329]
- Prefer home-quadrant emergencies only when a unit is idle; prioritizing cross-quad WATER over local PLANT collapses NE fill. [n008, score 37,329]

## Dead ends

# Dead ends (do not retry; each line cites the node)

- TARGET_HANDS=8: worker quick 8297 — more hands scatter ownership and tie capital in unfinished seed cycles. [n002]
- TARGET_HANDS=5: worker quick 8328 — under-bandwidth vs 6. [n002]
- Aggressive seed stockpiling: worker quick 9118 — locks money without raising throughput; mid-day DROP haul thresh=6: quick 10751 vs opportunistic-only 11690. [n002]
- Plant-gating on urgent_water hurt expansion (worker quick 7342). [n001]
- Compact 8–12 tile or serpentine 15-tile fields scored lower on quick (6705–8163 / 7773) despite fewer weeds. [n001]
- Age-4 on 10 tiles and age-3/full 25-tile variants underperformed age-2/20 on quick (8090 / 8593 / 8561). [n001]
- Pure melon (price gate 0) underperforms: worker quick 26606 vs capped mix 37637 — second wave sells near $1. [n004]
- Mid-day DROP haul at inv≥6 hurts: worker quick 34588 vs no-haul 35045. [n004]
- Melon caps 10/18/20 and thresh 200 are worse on quick than tiles=16 × thresh=180 (34038/33103/32272/32056 vs 37637). [n004]
- BUY_LAND NE + same carrot loop on 50 tiles: validation 8229.41 < parent 9085; worker quick 8656.7 < no-land quick 11690.2. [n003]
- Contiguous/quadrant partitions and plant-caps 25–50: best quick ~9221 still below no-land 11690. [n003]
- Dynamic hands 6→8/10/12 after NE: quick 7115 / 4739 / 3665 — worse. [n003]
- BUY_LAND earlier than day 10 (worker quick ~34701–37718) underperformed day-10 timing. [n005]
- MELON_MAX_TILES 12/14/18/20 with NE (worker quick ~32461–36022) all worse than cap 16. [n005]
- Forcing carrot fill before melon replant (worker quick ~32028–32411) and BUY_LAND_MIN_MONEY gates that look best on quick transfer poorly to validation. [n005]
- POST_LAND_HANDS 8–10 after NE (unlock or day): worker quick 38004 / 36569 / 35548 vs baseline 38708. [n007]
- POST_LAND_HANDS=7 unlock-gated: worker quick +187 but official validation 36405 < parent 36584 (−179). [n007]
- Seed-before-extra-hire reorder: mornings with 2 SELLs leave no market slots for extra HIREs. [n007]
- BUY_PRODUCT + FERTILIZE melons while still harvesting at 10: worker quick 33820.5 vs parent quick 37637.3 — cost with no gain. [n006]
- Same fert path with harvest at age 8: worker quick 6975.0 — HARVEST no-ops at ages 8–9 starve the farm loop. [n006]
- Within-quad local-index modulo (NW=3): worker quick 37004.4 (−1703 vs parent quick). [n008]
- Emergency WATER before PLANT across quadrants: worker quick 33989.0. [n008]
- NW_UNIT_COUNT 4/5/6 row-bands: worker quick 38285/38338/37303, all below parent quick. [n008]
