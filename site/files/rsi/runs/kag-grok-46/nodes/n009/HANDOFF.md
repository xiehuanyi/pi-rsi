# Handoff n009: Skip late DROP while tiles need water
## Hypothesis
Parent leftover at hour 23 is 4–5 unwatered wheat tiles (0 leftover ripe on greedy). DROP_LATE_HOUR=21 sent every carrier toward the shed for hours 21–23. Keep DROP_INVENTORY_THRESHOLD=24, but only take the hour>=21 DROP path when the unit has no remaining WATER/HARVEST/PLANT job, or when no unwatered plants remain on the board. Stay-on-tile matching unchanged. EOD auto-drop still banks inventory.
## What I did
- Measured untouched n006 on quick (21815.2) and diagnosed seed 101 seat 0: $21919, leftover unwatered 4–5 on harvest nights, late hours DROP=8 MOVE=160 WATER=53 (carriers walk to the shed, not yet adjacent).
- `src/policy.py`: `_has_unwatered`, `_is_crop_job`; `choose_unit_actions` late DROP now requires `not crop_job or not unwatered_remain`. Threshold-24 DROP and idle DROP (no tgt) unchanged. Stay-on-tile and `_region_targets` untouched.
- `src/constants.py` / `agent.py`: comments only.
## Result
- untouched quick: score 21815.2 (12 games, errors=0). Command: `eval/eval.py --seedset quick`
- seed 101 seat 0 v1: $22373 (was $21919); leftover unwatered d8 4→2, harvest-cycle nights 4→2 or 3; d9 weeds gone; late WATER 53→68, MOVE 160→133. Shed empty at 21–23 so eod auto-drop of ~80–88 wheat fits cap 100.
- quick: score 22221.7 (was 21815.2); margin 18739.3; win_rate 1.00; errors 0; std 180.1; min 21891 max 22373. Command: `eval/eval.py --seedset quick`
- validation: score 22085.9 (was 21683.1 at n006); margin 18381.6; win_rate 1.00; errors 0; std 242.5; min 21632 max 22373; n_games 32. Command: `eval/eval.py --seedset validation`
- git: `d5d3f811672c3993224eced7b5ae69a467eb862b`
## Mechanism
Stay-on-tile already waters a tile the unit stands on, even at hour 21. Late DROP only redirected carriers who would have *walked* to leftover unwatered tiles. Skipping that redirect spends hours 21–23 on remaining WATER/HARVEST/PLANT jobs; eod auto-drop from any tile still banks the harvest, and the shed was empty so cap-100 did not clip. About 2–3 unwatered tiles still remain because they are more than three steps from the assigned actor, and n006 locked-column matching still leaves leftover ripe (d8: 3) — matching, not DROP, is now the leftover bottleneck.
## Dead ends
- None tried and reverted. Did not change matching (on-hypothesis). Did not lower DROP_LATE_HOUR or drop the overload threshold. Overflow risk on a 25-tile harvest did not fire on seed 101 (carried 80–88, shed 0).
## Next hypotheses
- Revert n006 locked-column `_region_targets` to unconstrained greedy `_greedy_targets`, keeping this skip-late-DROP. n003 greedy was quick 22343.1 / validation 22269 with 0 leftover ripe; n006 matching still costs ~$400–500 and leaves d8 ripe. Combining greedy with skip-late-DROP should close more of the 4–5 unwatered n003 leftover.
- Fertilize wheat ages 2–4 with 2–3 shed-adjacent geese and forced morning PICKUP so fertilizer actually leaves the shed (n004 failure mode); pair with DROP only when idle so harvest chains are not interrupted.
- Y-first (not x-first) stepping from locked SW/SE spawn (4,5)/(5,5) so the first step is NORTH onto (4,4)/(5,4) without claiming a spawn-column job that greedy would give to a closer actor.
## Open questions
- After skip-late-DROP, are the remaining 2–3 unwatered tiles always the far corners of the harvest half, and does greedy (no spawn-column claim) reach them in 3 hours?
- Last plant day is 25; day 28 leftover unwatered=1 and 22 plants — is a final-days harvest/sell pass still leaving money in the field?
- Would skipping late DROP for WATER jobs only (still DROP when walking to HARVEST/PLANT) free extra water labor, or just reintroduce leftover ripe?
