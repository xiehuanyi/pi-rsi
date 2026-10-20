# pi-rsi report: st-grok46

- task: kaggle-spaceship-titanic; metric `score` (higher is better)
- worker: grok:grok-4.6 (xhigh); utility: grok:grok-4.5
- search: width_root=3 width=2 depth=4 max_nodes=16 parallel=2 patience=5
- stop reason: patience; elapsed 37m47s
- baseline (root) official score: 0.7717
- best node: `n008` official score 0.8189
- held-out `kaggle` seed set: best 0.8034 vs baseline -
- reference scores: solid_public_lb 0.81
- cost: utility: 18 calls, $0.27, 6m50s; worker: 14 calls, $2.19, 2h04m

## Best path

- `root` 0.7717 — baseline: Baseline starter code. Official score: 0.7717.
- `n001` 0.8177 — Gradient boosting + cabin/group features: Switched from logistic regression to LightGBM with cabin deck/num/side, group id/size, categoricals, log1p spends, Age median, and CryoSleep-from-spend. Official validation score 0.81771 (n=1739) vs parent 0.7717 (+0.046). Worker quick-set: 0.80331 vs baseline quick 0.76335.
- `n004` 0.8137 — Group-consistent missing imputation: Added per-frame unique group-mate fill for HomePlanet/Cabin/Destination plus hard deck→planet map (A/B/C/T→Europa, G→Earth) in LightGBM features. Official validation score 0.81369 (n=1739, sem=0.00934) vs parent 0.8177 (Δ−0.00401). Worker's quick-set: 0.80331→0.80732.
- `n006` 0.8166 — Surname and cabin occupancy: Added per-frame LastNameSize and CabinOccupancy to LightGBM features. Official validation score 0.81656 (n=1739, sem=0.00928) vs parent 0.8137; |Δ|=0.00286 within noise. Worker's quick-set: 0.80417 vs untouched parent 0.80732 (Δ=−0.00315).
- `n008` 0.8189 — CryoSleep remaining NA and spend mix: Added CryoSleep NA→True when spend=0 plus LuxuryShare and FoodShopShare in features.py; LightGBM unchanged. Official validation score 0.81886 (n=1739, sem=0.00924) vs parent 0.8166 (Δ+0.00226, within no_change band). Worker quick-set: 0.80748 vs untouched parent 0.80417 (+0.00331).

## All nodes

| id | parent | depth | status | verdict | score | Δparent | title | duration |
|---|---|---|---|---|---|---|---|---|
| root | - | 0 | done | baseline | 0.7717 | - | baseline | - |
| n001 | root | 1 | done | improved | 0.8177 | 0.046 | Gradient boosting + cabin/group features | 5m55s |
| n002 | root | 1 | done | improved | 0.8125 | 0.04083 | CryoSleep-consistent spend imputation + rules | 12m23s |
| n003 | root | 1 | done | improved | 0.8016 | 0.0299 | Group-level transported prior features | 12m10s |
| n004 | n001 | 2 | done | no_change | 0.8137 | -0.00402 | Group-consistent missing imputation | 9m58s |
| n005 | n001 | 2 | done | no_change | 0.8097 | -0.00805 | Surname and cabin occupancy counts | 8m30s |
| n006 | n004 | 3 | done | no_change | 0.8166 | 0.00287 | Surname and cabin occupancy | 8m13s |
| n007 | n006 | 4 | done | no_change | 0.8148 | -0.00172 | Within-group family flag | 6m55s |
| n008 | n006 | 4 | done | no_change | 0.8189 | 0.0023 | CryoSleep remaining NA and spend mix | 8m00s |
| n009 | n004 | 3 | done | no_change | 0.8108 | -0.00288 | CryoSleep remaining NA and spend mix | 6m44s |
| n010 | n002 | 2 | done | no_change | 0.8079 | -0.0046 | Group size, cabin side, within-group sharing | 15m17s |
| n011 | n002 | 2 | done | no_change | 0.8068 | -0.00575 | Luxury vs essential spend and IsChild | 11m34s |
| n012 | n009 | 4 | done | no_change | 0.8154 | 0.0046 | Ablate integer GroupId | 5m29s |
| n013 | n009 | 4 | done | improved | 0.8183 | 0.00748 | F-deck leftover HomePlanet from spend mix | 12m24s |
| n014 | n005 | 3 | done | no_change | 0.8148 | 0.00518 | Group-consistent missing imputation | 7m35s |

## Insights

# Insights (verified across nodes; each line cites the node)

- GBDT on cabin/group + spend features beats linear spend/age/CryoSleep because trees capture non-linear deck/side/cryo and spend-tail interactions. [n001, score 0.8177]
- Forcing CryoSleep=False when any spend>0 removes a real train contradiction (~100 rows) and clarifies the cryo–transport signal. [n001, score 0.8177]
- GroupSize and Deck/Side are strong tabular levers on this task; fixed 500 trees at lr=0.05 already landed in the hypothesized 0.80–0.81 band. [n001, score 0.8177]
- CryoSleep=True always has zero amenity spend, and missing CryoSleep splits by spend like awake vs cryo, so spend-based Cryo imputation aligns features with a hard domain rule. [n002, score 0.8125]
- Under the same cryo/one-hot features, logistic regression gains little (worker quick +0.006) while depth-3 HGB captures spend×planet/deck interactions and drives most of the lift. [n002, score 0.8125]
- Worker same-fold probes show cryo rules add only ~0.001–0.004 once HGB is used on baseline columns, so the booster—not imputation alone—explains most of the jump. [n002, score 0.8125]
- With group-aware CV and zero train/test group overlap, LOO group label priors collapse to the global mean at predict, so they cannot transfer the within-group outcome dependence they encode on train. [n003, score 0.8016]
- Most of the jump from worker quick-set 0.76 to 0.80 came from LightGBM plus GroupSize and group-filled planet/cabin location features, not from GroupTransportedMean. [n003, score 0.8016]
- A fixed predict-time blend of row probabilities toward the in-batch group mean is the only label-free way to use outcome correlation on unseen groups, but fixed weights 0.30/0.50 stayed inside fold noise. [n003, score 0.8016]
- Unique-only group fill plus hard A/B/C/T/G deck→planet cuts HomePlanet NA a lot (worker: 152→49) but ~55% singletons only get the deck map, so location NA-fill has limited leverage. [n004, score 0.8137]
- A worker quick-set lift of +0.004 below fold std (~0.008) did not carry to official validation—treat small quick gains on location imputation as noise unless validation moves. [n004, score 0.8137]
- Destination is mixed in many multi-groups; unique-only Destination fill barely moves score (worker ablation −0.00058) and is not the driver. [n004, score 0.8137]
- Global surname frequency can cancel a useful cabin signal because LightGBM spends splits on name counts that span unrelated groups (corr with GroupSize ~0.35). [n005, score 0.8097]
- CabinOccupancy ≠ GroupSize on many rows (groups split across cabins / missing Cabin), so room-sharing is a distinct co-travel cue from booking-group size. [n005, score 0.8097]
- Global surname frequency is a weak family proxy because many last names span multiple passenger groups, so the count mostly ranks common names and can raise fold variance. [n006, score 0.8166]
- CabinOccupancy is near-redundant with GroupSize (high correlation; occupancy never exceeds group size), so LightGBM gains little from the extra integer once GroupSize is present. [n006, score 0.8166]
- Sharing a last name inside the same group is a clearer family signal than global LastNameSize and was not tested here. [n006, score 0.8166]
- Within-group surname counts add little once GroupSize exists: FamilyInGroup equals GroupSize on most rows (worker: 84.9%, corr 0.830), so trees mostly relearn group size. [n007, score 0.8148]
- A small worker quick lift vs n006 can come from dropping LastNameSize/CabinOccupancy, not from FamilyInGroup itself (worker ablation without it: quick 0.80732 > 0.80603). [n007, score 0.8148]
- Spend composition shares can beat raw amenity magnitudes as signals: luxury share corr with Transported was −0.446 vs −0.275 for raw Spa+VRDeck, and LightGBM used both new shares (ranks 6 and 8). [n008, score 0.8189]
- Combining a small domain fill with composition features can stabilize folds even when the fill alone is weak: cryo-fill-only quick mixed folds/higher std, shares-only had two folds down, both together lifted all five. [n008, score 0.8189]
- Spend-mix shares can rank high in LightGBM splits yet still fail to raise accuracy when five log1p amenity columns already encode the same structure (collinearity). [n009, score 0.8108]
- After spend>0→CryoSleep=False, remaining zero-spend CryoSleep NA looks cryo-like on average but overlaps many awake non-spenders (esp. children), so a blanket True fill stays near noise. [n009, score 0.8108]
- Quick-set gains from cabin side and within-group sharing (~+0.008 worker quick) can fail to transfer to official validation when fold variance also rises (worker quick std 0.00745→0.00909), so treat share flags as provisional until validation confirms. [n010, score 0.8079]
- For depth-3 HGB, cabin side appears to carry most of the quick lift; GroupSize/IsAlone add little once Side is present (worker ablations). [n010, score 0.8079]
- Within-group sharing flags without target encoding still risk acting as noise on held-out validation, similar to prior group-fill/surname dead ends. [n010, score 0.8079]
- Luxury vs essential spend is a real axis (LuxurySpend dominates tree splits), but depth-3 HGB already recovered most of it from the five raw logs, so accuracy barely moves. [n011, score 0.8068]
- IsChild is a true domain fact (Age<13 never spend) but is redundant for shallow HGB once Age and ZeroSpend exist—ablations matched sums-only fold-for-fold. [n011, score 0.8068]
- Linear models harvest the composition (+0.017 worker LR) because they cannot recombine five logs; HGB still wins overall, so shipping LR for this alone is not worth it. [n011, score 0.8068]
- Integer GroupId is largely redundant with CabinNum (worker corr 0.681); after removal, LightGBM shifts splits onto CabinNum and other existing numerics, so accuracy stays flat. [n012, score 0.8154]
- Consecutive gggg groups do not share Deck/Side above chance (worker), so sequential GroupId is not a cabin-block proxy worth keeping as a numeric split feature. [n012, score 0.8154]
- Unique group-mate fill plus A/B/C/T/G→planet cuts location NA a lot (worker: HomePlanet 152→49, Side 164→80) but does not reliably raise LightGBM accuracy once GroupSize/CabinOccupancy exist, because ~55% of rows are singletons and NA itself is already a usable split. [n014, score 0.8148]
- Recomputing CabinOccupancy after filling Cabin changes many rows (worker: 226) and was the weakest occupancy timing on quick folds—reconstructed roommates are a noisier sharing signal than raw missing-cabin occupancy=1. [n014, score 0.8148]
- Leftover F-deck HomePlanet NA is Earth/Mars-separable by spend mix (Mars luxury ~0.15 vs Earth ~0.40; zeros mostly Mars), and filling only those 33 train rows moved official validation +0.00749 despite near-noise quick delta—small targeted location fills can still help holdout. [n013, score 0.8183]
- Spend-mix planet guesses largely duplicate amenity axes LightGBM already sees, so the fill’s ceiling is tiny (33/6954 rows) and can leak Transported signal via HomePlanet. [n013, score 0.8183]
- Unique last-name→planet among known F has perfect group-LOO planet accuracy but still spans unrelated groups, so it is a bad imputation feature even when planet labels look pure. [n013, score 0.8183]

## Dead ends

# Dead ends (do not retry; each line cites the node)

- LogisticRegression on cryo-imputed + one-hot features: worker quick 0.76910 vs 0.76335; C tuning did not help. [n002]
- Raw vs log1p spends under HGB both scored worker quick 0.79655. [n002]
- Depth-4 HGB reached worker quick 0.80061 but raised fold std (0.010 vs 0.007) and was not shipped. [n002]
- LOO GroupTransportedMean / GroupOtherTransportedCount as tree features: worker local ablation 0.80073 (on) vs 0.80163 (off); no reliable gain because predict values are constant. [n003]
- Fixed group-proba blend strength 0.30 or 0.50: worker |delta| ≤ 0.002 vs no blend on the same folds. [n003]
- Group-consistent HomePlanet/Cabin/Destination fill + deck→planet map: official 0.81369 vs parent 0.8177 (Δ−0.00401 within no_change band); does not beat parent on validation. [n004]
- Hard-mapping deck F to Earth was correctly avoided; remaining HomePlanet NA are mostly F (Earth vs Mars), so majority guess is not an almost-hard rule. [n004]
- Frame-wide SurnameFreq with CabinOccupancy: worker quick both 0.80374 ≈ parent quick 0.80331; surname alone mixed folds—do not retry global surname counts. [n005]
- CabinOccupancy alone lifted worker quick (+0.00487) but official validation 0.80966 did not beat parent 0.8177. [n005]
- LastNameSize+CabinOccupancy together: worker quick 0.80417 vs parent 0.80732 (three folds down); official validation flat vs parent. [n006]
- CabinOccupancy alone: worker quick 0.80460 with all five folds down vs parent. [n006]
- LastNameSize alone: worker quick 0.80534 with fold-0 −0.01278 and higher fold std (0.01351 vs parent 0.00812). [n006]
- Integer FamilyInGroup on LightGBM: official 0.81484 vs parent 0.8166 (|Δ|<0.01085); worker's quick also below n004-like ablation (0.80603 vs 0.80732). [n007]
- Cryo remaining-NA→True alone: worker quick 0.80562 vs parent 0.80417 (+0.00145) with mixed folds and std 0.01274—extra cryo rules add little once spend features exist. [n008]
- Adding RoomService share is redundant: on spenders it equals 1−LuxuryShare−FoodShopShare (residual ~2e-16). [n008]
- Cryo zero-spend True fill + continuous Luxury/FoodShopping shares: official 0.81081 vs parent 0.8137; worker quick 0.80718 vs 0.80732. [n009]
- Continuous LuxuryShare+FoodShoppingShare alone: worker same-fold 0.80503 vs parent-like 0.80732 (Δ −0.00229). [n009]
- Full GroupSize+Side+SharesLastName+Shared{HomePlanet,Destination,Deck,CryoSleep} set: official validation 0.80794 vs parent 0.8125 (no meaningful improvement). [n010]
- Worker side-only quick 0.80304 missed their 0.007 bar vs parent quick 0.79655, so shipping side alone was not justified even on quick. [n010]
- Keeping five raw amenity logs plus the two sums (sums+raw): worker quick 0.79918 with higher fold std; collinear and not better than sums-only. [n011]
- Adding IsChild or AgeBin on top of Age/ZeroSpend under depth-3 HGB: identical folds to the matching spend config. [n011]
- Dropping TotalSpend once Luxury+Essential exist: worker quick 0.79859, slightly worse than keeping it. [n011]
- Ablating GroupId alone does not improve the official score beyond noise (0.81541 vs parent 0.8108, |Δ| 0.00461 < 0.009201); worker quick also flat (+0.00043). [n012]
- Shipped stack (unique HomePlanet/Cabin/Destination fill + deck→planet + occupancy-after-fill): worker quick 0.80460 vs parent 0.80818 (4/5 down); official 0.81484 stays within |Δ|<0.008682 of parent 0.8097—no meaningful gain to retry. [n014]
- Fill with occupancy counted on raw Cabin still lost on quick (worker 0.80530); skipping Destination fill (0.80617) or dropping occupancy under fill (0.80732) also stayed below the occupancy-only parent. [n014]
- Unique F-deck last-name→planet fill: worker same-fold quick 0.80475 vs parent quick 0.80718 (Δ −0.00243). [n013]
- Last-name map plus spend-mix LR: official quick 0.80660 vs parent quick 0.80718 (Δ −0.00058); last name was the drag. [n013]
