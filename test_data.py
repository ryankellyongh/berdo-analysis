"""Data preparation, campus rows, and linking buildings across years."""
import pandas as pd

from berdo.data import (
    MissingColumnsError, find_building_in_year, lookup_building_priority, mark_campus_rows,
    normalize_id, prepare_dataframe, standardize_address_series,
)


def _raw(rows):
    """A tiny BERDO-style disclosure with the City's column names."""
    base = {"Building Address": None, "Property Owner Name": "OWNER LLC", "Largest Property Type": "Office",
            "Reported Gross Floor Area (Sq Ft)": 50_000, "Site EUI (Energy Use Intensity kBtu/ft²)": 60,
            "Estimated Total GHG Emissions (kgCO2e)": 300_000, "Reporting Compliance Status": "In Compliance",
            "First Emissions Compliance Year (Projected)": 2025, "BERDO ID": None, "Tax Parcel ID": None,
            "Corresponding Campus ID": None, "Notes": None}
    return pd.DataFrame([{**base, **r} for r in rows])


def test_normalize_id():
    assert normalize_id(100182.0) == "100182" and normalize_id(" C10002 ") == "C10002"
    assert normalize_id(float("nan")) is None and normalize_id("") is None


def test_standardize_address_handles_missing():
    out = standardize_address_series(pd.Series(["500 Boylston Street, Boston", None]))
    assert out.iloc[0] == "500 BOYLSTON ST" and out.iloc[1] == ""


def test_prepare_dataframe_computes_intensity_and_cleans():
    df = prepare_dataframe(_raw([{"Building Address": "1 A St", "BERDO ID": 100001.0}]))
    assert df.loc[0, "ghg_intensity_kgco2e_sqft"] == 6.0
    assert df.loc[0, "berdo_id"] == "100001" and df.loc[0, "compliance_status"] == "in compliance"


def test_prepare_dataframe_reports_missing_columns():
    try:
        prepare_dataframe(pd.DataFrame({"Building Address": ["1 A St"]}))
        assert False, "expected MissingColumnsError"
    except MissingColumnsError as e:
        assert "property_type" in e.missing


def test_campus_summary_and_member_rows():
    df = prepare_dataframe(_raw([
        {"Building Address": "300 Mass Ave", "BERDO ID": "100001", "Corresponding Campus ID": "C10059"},
        {"Building Address": None, "BERDO ID": "C10059"},                           # 2025-style summary
        {"Building Address": "2014 Columbus Ave", "BERDO ID": "106437",
         "Notes": "This is a campus comprised of multiple buildings."},              # 2022-style summary
    ]))
    assert df["is_campus_member"].tolist() == [True, False, False]
    assert df["is_campus_summary"].tolist() == [False, True, True]


def test_search_excludes_campus_totals_and_prefers_exact_match():
    df = prepare_dataframe(_raw([
        {"Building Address": "20 Gillette Park Rear", "BERDO ID": "2"},
        {"Building Address": "20 Gillette Park", "BERDO ID": "1"},
        {"Building Address": "20 Gillette Park Campus", "BERDO ID": "C1", "Notes": "This is a campus of buildings"},
    ]))
    res = lookup_building_priority(df, "20 Gillette Park")
    assert res.iloc[0]["BERDO ID"] == "1" and "C1" not in res["BERDO ID"].tolist()


def test_year_linking_uses_berdo_id_when_address_changes():
    y2024 = prepare_dataframe(_raw([{"Building Address": "761 harrison av", "BERDO ID": "100233"}]))
    row, method, dup = find_building_in_year(y2024, "100233", None, "761 Harrison Ave")
    assert method == "BERDO ID" and row["Building Address"] == "761 harrison av"


def test_year_linking_prefers_record_with_emissions_when_duplicated():
    y = prepare_dataframe(_raw([
        {"Building Address": "150 Mass Ave", "BERDO ID": "7", "Estimated Total GHG Emissions (kgCO2e)": None},
        {"Building Address": "150 Mass Ave", "BERDO ID": "7"},
    ]))
    row, method, dup = find_building_in_year(y, "7")
    assert dup and pd.notna(row["ghg_intensity_kgco2e_sqft"])


def test_2021_style_parcel_fallback_only_when_one_building():
    y2021 = prepare_dataframe(_raw([
        {"Building Address": "1 A St", "Tax Parcel ID": "P1"},
        {"Building Address": "2 B St", "Tax Parcel ID": "P2"},
        {"Building Address": "3 B St", "Tax Parcel ID": "P2"},
    ]))
    assert find_building_in_year(y2021, "999", "P1", "1 A St")[1] == "Tax parcel"
    assert find_building_in_year(y2021, "999", "P2", "3 B St")[1] == "Tax parcel + address"
    assert find_building_in_year(y2021, "999", None, None) is None
