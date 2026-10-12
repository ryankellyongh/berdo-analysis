# Predicting 2025 compliance results the City hasn't published yet

The City's 2026 BERDO disclosure (2025 energy use, the first compliance year) is provisional.
Of 5,591 buildings, 3,782 have no emissions data yet. This analysis predicts, from each
building's **earlier-year data only**, which buildings without a published result are likely
to be marked **Action Needed**, and tests that prediction against results the City has published.

## Files

| File | What it does |
|---|---|
| `build_features.py` | Builds one row per building from its most recent earlier record (2024 or 2023 energy use) |
| `evaluate.py` | Tests the approach on the 809 buildings that already have a City result |
| `predict.py` | Trains the final model and scores buildings without a result |
| `predictions_2026_pending.csv` | The saved predictions |
| `prediction_hash.txt` | Fingerprint (SHA-256) of the predictions file, to show it hasn't changed |
| `check_after_update.py` | Scores the saved predictions when the City publishes updated results |

Run from the repository root, in order: `build_features.py`, `evaluate.py`, `predict.py`.

## Method

For each building, last year's emissions are restated at the 2025 grid factor (same energy
use, cleaner grid) and compared with its 2025–29 limit. A logistic regression adds four
building traits: electricity share, size, mixed use, and City ownership. Buildings are also
placed in three tiers by how last year's emissions compare with the limit:

- **Likely over:** above the limit
- **Watch:** within 10% of the limit
- **Likely compliant:** more than 10% under

## How well it works (buildings with a published result, earlier-year data only)

| Tier | Buildings | Turned out Action Needed |
|---|---|---|
| Likely over | 88 | 35 (40%) |
| Watch | 45 | 8 (18%) |
| Likely compliant | 676 | 4 (0.6%) |

- The tiers find **43 of 47** Action Needed buildings (Likely over plus Watch), and a
  "Likely compliant" building ends up Action Needed less than 1% of the time.
- Ranking accuracy (cross-validated AUC): **0.91**. The model's added value over the tiers
  is a probability for each building, not more buildings caught.
- The misses were mostly multifamily buildings just under their limit that crossed it in 2025,
  and two buildings whose emissions jumped sharply (likely occupancy or data changes).

## Predictions for buildings without a result

| Group | Buildings | With earlier data | Likely over | Watch | Expected Action Needed |
|---|---|---|---|---|---|
| Pending Reporting (covered in 2025) | 1,110 | 530 | 97 | 39 | about 50 to 65 |
| Under City review | 249 | 243 | 66 | 15 | about 30 |

The two estimates come from the model's probabilities and from the tier rates above; the
model runs slightly high for low-risk buildings. 580 pending buildings have no earlier
emissions data and can't be predicted individually.

ZIP codes with the most at-risk buildings: 02119, 02215, 02115, 02135, 02118, 02134.

## Limitations

- **Late reporters may differ.** The model learns from buildings that reported on time.
  Buildings that report late, or are under review, may be more likely to have problems,
  so these estimates could be low.
- **Under City review:** the City says these buildings are not considered out of compliance
  while under review.
- **Small number of examples:** only 47 Action Needed buildings to learn from.
- **One year of change:** predictions assume 2025 emissions resemble the previous year's.
- This is a screening estimate, not a City determination.

## Validation plan

The predictions were saved before the City's planned update after October 15, 2026. When the
update is published, `check_after_update.py` scores them against the new results. The commit
date on GitHub and the fingerprint in `prediction_hash.txt` show the predictions were made first
and not changed afterward.

## A correction to earlier materials

Earlier summaries said the app "flagged all 49 Action Needed buildings." That comparison used
each building's 2025 data, the same data the City used, so it shows the app applies the rules
the way the City does. It is not a prediction. The predictive result is above: from the
previous year's data alone, the tiers flagged 43 of 47.
