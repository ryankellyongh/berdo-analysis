"""
Regression tests for the November 2026 review fixes:
  1. Planner and retrofit inputs never keep another record's values
  2. Avoided ACP compares baseline and remaining ACP for the same building
  3. Missing data never earns a "Compliant through 2034" label
  4. Newer Portfolio Manager property-type names map to their Appendix A uses
Tests 1-3 import the Streamlit interface modules; without streamlit and plotly installed
they return early, like test_pdf.py does without reportlab.
"""
import importlib

import pandas as pd

from berdo import data as D
from berdo.emissions import map_property_type


def _ui(name):
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


# 4. Property-type names ------------------------------------------------------------

def test_newer_portfolio_manager_names_map():
    assert map_property_type("Vehicle Repair Services") == "Services"     # Appendix A: Repair Services (Vehicle...)
    assert map_property_type("Vehicle Dealership") == "Retail"            # Appendix A: Automobile Dealership
    assert map_property_type("Other/Specialty Hospital") == "Healthcare"  # Appendix A: Other - Specialty Hospital


def test_bare_other_stays_unmapped():
    # "Other" isn't in Appendix A: a person has to classify the building
    assert map_property_type("Other") is None


# 1. Prefill clears stale values ----------------------------------------------------

def test_prefill_overwrites_and_clears_on_new_record(monkeypatch):
    common = _ui("ui.common")
    if common is None:
        return
    state = {}
    monkeypatch.setattr(common.st, "session_state", state)
    common.apply_prefill_once("m", "1047 COMM|2026", {"ep_ghg": 4.255, "ep_sqft": 100_800})
    state["ep_ghg"] = 5.0                                                   # user edit
    common.apply_prefill_once("m", "1047 COMM|2026", {"ep_ghg": 4.255, "ep_sqft": 100_800})
    assert state["ep_ghg"] == 5.0                                           # same record: edit kept
    common.apply_prefill_once("m", "1047 COMM|2025", {"ep_ghg": None, "ep_sqft": None})
    assert state["ep_ghg"] is None and state["ep_sqft"] is None             # unknown, not the 2026 values


def test_prefill_keeps_reported_zero(monkeypatch):
    common = _ui("ui.common")
    if common is None:
        return
    state = {}
    monkeypatch.setattr(common.st, "session_state", state)
    common.apply_prefill_once("m", "A", {"ep_ghg": 6.0})
    common.apply_prefill_once("m", "B", {"ep_ghg": 0.0})
    assert state["ep_ghg"] == 0.0


# 2. Avoided ACP from one baseline --------------------------------------------------

OFFICE_PREFILL = {"sqft": 100_000, "berdo_category": "Office", "ghg_intensity": 6.0,
                  "annual_fine_usd": 16_380.0}


def test_avoided_acp_after_floor_area_edit():
    rf = _ui("ui.retrofit")
    if rf is None:
        return
    # Area edited to 50,000 sq ft; a 1,000 kg project takes 6.0 to 5.98 kg/sf
    baseline, remaining, avoided = rf._retrofit_avoided(OFFICE_PREFILL, "Office", 50_000, 5.98)
    assert (baseline, remaining, avoided) == (8_190.0, 7_956.0, 234.0)     # not 8,424


def test_avoided_acp_keeps_stored_baseline_when_unedited():
    rf = _ui("ui.retrofit")
    if rf is None:
        return
    baseline, remaining, avoided = rf._retrofit_avoided(OFFICE_PREFILL, "Office", 100_000, 5.99)
    assert baseline == 16_380.0 and remaining == 16_146.0 and avoided == 234.0


def test_avoided_acp_unknown_area_is_none():
    rf = _ui("ui.retrofit")
    if rf is None:
        return
    _, remaining, avoided = rf._retrofit_avoided(OFFICE_PREFILL, "Office", None, 5.98)
    assert remaining is None and avoided is None


# 3. Unknown later periods ----------------------------------------------------------

def _city_compliant(ptype):
    raw = {"BERDO ID": "900002", "Building Address": "2 Test St", "Property Owner Name": "Test Owner",
           "Largest Property Type": ptype, "Reported Gross Floor Area (Sq Ft)": 50_000,
           "Site EUI (Energy Use Intensity kBtu/ft²)": 60.0, "Total Site Energy Usage (kBtu)": 3_000_000,
           "Estimated Total GHG Emissions (kgCO2e)": 200_000.0, "Reporting Compliance Status": "In Compliance",
           "First Emissions Compliance Year (Projected)": 2025, "Emissions Compliance Status": "In Compliance"}
    return D.prepare_dataframe(pd.DataFrame([raw]))


def test_city_compliant_without_limit_is_not_labeled_through_2034():
    cw = _ui("ui.citywide")
    if cw is None:
        return
    ev = cw.evaluate_year(_city_compliant("Other"))
    assert ev.loc[0, "status_group"] == "Meets 2025–29 limit; later periods unknown"
    assert "Meets 2025–29 limit; later periods unknown" in [n for n, _, _ in cw.STATUS_GROUPS]


def test_city_compliant_with_limit_is_still_assessed():
    cw = _ui("ui.citywide")
    if cw is None:
        return
    ev = cw.evaluate_year(_city_compliant("Office"))                       # 4.0 kg/sf: 2030 limit 3.2
    assert ev.loc[0, "status_group"] == "Fails 2030–34"
