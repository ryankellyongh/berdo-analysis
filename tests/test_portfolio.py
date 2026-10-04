"""
Building Portfolio calculations, on a two-building example worked out by hand:

  A: Office, 100,000 sq ft, 600,000 kg CO2e (6.0 kg/sf), 300,000 kg from electricity
  B: Multifamily, 100,000 sq ft, 300,000 kg CO2e (3.0 kg/sf), no electricity breakdown

  Portfolio: 900,000 kg / 200,000 sq ft = 4.5 kg/sf
  Blended limits = average of Office and Multifamily (equal floor area):
    2025: (5.3 + 4.1) / 2 = 4.7   -> compliant
    2030: (3.2 + 2.4) / 2 = 2.8   -> 1.7 over x 200,000 sf = 340 t -> USD 79,560/yr
    2035: 2.1 -> 480 t; 2040: 1.35 -> 630 t; 2045: 0.7 -> 760 t; 2050+: 0 -> 900 t
"""
import pandas as pd

from berdo.regulations import ACP_RATE
from berdo.portfolio import (
    building_surplus_deficit, classify_portfolio_buildings, portfolio_electricity_share,
    portfolio_summary, worst_building,
)


def _bldg(addr, ptype, sqft, ghg, elec=None, status="in compliance", year=2025, owner="OWNER LLC"):
    return {"Building Address": addr, "Property Type": ptype, "All Property Types": None,
            "Gross Floor Area": sqft, "GHG Emissions (kgCO2e)": ghg,
            "GHG Intensity (kgCO2e/sqft)": (ghg / sqft) if ghg is not None and sqft else None,
            "Electricity Emissions (kgCO2e)": elec, "Compliance Status": status,
            "First Compliance Year": year, "Property Owner Name": owner, "Site EUI": 50}


A = _bldg("A St", "Office", 100_000, 600_000, elec=300_000)
B = _bldg("B St", "Multifamily Housing", 100_000, 300_000)


def test_classify_includes_and_excludes_with_reasons():
    df = pd.DataFrame([A, B,
                       _bldg("State Bldg", "Office", 50_000, 100_000, status="state"),
                       _bldg("Small Bldg", "Office", 25_000, 100_000, year=2030),
                       _bldg("No Data", "Office", 50_000, None, status="not reported")])
    valid, excluded = classify_portfolio_buildings(df)
    assert valid["Building Address"].tolist() == ["A St", "B St"]
    reasons = {r["Building Address"]: r["Exclusion Reason"] for r in excluded}
    assert reasons["State Bldg"].startswith("State record")
    assert reasons["Small Bldg"] == "Not yet covered: no emissions limit until 2030 emissions"
    assert reasons["No Data"] == "Did not report: no GHG data submitted"


def test_portfolio_summary_by_hand():
    s = portfolio_summary(pd.DataFrame([A, B]))
    assert s["intensity"] == 4.5 and s["total_sqft"] == 200_000
    assert s["blended_limits"][:2] == [4.7, 2.8]
    p2025, p2030 = s["periods"][0], s["periods"][1]
    assert p2025["compliant"] and p2025["annual_fine"] == 0
    assert p2030["excess_tons"] == 340.0 and p2030["annual_fine"] == round(340.0 * ACP_RATE)   # 79,560
    assert [i for i, _ in s["non_compliant_periods"]] == [1, 2, 3, 4, 5]
    # five-year periods 2030-2049: (340 + 480 + 630 + 760) t x 234 x 5
    assert round(s["total_5yr"]) == round((340 + 480 + 630 + 760) * ACP_RATE * 5)              # 2,585,700
    assert round(s["indefinite_annual_fine"]) == round(900 * ACP_RATE)                         # 210,600


def test_portfolio_summary_without_mappable_uses():
    s = portfolio_summary(pd.DataFrame([_bldg("X", "Unknown type", 100_000, 500_000)]))
    assert s["blended_limits"] is None


def test_portfolio_electricity_share_mixes_reported_and_sidebar():
    # A reports 50%; B uses the sidebar's 40%: (0.5 x 600,000 + 0.4 x 300,000) / 900,000
    share, source = portfolio_electricity_share(pd.DataFrame([A, B]), 900_000, 0.4)
    assert abs(share - 420_000 / 900_000) < 1e-12
    assert source == "reported for 1 of 2 buildings; sidebar estimate for the rest"
    assert portfolio_electricity_share(pd.DataFrame([A, B]), 900_000, 0.4, use_reported=False) == \
        (0.4, "sidebar estimate")


def test_worst_building_and_surplus_deficit():
    assert worst_building(pd.DataFrame([A, B])) == ("A St", 70.0)          # (6.0 - 5.3) x 100 t
    table = building_surplus_deficit(pd.DataFrame([B, A]))
    assert table["Address"].tolist() == ["A St", "B St"]                   # largest deficit first
    assert table["2025 Gap (MT)"].tolist() == [70.0, -110.0]               # B: (3.0 - 4.1) x 100 t
    assert table["2025"].tolist() == ["Fail", "Pass"]
