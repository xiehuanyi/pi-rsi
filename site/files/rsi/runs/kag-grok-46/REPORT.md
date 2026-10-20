# pi-rsi report: kag-grok-46

- task: kaggriculture; metric `score` (higher is better)
- worker: grok:grok-4.6 (high); utility: grok:grok-4.5
- search: width_root=3 width=2 depth=4 max_nodes=10 parallel=2 patience=4
- stop reason: max_nodes; elapsed 1h49m
- baseline (root) official score: 3,587
- best node: `n008` official score 24,614
- held-out `test` seed set: best 24,926 vs baseline 3,589
- reference scores: user_v45_tape 138,283
- cost: utility: 11 calls, $0.15, 3m45s; worker: 10 calls, $4.80, 3h19m

## Best path

- `root` 3,587 — baseline: Baseline starter code. Official score: 3,587.
- `n002` 16,217 — Early daily HIRE to multiply plant/water throughput: Replaced solo carrot loop with morning HIRE of 5 hands (Fibonacci ~$12/day) plus WHEAT on the NW 5×5, stay-on-tile plant/water/harvest/sell. Official validation score 16216.75 (parent ~3587; margin 12609.25; win_rate 1.0; n=32; errors 0). Worker quick-set: 15888.33 vs untouched 3491.3.
- `n003` 22,269 — Buy NE land and scale wheat: Bought NE land after first harvest and raised MAX_HANDS to 8, planting all unlocked wheat tiles with stay-on-tile labor. Official validation score 22268.97 (parent 16217), margin 18708.31, win_rate 1.0, 32/32 wins, errors 0. Worker quick-set rose from 15888.3 to 22343.1 (NE-only); NE+SW was worse on quick.
- `n005` 23,598 — Fertilize wheat bonus window: Shipped 2 spawn-tile geese for on-farm fertilizer: FERTILIZE ages 2–4 before WATER, feed reserve, DROP at 12. Official validation score 23597.91 vs parent 22269 (+1329), win_rate 1.0, 0 errors, n=32. Worker quick-set: 23286.6 vs untouched 22343.1.
- `n008` 24,614 — Compact spawn-aware NW+NE regions: Assigned locked SW/SE spawns compact exclusive far-edge columns (x=0,1,8,9), preferred NORTH off locked tiles, and skipped coop CARE/FEED for those walkers; shed-spawn actors stayed greedy. Official validation score 24613.59 vs parent 23598 (+~1016); win_rate 1.0, errors 0, n_games 32. Worker quick-set: 24974.6 vs 23286.6.

## All nodes

| id | parent | depth | status | verdict | score | Δparent | title | duration |
|---|---|---|---|---|---|---|---|---|
| root | - | 0 | done | baseline | 3,587 | - | baseline | - |
| n001 | root | 1 | done | improved | 9,525 | 5,938 | Multi-tile wheat farm with daily water/harvest route | 21m48s |
| n002 | root | 1 | done | improved | 16,217 | 12,630 | Early daily HIRE to multiply plant/water throughput | 20m31s |
| n003 | n002 | 2 | done | improved | 22,269 | 6,052 | Buy NE land and scale wheat | 17m41s |
| n004 | n002 | 2 | done | improved | 20,736 | 4,519 | Fertilize wheat bonus window | 20m42s |
| n005 | n003 | 3 | done | improved | 23,598 | 1,329 | Fertilize wheat bonus window | 27m27s |
| n006 | n003 | 3 | done | worse | 21,683 | -585.9 | Compact spawn-aware 5x10 regions | 26m38s |
| n007 | n005 | 4 | done | improved | 24,088 | 490.1 | Defer goose CARE on harvest days | 21m22s |
| n008 | n005 | 4 | done | improved | 24,614 | 1,016 | Compact spawn-aware NW+NE regions | 19m29s |
| n009 | n006 | 4 | done | improved | 22,086 | 402.8 | Skip late DROP while tiles need water | 8m50s |
| n010 | n006 | 4 | done | improved | 24,575 | 2,892 | Fertilize wheat bonus window | 20m32s |

## Insights

# Insights (verified across nodes; each line cites the node)

- Daily Fibonacci HIRE (~$12 for 5 hands) multiplies actions/day (~138 vs 24), unlocking multi-tile wheat the solo farmer cannot tend. [n002, score 16,217]
- Exclusive stay-on-tile finish (water→harvest→replant→water) keeps the 5-day wheat cycle; global water-first slips replant a day. [n002, score 16,217]
- Never plant at hour 23: new plants need same-day water or they weed. [n002, score 16,217]
- One farmer can sustainably daily-water and harvest+replant only ~8 compact tiles: watering N path-connected tiles costs 2N−1 actions, and harvest days push past 24 turns beyond that. [n001, score 9,525]
- Capping new wheat plants at 2/day keeps harvest cohorts from clumping so water-first days stay within the 24-turn budget. [n001, score 9,525]
- New plants start consecutive_unwatered=1, so age-1 must be watered the same day or they weed at EOD—skipping age-1 water is not a reliable way to free turns. [n001, score 9,525]
- Unlocking NE after the first wheat SELL (~$4000) doubles plantable tiles and hands already spawn on the newly plantable NE shed tile, so expansion needs no spawn redesign. [n003, score 22,269]
- Staggering NE planting one day after NW spreads the 5-day wheat cycle so harvest peaks are ~25 ripe tiles, letting 8 actors finish water/harvest without mid-day DROP. [n003, score 22,269]
- On 50 tiles, the 8th hand (fib $21/day) beats 6–7 hands because missed water and weeds cost more than the hire fee. [n003, score 22,269]
- Goose-sourced fertilizer can raise wheat from yield-cap 4 to 6 because one FERTILIZE at age 2–3 sets a multi-day window covering bonus watering days, and eggs offset coop/feed opportunity cost. [n004, score 20,736]
- Logistics matter: fertilizer left in the shed never fires; forced morning PICKUP was required so field actors actually apply it. [n004, score 20,736]
- At glut wheat ~$22, bought $100 fertilizer has negative ROI versus +2 units (~$44), so recycling via geese is the viable path. [n004, score 20,736]
- Spawn-adjacent coops keep FEED/COLLECT local, so fertilizer is applied before EOD shed dump and FERTILIZE-before-WATER can lift wheat 4→6. [n005, score 23,598]
- DROP at 12 only after stay-on-tile lets mid-harvest SELL clear the 100-cap shed once 6-yield tiles are online. [n005, score 23,598]
- Daily market wheat buys whenever shed wheat < n_geese retrigger after reserve pickup and burn cash; emergency buy only when total wheat is 0 avoids that loop. [n005, score 23,598]
- Exclusive NW/NE partitions understaff the harvest half: 4 actors cannot finish 25×4 harvest chains in 23 turns, so ripe tiles and weeds remain. [n006, score 21,683]
- Parent greedy stay-on-tile already clears all ripe tiles; leftover is 4–5 unwatered, so region matching is not the bottleneck. [n006, score 21,683]
- Pinning locked SW/SE spawns to spawn columns still steals jobs from closer actors and regresses versus unconstrained greedy. [n006, score 21,683]
- CARE/egg-HARVEST defer on harvest days raises mean score only when DROP visitors cannot PICKUP wheat to FEED; otherwise extra FEED no-ops consume the freed actor slots and leftovers stay ~6–7. [n007, score 24,088]
- A ripe/replant cohort latch is required: gating on wheat_chain_busy alone is true every morning, so CARE never runs on unfinished harvest days and egg income collapses. [n007, score 24,088]
- Assigned-only coop feed pickup (target==pos) restores FEED=2 on harvest days without the exclusive-occupant CARE lock that blocked anyone from caring. [n007, score 24,088]
- Exclusive homes only on far leftover columns, with shed-spawn actors fully greedy, lifts score because far edges are the hour-23 unwatered cluster while harvest still needs overflow labor. [n008, score 24,614]
- Preferring a step onto unlocked land from locked SW/SE and skipping coop CARE for far walkers reduces morning walks into locked tiles and coop stalls before they reach the edges. [n008, score 24,614]
- Full exclusive 5×10 partitions still understaff harvest and leave unassigned columns unwatered/ripe (same failure mode as n006). [n008, score 24,614]
- Skipping hour≥21 DROP while crop jobs or unwatered tiles remain recovers ~$400 by turning shed-bound MOVE into WATER; eod auto-drop still banks inventory when shed capacity is free. [n009, score 22,086]
- After this gate, leftover unwatered (2–3) and leftover ripe are a matching bottleneck, not late DROP—locked-column assignment still leaves far tiles beyond a 3-hour walk. [n009, score 22,086]
- Deferring hour≥21 DROP while WATER jobs remain returns actions to watering (seed 101 WATER 1423 vs n005 1386; DIG 10 vs 14), cutting late weeds without interrupting stay-on-tile harvest. [n010, score 24,575]
- Forced morning PICKUP is required for shed fertilizer to leave and get applied; COLLECT alone left it unused in earlier passes. [n010, score 24,575]
- Coops on spawn/shed tiles break spawn-strip matching; greedy stay-on-tile+nearest plus CARE and overflow DROP@12 is needed so harvest finishes while two actors tend geese. [n010, score 24,575]

## Dead ends

# Dead ends (do not retry; each line cites the node)

- Stride tile partitions zigzag the 5×5 and leave harvest-day weeds (seed 101 ≈14751). [n002]
- Water-whole-field-before-harvest desyncs the 5-day cycle (seed 101 15643→14659). [n002]
- Greedy plant-job caps that drop corner tiles leave the farmer on fallow (seed 101 ≈14488). [n002]
- 9-tile 3×3 with a 3-plant ramp: 3-harvest days need ~26 actions; missed waters, weeds, and day-29 harvests never DROPped (seed 101 $7028 vs 8-tile ~$8828). [n001]
- Skipping age-1 watering for a 9th tile: seed 101 $9936 but seed 102 $7735 from weeds/missed bonus—reverted as non-robust. [n001]
- Full 25-tile NW serpentine with one farmer cannot daily-water; weeds wipe the field. [n001]
- NE+SW with MAX_HANDS=7 and DROP at 12: worker quick 19436.0; mid-harvest DROP left 6–11 plants unwatered and SW’s $2000 bought only ~8 tended tiles plus weeds. [n003]
- SW at $6500 with 8–12 hands on seed 101 scored 21539–21841 vs NE-only 22454 — more labor does not repay the $2000 score hit on 75 tiles. [n003]
- BUY_SEED before HIRE on land-buy morning: worker quick 22252.2 vs 22343.1; the 10-order cap then fits only 7 hires, missing the 8th hand on the new-field day. [n003]
- First fert pass without forced PICKUP left fertilizer unused (seed 101 $15489, below parent). [n004]
- Empty goose-tile None.get crash idled the agent at $3000 until fail-closed handling was fixed. [n004]
- PLACE below PLANT priority delayed the (3,4) goose; raising BUILD_COOP/PLACE above PLANT was needed for day-0 placement. [n004]
- Assigned-only coop actions left fertilizer in the shed (seed 101 score 16847; ~9 FERTILIZE vs ~53 COLLECT). [n005]
- Third goose on off-shed (4,3) escaped and broke coop logistics (seed 101 score 20104; 4 BUY_ANIMAL / 6 BUILD_COOP). [n005]
- Delaying geese, DROP 24, and skipping CARE lost watering labor to coop tiles (seed 101 scores ~21501–21553). [n005]
- Exclusive 5×10 row chunks: seed 101 $21118 vs parent $22454, with leftover ripe+unwatered. [n006]
- Exclusive NW/NE side blocks: seed 101 $20849; 4 NE actors cannot finish 100 harvest actions. [n006]
- Shipped locked-spawn columns: official validation 21683 vs parent 22269. [n006]
- Skip CARE whenever wheat_chain_busy: seed 101 21693, worker quick 21879.6; CARE=0 most days and FEED 4–6. [n007]
- Exclusive one-unit-per-coop plus harvest latch: seed 101 18019, worker quick 17871.4; occupant leaves after COLLECT so CARE never happens and leftovers worsen to 11–13. [n007]
- Harvest-day CARE skip without blocking visitor wheat pickup: seed 101 22713, worker quick 22989.4; FEED rises to 4–6 and peak leftovers stay 6–7. [n007]
- Full spawn-outward exclusive columns for all 9: worker seed 101 $24647 vs parent $23453, but leftover hotspot moved to unassigned x=7 and day 8 still had 8 ripe. [n008]
- Same full columns plus a 10-tile exclusive NE home for actor 5: worker seed 101 $23388 below parent $23453 (40-action harvest chain > 23 turns). [n008]
- BFS blobs grown from spawn/far corners gave the last shed-spawn actor a disconnected scrap (diameter 8). [n008]
- Geese on n006 spawn-strips with heavy CARE/PICKUP: seed 101 $20072 and worker quick 21461.8; leftover ripe/unwatered from labor steal. [n010]
- Skipping CARE/visitor wheat pickup: seed 101 $18614; HARVEST 371→254 and worse leftovers. [n010]
- Fertilizer ages 2–3 only plus idle-only DROP: seed 101 $18652; SELL WHEAT 39→28 and day-14 weeds from shed overflow. [n010]
