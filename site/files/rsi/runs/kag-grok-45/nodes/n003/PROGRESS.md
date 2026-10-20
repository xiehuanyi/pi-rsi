# Progress n003: Buy NE land, extend hand farm

## Plan
1. Baseline quick score of untouched n002 code.
2. Add BUY_LAND once money > ~4000 (NE for $1000); farm already uses unlocked_tiles so should auto-extend to 50 tiles.
3. Tune TARGET_HANDS if watering 50 tiles falls behind (try 6 first, then 8–10).
4. Validation once quick looks good.

## Log

### Baseline (untouched n002)
- Command: `eval/eval.py --seedset quick`
- Result: score=11690.2, margin=8402.2, win_rate=1.00, errors=0, std=3050.9
- Matches parent handoff. Proceeding to add BUY_LAND for NE.

### v1: BUY_LAND NE @ money>4000, TARGET_HANDS=6
- Commit: 575798e
- quick: score=8656.7 (margin=5440.7, win_rate=1.00, errors=0, std=962.1) — WORSE than baseline 11690
- Diagnose seed0: NE unlocks ~day8; plants stall ~25-32/50; dying often 5-20; empty stays high. Watering fails.

### Hand/threshold sweeps (quick, monkeypatch)
- hands=6 thresh=4000: 8656.7
- hands=8 thresh=4000: 6668.4 (worse)
- hands=10 thresh=4000: 4055.2 (worse)
- hands=8 thresh=6000/8000: 6356 / 7158
- hands=10 thresh=8000: 6276
- hands=6 thresh=5000/7000/10000/12000: 9815 / 10652 / 11132 / 11232 — approaches but never beats no-land
- hands=6 thresh=999999 (no land): 11690.2 (baseline)
- More hands hurt (matches n002). Delaying land just dilutes the damage. Index-mod across NW+NE is the killer.

### Contiguous-block partition + hands=6 thresh=4000
- quick: score=9015.5 — better than mod+land (8656) but still << no-land 11690

### Contiguous + hand sweep
- hands 6/7/8/9 @4000: 9015 / 7785 / 7120 / 5177 — more hands still hurt
- hands 6/8 @7000: 8324 / 7853

### Plant-cap (skip PLANT beyond first N unlocked) + contiguous
- cap 25/28/32/35/40/50: 9002 / 8503 / 9221 / 9186 / 8671 / 9015
- Best land variant 9221 still below baseline; cap=25 wastes $1000 and steals units onto fallow NE ranks

### Quadrant-split ownership (units stay in one quadrant)
- quick: score=8713.9 — no win
- Dynamic hands 6→8/10/12 after NE: all worse (7115 / 4739 / ... / 3665)

### Root cause: carrot market glut
- No-land seed0: price stabilizes ~$21 (mkt inv ~10150), final ~11585, plants=25 steady
- Land-buy seed0: price crashes to ~$5 (mkt inv ~10666), final ~6027; plants 28-41
- Env prices carrot with T=450 sized for one 5x5 field; two fields of carrots are structurally oversupply
- Watering/partition issues are secondary; even when plants grow, dumping doubles supply into glut destroys revenue

### Final (hypothesized recipe shipped)
- Commit: `97ceabeca6a9d6aa457307e8141fdb1cf00704cb`
- quick: score=8656.7 (margin=5440.7, win_rate=1.00, errors=0, std=962.1) — below baseline 11690.2
- validation: score=8229.4 (margin=5024.2, win_rate=1.00, errors=0, std=2640.0, n_games=32) — below parent 9084.6
- Hypothesis REJECTED for same-crop carrot expansion: market T calibrates one 5x5; second field crashes price.
- HANDOFF.md and proposals.json written.
