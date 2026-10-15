# Supplied competition columns

S6E10 tabular airline satisfaction: 699,635 supplied labeled rows and 299,844 unlabeled competition-test rows. Only the frozen training pool is available for model development. Numeric target `satisfaction` takes exactly 0 and 1; output probability of observed label 1. `id` is unique and used only for output alignment, **not prediction**.

| Columns | Interpretation / baseline handling |
|---|---|
| Age | Passenger age; numeric |
| Flight Distance | Trip distance; numeric |
| Inflight wifi service | Ordinal service rating |
| Departure/Arrival time convenient | Schedule convenience rating |
| Ease of Online booking | Booking rating |
| Gate location | Gate rating |
| Food and drink | Catering rating |
| Online boarding | Boarding rating |
| Seat comfort | Seat rating |
| Inflight entertainment | Entertainment rating |
| On-board service | On-board rating |
| Leg room service | Legroom rating |
| Baggage handling | Baggage rating |
| Checkin service | Check-in rating |
| Cleanliness | Cleanliness rating |
| Departure Delay in Minutes | Departure delay; numeric |
| Arrival Delay in Minutes | Arrival delay; numeric, preserve missing as NaN |
| Gender | Native categorical: Female / Male |
| Customer Type | Native categorical: Loyal Customer / disloyal Customer |
| Type of Travel | Native categorical: Business travel / Personal Travel |
| Class | Native categorical: Business / Eco / Eco Plus |

Public training-pool inspection: 204 missing arrival-delay values, no missing values in other columns. Service ratings observed as integer levels 0–5 (Baggage handling 1–5). Do not assume that rating zero is missing; it is an observed numeric level. The baseline keeps all ratings numeric, converts categorical missing values to a sentinel, and uses CatBoost's native handling of numeric NaN. No scaler/imputer/encoder is learned from prediction rows.

The sample submission is `id,satisfaction` aligned with test IDs. Its constant placeholder probability is a format example, not a label or reference solution. Test/sample files are useful only for schema/output checks; no Kaggle submission, leaderboard lookup or additional data. Avoid claiming undocumented measurement units beyond the supplied column names.

All split/source SHA-256 values, counts and ordered-ID hashes are frozen in the manifests. See PROTOCOL.md for which paths are worker-visible and prohibited.
