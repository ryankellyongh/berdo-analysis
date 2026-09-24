"""
BERDO calculations: limits, blended standards, coverage, compliance gaps,
screening status, grid projections, RECs, and the Emissions Planner model.

Pure functions (no Streamlit), so they can be tested directly.
"""
import pandas as pd
import re
import math
from berdo.regulations import (
    ACP_RATE,
    BERDO_LINKS,
    BERDO_STANDARDS,
    COMPLIANCE_PERIODS,
    FLEX_DEADLINES,
    GOVERNMENT_STATUSES,
    PERIOD_REPRESENTATIVE_YEARS,
    PERIOD_START_YEARS,
    PLANNER_PERIOD_START_YEARS,
    PLANNER_PERIOD_YEARS,
    PROJECTED_GRID_EF,
    PROPERTY_TYPE_MAP,
    REC_CONNECTOR_DEADLINE,
    REC_CONNECTOR_TIERS,
    RPS_CLASS_I,
    _EF_MAX_YR,
    _EF_MIN_YR,
    _RPS_MAX_YR,
    _RPS_MIN_YR,
)


def rps_class_i(year: int) -> float:
    return RPS_CLASS_I.get(min(max(year, _RPS_MIN_YR), _RPS_MAX_YR), 0.0)


def effective_grid_ef(year: int) -> float:
    """
    BERDO-effective grid EF in kg CO2e/MWh, after the RPS Class I offset.
    This, not the raw Appendix B value, is what BERDO bills electricity at.
    """
    clamped = min(max(year, _EF_MIN_YR), _EF_MAX_YR)
    return PROJECTED_GRID_EF[clamped] * (1.0 - rps_class_i(clamped))

def rec_pathway(gap_kg, elec_emissions_kg, year, rec_price):
    """
    Cost of closing a compliance gap with MA Class I RECs instead of ACP.
    RECs offset electricity emissions only; any fossil residual still pays ACP.

    Each REC avoids the raw projected factor E (not E × (1 − RPS)), because RECs
    cover grid electricity not already matched by the RPS. The most a building can
    abate is its electricity emissions, which already reflect (1 − RPS). So using
    PROJECTED_GRID_EF here, and effective_grid_ef() elsewhere, is intentional.
    Returns a dict, or None if there is no gap.
    """
    if gap_kg <= 0:
        return None
    ef = PROJECTED_GRID_EF[min(max(year, _EF_MIN_YR), _EF_MAX_YR)]
    abatable_kg = min(gap_kg, max(elec_emissions_kg, 0.0))
    recs        = abatable_kg / ef
    residual_kg = gap_kg - abatable_kg
    residual_acp = residual_kg / 1000 * ACP_RATE
    return {
        "recs_needed":   recs,
        "rec_cost":      recs * rec_price,
        "residual_acp":  residual_acp,
        "total_cost":    recs * rec_price + residual_acp,
        "acp_only":      gap_kg / 1000 * ACP_RATE,
        "breakeven_price": ACP_RATE * ef / 1000,
        "fully_covered": residual_kg <= 0,
    }


def _normalize(raw: str) -> str:
    """
    Lowercase, collapse whitespace, and normalize punctuation spacing so that
    'Residence Hall / Dormitory', 'Residence Hall/Dormitory', and
    'residence  hall/dormitory' all resolve to the same key.
    """
    s = raw.strip().lower()
    s = re.sub(r"\s+", " ", s)          #collapse runs of whitespace
    s = re.sub(r"\s*/\s*", "/", s)      #' / ' -> '/'
    s = re.sub(r"\s*-\s*", " - ", s)    #normalize the ESPM 'Other - X' dash
    s = re.sub(r"\s+", " ", s).strip()
    return s

def project_ghg_intensities(ghg_intensity, elec_share, base_year):
    """
    Electricity component scales by the ratio of BERDO-effective grid EFs
    (Appendix B factor × (1 − RPS Class I)); fossil component held constant.
    """
    base_ef = effective_grid_ef(base_year)
    if base_ef <= 0:
        return [ghg_intensity] * len(COMPLIANCE_PERIODS)

    elec_intensity   = ghg_intensity * elec_share
    fossil_intensity = ghg_intensity * (1.0 - elec_share)

    projected = []
    for yr in PERIOD_REPRESENTATIVE_YEARS:
        future_elec = elec_intensity * (effective_grid_ef(yr) / base_ef)
        projected.append(round(fossil_intensity + future_elec, 3))
    return projected

def building_elec_share(total_kg, elec_kg):
    """
    Share of a building's reported GHG emissions that comes from grid electricity:
    City-reported electricity emissions ÷ reported total emissions.

    Returns (share, note). share is None when it can't be determined, e.g. the
    2023 dataset has no fuel-level emissions. note explains any adjustment.
    """
    total = pd.to_numeric(total_kg, errors="coerce")
    elec  = pd.to_numeric(elec_kg,  errors="coerce")
    if total is None or elec is None or pd.isna(total) or pd.isna(elec) or total <= 0:
        return None, None
    if elec < 0:
        return 0.0, (
            "Reported electricity emissions are negative, likely from on-site "
            "generation exported to the grid. Electricity share set to 0% for the "
            "grid scenario. Verify."
        )
    share = elec / total
    if share > 1:
        return 1.0, "Electricity emissions exceed the reported total; share capped at 100%. Verify."
    return round(float(share), 3), None


def fmt_share(share) -> str:
    """Format an electricity share consistently: one decimal under 10% (0.6%), else whole (37%)."""
    if share is None or pd.isna(share):
        return "Not reported"
    return f"{share:.1%}" if 0 < share < 0.10 else f"{share:.0%}"


def resolve_elec_share(prefill, sidebar_share, use_reported=True):
    """
    Electricity share for the Retrofit and Planner tabs, with a plain-language
    source. Prefers the looked-up building's reported share.
    """
    prefill = prefill or {}
    reported = prefill.get("elec_share")
    if use_reported and reported is not None:
        yr = prefill.get("elec_share_year")
        return reported, f"this building's reported {yr} data" if yr else "this building's reported data"
    if sidebar_share is not None:
        return sidebar_share, "sidebar estimate"
    return 0.5, "default estimate; no reported breakdown available"


def planner_period_for_year(y: int) -> int:
    for i in range(len(PLANNER_PERIOD_START_YEARS) - 1, -1, -1):
        if y >= PLANNER_PERIOD_START_YEARS[i]:
            return i
    return 0


def planner_model(baseline_intensity, sqft, limits, projects, covered,
                  apply_grid=False, elec_share=0.5, base_year=2025):
    """
    Every number the Emissions Planner shows, computed without Streamlit.

    baseline_intensity  kg CO2e/sf/yr (the planner's editable field)
    limits              six period limits (kg CO2e/sf/yr)
    projects            dicts with year, reduction_kg (first-year kg), elec_mwh (MWh/yr, 0 if not electricity)
    covered             six booleans: whether an emissions limit applies in each period
    apply_grid          grid decarbonization scenario on/off
    elec_share          share of baseline emissions from grid electricity
    base_year           year of the baseline energy use (grid factor the baseline reflects)

    Rules:
      - Projects count from their implementation year onward, never earlier.
      - Fossil savings are fixed; electricity savings are MWh x that year's grid factor
        (the same factor the baseline uses), capped at the building's electricity emissions.
      - ACP only in covered periods. Cumulative totals are summed year by year when
        projects are involved; "2050+" is excluded from cumulative totals (no end date).
    """
    n = len(COMPLIANCE_PERIODS)
    E = baseline_intensity * sqft
    if apply_grid:
        grid_kg = [pi * sqft for pi in project_ghg_intensities(baseline_intensity, elec_share, base_year)]
    else:
        grid_kg = [E] * n
    active = [p for p in projects if p.get("reduction_kg", 0) > 0]
    capped_years = set()
    base_ef = effective_grid_ef(base_year)

    def grid_ef_for_year(y):
        if apply_grid:
            return effective_grid_ef(PERIOD_REPRESENTATIVE_YEARS[planner_period_for_year(y)])
        return base_ef

    def reduction_in_year(y):
        live = [p for p in active if p["year"] <= y]
        fossil = sum(p["reduction_kg"] for p in live if not p.get("elec_mwh"))
        ef = grid_ef_for_year(y)
        elec = sum(p["elec_mwh"] for p in live if p.get("elec_mwh")) * ef
        elec_cap = E * elec_share * ef / base_ef
        if elec > elec_cap:
            capped_years.add(y)
            elec = elec_cap
        return fossil + elec

    def yearly_acp(base_kg, i):
        limit_kg = limits[i] * sqft
        return [max(base_kg - reduction_in_year(y) - limit_kg, 0) / 1000 * ACP_RATE
                for y in PLANNER_PERIOD_YEARS[i]]

    def avg_yearly_acp(base_kg, i):
        vals = yearly_acp(base_kg, i)
        return sum(vals) / len(vals)

    period_reductions = [sum(reduction_in_year(y) for y in yrs) / len(yrs) for yrs in PLANNER_PERIOD_YEARS]
    has_projects = any(r > 0 for r in period_reductions)
    finite = [i for i in range(n) if COMPLIANCE_PERIODS[i] != "2050+" and covered[i]]

    def flat_acp(base_kg, i):
        return max(base_kg - limits[i] * sqft, 0) / 1000 * ACP_RATE

    def all_years_ok(base_kg, i):
        return all(base_kg - reduction_in_year(y) <= limits[i] * sqft for y in PLANNER_PERIOD_YEARS[i])

    fines = {
        "baseline": [round(flat_acp(E, i), 0) * covered[i] for i in range(n)],
        "grid":     [round(flat_acp(grid_kg[i], i), 0) * covered[i] for i in range(n)],
        "projects": [round(avg_yearly_acp(E, i), 0) * covered[i] for i in range(n)],
        "combined": [round(avg_yearly_acp(grid_kg[i], i), 0) * covered[i] for i in range(n)],
    }
    cumulative = {
        "baseline": sum(flat_acp(E, i) * 5 for i in finite),
        "grid":     sum(flat_acp(grid_kg[i], i) * 5 for i in finite),
        "projects": sum(sum(yearly_acp(E, i)) for i in finite),
        "combined": sum(sum(yearly_acp(grid_kg[i], i)) for i in finite),
    }
    compliant = {
        "baseline": sum(1 for i in range(n) if E <= limits[i] * sqft),
        "projects": sum(1 for i in range(n) if all_years_ok(E, i)),
        "grid":     sum(1 for i in range(n) if grid_kg[i] <= limits[i] * sqft),
        "combined": sum(1 for i in range(n) if all_years_ok(grid_kg[i], i)),
    }
    return {
        "total_emissions_kg": E,
        "grid_emissions_kg": grid_kg,
        "period_reductions_kg": period_reductions,
        "has_projects": has_projects,
        "reduction_in_year": reduction_in_year,
        "elec_capped_years": capped_years,
        "fines": fines,
        "cumulative": cumulative,
        "current_annual_fine": flat_acp(E, 0) if covered[0] else 0.0,
        "compliant_periods": compliant,
    }


def map_property_type(raw_type):
    """
    Return the BERDO Building Use for an ESPM property type, or None if the
    type is not in Appendix A. None is a meaningful result: it means a human
    needs to classify the building, not that the building is exempt.
    """
    if raw_type is None or not isinstance(raw_type, str):
        return None
    key = _normalize(raw_type)
    hit = PROPERTY_TYPE_MAP.get(key)
    if hit:
        return hit
    #Retry without the normalized dash spacing, for keys stored tightly.
    return PROPERTY_TYPE_MAP.get(key.replace(" - ", "-"))


#Mixed-use buildings
#BERDO sets a mixed-use building's limit as the floor-area-weighted average of
#the limits for each of its uses. The 2024+ datasets report floor area by use in
#"All Property Types and GFAs", e.g. "Office (26744),Laboratory (85744)".
#Earlier years list the uses without floor areas, so the blend can't be computed.

_USE_WITH_GFA = re.compile(r"\s*,?\s*(.+?)\s*\((\d[\d,]*\.?\d*)\)")


def _is_parking(name) -> bool:
    return "parking" in str(name).lower()


def _split_top_level(raw: str) -> list:
    """Split a comma-separated list, ignoring commas inside parentheses."""
    parts, depth, cur = [], 0, ""
    for ch in raw:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0)
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return [p for p in parts if p]


def parse_property_uses(raw) -> list:
    """
    Parse reported uses WITH floor areas into
    [{"ESPM use", "BERDO category", "Sq ft"}, ...].
    Returns [] when the field is empty or lists no floor areas (pre-2024 data).
    """
    if not isinstance(raw, str) or "(" not in raw:
        return []
    uses = []
    for m in _USE_WITH_GFA.finditer(raw):
        name = m.group(1).strip().strip(",").strip()
        try:
            sqft = float(m.group(2).replace(",", ""))
        except ValueError:
            continue
        if sqft > 0:
            uses.append({
                "ESPM use": name,
                "BERDO category": map_property_type(name),
                "Sq ft": sqft,
            })
    return uses


def blend_limits_by_area(uses, primary_threshold=0.10):
    """
    Blended Emissions Standard per BERDO Policies & Procedures v5, section 6:
        BES = [sum(SF_i × ES_i) over primary uses + SF_np × ES_1] / total SF
    A use is primary only if it occupies at least 10% of floor area (ordinance
    section (i)). Smaller uses, and uses with no BERDO category, are non-primary
    and count at the limit of the largest primary use (ES_1).

    The ordinance also lets a use qualify as primary if it accounts for more than
    10% of energy use or emissions. Public data can't show that, so a small but
    energy-intensive use may be treated as non-primary here.

    Returns (limits or None, total_sqft, non_primary_sqft, n_primary_uses).
    """
    rows = []
    for u in uses:
        sq = pd.to_numeric(u.get("Sq ft"), errors="coerce")
        if sq is None or pd.isna(sq) or sq <= 0:
            continue
        rows.append((u.get("BERDO category"), float(sq)))
    total = sum(sq for _, sq in rows)
    if total == 0:
        return None, 0.0, 0.0, 0

    by_cat = {}
    for cat, sq in rows:
        if cat in BERDO_STANDARDS:
            by_cat[cat] = by_cat.get(cat, 0.0) + sq
    primary = {c: sq for c, sq in by_cat.items() if sq / total >= primary_threshold}
    if not primary:
        return None, total, total, 0

    largest = max(primary, key=primary.get)
    non_primary = total - sum(primary.values())
    weighted = [0.0] * len(COMPLIANCE_PERIODS)
    for cat, sq in primary.items():
        for i, lim in enumerate(BERDO_STANDARDS[cat]):
            weighted[i] += lim * sq
    for i, lim in enumerate(BERDO_STANDARDS[largest]):
        weighted[i] += lim * non_primary
    return [round(w / total, 3) for w in weighted], total, non_primary, len(primary)


def building_limits(property_type, all_property_types=None, exclude_parking=True):
    """
    Decide which limits apply to a building.

    Per the City's BERDO page, buildings comply with the standard for their
    LARGEST PRIMARY USE by default; mixed-use buildings MAY adopt a Blended
    Emissions Standard weighted by the floor area of each primary use.
    So "limits" is always the default, and "blended" is the optional alternative.

    basis:
      "blended"      more than one BERDO category with reported floor areas
                     (a blended standard can be estimated)
      "multi_no_gfa" more than one category listed, but no floor areas (pre-2024)
      "largest_use"  single use

    Parking is excluded from the blend by default, which keeps limits the same
    as the previous single-use logic for e.g. "Multifamily Housing, Parking".
    Verify parking treatment against the BERDO regulations.
    """
    largest_cat = map_property_type(property_type)
    notes = []

    uses = parse_property_uses(all_property_types)
    if exclude_parking:
        uses = [u for u in uses if not _is_parking(u["ESPM use"])]
    mapped_cats = {u["BERDO category"] for u in uses if u["BERDO category"]}

    default_limits = BERDO_STANDARDS.get(largest_cat) if largest_cat else None

    blended, _, non_primary, n_primary = (blend_limits_by_area(uses)
                                          if len(mapped_cats) > 1 else (None, 0, 0, 0))
    if n_primary > 1:
        notes.append(
            f"Mixed-use: default limit is the largest use ({largest_cat or 'unmapped'}). "
            f"A Blended Emissions Standard, if adopted, would be about "
            f"{blended[0]:.2f} for 2025–29"
        )
        if non_primary > 0:
            notes.append(
                f"{non_primary:,.0f} sq ft of smaller or unclassified uses counts at the "
                "largest primary use's limit, per the City's blended standard formula"
            )
        return {"limits": default_limits, "label": largest_cat,
                "category": largest_cat, "basis": "blended", "blended": blended,
                "uses": uses, "listed_names": [], "notes": notes}

    listed_names = []
    if isinstance(all_property_types, str) and not uses:
        listed_names = _split_top_level(all_property_types)
        if exclude_parking:
            listed_names = [n for n in listed_names if not _is_parking(n)]
    listed_cats = {map_property_type(n) for n in listed_names} - {None}

    if len(listed_cats) > 1:
        basis = "multi_no_gfa"
        notes.append(
            "Mixed-use: floor area by use not reported this year, so a Blended "
            "Emissions Standard can't be estimated"
        )
    else:
        basis = "largest_use"
        listed_names = []

    return {"limits": default_limits,
            "label": largest_cat, "category": largest_cat, "basis": basis,
            "blended": None,
            "uses": uses, "listed_names": listed_names, "notes": notes}


def limits_for_category(berdo_category, prefill):
    """
    Limits for the Retrofit and Planner tabs: use the blended limits carried
    over from Address Lookup when the tab is still showing that building's
    category; otherwise fall back to the single-category standard.
    """
    prefill = prefill or {}
    if prefill.get("limits") and berdo_category == prefill.get("berdo_category"):
        return prefill["limits"]
    return BERDO_STANDARDS[berdo_category]

_CITY_OWNER = re.compile(r"^\s*CITY OF BOSTON\b|BOSTON HOUSING AUTH", re.IGNORECASE)


def is_city_building(owner_name) -> bool:
    """
    Ordinance definition: owned by the City, or the City pays all energy bills;
    includes buildings owned or managed by the Boston Housing Authority. Public data
    only shows the owner, so this detects City and BHA ownership by name.
    """
    return isinstance(owner_name, str) and bool(_CITY_OWNER.search(owner_name))


def coverage_for(compliance_year=None, compliance_status=None, owner_name=None) -> dict:
    """
    Whether and when an emissions limit applies.
      applies_from: first data year a limit applies (2025 or 2030), or None
      known:        False for state/federal records or a missing compliance year
      city:         City Building; ordinance section (r) daily fines don't apply
    Per the ordinance, buildings of 20,000-35,000 sq ft or 15-34 units are not subject
    to the standards until 2030 emissions; the City's "First Emissions Compliance Year
    (Projected)" field records this.
    """
    gov = government_status(compliance_status)
    city = is_city_building(owner_name) and not gov
    cy = pd.to_numeric(compliance_year, errors="coerce")
    if gov:
        return {"applies_from": None, "known": False, "gov": gov, "city": False,
                "reason": f"Not assessed ({gov.lower()})"}
    if cy is None or pd.isna(cy):
        return {"applies_from": None, "known": False, "gov": None, "city": city,
                "reason": "Coverage year not reported"}
    return {"applies_from": int(cy), "known": True, "gov": None, "city": city, "reason": None}


def period_covered(cov, i) -> bool:
    """True if a limit applies in compliance period i. No coverage info = assume it applies."""
    if cov is None:
        return True
    return bool(cov["known"]) and PERIOD_START_YEARS[i] >= cov["applies_from"]


def coverage_label(cov, i) -> str:
    """Short label for a period where no limit applies."""
    if cov and cov.get("gov"):
        return "Not assessed"
    if cov and not cov.get("known"):
        return "Coverage unknown"
    return "Not yet covered"


def calculate_compliance_gap(ghg_intensity, sqft, berdo_category, limits=None, coverage=None):
    """
    Gap to the limit in each period. When `coverage` says no limit applies in a
    period, the gap is still reported for reference, but the period is marked
    covered=False and carries no excess tons or ACP.
    """
    if limits is None:
        limits = BERDO_STANDARDS.get(berdo_category)
    if limits is None:
        return []

    results = []
    for i, period in enumerate(COMPLIANCE_PERIODS):
        limit = limits[i]
        gap = round(ghg_intensity - limit, 3)
        compliant = gap <= 0
        covered = period_covered(coverage, i)
        excess_tons = 0.0 if (compliant or not covered) else round(gap * sqft / 1000, 1)
        fine = 0.0 if (compliant or not covered) else round(excess_tons * ACP_RATE, 0)
        results.append({
            "period": period,
            "limit": limit,
            "gap": gap,
            "compliant": compliant,
            "covered": covered,
            "excess_metric_tons": excess_tons,
            "annual_fine_usd": fine,
        })
    return results


def coverage_from_prefill(prefill) -> dict:
    """Coverage carried from Address Lookup; manual entries are assumed covered from 2025."""
    prefill = prefill or {}
    if "coverage" in prefill and prefill["coverage"]:
        return prefill["coverage"]
    return {"applies_from": 2025, "known": True, "gov": None, "city": False, "reason": None}


#Compliance pathways

def get_compliance_pathways(ctx: dict) -> list:
    """
    Every BERDO compliance mechanism and flexibility measure, with official links
    and a plain-text note on why each may or may not fit this building.
    Used by the on-screen pathways section and the PDF summary.

    ctx keys (all optional): over_now, fails_later, blend_available, blend_fixes,
    owner_building_count, elec_share.
    Nothing here is an eligibility determination; it points owners to options.
    """
    over_now    = ctx.get("over_now", False)
    fails_later = ctx.get("fails_later", False)
    n_owned     = ctx.get("owner_building_count", 0) or 0
    elec_share  = ctx.get("elec_share")

    def L(*pairs):
        return [(label, BERDO_LINKS[key]) for label, key in pairs]

    if ctx.get("blend_fixes"):
        blend_why, blend_strong = ("adopting a blended standard would bring this building "
                                   "under its 2025–29 limit.", True)
    elif ctx.get("blend_available"):
        blend_why, blend_strong = ("this building reports more than one use; compare the "
                                   "default and blended limits.", False)
    else:
        blend_why, blend_strong = ("only one primary use is reported, so this likely "
                                   "doesn't apply.", False)

    if n_owned > 1:
        port_why = (f"this owner name appears on {n_owned} buildings in the dataset. Owner "
                    "names in public data can be inconsistent; verify.")
    else:
        port_why = "only one building found under this owner name in the dataset."

    return [
        {"group": "Ways to comply", "name": "Reduce emissions",
         "what": "Improve efficiency and move away from fossil fuels. This is the only "
                 "option that lowers emissions permanently.",
         "approval": "None",
         "deadline": "Ongoing; plan around equipment replacement cycles",
         "links": L(("Retrofit Resource Hub", "retrofit_hub"),
                    ("Building Decarbonization Advisor Program", "advisor_program")),
         "why": "model projects in the Retrofit & Incentives and Emissions Planner tabs.",
         "strong": over_now or fails_later},
        {"group": "Ways to comply", "name": "Renewable energy (RECs, PPAs)",
         "what": "Buy eligible renewable energy to offset electricity emissions. "
                 "It does not offset fossil fuel emissions.",
         "approval": "None; eligibility rules apply",
         "deadline": f"REC Connector purchases for 2025 emissions: {REC_CONNECTOR_DEADLINE}",
         "links": L(("Renewable Energy quick guide", "renewable_guide"),
                    ("MA Class I REC Connector Program", "rec_connector")),
         "why": (f"electricity is about {fmt_share(elec_share)} of reported emissions, so renewables "
                 "can address at most that share." if elec_share is not None else
                 "the electricity share isn't reported for this year; RECs only cover electricity."),
         "strong": False},
        {"group": "Ways to comply", "name": "Alternative Compliance Payment (ACP)",
         "what": f"Pay USD {ACP_RATE} per metric ton CO2e over the limit (the rate this tool "
                 "uses). Payments go to the Equitable Emissions Investment Fund for "
                 "projects in environmental justice communities.",
         "approval": "None",
         "deadline": "Annual, with emissions compliance",
         "links": L(("Equitable Emissions Investment Fund", "eeif")),
         "why": "this tool estimates ACP exposure in the compliance gap analysis.",
         "strong": over_now},
        {"group": "Flexibility measures", "name": "Blended Emissions Standard",
         "what": "Mixed-use buildings may use a limit weighted by the floor area of "
                 "each primary use instead of the largest-use default.",
         "approval": "No Review Board approval listed; follow the City's template",
         "deadline": "With annual reporting",
         "links": L(("Building-level blended standard template", "blended_template"),
                    ("Flexibility Measures quick guide", "flex_guide")),
         "why": blend_why, "strong": blend_strong},
        {"group": "Flexibility measures", "name": "Building Portfolio",
         "what": "An owner groups their BERDO buildings and complies with one "
                 "portfolio-wide blended standard. All buildings must have the same owner.",
         "approval": "BERDO Review Board",
         "deadline": f"September 1 each year. Next: {_fmt_deadline('portfolio_ics')}",
         "links": L(("Apply (application portal)", "apply_portal"),
                    ("Portfolio blended standard template", "portfolio_template")),
         "why": port_why, "strong": n_owned > 1 and over_now},
        {"group": "Flexibility measures", "name": "Individual Compliance Schedule",
         "what": "Owners who have tracked historical emissions can choose a baseline "
                 "year and follow a custom timeline: 50% reduction by 2030 and net zero "
                 "by 2050 from that baseline.",
         "approval": "BERDO Review Board",
         "deadline": f"September 1 each year. Next: {_fmt_deadline('portfolio_ics')}",
         "links": L(("Apply (application portal)", "apply_portal"),
                    ("ICS eligibility template", "ics_template")),
         "why": "may help if the building has already cut emissions since an earlier "
                "baseline year. Public data can't show this; check your own records.",
         "strong": False},
        {"group": "Flexibility measures", "name": "Hardship Compliance Plan",
         "what": "Owners facing an eligible financial or technical hardship can request "
                 "an alternative timeline and/or more flexible targets. Under-resourced "
                 "owners can use a streamlined short-term application.",
         "approval": "BERDO Review Board",
         "deadline": (f"Short-term: October 1. Next: {_fmt_deadline('short_term_hcp')}. "
                      f"Long-term: July 1. Next: {_fmt_deadline('long_term_hcp')}"),
         "links": L(("Guidance & FAQ", "hcp_guide"),
                    ("Streamlined option for under-resourced owners", "hcp_streamlined")),
         "why": "public data can't show financial or technical hardship; review the "
                "eligibility criteria in the guidance.",
         "strong": False},
    ]


#One-page PDF summary

def reporting_status_label(raw) -> str:
    """
    Plain-language label for the City's "Reporting Compliance Status". That field is
    about the annual report only, not emissions limits, so the label says so.
    """
    s = str(raw or "").strip().lower()
    labels = {
        "in compliance":     "Submitted and accepted (City status: in compliance)",
        "not submitted":     "Not submitted (City status: not submitted)",
        "pending revisions": "Submitted, awaiting City acceptance (City status: pending revisions)",
        "state":             "City status: state (verify BERDO treatment)",
        "federal":           "City status: federal (verify BERDO treatment)",
    }
    return labels.get(s, "Not reported" if s in ("", "nan", "none") else f"City status: {s}")


def government_status(raw):
    """Return 'State' or 'Federal' for those City statuses, otherwise None."""
    return GOVERNMENT_STATUSES.get(str(raw or "").strip().lower())


def evaluate_building(row):
    """
    Returns (data_status, berdo_status, acp_2025, notes).

    Two independent flags rather than one blended score: a building that
    didn't report needs outreach; a building over its limit needs retrofit
    capital. Those are different interventions.
    """
    bl        = building_limits(row.get("property_type"), row.get("all_property_types"))
    limits    = bl["limits"]
    ghg       = row["ghg_intensity_kgco2e_sqft"]
    sqft      = row["gross_floor_area"]
    notes     = list(bl["notes"])
    if bool(row.get("is_campus_member")):
        notes.append(
            f"Reported as part of campus {row.get('campus_id')}: per the City, this row may "
            "not reflect the building's full energy use, so its intensity and status are less certain"
        )

    scoreable = (
        limits is not None
        and pd.notna(ghg)
        and pd.notna(sqft)
        and sqft > 0
    )

    #State and federal records: report emissions for reference, don't flag
    gov = government_status(row.get("compliance_status"))
    if gov:
        data_status = f"{gov} record"
        notes.append(
            f"The City's data marks this as a {gov.lower()} building. BERDO's emissions "
            "limits and penalties may not apply the same way; confirm with the City before "
            "treating it as noncompliant"
        )
        if scoreable:
            g0 = calculate_compliance_gap(ghg, sqft, None, limits=limits)[0]
            notes.append(
                f"For reference only: {ghg:.2f} kg/sf/yr vs. a 2025–29 limit of "
                f"{g0['limit']} ({'over' if not g0['compliant'] else 'under'} by "
                f"{abs(g0['gap']):.2f})"
            )
        else:
            notes.append("Emissions data incomplete in the public dataset")
        if pd.notna(sqft) and sqft >= 100_000:
            notes.append("Over 100,000 sq ft: longer retrofit lead time")
        return data_status, f"Not assessed ({gov.lower()})", 0.0, notes

    #Flag 1: data status
    if row["compliance_status"] == "not submitted":
        data_status = "Not submitted"
        notes.append("Did not report by the deadline; daily reporting fines may apply")
    elif not scoreable:
        data_status = "Incomplete data"
        if limits is None:
            notes.append("Property type missing or not mappable to a BERDO category")
        if pd.isna(sqft) or sqft <= 0:
            notes.append("Floor area missing")
        if pd.isna(ghg):
            notes.append("GHG intensity missing")
    else:
        data_status = "Reported"

    #Flag 2: BERDO compliance status
    cov = coverage_for(row.get("compliance_year"), row.get("compliance_status"),
                       row.get("Property Owner Name"))
    subject_now = period_covered(cov, 0)
    if cov["city"]:
        notes.append(
            "City building: the ordinance's daily fines (section r) don't apply to City "
            "buildings; emissions standards still do"
        )

    acp_2025 = 0.0
    if not scoreable:
        berdo_status = "Unknown (data incomplete)"
    elif not cov["known"]:
        berdo_status = "Coverage year not reported"
        notes.append("First compliance year missing, so it's unclear whether an emissions limit applies")
    elif not subject_now:
        berdo_status = "Not yet covered"
        notes.append(f"Not subject to a BERDO emissions limit until {cov['applies_from']} emissions")
        _g30 = calculate_compliance_gap(ghg, sqft, None, limits=limits)[1]
        notes.append(
            f"For reference: at current emissions, {'over' if not _g30['compliant'] else 'under'} "
            f"the 2030–34 limit by {abs(_g30['gap']):.2f} kg/sf/yr"
        )
    else:
        gaps = calculate_compliance_gap(ghg, sqft, None, limits=limits, coverage=cov)
        if not gaps[0]["compliant"]:
            berdo_status = "Over 2025–29 limit"
            acp_2025 = gaps[0]["annual_fine_usd"]
            if bl.get("blended"):
                _bg = calculate_compliance_gap(ghg, sqft, None, limits=bl["blended"])
                if _bg and _bg[0]["compliant"]:
                    notes.append(
                        "Would meet the 2025–29 limit if the owner adopts a Blended "
                        "Emissions Standard (see compliance pathways)"
                    )
            notes.append(
                f"Exceeds 2025–29 limit by {gaps[0]['gap']:.2f} kg/sf/yr "
                f"({gaps[0]['excess_metric_tons']:,.0f} excess MT)"
            )
            _dy  = pd.to_numeric(row.get("data_year"), errors="coerce")
            _el  = pd.to_numeric(row.get("elec_emissions_kg"), errors="coerce")
            _tot = pd.to_numeric(row.get("ghg_emissions"), errors="coerce")
            if pd.notna(_dy) and int(_dy) < 2025 and pd.notna(_el) and pd.notna(_tot) and _el > 0:
                _adj = (_tot - _el + _el * effective_grid_ef(2025) / effective_grid_ef(int(_dy))) / sqft
                notes.append(
                    f"Based on {int(_dy)} energy use. At the 2025 grid factor, the same energy use "
                    f"would be about {_adj:.2f} kg/sf/yr "
                    f"({'still over' if _adj > gaps[0]['limit'] else 'under'} the 2025–29 limit)"
                )
        elif not gaps[1]["compliant"]:
            berdo_status = "Fails 2030–34"
            notes.append("Compliant now; exceeds the 2030–34 limit at current emissions")
        elif not gaps[2]["compliant"]:
            berdo_status = "Compliant through 2034"
        else:
            berdo_status = "Compliant through 2039+"

    if pd.notna(sqft) and sqft >= 100_000:
        notes.append("Over 100,000 sq ft: longer retrofit lead time")

    return data_status, berdo_status, acp_2025, notes


def calculate_blended_standard(buildings_df):
    """
    Calculates the area-weighted blended emissions standard for a portfolio,
    one value per compliance period.

    Returns a list of 6 floats (kg CO2e/sqft/yr), or None if the portfolio
    cannot be evaluated (missing sqft or unmappable property types).
    """
    total_sqft = 0.0
    weighted_limits = [0.0] * len(COMPLIANCE_PERIODS)

    for _, row in buildings_df.iterrows():
        sqft = pd.to_numeric(row.get("Gross Floor Area"), errors="coerce")
        limits = building_limits(row.get("Property Type"), row.get("All Property Types"))["limits"]
        if pd.isna(sqft) or sqft <= 0 or limits is None:
            continue
        total_sqft += sqft
        for i, lim in enumerate(limits):
            weighted_limits[i] += lim * sqft

    if total_sqft == 0:
        return None

    return [round(wl / total_sqft, 4) for wl in weighted_limits]


def next_deadline(month: int, day: int, today=None):
    """Next occurrence of an annual month/day deadline, as (date, days_away)."""
    import datetime as _dt
    today = today or _dt.date.today()
    d = _dt.date(today.year, month, day)
    if d < today:
        d = _dt.date(today.year + 1, month, day)
    return d, (d - today).days


def _fmt_deadline(key):
    d, days = next_deadline(*FLEX_DEADLINES[key])
    when = "today" if days == 0 else f"in {days} days"
    return f"{d.strftime('%B')} {d.day}, {d.year} ({when})"


def rec_connector_price(n_recs) -> float:
    """All-inclusive REC Connector price per REC for a given purchase quantity."""
    import math
    n = max(int(math.ceil(n_recs or 0)), 1)
    for min_qty, price in REC_CONNECTOR_TIERS:
        if n >= min_qty:
            return price
    return REC_CONNECTOR_TIERS[-1][1]


def _opt_incentive_applies(inc, scopes, fuel, ownership, berdo_category):
    """Return True if this incentive matches the user's inputs."""
    if inc.get("closed_to_new_projects"):
        return False
    if not any(s in inc["scopes"] for s in scopes):
        return False
    if fuel not in inc["fuels"]:
        return False
    if ownership != "Not sure":
        if ownership not in inc["ownership"]:
            return False
    if "berdo_types" in inc and berdo_category is not None:
        if berdo_category not in inc["berdo_types"]:
            return False
    return True
    
def _estimate_incentive_value(inc, sqft):
    """
    Return (low, high) dollar estimate for an incentive.
    Deductions are converted to after-tax cash value via cash_value_factor;
    credits and rebates default to 1.0 (dollar-for-dollar).
    """
    f = inc.get("cash_value_factor", 1.0)
    return (
        round(inc["amount_psf_low"]  * sqft * f, 0),
        round(inc["amount_psf_high"] * sqft * f, 0),
    )
