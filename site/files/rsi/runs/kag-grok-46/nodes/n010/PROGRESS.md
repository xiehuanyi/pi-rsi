# n010 progress

Hypothesis: fertilize wheat bonus window (ages 2–4) with 2 spawn-adjacent geese,
forced morning PICKUP of fertilizer, FERTILIZE-before-WATER, DROP only when idle
or hour>=21 with no remaining water jobs (never interrupt stay-on-tile).

## 2026-09-10 start
- Parent n006: official validation 21683; worker quick 21815.2.
- Global best n008: 24614. n005 already shipped a similar goose-fert path on n003
  greedy (validation 23598). This node is n006 parent (spawn-aware regions).
- Will not retry n005 dead ends: 3rd goose on (4,3), assigned-only coop actions,
  daily BUY_PRODUCT WHEAT whenever shed < n_geese, BUY_PRODUCT FERTILIZER at $100.
- Plan: 2 coops at (4,4)/(5,4); forced hour-0 PICKUP so shed fertilizer leaves;
  FERTILIZE then WATER; DROP idle or late-hour only if no WATER jobs remain;
  overflow DROP only on non-stay-on-tile actors (n003 labor-steal risk).

## Untouched baseline
Running `eval/eval.py --seedset quick` on parent code before any edits.

- untouched quick: score 21815.2 (12 games, errors=0, std=170.6, margin=18289.8). Matches n006 worker quick.

## v1 implement
- 2 coops at (4,4)/(5,4); BUILD_COOP/PLACE/FEED/COLLECT/CARE; no $100 fertilizer.
- FERTILIZE before WATER on ages 2–4; redirect fertilizer carriers to bonus-window plants.
- Forced PICKUP of shed fertilizer in hours 0–1 (and whenever shed-adjacent with demand).
- DROP: never interrupt stay-on-tile; overflow at 12 on walkers; hour>=21 only if no WATER jobs.
- Keep n006 spawn-strip matching. Fail-closed on non-dict tiles.
- Emergency BUY_PRODUCT WHEAT only when total wheat is 0.

Running seed-101 diagnostic + quick eval.

- v1 seed 101 seat 0: $20072 (parent n006 $22454). FERTILIZE=48 COLLECT=67 PICKUP_FERT=40 FEED=53 CARE=123. Fertilizer leaves the shed. CARE=123 and PICKUP WHEAT=95 steal harvest labor: day 13 leftover 8 unwatered + 4 ripe (parent 0 ripe + 4–5 unwatered). BUILD_COOP=3 PICKUP GOOSE=7 (place/drop cycle). BUY_PRODUCT WHEAT=11.
- v1 quick: score 21461.8 (was 21815.2); margin 17810.2; win_rate 1.00; errors 0; std 1209.6. Command: `eval/eval.py --seedset quick`

## v2–v4 dead ends (seed 101 seat 0)
- v2 skip CARE/visitor wheat pickup: $18614. HARVEST 371→254; leftovers worse (day 13: 7 unwatered + 6 ripe).
- v3 fert ages 2–3 + strict idle-only DROP: $18652. SELL WHEAT 39→28; shed overflow; day 14 weeds=5.
- v4 greedy + those cuts: $18534. n006 matching was not the only issue; cutting CARE/overflow DROP was.
- Layering geese onto n006 spawn-strips without n005's greedy+CARE+DROP@12 scored ~20k.

## v5 n005 fertilizer base + skip late DROP while water-busy
- Port n005 (2 spawn coops, FERTILIZE-before-WATER, overflow DROP@12 after stay-on-tile, CARE, emergency wheat buy only if total=0).
- Hypothesis increment: hour>=21 DROP only if no WATER jobs remain; morning PICKUP of shed fertilizer even before demand.
- Fail-closed on non-dict coop tiles (n004 None.get).
- seed 101 seat 0: $24139 (n005 $23453, n006 parent $22454). WATER 1423 vs n005 1386; DIG 10 vs 14.
- v5 quick: score 24122.6 (was 21815.2); margin 20501.2; win_rate 1.00; errors 0; std 280.6. Command: `eval/eval.py --seedset quick`
- git: `51fa321`

## validation
Running `eval/eval.py --seedset validation` on shipped v5.

- validation: score 24574.6 (was 21683.1 at n006); margin 20902.5; win_rate 1.00; errors 0; std 714.3; min 23449 max 26182; n_games 32. Command: `eval/eval.py --seedset validation`
- Above n005 fertilizer baseline (23597.9) and near n008 global best (24614).

## done
HANDOFF.md and proposals.json written. Shipped commit 51fa321.
- Walk to coops only for BUILD/PLACE/FEED/COLLECT (no CARE/egg walks).
- Standing CARE/eggs only when no WATER jobs remain; harvest loads skip coop actions.
- Wheat-for-feed PICKUP only if stay-on-tile on that coop (DROP visitors no longer PICKUP wheat).
- Don't DROP a carried goose (PICKUP/PLACE cycle).
