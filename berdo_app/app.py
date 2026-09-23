import pandas as pd
import re
import plotly.graph_objects as go
import streamlit as st
from pathlib import Path

#Page config

st.set_page_config(
    page_title="BERDO Priority Screening Tool",
    layout="wide"
)

#BERDO 2.0 emissions standards
#Source: BERDO ordinance (City of Boston Code 7-2.2), Table 1 (adopted October 2021).
#VERIFIED September 22, 2026: every value matches Table 1 of the ordinance text.
#Units: kg CO2e / sq ft / year
#Periods: 2025-29, 2030-34, 2035-39, 2040-44, 2045-49, 2050+

BERDO_STANDARDS = {
    "Assembly":                [7.8,  4.6,  3.3,  2.1, 1.1, 0.0],
    "College/University":      [10.2, 5.3,  3.8,  2.5, 1.2, 0.0],
    "Education":               [3.9,  2.4,  1.8,  1.2, 0.6, 0.0],
    "Food Sales & Service":    [17.4, 10.9, 8.0,  5.4, 2.7, 0.0],
    "Healthcare":              [15.4, 10.0, 7.4,  4.9, 2.4, 0.0],
    "Lodging":                 [5.8,  3.7,  2.7,  1.8, 0.9, 0.0],
    "Manufacturing/Industrial":[23.9, 15.3, 10.9, 6.7, 3.2, 0.0],
    "Multifamily Housing":     [4.1,  2.4,  1.8,  1.1, 0.6, 0.0],
    "Office":                  [5.3,  3.2,  2.4,  1.6, 0.8, 0.0],
    "Retail":                  [7.1,  3.4,  2.4,  1.5, 0.7, 0.0],
    "Services":                [7.5,  4.5,  3.3,  2.2, 1.1, 0.0],
    "Storage":                 [5.4,  2.8,  1.8,  1.0, 0.4, 0.0],
    "Technology/Science":      [19.2, 11.1, 7.8,  5.1, 2.5, 0.0],
}

COMPLIANCE_PERIODS = ["2025–29", "2030–34", "2035–39", "2040–44", "2045–49", "2050+"]

#ACP rate: USD 234 per metric ton CO2e, per ordinance section (m)(d). The Review Board
#reviews it every five years and it may be adjusted by regulation.
#VERIFIED September 22, 2026.
ACP_RATE = 234  #USD per metric ton CO2e over the limit


#Projected ISO New England grid emissions factors by year, kg CO2e/MWh.
#Sources: BERDO Policies & Procedures Version 5 (adopted September 14, 2026), Appendix B,
#unchanged since Version 3 (September 17, 2025); and the BERDO Emissions Factors List
#(updated September 18, 2026), Appendix B, which adds 2022 to 2024. VERIFIED September 23, 2026.
#CORRECTED September 22, 2026: the previous schedule (a straight-line decline to 71 kg/MWh in 2050)
#matched the official values only for 2025 and 2026.
PROJECTED_GRID_EF = {
    2022: 270, 2023: 263, 2024: 256,
    2025: 249, 2026: 242, 2027: 265, 2028: 265, 2029: 264,
    2030: 259, 2031: 254, 2032: 249, 2033: 243, 2034: 237,
    2035: 231, 2036: 224, 2037: 217, 2038: 211, 2039: 204,
    2040: 198, 2041: 192, 2042: 187, 2043: 182, 2044: 177,
    2045: 173, 2046: 168, 2047: 163, 2048: 159, 2049: 155,
    2050: 150,
}

#MA RPS Class I minimum standard, per 225 CMR 14.07(1).
#VERIFIED September 22, 2026 against the regulation's table: 27% in 2025, +3 points a year to
#39% in 2029, 40% in 2030, then +1 point a year "unless modified by law".
#BERDO electricity formula (Policies & Procedures v5, section 5.B):
#Emissions = Electricity Use × (100% − RPS Class I) × Emissions Factor
#Schedule: +3 pp/yr 2025–2029, 40% in 2030, +1 pp/yr thereafter.
RPS_CLASS_I = {
    2022: 0.20, 2023: 0.22, 2024: 0.24, 2025: 0.27, 2026: 0.30,
    2027: 0.33, 2028: 0.36, 2029: 0.39, 2030: 0.40,
}
for _y in range(2031, 2051):
    RPS_CLASS_I[_y] = round(0.40 + 0.01 * (_y - 2030), 2)

_EF_MIN_YR,  _EF_MAX_YR  = min(PROJECTED_GRID_EF), max(PROJECTED_GRID_EF)
_RPS_MIN_YR, _RPS_MAX_YR = min(RPS_CLASS_I),       max(RPS_CLASS_I)

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

#Representative year for each compliance period (midpoint, or period start for 2050)
PERIOD_REPRESENTATIVE_YEARS = [2027, 2032, 2037, 2042, 2047, 2050]


#Mapping from Energy Star Portfolio Manager property types → BERDO categories

#Mapping from Energy Star Portfolio Manager property types → BERDO categories

PROPERTY_TYPE_MAP = {
    #Assembly (2025-29 limit: 7.8)
    "aquarium":                             "Assembly",
    "convention center":                    "Assembly",
    "fitness center/health club/gym":       "Assembly",
    "heated swimming pool":                 "Assembly",
    "indoor arena":                         "Assembly",
    "ice/curling rink":                     "Assembly",
    "museum":                               "Assembly",
    "movie theater":                        "Assembly",
    "other - entertainment/public assembly":"Assembly",
    "other - recreation":                   "Assembly",
    "other - stadium":                      "Assembly",
    "performing arts":                      "Assembly",
    "race track":                           "Assembly",
    "social/meeting hall":                  "Assembly",
    "stadium (open)":                       "Assembly",
    "stadium (closed)":                     "Assembly",
    "swimming pool":                        "Assembly",
    "worship facility":                     "Assembly",
    "bowling alley":                        "Assembly",
    "casino":                               "Assembly",
    "roller rink":                          "Assembly",
    "zoo":                                  "Assembly",
    "boat marinas":                         "Assembly",
    "movie production studios":             "Assembly",
    "tv/radio broadcast studios":           "Assembly",

    #College/University (10.2)
    "college/university":                   "College/University",

    #Education (3.9)
    "adult education":                      "Education",
    "k-12 school":                          "Education",
    "other - education":                    "Education",
    "pre-school/daycare":                   "Education",
    "vocational school":                    "Education",

    #Food Sales & Service (17.4)
    "bar/nightclub":                        "Food Sales & Service",
    "fast food restaurant":                 "Food Sales & Service",
    "food sales":                           "Food Sales & Service",
    "food service":                         "Food Sales & Service",
    "other - restaurant/bar":               "Food Sales & Service",
    "restaurant":                           "Food Sales & Service",
    "supermarket/grocery store":            "Food Sales & Service",

    #Healthcare (15.4)
    "ambulatory surgical center":           "Healthcare",
    "hospital (general medical & surgical)":"Healthcare",
    "medical office":                       "Healthcare",
    "other - specialty hospital":           "Healthcare",
    "outpatient rehabilitation/physical therapy": "Healthcare",
    "urgent care/clinic/other outpatient":  "Healthcare",
    "veterinary office":                    "Healthcare",
    "residential care facility":            "Healthcare",
    "senior care community":                "Healthcare",
    "senior living community":              "Healthcare",
    "nursing home":                         "Healthcare", #legacy name

    #Lodging (5.8)
    "barracks":                             "Lodging",
    "hotel":                                "Lodging",
    "other - lodging/residential":          "Lodging",
    "residence hall/dormitory":             "Lodging",
    "single family home":                   "Lodging",
    "prison/incarceration":                 "Lodging", 

    #Manufacturing/Industrial (23.9)
    "manufacturing/industrial plant":       "Manufacturing/Industrial",
    "hydroponic, greenhouse and other growing facilities": "Manufacturing/Industrial",

    #Multifamily Housing (4.1)
    "multifamily housing":                  "Multifamily Housing",

    #Office (5.3)
    "financial office":                     "Office",
    "office":                               "Office",

    #Retail (7.1)
    "automobile dealership":                "Retail",
    "bank branch":                          "Retail",
    "enclosed mall":                        "Retail",
    "lifestyle center":                     "Retail",
    "other - mall":                         "Retail",
    "retail store":                         "Retail",
    "strip mall":                           "Retail",
    "wholesale club/supercenter":           "Retail",

    #Services (7.5)
    "convenience store without gas station":"Services",
    "courthouse":                           "Services",
    "energy/power station":                 "Services",
    "fire station":                         "Services",
    "library":                              "Services",
    "other - public services":              "Services",
    "other - services":                     "Services",
    "other - utility":                      "Services",
    "personal services (health/beauty, dry cleaning, etc.)": "Services",
    "police station":                       "Services",
    "repair services (vehicle, shoe, locksmith, etc.)":      "Services",
    "drinking water treatment & distribution": "Services",
    "mailing center/post office":           "Services",
    "transportation terminal/station":      "Services",
    "wastewater treatment plant":           "Services",

    #Storage (5.4)
    "distribution center":                  "Storage",
    "non-refrigerated warehouse":           "Storage",
    "parking":                              "Storage",
    "refrigerated warehouse":               "Storage",
    "self-storage facility":                "Storage",

    #Technology/Science (19.2)
    "data center":                          "Technology/Science",
    "laboratory":                           "Technology/Science",
    "other - technology/science":           "Technology/Science",
}

PROPERTY_TYPE_ALIASES = {
    "college / university":         "College/University",
    "residence hall / dormitory":   "Lodging",
    "manufacturing/industrial":     "Manufacturing/Industrial",
    #City data sometimes writes "etc" without the period
    "personal services (health/beauty, dry cleaning, etc)": "Services",
    "personal services (health/beauty dry cleaning etc.)":  "Services",   #Appendix A spelling
    "repair services (vehicle, shoe, locksmith, etc)":      "Services",
}
PROPERTY_TYPE_MAP.update(PROPERTY_TYPE_ALIASES)


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
    
def standardize_address_series(series):
    """
    This section addresses standardization.
    IT also strips out full address details (like city, state, zip) after a comma.
    """
    extracted = series.astype(str).str.split(",").str[0]
    
    cleaned = (
        extracted
        .str.strip()
        .str.upper()
        .str.replace(".", "", regex=False)
        .str.replace(" STREET", " ST", regex=False)
        .str.replace(" AVENUE", " AVE", regex=False)
        .str.replace(" ROAD", " RD", regex=False)
    )
    return cleaned

#Compliance gap calculation

def calculate_compliance_gap(ghg_intensity, sqft, berdo_category, limits=None):
    if limits is None:
        limits = BERDO_STANDARDS.get(berdo_category)
    if limits is None:
        return []

    results = []
    for i, period in enumerate(COMPLIANCE_PERIODS):
        limit = limits[i]
        gap = round(ghg_intensity - limit, 3)
        compliant = gap <= 0
        excess_tons = 0.0 if compliant else round(gap * sqft / 1000, 1)
        fine = 0.0 if compliant else round(excess_tons * ACP_RATE, 0)
        results.append({
            "period": period,
            "limit": limit,
            "gap": gap,
            "compliant": compliant,
            "excess_metric_tons": excess_tons,
            "annual_fine_usd": fine,
        })
    return results


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


def render_compliance_pathways(ctx: dict):
    """On-screen version of get_compliance_pathways()."""
    over_now = ctx.get("over_now", False)
    title = "BERDO compliance pathways" + (": options for a building over its limit" if over_now else "")
    with st.expander(title, expanded=over_now):
        st.caption(
            "BERDO offers several ways to comply. This list explains each option and why it "
            "may or may not fit this building. It is not an eligibility determination. "
            "Confirm details and deadlines on the City's pages."
        )
        current_group = None
        for p in get_compliance_pathways(ctx):
            if p["group"] != current_group:
                current_group = p["group"]
                st.markdown(f"#### {current_group}")
            why = (f"**For this building:** {p['why']}" if p["strong"]
                   else f"*For this building:* {p['why']}")
            links = " · ".join(f"[{label}]({url})" for label, url in p["links"])
            st.markdown(
                f"**{p['name']}:** {p['what']}  \n"
                f"Approval: {p['approval']} · Deadline: {p['deadline']}  \n"
                f"{why}  \n"
                f"{links}"
            )
        st.markdown("#### Get help")
        st.markdown(
            f"[Schedule a one-on-one call with BERDO staff]({BERDO_LINKS['one_on_one']}) · "
            f"[What to do if you're out of compliance]({BERDO_LINKS['out_of_compliance']}) · "
            f"[Review Board page and deadline table]({BERDO_LINKS['review_board']}) · "
            f"[City's official BERDO Emissions Calculator]({BERDO_LINKS['city_calculator']}) · "
            f"[Approved flexibility measures list]({BERDO_LINKS['approved_flex']})"
        )
        st.caption(
            f"Pathway descriptions, deadlines, and links from boston.gov, verified "
            f"{PATHWAYS_VERIFIED}. BERDO regulations are being updated; check the City's "
            "pages before acting."
        )


#One-page PDF summary

def reporting_status_label(raw) -> str:
    """
    Plain-language label for the City's "Reporting Compliance Status". That field is
    about the annual report only, not emissions limits, so the label says so.
    """
    s = str(raw or "").strip().lower()
    labels = {
        "in compliance":     "Submitted (City status: in compliance)",
        "not submitted":     "Not submitted (City status: not submitted)",
        "pending revisions": "Submitted, revisions pending (City status: pending revisions)",
        "state":             "City status: state (verify BERDO treatment)",
        "federal":           "City status: federal (verify BERDO treatment)",
    }
    return labels.get(s, "Not reported" if s in ("", "nan", "none") else f"City status: {s}")


def build_building_summary_pdf(s: dict) -> bytes:
    """
    One-page PDF of a building's screening results and options, for sharing with a
    board, lender, or consultant. Every figure is labeled Reported, Calculated, or
    Estimated. KeepInFrame(shrink) guarantees the content fits on one page.

    s keys: address, owner, data_year, facts [(item, value, source)],
    periods [dict], limit_basis, blend_note, grid_note, notes [str], pathways [dict].
    """
    from io import BytesIO
    from xml.sax.saxutils import escape
    import datetime as _dt
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, KeepInFrame)

    def esc(x):
        return escape(str(x)) if x is not None else ""

    def co2(text):
        #Built-in PDF fonts have no subscript-2 glyph, so use markup instead
        return text.replace("CO₂", "CO<sub>2</sub>").replace("CO2e", "CO<sub>2</sub>e")

    base = getSampleStyleSheet()
    ink, muted, accent, rule = (colors.HexColor("#1F2A37"), colors.HexColor("#5B6573"),
                                colors.HexColor("#2F5D8A"), colors.HexColor("#D5DAE1"))
    st_title = ParagraphStyle("t", parent=base["Title"], fontName="Helvetica-Bold",
                              fontSize=15, leading=18, alignment=0, spaceAfter=2, textColor=ink)
    st_sub   = ParagraphStyle("s", parent=base["Normal"], fontName="Helvetica-Bold",
                              fontSize=11, leading=14, textColor=ink)
    st_meta  = ParagraphStyle("m", parent=base["Normal"], fontSize=8, leading=10, textColor=muted)
    st_h     = ParagraphStyle("h", parent=base["Normal"], fontName="Helvetica-Bold",
                              fontSize=9.5, leading=12, textColor=accent, spaceBefore=7, spaceAfter=3)
    st_body  = ParagraphStyle("b", parent=base["Normal"], fontSize=8, leading=10, textColor=ink)
    st_cell  = ParagraphStyle("c", parent=st_body, fontSize=7.8, leading=9.5)
    st_cellb = ParagraphStyle("cb", parent=st_cell, fontName="Helvetica-Bold")
    st_small = ParagraphStyle("sm", parent=st_body, fontSize=7, leading=8.6, textColor=muted)

    def P(text, style=st_cell):
        return Paragraph(text, style)

    grid = TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, accent),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, rule),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ])

    story = []
    today = _dt.date.today()
    story.append(P("BERDO Screening Summary", st_title))
    story.append(P(esc(s.get("address", "")), st_sub))
    story.append(P(
        f"Owner: {esc(s.get('owner') or 'Not reported')} &nbsp;·&nbsp; "
        f"Data year: {esc(s.get('data_year') or 'Not specified')} &nbsp;·&nbsp; "
        f"Generated {today.strftime('%B')} {today.day}, {today.year}", st_meta))
    story.append(Spacer(1, 5))

    banner = Table([[P(
        "<b>Screening estimate, not an official City of Boston compliance determination.</b> "
        "Figures are labeled <b>Reported</b> (from the City's public BERDO data), "
        "<b>Calculated</b> (by this tool from reported data), or <b>Estimated</b> "
        "(depends on this tool's assumptions).", st_body)]], colWidths=[7.3 * inch], hAlign="LEFT")
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF3F8")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#B8C7D9")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(banner)

    #Building at a glance: two side-by-side fact tables
    story.append(P("Building at a glance", st_h))
    facts = s.get("facts", [])
    half = (len(facts) + 1) // 2
    #One table with two halves (Item | Value | Source, gap, Item | Value | Source), so
    #each row has a single height and every rule lines up across the page.
    left, right = facts[:half], facts[half:]
    right += [("", "", "")] * (len(left) - len(right))
    hdr = [P("<b>Item</b>"), P("<b>Value</b>"), P("<b>Source</b>")]
    data = [hdr + [""] + hdr]
    for (a1, b1, c1), (a2, b2, c2) in zip(left, right):
        data.append([P(esc(a1)), P(co2(esc(b1))), P(esc(c1), st_small), "",
                     P(esc(a2)), P(co2(esc(b2))), P(esc(c2), st_small)])
    gap = 0.2
    half_w = (7.3 - gap) / 2                       #3.55 in per half; total 7.3 in
    col_w = [1.25, 1.45, half_w - 2.7]
    facts_t = Table(data, colWidths=[w * inch for w in col_w + [gap] + col_w], hAlign="LEFT")
    facts_t.setStyle(TableStyle([
        #Rules drawn per half so they don't cross the gap column
        ("LINEBELOW", (0, 0), (2, 0), 0.8, accent),
        ("LINEBELOW", (4, 0), (6, 0), 0.8, accent),
        ("LINEBELOW", (0, 1), (2, -1), 0.3, rule),
        ("LINEBELOW", (4, 1), (6, -1), 0.3, rule),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (3, 0), (3, -1), 0), ("RIGHTPADDING", (3, 0), (3, -1), 0),
    ]))
    story.append(facts_t)

    #Emissions limit by period
    periods = s.get("periods", [])
    if periods:
        story.append(P("Emissions limit by compliance period", st_h))
        has_grid = any(p.get("grid_status") for p in periods)
        head = ["Period", "Limit (kg CO2e/sf/yr)", "Gap vs. current intensity",
                "Status at current emissions", "Est. annual ACP"]
        if has_grid:
            head.append("Grid scenario")
        data = [[P(f"<b>{co2(h)}</b>") for h in head]]
        for p in periods:
            row = [P(esc(p["period"])), P(f"{p['limit']:.2f}"),
                   P(f"{p['gap']:+.2f}"),
                   P(esc(p["status"]), st_cellb if p["status"] != "Meets limit" else st_cell),
                   P(f"USD {p['acp']:,.0f}" if p["acp"] else "USD 0")]
            if has_grid:
                row.append(P(esc(p.get("grid_status") or "")))
            data.append(row)
        widths = [0.8, 1.35, 1.35, 1.6, 1.1] + ([1.1] if has_grid else [])
        scale = 7.3 / sum(widths)   #always span the full page width, with or without the grid column
        t = Table(data, colWidths=[w * scale * inch for w in widths], hAlign="LEFT")
        t.setStyle(grid)
        story.append(t)
        cap = [esc(s.get("limit_basis", ""))]
        if s.get("blend_note"):
            cap.append(esc(s["blend_note"]))
        if s.get("grid_note"):
            cap.append(esc(s["grid_note"]))
        cap.append("Limits: Reported (BERDO emissions standards). Gap and status: Calculated. "
                   f"ACP: Estimated at USD {ACP_RATE} per metric ton over the limit, "
                   "assuming emissions stay flat. The 2050+ row is an annual figure with no end date.")
        story.append(Spacer(1, 2))
        story.append(P(co2(" ".join(c for c in cap if c)), st_small))

    #Screening notes
    notes = [n for n in s.get("notes", []) if n]
    if notes:
        story.append(P("Screening notes", st_h))
        for n in notes[:6]:
            story.append(P(f"• {co2(esc(n))}", st_body))

    #Options
    pw = s.get("pathways", [])
    if pw:
        story.append(P("Options to consider", st_h))
        ordered = sorted(pw, key=lambda p: not p["strong"])
        data = [[P("<b>Option</b>"), P("<b>For this building</b>"),
                 P("<b>Approval · Deadline</b>"), P("<b>Official link</b>")]]
        for p in ordered:
            label, url = p["links"][0]
            data.append([
                P(("<b>" if p["strong"] else "") + esc(p["name"]) + ("</b>" if p["strong"] else "")),
                P(co2(esc(p["why"][:1].upper() + p["why"][1:]))),
                P(f"{esc(p['approval'])} · {esc(p['deadline'])}", st_small),
                P(f'<link href="{esc(url)}" color="#2F5D8A"><u>{esc(label)}</u></link>', st_small),
            ])
        t = Table(data, colWidths=[1.45 * inch, 2.75 * inch, 1.75 * inch, 1.35 * inch], hAlign="LEFT")
        t.setStyle(grid)
        story.append(t)
        story.append(Spacer(1, 2))
        story.append(P("Options in bold are most relevant to this building's screening result. "
                       "Listing an option is not a determination of eligibility.", st_small))

    #Footer
    story.append(Spacer(1, 6))
    story.append(P(
        "Sources: City of Boston BERDO public data disclosure; BERDO emissions standards; "
        f"boston.gov BERDO and Review Board pages (pathways and deadlines verified {PATHWAYS_VERIFIED}). "
        f'Questions about official compliance: <link href="{BERDO_LINKS["one_on_one"]}" color="#2F5D8A">'
        "<u>schedule a call with BERDO staff</u></link>. "
        "Prepared with the BERDO Priority Screening Tool. Not financial, legal, or tax advice.",
        st_small))

    buf = BytesIO()
    margin = 0.5 * inch
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=margin, rightMargin=margin,
                            topMargin=margin, bottomMargin=margin,
                            title=f"BERDO Screening Summary: {s.get('address', '')}",
                            author="BERDO Priority Screening Tool")
    frame_w, frame_h = letter[0] - 2 * margin, letter[1] - 2 * margin
    doc.build([KeepInFrame(frame_w, frame_h - 2, story, mode="shrink")])
    return buf.getvalue()


#Mixed-use editor

def render_use_mix_editor(top):
    """
    Shows floor area by use and lets the owner correct it. Pre-fills from the
    reported data (2024+). Returns blended limits when the building has more
    than one BERDO category, otherwise None (single-use limits apply).
    """
    address  = str(top.get("Building Address", ""))
    raw_type = top.get("Property Type")
    bl = building_limits(raw_type, top.get("All Property Types"))
    reported_gfa = pd.to_numeric(top.get("Gross Floor Area"), errors="coerce")
    reported_gfa = 0.0 if pd.isna(reported_gfa) else float(reported_gfa)

    if bl["basis"] == "blended":
        rows = bl["uses"]
    elif bl["basis"] == "multi_no_gfa":
        #Floor areas not reported: give the largest use the full GFA, others 0
        rows = [{
            "ESPM use": n,
            "BERDO category": map_property_type(n),
            "Sq ft": reported_gfa if map_property_type(n) == bl["category"] else 0.0,
        } for n in bl["listed_names"]]
    else:
        rows = [{"ESPM use": str(raw_type or ""), "BERDO category": bl["category"],
                 "Sq ft": reported_gfa}]

    is_mixed = bl["basis"] != "largest_use"
    title = "Building uses and emissions limit" + (" (mixed-use)" if is_mixed else "")

    with st.expander(title, expanded=is_mixed):
        if bl["basis"] == "blended":
            st.caption(
                "This building reports more than one use. By default, BERDO applies the "
                "limit for the largest primary use. Owners may instead adopt a Blended "
                "Emissions Standard weighted by the floor area of each primary use. "
                "The table is pre-filled from the reported data. Correct it if needed."
            )
        elif bl["basis"] == "multi_no_gfa":
            st.warning(
                "This year's data lists more than one use but no floor area for each. "
                "Enter the square footage by use to see what a Blended Emissions "
                "Standard would be. The default limit is the largest use's."
            )
        else:
            st.caption(
                "One use reported. If the building has more than one use, add a row "
                "for each use with its floor area."
            )

        edited = st.data_editor(
            pd.DataFrame(rows, columns=["ESPM use", "BERDO category", "Sq ft"]),
            key=f"use_mix_{address}",
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            column_config={
                "ESPM use": st.column_config.TextColumn("Reported use"),
                "BERDO category": st.column_config.SelectboxColumn(
                    "BERDO category", options=sorted(BERDO_STANDARDS.keys())),
                "Sq ft": st.column_config.NumberColumn(
                    "Floor area (sq ft)", min_value=0, step=100, format="%d"),
            },
        )
        exclude_parking = st.checkbox(
            "Leave parking out of the blend", value=True,
            key=f"use_mix_parking_{address}",
            help="Parking is commonly excluded from BERDO emissions standards. "
                 "Verify against the BERDO regulations for this building.",
        )

        use_rows = edited.to_dict("records")
        if exclude_parking:
            use_rows = [r for r in use_rows if not _is_parking(r.get("ESPM use"))]
        limits, total_sqft, non_primary_sqft, n_cats = blend_limits_by_area(use_rows)
        unclassified_sqft = sum(
            float(pd.to_numeric(r.get("Sq ft"), errors="coerce") or 0)
            for r in use_rows
            if r.get("BERDO category") not in BERDO_STANDARDS
            and (pd.to_numeric(r.get("Sq ft"), errors="coerce") or 0) > 0
        )

        if unclassified_sqft > 0:
            st.warning(
                f"{unclassified_sqft:,.0f} sq ft has no BERDO category, so it counts at the "
                "largest primary use's limit. Choose a category if it is a primary use."
            )
        if limits and non_primary_sqft > 0:
            st.caption(
                f"{non_primary_sqft:,.0f} sq ft is non-primary (under 10% of floor area, or "
                "unclassified) and counts at the largest primary use's limit, per the City's "
                "formula. A use can also be primary if it accounts for more than 10% of "
                "energy use or emissions, which public data can't show."
            )
        if reported_gfa > 0 and total_sqft > 0 and abs(total_sqft - reported_gfa) / reported_gfa > 0.05:
            st.caption(
                f"Floor area in this table ({total_sqft:,.0f} sq ft) differs from the "
                f"reported gross floor area ({reported_gfa:,.0f} sq ft) by more than 5%. "
                "The City requires the uses to add up to the building's total floor area."
            )

        if limits and n_cats > 1:
            default = bl["limits"] or [None] * len(COMPLIANCE_PERIODS)
            st.markdown("**Default limit vs. Blended Emissions Standard (kg CO₂e/sf/yr)**")
            st.dataframe(
                pd.DataFrame({
                    "Period": COMPLIANCE_PERIODS,
                    f"Default ({bl['label'] or 'largest use'})": default,
                    "Blended (if adopted)": limits,
                }),
                hide_index=True, use_container_width=True,
            )
            st.caption(
                "Blended estimate calculated by this tool. BERDO counts primary uses "
                "only. Confirm which uses qualify with the City's "
                f"[building-level blended standard template]({BERDO_LINKS['blended_template']}). "
                "Not an official City of Boston determination."
            )
            adopt = st.checkbox(
                "Show results using the Blended Emissions Standard",
                value=False, key=f"use_mix_adopt_{address}",
                help="Off = the default (largest-use) limit. On = the blended standard "
                     "an owner could choose to adopt.",
            )
            if adopt:
                return limits
        return None


#Compliance gap display

def render_compliance_section(
    row,
    prior_year_ghg_intensity=None,
    prior_year_label=None,
    projected_intensities=None,
    base_year=2025,
    limits=None,
):
    """
    projected_intensities: list of 6 floats (one per compliance period) from
    project_ghg_intensities(), or None to skip the grid decarb overlay.
    """
    ghg_intensity = row.get("GHG Intensity (kgCO2e/sqft)")
    sqft = row.get("Gross Floor Area")
    raw_type = row.get("Property Type")
    berdo_category = map_property_type(raw_type)

    st.subheader("Compliance Gap Analysis")

    if pd.isna(ghg_intensity) or ghg_intensity == 0:
        st.warning(
            "GHG intensity is missing or zero for this building, "
            "so the compliance gap can't be calculated. Check that GHG emissions "
            "and floor area are reported in the dataset."
        )
        return

    if pd.isna(sqft) or sqft <= 0:
        st.warning("Floor area is missing, so fine exposure can't be calculated.")
        return

    if berdo_category is None and limits is None:
        st.warning(
            f"Property type **{raw_type}** could not be mapped to a BERDO "
            "emissions category. Add it to the PROPERTY_TYPE_MAP to enable "
            "gap calculations."
        )
        return

    gaps = calculate_compliance_gap(ghg_intensity, sqft, berdo_category, limits=limits)
    category_label = "Blended Emissions Standard" if limits is not None else berdo_category

    #Projected gaps (for grid decarb scenario metric cards)
    if projected_intensities is not None:
        proj_gaps = [
            calculate_compliance_gap(pi, sqft, berdo_category, limits=limits)
            for pi in projected_intensities
        ]
        #proj_gaps[i] is a list of 6 period gaps for the projected intensity at period i
        #We only need the gap for each period against its own limit, i.e. proj_gaps[i][i]
        proj_gap_for_period = [proj_gaps[i][i] for i in range(len(COMPLIANCE_PERIODS))]
    else:
        proj_gap_for_period = None

    st.caption(
        f"Current intensity: **{ghg_intensity:.3f} kg CO₂e/sf/yr** · "
        f"Floor area: **{int(sqft):,} sq ft** · "
        f"BERDO category: **{category_label}**"
    )

    #Metric cards (first 3 periods)
    cols = st.columns(3)
    period_labels = ["2025–2029", "2030–2034", "2035–2039"]
    for i, col in enumerate(cols):
        g = gaps[i]
        with col:
            status = "Compliant" if g["compliant"] else "Non-compliant"
            fine_str = (
                "$0"
                if g["compliant"]
                else f"${g['annual_fine_usd']:,.0f}/yr"
            )
            gap_delta = (
                f"−{abs(g['gap']):.2f} kg under limit"
                if g["compliant"]
                else f"+{g['gap']:.2f} kg over limit"
            )
            st.metric(
                label=f"{period_labels[i]}  |  {status}",
                value=fine_str,
                delta=gap_delta,
                delta_color="normal" if g["compliant"] else "inverse",
            )
            if not g["compliant"]:
                st.caption(
                    f"Limit: {g['limit']} kg · "
                    f"{g['excess_metric_tons']:,.0f} excess metric tons"
                )
                #Show projected outcome if available
                if proj_gap_for_period is not None:
                    pg = proj_gap_for_period[i]
                    if pg["compliant"]:
                        st.caption("Grid scenario: compliant")
                    else:
                        st.caption(
                            f"Grid scenario: +{pg['gap']:.2f} kg over limit "
                            f"(${pg['annual_fine_usd']:,.0f}/yr)"
                        )

    st.markdown("---")

    #Chart
    limits = [g["limit"] for g in gaps]
    fines  = [g["annual_fine_usd"] for g in gaps]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=COMPLIANCE_PERIODS,
        y=limits,
        name="BERDO limit",
        marker_color="#3266ad",
        text=[f"{v} kg" for v in limits],
        textposition="outside",
        textfont=dict(size=11),
    ))

    fig.add_trace(go.Scatter(
        x=COMPLIANCE_PERIODS,
        y=[ghg_intensity] * len(COMPLIANCE_PERIODS),
        name="Conservative (no change)",
        mode="lines",
        line=dict(color="#E24B4A", width=2, dash="dash"),
    ))

    #Grid decarbonization scenario overlay
    if projected_intensities is not None:
        fig.add_trace(go.Scatter(
            x=COMPLIANCE_PERIODS,
            y=projected_intensities,
            name="Grid decarbonization scenario",
            mode="lines+markers",
            line=dict(color="#2ECC71", width=2),
            marker=dict(size=7, symbol="diamond"),
        ))

    #Optional prior-year intensity overlay
    if prior_year_ghg_intensity is not None and not pd.isna(prior_year_ghg_intensity):
        fig.add_trace(go.Scatter(
            x=COMPLIANCE_PERIODS,
            y=[prior_year_ghg_intensity] * len(COMPLIANCE_PERIODS),
            name=f"{prior_year_label} intensity",
            mode="lines",
            line=dict(color="#9B59B6", width=1.5, dash="dot"),
        ))

    fig.add_trace(go.Scatter(
        x=COMPLIANCE_PERIODS,
        y=fines,
        name="Annual ACP fine, conservative (USD)",
        mode="lines+markers",
        yaxis="y2",
        line=dict(color="#BA7517", width=1.5, dash="dot"),
        marker=dict(size=6),
        visible="legendonly",
    ))

    if projected_intensities is not None:
        proj_fines = [
            calculate_compliance_gap(pi, sqft, berdo_category, limits=limits)[i]["annual_fine_usd"]
            for i, pi in enumerate(projected_intensities)
        ]
        fig.add_trace(go.Scatter(
            x=COMPLIANCE_PERIODS,
            y=proj_fines,
            name="Annual ACP fine, grid scenario (USD)",
            mode="lines+markers",
            yaxis="y2",
            line=dict(color="#27AE60", width=1.5, dash="dot"),
            marker=dict(size=6),
            visible="legendonly",
        ))

    y_max = max(max(limits), ghg_intensity) * 1.25

    fig.update_layout(
        xaxis_title="Compliance period",
        yaxis=dict(title="kg CO₂e / sf / yr", range=[0, y_max]),
        yaxis2=dict(
            title="Annual ACP fine (USD)",
            overlaying="y",
            side="right",
            showgrid=False,
            rangemode="tozero",
            range=[0, max(fines) * 1.1] if max(fines) > 0 else None,
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=400,
        margin=dict(t=40, b=40, l=60, r=60),
        bargap=0.35,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )

    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.12)")

    st.plotly_chart(fig, use_container_width=True)

    #Fine exposure summary
    non_compliant_periods = [g for g in gaps if not g["compliant"]]
    if non_compliant_periods:
        finite     = [g for g in non_compliant_periods if g["period"] != "2050+"]
        indefinite = next((g for g in non_compliant_periods if g["period"] == "2050+"), None)
        total_5yr_fine = sum(g["annual_fine_usd"] * 5 for g in finite)
        msg = (
            f"**Conservative scenario:** if no emissions reductions are made, this building "
            f"faces an estimated USD {total_5yr_fine:,.0f} in cumulative ACP payments across "
            f"{len(finite)} five-year non-compliant period(s) through 2050 "
            f"(annual fine × 5 years per period)."
        )
        if indefinite:
            msg += (
                f" From 2050 onward, an additional estimated USD "
                f"{indefinite['annual_fine_usd']:,.0f}/year applies indefinitely if the "
                f"building remains non-compliant."
            )
        if projected_intensities is not None:
            proj_non_compliant = [
                proj_gap_for_period[i]
                for i in range(len(COMPLIANCE_PERIODS))
                if not proj_gap_for_period[i]["compliant"]
            ]
            proj_finite = [g for g in proj_non_compliant if g["period"] != "2050+"]
            total_proj_fine = sum(g["annual_fine_usd"] * 5 for g in proj_finite)
            if proj_non_compliant:
                msg += (
                    f"\n\n**Grid decarbonization scenario:** estimated USD {total_proj_fine:,.0f} "
                    f"across {len(proj_finite)} five-year non-compliant period(s) through 2050."
                )
            else:
                msg += "\n\n**Grid decarbonization scenario:** building achieves compliance in all periods from grid cleaning alone."
        st.info(msg)

    #Caption
    base_ef = effective_grid_ef(base_year)
    caption = (
        "ACP = Alternative Compliance Payment at $234/metric ton CO₂e over limit. "
        "**Conservative line:** current GHG intensity held flat, no operational changes, "
        "no grid improvement. "
    )
    if projected_intensities is not None:
        caption += (
            f"**Grid decarbonization line:** electricity component scaled by ISO-NE projected "
            f"grid EFs (Appendix B × RPS Class I, base year {base_year} = {base_ef:.0f} kg/MWh); "
            "fossil fuel use held constant. "
        )
    caption += (
        "Sources: BERDO ordinance Table 1 and ACP rate; BERDO Policies & Procedures v5 (September 2026), Appendix B projected grid factors; 225 CMR 14.07 RPS Class I schedule. "
        "Not an official City of Boston compliance determination."
    )
    st.caption(caption)

    with st.expander("About this tool"):
        st.markdown(r"""
        
**What is BERDO?**

The Building Emissions Reduction and Disclosure Ordinance (BERDO) requires large buildings
in Boston to reduce greenhouse gas emissions on a mandatory schedule toward net-zero by 2050.
Buildings over 35,000 sq ft or with 35+ residential units must meet emissions limits starting
in 2025. Smaller covered buildings (20,000–35,000 sq ft or 15–34 residential units) begin
compliance in 2030.

**How are buildings evaluated?**

Each building gets two independent flags rather than a single blended score, because a
building that didn't report needs a different intervention than one that reported and
is over its limit: outreach versus retrofit capital.

**Data Status** reflects reporting completeness: whether data was submitted at all, and
whether property type, floor area, and GHG intensity are present and mappable to a BERDO
category. Buildings marked "not submitted" face daily reporting fines and are the most
urgent outreach targets.

**BERDO Status** compares the building's actual GHG intensity against its own sector limit,
not against a dataset average, so an energy-intensive hospital isn't penalized for using
more energy than a warehouse. It shows whether the building is over the current 2025–29
limit, will fail the 2030–34 limit at current emissions, or is compliant further out.
Smaller covered buildings show "Not yet covered" until their 2030 compliance year.

**How is the compliance gap calculated?**

The tool compares each building's reported GHG intensity (kg CO₂e per square foot per year)
against the BERDO 2.0 emissions limits for its property type. If the building exceeds the limit,
the tool estimates the annual Alternative Compliance Payment (ACP) at \$234 per excess metric
ton of CO₂e. Buildings that do not make ACPs and remain non-compliant face additional daily
fines of \$1,000/day (buildings over 35,000 sq ft or 35+ units) or \$300/day (smaller covered
buildings).

**What is the grid decarbonization scenario?**

The ISO New England electric grid is projected to become cleaner over time as renewable energy
grows. This scenario holds fossil fuel use constant but scales down the electricity-attributed
emissions using the City of Boston's official projected grid emissions factors (Appendix B of the
BERDO Policies & Procedures) and the state RPS Class I schedule. It uses each building's
reported electricity share of emissions (2024 data onward); the sidebar slider applies only
when that share isn't reported.

Sources: BERDO ordinance Table 1 and ACP rate; BERDO Policies & Procedures v5 (September 2026),
Appendix B; 225 CMR 14.07. See "Sources & verification" in the sidebar.
Not an official City of Boston compliance determination.
""")

#Data loading. Supports single file (berdo.csv) or multi-year files
#(berdo_2022.csv, berdo_2023.csv, …) in the data/ folder.

COLUMN_RENAME_MAP = {
    "Largest Property Type": "property_type",
    "All Property Types and GFAs": "all_property_types",
    "Reported Gross Floor Area (Sq Ft)": "gross_floor_area",
    "Site EUI (Energy Use Intensity kBtu/ft²)": "site_eui",
    "Estimated Total GHG Emissions (kgCO2e)": "ghg_emissions",
    "Estimated Total GHG Emissions e(kgCO2e)": "ghg_emissions",
    "Reporting Compliance Status": "compliance_status",
    "First Emissions Compliance Year (Projected)": "compliance_year",
    
    #Fuel usage columns (all in kBtu except Electricity which is kWh)
    
    "Electricity Emissions (kgCO2e)": "elec_emissions_kg",
    "Natural Gas Usage (kBtu)":       "fuel_natural_gas_kbtu",
    "Electricity Usage (kWh)":        "fuel_electricity_kwh",
    "District Steam Usage (kBtu)":    "fuel_district_steam_kbtu",
    "District Hot Water Usage (kBtu)":"fuel_district_hot_water_kbtu",
    "Fuel Oil 1 Usage (kBtu)":        "fuel_oil1_kbtu",
    "Fuel Oil 2 Usage (kBtu)":        "fuel_oil2_kbtu",
    "Fuel Oil 4 Usage (kBtu)":        "fuel_oil4_kbtu",
    "Fuel Oil 5 and 6 Usage (kBtu)":  "fuel_oil56_kbtu",
    "Propane Usage (kBtu)":           "fuel_propane_kbtu",
    "Diesel Usage (kBtu)":            "fuel_diesel_kbtu",
    "Kerosene Usage (kBtu)":          "fuel_kerosene_kbtu",
}

def infer_primary_fuel(row) -> str:
    """
    Infer a building's primary heating fuel from BERDO reported usage columns.
    All values converted to kBtu for comparison.
    Electricity: kWh × 3.412 → kBtu.
    Fuel oils combined into one bucket.
    Returns dominant fuel if >60% of total, else 'Mixed / unknown'.
    Maps to the dropdown options used in the Retrofit Estimator and Incentive Optimizer.
    """
    import math

    def _get(col):
        v = row.get(col)
        try:
            f = float(v)
            return 0.0 if math.isnan(f) else f
        except (TypeError, ValueError):
            return 0.0

    gas_kbtu   = _get("fuel_natural_gas_kbtu")
    elec_kbtu  = _get("fuel_electricity_kwh") * 3.412
    steam_kbtu = _get("fuel_district_steam_kbtu") + _get("fuel_district_hot_water_kbtu")
    oil_kbtu   = (_get("fuel_oil1_kbtu") + _get("fuel_oil2_kbtu") +
                  _get("fuel_oil4_kbtu") + _get("fuel_oil56_kbtu"))
    other_kbtu = _get("fuel_propane_kbtu") + _get("fuel_diesel_kbtu") + _get("fuel_kerosene_kbtu")

    total = gas_kbtu + elec_kbtu + steam_kbtu + oil_kbtu + other_kbtu
    if total <= 0:
        return "Mixed / unknown"

    buckets = {
        "Natural gas":    gas_kbtu,
        "Electric":       elec_kbtu,
        "District steam": steam_kbtu,
        "Fuel oil":       oil_kbtu,
        "Mixed / unknown": other_kbtu,
    }
    dominant_fuel  = max(buckets, key=buckets.get)
    dominant_share = buckets[dominant_fuel] / total

    if dominant_share >= 0.60:
        return dominant_fuel
    return "Mixed / unknown"


def get_fuel_breakdown(row) -> list:
    """
    Returns a list of (label, kBtu, pct) tuples for non-zero fuels,
    sorted descending by kBtu. Used to display the fuel breakdown in the UI.
    """
    import math

    def _get(col):
        v = row.get(col)
        try:
            f = float(v)
            return 0.0 if math.isnan(f) else f
        except (TypeError, ValueError):
            return 0.0

    buckets = {
        "Natural gas":    _get("fuel_natural_gas_kbtu"),
        "Electricity":    _get("fuel_electricity_kwh") * 3.412,
        "District steam": _get("fuel_district_steam_kbtu") + _get("fuel_district_hot_water_kbtu"),
        "Fuel oil":       (_get("fuel_oil1_kbtu") + _get("fuel_oil2_kbtu") +
                           _get("fuel_oil4_kbtu") + _get("fuel_oil56_kbtu")),
        "Other":          _get("fuel_propane_kbtu") + _get("fuel_diesel_kbtu") + _get("fuel_kerosene_kbtu"),
    }
    total = sum(buckets.values())
    if total <= 0:
        return []
    return sorted(
        [(label, kbtu, kbtu / total * 100)
         for label, kbtu in buckets.items() if kbtu > 0],
        key=lambda x: x[1], reverse=True
    )


REQUIRED_COLUMNS = [
    "Building Address", "Property Owner Name", "property_type",
    "gross_floor_area", "site_eui", "ghg_emissions",
    "compliance_status", "compliance_year",
]


@st.cache_data(show_spinner=False)
def _load_single_csv(file_path: Path) -> pd.DataFrame:
    df = pd.read_csv(file_path)
    df.columns = df.columns.astype(str).str.strip()
    df = df.rename(columns=COLUMN_RENAME_MAP)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        st.error(f"Missing required columns in {file_path.name}:")
        st.write(missing)
        st.write("Available columns:", list(df.columns))
        st.stop()

    df["gross_floor_area"] = pd.to_numeric(df["gross_floor_area"], errors="coerce")
    df["site_eui"]         = pd.to_numeric(df["site_eui"],         errors="coerce")
    df["ghg_emissions"]    = pd.to_numeric(df["ghg_emissions"],    errors="coerce")
    df["compliance_year"]  = pd.to_numeric(df["compliance_year"],  errors="coerce")

    #Load fuel usage columns as numeric
    fuel_cols = [
        "fuel_natural_gas_kbtu", "fuel_electricity_kwh",
        "fuel_district_steam_kbtu", "fuel_district_hot_water_kbtu",
        "fuel_oil1_kbtu", "fuel_oil2_kbtu", "fuel_oil4_kbtu", "fuel_oil56_kbtu",
        "fuel_propane_kbtu", "fuel_diesel_kbtu", "fuel_kerosene_kbtu",
    ]
    for col in fuel_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
            
            #Deductions block for _load_single_csv
    
    #Reported electricity emissions. Missing stays missing (not 0), so buildings
    #without a breakdown fall back to the sidebar estimate instead of 0%.
    if "elec_emissions_kg" in df.columns:
        df["elec_emissions_kg"] = pd.to_numeric(df["elec_emissions_kg"], errors="coerce")

    #Zero-out negative electricity net metering (prevents negative roll-over)
    if "fuel_electricity_kwh" in df.columns:
        df["fuel_electricity_kwh"] = df["fuel_electricity_kwh"].clip(lower=0)
        
    #Subtract excluded EV emissions (requires 'ev_charging_kwh' column mapped)
    if "ev_charging_kwh" in df.columns:
        df["ev_charging_kwh"] = pd.to_numeric(df["ev_charging_kwh"], errors="coerce").fillna(0)
        ev_deduction_kg = df["ev_charging_kwh"] * (effective_grid_ef(2025) / 1000) # Assumes 2025 base EF
        df["ghg_emissions"] = (df["ghg_emissions"] - ev_deduction_kg).clip(lower=0)

    valid = (
        df["ghg_emissions"].notna() &
        df["gross_floor_area"].notna() &
        (df["gross_floor_area"] > 0)
    )
    df["ghg_intensity_kgco2e_sqft"] = pd.NA
    df.loc[valid, "ghg_intensity_kgco2e_sqft"] = (
        df.loc[valid, "ghg_emissions"] / df.loc[valid, "gross_floor_area"]
    )

    df["compliance_status"] = (
        df["compliance_status"].astype(str).str.lower().str.strip()
    )
    return df


@st.cache_data(show_spinner=False)
def load_all_years() -> dict[int, pd.DataFrame]:
    """
    Returns a dict mapping year (int) → DataFrame.

    Discovery rules (in priority order):
      1. berdo_<year>.csv files  →  multi-year mode
      2. berdo.csv               →  single-year fallback (keyed as year 0)
    """
    #Streamlit Cloud runs from repo root, so data/ resolves correctly.
    #Also check relative to app.py location as fallback.
    
    data_dir = Path("data")
    if not data_dir.exists() or not any(data_dir.glob("berdo_*.csv")):
        data_dir = Path(__file__).parent.parent / "data"
    year_files = sorted(data_dir.glob("berdo_*.csv"))

    year_map: dict[int, pd.DataFrame] = {}
    for fp in year_files:
        stem = fp.stem  #e.g. "berdo_2023"
        try:
            year = int(stem.split("_")[1])
        except (IndexError, ValueError):
            continue
        year_map[year] = _load_single_csv(fp)

    if not year_map:
        #Fallback: single legacy file
        
        legacy = data_dir / "berdo.csv"
        if not legacy.exists():
            st.error(
                "Dataset not found. Place a CSV at data/berdo.csv, "
                "or use per-year files named data/berdo_<year>.csv "
                "(e.g. data/berdo_2023.csv)."
            )
            st.stop()
        year_map[0] = _load_single_csv(legacy)

    return year_map



#Priority scoring

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

    scoreable = (
        limits is not None
        and pd.notna(ghg)
        and pd.notna(sqft)
        and sqft > 0
    )

    #Flag 1: data status
    if row["compliance_status"] == "not submitted":
        data_status = "Not submitted"
        notes.append("Did not report: accruing daily reporting fines")
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
    subject_now = (
        pd.notna(row.get("compliance_year"))
        and int(row["compliance_year"]) <= 2025
    )

    acp_2025 = 0.0
    if not scoreable:
        berdo_status = "Unknown (data incomplete)"
    elif pd.isna(row.get("compliance_year")):
        berdo_status = "Coverage year not reported"
        notes.append("First compliance year missing, so it's unclear whether an emissions limit applies")
    elif not subject_now:
        berdo_status = "Not yet covered"
        notes.append("Not subject to a BERDO emissions limit until 2030")
    else:
        gaps = calculate_compliance_gap(ghg, sqft, None, limits=limits)
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


def lookup_building_priority(df, address):
    if not address or not isinstance(address, str):
        return None
        
    #Isolate the street component if a full address with commas is entered
    search_clean = address.split(",")[0].strip()
    search_std = (
        search_clean.upper()
        .replace(".", "")
        .replace(" STREET", " ST")
        .replace(" AVENUE", " AVE")
        .replace(" ROAD", " RD")
    )
    
    if not search_std:
        return None

    #Standardize the dataframe's address column using your updated series function
    df_addresses_std = standardize_address_series(df["Building Address"])
    
    #Filter matches where the standardized address contains the search query
    matches = df[df_addresses_std.str.startswith(search_std, na=False)]
    
    if matches.empty:
        return None
        
    results = []

    for _, row in matches.iterrows():
        data_status, berdo_status, acp_2025, notes = evaluate_building(row)
        results.append({
            "Building Address":             row.get("Building Address"),
            "Property Owner Name":         row.get("Property Owner Name"),
            "Property Type":               row.get("property_type"),
            "All Property Types":          row.get("all_property_types"),
            "Gross Floor Area":            row.get("gross_floor_area"),
            "Site EUI":                    row.get("site_eui"),
            "GHG Intensity (kgCO2e/sqft)": row.get("ghg_intensity_kgco2e_sqft"),
            "GHG Emissions (kgCO2e)":      row.get("ghg_emissions"),
            "Electricity Emissions (kgCO2e)": row.get("elec_emissions_kg"),
            "Primary Fuel":                infer_primary_fuel(row),
            "fuel_natural_gas_kbtu":       row.get("fuel_natural_gas_kbtu"),
            "fuel_electricity_kwh":        row.get("fuel_electricity_kwh"),
            "fuel_district_steam_kbtu":    row.get("fuel_district_steam_kbtu"),
            "fuel_district_hot_water_kbtu":row.get("fuel_district_hot_water_kbtu"),
            "fuel_oil1_kbtu":              row.get("fuel_oil1_kbtu"),
            "fuel_oil2_kbtu":              row.get("fuel_oil2_kbtu"),
            "fuel_oil4_kbtu":              row.get("fuel_oil4_kbtu"),
            "fuel_oil56_kbtu":             row.get("fuel_oil56_kbtu"),
            "fuel_propane_kbtu":           row.get("fuel_propane_kbtu"),
            "fuel_diesel_kbtu":            row.get("fuel_diesel_kbtu"),
            "fuel_kerosene_kbtu":          row.get("fuel_kerosene_kbtu"),
            "Compliance Status":           row.get("compliance_status"),
            "Data Status":                 data_status,
            "BERDO Status":                berdo_status,
            "Est. ACP (2025–29)":          acp_2025,
            "Notes":                       "; ".join(notes),
        })

    return pd.DataFrame(results)


#Owner portfolio lookup

def lookup_owner_portfolio(df, owner_name):
    """
    Returns a DataFrame of all buildings matching the given owner name
    (case-insensitive substring match), enriched with the same fields
    used by the single-building lookup.
    """
    import re
    owner_clean = owner_name.strip()
    matches = df[
        df["Property Owner Name"].astype(str).str.contains(
            re.escape(owner_clean), case=False, na=False
        )
    ]
    if matches.empty:
        return None

    results = []
    for _, row in matches.iterrows():
        data_status, berdo_status, acp_2025, notes = evaluate_building(row)
        results.append({
            "Building Address":            row.get("Building Address"),
            "Property Owner Name":         row.get("Property Owner Name"),
            "Property Type":               row.get("property_type"),
            "All Property Types":          row.get("all_property_types"),
            "Gross Floor Area":            row.get("gross_floor_area"),
            "Site EUI":                    row.get("site_eui"),
            "GHG Intensity (kgCO2e/sqft)": row.get("ghg_intensity_kgco2e_sqft"),
            "GHG Emissions (kgCO2e)":      row.get("ghg_emissions"),
            "Electricity Emissions (kgCO2e)": row.get("elec_emissions_kg"),
            "Compliance Status":           row.get("compliance_status"),
            "Data Status":                 data_status,
            "BERDO Status":                berdo_status,
            "Est. ACP (2025–29)":          acp_2025,
            "Notes":                       "; ".join(notes),
        })
    return pd.DataFrame(results)


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



#Portfolio compliance section

def render_portfolio_section(buildings_df, selected_year, elec_share, all_years, show_yoy,
                             use_reported_share=True):
    """
    Renders BERDO compliance analysis for a multi-building owner portfolio.
    Shows portfolio-level blended standard, aggregate gap, fine exposure,
    and a per-building surplus/deficit breakdown table.
    """
    st.subheader("Portfolio Compliance Analysis")

    #Classify buildings: valid vs excluded (with reason)
    
    excluded_rows = []
    valid_rows = []
    for _, row in buildings_df.iterrows():
        ghg   = pd.to_numeric(row.get("GHG Emissions (kgCO2e)"), errors="coerce")
        sqft  = pd.to_numeric(row.get("Gross Floor Area"), errors="coerce")
        missing_ghg  = pd.isna(ghg)
        missing_sqft = pd.isna(sqft) or sqft <= 0

        if missing_ghg or missing_sqft:
            status = str(row.get("Compliance Status", "")).strip().lower()
            if status == "state":
                reason = "Reported under state status. Verify BERDO treatment before excluding"
            elif missing_ghg and missing_sqft:
                if status == "not submitted":
                    reason = "Did not report: no GHG data or floor area submitted"
                elif status == "pending revisions":
                    reason = "Pending revisions: GHG data and floor area incomplete"
                else:
                    reason = "Missing GHG emissions and floor area"
            elif missing_ghg:
                if status == "not submitted":
                    reason = "Did not report: no GHG data submitted"
                elif status == "pending revisions":
                    reason = "Pending revisions: GHG data incomplete"
                else:
                    reason = "Missing GHG emissions data"
            else:
                reason = "Missing floor area"
            excluded_rows.append({
                "Building Address":  row.get("Building Address"),
                "Property Type":     row.get("Property Type"),
                "Compliance Status": row.get("Compliance Status"),
                "Exclusion Reason":  reason,
            })
        else:
            valid_rows.append(row)

    valid = pd.DataFrame(valid_rows) if valid_rows else pd.DataFrame()
    total_buildings  = len(buildings_df)
    usable_buildings = len(valid)
    skipped          = len(excluded_rows)

    if valid.empty:
        st.error("No buildings with sufficient data to calculate portfolio compliance.")
        
        #Still show excluded table so user knows what's missing
        
        if excluded_rows:
            with st.expander(f"Excluded buildings ({skipped})", expanded=True):
                st.dataframe(pd.DataFrame(excluded_rows), use_container_width=True, hide_index=True)
        return

    #Portfolio-level aggregates
    
    valid = valid.copy()
    valid["Gross Floor Area"]      = pd.to_numeric(valid["Gross Floor Area"], errors="coerce")
    valid["GHG Emissions (kgCO2e)"] = pd.to_numeric(valid["GHG Emissions (kgCO2e)"], errors="coerce")

    total_sqft          = valid["Gross Floor Area"].sum()
    total_emissions     = valid["GHG Emissions (kgCO2e)"].sum()
    portfolio_intensity = round(total_emissions / total_sqft, 4)

    blended_limits = calculate_blended_standard(valid)
    if blended_limits is None:
        st.error(
            "Could not calculate a blended standard. Check that property types "
            "are mapped for all buildings in the portfolio."
        )
        return

    #Determine current-period compliance status
    current_limit     = blended_limits[0]
    current_gap       = round(portfolio_intensity - current_limit, 4)
    current_compliant = current_gap <= 0
    current_excess_tons = 0.0 if current_compliant else round(current_gap * total_sqft / 1000, 1)
    current_fine        = 0.0 if current_compliant else round(current_excess_tons * ACP_RATE, 0)

    non_compliant_periods = [
        (i, blended_limits[i])
        for i in range(len(COMPLIANCE_PERIODS))
        if portfolio_intensity > blended_limits[i]
    ]
    finite_non_compliant = [
        (i, lim) for i, lim in non_compliant_periods if COMPLIANCE_PERIODS[i] != "2050+"
    ]
    indefinite_limit = next(
        (lim for i, lim in non_compliant_periods if COMPLIANCE_PERIODS[i] == "2050+"), None
    )
    total_5yr = sum(
        round(max(portfolio_intensity - lim, 0) * total_sqft / 1000, 1) * ACP_RATE * 5
        for _, lim in finite_non_compliant
    )
    indefinite_annual_fine = (
        round(max(portfolio_intensity - indefinite_limit, 0) * total_sqft / 1000, 1) * ACP_RATE
        if indefinite_limit is not None else 0.0
    )

        #Plain-English summary
    if current_compliant:
        #Off-by-one guard: non_compliant_periods[0] is the first period the
        #portfolio FAILS, so it stays compliant through the period BEFORE it.
        if not non_compliant_periods:
            horizon_str = "all periods through 2050"
        else:
            first_fail_idx = non_compliant_periods[0][0]
            if first_fail_idx == 0:
                horizon_str = "the current period only"
            else:
                horizon_str = (
                    f"the {COMPLIANCE_PERIODS[first_fail_idx - 1]} period, "
                    f"then exceeds the {COMPLIANCE_PERIODS[first_fail_idx]} limit"
                )
        st.success(
            f"This portfolio is **compliant** in the current 2025–2029 period under the "
            f"blended emissions standard of {current_limit:.3f} kg CO₂e/sf/yr. "
            f"If emissions remain unchanged, it stays compliant through {horizon_str}."
        )
    else:
        error_msg = (
            f"This portfolio is **non-compliant** in the current 2025–2029 period. "
            f"At current emissions, it faces an estimated USD {current_fine:,.0f}/year in ACP fines "
            f"and USD {total_5yr:,.0f} in cumulative payments across "
            f"{len(finite_non_compliant)} five-year non-compliant period(s) through 2050 "
            f"if no reductions are made."
        )
        if indefinite_annual_fine > 0:
            error_msg += (
                f" From 2050 onward, an additional estimated USD "
                f"{indefinite_annual_fine:,.0f}/year applies indefinitely."
            )
        st.error(error_msg)
       
    #Summary header metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Buildings in portfolio", usable_buildings)
    c2.metric("Total floor area", f"{int(total_sqft):,} sq ft")
    c3.metric("Total emissions", f"{int(total_emissions / 1000):,} metric tons CO₂e")
    c4.metric("Portfolio GHG intensity", f"{portfolio_intensity:.3f} kg/sf/yr")

    st.caption(
        "Portfolio intensity = total GHG emissions ÷ total floor area. "
        "Blended standard = area-weighted average of per-building BERDO limits."
    )

    #Vacancy warning
    zero_emission = valid[
        (valid["GHG Emissions (kgCO2e)"] == 0) &
        (pd.to_numeric(valid["Site EUI"], errors="coerce").fillna(0) == 0)
    ]
    if not zero_emission.empty:
        addresses = ", ".join(zero_emission["Building Address"].astype(str).tolist())
        st.warning(
            f"Possible vacant building(s) detected: **{addresses}**. "
            "BERDO Building Portfolios cannot include vacant buildings. "
            "Verify before submitting a portfolio application."
        )

    st.markdown("---")

    #Metric cards: first 3 compliance periods
    st.markdown("Portfolio vs. Blended Standard")
    cols = st.columns(3)
    period_labels = ["2025–2029", "2030–2034", "2035–2039"]
    for i, col in enumerate(cols):
        limit     = blended_limits[i]
        gap       = round(portfolio_intensity - limit, 4)
        compliant = gap <= 0
        excess_tons = 0.0 if compliant else round(gap * total_sqft / 1000, 1)
        fine        = 0.0 if compliant else round(excess_tons * ACP_RATE, 0)
        with col:
            status   = "Compliant" if compliant else "Non-compliant"
            fine_str = "$0" if compliant else f"${fine:,.0f}/yr"
            gap_delta = (
                f"−{abs(gap):.3f} kg under limit"
                if compliant
                else f"+{gap:.3f} kg over limit"
            )
            st.metric(
                label=f"{period_labels[i]}  |  {status}",
                value=fine_str,
                delta=gap_delta,
                delta_color="normal" if compliant else "inverse",
            )
            if not compliant:
                st.caption(
                    f"Blended limit: {limit:.3f} kg · "
                    f"{excess_tons:,.0f} excess metric tons"
                )

    st.markdown("---")

    #Compliance chart
    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=COMPLIANCE_PERIODS,
        y=blended_limits,
        name="Blended BERDO limit",
        marker_color="#3266ad",
        text=[f"{v:.3f} kg" for v in blended_limits],
        textposition="outside",
        textfont=dict(size=11),
    ))

    fig.add_trace(go.Scatter(
        x=COMPLIANCE_PERIODS,
        y=[portfolio_intensity] * len(COMPLIANCE_PERIODS),
        name="Portfolio intensity (no change)",
        mode="lines",
        line=dict(color="#E24B4A", width=2, dash="dash"),
    ))

    if elec_share is not None:
        #Emissions-weighted portfolio share: each building's reported share where
        #available, the sidebar estimate for the rest.
        portfolio_share, share_src = elec_share, "sidebar estimate"
        if use_reported_share and total_emissions > 0:
            elec_kg, n_reported = 0.0, 0
            for _, r in valid.iterrows():
                s, _ = building_elec_share(
                    r.get("GHG Emissions (kgCO2e)"), r.get("Electricity Emissions (kgCO2e)"))
                if s is None:
                    s = elec_share
                else:
                    n_reported += 1
                elec_kg += s * float(r["GHG Emissions (kgCO2e)"])
            if n_reported > 0:
                portfolio_share = elec_kg / total_emissions
                share_src = f"reported for {n_reported} of {len(valid)} buildings"
                if n_reported < len(valid):
                    share_src += "; sidebar estimate for the rest"
        st.caption(
            f"Grid scenario electricity share: **{fmt_share(portfolio_share)}** ({share_src})."
        )
        projected = project_ghg_intensities(
            portfolio_intensity, portfolio_share,
            selected_year,
        )
        fig.add_trace(go.Scatter(
            x=COMPLIANCE_PERIODS,
            y=projected,
            name="Grid decarbonization scenario",
            mode="lines+markers",
            line=dict(color="#2ECC71", width=2),
            marker=dict(size=7, symbol="diamond"),
        ))

    portfolio_fines = []
    for i, limit in enumerate(blended_limits):
        gap = portfolio_intensity - limit
        excess_tons = max(gap * total_sqft / 1000, 0)
        portfolio_fines.append(round(excess_tons * ACP_RATE, 0))

    fig.add_trace(go.Scatter(
        x=COMPLIANCE_PERIODS,
        y=portfolio_fines,
        name="Annual ACP fine, portfolio (USD)",
        mode="lines+markers",
        yaxis="y2",
        line=dict(color="#BA7517", width=1.5, dash="dot"),
        marker=dict(size=6),
        visible="legendonly",
    ))

    y_max = max(max(blended_limits), portfolio_intensity) * 1.3

    fig.update_layout(
        xaxis_title="Compliance period",
        yaxis=dict(title="kg CO₂e / sf / yr", range=[0, y_max]),
        yaxis2=dict(
            title="Annual ACP fine (USD)",
            overlaying="y",
            side="right",
            showgrid=False,
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=400,
        margin=dict(t=40, b=40, l=60, r=60),
        bargap=0.35,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.12)")

    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "Blended standard per BERDO 2.0: area-weighted average of each building's sector limit. "
        "ACP = Alternative Compliance Payment at $234/metric ton CO₂e over the limit. "
        "Not an official City of Boston compliance determination."
    )

    #What should I do? expander
    with st.expander("What should I do?"):
        if current_compliant:
            st.markdown(f"""
**For building owners:** Your portfolio currently meets the blended 2025–2029 standard of
{current_limit:.3f} kg CO₂e/sf/yr. If you haven't already, consider filing a Building Portfolio
application with the BERDO Review Board. Applications are due **September 1** each year
(next: {_fmt_deadline('portfolio_ics')}); see the City's deadline table for which reporting year applies.

**For policymakers:** This portfolio is currently compliant. Monitor whether high-emitting
buildings within the portfolio are being offset by efficient ones; the per-building table below
shows individual gaps.
""")
        else:
        
            #Find the worst-gap building for owner-facing guidance
            
            worst_addr = ""
            worst_gap_tons = 0.0
            for _, row in valid.iterrows():
                intensity = pd.to_numeric(row.get("GHG Intensity (kgCO2e/sqft)"), errors="coerce")
                sqft_r    = pd.to_numeric(row.get("Gross Floor Area"), errors="coerce")
                b_limits = building_limits(row.get("Property Type"), row.get("All Property Types"))["limits"]
                if pd.isna(intensity) or pd.isna(sqft_r) or b_limits is None:
                    continue
                lim  = b_limits[0]
                tons = round(max(intensity - lim, 0) * sqft_r / 1000, 1)
                if tons > worst_gap_tons:
                    worst_gap_tons = tons
                    worst_addr     = str(row.get("Building Address", ""))

            st.markdown(f"""
**For building owners:** This portfolio exceeds the blended 2025–2029 standard and faces an
estimated USD {current_fine:,.0f}/year in ACP payments. To come into compliance:

- **Prioritize retrofits at your highest-emitting buildings first.** The building with the
  largest individual gap is **{worst_addr}** ({worst_gap_tons:,.0f} excess metric tons in 2025–29).
  Reducing emissions there has the greatest impact on the portfolio total.
- **Resolve missing data for excluded buildings.** If any of your buildings didn't report,
  their emissions are not counted here, so your actual exposure may be higher.
- **File a portfolio application by September 1** (next: {_fmt_deadline('portfolio_ics')})
  to use the blended compliance pathway. Without it, each building is assessed individually.

**For policymakers:** This owner's portfolio is non-compliant. The per-building table below
identifies which buildings are driving the deficit and which are providing surplus. Buildings
marked "Did not report" in the excluded table represent additional unknown exposure.
""")

    st.markdown("---")

    #Per-building surplus/deficit table (sorted by 2025 gap, worst first) ---
    st.markdown("#### Per-Building Surplus / Deficit")
    st.caption(
        "Sorted by largest deficit first. "
        "Buildings with a surplus (negative gap) can offset those with a deficit at the portfolio level."
    )

    breakdown_rows = []
    for _, row in valid.iterrows():
        sqft      = pd.to_numeric(row["Gross Floor Area"], errors="coerce")
        intensity = pd.to_numeric(row["GHG Intensity (kgCO2e/sqft)"], errors="coerce")
        bl = building_limits(row.get("Property Type"), row.get("All Property Types"))

        if pd.isna(sqft) or pd.isna(intensity) or bl["limits"] is None:
            continue

        limit_2025, limit_2030, limit_2035 = bl["limits"][:3]

        def _gap_tons(lim):
            return round((intensity - lim) * sqft / 1000, 1)

        def _status(lim):
            return "Pass" if intensity <= lim else "Fail"

        breakdown_rows.append({
            "Address":        row["Building Address"],
            "Type":           bl["label"],
            "Sq Ft":          f"{int(sqft):,}",
            "GHG (kg/sf/yr)": round(intensity, 3),
            "2025 Limit":     limit_2025,
            "2025 Gap (MT)":  _gap_tons(limit_2025),
            "2025":           _status(limit_2025),
            "2030 Limit":     limit_2030,
            "2030 Gap (MT)":  _gap_tons(limit_2030),
            "2030":           _status(limit_2030),
            "2035 Limit":     limit_2035,
            "2035 Gap (MT)":  _gap_tons(limit_2035),
            "2035":           _status(limit_2035),
        })

    if breakdown_rows:
        breakdown_df = (
            pd.DataFrame(breakdown_rows)
            .sort_values("2025 Gap (MT)", ascending=False)
            .reset_index(drop=True)
        )
        st.dataframe(breakdown_df, use_container_width=True, hide_index=True)
        st.caption(
            "Gap (MT) = metric tons CO₂e above (+) or below (−) the period limit. "
            "Negative = surplus that can offset other buildings in the portfolio."
        )

    #Excluded buildings
    if excluded_rows:
        not_reported = sum(
            1 for r in excluded_rows if "did not report" in r["Exclusion Reason"].lower()
        )
        state_exempt = sum(
            1 for r in excluded_rows if "state status" in r["Exclusion Reason"].lower()
        )
        label_parts = [f"Excluded buildings ({skipped})"]
        if state_exempt:
            label_parts.append(f"{state_exempt} state status")
        if not_reported:
            label_parts.append(f"{not_reported} did not report")
        expander_label = " · ".join(label_parts)

        auto_expand = (skipped / total_buildings) > 0.3
        with st.expander(expander_label, expanded=auto_expand):
            st.caption(
                "These buildings are not included in the portfolio calculation. "
                "**State status** buildings are listed separately. Verify their BERDO treatment before excluding. "
                "**Did not report** means no energy data was submitted to the City of Boston, "
                "so their emissions are unknown and not reflected above. "
                "**Pending revisions** means data was submitted but flagged for corrections."
            )
            st.dataframe(
                pd.DataFrame(excluded_rows),
                use_container_width=True,
                hide_index=True,
            )

    st.markdown("---")

    #Application deadline callout
    st.info(
        f"**Portfolio applications are due September 1 each year** (next: "
        f"{_fmt_deadline('portfolio_ics')}). See the City's deadline table for which "
        "reporting year each deadline applies to. "
        "All buildings must have the same owner and no vacant properties may be included. "
        "Approval from the BERDO Review Board is required."
    )



#Year-over-year trend chart

def render_yoy_trend(address, all_years: dict[int, pd.DataFrame]):
    """
    Searches every loaded year for the given address and renders a
    year-over-year trend chart for GHG intensity and Site EUI.
    Returns the prior-year GHG intensity (float | None) for use in the
    compliance chart overlay, and the prior-year label string.
    """
    years_sorted = sorted(y for y in all_years if y != 0)
    if len(years_sorted) < 2:
        return None, None  #Nothing to compare

    import re
    search_std = (
        re.split(r',', address)[0].strip().upper()
        .replace(".", "").replace(" STREET", " ST")
        .replace(" AVENUE", " AVE").replace(" ROAD", " RD")
    )
    records = []
    for yr in years_sorted:
        df = all_years[yr]
        df_std = standardize_address_series(df["Building Address"])
        matches = df[df_std.str.startswith(search_std, na=False)]
        
        if matches.empty:
            continue
        row = matches.iloc[0]
        ghg = pd.to_numeric(row.get("ghg_intensity_kgco2e_sqft"), errors="coerce")
        eui = pd.to_numeric(row.get("site_eui"), errors="coerce")
        records.append({"year": yr, "ghg_intensity": ghg, "site_eui": eui})

    if len(records) < 2:
        return None, None

    trend_df = pd.DataFrame(records)

    st.subheader("Year-over-Year Trend")

    #Delta metrics row
    latest = trend_df.iloc[-1]
    prior  = trend_df.iloc[-2]

    ghg_delta  = latest["ghg_intensity"] - prior["ghg_intensity"]
    eui_delta  = latest["site_eui"]      - prior["site_eui"]

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            label=f"GHG Intensity {int(latest['year'])} (kg CO₂e/sf/yr)",
            value=f"{latest['ghg_intensity']:.3f}" if pd.notna(latest["ghg_intensity"]) else "N/A",
            delta=f"{ghg_delta:+.3f} vs {int(prior['year'])}" if pd.notna(ghg_delta) else None,
            delta_color="inverse",   #lower is better
        )
    with col2:
        st.metric(
            label=f"Site EUI {int(latest['year'])} (kBtu/sf/yr)",
            value=f"{latest['site_eui']:.1f}" if pd.notna(latest["site_eui"]) else "N/A",
            delta=f"{eui_delta:+.1f} vs {int(prior['year'])}" if pd.notna(eui_delta) else None,
            delta_color="inverse",
        )
    with col3:
        n_ghg = trend_df["ghg_intensity"].notna().sum()
        missing_ghg = trend_df.loc[trend_df["ghg_intensity"].isna(), "year"].astype(int).tolist()
        st.metric(label="Years of GHG data", value=int(n_ghg))
        if missing_ghg:
            st.caption(f"No data: {', '.join(str(y) for y in missing_ghg)}")
        else:
            st.caption("All years present")
    with col4:
        n_eui = trend_df["site_eui"].notna().sum()
        missing_eui = trend_df.loc[trend_df["site_eui"].isna(), "year"].astype(int).tolist()
        st.metric(label="Years of EUI data", value=int(n_eui))
        if missing_eui:
            st.caption(f"No data: {', '.join(str(y) for y in missing_eui)}")
        else:
            st.caption("All years present")

    #Trend chart
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=trend_df["year"].astype(str),
        y=trend_df["ghg_intensity"],
        name="GHG Intensity (kg CO₂e/sf/yr)",
        mode="lines+markers",
        line=dict(color="#E24B4A", width=2),
        marker=dict(size=8),
        connectgaps=True,
    ))

    fig.add_trace(go.Bar(
        x=trend_df["year"].astype(str),
        y=trend_df["site_eui"],
        name="Site EUI (kBtu/sf/yr)",
        marker_color="#3266ad",
        opacity=0.45,
        yaxis="y2",
    ))

    fig.update_layout(
        xaxis_title="Reporting year",
        xaxis_type="category",
        yaxis=dict(title="GHG Intensity (kg CO₂e/sf/yr)", side="left"),
        yaxis2=dict(
            title="Site EUI (kBtu/sf/yr)",
            overlaying="y",
            side="right",
            showgrid=False,
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=320,
        margin=dict(t=40, b=40, l=60, r=60),
        bargap=0.4,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.12)")

    st.plotly_chart(fig, use_container_width=True)

    if 2022 in [r["year"] for r in records] and trend_df.loc[trend_df["year"] == 2022, "ghg_intensity"].isna().all():
        st.caption(
            "2022 GHG intensity is not shown because the City of Boston did not publish "
            "GHG emissions totals in that year's dataset."
        )

    prior_ghg   = prior["ghg_intensity"] if pd.notna(prior["ghg_intensity"]) else None
    prior_label = str(int(prior["year"]))
    return prior_ghg, prior_label


#RETROFIT COST BENCHMARKS
#Source: ASHRAE, RSMeans, NBI New Construction Cost Study, DOE BTO
#Units: national baseline USD per sq ft (low, high), Boston multiplier applied separately
#NOT VERIFIED against a current source; treat as order-of-magnitude benchmarks.

RETROFIT_COST_PER_SQFT = {
    #scope → (low $/sqft national, high $/sqft national, notes)
    "Lighting (LED retrofit + controls)":               (1.5,   4.0,   "LED fixtures, occupancy sensors, daylight controls"),
    "HVAC (tune-up, controls, VFDs)":                   (3.0,   8.0,   "Controls upgrades, VFDs on pumps/fans, recommissioning"),
    "HVAC (full system replacement)":                   (15.0,  35.0,  "Chiller, AHU, or boiler replacement"),
    "Building envelope (windows + insulation)":         (8.0,   20.0,  "Window replacement, roof/wall insulation"),
    "Electrification: HVAC (air-source heat pump)":    (10.0,  22.0,  "Air-source heat pump: lower cost, suitable for most commercial buildings"),
    "Electrification: HVAC (ground-source heat pump)": (20.0,  45.0,  "Ground-source (geothermal): higher efficiency, significantly higher upfront cost"),
    "Electrification: water heating":                  (2.0,   6.0,   "Heat pump water heaters replacing gas"),
    "Building-wide deep retrofit (all systems)":        (40.0,  100.0, "Comprehensive envelope + MEP overhaul"),
}

#Boston labor cost multiplier vs. national RSMeans baseline
#Source: RSMeans City Cost Index, Boston MA (2024-2025 avg)
BOSTON_LABOR_MULTIPLIER = 1.25

#BERDO EMISSIONS FACTORS FOR FUELS
#Source: BERDO Emissions Factors List (City of Boston, updated September 18, 2026),
#"2025 Emissions Factors". The City uses Portfolio Manager factors "as adopted in January
#2025", which differ slightly from Portfolio Manager's August 2025 technical reference.
#The City's list governs BERDO, so those values are used here.
#VERIFIED September 23, 2026. Units: kg CO2e per kBtu (= kg/mmBtu ÷ 1000).

FUEL_EF_KG_PER_KBTU = {
    "Natural gas":      0.05311,   #53.11
    "Propane":          0.06425,   #64.25
    "Fuel oil #1":      0.07350,   #73.50
    "Fuel oil #2":      0.07421,   #74.21, distillate / home heating oil
    "Fuel oil #4":      0.07529,   #75.29
    "Fuel oil #5/#6":   0.07535,   #75.35, residual
    "Diesel":           0.07421,   #74.21
    "Kerosene":         0.07769,   #77.69
    "District steam":   0.06640,   #Default District Steam; named systems differ, see below
    "Electricity":      None,      #use effective_grid_ef(): Appendix B × (1 − RPS Class I)
}

#District energy system factors, kg CO2e/kBtu.
#VERIFIED September 23, 2026 against the BERDO Emissions Factors List (September 18, 2026).
#Not currently used in any calculation.
DISTRICT_STEAM_EF = {
    "Default (unknown system)":              0.06640,
    "Vicinity District Steam (Boston)":      0.05810,
    "Vicinity District Steam (Longfellow)":  0.05110,
    "Vicinity District e-steam":             0.0,
    "MATEP District Steam":                  0.06220,
}

#Official City of Boston BERDO links. Verified September 22, 2026.
PATHWAYS_VERIFIED = "September 22, 2026"
BERDO_LINKS = {
    "berdo_home":         "https://www.boston.gov/departments/environment/berdo",
    "review_board":       "https://www.boston.gov/departments/environment/berdo-review-board",
    "flex_guide":         "https://www.boston.gov/sites/default/files/berdo/BERDO_FlexibilityMeasures.pdf",
    "compliance_guide":   "https://www.boston.gov/sites/default/files/berdo/BERDO_EmissionsCompliance.pdf",
    "apply_portal":       "https://bostonopendata.knack.com/air-pollution-control-commission#berdo-home-page/",
    "blended_template":   "https://docs.google.com/spreadsheets/d/1kZ4flS4Dr0u2U5wMDH9h3Q_xwVlcr5ANo3_Wnc81mNs/edit?usp=sharing",
    "portfolio_template": "https://docs.google.com/spreadsheets/d/1Z1fD6vUdyvJl3OS66p00auXBx4KsEXlxmzjCYTOGzNU/edit?usp=sharing",
    "ics_template":       "https://docs.google.com/spreadsheets/d/1lHr4RMHERfzDaQtruZARovwTi3YELdXZDIIRIxI60fE/edit?usp=sharing",
    "hcp_guide":          "https://docs.google.com/document/d/1G5hdDeFVSbTRmivYXtfaTOBeVrwJHQUlesyZpNBlsNs/edit?usp=sharing",
    "hcp_streamlined":    "https://docs.google.com/document/d/1T4hWz9LM_MNnFO5sQ77bYbDjKRpvFD5Fcx3MEyMSoUs/edit?usp=sharing",
    "retrofit_hub":       "https://www.boston.gov/departments/environment/retrofit-resource-hub",
    "renewable_guide":    "https://www.boston.gov/sites/default/files/berdo/BERDO_RenewableEnergy.pdf",
    "rec_connector":      "https://www.boston.gov/departments/environment/berdo/how-purchase-ma-class-i-recs-berdo-compliance",
    "eeif":               "https://www.boston.gov/departments/environment/equitable-emissions-investment-fund",
    "out_of_compliance":  "https://www.boston.gov/node/16572006",
    "one_on_one":         "https://www.boston.gov/departments/environment/berdo#support",
    "advisor_program":    "https://www.boston.gov/departments/environment/building-decarbonization-advisor-program",
    "city_calculator":    "https://berdocalculator.touchstoneiq.com/",
    "approved_flex":      "https://docs.google.com/spreadsheets/d/1txTR6pdCedSiuN04uuh8p64atlTfjIbHImJDi0YGas4/edit?usp=sharing",
}

#Recurring annual Review Board application deadlines (month, day), per the
#BERDO Review Board page. Stored as month/day so the "next deadline" never goes stale.
FLEX_DEADLINES = {
    "long_term_hcp":  (7, 1),
    "portfolio_ics":  (9, 1),
    "short_term_hcp": (10, 1),
}


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


#MA Class I REC pathway (BERDO Renewable Energy Quick Guide; City REC Connector Program).
#Retiring 1 MA Class I REC covers 1 MWh of otherwise-unmatched grid electricity,
#avoiding PROJECTED_GRID_EF[year] kg CO2e. RECs offset ELECTRICITY emissions only.
REC_CONNECTOR_DEADLINE = "October 31, 2026"   #for 2025 emissions compliance
REC_DEFAULT_PRICE  = 40.0                 #USD/REC. Verify at berdo.greenenergyconsumers.org

#Convenient billing unit → kBtu conversions (EPA Portfolio Manager)
FUEL_UNIT_TO_KBTU = {
    "therms":   100.0,      #natural gas
    "ccf":      102.6,      #natural gas (hundred cubic feet)
    "mcf":      1026.0,     #natural gas (thousand cubic feet)
    "gallons_oil2":  138.0, #fuel oil #2
    "gallons_oil4":  146.0, #fuel oil #4
    "gallons_oil56": 150.0,  #fuel oil #5/#6
    "gallons_propane": 92.0,
    "gallons_diesel":  138.0,
    "gallons_kerosene": 135.0,
    "kbtu":     1.0,
    "mmbtu":    1000.0,
    "kwh":      3.412,      #electricity
    "mwh":      3412.0,     #electricity
}

def _fmt_dollars(val):
    """Format a dollar value with commas, no decimals."""
    return f"${val:,.0f}"

#INCENTIVE OPTIMIZER. data & logic

#Incentive stacking order: apply these first to preserve basis for later credits.
#Each entry has a priority rank (1 = apply first), conflict notes, and BERDO period relevance.
INCENTIVE_STACK = [
    {
        "name": "Mass Save: Commercial HVAC Rebates",
        "short": "Mass Save HVAC",
        "type": "Utility rebate",
        "priority": 1,
        "apply_first_reason": "Utility rebates are taxable income and reduce your 179D basis. Claim after filing taxes, but negotiate before project start.",
        "scopes": ["HVAC (tune-up, controls, VFDs)", "HVAC (full system replacement)",
                   "Electrification: HVAC (air-source heat pump)", "Electrification: HVAC (ground-source heat pump)"],
        "fuels": ["Natural gas", "Fuel oil", "Mixed / unknown", "Electric"],
        "amount_psf_low": 0.50,
        "amount_psf_high": 2.00,
        "amount_str": "USD 50–USD 300/ton cooling capacity; heat pump adders available",
        "eligibility": "MA commercial accounts with Eversource, National Grid, or Unitil",
        "expiration": "Program year 2026 (resets each January)",
        "conflicts": [],
        "stacks_with": ["IRA 179D", "IRA 45L"],
        "berdo_periods": ["2025–29", "2030–34"],
        "ownership": ["For-profit", "Nonprofit / Government"],
        "source": "https://www.masssave.com/saving/business-rebates",
        "checklist": [
            "Contact your utility (Eversource / National Grid / Unitil) before project start",
            "Get pre-approval from Mass Save (required before installation)",
            "Select a Mass Save Trade Ally contractor",
            "Complete installation and submit documentation",
            "Receive rebate check (typically 6–8 weeks post-completion)",
        ],
    },
    {
        "name": "Mass Save: Lighting Rebates",
        "short": "Mass Save Lighting",
        "type": "Utility rebate",
        "priority": 1,
        "apply_first_reason": "Pre-approval required before installation: start here.",
        "scopes": ["Lighting (LED retrofit + controls)"],
        "fuels": ["Natural gas", "Fuel oil", "Mixed / unknown", "Electric"],
        "amount_psf_low": 0.10,
        "amount_psf_high": 0.60,
        "amount_str": "USD 0.05–USD 0.30/kWh saved; fixture rebates vary by product",
        "eligibility": "MA commercial accounts",
        "expiration": "Program year 2026 (resets each January)",
        "conflicts": [],
        "stacks_with": ["IRA 179D"],
        "berdo_periods": ["2025–29", "2030–34"],
        "ownership": ["For-profit", "Nonprofit / Government"],
        "source": "https://www.masssave.com/saving/business-rebates",
        "checklist": [
            "Contact Mass Save or your utility for pre-approval",
            "Select eligible LED fixtures from the approved product list",
            "Complete installation with a Trade Ally contractor",
            "Submit lighting inventory and rebate application",
        ],
    },
    {
        "name": "Mass Save: Deep Energy Retrofit",
        "short": "Mass Save Deep Retrofit",
        "type": "Utility rebate",
        "priority": 1,
        "apply_first_reason": "Requires energy model and pre-approval. Begin 3–6 months before construction.",
        "scopes": ["Building-wide deep retrofit (all systems)",
                   "Building envelope (windows + insulation)"],
        "fuels": ["Natural gas", "Fuel oil", "Mixed / unknown", "Electric"],
        "amount_psf_low": 0.50,
        "amount_psf_high": 3.00,
        "amount_str": "Up to USD 400,000/project; custom incentive based on modeled savings",
        "eligibility": "MA commercial buildings; requires pre-approval and energy model",
        "expiration": "Program year 2026",
        "conflicts": [],
        "stacks_with": ["IRA 179D", "IRA 48C"],
        "berdo_periods": ["2025–29", "2030–34", "2035–39"],
        "ownership": ["For-profit", "Nonprofit / Government"],
        "source": "https://www.masssave.com/saving/large-business",
        "checklist": [
            "Submit a pre-application to Mass Save Large Business program",
            "Commission an ASHRAE Level 2 energy audit",
            "Develop an energy model (EnergyPlus or eQUEST)",
            "Receive custom incentive offer from Mass Save",
            "Execute project and submit final documentation",
        ],
    },
    {
        "name": "IRA Section 179D",
        "short": "IRA 179D",
        "type": "Federal tax deduction",
        "priority": 2,
        "apply_first_reason": "Claim after utility rebates are received. Rebates reduce your depreciable basis, which affects 179D calculation.",
        "scopes": ["Lighting (LED retrofit + controls)", "HVAC (tune-up, controls, VFDs)",
                   "HVAC (full system replacement)", "Building envelope (windows + insulation)",
                   "Electrification: HVAC (air-source heat pump)", "Electrification: HVAC (ground-source heat pump)", "Building-wide deep retrofit (all systems)"],
        "fuels": ["Natural gas", "Fuel oil", "Mixed / unknown", "Electric"],
        "amount_psf_low": 0.59,   #2026 base (IRS Form 7205 instructions; Rev. Proc. 2025-32)
        "amount_psf_high": 5.94,  #2026 maximum with prevailing wage and apprenticeship
        "cash_value_factor": 0.21,   #deduction, not credit: worth marginal rate × amount
        "closed_to_new_projects": True,
        "amount_str": "Up to USD 5.94/sqft (2026, prevailing wage and apprenticeship, Rev. Proc. 2025-32); USD 0.59–1.19/sqft base",
        "eligibility": "For-profit owners; nonprofits/govts transfer deduction to designer",
        "expiration": "Only available for construction that began on or before June 30, 2026 (One Big Beautiful Bill Act, P.L. 119-21). Confirm with a tax advisor if your project started before that date.",
        "conflicts": [],
        "stacks_with": ["Mass Save rebates", "IRA 45L"],
        "berdo_periods": ["2025–29"],
        "ownership": ["For-profit"],
        "ownership_transfer": "Nonprofit / Government",
        "ownership_transfer_note": "Nonprofits and government owners can allocate the deduction to the project designer/engineer.",
        "source": "https://www.energy.gov/eere/buildings/179d-commercial-buildings-energy-efficiency-tax-deduction",
        "checklist": [
            "179D only applies to construction that began on or before June 30, 2026. Confirm your project start date with a tax advisor",
            "Engage a qualified third-party certifier (licensed engineer or contractor)",
            "Commission a 179D energy model demonstrating qualifying energy savings",
            "Ensure prevailing wage + apprenticeship compliance for the enhanced rate",
            "Obtain signed certification from the certifier",
            "Claim deduction on federal tax return (Form 3115 if prior year)",
        ],
    },
    {
        "name": "IRA Section 45L (multifamily)",
        "short": "IRA 45L",
        "type": "Federal tax credit",
        "priority": 2,
        "apply_first_reason": "Claim alongside 179D: these stack. Document unit-level improvements during construction.",
        "scopes": ["Electrification: HVAC (air-source heat pump)", "Electrification: HVAC (ground-source heat pump)",
                   "Building-wide deep retrofit (all systems)"],
        "fuels": ["Natural gas", "Fuel oil", "Mixed / unknown", "Electric"],
        "amount_psf_low": 0.50,
        "amount_psf_high": 5.00,
        "closed_to_new_projects": True,
        "amount_str": "USD 500–USD 2,500/unit (Energy Star); USD 1,000–USD 5,000/unit (Zero Energy Ready)",
        "eligibility": "Multifamily residential; new construction and substantial rehab",
        "expiration": "Terminated for homes acquired after June 30, 2026 (One Big Beautiful Bill Act, P.L. 119-21). Confirm eligibility with a tax advisor.",
        "conflicts": [],
        "stacks_with": ["Mass Save rebates", "IRA 179D"],
        "berdo_periods": ["2025–29", "2030–34"],
        "ownership": ["For-profit"],
        "berdo_types": ["Multifamily Housing"],
        "source": "https://www.irs.gov/credits-deductions/energy-efficient-home-credit",
        "checklist": [
            "Determine unit count and confirm project qualifies as 'substantial rehab'",
            "Select Energy Star or DOE Zero Energy Ready Home certification path",
            "Commission third-party Energy Star rater during construction",
            "Obtain Energy Star or ZERH certification for each unit",
            "Claim credit on federal return (Form 8908)",
        ],
    },
    {
        "name": "IRA Section 48C",
        "short": "IRA 48C",
        "type": "Federal tax credit",
        "priority": 3,
        "apply_first_reason": "Competitive allocation: apply early via IRS portal. May conflict with other IRA investment credits.",
        "scopes": ["Electrification: HVAC (air-source heat pump)", "Electrification: HVAC (ground-source heat pump)", "Electrification: water heating",
                   "Building-wide deep retrofit (all systems)"],
        "fuels": ["Natural gas", "Fuel oil", "Mixed / unknown"],
        "closed_to_new_projects": True,   #manufacturing-facility allocation; $10B fully allocated 2024
        "amount_psf_low": 0.60,
        "amount_psf_high": 3.00,
        "amount_str": "6% base (30% with prevailing wage and apprenticeship); capped per project",
        "eligibility": "Competitive allocation; manufacturing/industrial sites prioritized",
        "expiration": "Closed. The full USD 10B was allocated across two rounds (about USD 4B in March 2024, about USD 6B in January 2025). OBBBA sec. 70515 (P.L. 119-21) caps allocations at USD 10B, so no further rounds are expected.",
        "conflicts": ["IRA 48E", "Other IRA investment credits on same property"],
        "stacks_with": ["Mass Save rebates"],
        "berdo_periods": ["2025–29", "2030–34"],
        "ownership": ["For-profit"],
        "source": "https://www.irs.gov/credits-deductions/businesses/advanced-energy-project-credit",
        "checklist": [
            "No open allocation rounds: the USD 10B cap is fully allocated. Listed for reference only.",
            "Prepare project application (technology description, cost, job creation)",
            "Submit application during open window (allocations are competitive)",
            "If awarded, begin construction within required timeframe",
            "Comply with prevailing wage + apprenticeship for 30% rate",
            "Claim credit on federal return (Form 3468)",
        ],
    },
    {
        "name": "MassDEP Gap Energy Grant",
        "short": "MassDEP Gap Grant",
        "type": "State grant",
        "priority": 1,
        "apply_first_reason": "Competitive rounds with fixed deadlines; the grant fills the last funding gap after utility incentives.",
        "scopes": ["Lighting (LED retrofit + controls)", "HVAC (tune-up, controls, VFDs)",
                   "HVAC (full system replacement)", "Electrification: HVAC (air-source heat pump)",
                   "Electrification: HVAC (ground-source heat pump)", "Electrification: water heating",
                   "Building-wide deep retrofit (all systems)"],
        "fuels": ["Natural gas", "Fuel oil", "Mixed / unknown", "Electric"],
        "amount_psf_low": 0.0,
        "amount_psf_high": 0.0,   #per-project grant (USD 75,000 to 350,000); no $/sqft proxy
        "amount_str": "Gap IV round: USD 75,000 to 350,000 per grantee; USD 5M total program",
        "eligibility": "Narrow: publicly owned drinking water and wastewater facilities, food or agricultural nonprofits, and small food distribution or processing businesses. Most BERDO buildings will not qualify.",
        "expiration": "Periodic competitive rounds run by MassDEP's Clean Energy Results Program; check mass.gov for the current round",
        "conflicts": [],
        "stacks_with": ["Mass Save rebates"],
        "berdo_periods": ["2025–29", "2030–34"],
        "ownership": ["Nonprofit / Government", "For-profit"],
        "source": "https://mass.gov/info-details/massachusetts-gap-energy-grant-program",
        "checklist": [
            "Confirm your facility type is eligible for the current round",
            "Line up utility incentives (e.g., Mass Save) first; the grant fills the remaining gap",
            "Submit the application by the round's deadline",
            "Complete the project and submit documentation for reimbursement",
        ],
    },
    {
        "name": "Green Communities Grant",
        "short": "Green Communities",
        "type": "State grant",
        "priority": 1,
        "apply_first_reason": "Annual grant cycle: apply in the current round.",
        "scopes": ["Lighting (LED retrofit + controls)", "HVAC (tune-up, controls, VFDs)",
                   "HVAC (full system replacement)", "Building envelope (windows + insulation)",
                   "Electrification: HVAC (air-source heat pump)", "Electrification: HVAC (ground-source heat pump)",
                   "Building-wide deep retrofit (all systems)"],
        "fuels": ["Natural gas", "Fuel oil", "Mixed / unknown", "Electric"],
        "amount_psf_low": 0.0,
        "amount_psf_high": 0.0,   #per-municipality formula grant: no $/sqft proxy is meaningful
        "amount_str": "Competitive grants capped at USD 250,000 per municipality, or USD 500,000 for comprehensive building decarbonization",
        "eligibility": "Municipally owned buildings in MA communities with Green Community designation. Not available to private nonprofits.",
        "expiration": "Annual grant rounds; check DOER for current cycle",
        "conflicts": [],
        "stacks_with": ["Mass Save rebates"],
        "berdo_periods": ["2025–29", "2030–34", "2035–39"],
        "ownership": ["Nonprofit / Government"],
        "source": "https://www.mass.gov/info-details/green-communities-grants",
        "checklist": [
            "Confirm your municipality has Green Community designation",
            "Identify eligible measures in your approved Green Communities plan",
            "Submit application to DOER during open grant round",
            "Execute grant agreement and comply with reporting requirements",
        ],
    },
]

RETROFIT_SCOPES_OPT = list(RETROFIT_COST_PER_SQFT.keys())
FUEL_TYPES_OPT = ["Natural gas", "Fuel oil", "Electric", "District steam", "Mixed / unknown"]
OWNERSHIP_TYPES_OPT = ["For-profit", "Nonprofit / Government", "Not sure"]


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

def render_retrofit_optimizer_tab(prefill: dict = None):
    """
    Tab 3: Retrofit & Incentives (merged Retrofit Estimator + Incentive Optimizer).
    Collects building inputs once, then shows condition-adjusted cost estimates,
    matched incentives ranked by value, stacking order, and payback.
    Pre-fills from address lookup session state where available.
    """
    if prefill is None:
        prefill = {}

    st.write(
        "Estimate retrofit costs and find the right incentives in one place. "
        "Enter your building details and the scopes you're considering to see "
        "condition-adjusted cost ranges, matched funding programs, stacking order, and payback."
    )
    st.info(
        "**Federal tax rules and state grant caps verified September 22, 2026.** "
        "Mass Save dollar figures and retrofit costs are unverified estimates. "
        "Always confirm amounts at the source links before advising a client."
    )

    #Inputs
    
    #Inject prefill into session state when a new address lookup arrives.
    #We detect a "fresh" prefill by comparing the prefill address to the
    #last address we injected: if different, overwrite widget state.
    
    prefill_addr_key = prefill.get("address", "")
    last_injected    = st.session_state.get("opt_last_injected_addr", "")

    if prefill_addr_key and prefill_addr_key != last_injected:
        if prefill.get("sqft"):
            st.session_state["opt_sqft"] = int(prefill["sqft"])
        if prefill.get("berdo_category"):
            type_options_init = ["Select a type"] + sorted(BERDO_STANDARDS.keys())
            if prefill["berdo_category"] in type_options_init:
                st.session_state["opt_btype"] = prefill["berdo_category"]
        if prefill.get("primary_fuel"):
            if prefill["primary_fuel"] in FUEL_TYPES_OPT:
                st.session_state["opt_fuel"] = prefill["primary_fuel"]
        st.session_state["opt_last_injected_addr"] = prefill_addr_key

    st.subheader("Building inputs")
    col1, col2 = st.columns(2)

    with col1:
        sqft = st.number_input(
            "Gross floor area (sq ft)",
            min_value=1_000, max_value=5_000_000,
            value=st.session_state.get("opt_sqft", 50_000),
            step=1_000,
            help="Pre-filled from Address Lookup if available.",
            key="opt_sqft",
        )

        ownership = st.selectbox(
            "Ownership type",
            options=OWNERSHIP_TYPES_OPT,
            help="For-profit owners access IRA tax credits. Nonprofits/government access grants.",
            key="opt_ownership",
        )

    with col2:
        type_options = ["Select a type"] + sorted(BERDO_STANDARDS.keys())
        prefill_cat  = st.session_state.get("opt_btype", "Select a type")
        default_idx  = type_options.index(prefill_cat) if prefill_cat in type_options else 0
        selected_type = st.selectbox(
            "Building type (BERDO category)",
            options=type_options, index=default_idx,
            help="Pre-filled from Address Lookup if available.",
            key="opt_btype",
        )
        berdo_category = selected_type if selected_type != "Select a type" else None

        fuel = st.selectbox(
            "Primary heating fuel",
            options=FUEL_TYPES_OPT,
            help="Affects which electrification incentives apply.",
            key="opt_fuel",
        )

    #Fine exposure context (pre-filled from address lookup)
    
    prefill_fine = prefill.get("annual_fine_usd")
    prefill_ghg  = prefill.get("ghg_intensity")
    prefill_addr = prefill.get("address", "")

    if prefill_fine and prefill_fine > 0:
        st.info(
            f"Pre-filled from **{prefill_addr}**: "
            f"estimated annual BERDO fine USD {prefill_fine:,.0f}/yr "
            f"(2025–29 period, at {prefill_ghg:.3f} kg CO₂e/sqft/yr). "
            "Use the payback section below to compare against net retrofit cost."
        )

    #Retrofit scope
    
    st.subheader("Retrofit scope")
    st.caption("Select all measures you are considering.")

    scopes_selected = []
    scope_cols = st.columns(2)
    for i, (scope, (low, high, note)) in enumerate(RETROFIT_COST_PER_SQFT.items()):
        with scope_cols[i % 2]:
            if st.checkbox(f"**{scope}**", help=note, key=f"opt_scope_{i}"):
                scopes_selected.append(scope)

    if not scopes_selected:
        st.warning("Select at least one retrofit scope above to see incentive matches.")
        return

    #Estimated retrofit cost (folded in from the former Retrofit Estimator)
    st.markdown("---")
    st.subheader("Estimated retrofit cost")
    st.caption(
        "Order-of-magnitude ranges from RSMeans / ASHRAE / DOE benchmarks. "
        "Answer the condition question below to narrow the estimate. "
        "Get competitive bids before budgeting."
    )

    prior_audit = st.radio(
        "Has an energy audit or feasibility study been completed?",
        options=["Yes, ASHRAE Level 2 or equivalent", "No, rough estimate only"],
        index=1,
        key="opt_cond_audit",
        help=(
            "An audit replaces range assumptions with building-specific data. "
            "Without one, unknowns tend to push costs toward the upper half of the range, "
            "so this estimate defaults to the mid-range as a conservative starting point."
        ),
    )
    has_audit = "ASHRAE" in prior_audit
    if has_audit:
        position        = 0.20
        condition_label = "Audit complete: estimate toward low end"
    else:
        position        = 0.55
        condition_label = "No audit: mid-range estimate (actual scope may run higher)"

    apply_boston = st.checkbox(
        "Apply Boston labor cost multiplier (1.25x)",
        value=True, key="opt_boston_multiplier",
        help=(
            "Boston construction labor runs ~25% above the national RSMeans baseline "
            "(RSMeans City Cost Index, 2024–2025). Uncheck to see national benchmark figures."
        ),
    )
    multiplier = BOSTON_LABOR_MULTIPLIER if apply_boston else 1.0

    cost_rows = []
    total_cost_low = total_cost_high = total_cost_adjusted = 0.0
    for scope in scopes_selected:
        low_nat, high_nat, _ = RETROFIT_COST_PER_SQFT[scope]
        low_psf  = low_nat  * multiplier
        high_psf = high_nat * multiplier
        adj_psf  = low_psf + position * (high_psf - low_psf)
        cost_rows.append({
            "Scope":             scope,
            "Low ($/sqft)":      f"${low_psf:.2f}",
            "Adjusted ($/sqft)": f"${adj_psf:.2f}",
            "High ($/sqft)":     f"${high_psf:.2f}",
            "Low total":         _fmt_dollars(low_psf * sqft),
            "Adjusted total":    _fmt_dollars(adj_psf * sqft),
            "High total":        _fmt_dollars(high_psf * sqft),
        })
        total_cost_low      += low_psf  * sqft
        total_cost_high     += high_psf * sqft
        total_cost_adjusted += adj_psf  * sqft

    st.dataframe(pd.DataFrame(cost_rows), use_container_width=True, hide_index=True)

    _badge = "Low" if has_audit else "Mid"
    st.caption(
        f"{_badge} **{condition_label}**. Adjusted estimate: "
        f"**{_fmt_dollars(total_cost_adjusted)}** "
        f"(between low {_fmt_dollars(total_cost_low)} and high {_fmt_dollars(total_cost_high)})"
    )
    _cc1, _cc2, _cc3 = st.columns(3)
    _cc1.metric("Low estimate",       _fmt_dollars(total_cost_low),
                delta="Boston low" if apply_boston else "National low")
    _cc2.metric("Condition-adjusted", _fmt_dollars(total_cost_adjusted),
                delta=condition_label)
    _cc3.metric("High estimate",      _fmt_dollars(total_cost_high),
                delta="Boston high" if apply_boston else "National high")
    st.caption(
        ("Boston 1.25x multiplier applied to national RSMeans baselines. "
         if apply_boston else "National RSMeans baselines (no Boston multiplier). ") +
        "Adjusted estimate uses the low end with an audit on file, mid-range without one."
    )

    #Planned project, emissions reduction calculator
    st.markdown("---")
    st.subheader("Planned project: will it close the compliance gap?")
    st.caption(
        "Enter your planned energy reduction to see whether it brings your building "
        "into compliance. Uses the same emissions factors BERDO applies."
    )

    proj_cols = st.columns(3)
    with proj_cols[0]:
        proj_fuel = st.selectbox(
            "Fuel type being reduced",
            options=["Natural gas", "Fuel oil #1", "Fuel oil #2", "Fuel oil #4", "Fuel oil #5/#6",
                     "Propane", "Diesel", "Kerosene", "Electricity", "District steam"],
            key="proj_fuel_type",
            help="Select the fuel your retrofit will reduce or eliminate.",
        )
    with proj_cols[1]:
        unit_options = {
            "Natural gas":    ["therms", "ccf", "mcf", "kBtu", "MMBtu"],
            "Fuel oil #1":     ["gallons", "kBtu", "MMBtu"],
            "Fuel oil #2":    ["gallons", "kBtu", "MMBtu"],
            "Fuel oil #4":    ["gallons", "kBtu", "MMBtu"],
            "Fuel oil #5/#6": ["gallons", "kBtu", "MMBtu"],
            "Propane":        ["gallons", "kBtu", "MMBtu"],
            "Diesel":         ["gallons", "kBtu", "MMBtu"],
            "Kerosene":       ["gallons", "kBtu", "MMBtu"],
            "Electricity":    ["kWh", "MWh", "kBtu", "MMBtu"],
            "District steam": ["kBtu", "MMBtu", "therms"],
        }
        units = unit_options.get(proj_fuel, ["kBtu", "MMBtu"])
        proj_unit = st.selectbox(
            "Unit",
            options=units,
            key="proj_unit",
        )
    with proj_cols[2]:
        proj_amount = st.number_input(
            "Annual energy saved",
            min_value=0.0,
            value=0.0,
            step=1000.0,
            key="proj_amount",
            help="Annual reduction in consumption from this project.",
        )

    if proj_amount > 0:
        #Convert to kBtu
        unit_map = {
            "therms": 100.0, "ccf": 102.6, "mcf": 1026.0,
            "gallons": 138.0,  #default for oil; overridden below
            "kBtu": 1.0, "MMBtu": 1000.0,
            "kWh": 3.412, "MWh": 3412.0,
        }
        #Override gallon factor by fuel type
        if proj_unit == "gallons":
            gal_factor = {
                "Fuel oil #1": 135.0,
                "Fuel oil #2": 138.0, "Fuel oil #4": 146.0,
                "Fuel oil #5/#6": 150.0, "Propane": 92.0,
                "Diesel": 138.0, "Kerosene": 135.0,
            }.get(proj_fuel, 138.0)
            proj_kbtu = proj_amount * gal_factor
        else:
            proj_kbtu = proj_amount * unit_map.get(proj_unit, 1.0)

        #Calculate emissions reduction
        if proj_fuel == "Electricity":
            #BERDO-effective grid EF (Appendix B × (1 − RPS Class I)), kg/MWh → kg/kBtu.
            #This section answers "does it close the 2025–29 gap?", so use that
            #period's representative year to match the limit being compared against.
            ef = effective_grid_ef(PERIOD_REPRESENTATIVE_YEARS[0]) / 1000 / 3.412
        else:
            ef = FUEL_EF_KG_PER_KBTU[proj_fuel]
        
        proj_emission_reduction_kg  = proj_kbtu * ef           #kg CO₂e/yr
        proj_emission_reduction_mt  = proj_emission_reduction_kg / 1000  #metric tons
        proj_intensity_reduction    = proj_emission_reduction_kg / sqft  #kg/sqft/yr

        res_cols = st.columns(3)
        res_cols[0].metric(
            "Estimated emission reduction",
            f"{proj_emission_reduction_mt:,.1f} metric tons CO₂e/yr",
        )
        res_cols[1].metric(
            "GHG intensity reduction",
            f"{proj_intensity_reduction:.3f} kg CO₂e/sqft/yr",
        )

        #Show compliance impact if we have the building's current GHG intensity
        prefill_ghg_proj = prefill.get("ghg_intensity")
        if prefill_ghg_proj and berdo_category and berdo_category in BERDO_STANDARDS:
            new_intensity = max(prefill_ghg_proj - proj_intensity_reduction, 0)
            limit_2025 = limits_for_category(berdo_category, prefill)[0]
            gap_before = prefill_ghg_proj - limit_2025
            gap_after  = new_intensity - limit_2025

            with res_cols[2]:
                if gap_after <= 0:
                    st.metric(
                        "2025–29 compliance after project",
                        "Compliant",
                        delta=f"{abs(gap_after):.3f} kg under limit",
                    )
                else:
                    st.metric(
                        "2025–29 compliance after project",
                        "Still non-compliant",
                        delta=f"{gap_after:.3f} kg over limit (was {gap_before:.3f})",
                    )

            if gap_after <= 0:
                st.success(
                    f"This project alone would bring the building into compliance for the "
                    f"2025–29 period. New estimated intensity: "
                    f"{new_intensity:.3f} kg CO₂e/sqft/yr (limit: {limit_2025} kg)."
                )
            elif gap_before > 0:
                pct_closed = min(round((gap_before - gap_after) / gap_before * 100, 0), 100)
                remaining_mt = round(gap_after * sqft / 1000, 1)
                st.info(
                    f"This project closes **{pct_closed:.0f}%** of the 2025–29 compliance gap. "
                    f"Remaining gap: {gap_after:.3f} kg CO₂e/sqft/yr "
                    f"({remaining_mt:,.0f} excess metric tons). "
                    f"Additional measures or an Alternative Compliance Payment would be needed."
                )
        else:
            st.caption(
                "Look up your building in the Address Lookup tab to see how this project "
                "affects your compliance gap."
            )

        #Update the energy savings input with the calculated savings
        st.caption(
            f"Tip: enter this project's energy cost savings in the Cash flow & payback "
            f"section below to model the full financial return."
        )
    else:
        st.caption(
            "Enter a planned annual energy reduction above to see its compliance impact."
        )

    #Match incentives
    matched = [
        inc for inc in INCENTIVE_STACK
        if _opt_incentive_applies(inc, scopes_selected, fuel, ownership, berdo_category)
    ]

    if not matched:
        st.info(
            "No incentives matched your inputs. "
            "Try adjusting ownership type, fuel, or scope, "
            "or check masssave.com and masscec.com directly."
        )
        return

    #Dollar estimates
    for inc in matched:
        inc["_est_low"], inc["_est_high"] = _estimate_incentive_value(inc, sqft)

    total_incentive_low  = sum(i["_est_low"]  for i in matched)
    total_incentive_high = sum(i["_est_high"] for i in matched)

    #Gross retrofit cost. Reuse the Boston-multiplier + condition-adjusted totals
    #Computed in the "Estimated retrofit cost" section above, so the cost shown
    #There and the net cost here are consistent. (Previously this recomputed raw
    #National baselines, understating cost whenever the Boston multiplier applied.)
    #total_cost_low / total_cost_high already set above.

    #Net cost (incentives capped at gross cost)
    net_low  = max(total_cost_low  - total_incentive_high, 0)
    net_high = max(total_cost_high - total_incentive_low,  0)

    #Headline summary card
    st.markdown("---")

    #Build the headline sentence
    incentive_str   = _fmt_dollars(total_incentive_high).replace("$", "USD ")
    net_low_display = "fully covered by incentives" if net_low == 0 else _fmt_dollars(net_low).replace("$", "USD ")
    prefill_fine_val = prefill.get("annual_fine_usd", 0) or 0
    default_energy   = 1.0 * sqft  #$1/sqft default energy savings
    total_return     = prefill_fine_val + default_energy

    #Cap headline payback. Don't show absurd numbers for large buildings
    if prefill_fine_val > 0 and total_return > 0 and net_low > 0:
        headline_payback_raw = net_low / total_return
        if headline_payback_raw <= 50:
            payback_str = f", with an estimated {round(headline_payback_raw, 1)}-year payback including energy savings"
        else:
            payback_str = ". Energy savings are the primary return driver for a building this size"
    elif prefill_fine_val > 0 and net_low == 0:
        payback_str = ", with the retrofit fully covered by incentives"
    else:
        payback_str = ""

    headline = (
        f"For this building, you qualify for up to {incentive_str} "
        f"in incentives, reducing your estimated net retrofit cost to {net_low_display}"
        f"{payback_str}."
    )

    st.info(headline)

    st.markdown("---")

    #Summary metric cards
    st.subheader("Summary")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Incentive programs matched", len(matched))
    m2.metric("Total incentives (low–high)",
              f"USD {total_incentive_low:,.0f} – {total_incentive_high:,.0f}")
    m3.metric("Gross retrofit cost (low–high)",
              f"USD {total_cost_low:,.0f} – {total_cost_high:,.0f}")
    m4.metric("Estimated net cost (low–high)",
              f"USD {net_low:,.0f} – {net_high:,.0f}")

    st.caption(
        "Incentive estimates are $/sqft proxies based on program benchmarks. "
        "Actual awards depend on application, project scope, and program availability. "
        "Tax **deductions** are shown at after-tax cash value (21% corporate rate), not face value. "
        "Programs closed to new projects (IRA 179D and 45L, both terminated for work beginning "
        "after June 30, 2026) are excluded from these totals. "
        "Gross cost benchmarks from RSMeans / ASHRAE / DOE BTO (2024–2026)."
    )

    #Ranked incentive table
    st.markdown("---")
    st.subheader("Incentives ranked by estimated value")

    ranked = sorted(matched, key=lambda x: x["_est_high"], reverse=True)

    rank_rows = []
    for inc in ranked:
        conflict_flag = "; ".join(inc["conflicts"]) if inc["conflicts"] else "None"
        rank_rows.append({
            "Program": inc["short"],
            "Type": inc["type"],
            "Est. value (low)": f"${inc['_est_low']:,.0f}",
            "Est. value (high)": f"${inc['_est_high']:,.0f}",
            "Applies in": ", ".join(inc["berdo_periods"][:2]),
            "Conflicts": conflict_flag,
        })

    st.dataframe(pd.DataFrame(rank_rows), use_container_width=True, hide_index=True)

    #Stacking strategy
    st.markdown("---")
    st.subheader("Stacking strategy: apply in this order")
    st.caption(
        "Order matters. Utility rebates reduce your tax basis; "
        "some IRA credits conflict with each other. Follow this sequence."
    )

    steps = sorted(matched, key=lambda x: x["priority"])
    for i, inc in enumerate(steps, 1):
        with st.expander(
            f"**{i}. {inc['name']}**: {inc['type']} "
            f"(est. USD {inc['_est_low']:,.0f} – {inc['_est_high']:,.0f})",
            expanded=(i <= 2),
        ):
            col_a, col_b = st.columns([2, 1])
            with col_a:
                st.markdown(f"**Why this order:** {inc['apply_first_reason']}")
                st.markdown(f"**Amount:** {inc['amount_str']}")
                st.markdown(f"**Eligible:** {inc['eligibility']}")
                st.markdown(f"**Applies to BERDO periods:** {', '.join(inc['berdo_periods'])}")
                if inc["conflicts"]:
                    st.warning(
                        f"**Potential conflicts:** {', '.join(inc['conflicts'])}. "
                        "Verify with a tax advisor before claiming both."
                    )
                else:
                    stacks = ", ".join(inc["stacks_with"]) if inc["stacks_with"] else "No conflicts identified"
                    st.success(f"**Stacks cleanly with:** {stacks}")
                if ownership == "Not sure" and "For-profit" in inc["ownership"] and "Nonprofit / Government" not in inc["ownership"]:
                    st.warning("This incentive is available to for-profit owners only. Confirm your ownership structure.")
                if "ownership_transfer_note" in inc:
                    st.info(f"{inc['ownership_transfer_note']}")
            with col_b:
                st.markdown(f"**Expires:** {inc['expiration']}")
                st.markdown(f"[Apply / learn more →]({inc['source']})")

    #Application checklist
    st.markdown("---")
    st.subheader("Application checklist")
    st.caption("Complete these steps for each matched program.")

    for inc in steps:
        with st.expander(f"**{inc['name']}** checklist", expanded=False):
            for step in inc["checklist"]:
                st.checkbox(step, key=f"chk_{inc['short']}_{step[:20]}")
            st.markdown(f"[Source / apply →]({inc['source']})")

    #Cash flow & payback
    st.markdown("---")
    st.subheader("Cash flow & payback")

    annual_fine = prefill_fine if prefill_fine else None

    if annual_fine is None:
        st.caption(
            "Look up your building in the Address Lookup tab to pre-fill your "
            "estimated annual BERDO fine, or enter it manually below."
        )
        annual_fine_input = st.number_input(
            "Estimated annual BERDO fine ($/yr)",
            min_value=0, value=0, step=1_000,
            key="opt_fine_manual",
        )
        if annual_fine_input > 0:
            annual_fine = annual_fine_input

    if annual_fine and annual_fine > 0:

        #Energy savings input 
        st.caption(
            "Energy cost savings from a retrofit are typically the largest financial return, "
            "often larger than fine avoidance alone. Enter an estimate below to include them."
        )
        energy_cols = st.columns([1, 1, 2])
        with energy_cols[0]:
            energy_savings_psf = st.number_input(
                "Energy savings ($/sqft/yr)",
                min_value=0.0, max_value=10.0,
                value=1.00, step=0.25,
                key="opt_energy_savings_psf",
                help=(
                    "Typical range for Boston commercial buildings: "
                    "USD 0.50–1.50/sqft/yr for HVAC upgrades; "
                    "USD 1.00–2.50/sqft/yr for deep retrofits. "
                    "Set to 0 to see fine avoidance only."
                ),
            )
        with energy_cols[1]:
            energy_savings_annual = energy_savings_psf * sqft
            st.metric(
                "Annual energy savings",
                _fmt_dollars(energy_savings_annual),
                delta=f"at {energy_savings_psf:.2f}/sqft/yr",
            )
        with energy_cols[2]:
            st.caption(
                "Sources: ASHRAE, DOE BTO, and MA utility program data suggest "
                "USD 0.50–1.00/sqft/yr for controls and lighting, "
                "USD 1.00–2.00/sqft/yr for HVAC replacement, and "
                "USD 1.50–3.00/sqft/yr for deep retrofits. "
                "Use 0 to see a conservative fine-avoidance-only view."
            )

        #Combined annual benefit
        total_annual_benefit = annual_fine + energy_savings_annual

        #Payback metrics: cap at 50 years; beyond that fine avoidance is the wrong frame
        PAYBACK_CAP = 50

        payback_low_fine_only  = round(net_low  / annual_fine, 1) if net_low  > 0 else 0.0
        payback_high_fine_only = round(net_high / annual_fine, 1) if net_high > 0 else 0.0
        payback_low_combined   = round(net_low  / total_annual_benefit, 1) if net_low  > 0 else 0.0
        payback_high_combined  = round(net_high / total_annual_benefit, 1) if net_high > 0 else 0.0

        def _fmt_payback(yrs):
            if yrs == 0:
                return "< 1 yr"
            if yrs > PAYBACK_CAP:
                return "Fine avoidance insufficient"
            return f"{yrs} yrs"

        fine_only_impractical = payback_low_fine_only > PAYBACK_CAP

        pb_cols = st.columns(4)
        pb_cols[0].metric(
            "Payback: fine only (low)",
            _fmt_payback(payback_low_fine_only),
        )
        pb_cols[1].metric(
            "Payback: fine only (high)",
            _fmt_payback(payback_high_fine_only),
        )
        pb_cols[2].metric(
            "Payback: fine + energy (low)",
            _fmt_payback(payback_low_combined),
            delta=f"{round(payback_low_fine_only - payback_low_combined, 1)} yrs faster"
                  if 0 < payback_low_fine_only <= PAYBACK_CAP and payback_low_combined <= PAYBACK_CAP and payback_low_fine_only > payback_low_combined
                  else None,
        )
        pb_cols[3].metric(
            "Payback: fine + energy (high)",
            _fmt_payback(payback_high_combined),
            delta=f"{round(payback_high_fine_only - payback_high_combined, 1)} yrs faster"
                  if 0 < payback_high_fine_only <= PAYBACK_CAP and payback_high_combined <= PAYBACK_CAP and payback_high_fine_only > payback_high_combined
                  else None,
        )

        if fine_only_impractical:
            st.warning(
                f"For a building this size ({sqft:,} sqft), BERDO fines alone do not justify "
                "the retrofit cost. This is normal for large commercial buildings: "
                "the financial case rests on **energy cost savings** and **asset value**, not fine avoidance. "
                f"At {energy_savings_psf:.2f}/sqft/yr in energy savings, the combined payback is "
                f"**{_fmt_payback(payback_low_combined)}** at the low estimate."
            )

        #Cash flow chart
        years = list(range(0, 16))
        cumulative_low_fine   = [-net_low  + annual_fine * y for y in years]
        cumulative_high_fine  = [-net_high + annual_fine * y for y in years]
        cumulative_low_total  = [-net_low  + total_annual_benefit * y for y in years]
        cumulative_high_total = [-net_high + total_annual_benefit * y for y in years]

        fig = go.Figure()

        if energy_savings_psf > 0:
            fig.add_trace(go.Scatter(
                x=years, y=cumulative_low_total,
                name="Low cost + energy savings",
                mode="lines", line=dict(color="#1D9E75", width=2.5),
                fill="tozeroy", fillcolor="rgba(29,158,117,0.08)",
            ))
            fig.add_trace(go.Scatter(
                x=years, y=cumulative_high_total,
                name="High cost + energy savings",
                mode="lines", line=dict(color="#1D9E75", width=1.5, dash="dot"),
            ))
            fig.add_trace(go.Scatter(
                x=years, y=cumulative_low_fine,
                name="Low cost, fine avoidance only",
                mode="lines", line=dict(color="#3266ad", width=1.5, dash="dash"),
            ))
            fig.add_trace(go.Scatter(
                x=years, y=cumulative_high_fine,
                name="High cost, fine avoidance only",
                mode="lines", line=dict(color="#9B59B6", width=1.5, dash="dash"),
            ))
        else:
            fig.add_trace(go.Scatter(
                x=years, y=cumulative_low_fine,
                name="Low net cost",
                mode="lines", line=dict(color="#1D9E75", width=2),
                fill="tozeroy", fillcolor="rgba(29,158,117,0.08)",
            ))
            fig.add_trace(go.Scatter(
                x=years, y=cumulative_high_fine,
                name="High net cost",
                mode="lines", line=dict(color="#3266ad", width=2, dash="dash"),
            ))

        fig.add_hline(
            y=0, line_width=1, line_dash="dot",
            line_color="rgba(128,128,128,0.5)",
            annotation_text="Break-even", annotation_position="right",
        )
        fig.update_layout(
            xaxis_title="Years from retrofit",
            yaxis_title="Cumulative cash flow (USD)",
            height=340,
            margin=dict(t=30, b=40, l=60, r=60),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(gridcolor="rgba(128,128,128,0.12)")
        st.plotly_chart(fig, use_container_width=True)

        energy_note = (
            f"Green lines include {_fmt_dollars(energy_savings_annual)}/yr in energy savings "
            f"at {energy_savings_psf:.2f}/sqft/yr. Dashed lines show fine avoidance only. "
            if energy_savings_psf > 0 else
            "Set energy savings above zero to see how savings shorten payback. "
        )
        st.caption(
            energy_note +
            "Not an investment projection. Energy savings are estimates; actual savings "
            "depend on building operations, utility rates, and project scope. "
            "Consult a licensed energy auditor for project-specific figures."
        )

        #Payback summary message
        best_payback = payback_low_combined if energy_savings_psf > 0 else payback_low_fine_only
        if best_payback == 0:
            st.success(
                "At the low net cost estimate, the retrofit is fully covered by incentives, "
                "so any energy savings and fine avoidance are pure return from day one."
            )
        elif best_payback <= 7:
            st.success(
                f"Strong financial case: best-case payback is **{best_payback} years** "
                f"({'fine avoidance + energy savings' if energy_savings_psf > 0 else 'fine avoidance alone'}). "
                "This is well within typical commercial real estate investment horizons."
            )
        elif best_payback <= 12:
            st.info(
                f"Reasonable case: best-case payback is **{best_payback} years**. "
                "Within a standard hold period for most commercial properties. "
                + ("Increasing energy savings or reducing net cost would strengthen the case." if energy_savings_psf < 1.0 else "")
            )
        elif best_payback <= PAYBACK_CAP:
            st.info(
                f"Longer payback: best-case is **{best_payback} years**. "
                "Consider whether a phased retrofit, with higher-ROI measures first, "
                "improves the near-term economics."
            )
        else:
            #Large building: fine avoidance is the wrong frame entirely
            energy_annual_str = _fmt_dollars(energy_savings_annual).replace("$", "USD ")
            st.info(
                "For a building this size, the primary financial drivers are **energy cost savings** "
                f"({energy_annual_str}/yr at current assumptions) and **asset value protection**, "
                "not fine avoidance alone. Consider: lender and investor ESG requirements, "
                "tenant retention in a market increasingly sensitive to building performance, "
                "and the cost trajectory of fines as BERDO limits tighten toward 2050. "
                "Adjust the energy savings input above to model the full return."
            )

    #Retrofit vs. compliance decision
    st.subheader("Three paths: retrofit, RECs, or pay the ACP")
    st.caption(
        "Three ways to close a BERDO gap: retrofit the building, retire MA Class I RECs "
        "to offset electricity emissions, or pay the Alternative Compliance Payment. "
        "This section compares all three so you can make an informed decision."
    )

    if not annual_fine or annual_fine == 0:
        st.info(
            "Look up your building in the Address Lookup tab or enter your annual fine above "
            "to see the retrofit vs. compliance comparison."
        )
    elif berdo_category and berdo_category in BERDO_STANDARDS:
    
        #Cost of paying the fine across each compliance period
        fine_5yr  = annual_fine * 5

        #Future period fines: limits tighten each period
        limits = limits_for_category(berdo_category, prefill)
        prefill_ghg_val = prefill.get("ghg_intensity")

        period_fines = []
        if prefill_ghg_val:
            for i, period in enumerate(COMPLIANCE_PERIODS[:5]):
                limit = limits[i]
                gap = max(prefill_ghg_val - limit, 0)
                excess_tons = gap * sqft / 1000
                period_fines.append({
                    "period": period,
                    "limit": limit,
                    "annual_fine": round(excess_tons * ACP_RATE, 0),
                    "5yr_fine": round(excess_tons * ACP_RATE * 5, 0),
                })

        #Decision matrix
        st.markdown("Cost comparison. Retrofit now vs. pay escalating fines")
        st.caption(
            "BERDO fines grow every five years as the emissions limit tightens. "
            "The comparison below uses cumulative fines through 2050, not just the current period."
        )

        cumulative_fine_all = sum(r["5yr_fine"] for r in period_fines) if period_fines else fine_5yr
        cum_fine_10yr = sum(r["5yr_fine"] for r in period_fines[:2]) if len(period_fines) >= 2 else fine_5yr

        d1, d2, d3 = st.columns(3)
        d1.metric(
            "Fines: current period only (5 yrs)",
            _fmt_dollars(fine_5yr),
            delta="Grows each period as limits tighten",
        )
        d2.metric(
            "Fines: cumulative through 2050",
            _fmt_dollars(cumulative_fine_all),
            delta="If no retrofit is ever made",
        )
        d3.metric(
            "Retrofit: net cost (low estimate)",
            "Fully covered by incentives" if net_low == 0 else _fmt_dollars(net_low),
            delta="One-time outlay, fines avoided permanently",
        )

                #REC pathway: the third option
        st.markdown("#### Option 3: buy MA Class I RECs")
        st.caption(
            "BERDO lets you retire MA Class I RECs to offset electricity emissions. "
            "One REC covers 1 MWh and avoids the full grid emissions factor for that year. "
            "RECs cannot offset fossil fuel emissions."
        )
        rc1, rc2 = st.columns([1, 3])
        with rc1:
            rec_price = st.number_input(
                "REC price (USD/REC)", min_value=0.0, max_value=200.0,
                value=REC_DEFAULT_PRICE, step=5.0, key="opt_rec_price",
                help="Check current pricing at berdo.greenenergyconsumers.org. Prices move.",
            )
        _rec_gap_kg  = max(prefill_ghg_val - limits[0], 0) * sqft if prefill_ghg_val else 0
        _rec_share, _rec_share_src = resolve_elec_share(prefill, elec_share, use_reported_share)
        _rec_elec_kg = (prefill_ghg_val or 0) * sqft * _rec_share
        rec = rec_pathway(_rec_gap_kg, _rec_elec_kg, 2025, rec_price)
        if rec:
            with rc2:
                r1, r2, r3 = st.columns(3)
                r1.metric("MA Class I RECs needed", f"{rec['recs_needed']:,.0f}/yr")
                r2.metric("Annual REC cost", _fmt_dollars(rec["rec_cost"]))
                r3.metric("vs. paying the ACP",
                          _fmt_dollars(abs(rec["acp_only"] - rec["total_cost"])),
                          delta="cheaper per year" if rec["total_cost"] < rec["acp_only"]
                          else "more expensive per year",
                          delta_color="off")
            if rec["total_cost"] < rec["acp_only"]:
                st.success(
                    f"**RECs are cheaper than the ACP at this price.** "
                    f"{_fmt_dollars(rec['total_cost'])}/yr vs {_fmt_dollars(rec['acp_only'])}/yr in ACP, "
                    f"saving {_fmt_dollars(rec['acp_only'] - rec['total_cost'])}/yr. "
                    f"Break-even is **{rec['breakeven_price']:.2f} USD/REC** at the 2025 grid factor. "
                    f"RECs buy time, not compliance: they must be repurchased every year, and the "
                    f"break-even falls to {ACP_RATE * PROJECTED_GRID_EF[2050] / 1000:.2f} USD/REC by 2050 "
                    f"as the grid cleans up and each REC avoids less CO2e."
                )
            else:
                st.info(
                    f"**At {rec_price:.0f} USD/REC, paying the ACP is cheaper.** "
                    f"RECs would cost {_fmt_dollars(rec['total_cost'])}/yr vs "
                    f"{_fmt_dollars(rec['acp_only'])}/yr in ACP. "
                    f"Break-even is {rec['breakeven_price']:.2f} USD/REC."
                )
            if not rec["fully_covered"]:
                st.warning(
                    f"RECs offset electricity emissions only. "
                    f"{_fmt_dollars(rec['residual_acp'])}/yr in ACP would remain on the "
                    f"fossil-fuel portion of this building's gap."
                )
            st.caption(
                f"Assumes {fmt_share(_rec_share)} of this building's emissions come from "
                f"electricity ({_rec_share_src}). "
                f"Purchase deadline for 2025 compliance: **{REC_CONNECTOR_DEADLINE}** via the City's "
                "REC Connector Program (Green Energy Consumers Alliance), or any time through an "
                "independent broker. RECs must be MA Class I from non-emitting sources: solar, wind, "
                "small hydro, geothermal. Biomass and landfill gas do not qualify. BERDO's REC rules "
                "are under active revision; confirm before relying on this."
            )
        else:
            rec = None

        #Recommendation
        st.markdown("Recommendation")

        #Key insight: fines escalate, so compare retrofit against cumulative fines
        #not just one period. Also compute crossover period.
        running = 0
        crossover_period = None
        crossover_yr = None
        for r in period_fines:
            running += r["5yr_fine"]
            if running >= net_low and crossover_period is None:
                crossover_period = r["period"]

        net_low_str      = "fully covered by incentives" if net_low == 0 else _fmt_dollars(net_low).replace("$", "USD ")
        fine_5yr_str     = _fmt_dollars(fine_5yr).replace("$", "USD ")
        cum_str          = _fmt_dollars(cumulative_fine_all).replace("$", "USD ")
        cum_10yr_str     = _fmt_dollars(cum_fine_10yr).replace("$", "USD ")

        if net_low == 0 or net_low <= fine_5yr:
            #Retrofit cost is zero or cheaper than even one period of fines
            st.success(
                f"**Retrofit now: clear financial case.** The net retrofit cost "
                f"({net_low_str}) is less than or equal to one period of BERDO fines "
                f"({fine_5yr_str} for 2025–29 alone). "
                "And fines only grow from here. Each period the limit tightens and the "
                "gap widens. Retrofitting eliminates all future fine exposure permanently."
            )
        elif net_low <= cum_fine_10yr:
            #Retrofit pays back within 2 periods (10 years) of escalating fines
            st.success(
                f"**Retrofit soon: strong case once fines escalate.** "
                f"The net retrofit cost ({net_low_str}) is less than cumulative fines "
                f"over the first two periods ({cum_10yr_str} through 2030–34). "
                f"Fines increase each period as the BERDO limit tightens, "
                "so waiting means paying more before you eventually retrofit anyway."
            )
        elif net_low <= cumulative_fine_all:
            #Retrofit is cheaper than total lifetime fines, crossover at some period
            st.warning(
                f"**Consider phasing: fines will exceed retrofit cost by {crossover_period or 'a future period'}.** "
                f"Paying the fine costs less upfront ({fine_5yr_str} for 2025–29) "
                f"vs. retrofitting now ({net_low_str}). "
                f"However, BERDO limits tighten every 5 years. Your annual fine grows "
                f"each period as the gap between your building's emissions and the limit widens. "
                f"Cumulative fines reach {cum_str} through 2050 if nothing is done. "
                "A phased approach (lower-cost measures now, deeper retrofit before the next "
                "period tightens) may be the most cost-effective path."
            )
        else:
            #Even cumulative fines are less than net retrofit cost
            net_high_str = _fmt_dollars(net_high).replace("$", "USD ")
            low_sav_str  = _fmt_dollars(round(sqft * 1.0)).replace("$", "USD ")
            high_sav_str = _fmt_dollars(round(sqft * 2.0)).replace("$", "USD ")
            st.info(
                f"**Fine avoidance alone does not justify this retrofit.** "
                f"Even cumulative BERDO fines through 2050 ({cum_str}) are less than "
                f"the high net retrofit cost ({net_high_str}). "
                f"However, this excludes energy savings "
                f"(typically {low_sav_str}–{high_sav_str}/yr), asset value protection, "
                "and lender/investor ESG requirements, which for large buildings often "
                "dwarf the fine exposure. Run the numbers with your energy consultant "
                "before ruling out the retrofit."
            )

        #Period-by-period fine escalation table
        if period_fines:
            st.markdown("Fine escalation by period")
            st.caption(
                "Each period the BERDO limit drops. If your building's emissions stay flat, "
                "the gap, and the fine, grows. The right column shows when cumulative "
                "fines exceed the low net retrofit cost."
            )

            fine_rows = []
            running_total = 0
            for r in period_fines:
                running_total += r["5yr_fine"]
                fine_rows.append({
                    "Period":              r["period"],
                    "BERDO limit":         f"{r['limit']} kg CO₂e/sf/yr",
                    "Annual fine":         f"${r['annual_fine']:,.0f}",
                    "5-yr period fine":    f"${r['5yr_fine']:,.0f}",
                    "Cumulative fines":    f"${running_total:,.0f}",
                    "vs. retrofit (low)":  (
                        "Fines now cheaper"
                        if running_total < net_low
                        else "Cumulative fines exceed retrofit"
                    ),
                })

            st.dataframe(
                pd.DataFrame(fine_rows),
                use_container_width=True,
                hide_index=True,
            )

            st.caption(
                "Assumes current GHG intensity held flat with no operational changes. "
                "Grid decarbonization would reduce electricity-attributed fines over time. "
                "Not an official BERDO compliance determination."
            )
    else:
        st.info(
            "Select a building type above to see the retrofit vs. fine comparison."
        )

    #Phasing by BERDO period
    st.markdown("---")
    st.subheader("Phasing by BERDO compliance period")
    st.caption(
        "Not all work needs to happen at once. This shows which incentives "
        "are available in each compliance period to help you phase investment."
    )

    period_map: dict[str, list] = {p: [] for p in COMPLIANCE_PERIODS[:3]}
    for inc in matched:
        for p in inc["berdo_periods"]:
            if p in period_map:
                period_map[p].append(inc["short"])

    ph_cols = st.columns(3)
    for col, period in zip(ph_cols, COMPLIANCE_PERIODS[:3]):
        with col:
            st.markdown(f"**{period}**")
            if period_map[period]:
                for name in period_map[period]:
                    st.markdown(f"- {name}")
            else:
                st.caption("No matched incentives")

    #Disclaimer
    st.markdown("---")
    st.warning(
        "**Screening tool only. Not professional financial or tax advice.** "
        "Incentive amounts are estimates; see Sources & verification in the sidebar. "
        "IRA credit stacking rules are complex; consult a tax advisor for your specific situation. "
        "Do not use these figures for contracts, loan applications, or compliance filings."
    )

    with st.expander("Sources & methodology"):
        st.markdown("""
**Incentive data sources (checked September 22, 2026)**
- Mass Save commercial rebates: masssave.com (amounts reset each January; this tool's $/sqft figures are unverified estimates)
- IRA Section 179D: inflation-adjusted amounts per Rev. Proc. 2024-40 (2025) and Rev. Proc. 2025-32 (2026)
- IRA Section 48C: IRS Notice 2023-18 and Notice 2023-44; allocation rounds closed
- IRA Section 45L: IRS Notice 2023-65; terminated for homes acquired after June 30, 2026 (P.L. 119-21)
- IRA Section 179D: terminated for property whose construction begins after June 30, 2026 (P.L. 119-21)
- MassDEP Gap Energy Grant: mass.gov, Clean Energy Results Program (narrow eligibility; USD 75,000 to 350,000 per grantee in the Gap IV round)
- Green Communities: mass.gov (competitive grants capped at USD 250,000 per municipality, or USD 500,000 for comprehensive building decarbonization)

**Stacking methodology**
Utility rebates (Mass Save) are taxable income and reduce your 179D depreciable basis, so
claim them before calculating your 179D deduction. IRA 48C may conflict with other IRA
investment credits applied to the same property. Verify with a tax advisor. All other
matched programs stack cleanly for most commercial scenarios.

**Dollar estimates**
Incentive values are estimated using $/sqft proxies derived from published program benchmarks.
Actual awards depend on application outcome, project documentation, and contractor certification.
""")

#EMISSIONS PLANNER, Tab 5

def render_emissions_planner_tab(prefill: dict = None, show_grid_decarb: bool = False, elec_share=None,
                                 use_reported_share: bool = True):
    """
    Tab 5: Emissions Planner.
    Shows compliance projection table across all BERDO periods,
    allows users to enter planned emission reduction projects,
    and recalculates compliance and ACP fines with and without projects.
    Pre-fills from Address Lookup session state where available.
    """
    if prefill is None:
        prefill = {}

    st.write(
        "Model your path to BERDO compliance. Enter planned emission reduction projects "
        "to see how they affect your compliance status and fine exposure across all periods through 2050."
    )

    #Building inputs
    st.subheader("Building inputs")

    #Inject prefill into session state when a new address lookup arrives
    prefill_addr_key = prefill.get("address", "")
    last_injected    = st.session_state.get("ep_last_injected_addr", "")
    if prefill_addr_key and prefill_addr_key != last_injected:
        if prefill.get("sqft"):
            st.session_state["ep_sqft"] = int(prefill["sqft"])
        if prefill.get("berdo_category"):
            st.session_state["ep_btype"] = prefill["berdo_category"]
        if prefill.get("ghg_intensity"):
            st.session_state["ep_ghg"] = float(prefill["ghg_intensity"])
        st.session_state["ep_last_injected_addr"] = prefill_addr_key

    col1, col2, col3 = st.columns(3)
    with col1:
        sqft = st.number_input(
            "Gross floor area (sq ft)",
            min_value=1_000, max_value=5_000_000,
            value=st.session_state.get("ep_sqft", 50_000),
            step=1_000, key="ep_sqft",
            help="Pre-filled from Address Lookup if available.",
        )
    with col2:
        type_options = ["Select a type"] + sorted(BERDO_STANDARDS.keys())
        prefill_cat  = st.session_state.get("ep_btype", "Select a type")
        default_idx  = type_options.index(prefill_cat) if prefill_cat in type_options else 0
        selected_type = st.selectbox(
            "Building type (BERDO category)",
            options=type_options, index=default_idx, key="ep_btype",
            help="Pre-filled from Address Lookup if available.",
        )
        berdo_category = selected_type if selected_type != "Select a type" else None
    with col3:
        ghg_intensity = st.number_input(
            "Current GHG intensity (kg CO₂e/sqft/yr)",
            min_value=0.0, max_value=100.0,
            value=float(st.session_state.get("ep_ghg", 0.0)),
            step=0.001, format="%.3f", key="ep_ghg",
            help="Pre-filled from Address Lookup if available. Found on your BERDO report.",
        )

    if prefill_addr_key:
        st.caption(f"Pre-filled from: {prefill_addr_key}")
    if prefill.get("limits") and berdo_category == prefill.get("berdo_category"):
        st.caption(
            "Using the blended mixed-use limit from Address Lookup. "
            "Change the building type above to use a single-category limit instead."
        )

    if not berdo_category or ghg_intensity <= 0 or sqft <= 0:
        st.info(
            "Enter your building type and current GHG intensity above to see the compliance projection. "
            "Look up your building in the Address Lookup tab to pre-fill automatically."
        )
        return

    #Emission Reduction Projects
    st.markdown("---")
    st.subheader("Emission Reduction Projects")
    st.caption(
        "Add planned projects to see how they affect your compliance trajectory. "
        "Uses the same emissions factors BERDO applies (EPA Portfolio Manager)."
    )

    #Initialise project list in session state
    if "ep_projects" not in st.session_state:
        st.session_state["ep_projects"] = []

    col_add = st.columns([6, 1])
    with col_add[1]:
        if st.button("Add New", key="ep_add_project"):
            st.session_state["ep_projects"].append({
                "name": "",
                "year": 2030,
                "fuel": "Natural gas",
                "unit": "therms",
                "amount": 0.0,
                "reduction_kg": 0.0,
            })

    #Project entry table
    fuel_unit_options = {
        "Natural gas":    ["therms", "ccf", "mcf", "kBtu", "MMBtu"],
        "Fuel oil #1":    ["gallons", "kBtu", "MMBtu"],
        "Fuel oil #2":    ["gallons", "kBtu", "MMBtu"],
        "Fuel oil #4":    ["gallons", "kBtu", "MMBtu"],
        "Fuel oil #5/#6": ["gallons", "kBtu", "MMBtu"],
        "Propane":        ["gallons", "kBtu", "MMBtu"],
        "Diesel":         ["gallons", "kBtu", "MMBtu"],
        "Kerosene":       ["gallons", "kBtu", "MMBtu"],
        "Electricity":    ["kWh", "MWh", "kBtu", "MMBtu"],
        "District steam": ["kBtu", "MMBtu", "therms"],
    }
    unit_to_kbtu = {
        "therms": 100.0, "ccf": 102.6, "mcf": 1026.0,
        "kBtu": 1.0, "MMBtu": 1000.0,
        "kWh": 3.412, "MWh": 3412.0,
        "gallons": 138.0,  #overridden per fuel below
    }
    gallon_kbtu = {
        "Fuel oil #1": 135.0,  
        "Fuel oil #2": 138.0, "Fuel oil #4": 146.0,
        "Fuel oil #5/#6": 150.0, "Propane": 92.0,
        "Diesel": 138.0, "Kerosene": 135.0,
    }

    def calc_reduction_kg(fuel, unit, amount, year=2025):
        if unit == "gallons":
            kbtu_factor = gallon_kbtu.get(fuel, 138.0)
        else:
            kbtu_factor = unit_to_kbtu.get(unit, 1.0)
        kbtu = amount * kbtu_factor
        if fuel == "Electricity":
            ef = effective_grid_ef(year) / 1000 / 3.412  #kg/kBtu
        else:
            ef = FUEL_EF_KG_PER_KBTU[fuel]  
        return round(kbtu * ef, 2)

    projects_to_remove = []
    projects = st.session_state["ep_projects"]

    if projects:
        header_cols = st.columns([3, 1.5, 2, 1.5, 2, 1.5, 1])
        header_cols[0].caption("Project name")
        header_cols[1].caption("Year")
        header_cols[2].caption("Fuel type")
        header_cols[3].caption("Amount")
        header_cols[4].caption("Unit")
        header_cols[5].caption("Emission reduction (kg CO₂e/yr)")
        header_cols[6].caption("")

        for idx, proj in enumerate(projects):
            row = st.columns([3, 1.5, 2, 1.5, 2, 1.5, 1])
            with row[0]:
                proj["name"] = st.text_input(
                    "Name", value=proj.get("name", ""),
                    key=f"ep_proj_name_{idx}", label_visibility="collapsed"
                )
            with row[1]:
                period_years = [2025, 2026, 2027, 2028, 2029,
                                2030, 2031, 2032, 2033, 2034,
                                2035, 2036, 2037, 2038, 2039,
                                2040, 2041, 2042, 2043, 2044,
                                2045, 2046, 2047, 2048, 2049, 2050]
                curr_yr = proj.get("year", 2030)
                yr_idx  = period_years.index(curr_yr) if curr_yr in period_years else 5
                proj["year"] = st.selectbox(
                    "Year", options=period_years, index=yr_idx,
                    key=f"ep_proj_year_{idx}", label_visibility="collapsed"
                )
            with row[2]:
                fuel_list = list(fuel_unit_options.keys())
                curr_fuel = proj.get("fuel", "Natural gas")
                f_idx = fuel_list.index(curr_fuel) if curr_fuel in fuel_list else 0
                proj["fuel"] = st.selectbox(
                    "Fuel", options=fuel_list, index=f_idx,
                    key=f"ep_proj_fuel_{idx}", label_visibility="collapsed"
                )
            with row[3]:
                proj["amount"] = st.number_input(
                    "Amount", min_value=0.0, value=float(proj.get("amount", 0.0)),
                    step=100.0, key=f"ep_proj_amt_{idx}", label_visibility="collapsed"
                )
            with row[4]:
                unit_list = fuel_unit_options.get(proj["fuel"], ["kBtu"])
                curr_unit = proj.get("unit", unit_list[0])
                u_idx = unit_list.index(curr_unit) if curr_unit in unit_list else 0
                proj["unit"] = st.selectbox(
                    "Unit", options=unit_list, index=u_idx,
                    key=f"ep_proj_unit_{idx}", label_visibility="collapsed"
                )
            with row[5]:
                proj["reduction_kg"] = calc_reduction_kg(proj["fuel"], proj["unit"], proj["amount"], proj["year"])
                st.metric(
                    "Reduction", f"{proj['reduction_kg']:,.1f}",
                    label_visibility="collapsed"
                )
            with row[6]:
                if st.button("Remove", key=f"ep_remove_{idx}"):
                    projects_to_remove.append(idx)

    for idx in sorted(projects_to_remove, reverse=True):
        st.session_state["ep_projects"].pop(idx)
        st.rerun()

    #Grid decarbonization, read from sidebar
     
    st.markdown("---")
    st.subheader("Emissions Compliance Projection")

    if berdo_category not in BERDO_STANDARDS:
        st.warning("Select a valid building type above to see the compliance projection.")
        return

    apply_grid = show_grid_decarb
    elec_share_val, elec_share_src = resolve_elec_share(prefill, elec_share, use_reported_share)

    limits = limits_for_category(berdo_category, prefill)

    if apply_grid:
        base_ef = effective_grid_ef(2025)
        ef_2050 = effective_grid_ef(2050)
        st.caption(
            f"Grid decarbonization is ON (sidebar). "
            f"Electricity share: {fmt_share(elec_share_val)} ({elec_share_src}). "
            f"Base year grid EF (2025): {base_ef:.0f} kg/MWh → {ef_2050:.0f} kg/MWh at 2050 "
            f"({round((1 - ef_2050 / base_ef) * 100)}% cleaner). "
            "Toggle in the sidebar to turn off."
        )
    else:
        st.caption(
            "Grid decarbonization is OFF. "
            "Enable it in the sidebar to model how ISO-NE grid cleaning reduces "
            "electricity-attributed emissions over time."
        )
        
    limits = limits_for_category(berdo_category, prefill)
    ghg_emissions_raw = prefill.get("ghg_emissions_kg")
    if ghg_emissions_raw and ghg_emissions_raw > 0:
        total_emissions_kg = float(ghg_emissions_raw)
        baseline_intensity = total_emissions_kg / sqft
        st.caption(
            f"Baseline: **{total_emissions_kg:,.0f} kg CO₂e/yr** (from reported BERDO data). "
            f"Derived intensity: {baseline_intensity:.3f} kg CO₂e/sqft/yr, "
            f"used for every scenario below, including grid decarbonization."
        )
    else:
        baseline_intensity = ghg_intensity
        total_emissions_kg = baseline_intensity * sqft

    #Grid decarbonization, project intensities per period
    if apply_grid:
        projected_intensities = project_ghg_intensities(
            ghg_intensity=baseline_intensity,
            elec_share=elec_share_val,
            base_year=2025,
        )
        grid_emissions_kg = [pi * sqft for pi in projected_intensities]
    else:
        grid_emissions_kg = [total_emissions_kg] * len(COMPLIANCE_PERIODS)

    #Period mapping
    period_start_years = [2025, 2030, 2035, 2040, 2045, 2050]

    def period_for_year(y):
        for i in range(len(period_start_years) - 1, -1, -1):
            if y >= period_start_years[i]:
                return i
        return 0

    #Cumulative project reductions by period
    period_reductions_kg = [0.0] * len(COMPLIANCE_PERIODS)
    for proj in st.session_state.get("ep_projects", []):
        if proj.get("reduction_kg", 0) > 0:
            start_period = period_for_year(proj["year"])
            for p in range(start_period, len(COMPLIANCE_PERIODS)):
                period_reductions_kg[p] += proj["reduction_kg"]

    has_projects = any(r > 0 for r in period_reductions_kg)
    has_grid     = apply_grid

    #Build two stacked tables
    emissions_rows = []
    fines_rows     = []

    for i, period in enumerate(COMPLIANCE_PERIODS):
        limit_psf  = limits[i]
        limit_kg   = limit_psf * sqft

        baseline_kg  = total_emissions_kg
        grid_kg      = grid_emissions_kg[i]
        proj_kg      = max(baseline_kg - period_reductions_kg[i], 0)
        combined_kg  = max(grid_kg    - period_reductions_kg[i], 0)

        gap_baseline = baseline_kg  - limit_kg
        gap_grid     = grid_kg      - limit_kg
        gap_proj     = proj_kg      - limit_kg
        gap_combined = combined_kg  - limit_kg

        fine_baseline = round(max(gap_baseline, 0) / 1000 * ACP_RATE, 0)
        fine_grid     = round(max(gap_grid,     0) / 1000 * ACP_RATE, 0)
        fine_proj     = round(max(gap_proj,     0) / 1000 * ACP_RATE, 0)
        fine_combined = round(max(gap_combined, 0) / 1000 * ACP_RATE, 0)

        def _ou(gap):
            if gap < 0:   return f"{abs(gap)/1000:,.0f} MT Under"
            elif gap > 0: return f"{gap/1000:,.0f} MT Over"
            return "At limit"

        def _fmt_kg(v): return f"{v:,.0f}"
        def _fmt_fine(v): return f"${v:,.0f}" if v > 0 else "$0"

        #Emissions table row
        erow = {
            "Period":         period,
            "BERDO limit":    _fmt_kg(limit_kg) if limit_kg > 0 else "0 (net zero)",
            "Baseline":       _fmt_kg(baseline_kg),
            "Status":         _ou(gap_baseline),
        }
        if has_projects:
            erow["Reductions"]       = _fmt_kg(period_reductions_kg[i]) if period_reductions_kg[i] > 0 else "0"
            erow["After projects"]   = _fmt_kg(proj_kg)
            erow["Status (projects)"] = _ou(gap_proj)
        if has_grid:
            erow["Grid decarb"]      = _fmt_kg(grid_kg)
            erow["Status (grid)"]    = _ou(gap_grid)
        if has_projects and has_grid:
            erow["Grid + projects"]         = _fmt_kg(combined_kg)
            erow["Status (grid + projects)"] = _ou(gap_combined)
        emissions_rows.append(erow)

        #Fines table row
        frow = {
            "Period":             period,
            "ACP (baseline)":     _fmt_fine(fine_baseline),
        }
        if has_projects:
            frow["ACP (with projects)"]  = _fmt_fine(fine_proj)
        if has_grid:
            frow["ACP (grid decarb)"]    = _fmt_fine(fine_grid)
        if has_projects and has_grid:
            frow["ACP (grid + projects)"] = _fmt_fine(fine_combined)
        fines_rows.append(frow)

    #Table 1: Emissions
    st.markdown("#### Projected emissions vs. BERDO limit (kg CO₂e/yr)")
    st.dataframe(pd.DataFrame(emissions_rows), use_container_width=True, hide_index=True)

    #Table 2: ACP fines
    st.markdown("#### Estimated ACP fine: annual, per period")
    st.caption("Alternative Compliance Payment at $234/metric ton CO₂e over limit.")
    st.dataframe(pd.DataFrame(fines_rows), use_container_width=True, hide_index=True)

    st.caption(
        "ACP = $234/metric ton CO₂e over limit. "
        "Not an official City of Boston BERDO compliance determination."
    )

    #Summary metrics
    def _cumulative_fine(emissions_by_period):
        #"2050+" has no end date, so it can't be annualized ×5 like the
        #five-year periods. Sum only the finite periods.
        return sum(
            max(emissions_by_period[i] - limits[i] * sqft, 0) / 1000 * ACP_RATE * 5
            for i in range(len(COMPLIANCE_PERIODS))
            if COMPLIANCE_PERIODS[i] != "2050+"
        )

    baseline_fines_cumul = _cumulative_fine([total_emissions_kg] * len(COMPLIANCE_PERIODS))
    proj_fines_cumul     = _cumulative_fine([max(total_emissions_kg - period_reductions_kg[i], 0) for i in range(len(COMPLIANCE_PERIODS))])
    grid_fines_cumul     = _cumulative_fine(grid_emissions_kg)
    combined_fines_cumul = _cumulative_fine([max(grid_emissions_kg[i] - period_reductions_kg[i], 0) for i in range(len(COMPLIANCE_PERIODS))])

    st.markdown("---")
    num_cols = 1 + (1 if has_projects else 0) + (1 if has_grid else 0) + (1 if has_projects and has_grid else 0)
    s_cols = st.columns(max(num_cols, 2))

    current_annual_fine = max(total_emissions_kg - limits[0] * sqft, 0) / 1000 * ACP_RATE
    s_cols[0].metric(
        "Annual ACP: current period (2025–29)",
        f"${current_annual_fine:,.0f}",
        delta="at current emissions, this period's cap",
    )
    s_cols[0].metric(
        "Cumulative ACP 2025–2050: no action",
        f"${baseline_fines_cumul:,.0f}",
        delta="worst case: emissions flat, no retrofit",
    )
    col_idx = 1
    if has_projects:
        savings = baseline_fines_cumul - proj_fines_cumul
        s_cols[col_idx].metric(
            "Cumulative ACP: with projects",
            f"${proj_fines_cumul:,.0f}",
            delta=f"-${savings:,.0f} vs no action" if savings > 0 else "No change",
        )
        col_idx += 1
    if has_grid:
        savings_g = baseline_fines_cumul - grid_fines_cumul
        s_cols[col_idx].metric(
            "Cumulative ACP: grid decarb only",
            f"${grid_fines_cumul:,.0f}",
            delta=f"-${savings_g:,.0f} vs no action" if savings_g > 0 else "No change",
        )
        col_idx += 1
    if has_projects and has_grid:
        savings_c = baseline_fines_cumul - combined_fines_cumul
        s_cols[col_idx].metric(
            "Cumulative ACP: grid + projects",
            f"${combined_fines_cumul:,.0f}",
            delta=f"-${savings_c:,.0f} vs no action" if savings_c > 0 else "No change",
        )
        
        if has_projects:
            total_reduction_mt = period_reductions_kg[0] / 1000
            gap_mt = max(total_emissions_kg - limits[0] * sqft, 0) / 1000
            if gap_mt > 0:
                pct = total_reduction_mt / gap_mt * 100
                st.caption(
                    f"Your projects reduce ~{total_reduction_mt:,.0f} MT/yr, about {pct:.1f}% of the "
                    f"{gap_mt:,.0f} MT the building is over its 2025–29 cap. "
                    + ("Nowhere near enough to affect compliance." if pct < 5 else
                       "Still short of compliance." if pct < 100 else
                       "Enough to reach compliance this period.")
                )

    compliant_periods_baseline  = sum(1 for i in range(len(COMPLIANCE_PERIODS)) if total_emissions_kg <= limits[i] * sqft)
    compliant_periods_proj      = sum(1 for i in range(len(COMPLIANCE_PERIODS)) if max(total_emissions_kg - period_reductions_kg[i], 0) <= limits[i] * sqft) if has_projects else None
    compliant_periods_grid      = sum(1 for i in range(len(COMPLIANCE_PERIODS)) if grid_emissions_kg[i] <= limits[i] * sqft) if has_grid else None
    compliant_periods_combined  = sum(1 for i in range(len(COMPLIANCE_PERIODS)) if max(grid_emissions_kg[i] - period_reductions_kg[i], 0) <= limits[i] * sqft) if (has_projects and has_grid) else None

    _all_compliant = [v for v in [compliant_periods_baseline, compliant_periods_proj, compliant_periods_grid, compliant_periods_combined] if v is not None]
    st.caption(
        f"Compliant periods: baseline {compliant_periods_baseline}"
        + (f" | with projects {compliant_periods_proj}" if compliant_periods_proj is not None else "")
        + (f" | grid decarb only {compliant_periods_grid}" if compliant_periods_grid is not None else "")
        + (f" | grid + projects {compliant_periods_combined}" if compliant_periods_combined is not None else "")
        + f" (out of {len(COMPLIANCE_PERIODS)} periods)."
    )

    #Bar chart
    fig = go.Figure()

    limit_vals    = [l * sqft / 1000 for l in limits]
    baseline_mt   = [total_emissions_kg / 1000] * len(COMPLIANCE_PERIODS)
    proj_mt       = [max(total_emissions_kg - period_reductions_kg[i], 0) / 1000 for i in range(len(COMPLIANCE_PERIODS))]
    grid_mt       = [g / 1000 for g in grid_emissions_kg]
    combined_mt   = [max(grid_emissions_kg[i] - period_reductions_kg[i], 0) / 1000 for i in range(len(COMPLIANCE_PERIODS))]

    fig.add_trace(go.Bar(
        x=COMPLIANCE_PERIODS, y=limit_vals,
        name="BERDO limit",
        marker_color="#3266ad",
        text=[f"{v:,.0f} MT" for v in limit_vals],
        textposition="outside", textfont=dict(size=10),
    ))
    fig.add_trace(go.Scatter(
        x=COMPLIANCE_PERIODS, y=baseline_mt,
        name="Worst case (no action)",
        mode="lines",
        line=dict(color="#E24B4A", width=2, dash="dash"),
    ))
    if has_projects:
        fig.add_trace(go.Scatter(
            x=COMPLIANCE_PERIODS, y=proj_mt,
            name="With projects",
            mode="lines+markers",
            line=dict(color="#1D9E75", width=2),
            marker=dict(size=7),
        ))
    if has_grid:
        fig.add_trace(go.Scatter(
            x=COMPLIANCE_PERIODS, y=grid_mt,
            name="Grid decarb only",
            mode="lines+markers",
            line=dict(color="#9B59B6", width=1.5, dash="dot"),
            marker=dict(size=6, symbol="diamond"),
        ))
    if has_projects and has_grid:
        fig.add_trace(go.Scatter(
            x=COMPLIANCE_PERIODS, y=combined_mt,
            name="Grid + projects (combined)",
            mode="lines+markers",
            line=dict(color="#E67E22", width=2.5),
            marker=dict(size=8, symbol="star"),
        ))

    all_vals = baseline_mt + limit_vals + (proj_mt if has_projects else []) + (grid_mt if has_grid else []) + (combined_mt if has_projects and has_grid else [])
    y_max = max(all_vals) * 1.25

    fig.update_layout(
        xaxis_title="Compliance period",
        yaxis=dict(title="Metric tons CO₂e/yr", range=[0, y_max]),
        height=400,
        margin=dict(t=40, b=40, l=60, r=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        bargap=0.35,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.12)")
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("About this projection"):
        st.markdown(r"""
**How emissions are projected**

The baseline uses your building's current reported GHG intensity (kg CO₂e/sqft/yr) 
multiplied by floor area, held flat across all periods (a worst-case assumption, not a forecast). 
Grid decarbonization would reduce electricity-attributed emissions over time independently of 
any retrofit.

**How project reductions work**

Each project's annual emission reduction (calculated from fuel type, unit, and quantity using 
EPA Portfolio Manager emissions factors) is applied cumulatively from the BERDO compliance 
period containing its implementation year onwards. A project implemented in 2033 applies to 
the 2030–34 period and all subsequent periods.

**ACP fines**

Alternative Compliance Payments are assessed at \$234 per metric ton of CO₂e above the 
building's emissions limit. The table shows annual fines; the summary metrics multiply by 
5 years per period for cumulative exposure.

Sources: BERDO ordinance Table 1 and ACP rate; ENERGY STAR Portfolio Manager
BERDO Emissions Factors List (September 18, 2026) for fuel factors; BERDO Policies &
Procedures v5, Appendix B, for projected grid factors.
Not an official City of Boston BERDO compliance determination.
""")

#App layout

all_years = load_all_years()
years_sorted = sorted(y for y in all_years if y != 0)
multi_year_mode = len(years_sorted) >= 2

#Sidebar: year selector -
if multi_year_mode:
    st.sidebar.header("Data year")
    selected_year = st.sidebar.radio(
        "Select reporting year to screen:",
        options=years_sorted,
        index=len(years_sorted) - 1,
        format_func=str,
        horizontal=False,
    )
    df_full = all_years[selected_year]
    show_yoy = st.sidebar.checkbox("Show year-over-year comparison", value=True, key="sidebar_show_yoy")
else:
    selected_year = years_sorted[0] if years_sorted else 0
    df_full = all_years[selected_year]
    show_yoy = False

#Sidebar: grid decarbonization scenario
st.sidebar.header("Grid decarbonization scenario")
show_grid_decarb = st.sidebar.checkbox(
    "Show grid decarbonization scenario",
    value=False,
    key="sidebar_grid_decarb",
    help=(
        "Projects future GHG intensity assuming the ISO-NE grid cleans up "
        "per the City of Boston's official projected emissions factors "
        "(Appendix B, BERDO Policies & Procedures v5, September 2026). "
        "Fossil fuel use is held constant."
    ),
)
use_reported_share = True   #also applies to the REC comparison when the scenario is off
if show_grid_decarb:
    use_reported_share = st.sidebar.checkbox(
        "Use each building's reported electricity share",
        value=True,
        key="sidebar_use_reported_share",
        help=(
            "Uses the City-reported electricity emissions ÷ total emissions "
            "(available from the 2024 dataset onward). Buildings without a "
            "breakdown use the slider below. Uncheck to apply the slider to every building."
        ),
    )
    elec_share_pct = st.sidebar.slider(
        "Electricity share of GHG emissions (%)",
        min_value=0,
        max_value=100,
        value=50,
        step=5,
        key="sidebar_elec_share",
        help=(
            "Used when a building has no reported electricity breakdown, or for "
            "every building if the option above is unchecked. For reference, the "
            "median 2024–2025 building gets about 37% of its emissions from electricity."
        ),
    )
    elec_share = elec_share_pct / 100.0
    base_ef = effective_grid_ef(selected_year)
    ef_2050 = effective_grid_ef(2050)
    st.sidebar.caption(
        f"Base year grid EF ({selected_year}): **{base_ef:.0f} kg/MWh** "
        f"(Appendix B × RPS Class I). Projected EF at 2050: **{ef_2050:.0f} kg/MWh** "
        f"({round((1 - ef_2050 / base_ef) * 100)}% cleaner)."
    )
else:
    elec_share = None

#Sources & verification register
SOURCES_REGISTER = [
    ("Emissions standards (limits by use and period)", "Verified", "BERDO ordinance, Table 1"),
    ("ACP rate: USD 234 per metric ton", "Verified", "BERDO ordinance, section (m)(d); reviewed every 5 years"),
    ("Projected grid emissions factors, 2022 to 2050", "Corrected", "Policies & Procedures v5 (Sep 2026) and Emissions Factors List (Sep 18, 2026), Appendix B"),
    ("Electricity formula: use × (1 − RPS) × factor", "Verified", "BERDO Policies & Procedures v5, section 5.B"),
    ("RPS Class I schedule", "Verified", "225 CMR 14.07(1); Emissions Factors List, Appendix C"),
    ("Fuel and default district steam factors", "Verified", "BERDO Emissions Factors List (Sep 18, 2026)"),
    ("Property type to building use mapping", "Verified", "BERDO Policies & Procedures v5, Appendix A"),
    ("Blended standard formula and 10% primary-use rule", "Corrected", "BERDO ordinance (i); Policies & Procedures v5, section 6"),
    ("Daily fines: reporting and emissions", "Verified", "BERDO ordinance, section (r)"),
    ("Flexibility measure, REC Connector, and 2026 reporting deadlines", "Verified", "boston.gov BERDO and Review Board pages"),
    ("179D and 45L termination; 179D 2026 amounts", "Verified", "P.L. 119-21; IRS Form 7205 instructions"),
    ("48C: fully allocated, no new rounds", "Verified", "DOE 48C program page; P.L. 119-21 sec. 70515"),
    ("Green Communities grant caps", "Corrected", "Mass. DOER announcements"),
    ("MassDEP Gap Energy Grant (was mislabeled MassDOER)", "Corrected", "mass.gov Gap IV request for responses"),
    ("Parking left out of blended standard by default", "Unverified", "Not confirmed in City documents"),
    ("Mass Save rebate $/sqft estimates", "Unverified", "Tool estimates; confirm at masssave.com"),
    ("Retrofit cost ranges and Boston labor multiplier", "Unverified", "Order-of-magnitude benchmarks"),
    ("Default REC price (USD 40)", "Unverified", "Placeholder; user can change it"),
    ("Fuel unit conversions (therms, gallons)", "Unverified", "Standard Portfolio Manager conversions assumed"),
    ("Named district steam factors (Vicinity, MATEP)", "Verified", "BERDO Emissions Factors List (Sep 18, 2026); not used in calculations"),
]
SOURCES_VERIFIED_ON = "September 23, 2026"

with st.sidebar.expander("Sources & verification"):
    st.caption(
        f"Each constant this tool uses, checked against official sources on {SOURCES_VERIFIED_ON}. "
        "Corrected = the value was wrong and has been fixed. Unverified = no official source "
        "was found, so treat the figure as an estimate."
    )
    st.dataframe(
        pd.DataFrame(SOURCES_REGISTER, columns=["Item", "Status", "Source"]),
        hide_index=True, use_container_width=True,
    )

#Page header
st.title("BERDO Compliance Planner")
st.write(
    "Enter a Boston building address to see its BERDO compliance status, fine exposure, "
    "and a matched incentive plan for funding decarbonization."
)

if multi_year_mode:
    year_range_str = f"{years_sorted[0]}–{years_sorted[-1]}"
    st.info(
        f"Showing data for **{selected_year}**. "
        f"Multi-year data loaded: {year_range_str}. "
        "Use the sidebar to switch years or toggle the trend view."
    )
else:
    st.info(
        "This is a screening tool for analysis purposes. "
        "It is not an official City of Boston BERDO compliance determination."
    )

tab_address, tab_portfolio, tab_retrofit_optimizer, tab_planner = st.tabs([
    "Address Lookup", "Owner Portfolio", "Retrofit & Incentives", "Emissions Planner"
])

#Tab 1: single address lookup (unchanged behaviour)

with tab_address:
    address_input = st.text_input(
        "Enter building address",
        placeholder="Example: 20 Gillette Park"
    )

    if address_input:
        result = lookup_building_priority(df_full, address_input)

        if result is None:
            st.warning("No matching address found in the dataset.")
        else:
            result["Site EUI"] = result["Site EUI"].round(1)
            result["GHG Intensity (kgCO2e/sqft)"] = (
                pd.to_numeric(result["GHG Intensity (kgCO2e/sqft)"], errors="coerce")
                .round(3)
            )

            st.subheader("Building Result")

            display_cols = [
                "Building Address", "Property Owner Name", "Property Type",
                "Site EUI", "GHG Intensity (kgCO2e/sqft)",
                "Data Status", "BERDO Status", "Est. ACP (2025–29)", "Notes",
            ]
            st.dataframe(result[display_cols], use_container_width=True, hide_index=True)

            top = result.iloc[0]
            bldg_share, bldg_share_note = building_elec_share(
                top.get("GHG Emissions (kgCO2e)"), top.get("Electricity Emissions (kgCO2e)"))
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Data status", top["Data Status"])
            with col2:
                st.metric("BERDO status", top["BERDO Status"])
            with col3:
                acp = top["Est. ACP (2025–29)"]
                st.metric("Est. ACP (2025–29)", f"${acp:,.0f}/yr" if acp else "$0")

            st.write("**Notes:**", top["Notes"])


#Fuel breakdown
            fuel_breakdown = get_fuel_breakdown(top)
            primary_fuel   = top.get("Primary Fuel", "Mixed / unknown")
            if fuel_breakdown:
                n_cols = min(len(fuel_breakdown), 5)  #cap at 5 cols
                st.markdown(f"**Energy usage by fuel ({selected_year} reported)**")
                fuel_cols = st.columns(n_cols)
                for i, (label, kbtu, pct) in enumerate(fuel_breakdown[:n_cols]):
                    fuel_cols[i].metric(
                        label,
                        f"{kbtu/1_000:,.0f} MMBtu",
                        delta=f"{pct:.0f}% of total",
                    )
                dominant_note = "dominant fuel >60% of total" if primary_fuel != "Mixed / unknown" else "no single fuel >60% of total"
                st.caption(
                    f"Primary fuel inferred: {primary_fuel} ({dominant_note}). "
                    "Used to pre-fill the Retrofit & Incentives tab."
                )
            if bldg_share is not None:
                st.caption(
                    f"Electricity accounts for **{fmt_share(bldg_share)}** of this building's "
                    "reported emissions (City-reported electricity emissions ÷ total)."
                )
                if bldg_share_note:
                    st.caption(bldg_share_note)
                
            with st.expander("What do these fields mean?"):
                st.markdown(r"""
**Compliance Status**
- **Submitted**: The building owner reported energy and emissions data to the City of Boston for the previous calendar year.
- **Not submitted**: No data was reported. Buildings required to report under BERDO face fines of \$150–\$300/day for missing the annual May 15 reporting deadline (\$300/day for buildings over 35,000 sq ft; \$150/day for smaller covered buildings). For 2026, the City lists October 15 as the deadline for annual reporting with approved extensions. Separate daily fines of \$1,000/day (buildings over 35,000 sq ft) or \$300/day (smaller covered buildings) apply for failing to meet emissions standards.

**Site EUI (Energy Use Intensity)**
- Measures how much energy a building uses per square foot per year (kBtu/sq ft/yr). A higher EUI means the building uses more energy relative to its size. Missing EUI typically means the building did not submit complete energy data.

**GHG Intensity (kg CO₂e/sq ft/yr)**
- The building's greenhouse gas emissions per square foot per year, calculated from reported fuel and electricity use. This is the value compared against BERDO emissions limits to determine compliance.

**Data Status**
- **Reported**: energy and emissions data submitted and complete enough to evaluate.
- **Incomplete data**: submitted, but property type, floor area, or GHG data is missing or unmappable, so compliance can't be calculated.
- **Not submitted**: no data reported. Accruing daily reporting fines.

**BERDO Status**
- **Over 2025–29 limit**: currently exceeds its sector limit and accruing ACP.
- **Fails 2030–34**: compliant now, but over the next limit at current emissions.
- **Compliant through 2034** / **2039+**: how far the current trajectory holds.
- **Not yet covered**: smaller covered building, not subject to an emissions limit until 2030.
- **Unknown (data incomplete)**: compliance can't be determined from what was reported.

**Est. ACP (2025–29)**
- Estimated annual Alternative Compliance Payment for the current period, at \$234 per metric ton CO₂e over the limit. Shows \$0 for compliant buildings and those not yet covered.""")    

            st.markdown("---")

            #Year-over-year trend (multi-year mode only)
            prior_ghg, prior_label = None, None
            if show_yoy and multi_year_mode:
                prior_ghg, prior_label = render_yoy_trend(address_input, all_years)
                st.markdown("---")

            #Grid decarbonization projection 
            projected_intensities = None
            if show_grid_decarb and elec_share is not None:
                year_txt = f"{selected_year} data" if selected_year else "reported data"
                if use_reported_share and bldg_share is not None:
                    share_for_grid = bldg_share
                    st.caption(
                        f"Grid scenario uses this building's reported electricity share: "
                        f"**{fmt_share(bldg_share)}** ({year_txt})."
                    )
                else:
                    share_for_grid = elec_share
                    why = ("the reported-share option is off in the sidebar"
                           if not use_reported_share
                           else "this year's data has no electricity breakdown for this building")
                    st.caption(
                        f"Grid scenario uses the sidebar estimate of **{fmt_share(elec_share)}** "
                        f"because {why}."
                    )
                ghg_val = top.get("GHG Intensity (kgCO2e/sqft)")
                if pd.notna(ghg_val) and ghg_val > 0:
                    projected_intensities = project_ghg_intensities(
                        ghg_intensity=float(ghg_val),
                        elec_share=share_for_grid,
                        base_year=selected_year,
                    )

            use_mix_limits = render_use_mix_editor(top)

            render_compliance_section(
                top,
                prior_year_ghg_intensity=prior_ghg,
                prior_year_label=prior_label,
                projected_intensities=projected_intensities,
                base_year=selected_year,
                limits=use_mix_limits,
            )

            #Compliance pathways
            _bl_ctx = building_limits(top.get("Property Type"), top.get("All Property Types"))
            _blend_fixes = False
            _ghg_ctx  = pd.to_numeric(top.get("GHG Intensity (kgCO2e/sqft)"), errors="coerce")
            _sqft_ctx = pd.to_numeric(top.get("Gross Floor Area"), errors="coerce")
            if _bl_ctx.get("blended") and pd.notna(_ghg_ctx) and pd.notna(_sqft_ctx):
                _bg = calculate_compliance_gap(float(_ghg_ctx), float(_sqft_ctx), None,
                                               limits=_bl_ctx["blended"])
                _blend_fixes = (top["BERDO Status"] == "Over 2025–29 limit"
                                and bool(_bg) and _bg[0]["compliant"])
            _owner = str(top.get("Property Owner Name") or "").strip().lower()
            _n_owned = 0
            if _owner and _owner != "nan":
                _n_owned = int((df_full["Property Owner Name"].astype(str)
                                .str.strip().str.lower() == _owner).sum())
            _pathways_ctx = {
                "over_now":             top["BERDO Status"] == "Over 2025–29 limit",
                "fails_later":          top["BERDO Status"] == "Fails 2030–34",
                "blend_available":      _bl_ctx["basis"] != "largest_use",
                "blend_fixes":          _blend_fixes,
                "owner_building_count": _n_owned,
                "elec_share":           bldg_share,
            }
            render_compliance_pathways(_pathways_ctx)

            #One-page PDF summary for a board, lender, or consultant
            _pdf_limits = use_mix_limits or _bl_ctx["limits"]
            _periods = []
            if _pdf_limits and pd.notna(_ghg_ctx) and pd.notna(_sqft_ctx) and _sqft_ctx > 0:
                for _i, _g in enumerate(calculate_compliance_gap(
                        float(_ghg_ctx), float(_sqft_ctx), None, limits=_pdf_limits)):
                    _row = {"period": _g["period"], "limit": _g["limit"], "gap": _g["gap"],
                            "status": "Meets limit" if _g["compliant"] else "Over limit",
                            "acp": _g["annual_fine_usd"]}
                    if projected_intensities is not None:
                        _pg = calculate_compliance_gap(projected_intensities[_i], float(_sqft_ctx),
                                                       None, limits=_pdf_limits)[_i]
                        _row["grid_status"] = "Meets limit" if _pg["compliant"] else "Over limit"
                    _periods.append(_row)

            def _num(v, fmt):
                v = pd.to_numeric(v, errors="coerce")
                return fmt.format(v) if pd.notna(v) else "Not reported"

            _facts = [
                ("BERDO category", _bl_ctx["label"] or "Not mappable", "Calculated"),
                ("Reported property type", top.get("Property Type") or "Not reported", "Reported"),
                ("Gross floor area", _num(top.get("Gross Floor Area"), "{:,.0f} sq ft"), "Reported"),
                ("Total GHG emissions", _num(pd.to_numeric(top.get("GHG Emissions (kgCO2e)"),
                                                           errors="coerce") / 1000,
                                             "{:,.0f} metric tons CO2e"), "Reported"),
                ("GHG intensity", _num(_ghg_ctx, "{:.2f} kg CO2e/sf/yr"), "Calculated"),
                ("Electricity share of emissions",
                 fmt_share(bldg_share), "Calculated"),
                ("Site EUI", _num(top.get("Site EUI"), "{:.1f} kBtu/sf/yr"), "Reported"),
                ("Annual reporting", reporting_status_label(top.get("Compliance Status")), "Reported"),
                ("Screening result", top.get("BERDO Status"), "Calculated"),
                ("Est. annual ACP (2025–29)",
                 f"USD {top['Est. ACP (2025–29)']:,.0f}" if top["Est. ACP (2025–29)"] else "USD 0",
                 "Estimated"),
            ]
            _limit_basis = (
                "Limits shown use the Blended Emissions Standard, an option the owner may adopt "
                "(estimated by this tool from floor area by use)."
                if use_mix_limits else
                f"Limits shown are the default for the building's largest use ({_bl_ctx['label']})."
            )
            _blend_note = ""
            if not use_mix_limits and _bl_ctx.get("blended"):
                _blend_note = (f"If the owner adopts a Blended Emissions Standard, the 2025–29 "
                               f"limit would be about {_bl_ctx['blended'][0]:.2f} (estimated).")
            _grid_note = ""
            if projected_intensities is not None:
                _grid_note = ("Grid scenario: projection assuming the electric grid gets cleaner "
                              "per the City's projected emissions factors, with fossil fuel use "
                              "unchanged (Estimated).")
            _notes = [n.strip() for n in str(top.get("Notes") or "").split(";") if n.strip()]

            try:
                _pdf_bytes = build_building_summary_pdf({
                    "address":     top.get("Building Address", address_input),
                    "owner":       top.get("Property Owner Name"),
                    "data_year":   selected_year or None,
                    "facts":       _facts,
                    "periods":     _periods,
                    "limit_basis": _limit_basis,
                    "blend_note":  _blend_note,
                    "grid_note":   _grid_note,
                    "notes":       _notes,
                    "pathways":    get_compliance_pathways(_pathways_ctx),
                })
                _slug = re.sub(r"[^A-Za-z0-9]+", "_", str(top.get("Building Address", "building"))).strip("_")
                st.download_button(
                    "Download one-page summary (PDF)",
                    data=_pdf_bytes,
                    file_name=f"BERDO_summary_{_slug}_{selected_year or 'data'}.pdf",
                    mime="application/pdf",
                    help="Status, limits by period, screening notes, and compliance options "
                         "on one page, for a board, lender, or consultant. Reflects the "
                         "settings currently shown (blended standard, grid scenario).",
                )
            except ImportError:
                st.caption(
                    "PDF export needs the reportlab package. Add `reportlab` to requirements.txt."
                )

            #Store prefill data for Incentive Optimizer tab
            ghg_val = top.get("GHG Intensity (kgCO2e/sqft)")
            sqft_val = top.get("Gross Floor Area")
            raw_type = top.get("Property Type")
            berdo_cat = map_property_type(raw_type)

            opt_prefill = {
                "address":       top.get("Building Address", address_input),
                "sqft":          int(sqft_val) if pd.notna(sqft_val) and sqft_val > 0 else 50_000,
                "berdo_category": berdo_cat,
                "primary_fuel":  top.get("Primary Fuel", "Mixed / unknown"),
                "limits":        use_mix_limits,
                "elec_share":    bldg_share,
                "elec_share_year": selected_year or None,
            }

            #Calculate fine for 2025–29 period if possible
            if (
                pd.notna(ghg_val) and ghg_val > 0
                and pd.notna(sqft_val) and sqft_val > 0
                and (use_mix_limits is not None or berdo_cat in BERDO_STANDARDS)
            ):
                limit_2025 = (use_mix_limits or BERDO_STANDARDS[berdo_cat])[0]
                gap = float(ghg_val) - limit_2025
                if gap > 0:
                    excess_tons = gap * float(sqft_val) / 1000
                    opt_prefill["annual_fine_usd"] = round(excess_tons * ACP_RATE, 0)
                    opt_prefill["ghg_intensity"] = float(ghg_val)

            st.session_state["optimizer_prefill"] = opt_prefill
           
            #Also pre-fill the Emissions Planner tab
            ghg_emissions_raw = top.get("GHG Emissions (kgCO2e)")
            planner_prefill = {
                "address":          opt_prefill.get("address", address_input),
                "sqft":             opt_prefill.get("sqft", 50_000),
                "berdo_category":   berdo_cat,
                "limits":           use_mix_limits,
                "elec_share":       bldg_share,
                "elec_share_year":  selected_year or None,
                "ghg_intensity":    float(ghg_val) if pd.notna(ghg_val) and ghg_val > 0 else 0.0,
                "ghg_emissions_kg": float(ghg_emissions_raw) if pd.notna(ghg_emissions_raw) and ghg_emissions_raw > 0 else None,
            }
            st.session_state["planner_prefill"] = planner_prefill
            #Inject directly into widget state for planner
            if planner_prefill.get("sqft"):
                st.session_state["ep_sqft"] = int(planner_prefill["sqft"])
            if planner_prefill.get("berdo_category"):
                st.session_state["ep_btype"] = planner_prefill["berdo_category"]
            if planner_prefill.get("ghg_intensity", 0) > 0:
                st.session_state["ep_ghg"] = planner_prefill["ghg_intensity"]
            st.session_state["ep_last_injected_addr"] = planner_prefill["address"]

            st.info(
                "Building data saved: open the **Retrofit & Incentives** or **Emissions Planner** tabs "
                "to model funding programs and compliance trajectory for this building."
            )


#Tab 2: owner portfolio lookup

with tab_portfolio:
    st.write(
        "Enter a property owner name to group all their buildings into a BERDO "
        "Building Portfolio and see combined compliance exposure under the blended "
        "emissions standard."
    )
    owner_input = st.text_input(
        "Enter property owner name",
        placeholder="Example: City of Boston",
        key="owner_input",
    )

    if owner_input:
        portfolio_result = lookup_owner_portfolio(df_full, owner_input)

        if portfolio_result is None:
            st.warning("No buildings found for that owner name in the dataset.")
        else:
            st.subheader(f"Buildings found: {len(portfolio_result)}")

            display_cols = [
                "Building Address", "Property Owner Name", "Property Type",
                "Gross Floor Area", "Site EUI", "GHG Intensity (kgCO2e/sqft)",
                "Compliance Status", "Data Status", "BERDO Status",
            ]
            st.dataframe(portfolio_result[display_cols], use_container_width=True, hide_index=True)

            if len(portfolio_result) == 1:
                st.info(
                    "Only one building found for this owner. "
                    "A Building Portfolio requires multiple buildings. "
                    "Use the Address Lookup tab for single-building analysis."
                )
            else:
                st.markdown("---")
                render_portfolio_section(
                    portfolio_result,
                    selected_year=selected_year,
                    elec_share=elec_share if show_grid_decarb else None,
                    all_years=all_years,
                    show_yoy=show_yoy,
                    use_reported_share=use_reported_share,
                )
                

#Tab 3: Retrofit & Incentives (merged Retrofit Estimator + Incentive Optimizer)

with tab_retrofit_optimizer:
    opt_prefill = st.session_state.get("optimizer_prefill", {})
    render_retrofit_optimizer_tab(prefill=opt_prefill)


#Tab 4: Emissions Planner

with tab_planner:
    planner_prefill = st.session_state.get("planner_prefill", {})
    render_emissions_planner_tab(
        prefill=planner_prefill,
        show_grid_decarb=show_grid_decarb,
        elec_share=elec_share,
        use_reported_share=use_reported_share,
    )
