"""Retrofit, incentive, payback, and ACP schedule calculations, checked by hand."""
from berdo.regulations import ACP_RATE, BERDO_STANDARDS, INCENTIVE_STACK
from berdo.emissions import _opt_incentive_applies, coverage_for, effective_grid_ef
from berdo.retrofit import (
    acp_schedule, acp_totals, estimate_incentives, first_year_reduction_kg, headline_payback,
    net_retrofit_cost, payback_estimates, planned_project_impact, rec_break_even_price,
    rec_inputs, retrofit_cost_estimate, retrofit_recommendation,
)

OFFICE = BERDO_STANDARDS["Office"]
LIGHTING = "Lighting (LED retrofit + controls)"     # USD 1.50 to 4.00 per sq ft nationally
HVAC_TUNEUP = "HVAC (tune-up, controls, VFDs)"


def test_cost_estimate_no_audit_with_boston_multiplier():
    # 1.5 x 1.25 = 1.875 and 4.0 x 1.25 = 5.0 per sq ft; adjusted = 1.875 + 0.55 x 3.125
    est = retrofit_cost_estimate([LIGHTING], 10_000, has_audit=False, apply_boston=True)
    assert (est["total_low"], est["total_high"]) == (18_750, 50_000)
    assert abs(est["total_adjusted"] - 35_937.5) < 1e-9


def test_cost_estimate_with_audit_national():
    est = retrofit_cost_estimate([LIGHTING], 10_000, has_audit=True, apply_boston=False)
    assert abs(est["total_adjusted"] - 20_000) < 1e-9                    # 1.5 + 0.2 x 2.5 = 2.0/sf


def test_first_year_reduction():
    assert abs(first_year_reduction_kg("Natural gas", "therms", 1000) - 100_000 * 0.05311) < 1e-9   # 5,311 kg
    assert abs(first_year_reduction_kg("Electricity", "MWh", 1, year=2025) - effective_grid_ef(2025)) < 1e-9
    assert abs(first_year_reduction_kg("Electricity", "MWh", 1) - effective_grid_ef(2027)) < 1e-9  # 2025-29 default


def test_planned_project_partly_closes_gap():
    # 50,000 kg / 100,000 sf = 0.5 kg/sf: 6.0 -> 5.5 against 5.3; gap 0.7 -> 0.2
    imp = planned_project_impact(50_000, 100_000, 6.0, 5.3)
    assert not imp["closes_gap"] and abs(imp["new_intensity"] - 5.5) < 1e-9
    assert imp["pct_closed"] == 71 and imp["remaining_mt"] == 20.0


def test_planned_project_closes_gap():
    imp = planned_project_impact(100_000, 100_000, 6.0, 5.3)
    assert imp["closes_gap"] and imp["pct_closed"] is None


def test_incentive_matching_rules():
    by_short = {i["short"]: i for i in INCENTIVE_STACK}
    assert _opt_incentive_applies(by_short["Mass Save Lighting"], [LIGHTING], "Natural gas", "For-profit", "Office")
    assert not _opt_incentive_applies(by_short["IRA 179D"], [LIGHTING], "Natural gas", "For-profit", "Office")   # closed
    assert not _opt_incentive_applies(by_short["Green Communities"], [LIGHTING], "Natural gas", "For-profit", "Office")
    assert not _opt_incentive_applies(by_short["Mass Save Lighting"], [HVAC_TUNEUP], "Natural gas", "For-profit", "Office")


def test_incentive_estimates_use_cash_value_and_copies():
    by_short = {i["short"]: i for i in INCENTIVE_STACK}
    hvac, tax = by_short["Mass Save HVAC"], by_short["IRA 179D"]
    out, low, high = estimate_incentives([hvac, tax], 10_000)
    assert (out[0]["_est_low"], out[0]["_est_high"]) == (5_000, 20_000)        # USD 0.50 to 2.00/sf
    # deduction at after-tax value: 0.59 x 10,000 x 0.21 and 5.94 x 10,000 x 0.21
    assert (out[1]["_est_low"], out[1]["_est_high"]) == (1_239, 12_474)
    assert (low, high) == (6_239, 32_474)
    assert "_est_low" not in hvac                                             # shared table untouched


def test_net_cost_is_capped_at_zero():
    assert net_retrofit_cost(100_000, 200_000, 30_000, 50_000) == (50_000, 170_000)
    assert net_retrofit_cost(10_000, 20_000, 30_000, 50_000) == (0, 0)


def test_headline_payback():
    # return = 10,000 ACP + 1.00/sf x 10,000 sf = 20,000/yr
    assert headline_payback(100_000, 10_000, 10_000) == ("years", 5.0)
    assert headline_payback(10_000_000, 10_000, 10_000) == ("energy_driven", None)   # > 50 years
    assert headline_payback(0, 10_000, 10_000) == ("covered", None)
    assert headline_payback(100_000, 0, 10_000) == (None, None)


def test_payback_estimates():
    pb = payback_estimates(100_000, 150_000, 10_000, 10_000)
    assert (pb["low_acp_only"], pb["high_acp_only"]) == (10.0, 15.0)
    assert (pb["low_combined"], pb["high_combined"]) == (5.0, 7.5)
    assert pb["cash_low_total"][5] == 0 and pb["cash_low_acp"][0] == -100_000
    assert payback_estimates(0, 0, 10_000, 0)["low_acp_only"] == 0.0


def test_acp_schedule_and_totals():
    # Office at 6.0 kg/sf on 100,000 sf: 2025 70 t -> 16,380/yr; 2030 280 t -> 65,520/yr
    sched = acp_schedule(6.0, 100_000, OFFICE, coverage=None)
    assert [r["annual_fine"] for r in sched[:2]] == [16_380, 65_520]
    assert [r["5yr_fine"] for r in sched[:2]] == [81_900, 327_600]
    t = acp_totals(16_380, sched, net_low=200_000)
    assert t["fine_5yr"] == 81_900 and t["cumulative_10yr"] == 409_500
    assert t["crossover_period"] == "2030–34"                                  # 81,900 + 327,600 >= 200,000


def test_acp_schedule_skips_uncovered_periods():
    sched = acp_schedule(6.0, 100_000, OFFICE, coverage_for(2030, "in compliance", "X"))
    assert sched[0]["annual_fine"] == 0 and sched[1]["annual_fine"] == 65_520


def test_retrofit_recommendation_thresholds():
    assert retrofit_recommendation(0, 50_000, 100_000, 300_000) == "retrofit_now"
    assert retrofit_recommendation(50_000, 50_000, 100_000, 300_000) == "retrofit_now"
    assert retrofit_recommendation(90_000, 50_000, 100_000, 300_000) == "retrofit_soon"
    assert retrofit_recommendation(250_000, 50_000, 100_000, 300_000) == "phase"
    assert retrofit_recommendation(400_000, 50_000, 100_000, 300_000) == "acp_alone_insufficient"


def test_rec_helpers():
    assert abs(rec_break_even_price(2025) - ACP_RATE * 249 / 1000) < 1e-9     # about USD 58.27
    assert abs(rec_break_even_price(2050) - ACP_RATE * 150 / 1000) < 1e-9     # about USD 35.10
    gap_kg, elec_kg = rec_inputs(6.0, 100_000, 5.3, 0.4)
    assert abs(gap_kg - 70_000) < 1e-6 and abs(elec_kg - 240_000) < 1e-6
