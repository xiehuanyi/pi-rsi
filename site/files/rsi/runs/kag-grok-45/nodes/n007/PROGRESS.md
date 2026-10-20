# Progress n007: More hands after NE unlock

## Plan
Keep BUY_LAND NE (day>=10, melon cap 16). Raise TARGET_HANDS from 6 to 8–10 once NE is unlocked so ~50 tiles get enough labor for carrot fill. Tune on quick, then validation.

## Baseline (untouched parent n005)
- `eval/eval.py --seedset quick`: score **38707.5** (margin 35273.2, win_rate 1.00, errors 0, std 2494.5). Matches parent handoff.

## Change: dynamic POST_LAND_HANDS after NE unlock
- `src/farm_ops.py`: `BASE_HANDS=6`, `target_hands(farm, day)` scales after NE / day gate.
- `src/market.py`: hire BASE first (so BUY_LAND fits), top up to post-land target, then seeds.

### Quick sweep (`eval/eval.py --seedset quick`)
| POST_LAND_HANDS | mode | score | vs baseline 38707.5 |
|---|---|---|---|
| 7 | unlock | **38894.3** | +186.8 |
| 8 | unlock | 38004.4 | −703.1 |
| 8 | day | 38004.4 | −703.1 |
| 9 | unlock | 36568.9 | −2138.6 |
| 10 | unlock | 35547.8 | −3159.7 |

Hypothesis range 8–10 all regress. Only +1 hand (7) is a tiny quick gain. Selecting POST=7 for validation.

## Validation (POST_LAND_HANDS=7, unlock-gated)
- `eval/eval.py --seedset validation`: score **36405.2** (margin 33065.9, win_rate 1.00, errors 0, std 3068.9, n=32).
- Parent n005 validation was **36583.7** → this is a **regression of ~−178**.
- Quick gain did not transfer. More hands after NE (even +1) fails the official metric; 8–10 are clearly worse on quick.

## Conclusion
Hypothesis refuted for the 8–10 range. Bottleneck is not raw hire count under index-mod ownership — likely pathing/partition scatter and melon watering dilution. Next: quadrant-local assignment or melon fertilizer to free bandwidth without more hands.
