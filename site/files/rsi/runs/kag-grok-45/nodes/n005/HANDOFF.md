# Handoff n005: Buy NE land under melon tile cap
## Hypothesis
Once melon+carrot cashflow is stable (~day 10 / after first melon harvest), submit BUY_LAND for NE ($1000). Extend the same TARGET_HANDS=6 index-mod partition onto the unlocked 50 tiles, but keep MELON_MAX_TILES at 16 so new tiles fill with carrot rather than doubling melon into the price floor. Expected large gain from extra carrot throughput; risk that 6 hands cannot tend 50 tiles.

## What I did
- `src/farm_ops.py`: added `BUY_LAND_MIN_DAY=10`, `BUY_LAND_RESERVE=500`, `BUY_LAND_MIN_MONEY` (final 0), `BUY_LAND_TARGET="NE"`; kept `MELON_MAX_TILES=16` and `TARGET_HANDS=6`. `unlocked_tiles()` already covers newly unlocked NE.
- `src/market.py` `build_market_orders`: after sell+hire, emit `["BUY_LAND"]` when NE locked, day≥10, and money ≥ cost+reserve; optional min-money gate; credit conservative sell proceeds for same-turn affordability/seed buys.
- `agent.py`: pass market `prices` into `build_market_orders`.
- Tuned on quick: day/cap sweep, post-sale money gate, and a failed “force carrot fill before melon replant” experiment.

## Result
- Untouched parent quick: score 37637.3 (`eval/eval.py --seedset quick`).
- Best worker quick: score 38866.9 with `BUY_LAND_MIN_MONEY=5000` (margin 35426.7, win_rate 1.00, errors 0, std 2531.7).
- Final knobs (better validation among land variants): `BUY_LAND_MIN_DAY=10`, `BUY_LAND_MIN_MONEY=0`, `MELON_MAX_TILES=16` — quick 38707.5; validation **36583.7** (margin 33230.4, win_rate 1.00, errors 0, std 2771.9, n_games 32) — `eval/eval.py --seedset validation`.
- Parent validation was 36891.8; this node is a slight **regression** (~−308). Hypothesis did not improve the official metric.
- Final git commit: `ab628537da552a04c986425491ede2634e000168`.

## Mechanism
NE unlock does add 25 plantable tiles, and the melon cap correctly prevents a double melon glut. The bottleneck is labor: with only 7 actors (farmer+6) already watering 16 long-cycle melons, index-mod ownership across non-contiguous NW+NE leaves ~20–30 empties for much of the season. Extra carrot revenue on quick is only ~+1k mean, and on validation the $1000 land cost plus scattered pathing/weeds outweigh that. Forcing carrot fill before the second melon wave (delaying melon replant) crashed quick to ~32k — melon revenue still dominates.

## Dead ends
- Earlier BUY_LAND (day 5/6/8): quick 34701–37718, all below day-10.
- Melon caps 12/14/18/20 with NE: quick 34428 / 36022 / 32706 / 32461 — worse than 16.
- `BUY_LAND_MIN_MONEY=5000/10000`: best quick 38866.9 but worse validation 36491.5 vs day10-only 36583.7.
- Force carrot fill until empties≤8/5/15 before melon replant: quick 32028 / 32028 / 32411.

## Next hypotheses
1. Raise hired hands (or add a second daily hire wave) after NE unlock so 50 tiles can be watered/planted; land only pays once bandwidth matches area.
2. Quadrant-local partition: assign some units exclusively to NE and some to NW so pathing stops crossing the shed gap under index-mod.
3. Melon fertilizer (BUY_PRODUCT or goose) on ages 6–8 to hit yield 6 by age 8 — free two days per cycle without needing more land.

## Open questions
- What TARGET_HANDS makes 50-tile NE+NW carrot fill net-positive on validation (8? 10?) without repeating n002’s TARGET=8 failure on 25 tiles?
- Does buying NE *after* fertilizer shortens melon duty-cycle enough that the same 6 hands can cover carrots?
- Is SW ($2k) ever worth it, or is land expansion strictly bandwidth-gated?
