# BERDO Priority Screening Tool

A web app that helps Boston building owners, property managers, and City outreach staff
understand the **Building Emissions Reduction and Disclosure Ordinance (BERDO)**: whether a
building is on track, what it may owe if it isn't, and what it can do about it, using the
City of Boston's public data.

**Live app:** https://berdo-priority-screening-tool.streamlit.app/

> **Screening tool, not an official City of Boston determination.** Results are estimates
> from public data and may differ from the City's assessment. Not financial, legal, or tax advice.

---

## What it does

BERDO requires larger Boston buildings to report energy use and emissions every year. Starting
with 2025 emissions, buildings of 35,000 sq ft or more (or 35+ units) must stay under emissions
limits that tighten every five years and reach zero in 2050; smaller covered buildings
(20,000–35,000 sq ft, or 15–34 units) begin in 2030. Emissions above the limit can be met with an
**Alternative Compliance Payment (ACP)** of $234 per metric ton of CO₂e.

The app answers, for any covered building:

1. Is it covered, and has it reported?
2. How do its emissions compare with its limit, now and in each future period?
3. What would it owe, and how much would a project save?
4. For buildings the City hasn't scored yet, how likely is it to need action?

### Pages

| Page | What it shows |
|---|---|
| **Citywide Overview** *(access code)* | Reporting and emissions status for every covered building, a map, counts by building category, and the **2025 Outlook** (saved predictions) |
| **Address Lookup** | One building's evidence, limits by period, estimated ACP, year-over-year trend, compliance pathways, and a one-page PDF summary |
| **Owner Portfolio** | Buildings that share an owner name, with a blended standard. Name matches are candidates until ownership is confirmed |
| **Retrofit & Incentives** | Cost ranges, a planned project's effect, avoided ACP, payback, renewable energy credits (RECs), and incentive programs to investigate |
| **Emissions Planner** | Year-by-year emissions and ACP with planned projects |
| **About** | Purpose, methods, sources, and limits |

A **reporting year** contains the previous calendar year's energy use (reporting year 2026 = 2025
emissions, the first compliance year).

### How the numbers work

- **ACP** = $234 × metric tons of CO₂e above the building's limit. Nothing is rounded before the
  compliance test.
- **Avoided ACP** = baseline ACP minus the ACP still owed after a project. Payback uses avoided ACP
  plus energy savings, never the whole baseline ACP.
- **N/A** means a value can't be estimated (missing data, not yet covered, or not assessed). It never
  means $0.
- **Incentives** are shown as programs to investigate. Only *confirmed* funding reduces net cost.
- **Grid decarbonization** (optional) scales only the electricity part of each building's emissions,
  using the building's own reported energy mix and the City's projected grid factors.
- Where the City publishes an official standard or status (2026 onward), the app uses it.

---

## Data

| Source | Use |
|---|---|
| City of Boston BERDO disclosures, reporting years 2021–2026 (Analyze Boston) | Building records, emissions, reporting and compliance status |
| BERDO 2.0 emissions standards and BERDO Emissions Factors List | Limits, ACP rate, grid and fuel factors |
| City of Boston Street Address Management (SAM) addresses | Map locations |

Data notes:

- The 2026 file is the City's **September 30, 2026 provisional release**. Results for buildings
  under review or still reporting were not yet published.
- In that release, the **Site EUI column duplicates GHG intensity** in all 1,809 records with both
  values. Site EUI is recalculated from total site energy ÷ floor area (`convert_berdo_2026.py`).
- The 2026 file has **5,514 buildings plus 77 campus records** (whole-campus totals, IDs starting
  with "C"). Campus records are counted separately, never added to building counts.
- About 99% of buildings are mapped (earlier geocoded data plus SAM address matches).

---

## Predicting results the City hasn't published

The City had not published 2025 results for **1,359 covered buildings**. The model estimates which
are likely to be marked **"Action Needed."** Full details: `analysis/predictions_2026/README.md`.

- **Main feature:** last year's emissions, restated at the 2025 grid factor, divided by the
  building's 2025–29 limit.
- **Model:** logistic regression adding electricity share, size, mixed use, and City ownership.
- **Training:** 809 buildings with a City result (47 Action Needed, 5.8%).
- **Testing:** 5-fold cross-validation repeated 20 times.

| Result | Value |
|---|---|
| ROC AUC | 0.91 (95% bootstrap interval 0.84–0.96) |
| Average precision | 0.55 (baseline 0.058) |
| Top 50 buildings contacted | Model finds 30 Action Needed; simple rule finds 23 |
| 130+ contacted | Simple rule finds slightly more (43 vs. 40) |

**Limitations:** only 47 positive cases; trained on on-time reporters but applied to late reporters
and buildings under review; probabilities run too low in the 30–60% range (about 41% predicted vs.
66% observed); assumes 2025 emissions resemble the previous year's.

**Pre-registered test:** predictions were saved on **October 9, 2026**, with a SHA-256 fingerprint
(`prediction_hash.txt`). When the City publishes updated results, run
`python analysis/predictions_2026/check_after_update.py path/to/updated_2026.csv`.

**Data-use policy:** building-level predictions are shown only behind the access code and to owners
for their own buildings; small counts are suppressed; buildings under City review are never labeled
individually.

---

## Repository layout

| Path | Contents |
|---|---|
| `app.py` | Streamlit entry point: loads data, builds the shared page context, lays out the tabs. No calculations |
| `site_theme.py` | Website styling: header, tabs, cards, footer |
| `berdo/` | All rules and calculations (no Streamlit): standards, emissions, data preparation, portfolio, retrofit, predictions, PDF export |
| `ui/` | One module per tab; displays what `berdo/` calculates |
| `data/` | City disclosure files (`berdo_<year>.csv`), coordinates, and source spreadsheets |
| `analysis/predictions_2026/` | Prediction features, evaluation, saved predictions, and fingerprint |
| `tests/` | Tests for official values and calculation rules |
| `convert_berdo_2026.py` | Converts the City's 2026 spreadsheet to `data/berdo_2026.csv` |
| `.github/workflows/` | Workflow that visits the app every 6 hours so it doesn't sleep |
| `DEVELOPING.md` | Developer notes |

Rule of thumb: if it's a number or a rule, it belongs in `berdo/` and should have a test.

---

## Running locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

The Citywide Overview needs an access code. Create `.streamlit/secrets.toml` (never commit it):

```toml
CITY_ACCESS_CODE = "your-code"
```

Theme settings go in `.streamlit/config.toml`.

### Tests

```bash
python run_tests.py                 # runs everything in tests/
pytest                              # if requirements-dev.txt is installed
python check_function_coverage.py   # which berdo/ functions the tests exercise
python analysis/predictions_2026/evaluate.py   # reproduces the model results above
```

---

## Updating for a new year of data

1. Save the City's disclosure as `data/berdo_<reporting year>.csv` (convert the 2026-format
   spreadsheet with `convert_berdo_2026.py`). Only files named exactly `berdo_<year>.csv` are loaded.
2. Run the app. If it reports missing columns, add the City's new column name to
   `CITY_COLUMN_NAMES` in `berdo/schema.py`.
3. Run the tests.

---

## Deployment notes (Streamlit Community Cloud)

- Main file: `app.py`, branch `main`. Secrets (`CITY_ACCESS_CODE`) are set in the app's settings.
- `requirements.txt` pins **`streamlit==1.57.0`** and **`starlette<1.8`**. Starlette 1.8+
  (October 13, 2026) breaks Streamlit's compressed file serving, which shows up in the browser as
  "Failed to fetch dynamically imported module."
- After changing requirements or imported modules, **reboot** the app (Manage app → ⋮ → Reboot).

---

## Known issues and next steps

- Move `config.toml` into `.streamlit/` so the theme applies.
- Replace `use_container_width` with `width="stretch"` (deprecated in recent Streamlit).
- Move median imputation inside the cross-validation pipeline (`SimpleImputer`).
- Recalibrate predicted probabilities and report calibration curves.
- Score the October 9 predictions when the City publishes updated 2026 results.
- Interview owners, consultants, and City staff to validate the users and their needs; early
  feedback suggests owners expect a 3–5 year payback, which current incentives often don't reach.
