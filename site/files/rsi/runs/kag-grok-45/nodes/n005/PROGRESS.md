# Progress n005: Buy NE land under melon tile cap

## Plan
1. Baseline untouched parent on quick.
2. Add BUY_LAND for NE once cashflow is stable (after first melon harvest / ~day 10), keep MELON_MAX_TILES ~16–20, fill new tiles with carrot under TARGET_HANDS=6 index-mod partition.
3. Tune timing / melon cap on quick; then validation.

## Log

### Baseline (untouched parent)
- Command: `eval/eval.py --seedset quick`
- Result: score=37637.3 margin=34208.8 win_rate=1.00 errors=0 std=1450.4
- Matches n004 handoff.

### Next
Implement BUY_LAND NE after day>=10 once money covers $1000 + ops reserve; keep MELON_MAX_TILES=16; new empties get carrot via existing plant gate.

### Try 1: BUY_LAND NE day>=10, reserve=500, melon_cap=16
- Change: market.build_market_orders emits BUY_LAND after hire when NE locked, day>=10, money>=1500.
- farm_ops keeps MELON_MAX_TILES=16; unlocked_tiles auto-includes NE.
- Result: score=38707.5 margin=35273.2 win_rate=1.00 errors=0 std=2494.5
- Lift vs baseline: +1070.2 (modest; expected larger from +25 carrot tiles)
- Committed.

### Sweep: BUY_LAND_MIN_DAY × MELON_MAX_TILES (reserve 500 unless noted)
| day | cap | reserve | quick score |
|-----|-----|---------|-------------|
| 6 | 14 | 500 | 35858.5 |
| 6 | 16 | 500 | 37718.2 |
| 6 | 18 | 500 | 30402.8 |
| 8 | 14 | 500 | 36517.8 |
| 8 | 16 | 500 | 37093.5 |
| 8 | 18 | 500 | 29666.2 |
| 10 | 14 | 500 | 36021.8 |
| **10** | **16** | **500** | **38707.5** |
| 10 | 18 | 500 | 32705.8 |
| 12 | 14 | 500 | 36520.7 |
| 12 | 16 | 500 | 36669.2 |
| 12 | 18 | 500 | 32623.3 |
| 5 | 16 | 200 | 34701.3 |
| 10 | 12 | 500 | 34428.3 |
| 10 | 20 | 500 | 32461.2 |
Earlier buys / other caps all worse. Cap 16 × day 10 best in this grid.

### Probe notes
- NE buys on day 10 with ~2400 bank; after unlock ~20–30/50 tiles stay empty.
- Hands bandwidth: watering 16 melons + index-mod across NW+NE leaves carrot fill incomplete.
- Day 15 often shows melon=16, carrot≈1, empty≈30 after second melon wave.

### Try 2: post-sale money gate + sell-proceeds credit
- BUY_LAND_MIN_MONEY=5000 (or 10000): quick **38866.9** (+159 vs day10-only).
- Sell-proceeds credit in build_market_orders for same-turn land affordability.

### Dead end: force carrot fill before melon replant (NE_FILL_EMPTY_THRESHOLD)
- thresh 8/5 → 32028.4; thresh 15 → 32410.6. Delaying second melon wave costs more than extra carrots earn. Reverted.

### Final knobs before validation
- BUY_LAND_MIN_DAY=10, BUY_LAND_MIN_MONEY=5000, BUY_LAND_RESERVE=500, MELON_MAX_TILES=16, TARGET_HANDS=6
- quick: 38866.9 (parent untouched 37637.3; lift +1229.6)

### Validation
- min_money=5000 (best quick): validation **36491.5** (margin 33140.1, win_rate 1.00, errors 0, std 2815.3) — below parent 36891.8
- min_money=0 (day>=10 only): validation **36583.7** (margin 33230.4, win_rate 1.00, errors 0, std 2771.9); quick 38707.5
- Chose min_money=0 for final (better validation among land variants). Hypothesis does **not** beat parent on validation.

### Conclusion
Buying NE adds plantable area but TARGET_HANDS=6 cannot productively farm 50 tiles while tending 16 melons; ~20–30 empties persist and pathing across NW+NE is wasteful. Modest quick lift (~+1.2k) does not transfer to validation (slight regression). Next: more hands / quadrant-local partition / fertilizer for faster melon cycles — not more land yet.
