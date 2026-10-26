"""
Regression tests for calculation defects found in external review (October 2026).
Each test reproduces the reviewer's example and checks the corrected result.

These exercise the berdo package, which is the only calculation code the app uses
(test_app_uses_berdo checks that). Run with pytest, or directly: python tests/test_regressions.py
"""
import ast
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from berdo import data as D                      # noqa: E402
from berdo import emissions as E                 # noqa: E402
from berdo import portfolio as P                 # noqa: E402
from berdo import retrofit as R                  # noqa: E402
from berdo.regulations import COMPLIANCE_PERIODS  # noqa: E402


def _close(a, b, tol=0.01):
    return a is not None and b is not None and math.isclose(a, b, abs_tol=tol)


def _building(**over):
    """One prepared building row, built through the real loader."""
    raw = {
        "BERDO ID": "900001", "Building Address": "1 Test St", "Property Owner Name": "Test Owner",
        "Largest Property Type": "Office", "All Property Types and GFAs (sq ft)": "Office (50000)",
        "Reported Gross Floor Area (Sq Ft)": 50000, "Site EUI (Energy Use Intensity kBtu/ft²)": 6.0,
        "Total Site Energy Usage (kBtu)": 3_000_000, "Estimated Total GHG Emissions (kgCO2e)": 300000.0,
        "Reporting Compliance Status": "In Compliance", "First Emissions Compliance Year (Projected)": 2025,
    }
    raw.update(over)
    return D.prepare_dataframe(pd.DataFrame([raw])).iloc[0]


# 1. The app runs the tested code ------------------------------------------------

def test_app_uses_berdo():
    """app.py must import its calculations from berdo, not define its own."""
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert any(m.startswith("berdo") for m in imported)
    assert any(m.startswith("ui") for m in imported)
    defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    duplicates = defined & {"calculate_compliance_gap", "evaluate_building", "effective_grid_ef",
                            "calculate_blended_standard", "project_ghg_intensities", "map_property_type",
                            "payback_estimates", "net_retrofit_cost"}
    assert not duplicates, f"app.py redefines calculation functions: {sorted(duplicates)}"


# 2. Payback uses avoided ACP, not baseline ACP ----------------------------------

def test_payback_uses_avoided_acp():
    """$100,000 project, ACP 23,400 -> 11,700, no energy savings: about 8.5 years, not 4.3."""
    avoided = R.avoided_acp(23_400, 11_700)
    assert avoided == 11_700
    pb = R.payback_estimates(100_000, 100_000, avoided, 0)
    assert pb["low_acp_only"] == 8.5
    assert pb["low_combined"] == 8.5


def test_payback_unavailable_without_benefit():
    pb = R.payback_estimates(100_000, 100_000, 0, 0)
    assert pb["low_acp_only"] is None and pb["low_combined"] is None


def test_remaining_acp_after_project():
    #6.0 kg/sf over a 5.3 limit on 50,000 sf -> 8,190; project brings it to 5.65 -> 4,095 remaining
    assert R.remaining_acp(5.65, 50_000, 5.3) == 4095.0
    assert R.avoided_acp(8190.0, R.remaining_acp(5.65, 50_000, 5.3)) == 4095.0


# 3. Reductions start in the implementation year ----------------------------------

def test_planner_no_savings_before_implementation():
    """A project implemented in 2029 gets credit for 2029 only within 2025-29."""
    limits = E.BERDO_STANDARDS["Office"]
    m = E.planner_model(6.0, 50_000, limits, [{"year": 2029, "reduction_kg": 35_000, "elec_mwh": 0}],
                        covered=[True] * 6)
    assert m["reduction_in_year"](2028) == 0
    assert m["reduction_in_year"](2029) == 35_000
    base = m["fines"]["baseline"][0]                 # 8,190 per year
    assert _close(base, 8190, tol=1)
    #2025-29 average: four years at 8,190 and one year at 0 (35 t removes all excess)
    assert _close(m["fines"]["projects"][0], 8190 * 4 / 5, tol=1)


# 4. One portfolio membership for emissions, area, and standards -------------------

def _portfolio_rows():
    common = {"Compliance Status": "in compliance", "First Compliance Year": 2025,
              "Property Owner Name": "Test Owner"}
    return pd.DataFrame([
        {**common, "Building Address": "Office", "Property Type": "Office", "All Property Types": "Office (50000)",
         "Gross Floor Area": 50_000, "GHG Emissions (kgCO2e)": 300_000.0, "GHG Intensity (kgCO2e/sqft)": 6.0},
        {**common, "Building Address": "Unknown", "Property Type": "Something unmapped", "All Property Types": None,
         "Gross Floor Area": 50_000, "GHG Emissions (kgCO2e)": 0.0, "GHG Intensity (kgCO2e/sqft)": 0.0},
    ])


def test_portfolio_membership_is_consistent():
    """Office 50,000 sf / 300,000 kg plus an unmapped 50,000 sf / 0 kg: ACP is the office's 8,190, not 0."""
    valid, excluded = P.classify_portfolio_buildings(_portfolio_rows())
    assert list(valid["Building Address"]) == ["Office"]
    assert any("can't be matched" in e["Exclusion Reason"] for e in excluded)
    s = P.portfolio_summary(valid, n_excluded=len(excluded))
    assert _close(s["periods"][0]["annual_fine"], 8190.0)
    assert s["is_subtotal"] is True


def test_portfolio_summary_drops_unmapped_even_if_passed_directly():
    s = P.portfolio_summary(_portfolio_rows())
    assert s["n_included"] == 1 and s["is_subtotal"] is True
    assert _close(s["periods"][0]["annual_fine"], 8190.0)


# 5. Unknown is N/A, never $0 ---------------------------------------------------

def test_unknown_emissions_give_no_acp():
    row = _building(**{"Estimated Total GHG Emissions (kgCO2e)": None})
    data_status, status, acp, _ = E.evaluate_building(row)
    assert status.startswith("Unknown")
    assert acp is None


def test_compliant_covered_building_owes_zero():
    row = _building(**{"Estimated Total GHG Emissions (kgCO2e)": 200_000.0})   # 4.0 < 5.3
    assert E.evaluate_building(row)[2] == 0.0


def test_state_record_gives_no_acp():
    row = _building(**{"Reporting Compliance Status": "State"})
    assert E.evaluate_building(row)[2] is None


def test_not_yet_covered_gives_no_acp():
    row = _building(**{"First Emissions Compliance Year (Projected)": 2030})
    assert E.evaluate_building(row)[2] is None


def test_zero_emissions_is_a_valid_value():
    """An all-electric building with zero reported emissions is assessable and compliant."""
    row = _building(**{"Estimated Total GHG Emissions (kgCO2e)": 0.0})
    _, status, acp, _ = E.evaluate_building(row)
    assert not status.startswith("Unknown") and acp == 0.0


def test_pdf_rows_keep_none():
    rows = E.period_status_rows(4.0, 50_000, E.BERDO_STANDARDS["Office"], E.coverage_for(2025))
    assert rows[0]["acp"] == 0.0


# 6. No rounding before the compliance test ---------------------------------------

def test_no_premature_rounding():
    """Office 5.3004 vs 5.3 on 1,000,000 sf: 400 kg over, $93.60, not compliant."""
    g = E.calculate_compliance_gap(5.3004, 1_000_000, "Office")[0]
    assert g["compliant"] is False
    assert _close(g["excess_metric_tons"], 0.4, tol=1e-6)
    assert _close(g["annual_fine_usd"], 93.60)


# 7. Incentive caps; potential incentives never reduce cost ------------------------

def test_incentive_estimate_respects_cap():
    inc = {"amount_psf_low": 0.5, "amount_psf_high": 3.0, "max_per_project": 400_000}
    assert E._estimate_incentive_value(inc, 1_000_000) == (400_000, 400_000)


def test_potential_incentives_not_deducted():
    assert R.net_retrofit_cost(100_000, 200_000) == (100_000, 200_000)
    assert R.net_retrofit_cost(100_000, 200_000, confirmed_funding=50_000) == (50_000, 150_000)
    assert R.net_retrofit_cost(100_000, 200_000, confirmed_funding=500_000) == (0, 0)


# 8. Headline counts use one population --------------------------------------------

def test_headline_counts_separate_campus_summaries():
    df = pd.DataFrame({"is_campus_summary": [False, False, True]})
    st = pd.Series(["Over 2025–29 limit", "Fails 2030–34", "Over 2025–29 limit"])
    c = D.headline_counts(df, st)
    assert c["buildings"] == 2 and c["campus_assessments"] == 1
    assert c["by_status"] == {"Over 2025–29 limit": 1, "Fails 2030–34": 1}
    assert c["campus_by_status"] == {"Over 2025–29 limit": 1}


# Data: Site EUI is recalculated, never copied from GHG intensity --------------------

def test_site_eui_recalculated():
    row = _building(**{"Site EUI (Energy Use Intensity kBtu/ft²)": 6.0,
                       "Total Site Energy Usage (kBtu)": 3_202_500})
    assert _close(row["site_eui"], 64.05)


def test_converter_official_columns_recognized():
    """convert_berdo_2026.py writes official_* names; the loader must map them."""
    raw = {"official_emissions_status": "Action Needed", "official_standard_2025": 5.3}
    df = D.prepare_dataframe(pd.DataFrame([{**_building().to_dict(), **raw}]))
    assert df.iloc[0]["emissions_status"] == "Action Needed"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as e:                       # noqa: BLE001
            failed += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
