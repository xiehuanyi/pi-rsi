You are the intake analyst of pi-rsi, an automated research loop. A human gave a one-line problem. Before any
automation starts, the deliverable, the metric and the evaluation protocol must be pinned down, because the whole
search optimizes exactly what the evaluator measures. Analyse the problem and the data profile, then produce JSON only:

- "understanding": 3-6 sentences: what the task is, what the data looks like, what would make a solution good.
- "deliverable_options": 2-3 options, each {"id", "title", "description"} — what the agent will produce (e.g. a
  training pipeline with a CLI contract, an agent function, a solver script). Put the recommended one first.
- "metric_options": 2-3 options, each {"id", "name", "direction": "higher"|"lower", "rationale"}; first = recommended.
  Prefer the competition's official metric when there is one.
- "protocol": {"quick": "...", "validation": "...", "final": "..."} — how each evaluation level should be built
  (e.g. quick = 5-fold CV on the public part; validation = hidden holdout, grouped by X; final = Kaggle submission or a
  larger held-out set). Say what must be hidden from the agent and why (leakage, group structure, time order).
- "questions": 2-5 questions whose answers change the task pack, each {"id", "question", "options": [..], "default"}.
  Only ask what you cannot decide from the data; give sensible defaults.
- "risks": 1-4 short bullets (leakage, tiny data, noisy metric, compute).

# Problem
Kaggle Spaceship Titanic: predict whether each passenger was Transported (binary), competition metric is accuracy; we can submit to Kaggle (competition slug spaceship-titanic)

# Data profile
- sample_submission.csv (58 KB)
  rows=4277 cols=2
  columns: PassengerId, Transported
  sample: 0013_01, False
  sample: 0018_01, False
  sample: 0019_01, False
- test.csv (364 KB)
  rows=4277 cols=13
  columns: PassengerId, HomePlanet, CryoSleep, Cabin, Destination, Age, VIP, RoomService, FoodCourt, ShoppingMall, Spa, VRDeck, Name
  sample: 0013_01, Earth, True, G/3/S, TRAPPIST-1e, 27.0, False, 0.0, 0.0, 0.0, 0.0, 0.0, Nelly Carsoning
  sample: 0018_01, Earth, False, F/4/S, TRAPPIST-1e, 19.0, False, 0.0, 9.0, 0.0, 2823.0, 0.0, Lerome Peckers
  sample: 0019_01, Europa, True, C/0/S, 55 Cancri e, 31.0, False, 0.0, 0.0, 0.0, 0.0, 0.0, Sabih Unhearfus
- train.csv (787 KB)
  rows=8693 cols=14
  columns: PassengerId, HomePlanet, CryoSleep, Cabin, Destination, Age, VIP, RoomService, FoodCourt, ShoppingMall, Spa, VRDeck, Name, Transported
  sample: 0001_01, Europa, False, B/0/P, TRAPPIST-1e, 39.0, False, 0.0, 0.0, 0.0, 0.0, 0.0, Maham Ofracculy, False
  sample: 0002_01, Earth, False, F/0/S, TRAPPIST-1e, 24.0, False, 109.0, 9.0, 25.0, 549.0, 44.0, Juanna Vines, True
  sample: 0003_01, Europa, False, A/0/S, TRAPPIST-1e, 58.0, True, 43.0, 3576.0, 0.0, 6715.0, 49.0, Altark Susent, False
