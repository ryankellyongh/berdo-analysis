"""
Building Portfolio calculations: which buildings are included, the blended
portfolio standard, ACP exposure, and each building's surplus or deficit.
No Streamlit, so these can be tested directly.
"""
import pandas as pd

from berdo.regulations import ACP_RATE, COMPLIANCE_PERIODS
from berdo.emissions import (
    building_elec_share,
    building_limits,
    calculate_blended_standard,
    coverage_for,
    government_status,
    period_covered,
)


def _excluded(row, reason):
    return {
        "Building Address":  row.get("Building Address"),
        "Property Type":     row.get("Property Type"),
        "Compliance Status": row.get("Compliance Status"),
        "Exclusion Reason":  reason,
    }


def classify_portfolio_buildings(buildings_df: pd.DataFrame):
    """
    Split an owner's buildings into those included in the portfolio calculation and
    those excluded, with a reason for each exclusion.
    Excluded: state/federal records, buildings not covered in 2025-29, and buildings
    missing GHG emissions or floor area. Returns (included_df, excluded_rows).
    """
    excluded_rows, valid_rows = [], []
    for _, row in buildings_df.iterrows():
        ghg  = pd.to_numeric(row.get("GHG Emissions (kgCO2e)"), errors="coerce")
        sqft = pd.to_numeric(row.get("Gross Floor Area"), errors="coerce")
        missing_ghg  = pd.isna(ghg)
        missing_sqft = pd.isna(sqft) or sqft <= 0

        status = str(row.get("Compliance Status", "")).strip().lower()
        gov = government_status(status)
        if gov:
            excluded_rows.append(_excluded(
                row, f"{gov} record: BERDO treatment unconfirmed, so left out of the portfolio"))
            continue
        cov = coverage_for(row.get("First Compliance Year"), status, row.get("Property Owner Name"))
        if not period_covered(cov, 0):
            excluded_rows.append(_excluded(
                row, f"Not yet covered: no emissions limit until {cov['applies_from']} emissions"
                if cov["known"] else "First compliance year not reported"))
            continue
        if missing_ghg or missing_sqft:
            if missing_ghg and missing_sqft:
                if status in ("not submitted", "not reported"):
                    reason = "Did not report: no GHG data or floor area submitted"
                elif status == "pending revisions":
                    reason = "Pending revisions: GHG data and floor area incomplete"
                else:
                    reason = "Missing GHG emissions and floor area"
            elif missing_ghg:
                if status in ("not submitted", "not reported"):
                    reason = "Did not report: no GHG data submitted"
                elif status == "pending revisions":
                    reason = "Pending revisions: GHG data incomplete"
                else:
                    reason = "Missing GHG emissions data"
            else:
                reason = "Missing floor area"
            excluded_rows.append(_excluded(row, reason))
        else:
            valid_rows.append(row)
    valid = pd.DataFrame(valid_rows) if valid_rows else pd.DataFrame()
    return valid, excluded_rows


def portfolio_summary(valid: pd.DataFrame) -> dict:
    """
    Portfolio totals, blended standard, and ACP exposure.
    `blended_limits` is None when no building's use can be mapped to a BERDO standard.

    periods: for each compliance period, the blended limit, gap, compliance, excess
    tons, and annual ACP (excess tons rounded to 0.1 before applying the ACP rate).
    chart_fines: annual ACP per period from the unrounded excess, as charted.
    total_5yr: cumulative ACP across non-compliant five-year periods through 2049.
    indefinite_annual_fine: annual ACP from 2050 onward, if over the 2050+ limit.
    """
    valid = valid.copy()
    valid["Gross Floor Area"]       = pd.to_numeric(valid["Gross Floor Area"], errors="coerce")
    valid["GHG Emissions (kgCO2e)"] = pd.to_numeric(valid["GHG Emissions (kgCO2e)"], errors="coerce")
    total_sqft      = valid["Gross Floor Area"].sum()
    total_emissions = valid["GHG Emissions (kgCO2e)"].sum()
    intensity       = round(total_emissions / total_sqft, 4)
    out = {"valid": valid, "total_sqft": total_sqft, "total_emissions": total_emissions,
           "intensity": intensity, "blended_limits": calculate_blended_standard(valid)}
    limits = out["blended_limits"]
    if limits is None:
        return out

    periods = []
    for i, limit in enumerate(limits):
        gap = round(intensity - limit, 4)
        compliant = gap <= 0
        excess_tons = 0.0 if compliant else round(gap * total_sqft / 1000, 1)
        periods.append({"period": COMPLIANCE_PERIODS[i], "limit": limit, "gap": gap,
                        "compliant": compliant, "excess_tons": excess_tons,
                        "annual_fine": 0.0 if compliant else round(excess_tons * ACP_RATE, 0)})
    non_compliant = [(i, limits[i]) for i in range(len(COMPLIANCE_PERIODS)) if intensity > limits[i]]
    finite = [(i, lim) for i, lim in non_compliant if COMPLIANCE_PERIODS[i] != "2050+"]
    indefinite_limit = next((lim for i, lim in non_compliant if COMPLIANCE_PERIODS[i] == "2050+"), None)
    out.update({
        "periods": periods,
        "chart_fines": [round(max((intensity - lim) * total_sqft / 1000, 0) * ACP_RATE, 0) for lim in limits],
        "non_compliant_periods": non_compliant,
        "finite_non_compliant": finite,
        "total_5yr": sum(round(max(intensity - lim, 0) * total_sqft / 1000, 1) * ACP_RATE * 5
                         for _, lim in finite),
        "indefinite_annual_fine": (round(max(intensity - indefinite_limit, 0) * total_sqft / 1000, 1) * ACP_RATE
                                   if indefinite_limit is not None else 0.0),
    })
    return out


def portfolio_electricity_share(valid: pd.DataFrame, total_emissions, sidebar_share, use_reported=True):
    """
    Emissions-weighted electricity share for the grid scenario: each building's
    reported share where available, the sidebar estimate for the rest.
    Returns (share, plain-language source).
    """
    share, source = sidebar_share, "sidebar estimate"
    if use_reported and total_emissions > 0:
        elec_kg, n_reported = 0.0, 0
        for _, r in valid.iterrows():
            s, _ = building_elec_share(r.get("GHG Emissions (kgCO2e)"), r.get("Electricity Emissions (kgCO2e)"))
            if s is None:
                s = sidebar_share
            else:
                n_reported += 1
            elec_kg += s * float(r["GHG Emissions (kgCO2e)"])
        if n_reported > 0:
            share = elec_kg / total_emissions
            source = f"reported for {n_reported} of {len(valid)} buildings"
            if n_reported < len(valid):
                source += "; sidebar estimate for the rest"
    return share, source


def worst_building(valid: pd.DataFrame):
    """The building with the largest excess over its own 2025-29 limit: (address, excess tons)."""
    worst_addr, worst_tons = "", 0.0
    for _, row in valid.iterrows():
        intensity = pd.to_numeric(row.get("GHG Intensity (kgCO2e/sqft)"), errors="coerce")
        sqft = pd.to_numeric(row.get("Gross Floor Area"), errors="coerce")
        limits = building_limits(row.get("Property Type"), row.get("All Property Types"))["limits"]
        if pd.isna(intensity) or pd.isna(sqft) or limits is None:
            continue
        tons = round(max(intensity - limits[0], 0) * sqft / 1000, 1)
        if tons > worst_tons:
            worst_tons, worst_addr = tons, str(row.get("Building Address", ""))
    return worst_addr, worst_tons


def building_surplus_deficit(valid: pd.DataFrame) -> pd.DataFrame:
    """
    Each building's surplus (negative) or deficit (positive) against its own limit,
    in metric tons, for 2025, 2030, and 2035, sorted with the largest deficit first.
    """
    rows = []
    for _, row in valid.iterrows():
        sqft = pd.to_numeric(row["Gross Floor Area"], errors="coerce")
        intensity = pd.to_numeric(row["GHG Intensity (kgCO2e/sqft)"], errors="coerce")
        bl = building_limits(row.get("Property Type"), row.get("All Property Types"))
        if pd.isna(sqft) or pd.isna(intensity) or bl["limits"] is None:
            continue
        limit_2025, limit_2030, limit_2035 = bl["limits"][:3]
        gap_tons = lambda lim: round((intensity - lim) * sqft / 1000, 1)
        status = lambda lim: "Pass" if intensity <= lim else "Fail"
        rows.append({
            "Address":        row["Building Address"],
            "Type":           bl["label"],
            "Sq Ft":          f"{int(sqft):,}",
            "GHG (kg/sf/yr)": round(intensity, 3),
            "2025 Limit":     limit_2025, "2025 Gap (MT)": gap_tons(limit_2025), "2025": status(limit_2025),
            "2030 Limit":     limit_2030, "2030 Gap (MT)": gap_tons(limit_2030), "2030": status(limit_2030),
            "2035 Limit":     limit_2035, "2035 Gap (MT)": gap_tons(limit_2035), "2035": status(limit_2035),
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("2025 Gap (MT)", ascending=False).reset_index(drop=True)
