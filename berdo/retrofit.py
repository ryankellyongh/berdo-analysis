"""
Retrofit & Incentives calculations: cost estimates, planned-project impact,
incentive totals and net cost, payback, the ACP schedule, and the retrofit
recommendation. No Streamlit, so these can be tested directly.
"""
from berdo.regulations import (
    ACP_RATE,
    BOSTON_LABOR_MULTIPLIER,
    COMPLIANCE_PERIODS,
    FUEL_EF_KG_PER_KBTU,
    PERIOD_REPRESENTATIVE_YEARS,
    PROJECTED_GRID_EF,
    RETROFIT_COST_PER_SQFT,
)
from berdo.emissions import (
    _estimate_incentive_value,
    effective_grid_ef,
    fuel_to_kbtu,
    period_covered,
)

#Conventions (see tests/test_regressions.py):
#  baseline ACP   what the building owes at current emissions
#  remaining ACP  what it still owes after the project
#  avoided ACP    baseline minus remaining: the only ACP a project "saves"
#  Potential incentives are leads to verify. Only confirmed funding reduces cost.

PAYBACK_CAP_YEARS = 50          #beyond this, avoided ACP is the wrong frame for payback
DEFAULT_ENERGY_SAVINGS_PSF = 1.0   #USD/sq ft/yr, used for the headline payback


def retrofit_cost_estimate(scopes, sqft, has_audit, apply_boston=True) -> dict:
    """
    Cost range for the selected retrofit scopes. With an audit on file, the adjusted
    estimate sits 20% of the way from low to high; without one, 55% (mid-range).
    """
    position = 0.20 if has_audit else 0.55
    multiplier = BOSTON_LABOR_MULTIPLIER if apply_boston else 1.0
    rows, total_low, total_high, total_adjusted = [], 0.0, 0.0, 0.0
    for scope in scopes:
        low_nat, high_nat, _ = RETROFIT_COST_PER_SQFT[scope]
        low_psf, high_psf = low_nat * multiplier, high_nat * multiplier
        adj_psf = low_psf + position * (high_psf - low_psf)
        rows.append({"scope": scope, "low_psf": low_psf, "adj_psf": adj_psf, "high_psf": high_psf,
                     "low_total": low_psf * sqft, "adj_total": adj_psf * sqft, "high_total": high_psf * sqft})
        total_low      += low_psf * sqft
        total_high     += high_psf * sqft
        total_adjusted += adj_psf * sqft
    return {"position": position, "multiplier": multiplier, "rows": rows,
            "total_low": total_low, "total_high": total_high, "total_adjusted": total_adjusted}


def first_year_reduction_kg(fuel, unit, amount, year=None) -> float:
    """
    Annual kg CO2e avoided by saving `amount` of a fuel. Electricity uses the BERDO
    effective grid factor for `year` (default: the 2025-29 representative year).
    """
    kbtu = fuel_to_kbtu(fuel, unit, amount)
    if fuel == "Electricity":
        ef = effective_grid_ef(PERIOD_REPRESENTATIVE_YEARS[0] if year is None else year) / 1000 / 3.412
    else:
        ef = FUEL_EF_KG_PER_KBTU[fuel]
    return kbtu * ef


def planned_project_impact(reduction_kg, sqft, current_intensity, limit_2025) -> dict:
    """Whether a project's annual reduction closes the 2025-29 gap, and by how much."""
    intensity_reduction = reduction_kg / sqft
    new_intensity = max(current_intensity - intensity_reduction, 0)
    gap_before = current_intensity - limit_2025
    gap_after = new_intensity - limit_2025
    out = {"intensity_reduction": intensity_reduction, "new_intensity": new_intensity,
           "gap_before": gap_before, "gap_after": gap_after, "closes_gap": gap_after <= 0,
           "pct_closed": None, "remaining_mt": None}
    if gap_after > 0 and gap_before > 0:
        out["pct_closed"] = min(round((gap_before - gap_after) / gap_before * 100, 0), 100)
        out["remaining_mt"] = round(gap_after * sqft / 1000, 1)
    return out


def estimate_incentives(matched, sqft):
    """
    Dollar estimates for matched incentives. Returns copies of the incentive entries
    with _est_low and _est_high added (the shared program table isn't modified),
    plus the low and high totals.
    """
    out = []
    for inc in matched:
        low, high = _estimate_incentive_value(inc, sqft)
        out.append({**inc, "_est_low": low, "_est_high": high})
    return out, sum(i["_est_low"] for i in out), sum(i["_est_high"] for i in out)


def net_retrofit_cost(cost_low, cost_high, confirmed_funding=0.0):
    """
    Net cost range after funding the owner has actually secured. Returns (low, high).
    Potential incentives (estimate_incentives) are never subtracted: their eligibility
    and amounts are unverified until a program confirms them.
    """
    confirmed = max(float(confirmed_funding or 0.0), 0.0)
    return max(cost_low - confirmed, 0.0), max(cost_high - confirmed, 0.0)


def remaining_acp(new_intensity, sqft, limit, covered=True):
    """Annual ACP still owed after a project (0.0 if within the limit), or None if unknown."""
    if new_intensity is None or sqft is None or limit is None or not covered:
        return None
    return round(max(float(new_intensity) - limit, 0.0) * float(sqft) / 1000 * ACP_RATE, 2)


def avoided_acp(baseline_acp, remaining):
    """Avoided ACP = baseline ACP minus remaining ACP, or None if either is unknown."""
    if baseline_acp is None or remaining is None:
        return None
    return max(float(baseline_acp) - float(remaining), 0.0)


def headline_payback(net_low, avoided, sqft):
    """
    Payback for the headline sentence: net cost / (avoided ACP + USD 1/sq ft/yr energy savings).
    `avoided` is avoided ACP (baseline minus remaining), not the baseline ACP.
    Returns ("years", value), ("energy_driven", None), ("covered", None), or (None, None).
    """
    if avoided is None:
        return None, None
    total_return = avoided + DEFAULT_ENERGY_SAVINGS_PSF * sqft
    if avoided > 0 and total_return > 0 and net_low > 0:
        years = net_low / total_return
        return ("years", round(years, 1)) if years <= PAYBACK_CAP_YEARS else ("energy_driven", None)
    if avoided > 0 and net_low == 0:
        return "covered", None
    return None, None


def payback_estimates(net_low, net_high, avoided, energy_savings_annual, horizon_years=15) -> dict:
    """
    Simple paybacks (years, rounded to 0.1 only for display; 0 when the net cost is zero)
    from avoided ACP alone and from avoided ACP plus energy savings, and cumulative cash flows.

    `avoided` is avoided ACP = baseline ACP minus remaining ACP after the project.
    Passing the baseline ACP instead would assume the project removes every excess ton.
    A payback that can't be computed (no benefit) is None.
    """
    avoided = float(avoided or 0.0)
    benefit = avoided + energy_savings_annual
    years = list(range(0, horizon_years + 1))

    def _pb(cost, annual):
        if cost <= 0:
            return 0.0
        return round(cost / annual, 1) if annual > 0 else None

    return {
        "avoided_acp": avoided,
        "total_annual_benefit": benefit,
        "low_acp_only":  _pb(net_low, avoided),
        "high_acp_only": _pb(net_high, avoided),
        "low_combined":  _pb(net_low, benefit),
        "high_combined": _pb(net_high, benefit),
        "years": years,
        "cash_low_acp":    [-net_low + avoided * y for y in years],
        "cash_high_acp":   [-net_high + avoided * y for y in years],
        "cash_low_total":  [-net_low + benefit * y for y in years],
        "cash_high_total": [-net_high + benefit * y for y in years],
    }


def acp_schedule(current_intensity, sqft, limits, coverage, n_periods=5):
    """Annual and five-year ACP for each period through 2045-49, if emissions stay flat."""
    rows = []
    for i, period in enumerate(COMPLIANCE_PERIODS[:n_periods]):
        gap = max(current_intensity - limits[i], 0) if period_covered(coverage, i) else 0
        excess_tons = gap * sqft / 1000
        rows.append({"period": period, "limit": limits[i],
                     "annual_fine": round(excess_tons * ACP_RATE, 2),
                     "5yr_fine": round(excess_tons * ACP_RATE * 5, 2)})
    return rows


def avoided_acp_schedule(current_intensity, new_intensity, sqft, limits, coverage, n_periods=5):
    """
    Per period: baseline ACP at current emissions, remaining ACP after the project, and
    avoided ACP (baseline minus remaining). Rows also carry "annual_fine"/"5yr_fine" set
    to the AVOIDED amounts, so acp_totals() compares retrofit cost with avoided ACP.
    """
    base = acp_schedule(current_intensity, sqft, limits, coverage, n_periods)
    after = acp_schedule(new_intensity, sqft, limits, coverage, n_periods)
    rows = []
    for b, a in zip(base, after):
        av = max(b["annual_fine"] - a["annual_fine"], 0.0)
        rows.append({"period": b["period"], "limit": b["limit"],
                     "baseline_annual": b["annual_fine"], "remaining_annual": a["annual_fine"],
                     "annual_fine": av, "5yr_fine": av * 5})
    return rows


def acp_totals(annual_acp, schedule, net_low):
    """
    Five-year ACP for the current period, cumulative ACP through two periods and
    through 2049, and the first period in which cumulative ACP reaches the net cost.
    """
    fine_5yr = annual_acp * 5
    cumulative_all = sum(r["5yr_fine"] for r in schedule) if schedule else fine_5yr
    cumulative_10yr = sum(r["5yr_fine"] for r in schedule[:2]) if len(schedule) >= 2 else fine_5yr
    running, crossover = 0, None
    for r in schedule:
        running += r["5yr_fine"]
        if running >= net_low and crossover is None:
            crossover = r["period"]
    return {"fine_5yr": fine_5yr, "cumulative_all": cumulative_all,
            "cumulative_10yr": cumulative_10yr, "crossover_period": crossover}


def retrofit_recommendation(net_low, fine_5yr, cumulative_10yr, cumulative_all) -> str:
    """
    Compare the low net retrofit cost with ACP exposure:
      retrofit_now:  no more than one period of ACP
      retrofit_soon: no more than two periods of ACP
      phase:         no more than cumulative ACP through 2049
      acp_alone_insufficient: more than cumulative ACP
    """
    if net_low == 0 or net_low <= fine_5yr:
        return "retrofit_now"
    if net_low <= cumulative_10yr:
        return "retrofit_soon"
    if net_low <= cumulative_all:
        return "phase"
    return "acp_alone_insufficient"


def rec_break_even_price(year) -> float:
    """
    REC price (USD) at which buying a REC costs the same as paying the ACP for the
    emissions it avoids. Each REC avoids the projected grid factor for that year.
    """
    return ACP_RATE * PROJECTED_GRID_EF[year] / 1000


def rec_inputs(current_intensity, sqft, limit_2025, elec_share):
    """The 2025-29 gap and electricity emissions (kg/yr) used to size a REC purchase."""
    gap_kg = max(current_intensity - limit_2025, 0) * sqft if current_intensity else 0
    elec_kg = (current_intensity or 0) * sqft * elec_share
    return gap_kg, elec_kg
