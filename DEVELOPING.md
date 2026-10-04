# BERDO Priority Screening Tool: developer notes

## Layout

| File | What it holds | Uses Streamlit? |
|---|---|---|
| `app.py` | Page setup, cached data loading, sidebar, and the four tabs | Yes |
| `ui/address_lookup.py` | Address Lookup tab | Yes |
| `ui/portfolio.py` | Owner Portfolio tab | Yes |
| `ui/retrofit.py` | Retrofit & Incentives tab | Yes |
| `ui/planner.py` | Emissions Planner tab | Yes |
| `ui/common.py` | Small helpers shared by the tabs | Yes |
| `berdo/regulations.py` | Official tables: standards, ACP rate, grid factors, RPS, fuel factors, building-use map, links, deadlines, REC prices, incentives, units, sources register | No |
| `berdo/schema.py` | The City's column names, by field | No |
| `berdo/emissions.py` | Rules and calculations, including the City's official statuses and the Emissions Planner model | No |
| `berdo/data.py` | Preparing and searching the City's data | No |
| `berdo/portfolio.py` | Building Portfolio calculations: included buildings, blended standard, ACP exposure, per-building gaps | No |
| `berdo/retrofit.py` | Retrofit calculations: cost estimate, project impact, incentives, net cost, payback, ACP schedule, recommendation | No |
| `berdo/pdf_export.py` | The one-page PDF summary | No |
| `tests/` | Tests for official values and calculation rules | No |

Rule of thumb: if it's a number or a rule, it belongs in `berdo/` and should have a test.
The `ui/` files only display what `berdo/` calculates.

Each layer only uses the layers below it: `regulations` and `schema` -> `emissions` -> `data`, `portfolio`, `retrofit`, and `pdf_export` -> `ui` -> `app.py`.

The `ui/` files contain no ACP or emissions calculations; they call `berdo/` and format the results.

## Running tests

    python run_tests.py                 # no extra installs needed
    pytest                              # if you've installed requirements-dev.txt
    python check_function_coverage.py   # which berdo/ functions the tests exercise

Expected values in the tests are worked out by hand in comments next to each test,
so a failure means either the code or the official numbers changed. Every function
in `berdo/` should be exercised; add a test with each new function.

## Updating for a new year of data

1. Convert the City's "Buildings & Campuses" sheet to `data/berdo_<reporting year>.csv`.
2. Run the app. If it reports missing columns, the City renamed something: add the new name to that field's list in `CITY_COLUMN_NAMES` (`berdo/schema.py`).
3. Add a test for any new name in `tests/test_2026.py` (or a new test file).
4. Run the tests.

The app reads each file's energy-use year from its electricity emissions and warns in the sidebar if a file name doesn't match.

## Updating official values

1. Update the table in `berdo/regulations.py` (for example `PROJECTED_GRID_EF`, `FUEL_EF_KG_PER_KBTU`, `REC_CONNECTOR_TIERS`).
2. Update the matching test in `tests/test_regulations.py`.
3. Update the row in `SOURCES_REGISTER` with the source and date.
4. Run the tests.

Dates to watch:
- REC Connector prices are valid through December 31, 2026.
- The ACP rate is reviewed every five years by the Review Board.
- Grid projections are reviewed before the 2030 compliance period.
- The City plans to update the provisional 2026 disclosure after October 15, 2026.

## Data notes

- Each dataset is labeled by reporting year and covers the previous calendar year's energy use.
- Years are linked by BERDO ID (2022 onward); 2021 falls back to tax parcel, then exact address.
- Campus summary rows (whole-campus totals) are excluded from searches.
- From 2026, the City's emissions compliance status takes precedence over the tool's own screening.
- The 2026 Site EUI column repeats GHG intensity for most buildings, so Site EUI is recalculated from total energy.
