# BERDO Priority Screening Tool: developer notes

## Layout

| File | What it holds | Uses Streamlit? |
|---|---|---|
| `app.py` | The interface: tabs, widgets, charts, page layout, cached data loading | Yes |
| `berdo/regulations.py` | Official tables: emissions standards, ACP rate, grid factors, RPS, fuel factors, building-use map, links, deadlines, REC prices, incentives, sources register | No |
| `berdo/emissions.py` | Calculations: limits, blended standards, coverage, compliance gaps, screening status, grid projections, RECs, compliance pathways, Emissions Planner model | No |
| `berdo/data.py` | Preparing and searching the City's data: column mapping, IDs, campus rows, address matching, year-to-year linking, lookups | No |
| `berdo/pdf_export.py` | The one-page PDF summary | No |
| `tests/` | Tests for official values and calculation rules | No |

Rule of thumb: if it's a number or a rule, it belongs in `berdo/` and should have a test.
`app.py` should only display what `berdo/` calculates.

## Running tests

    python run_tests.py        # no extra installs needed
    pytest                     # if you've installed requirements-dev.txt

## Updating official values

When the City publishes new documents:

1. Update the table in `berdo/regulations.py` (e.g. `PROJECTED_GRID_EF`, `FUEL_EF_KG_PER_KBTU`, `REC_CONNECTOR_TIERS`).
2. Update the matching test in `tests/test_regulations.py` to the new official values.
3. Update the row in `SOURCES_REGISTER` with the source and date.
4. Run the tests.

Known dates to watch:
- REC Connector prices are valid through December 31, 2026.
- The ACP rate is reviewed every five years by the Review Board.
- Grid projections are reviewed before the 2030 compliance period.

## Data notes

- Each dataset is labeled by reporting year and covers the previous calendar year's energy use.
- Years are linked by BERDO ID (2022 onward); 2021 falls back to tax parcel, then exact address.
- Campus summary rows (whole-campus totals) are excluded from searches.
