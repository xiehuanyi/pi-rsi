# Progress n002: Cheap daily hired hands for parallel farm ops

## Plan
- Baseline quick eval on untouched starter (carrot solo loop)
- Implement: hire N hands at hour 0, multi-tile carrot planting on NW, assign farmer+hands to partitioned tasks with pathing
- Iterate on quick; finish with validation

## Log
- Reading docs + agent.py. Baseline is solo carrot on farmer tile only (~3500).
- **Baseline quick**: score=3491.3, margin=0.0, win_rate=0.00, errors=0, std=77.4 (12 games).
- Key env detail: unit actions run BEFORE market, so hands hired this turn act starting next turn. Hands clear each EOD; must re-hire daily. Planting day MUST be watered or plant becomes weed. Multi-PLANT exceeding seed count blocks ALL plants that turn.
- Implementing partitioned NW carrot farm with daily HIRE.

### Iterations (quick seedset)
| config | quick score | notes |
|---|---|---|
| baseline solo carrot | 3491.3 | starter |
| TARGET=4, basic partition, harvest-before-water | 8877.3 | first commit; yield often 2 not 3 |
| TARGET=6, water-before-harvest, DROP haul thresh=6 | 10751.2 | full bonus yield; DROP trips cost bandwidth |
| TARGET=8 | 8297.3 | worse — ownership scatters, money tied in seeds |
| TARGET=4 columns / in-place replant variants | 9766–10291 | full occupancy but mean below 10751 |
| seed stockpile buy | 9118.8 | overbuy ties up capital |
| TARGET=5 no DROP haul | 8328.8 | under-bandwidth |
| **TARGET=6, water-before-harvest, opportunistic DROP only** | **11690.2** | best quick; std=3050, min=7875 max=16734 |

### Mechanism notes
- Parallelism works: full 25 NW tiles planted vs 1 tile baseline; ~3× money.
- Hire cost negligible (fib sum for 6 = 20/day).
- Critical: WATER before HARVEST on max-yield day (carrot ages 2+3 bonuses → yield 3).
- Mid-day shed hauls kill harvest/replant throughput; rely on EOD drop.
- Town-shop RNG drives large seed variance (carrot demand).
- Still far from 138k strong agent — need land/animals/better crops next.

### Final scores
- **quick**: 11690.2 (best config, commit d48c775)
- **validation**: 9084.6 (margin 5888.0, win_rate 1.00, errors 0, std 1877.2, 32 games)
- vs parent/root validation 3586.81 → ~2.5× lift; hypothesis confirmed.
- HANDOFF.md + proposals.json written.
