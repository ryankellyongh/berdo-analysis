"""File years, owner search, campus totals, and fuel breakdown."""
import pandas as pd

from berdo.emissions import effective_grid_ef
from berdo.data import (
    add_year_file, campus_context, get_fuel_breakdown, lookup_owner_portfolio, prepare_dataframe,
    year_from_filename,
)


def test_year_from_filename():
    assert year_from_filename("berdo_2026.csv") == 2026
    assert year_from_filename("berdo_2026_v2.csv") == 2026
    assert year_from_filename("portfolios_2026.csv") is None
    assert year_from_filename("berdo.csv") is None


def _with_electricity(energy_year, n=80):
    kwh = [200_000 + 1000 * i for i in range(n)]
    return pd.DataFrame({"fuel_electricity_kwh": kwh,
                         "elec_emissions_kg": [k / 1000 * effective_grid_ef(energy_year) for k in kwh]})


def test_misnamed_file_gets_the_year_its_data_covers():
    m = add_year_file({}, "berdo_2025.csv", 2025, _with_electricity(2025))   # 2025 energy use -> reporting 2026
    assert list(m) == [2026] and m[2026]["data_year"].iat[0] == 2025


def test_duplicate_file_keeps_the_correctly_named_one():
    m = add_year_file({}, "berdo_2025.csv", 2025, _with_electricity(2025))
    m = add_year_file(m, "berdo_2026.csv", 2026, _with_electricity(2025))
    assert m[2026]["source_file"].iat[0] == "berdo_2026.csv"
    assert m[2026]["duplicate_file"].iat[0] == "berdo_2025.csv"


def test_duplicate_file_either_order():
    # Files load in name order, so the correctly named file can come first or second
    m = add_year_file({}, "berdo_2026.csv", 2026, _with_electricity(2025))
    m = add_year_file(m, "berdo_2027.csv", 2027, _with_electricity(2025))    # misnamed copy loads second
    assert list(m) == [2026]
    assert m[2026]["source_file"].iat[0] == "berdo_2026.csv"
    assert m[2026]["duplicate_file"].iat[0] == "berdo_2027.csv"


def test_file_without_electricity_uses_its_name():
    m = add_year_file({}, "berdo_2023.csv", 2023, pd.DataFrame({"x": [1]}))
    assert list(m) == [2023] and m[2023]["data_year"].iat[0] == 2022


def _raw(rows):
    base = {"Building Address": "1 A St", "Property Owner Name": "OWNER LLC", "Largest Property Type": "Office",
            "Reported Gross Floor Area (Sq Ft)": 50_000, "Site EUI (Energy Use Intensity kBtu/ft²)": 60,
            "Estimated Total GHG Emissions (kgCO2e)": 300_000, "Reporting Compliance Status": "In Compliance",
            "First Emissions Compliance Year (Projected)": 2025, "BERDO ID": None, "Tax Parcel ID": None,
            "Corresponding Campus ID": None, "Notes": None}
    return prepare_dataframe(pd.DataFrame([{**base, **r} for r in rows]))


def test_owner_search_is_case_insensitive_and_skips_campus_totals():
    df = _raw([{"Property Owner Name": "Acme Holdings LLC", "BERDO ID": "1"},
               {"Property Owner Name": "ACME HOLDINGS LLC", "BERDO ID": "2", "Building Address": "2 B St"},
               {"Property Owner Name": "ACME HOLDINGS LLC", "BERDO ID": "C9", "Notes": "This is a campus of buildings"},
               {"Property Owner Name": "Other Owner", "BERDO ID": "3"}])
    res = lookup_owner_portfolio(df, "acme")
    assert sorted(res["BERDO ID"]) == ["1", "2"]
    assert lookup_owner_portfolio(df, "nobody") is None


def test_campus_context_totals():
    df = _raw([{"BERDO ID": "10", "Corresponding Campus ID": "C1", "Reported Gross Floor Area (Sq Ft)": 40_000},
               {"BERDO ID": "11", "Corresponding Campus ID": "C1", "Building Address": "2 B St"},
               {"BERDO ID": "C1", "Building Address": None, "Reported Gross Floor Area (Sq Ft)": 100_000,
                "Estimated Total GHG Emissions (kgCO2e)": 700_000}])
    ctx = campus_context(df, "C1")
    assert len(ctx["members"]) == 2
    assert ctx["summary"]["intensity"] == 7.0                                      # 700,000 / 100,000
    assert campus_context(df, None) is None


def test_fuel_breakdown_shares():
    row = {"fuel_natural_gas_kbtu": 3412, "fuel_electricity_kwh": 1000}            # 1,000 kWh = 3,412 kBtu
    labels = {label: round(pct) for label, _, pct in get_fuel_breakdown(row)}
    assert labels == {"Natural gas": 50, "Electricity": 50}
    assert get_fuel_breakdown({}) == []
