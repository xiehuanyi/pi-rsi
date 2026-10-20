# n011 progress

## Hypothesis
LuxurySpend=RoomService+Spa+VRDeck and EssentialSpend=FoodCourt+ShoppingMall (log1p), plus IsChild=(Age<13) and maybe AgeBin. Keep CryoSleep rules unchanged. Ablate sums-only vs sums+raw.

## 2026-09-10 start
- Parent commit acb8299 (n002): FeatureBuilder with five log1p spends + TotalSpend + Cryo flags + planet/dest/deck one-hots, ShallowHGB depth 3.
- Parent official validation 0.8125; parent worker quick 0.79655, folds=[0.78495, 0.80229, 0.80476, 0.79985, 0.79088], std=0.00745.
- Data check on data/train.csv: Age<13 n=641, transported 0.680, any spend>0 = 0. Min age with spend is 13. Age==13 n=116 transported 0.517, 60 spenders.
- log1p(Luxury=RS+Spa+VRDeck) corr Transported = -0.5519 vs individual luxury logs ~-0.34 to -0.36. Among spenders, luxury share corr = -0.504.
- AgeBin rates: <13 0.680, 13-17 0.546, 18-24 0.449, 25-39 0.477, 40+ 0.490 (non-monotonic dip at 18-24).
- Untouched eval.py quick was started then killed: features.py changed mid-run so later folds would not be parent. Will recover parent as local same-fold config `parent_raw`.
- Implemented FeatureBuilder flags: include_raw_spends / include_spend_sums / include_is_child / include_age_bin. Cryo rules untouched.
- Next: in-process 8-config ablation on eval.py folds (seed 20260910).

## 2026-09-10 ablation (local same folds as eval.py seed 20260910, NOT official eval.py)
ShallowHGB depth 3, 200 iter, lr=0.06. parent_raw reproduced parent worker quick exactly.

| variant | mean | std | vs parent | folds |
| parent_raw | 0.79655 | 0.00745 | 0 | [0.78495, 0.80229, 0.80476, 0.79985, 0.79088] |
| sums_only | 0.80045 | 0.00719 | +0.00391 | [0.78637, 0.80158, 0.80331, 0.80566, 0.80535] |
| sums_plus_raw | 0.79918 | 0.00977 | +0.00263 | [0.77999, 0.80158, 0.80259, 0.80493, 0.8068] |
| sums_child | 0.80045 | 0.00719 | +0.00391 | identical to sums_only |
| sums_raw_child | 0.79918 | 0.00977 | +0.00263 | identical to sums_plus_raw |
| raw_child | 0.79655 | 0.00745 | 0 | identical to parent |
| sums_child_agebin | 0.80045 | 0.00719 | +0.00391 | identical to sums_only |
| sums_agebin | 0.80045 | 0.00719 | +0.00391 | identical to sums_only |
| sums_child no TotalSpend | 0.79859 | 0.00858 | +0.00204 | slightly worse |

LR (same folds): parent_raw 0.76910; sums_only 0.78635 (+0.01725); sums_child 0.78620. Linear model harvests the composition; HGB already had most of it from five logs.

Permutation importance on full train (sums_child HGB): LuxurySpend +0.20751, EssentialSpend +0.04216, CryoSleep +0.02657, Age +0.00590, TotalSpend +0.00561, IsChild +0.00014, ZeroSpend/HasAnySpend 0.

Decision: ship sums-only (drop five raw logs) + IsChild, keep TotalSpend, no AgeBin. Gain vs parent is below fold std (0.007) so treat as noise on quick; still the hypothesized replacement and LuxurySpend is the tree's top split. IsChild is unused by depth-3 HGB (identical fold scores) but is the hypothesized child flag and does not change predictions.

Shipped FeatureBuilder: log1p LuxurySpend + EssentialSpend + TotalSpend + IsChild; dropped five raw amenity logs; AgeBin not included; CryoSleep rules unchanged.

Committed. Running official `eval/eval.py --seedset quick` next. Local same-fold HGB for this config was 0.80045 (std 0.00719) vs parent 0.79655.

## 2026-09-10 official quick
Command: eval/eval.py --seedset quick with task venv python.
score 0.80045, folds=[0.78637, 0.80158, 0.80331, 0.80566, 0.80535], std=0.00719, sem=0.00322, n=6954, elapsed=7.3s.
vs parent worker quick 0.79655: +0.00390, below fold std. Fold 4 +0.01447; folds 1–2 slightly down. Treat as noise on quick.
validation: harness-only.
Final commit: 2d1615eb55ebfa8fd9262d37554c438bb761b5b2
Writing HANDOFF.md and proposals.json.
