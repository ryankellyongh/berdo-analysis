"""Tests for berdo/trends.py (citywide trends)."""
import pandas as pd

from berdo.trends import balanced, combine_years


def _year(ids, ghg, sqft=1000.0):
    return pd.DataFrame({"berdo_id": ids, "ghg_emissions": ghg, "gross_floor_area": sqft,
                         "total_site_energy_kbtu": 1.0, "elec_emissions_kg": 0.0,
                         "is_campus_summary": False, "property_type": "Office",
                         "all_property_types": None})


def test_combine_years_labels_energy_year_and_drops_campus_records():
    d = _year(["1", "2"], [100.0, 200.0])
    d.loc[1, "is_campus_summary"] = True
    out = combine_years({2025: d})
    assert list(out["energy_year"]) == [2024]          #reporting year 2025 holds 2024 energy use
    assert list(out["berdo_id"]) == ["1"]              #campus record excluded


def test_balanced_keeps_only_buildings_present_every_year():
    df = combine_years({2024: _year(["1", "2"], [100.0, 200.0]),
                        2025: _year(["1"], [90.0])})
    p = balanced(df, [2023, 2024], ["_ghg", "_sqft"])
    assert set(p["berdo_id"]) == {"1"}                 #building 2 is missing in 2024


def test_balanced_ignores_years_with_missing_values():
    df = combine_years({2024: _year(["1"], [100.0]), 2025: _year(["1"], [None])})
    assert balanced(df, [2023, 2024], ["_ghg"]).empty  #no emissions in 2024, so not in the panel
