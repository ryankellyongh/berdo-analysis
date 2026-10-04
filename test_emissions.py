"""
BERDO calculation rules. Hand-calculated values are noted where used.
"""
import datetime as dt
import pandas as pd

from berdo.regulations import ACP_RATE, BERDO_STANDARDS
from berdo.emissions import (
    building_elec_share, building_limits, blend_limits_by_area, calculate_compliance_gap,
    coverage_for, effective_grid_ef, evaluate_building, fmt_share, is_city_building,
    map_property_type, next_deadline, period_covered, planner_model, rec_connector_price,
    rec_pathway,
)

OFFICE = BERDO_STANDARDS["Office"]


# ── Grid factors ──

def test_effective_grid_factor_matches_city_estimates():
    # The City's estimated electricity emissions in the "2025" dataset use exactly
    # 256 x (1 - 24%) = 194.56 kg/MWh, the 2024 factors.
    assert round(effective_grid_ef(2024), 2) == 194.56
    assert round(effective_grid_ef(2025), 2) == 181.77


def test_rec_break_even_price():
    rec = rec_pathway(gap_kg=100_000, elec_emissions_kg=200_000, year=2025, rec_price=50)
    assert round(rec["breakeven_price"], 2) == round(ACP_RATE * 249 / 1000, 2)
    assert rec["fully_covered"]


def test_rec_connector_price_tiers():
    assert rec_connector_price(10) == 54 and rec_connector_price(49.2) == 52   # rounds up to 50
    assert rec_connector_price(100) == 50 and rec_connector_price(2500) == 42


# ── Property types and blended standards ──

def test_appendix_a_spelling_variant_maps():
    assert map_property_type("Personal Services (Health/Beauty Dry Cleaning etc.)") == "Services"


def test_blended_standard_60_washington_st():
    # K-12 147,205 + Library 57,602 + Social/Meeting Hall 8,534 (4%, non-primary -> counts as Education)
    raw = "K-12 School (147205),Library (57602),Social/Meeting Hall (8534)"
    bl = building_limits("K-12 School", raw)
    assert bl["limits"] == BERDO_STANDARDS["Education"]          # default = largest use
    expected = (3.9 * 147205 + 7.5 * 57602 + 3.9 * 8534) / 213341
    assert abs(bl["blended"][0] - expected) < 1e-3               # about 4.87


def test_uses_under_ten_percent_are_not_primary():
    uses = [{"BERDO category": "Multifamily Housing", "Sq ft": 90_000},
            {"BERDO category": "Food Sales & Service", "Sq ft": 8_000}]
    limits, total, non_primary, n_primary = blend_limits_by_area(uses)
    assert n_primary == 1 and non_primary == 8_000
    assert limits[0] == BERDO_STANDARDS["Multifamily Housing"][0]


def test_parking_left_out_of_blend_by_default():
    bl = building_limits("Multifamily Housing", "Multifamily Housing (134725),Parking (28940)")
    assert bl["basis"] == "largest_use" and bl["blended"] is None


# ── Coverage ──

def test_smaller_buildings_not_covered_until_2030():
    cov = coverage_for(2030, "in compliance", "SOME OWNER LLC")
    assert not period_covered(cov, 0) and period_covered(cov, 1)
    gaps = calculate_compliance_gap(6.0, 30_000, None, limits=OFFICE, coverage=cov)
    assert gaps[0]["annual_fine_usd"] == 0 and not gaps[0]["covered"]
    assert gaps[0]["gap"] > 0                                     # still reported for reference
    assert gaps[1]["annual_fine_usd"] > 0


def test_state_and_federal_records_not_assessed():
    for status in ("state", "federal"):
        cov = coverage_for(2025, status, "MASSACHUSETTS PORT AUTHORITY")
        assert not cov["known"] and not any(period_covered(cov, i) for i in range(6))


def test_city_and_bha_buildings_detected():
    assert is_city_building("CITY OF BOSTON") and is_city_building("BOSTON HOUSING AUTHORITY")
    assert not is_city_building("CITYSIDE REALTY LLC")


def test_missing_compliance_year_means_unknown_coverage():
    cov = coverage_for(None, "in compliance", "X")
    assert not cov["known"] and not period_covered(cov, 0)


# ── Screening status ──

def _row(**kw):
    base = dict(property_type="Office", all_property_types=None, ghg_intensity_kgco2e_sqft=6.0,
                gross_floor_area=50_000, compliance_status="in compliance", compliance_year=2025,
                ghg_emissions=300_000, elec_emissions_kg=None, data_year=2024,
                **{"Property Owner Name": "SOME OWNER LLC"})
    base.update(kw)
    return pd.Series(base)


def test_over_limit_acp_by_hand():
    data_status, status, acp, notes = evaluate_building(_row())
    assert status == "Over 2025–29 limit"
    assert acp == round(round((6.0 - 5.3) * 50_000 / 1000, 1) * ACP_RATE, 0)   # 35 t x 234 = 8,190


def test_not_yet_covered_gets_no_acp():
    _, status, acp, notes = evaluate_building(_row(compliance_year=2030))
    assert status == "Not yet covered" and acp == 0


def test_state_record_not_assessed():
    _, status, acp, _ = evaluate_building(_row(compliance_status="state"))
    assert status == "Not assessed (state)" and acp == 0


def test_city_building_keeps_acp_and_notes_fines():
    _, status, acp, notes = evaluate_building(_row(**{"Property Owner Name": "CITY OF BOSTON"}))
    assert acp > 0 and any("section r" in n for n in notes)


# ── Electricity share ──

def test_electricity_share_edge_cases():
    assert building_elec_share(1000, 370) == (0.37, None)
    assert building_elec_share(1000, -50)[0] == 0.0          # negative (on-site export) -> 0, flagged
    assert building_elec_share(1000, 1200)[0] == 1.0         # capped
    assert building_elec_share(1000, None) == (None, None)
    assert fmt_share(0.006) == "0.6%" and fmt_share(0.37) == "37%"


# ── Emissions Planner model ──

COVERED = [True] * 6


def test_planner_no_projects_cumulative():
    m = planner_model(6.0, 100_000, OFFICE, [], COVERED)
    assert round(m["cumulative"]["baseline"]) == 1_953_900


def test_planner_project_counts_from_implementation_year():
    # 150,000 kg/yr project in 2033: 2030-32 at the full gap, 2033-34 with the project.
    proj = [{"year": 2033, "reduction_kg": 150_000, "elec_mwh": 0}]
    m = planner_model(6.0, 100_000, OFFICE, proj, COVERED)
    assert m["period_reductions_kg"][1] == 60_000             # 2 of 5 years
    assert m["fines"]["projects"][1] == 51_480
    assert round(m["cumulative"]["projects"]) == 1_357_200    # hand-checked


def test_planner_electricity_savings_follow_baseline_grid():
    proj = [{"year": 2030, "reduction_kg": 1, "elec_mwh": 500}]
    off = planner_model(6.0, 100_000, OFFICE, proj, COVERED, apply_grid=False, elec_share=0.5, base_year=2025)
    assert round(off["period_reductions_kg"][1]) == round(500 * effective_grid_ef(2025))
    assert round(off["cumulative"]["projects"]) == 1_528_558
    on = planner_model(6.0, 100_000, OFFICE, proj, COVERED, apply_grid=True, elec_share=0.5, base_year=2025)
    assert round(on["period_reductions_kg"][1]) == round(500 * effective_grid_ef(2032))
    assert round(on["cumulative"]["combined"]) == 1_106_071


def test_planner_caps_electricity_savings():
    proj = [{"year": 2030, "reduction_kg": 1, "elec_mwh": 5000}]
    m = planner_model(6.0, 100_000, OFFICE, proj, COVERED, elec_share=0.5)
    assert m["elec_capped_years"]


def test_planner_uncovered_periods_have_no_acp():
    m = planner_model(6.0, 100_000, OFFICE, [], [False] + [True] * 5)
    assert m["fines"]["baseline"][0] == 0 and m["current_annual_fine"] == 0


# ── Deadlines ──

def test_next_deadline_rolls_to_next_year():
    d, days = next_deadline(9, 1, today=dt.date(2026, 9, 22))
    assert d == dt.date(2027, 9, 1) and days == 344
    d, days = next_deadline(10, 1, today=dt.date(2026, 9, 22))
    assert d == dt.date(2026, 10, 1) and days == 9
