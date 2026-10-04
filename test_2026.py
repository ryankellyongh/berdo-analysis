"""
The 2026 disclosure (2025 energy use): new column names, the City's official
emissions results, year detection, and the Site EUI correction.
"""
import pandas as pd

from berdo.regulations import ACP_RATE
from berdo.schema import COLUMN_RENAME_MAP
from berdo.emissions import effective_grid_ef, fuel_to_kbtu
from berdo.data import detect_data_year, evaluate_building, lookup_result_row, prepare_dataframe


def _raw2026(rows):
    """A tiny disclosure using the City's 2026 column names."""
    base = {"BERDO ID": "100001", "Parcel Owner Name": "OWNER LLC", "Building Address": "1 A St",
            "Gross Floor Area (sq ft)": 100_000, "Largest Property Type": "Office",
            "All Property Types and GFAs (sq ft)": None, "Total Site Energy Usage (kBtu)": 6_000_000,
            "Site EUI (Energy Use Intensity kBtu/ft²)": 5.0,      # the City's column holds GHG intensity
            "Total GHG Emissions (kgCO2e)": 500_000, "Reporting Compliance Status": "In Compliance",
            "Emissions Compliance Status": None, "Applicable Emissions Compliance Standard (kgCO2e/sq ft)": 5.3,
            "Flexibility Measures": None, "First Emissions Compliance Year": 2025,
            "Corresponding Campus ID": None, "Corresponding Portfolio ID": None}
    return prepare_dataframe(pd.DataFrame([{**base, **r} for r in rows]).assign(data_year=2025))


def test_2026_column_names_map_to_tool_fields():
    for city, field in {"Parcel Owner Name": "Property Owner Name", "Gross Floor Area (sq ft)": "gross_floor_area",
                        "Total GHG Emissions (kgCO2e)": "ghg_emissions", "First Emissions Compliance Year": "compliance_year",
                        "Emissions Compliance Status": "emissions_status"}.items():
        assert COLUMN_RENAME_MAP[city] == field
    # older names still work
    assert COLUMN_RENAME_MAP["Reported Gross Floor Area (Sq Ft)"] == "gross_floor_area"


def test_site_eui_recalculated_from_total_energy():
    df = _raw2026([{}])
    assert df.loc[0, "site_eui"] == 60.0          # 6,000,000 kBtu / 100,000 sq ft, not the City's 5.0
    assert bool(df.loc[0, "site_eui_calculated"])


def test_state_moves_from_emissions_status_to_one_rule():
    df = _raw2026([{"Emissions Compliance Status": "State"}])
    assert df.loc[0, "compliance_status"] == "state"
    assert evaluate_building(df.iloc[0])[1] == "Not assessed (state)"


def _status(**kw):
    df = _raw2026([kw])
    return evaluate_building(df.iloc[0])


def test_city_status_in_compliance():
    _, status, acp, notes = _status(**{"Emissions Compliance Status": "In Compliance"})
    assert status == "Meets 2025 limit (City)" and acp == 0


def test_city_status_action_needed_uses_city_standard():
    # 6.0 kg/sf vs. the City's 5.3 standard on 100,000 sq ft -> 70 t excess
    _, status, acp, notes = _status(**{"Emissions Compliance Status": "Action Needed",
                                       "Total GHG Emissions (kgCO2e)": 600_000})
    assert status == "Action needed (City)"
    assert acp == round(70.0 * ACP_RATE, 0)


def test_other_city_statuses():
    cases = {"Pending Review from BERDO Team": "Under City review",
             "Emissions Compliance at Portfolio Level": "Assessed in a Building Portfolio",
             "N/A until 2030": "Not yet covered", "Vacant": "Vacant (exempt)",
             "Pending Reporting": "Pending reporting (City)"}
    for city, label in cases.items():
        assert _status(**{"Emissions Compliance Status": city})[1] == label, city


def test_new_reporting_statuses():
    assert _status(**{"Reporting Compliance Status": "Not Reported"})[0] == "Not submitted"
    assert _status(**{"Reporting Compliance Status": "Extension"})[0] == "Extension granted"


def test_detect_data_year_from_grid_factor():
    def df_for(year, n=80):
        kwh = [200_000 + 1000 * i for i in range(n)]
        return pd.DataFrame({"fuel_electricity_kwh": kwh,
                             "elec_emissions_kg": [k / 1000 * effective_grid_ef(year) for k in kwh]})
    assert detect_data_year(df_for(2025)) == 2025
    assert detect_data_year(df_for(2024)) == 2024
    assert detect_data_year(pd.DataFrame({"x": [1]})) is None          # older files: no electricity emissions


def test_fuel_conversions():
    assert fuel_to_kbtu("Fuel oil #1", "gallons", 1) == 139.0
    assert fuel_to_kbtu("Natural gas", "therms", 1) == 100.0
    assert fuel_to_kbtu("Natural gas", "Mcf (thousand cu ft)", 1) == 1026.0
    assert fuel_to_kbtu("Electricity", "kWh", 1000) == 3412.0


def test_lookup_result_row_fields():
    row = _raw2026([{}]).iloc[0]
    with_fuel, without = lookup_result_row(row, include_fuel=True), lookup_result_row(row, include_fuel=False)
    assert "Primary Fuel" in with_fuel and "Primary Fuel" not in without
    assert with_fuel["BERDO Status"] == without["BERDO Status"]
