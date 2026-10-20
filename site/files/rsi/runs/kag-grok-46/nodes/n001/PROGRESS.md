# Progress n001 — Multi-tile wheat farm

## Plan
Implement a deterministic NW-quadrant wheat agent: bulk-buy wheat seeds, serpentine over unlocked empty tiles planting WHEAT, daily WATER first, then HARVEST (age >= first_yield_day, or max_yield_day if time allows), DROP at shed-adjacent, SELL all shed wheat every turn. No hands/land/animals.

## 2026-09-10 start
Reading docs/agent.py. Next: baseline quick eval of untouched starter, then implement wheat farm.

## Baseline (untouched starter)
- quick: score=3491.3, n=12, errors=0, std=77.4, elapsed=4.6s
  command: `eval/eval.py --seedset quick`

## Design notes (from env source)
- One farmer action/turn, 24 turns/day. WATER does not move, so watering N path-connected tiles costs 2N-1 actions.
- Daily watering of 20+ tiles is impossible with one farmer (~12 max if water-only). Harvest+replant adds ~3 extra actions/tile.
- Safe daily-water farm: ~8 tiles, harvest at max_yield_day=4 (bonus window ages 2–4), stagger 2 new plants/day so harvests do not clump.
- New plants start consecutive_unwatered=1: must WATER the same day or they weed at EOD.
- Farmer inventory auto-drops at EOD except there is no market after day-29 EOD, so last harvest day is 28 (sell on 29) or explicit DROP on 29.
- Yield starts at 1; +1 per watered bonus-window day; unfertilized wheat peaks at 4.

## Iteration
- First 8-tile 4x2 (with mid-route DROP): seed 101 seat0 **$8749**. Plants stable at 8, no missed water.
- 9-tile 3x3 with +1 ramp overflowed to 3-harvest days (26 actions needed): missed 2 waters EOD many days, plants weeded, day-29 harvest never DROPped. seed 101 **$7028**.
- Fix: hard cap 2 plants/day, harvest all age>=2 on day 28 for EOD drop/sell. 3x3 still only filled 8/9 because replants ate the cap. seed 101 **$8824**, 102 **$9419**, 103 **$8915**. No EOD unwatered.
- Revert patch to 4x2 (8 tiles) so we don't waste turns walking an empty 9th tile. Next: quick eval.

## Quick eval (8-tile 4x2, daily water, harvest age 4)
- **quick: score=9360.7** (was 3491.3), n=12, errors=0, std=407.2, win_rate=1.00, margin=5785.3, elapsed=5.3s
  command: `eval/eval.py --seedset quick`

## Dead ends this node
- 9-tile 3x3 with a 3-plant ramp cohort: 3-harvest days need 26 actions; missed 2 waters, weeds, day-29 harvest unsold. seed 101 $7028.
- Skip age-1 watering to free turns for a 9th tile: seed 101 $9936 but seed 102 $7735 (weeds / missed bonus). Not robust; reverted.

## Confirmed quick (committed 7ef8354)
- quick: score=9360.67, min=8828, max=10055, win_rate=1.00, errors=0

## Validation (official)
- **validation: score=9524.62**, n=32, errors=0, win_rate=1.00, margin=5975.19, std=804.27, min=7338, max=10439, elapsed=9.6s
  command: `eval/eval.py --seedset validation`
- vs parent/root 3586.81: about +5.9k mean money, still well below the 20k–50k hypothesis band because 20+ daily-watered tiles need hired hands.

