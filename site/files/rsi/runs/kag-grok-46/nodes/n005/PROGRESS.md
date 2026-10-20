# n005 PROGRESS

## Hypothesis
Fertilize wheat bonus window via 2–3 geese (BUILD_COOP near shed, BUY_ANIMAL GOOSE, PLACE, daily FEED, COLLECT_FERTILIZER) rather than $100 BUY_PRODUCT fertilizer. One FERTILIZE covers ages 2–4 (+2 wheat/day, cap 6). DROP threshold ~12 on non-stay-on-tile actors to avoid shed overflow and n003 labor-steal.

## Plan
1. Measure untouched parent on quick.
2. Implement 2 spawn-tile coops first (4,4) and (5,4): leave unplanted, BUILD_COOP, buy/place geese after cash allows, daily feed+collect, FERTILIZE before WATER on age-2 wheat, reserve wheat for feed, don't SELL fertilizer/animals.
3. DROP threshold 12 only when not stay-on-tile.
4. Iterate (2 vs 3 geese, CARE, thresholds) on quick, then validation.

## Baseline
Starting from parent n003 (official 22,269).
- untouched quick: score 22343.1; margin 18789.3; win_rate 1.00; errors 0; std 179.2; elapsed 8.2s
  Command: `eval/eval.py --seedset quick`

## v1 implementation
2 spawn-tile coops at (4,4) and (5,4). Leave unplanted, BUILD_COOP, BUY_ANIMAL GOOSE, PLACE, daily FEED + COLLECT_FERTILIZER + CARE. FERTILIZE before WATER on wheat ages 2–4. Don't SELL fertilizer/animals; reserve wheat for feed. DROP threshold 12, never interrupt stay-on-tile.

About to diagnose seed 101 then run quick.

## Iteration notes
- untouched quick: 22343.1
- v1 (2 spawn coops, DROP 12, CARE, daily BUY_PRODUCT wheat, 2 geese day 0): seed 101 seat0 **23633** (parent ~22454). FERTILIZE 53, but bought wheat every day and a 2nd goose sat in the shed until NE.
- v2 (delay geese until NE, DROP 24, no CARE): seed 101 **21501**. Unwatered leftovers, NE on time, but coop tiles stole DROP and watering.
- v3 (assigned-only coop actions): seed 101 **16847**. Fertilizer stuck in shed (only 9 FERTILIZE).
- v4 (anyone-on-coop, DROP 24, no CARE, no daily wheat buy): seed 101 **21553**. FERTILIZE 53 but FEED 106 (double-feed no-ops).
- v6 (v1 action order + don't buy extra goose + BUY_PRODUCT only if total wheat==0 + reserve 10 wheat + CARE + DROP 12): seed 101 **23453**. FERT 53 FEED 58 COLLECT 77 CARE 111 BUY_W 6 BUY_G 2.

v6 beats parent on seed 101. Running quick.

- v6 quick: **score 23286.6** (was 22343.1); margin 19618.1; win_rate 1.00; errors 0; std 318.9; min 22849 max 23740; n=12
  Command: `eval/eval.py --seedset quick`
- v7 NUM_GEESE=3 with extra coop at (4,3): seed 101 **20104**. Third coop is not shed-adjacent; geese escaped, 4 BUY_ANIMAL / 6 BUILD. Reverted.

About to run validation on v6 (2 spawn-tile geese).

- v6 validation: **score 23597.9** (was 22269.0); margin 19941.1; win_rate 1.00; errors 0; std 556.7; min 22665 max 24469; n_games 32
  Command: `eval/eval.py --seedset validation`
- git: `d8bc54481fdb0a5695f5fd269194d5019bb065f7`

Shipped 2 spawn-tile geese + FERTILIZE-before-WATER + feed reserve + DROP 12. Third off-shed goose and assigned-only coop logistics were dead ends.

