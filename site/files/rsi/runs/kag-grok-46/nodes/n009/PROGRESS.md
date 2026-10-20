# n009 progress

Hypothesis: Skip late DROP while tiles need water. Keep DROP_INVENTORY_THRESHOLD=24, but only take the hour>=21 DROP path when the unit has no remaining WATER/HARVEST/PLANT job (or when no unwatered plants remain). Stay-on-tile matching unchanged. EOD auto-drop still banks inventory.

## Plan
1. Measure untouched parent (n006 locked-column strips) on quick.
2. Change only the late-DROP gate in `choose_unit_actions`: overloaded units still DROP; hour>=21 DROP only if this unit has no WATER/HARVEST/PLANT job or the board has no unwatered plants.
3. Diagnose leftover unwatered on seed 101 hour 23; iterate on quick; then validation.

## Log

### 2026-09-10 start
Read `src/policy.py` DROP block: stay-on-tile fires first, then
`carried >= 24 or (hour >= 21 and carried > 0)` walks every carrier to the shed.
Idle DROP (tgt is None, carried > 0) still banks leftover inventory.
EOD auto-drop from any tile still fills the shed.

About to run untouched quick baseline.

### Untouched baseline
- quick: score 21815.2 (12 games, errors=0, std=170.6, margin=18289.8, win_rate=1.00). Command: `eval/eval.py --seedset quick`
- Matches n006 parent (21815.2).

### Diagnose seed 101 seat 0 (untouched n006)
- FINAL $21919.
- Hour-23 leftover unwatered: d5:5, d8:4, d9:2, then 4 on each harvest-cycle night (d12,13,16,17,20,21,24,25) plus d28:1. Weeds on d9.
- Late hours on leftover days: DROP=8, MOVE=160, WATER=53. Carriers are usually not shed-adjacent so they walk toward the shed (MOVE) instead of DROP. Stay-on-tile still waters/harvests if already standing on the job.
- Day 8 hour 21–23: carried 80–88, WATER 3+0+1, MOVE 3+4+6, leftover 4 unwatered. The MOVEs are the 4–5 missed waters.
- Day 5 carried=0 (NE plant-out), so late DROP is not the d5 leftover; that is expansion labor.

Implementing: keep threshold-24 DROP; hour>=21 DROP only if this unit has no WATER/HARVEST/PLANT job or no unwatered plants remain.

### v1 skip late DROP (crop job or unwatered remain)
- seed 101 seat 0: $22373 (was $21919). Leftover unwatered down: d8 4→2, harvest-cycle nights 4→2 or 3. d5 still 5 (carried=0). Weeds on d9 gone. Late WATER 53→68, MOVE 160→133. Shed empty at hour 21–23 so eod auto-drop of ~80–88 wheat fits the 100 cap.
- Still 2–3 leftover unwatered (and d8 leftover ripe=3 from n006 matching). Idle carriers have no tgt so they still DROP; matching unchanged so far tiles still need 3+ walk steps.
- quick: score 22221.7 (was 21815.2); margin 18739.3; win_rate 1.00; errors 0; std 180.1; elapsed 8.3s. Command: `eval/eval.py --seedset quick`
- Gain +406 vs parent quick. Hypothesis confirmed on quick (low end of +400–1500).

About to run validation.

### validation (v1 skip late DROP)
- validation: score 22085.9 (was 21683.1 at n006); margin 18381.6; win_rate 1.00; errors 0; std 242.5; min 21632 max 22373; n_games 32; elapsed 15.7s. Command: `eval/eval.py --seedset validation`
- Gain +403 vs parent, in line with quick +406. Still below n003 greedy (22269) because locked-column matching was left unchanged.
- git: `d5d3f811672c3993224eced7b5ae69a467eb862b`

Hypothesis confirmed: skipping hour-21 DROP while crop jobs / unwatered tiles remain recovers ~$400 by watering leftover plants instead of walking to the shed. Remaining 2–3 unwatered and d8 leftover ripe are n006 matching, not late DROP.
