# n004 progress

## Hypothesis
Fertilize wheat in the ages 2–4 bonus window so watered plants gain +2/day (cap 6) instead of +1 (cap 4). Prefer 2–3 geese for free daily fertilizer + eggs; do not buy $100 fertilizer unless 2× wheat price exceeds the buy price (ROI of bought fert is negative at glut ~$22).

## Plan
1. Measure untouched parent (n002 wheat + 5 daily hires) on quick.
2. Add 3 coops near the shed, buy/place geese, FEED + COLLECT_FERTILIZER daily, apply one fertilizer per wheat plant at age 2 (covers ages 2–4). Keep stay-on-tile water→harvest→replant.
3. Re-eval quick; iterate if weeds, missed feeds, or score drop; then validation.

## Log
- 2026-09-10: starting. Reading docs + parent policy. Launching untouched quick eval.
- untouched quick: score=15888.3 margin=12293.5 win_rate=1.00 errors=0 std=715.4 (12 games). Matches parent n002.
- Implementing 3 geese on (4,4)/(3,4)/(4,3), collect fertilizer, FERTILIZE wheat at ages 2–3. Not buying $100 fertilizer (2×wheat ≈ $44 < $100).
- Next: smoke seed 101, then quick eval.
- Bug: geese_owned crashed on empty tiles (None.get) → agent swallowed and idle $3000. Fixed.
- Seed 101 after first fert pass: $15489 (fert sat in shed; actors never picked it up).
- Forced morning PICKUP of wheat/geese/fertilizer + higher PLACE/BUILD prio: seed 101 $19448 vs starter $3441. Ops: FERTILIZE 76, EGG sold 144, WHEAT sold 582, 3 geese fed, 0 weeds. Untouched parent ~15888.
- Running quick eval.
- quick: score=21822.1 (was 15888.3); margin=18356.3; win_rate=1.00; errors=0; std=1774.3; min=19448 max=24072; n=12. Command: eval/eval.py --seedset quick
- Commit 8123f99. Launching validation.
- validation: score=20735.5 (was 16216.75); margin=17165.53; win_rate=1.00; errors=0; std=1884.07; min=18325 max=24975; n=32. Command: eval/eval.py --seedset validation
- Gain vs parent ~+4519 on validation. Hypothesis confirmed via geese (not bought fertilizer). Writing HANDOFF.
