"""
Convert the City's 2026 BERDO disclosure (2025 data) into data/berdo_2026.csv
in the column layout app.py already expects.

Usage:
    python convert_berdo_2026.py 2026-berdo-data-disclosure-9_30_26.xlsx data/berdo_2026.csv

The 2026 file differs from earlier years in ways that break _load_single_csv:
  - it is a multi-sheet .xlsx (building rows are on "Buildings & Campuses")
  - four required headers were renamed
  - "Not Submitted" is now "Not Reported"
  - BERDO ID mixes ints (buildings) and "C....." strings (campus rows)
  - First Emissions Compliance Year can be the text "Exempt During Vacancy"
  - Site EUI duplicates GHG intensity in the source; it is recalculated here
New official columns are kept: the City's 2025–29 standard (per sq ft and,
for Individual Compliance Schedules, absolute kg), emissions compliance status,
flexibility measures, and "All Property Types and GFAs (sq ft)", which app.py
uses to estimate later-period limits for Blended Emissions Standards.
"""
import sys
import pandas as pd

SHEET = "Buildings & Campuses"

# 2026 header -> header app.py's COLUMN_RENAME_MAP / REQUIRED_COLUMNS expects
LEGACY_HEADERS = {
    "Parcel Owner Name":               "Property Owner Name",
    "Gross Floor Area (sq ft)":        "Reported Gross Floor Area (Sq Ft)",
    "Total GHG Emissions (kgCO2e)":    "Estimated Total GHG Emissions (kgCO2e)",
    "First Emissions Compliance Year": "First Emissions Compliance Year (Projected)",
}

# Official fields worth carrying through, renamed to snake_case
OFFICIAL_EXTRAS = {
    "BERDO ID":                                                "berdo_id",
    "Electricity Emissions (kgCO2e)":                          "elec_emissions_kg",
    "Renewable Electricity Usage (kWh)":                       "renewable_elec_kwh",
    "Applicable Emissions Compliance Standard (kgCO2e/sq ft)": "official_standard_2025",
    "Emissions Compliance Status":                             "official_emissions_status",
    "Flexibility Measures":                                    "flexibility_measures",
    "Applicable Emissions Compliance Standard for Individual Compliance Schedules (kg CO2e)":
                                                               "official_ics_limit_kg",
    "Corresponding Campus ID":                                 "campus_id",
    "Corresponding Portfolio ID":                              "portfolio_id",
}


def convert(src: str, dst: str) -> pd.DataFrame:
    df = pd.read_excel(src, sheet_name=SHEET)

    missing = [c for c in [*LEGACY_HEADERS, *OFFICIAL_EXTRAS] if c not in df.columns]
    if missing:
        raise SystemExit(f"Unexpected layout, missing columns: {missing}")

    df = df.rename(columns={**LEGACY_HEADERS, **OFFICIAL_EXTRAS})

    df["berdo_id"] = df["berdo_id"].astype(str)
    df["is_campus_row"] = df["berdo_id"].str.startswith("C")

    # 376 rows have no Building Address; fall back to the assessor's address
    df["address_from_parcel"] = df["Building Address"].isna()
    df["Building Address"] = df["Building Address"].fillna(df["Parcel Address"])

    df["Reporting Compliance Status"] = df["Reporting Compliance Status"].replace(
        {"Not Reported": "Not Submitted"}
    )

    #Data-quality fix: in the 9/30/26 release the City's "Site EUI" column is a copy of
    #"GHG Emissions Intensity" (identical in all 1,809 records that have both). Rebuild
    #Site EUI from Total Site Energy Usage / floor area, keep the published value for
    #audit, and record which value is shown.
    eui_col = "Site EUI (Energy Use Intensity kBtu/ft²)"
    energy, area = df["Total Site Energy Usage (kBtu)"], df["Reported Gross Floor Area (Sq Ft)"]
    df["site_eui_as_published"] = df[eui_col]
    calc = (energy / area).where((area > 0) & energy.notna())
    df[eui_col] = calc.round(1)
    df["site_eui_source"] = calc.notna().map({True: "Calculated: total site energy / floor area",
                                               False: "Unavailable"})

    col = "First Emissions Compliance Year (Projected)"
    df["vacancy_exempt"] = df[col].astype(str).str.contains("Vacancy", na=False)
    df[col] = pd.to_numeric(df[col], errors="coerce")

    df.to_csv(dst, index=False)
    return df


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "2026-berdo-data-disclosure-9_30_26.xlsx"
    dst = sys.argv[2] if len(sys.argv) > 2 else "data/berdo_2026.csv"
    out = convert(src, dst)
    print(f"Wrote {len(out):,} rows to {dst}")
    print(f"  with GHG data: {out['Estimated Total GHG Emissions (kgCO2e)'].notna().sum():,}")
    print(f"  campus rows:   {out['is_campus_row'].sum():,}")
