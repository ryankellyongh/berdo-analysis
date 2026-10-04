"""Address Lookup calculations, labels, and passing values between tabs."""
from berdo.regulations import ACP_RATE, BERDO_STANDARDS
from berdo.emissions import (
    acp_exposure, building_limits, calculate_blended_standard, calculate_compliance_gap,
    coverage_for, coverage_from_prefill, coverage_label, current_period_acp, is_portfolio_level,
    limits_for_category, limits_with_city_standard, period_status_rows, reporting_status_label,
    resolve_elec_share,
)
import pandas as pd

OFFICE = BERDO_STANDARDS["Office"]


def test_acp_exposure_matches_hand_total():
    # Office at 6.0 kg/sf on 100,000 sf: excess 70, 280, 360, 440, 520 t (x 234 x 5), then 600 t/yr
    ex = acp_exposure(calculate_compliance_gap(6.0, 100_000, "Office"))
    assert ex["periods_over"] == 5 and ex["total_5yr"] == 1_953_900
    assert ex["annual_2050"] == round(600 * ACP_RATE)


def test_acp_exposure_only_after_2050():
    # 0.5 kg/sf is under every limit through 2049, but the 2050+ limit is 0: 50 t/yr from 2050
    ex = acp_exposure(calculate_compliance_gap(0.5, 100_000, "Office"))
    assert ex["any"] and ex["periods_over"] == 0 and ex["total_5yr"] == 0
    assert ex["annual_2050"] == round(50 * ACP_RATE)
    assert not acp_exposure(calculate_compliance_gap(0.0, 100_000, "Office"))["any"]   # zero emissions


def test_current_period_acp():
    cov = coverage_for(2025, "in compliance", "X")
    assert current_period_acp(6.0, 100_000, 5.3, cov) == 16_380
    assert current_period_acp(5.0, 100_000, 5.3, cov) is None                                 # under the limit
    assert current_period_acp(6.0, 100_000, 5.3, coverage_for(2030, "in compliance", "X")) is None
    assert current_period_acp(6.0, 100_000, 5.3, cov, "Emissions Compliance at Portfolio Level") is None
    assert is_portfolio_level("Emissions Compliance at Portfolio Level") and not is_portfolio_level(None)


def test_city_standard_replaces_2025_limit_only():
    assert limits_with_city_standard(OFFICE, 6.1) == [6.1] + OFFICE[1:]
    assert limits_with_city_standard(OFFICE, None) is None
    assert limits_with_city_standard(None, 6.1) is None


def test_period_status_rows_with_coverage_and_grid():
    cov = coverage_for(2030, "in compliance", "X")
    rows = period_status_rows(6.0, 100_000, OFFICE, cov, projected_intensities=[3.0] * 6)
    assert rows[0]["status"] == "Not yet covered" and rows[0]["acp"] == 0
    assert rows[1]["status"] == "Over limit" and rows[1]["grid_status"] == "Meets limit"   # 3.0 <= 3.2


def test_labels():
    assert coverage_label(coverage_for(2025, "state", "X"), 0) == "Not assessed"
    assert coverage_label(coverage_for(None, "in compliance", "X"), 0) == "Coverage unknown"
    assert coverage_label(coverage_for(2030, "in compliance", "X"), 0) == "Not yet covered"
    assert reporting_status_label("In Compliance") == "Submitted and accepted (City status: in compliance)"
    assert reporting_status_label("not reported").startswith("Not submitted")
    assert reporting_status_label(None) == "Not reported"


def test_values_passed_between_tabs():
    assert coverage_from_prefill({})["applies_from"] == 2025                     # manual entry assumes covered
    assert limits_for_category("Office", {"berdo_category": "Office", "limits": [9.9] * 6}) == [9.9] * 6
    assert limits_for_category("Office", {"berdo_category": "Retail", "limits": [9.9] * 6}) == OFFICE
    assert resolve_elec_share({"elec_share": 0.3, "elec_share_year": 2025}, 0.5) == \
        (0.3, "this building's reported 2025 data")
    assert resolve_elec_share({}, None)[0] == 0.5


def test_uses_listed_without_floor_areas():
    bl = building_limits("Office", "Office, Laboratory (Wet), Parking")
    assert bl["basis"] in ("multi_no_gfa", "largest_use") and bl["limits"] == OFFICE


def test_calculate_blended_standard_equal_areas():
    df = pd.DataFrame([{"Gross Floor Area": 100_000, "Property Type": "Office", "All Property Types": None},
                       {"Gross Floor Area": 100_000, "Property Type": "Multifamily Housing", "All Property Types": None}])
    assert calculate_blended_standard(df)[0] == 4.7                               # (5.3 + 4.1) / 2
