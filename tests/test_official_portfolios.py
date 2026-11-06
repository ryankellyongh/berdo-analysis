"""
Approved City Building Portfolios (portfolios_<year>.csv): loading, matching a query
to a portfolio, joining members on BERDO ID, and the City's standard as the 2025-29 limit.
"""
import pandas as pd

from berdo.data import (
    find_official_portfolios, latest_year_with_member_emissions, load_official_portfolios,
    official_portfolio_members,
)
from berdo.portfolio import portfolio_summary

CSV = """Portfolio ID,Portfolio Owner Name,Gross Floor Area (sq ft),Largest Property Type,Portfolio Approval Date,Emissions Compliance Status,Total GHG Emissions (kgCO2e),GHG Emissions Intensity (kgCO2e/sq ft),Applicable Emissions Compliance Standard (kgCO2e/sq ft),Applicable Emissions Compliance Standard for Individual Compliance Schedules (kg CO2e),Flexibility Measures,First Emissions Compliance Year,Member BERDO IDs
P1,Acme Holdings,200000,Office,2025-01-13,In Compliance,800000,4.0,5.4,,Building Portfolio,2025,"101, 102.0"
P2,Acme Medical,150000,Healthcare,2025-03-10,Pending Reporting,,,15.1,,Building Portfolio,2025,"103,C900"
P3,State University,500000,College / University,2025-04-28,Pending Review from BERDO Team,,,,9000000,"Building Portfolio, Individual Compliance Schedule",2025,104
"""


def _portfolios(tmp_path):
    f = tmp_path / "portfolios_2026.csv"
    f.write_text(CSV)
    return load_official_portfolios(f)


def _year(rows):
    return pd.DataFrame([{"berdo_id": i, "Property Owner Name": o, "ghg_emissions": g} for i, o, g in rows])


def test_load_parses_member_ids_and_numbers(tmp_path):
    p = _portfolios(tmp_path)
    assert p["member_ids"].tolist() == [["101", "102"], ["103", "C900"], ["104"]]   # "102.0" -> "102"
    assert p.loc[0, "Applicable Emissions Compliance Standard (kgCO2e/sq ft)"] == 5.4
    assert pd.isna(p.loc[2, "Applicable Emissions Compliance Standard (kgCO2e/sq ft)"])


def test_load_missing_or_bad_file_is_empty(tmp_path):
    assert load_official_portfolios(tmp_path / "nope.csv").empty
    (tmp_path / "bad.csv").write_text("a,b\n1,2\n")
    assert load_official_portfolios(tmp_path / "bad.csv").empty


def test_find_by_id_is_exact_and_case_insensitive(tmp_path):
    p = _portfolios(tmp_path)
    assert find_official_portfolios(p, "p2")["Portfolio ID"].tolist() == ["P2"]
    assert find_official_portfolios(p, "").empty


def test_find_by_name_returns_every_match(tmp_path):
    p = _portfolios(tmp_path)
    assert find_official_portfolios(p, "acme")["Portfolio ID"].tolist() == ["P1", "P2"]
    assert find_official_portfolios(p, "Nobody LLC").empty


def test_find_through_member_owner_name_ranked_by_overlap(tmp_path):
    # "Redevelopment Auth" appears in no portfolio name, but owns members of P1 and P3
    p = _portfolios(tmp_path)
    df = _year([("101", "Redevelopment Auth", 1.0), ("103", "Other", 1.0),
                ("104", "Redevelopment Auth", 1.0), ("102", "Acme", 1.0)])
    assert set(find_official_portfolios(p, "redevelopment", df)["Portfolio ID"]) == {"P1", "P3"}
    # A name match on the portfolio itself ranks ahead of member-owner matches, even when
    # the other portfolio holds more of the owner's buildings
    df3 = _year([("103", "Acme Medical Group", 1.0), ("101", "Acme Medical Group", 1.0),
                 ("102", "Acme Medical Group", 1.0)])
    assert find_official_portfolios(p, "acme medical", df3)["Portfolio ID"].tolist() == ["P2", "P1"]
    # Among member-owner matches, more overlap ranks first
    df4 = _year([("101", "Big Owner", 1.0), ("102", "Big Owner", 1.0), ("104", "Big Owner", 1.0)])
    assert find_official_portfolios(p, "big owner", df4)["Portfolio ID"].tolist() == ["P1", "P3"]


def test_members_joined_on_berdo_id_and_missing_reported(monkeypatch):
    import berdo.data as d
    monkeypatch.setattr(d, "buildings_only", lambda df: df)
    monkeypatch.setattr(d, "lookup_result_row", lambda row, include_fuel=False: {"BERDO ID": row["berdo_id"]})
    df = _year([("101", "Someone Else", 1.0), ("999", "Acme Holdings", 1.0)])
    members, missing = official_portfolio_members(df, ["101", "102"])
    assert members["BERDO ID"].tolist() == ["101"]        # owner name doesn't matter; 999 isn't a member
    assert missing == ["102"]
    assert official_portfolio_members(df, ["555"]) == (None, ["555"])


def test_latest_year_with_member_emissions_skips_portfolio_only_years():
    years = {2025: _year([("101", "A", 500.0), ("102", "A", None)]),
             2026: _year([("101", "A", None), ("102", "A", None)])}   # 2026: portfolio level only
    assert latest_year_with_member_emissions(years, ["101", "102"], 2026) == (2025, 1)
    assert latest_year_with_member_emissions(years, ["101"], 2024) == (None, 0)


A = {"Building Address": "A St", "Property Type": "Office", "All Property Types": None,
     "Gross Floor Area": 100_000, "GHG Emissions (kgCO2e)": 500_000}


def test_official_standard_replaces_only_the_2025_limit():
    blended = portfolio_summary(pd.DataFrame([A]))
    official = portfolio_summary(pd.DataFrame([A]), official_limit_2025=4.8)
    assert blended["limit_source"] == "blended" and blended["blended_limits"][0] == 5.3
    assert official["limit_source"] == "official"
    assert official["blended_limits"][0] == 4.8 and official["blended_limits"][1:] == blended["blended_limits"][1:]
    # 5.0 kg/sf: compliant under the Office default (5.3), over the City's 4.8 by 20 t
    assert blended["periods"][0]["compliant"]
    assert not official["periods"][0]["compliant"]
    assert round(official["periods"][0]["excess_tons"], 6) == 20.0


def test_missing_official_standard_falls_back_to_blended():
    s = portfolio_summary(pd.DataFrame([A]), official_limit_2025=float("nan"))
    assert s["limit_source"] == "blended" and s["blended_limits"][0] == 5.3
