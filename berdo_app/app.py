import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pathlib import Path


#Page config

st.set_page_config(
    page_title="BERDO Compliance Planner",
    layout="wide"
)

#BERDO 2.0 emissions standards
#Source: BERDO 2.0 Phase 1 Regulations (Boston APCC, adopted October 2021)
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

ACP_RATE = 234  #USD per metric ton CO2e over the limit


#Projected ISO New England grid emissions factors by year
#Source: BERDO Emissions Factors List, Appendix B (updated May 5, 2026)
#Units: kg CO2e / MWh

PROJECTED_GRID_EF = {
    2022: 270, 2023: 263, 2024: 256, 2025: 249, 2026: 242,
    2027: 265, 2028: 265, 2029: 264, 2030: 259, 2031: 254,
    2032: 249, 2033: 243, 2034: 237, 2035: 231, 2036: 224,
    2037: 217, 2038: 211, 2039: 204, 2040: 198, 2041: 192,
    2042: 187, 2043: 182, 2044: 177, 2045: 173, 2046: 168,
    2047: 163, 2048: 159, 2049: 155, 2050: 150,
}

# MA RPS Class I minimum standard, per 225 CMR 14.07 / BERDO Appendix C.
# Verified against BERDO Emissions Factors List, last updated May 5, 2026.
# BERDO electricity formula: G = U × (1 − R) × E
# Schedule: +3 pp/yr 2025–2029, 40% in 2030, +1 pp/yr thereafter.
RPS_CLASS_I = {
    2022: 0.20, 2023: 0.22, 2024: 0.24, 2025: 0.27, 2026: 0.30,
    2027: 0.33, 2028: 0.36, 2029: 0.39, 2030: 0.40,
}
for _y in range(2031, 2051):
    RPS_CLASS_I[_y] = round(0.40 + 0.01 * (_y - 2030), 2)

_EF_MIN_YR, _EF_MAX_YR = min(PROJECTED_GRID_EF), max(PROJECTED_GRID_EF)

def rps_class_i(year: int) -> float:
    """RPS Class I fraction for a year, clamped to the published schedule."""
    return RPS_CLASS_I.get(min(max(year, _EF_MIN_YR), _EF_MAX_YR), 0.0)


def effective_grid_ef(year: int) -> float:
    """
    BERDO-effective grid EF in kg CO2e/MWh, after the RPS Class I offset.
    This — not the raw Appendix B value — is what BERDO bills electricity at.
    """
    clamped = min(max(year, _EF_MIN_YR), _EF_MAX_YR)
    return PROJECTED_GRID_EF[clamped] * (1.0 - rps_class_i(clamped))





#Representative year for each compliance period (midpoint, or period start for 2050)
PERIOD_REPRESENTATIVE_YEARS = [2027, 2032, 2037, 2042, 2047, 2050]


#Mapping from Energy Star Portfolio Manager property types → BERDO categories

PROPERTY_TYPE_MAP = {
    "office": "Office",
    "financial office": "Office",
    "courthouse": "Office",
    "government office": "Office",
    "multifamily housing": "Multifamily Housing",
    "residential": "Multifamily Housing",
    "senior living community": "Multifamily Housing",
    "affordable housing": "Multifamily Housing",
    "residence hall / dormitory": "Multifamily Housing",
    "residence hall/dormitory": "Multifamily Housing",
    "retail store": "Retail",
    "strip mall": "Retail",
    "enclosed mall": "Retail",
    "retail": "Retail",
    "supermarket/grocery store": "Food Sales & Service",
    "wholesale club/supercenter": "Retail",
    "hotel": "Lodging",
    "lodging/residential": "Lodging",
    "motel or inn": "Lodging",
    "hospital (general medical & surgical)": "Healthcare",
    "medical office": "Healthcare",
    "outpatient rehabilitation/physical therapy": "Healthcare",
    "urgent care/clinic/other outpatient": "Healthcare",
    "ambulatory surgical center": "Healthcare",
    "nursing home": "Healthcare",
    "health center/public health clinic": "Healthcare",
    "k-12 school": "Education",
    "pre-school/daycare": "Education",
    "adult education": "Education",
    "vocational school": "Education",
    "college/university": "College/University",
    "college / university": "College/University",
    "food service": "Food Sales & Service",
    "restaurant or bar": "Food Sales & Service",
    "fast food restaurant": "Food Sales & Service",
    "convenience store without gas station": "Food Sales & Service",
    "convenience store with gas station": "Food Sales & Service",
    "bar/nightclub": "Food Sales & Service",
    "worship facility": "Assembly",
    "museum": "Assembly",
    "performing arts": "Assembly",
    "sports arena": "Assembly",
    "fitness center/health club/gym": "Assembly",
    "recreation": "Assembly",
    "social/meeting hall": "Assembly",
    "entertainment/public assembly": "Assembly",
    "library": "Assembly",
    "movie theater": "Assembly",
    "convention center": "Assembly",
    "indoor arena": "Assembly",
    "personal services (health/beauty, dry cleaning, etc.)": "Services",
    "salon": "Services",
    "bank branch": "Services",
    "repair services": "Services",
    "laboratory": "Technology/Science",
    "data center": "Technology/Science",
    "research and development": "Technology/Science",
    "manufacturing/industrial plant": "Manufacturing/Industrial",
    "distribution center": "Manufacturing/Industrial",
    "non-refrigerated warehouse": "Storage",
    "refrigerated warehouse": "Storage",
    "self-storage facility": "Storage",
    "warehouse and storage": "Storage",
    "parking": "Services",
    "mixed use property": "Office",
}

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

def map_property_type(raw_type):
    if pd.isna(raw_type) or not isinstance(raw_type, str):
        return None
    key = raw_type.strip().lower()
    return PROPERTY_TYPE_MAP.get(key)
    
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

def calculate_compliance_gap(ghg_intensity, sqft, berdo_category):
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


#Compliance gap display

def render_compliance_section(
    row,
    prior_year_ghg_intensity=None,
    prior_year_label=None,
    projected_intensities=None,
    base_year=2025,
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
            "GHG intensity is missing or zero for this building — "
            "cannot calculate compliance gap. Check that GHG emissions "
            "and floor area are reported in the dataset."
        )
        return

    if pd.isna(sqft) or sqft <= 0:
        st.warning("Floor area is missing — cannot calculate fine exposure.")
        return

    if berdo_category is None:
        st.warning(
            f"Property type **{raw_type}** could not be mapped to a BERDO "
            "emissions category. Add it to the PROPERTY_TYPE_MAP to enable "
            "gap calculations."
        )
        return

    gaps = calculate_compliance_gap(ghg_intensity, sqft, berdo_category)

    #Projected gaps (for grid decarb scenario metric cards)
    if projected_intensities is not None:
        proj_gaps = [
            calculate_compliance_gap(pi, sqft, berdo_category)
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
        f"BERDO category: **{berdo_category}**"
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
        name="Annual ACP fine — conservative (USD)",
        mode="lines+markers",
        yaxis="y2",
        line=dict(color="#BA7517", width=1.5, dash="dot"),
        marker=dict(size=6),
        visible="legendonly",
    ))

    if projected_intensities is not None:
        proj_fines = [
            calculate_compliance_gap(pi, sqft, berdo_category)[i]["annual_fine_usd"]
            for i, pi in enumerate(projected_intensities)
        ]
        fig.add_trace(go.Scatter(
            x=COMPLIANCE_PERIODS,
            y=proj_fines,
            name="Annual ACP fine — grid scenario (USD)",
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
        "**Conservative line:** current GHG intensity held flat — no operational changes, "
        "no grid improvement. "
    )
    if projected_intensities is not None:
        caption += (
            f"**Grid decarbonization line:** electricity component scaled by ISO-NE projected "
            f"grid EFs (Appendix B × RPS Class I, base year {base_year} = {base_ef:.0f} kg/MWh); "
            "fossil fuel use held constant. "
        )
    caption += (
        "Source: BERDO 2.0 Phase 1 Regulations (Boston APCC, adopted October 2021); "
        "BERDO Emissions Factors List (City of Boston, May 2026). "
        "Not an official City of Boston compliance determination."
    )
    st.caption(caption)

    with st.expander("About this tool"):
        st.markdown("""
        
**What is BERDO?**

The Building Emissions Reduction and Disclosure Ordinance (BERDO) requires large buildings
in Boston to reduce greenhouse gas emissions on a mandatory schedule toward net-zero by 2050.
Buildings over 35,000 sq ft or with 35+ residential units must meet emissions limits starting
in 2025. Smaller covered buildings (20,000–35,000 sq ft or 15–34 residential units) begin
compliance in 2030.

**How are buildings evaluated?**

Each building gets two independent flags rather than a single blended score, because a
building that didn't report needs a different intervention than one that reported and
is over its limit — outreach versus retrofit capital.

**Data Status** reflects reporting completeness: whether data was submitted at all, and
whether property type, floor area, and GHG intensity are present and mappable to a BERDO
category. Buildings marked "not submitted" face daily reporting fines and are the most
urgent outreach targets.

**BERDO Status** compares the building's actual GHG intensity against its own sector limit —
not against a dataset average — so an energy-intensive hospital isn't penalized for using
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
BERDO Emissions Factors List). Use the sidebar slider to set the share of the building's
emissions that come from electricity. If unknown, 50% is a reasonable starting point for a
mixed-use or office building; electricity-heavy buildings (all-electric, data centers) should
use a higher value.

Source: BERDO 2.0 Phase 1 Regulations (Boston APCC, adopted October 2021);
BERDO Emissions Factors List (City of Boston, updated May 5, 2026).
Not an official City of Boston compliance determination.
""")

#Data loading. Supports single file (berdo.csv) or multi-year files
#(berdo_2022.csv, berdo_2023.csv, …) in the data/ folder.

COLUMN_RENAME_MAP = {
    "Largest Property Type": "property_type",
    "Reported Gross Floor Area (Sq Ft)": "gross_floor_area",
    "Site EUI (Energy Use Intensity kBtu/ft²)": "site_eui",
    "Estimated Total GHG Emissions (kgCO2e)": "ghg_emissions",
    "Estimated Total GHG Emissions e(kgCO2e)": "ghg_emissions",
    "Reporting Compliance Status": "compliance_status",
    "First Emissions Compliance Year (Projected)": "compliance_year",
    
    #Fuel usage columns (all in kBtu except Electricity which is kWh)
    
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
    berdo_cat = map_property_type(row["property_type"])
    ghg       = row["ghg_intensity_kgco2e_sqft"]
    sqft      = row["gross_floor_area"]
    notes     = []

    scoreable = (
        berdo_cat is not None
        and pd.notna(ghg)
        and pd.notna(sqft)
        and sqft > 0
    )

    #Flag 1 — data status
    if row["compliance_status"] == "not submitted":
        data_status = "Not submitted"
        notes.append("Did not report — accruing daily reporting fines")
    elif not scoreable:
        data_status = "Incomplete data"
        if berdo_cat is None:
            notes.append("Property type missing or not mappable to a BERDO category")
        if pd.isna(sqft) or sqft <= 0:
            notes.append("Floor area missing")
        if pd.isna(ghg):
            notes.append("GHG intensity missing")
    else:
        data_status = "Reported"

    #Flag 2 — BERDO compliance status
    subject_now = (
        pd.notna(row.get("compliance_year"))
        and int(row["compliance_year"]) <= 2025
    )

    acp_2025 = 0.0
    if not scoreable:
        berdo_status = "Unknown — data incomplete"
    elif not subject_now:
        berdo_status = "Not yet covered"
        notes.append("Not subject to a BERDO emissions limit until 2030")
    else:
        gaps = calculate_compliance_gap(ghg, sqft, berdo_cat)
        if not gaps[0]["compliant"]:
            berdo_status = "Over 2025–29 limit"
            acp_2025 = gaps[0]["annual_fine_usd"]
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
        notes.append("Over 100,000 sq ft — longer retrofit lead time")

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
            "Gross Floor Area":            row.get("gross_floor_area"),
            "Site EUI":                    row.get("site_eui"),
            "GHG Intensity (kgCO2e/sqft)": row.get("ghg_intensity_kgco2e_sqft"),
            "GHG Emissions (kgCO2e)":      row.get("ghg_emissions"),
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
            "Gross Floor Area":            row.get("gross_floor_area"),
            "Site EUI":                    row.get("site_eui"),
            "GHG Intensity (kgCO2e/sqft)": row.get("ghg_intensity_kgco2e_sqft"),
            "GHG Emissions (kgCO2e)":      row.get("ghg_emissions"),
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
        berdo_cat = map_property_type(row.get("Property Type"))
        if pd.isna(sqft) or sqft <= 0 or berdo_cat is None:
            continue
        limits = BERDO_STANDARDS[berdo_cat]
        total_sqft += sqft
        for i, lim in enumerate(limits):
            weighted_limits[i] += lim * sqft

    if total_sqft == 0:
        return None

    return [round(wl / total_sqft, 4) for wl in weighted_limits]



#Portfolio compliance section

def render_portfolio_section(buildings_df, selected_year, elec_share, all_years, show_yoy):
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
                reason = "Reported under state status — verify BERDO treatment before excluding"
            elif missing_ghg and missing_sqft:
                if status == "not submitted":
                    reason = "Did not report — no GHG data or floor area submitted"
                elif status == "pending revisions":
                    reason = "Pending revisions — GHG data and floor area incomplete"
                else:
                    reason = "Missing GHG emissions and floor area"
            elif missing_ghg:
                if status == "not submitted":
                    reason = "Did not report — no GHG data submitted"
                elif status == "pending revisions":
                    reason = "Pending revisions — GHG data incomplete"
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
            "Could not calculate a blended standard — check that property types "
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
        st.success(
            f"This portfolio is **compliant** in the current 2025–2029 period under the "
            f"blended emissions standard of {current_limit:.3f} kg CO₂e/sf/yr. "
            f"If emissions remain unchanged, it stays compliant through "
            f"{'all periods' if not non_compliant_periods else f'the {COMPLIANCE_PERIODS[non_compliant_periods[0][0]]} period'}."
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
            "BERDO Building Portfolios cannot include vacant buildings — "
            "verify before submitting a portfolio application."
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
        projected = project_ghg_intensities(
            portfolio_intensity, elec_share,
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
        name="Annual ACP fine — portfolio (USD)",
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
application with the BERDO Review Board before **September 1, 2026** to lock in this compliance
pathway for your 2025 emissions reporting.

**For policymakers:** This portfolio is currently compliant. Monitor whether high-emitting
buildings within the portfolio are being offset by efficient ones — the per-building table below
shows individual gaps.
""")
        else:
        
            #Find the worst-gap building for owner-facing guidance
            
            worst_addr = ""
            worst_gap_tons = 0.0
            for _, row in valid.iterrows():
                intensity = pd.to_numeric(row.get("GHG Intensity (kgCO2e/sqft)"), errors="coerce")
                sqft_r    = pd.to_numeric(row.get("Gross Floor Area"), errors="coerce")
                berdo_cat = map_property_type(row.get("Property Type"))
                if pd.isna(intensity) or pd.isna(sqft_r) or berdo_cat is None:
                    continue
                lim  = BERDO_STANDARDS[berdo_cat][0]
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
  their emissions are not counted here — your actual exposure may be higher.
- **File a portfolio application by September 1, 2026** to use the blended compliance pathway
  for your 2025 reporting. Without it, each building is assessed individually.

**For policymakers:** This owner's portfolio is non-compliant. The per-building table below
identifies which buildings are driving the deficit and which are providing surplus. Buildings
marked "Did not report" in the excluded table represent additional unknown exposure.
""")

    st.markdown("---")

    #Per-building surplus/deficit table (sorted by 2025 gap, worst first) ---
    st.markdown("####Per-Building Surplus / Deficit")
    st.caption(
        "Sorted by largest deficit first. "
        "Buildings with a surplus (negative gap) can offset those with a deficit at the portfolio level."
    )

    breakdown_rows = []
    for _, row in valid.iterrows():
        sqft      = pd.to_numeric(row["Gross Floor Area"], errors="coerce")
        intensity = pd.to_numeric(row["GHG Intensity (kgCO2e/sqft)"], errors="coerce")
        berdo_cat = map_property_type(row.get("Property Type"))

        if pd.isna(sqft) or pd.isna(intensity) or berdo_cat is None:
            continue

        limit_2025 = BERDO_STANDARDS[berdo_cat][0]
        limit_2030 = BERDO_STANDARDS[berdo_cat][1]
        limit_2035 = BERDO_STANDARDS[berdo_cat][2]

        def _gap_tons(lim):
            return round((intensity - lim) * sqft / 1000, 1)

        def _status(lim):
            return "Pass" if intensity <= lim else "Fail"

        breakdown_rows.append({
            "Address":        row["Building Address"],
            "Type":           berdo_cat,
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
        expander_label = " — ".join(label_parts)

        auto_expand = (skipped / total_buildings) > 0.3
        with st.expander(expander_label, expanded=auto_expand):
            st.caption(
                "These buildings are not included in the portfolio calculation. "
                "**State status** buildings are listed separately — verify their BERDO treatment before excluding. "
                "**Did not report** means no energy data was submitted to the City of Boston — "
                "their emissions are unknown and not reflected above. "
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
        "**Portfolio application deadline: September 1, 2026** — to apply the Building "
        "Portfolio compliance pathway to your 2025 emissions reporting. "
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
            "2022 GHG intensity is not shown — the City of Boston did not publish "
            "GHG emissions totals in that year's dataset."
        )

    prior_ghg   = prior["ghg_intensity"] if pd.notna(prior["ghg_intensity"]) else None
    prior_label = str(int(prior["year"]))
    return prior_ghg, prior_label


#RETROFIT COST BENCHMARKS
#Source: ASHRAE, RSMeans, NBI New Construction Cost Study, DOE BTO
#Units: national baseline USD per sq ft (low, high) — Boston multiplier applied separately
#Last verified: June 2026

RETROFIT_COST_PER_SQFT = {
    #scope → (low $/sqft national, high $/sqft national, notes)
    "Lighting (LED retrofit + controls)":               (1.5,   4.0,   "LED fixtures, occupancy sensors, daylight controls"),
    "HVAC (tune-up, controls, VFDs)":                   (3.0,   8.0,   "Controls upgrades, VFDs on pumps/fans, recommissioning"),
    "HVAC (full system replacement)":                   (15.0,  35.0,  "Chiller, AHU, or boiler replacement"),
    "Building envelope (windows + insulation)":         (8.0,   20.0,  "Window replacement, roof/wall insulation"),
    "Electrification — HVAC (air-source heat pump)":    (10.0,  22.0,  "Air-source heat pump — lower cost, suitable for most commercial buildings"),
    "Electrification — HVAC (ground-source heat pump)": (20.0,  45.0,  "Ground-source (geothermal) — higher efficiency, significantly higher upfront cost"),
    "Electrification — water heating":                  (2.0,   6.0,   "Heat pump water heaters replacing gas"),
    "Building-wide deep retrofit (all systems)":        (40.0,  100.0, "Comprehensive envelope + MEP overhaul"),
}

#Boston labor cost multiplier vs. national RSMeans baseline
#Source: RSMeans City Cost Index, Boston MA (2024-2025 avg)
BOSTON_LABOR_MULTIPLIER = 1.25

#BERDO EMISSIONS FACTORS
#Source: EPA Energy Star Portfolio Manager (August 2025 edition)
#BERDO uses these factors per the City of Boston regulations.
#Units: kg CO₂e per kBtu of site energy consumed

FUEL_EF_KG_PER_KBTU = {
    #BERDO Emissions Factors List, 2025 factors (kg CO₂e/mmBtu ÷ 1000).
    #Verified against the City of Boston PDF, last updated May 5, 2026.
    "Natural gas":      0.05311,
    "Propane":          0.06425,
    "Fuel oil #1":      0.07350,
    "Fuel oil #2":      0.07421,   #distillate / home heating oil
    "Fuel oil #4":      0.07529,
    "Fuel oil #5/#6":   0.07535,   #residual
    "Diesel":           0.07421,
    "Kerosene":         0.07769,
    "District steam":   0.06640,   #Default District Steam; named systems differ — see below
    "Electricity":      None,      #use effective_grid_ef() — Appendix B × (1 − RPS Class I)
}

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
        "name": "Mass Save — Commercial HVAC Rebates",
        "short": "Mass Save HVAC",
        "type": "Utility rebate",
        "priority": 1,
        "apply_first_reason": "Utility rebates are taxable income and reduce your 179D basis — claim after filing taxes, but negotiate before project start.",
        "scopes": ["HVAC (tune-up, controls, VFDs)", "HVAC (full system replacement)",
                   "Electrification — HVAC (air-source heat pump)", "Electrification — HVAC (ground-source heat pump)"],
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
            "Get pre-approval from Mass Save — required before installation",
            "Select a Mass Save Trade Ally contractor",
            "Complete installation and submit documentation",
            "Receive rebate check (typically 6–8 weeks post-completion)",
        ],
    },
    {
        "name": "Mass Save — Lighting Rebates",
        "short": "Mass Save Lighting",
        "type": "Utility rebate",
        "priority": 1,
        "apply_first_reason": "Pre-approval required before installation — start here.",
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
        "name": "Mass Save — Deep Energy Retrofit",
        "short": "Mass Save Deep Retrofit",
        "type": "Utility rebate",
        "priority": 1,
        "apply_first_reason": "Requires energy model and pre-approval — begin 3–6 months before construction.",
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
        "apply_first_reason": "Claim after utility rebates are received — rebates reduce your depreciable basis, which affects 179D calculation.",
        "scopes": ["Lighting (LED retrofit + controls)", "HVAC (tune-up, controls, VFDs)",
                   "HVAC (full system replacement)", "Building envelope (windows + insulation)",
                   "Electrification — HVAC (air-source heat pump)", "Electrification — HVAC (ground-source heat pump)", "Building-wide deep retrofit (all systems)"],
        "fuels": ["Natural gas", "Fuel oil", "Mixed / unknown", "Electric"],
        "amount_psf_low": 0.58,
        "amount_psf_high": 5.81,
        "cash_value_factor": 0.21,   #deduction, not credit — worth marginal rate × amount
        "closed_to_new_projects": True,
        "amount_str": "Up to USD 5.81/sqft (2025, prevailing wage and apprenticeship); USD 0.58–1.16/sqft (partial)",
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
            "179D only applies to construction that began on or before June 30, 2026 — confirm your project start date with a tax advisor",
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
        "apply_first_reason": "Claim alongside 179D — these stack. Document unit-level improvements during construction.",
        "scopes": ["Electrification — HVAC (air-source heat pump)", "Electrification — HVAC (ground-source heat pump)",
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
        "apply_first_reason": "Competitive allocation — apply early via IRS portal. May conflict with other IRA investment credits.",
        "scopes": ["Electrification — HVAC (air-source heat pump)", "Electrification — HVAC (ground-source heat pump)", "Electrification — water heating",
                   "Building-wide deep retrofit (all systems)"],
        "fuels": ["Natural gas", "Fuel oil", "Mixed / unknown"],
        "amount_psf_low": 0.60,
        "amount_psf_high": 3.00,
        "amount_str": "6% base (30% with prevailing wage and apprenticeship); capped per project",
        "eligibility": "Competitive allocation; manufacturing/industrial sites prioritized",
        "expiration": "Allocations ongoing; check IRS portal",
        "conflicts": ["IRA 48E", "Other IRA investment credits on same property"],
        "stacks_with": ["Mass Save rebates"],
        "berdo_periods": ["2025–29", "2030–34"],
        "ownership": ["For-profit"],
        "source": "https://www.irs.gov/credits-deductions/businesses/advanced-energy-project-credit",
        "checklist": [
            "Check IRS portal for open allocation rounds",
            "Prepare project application (technology description, cost, job creation)",
            "Submit application during open window — allocations are competitive",
            "If awarded, begin construction within required timeframe",
            "Comply with prevailing wage + apprenticeship for 30% rate",
            "Claim credit on federal return (Form 3468)",
        ],
    },
    {
        "name": "MassDOER Clean Energy Grants",
        "short": "MassDOER Grant",
        "type": "State grant",
        "priority": 1,
        "apply_first_reason": "Grant funds must be committed before construction — apply during open rounds.",
        "scopes": ["Electrification — HVAC (air-source heat pump)", "Electrification — HVAC (ground-source heat pump)", "Electrification — water heating",
                   "Building-wide deep retrofit (all systems)"],
        "fuels": ["Natural gas", "Fuel oil", "Mixed / unknown", "Electric"],
        "amount_psf_low": 0.20,
        "amount_psf_high": 1.50,
        "amount_str": "Up to USD 250,000/project; varies by program round",
        "eligibility": "Nonprofits and municipal buildings in MA",
        "expiration": "Check MassCEC for current open rounds",
        "conflicts": [],
        "stacks_with": ["Mass Save rebates", "Green Communities"],
        "berdo_periods": ["2025–29", "2030–34", "2035–39"],
        "ownership": ["Nonprofit / Government"],
        "source": "https://www.masscec.com/program/clean-energy-results-program",
        "checklist": [
            "Monitor MassCEC website for open grant rounds",
            "Prepare project narrative and cost estimate",
            "Submit application during open window",
            "Execute grant agreement if awarded",
            "Submit progress reports and final documentation",
        ],
    },
    {
        "name": "Green Communities Grant",
        "short": "Green Communities",
        "type": "State grant",
        "priority": 1,
        "apply_first_reason": "Annual grant cycle — apply in the current round.",
        "scopes": ["Lighting (LED retrofit + controls)", "HVAC (tune-up, controls, VFDs)",
                   "HVAC (full system replacement)", "Building envelope (windows + insulation)",
                   "Electrification — HVAC (air-source heat pump)", "Electrification — HVAC (ground-source heat pump)",
                   "Building-wide deep retrofit (all systems)"],
        "fuels": ["Natural gas", "Fuel oil", "Mixed / unknown", "Electric"],
        "amount_psf_low": 0.20,
        "amount_psf_high": 2.00,
        "amount_str": "Up to USD 1.6M/municipality; formula-based on population",
        "eligibility": "MA municipalities with Green Community designation",
        "expiration": "Annual grant rounds; check DOER for current cycle",
        "conflicts": [],
        "stacks_with": ["MassDOER Grant", "Mass Save rebates"],
        "berdo_periods": ["2025–29", "2030–34", "2035–39"],
        "ownership": ["Nonprofit / Government"],
        "source": "https://www.mass.gov/green-communities-designation-grant-program",
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
    Tab 3 — Retrofit & Incentives (merged Retrofit Estimator + Incentive Optimizer).
    Collects building inputs once, then shows condition-adjusted cost estimates,
    matched incentives ranked by value, stacking order, and payback.
    Pre-fills from address lookup session state where available.
    """
    if prefill is None:
        prefill = {}

    st.write(
        "Estimate retrofit costs and find the right incentives — in one place. "
        "Enter your building details and the scopes you're considering to see "
        "condition-adjusted cost ranges, matched funding programs, stacking order, and payback."
    )
    st.info(
        "**Incentive data verified June 2026.** Mass Save program-year amounts reset each January. "
        "IRA figures reflect current regulations. Always confirm amounts at source links before advising a client."
    )

    #Inputs
    
    #Inject prefill into session state when a new address lookup arrives.
    #We detect a "fresh" prefill by comparing the prefill address to the
    #last address we injected — if different, overwrite widget state.
    
    prefill_addr_key = prefill.get("address", "")
    last_injected    = st.session_state.get("opt_last_injected_addr", "")

    if prefill_addr_key and prefill_addr_key != last_injected:
        if prefill.get("sqft"):
            st.session_state["opt_sqft"] = int(prefill["sqft"])
        if prefill.get("berdo_category"):
            type_options_init = ["— select —"] + sorted(BERDO_STANDARDS.keys())
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
        type_options = ["— select —"] + sorted(BERDO_STANDARDS.keys())
        prefill_cat  = st.session_state.get("opt_btype", "— select —")
        default_idx  = type_options.index(prefill_cat) if prefill_cat in type_options else 0
        selected_type = st.selectbox(
            "Building type (BERDO category)",
            options=type_options, index=default_idx,
            help="Pre-filled from Address Lookup if available.",
            key="opt_btype",
        )
        berdo_category = selected_type if selected_type != "— select —" else None

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
        options=["Yes — ASHRAE Level 2 or equivalent", "No — rough estimate only"],
        index=1,
        key="opt_cond_audit",
        help=(
            "An audit replaces range assumptions with building-specific data. "
            "Without one, unknowns tend to push costs toward the upper half of the range — "
            "so this estimate defaults to the mid-range as a conservative starting point."
        ),
    )
    has_audit = "ASHRAE" in prior_audit
    if has_audit:
        position        = 0.20
        condition_label = "Audit complete — estimate toward low end"
    else:
        position        = 0.55
        condition_label = "No audit — mid-range estimate (actual scope may run higher)"

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
        f"{_badge} **{condition_label}** — Adjusted estimate: "
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
    st.subheader("Planned project — will it close the compliance gap?")
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
            limit_2025 = BERDO_STANDARDS[berdo_category][0]
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
            "Try adjusting ownership type, fuel, or scope — "
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
            payback_str = " — energy savings are the primary return driver for a building this size"
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
              f"${total_incentive_low:,.0f} – ${total_incentive_high:,.0f}")
    m3.metric("Gross retrofit cost (low–high)",
              f"${total_cost_low:,.0f} – ${total_cost_high:,.0f}")
    m4.metric("Estimated net cost (low–high)",
              f"${net_low:,.0f} – ${net_high:,.0f}")

        st.caption(
        "Incentive estimates are $/sqft proxies based on program benchmarks — "
        "actual awards depend on application, project scope, and program availability. "
        "Tax **deductions** are shown at after-tax cash value (21% corporate rate), not face value. "
        "Programs closed to new projects — IRA 179D and 45L, both terminated for work beginning "
        "after June 30, 2026 — are excluded from these totals. "
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
    st.subheader("Stacking strategy — apply in this order")
    st.caption(
        "Order matters. Utility rebates reduce your tax basis; "
        "some IRA credits conflict with each other. Follow this sequence."
    )

    steps = sorted(matched, key=lambda x: x["priority"])
    for i, inc in enumerate(steps, 1):
        with st.expander(
            f"**{i}. {inc['name']}** — {inc['type']} "
            f"(est. ${inc['_est_low']:,.0f} – ${inc['_est_high']:,.0f})",
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
        with st.expander(f"**{inc['name']}** — checklist", expanded=False):
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
            "estimated annual BERDO fine — or enter it manually below."
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
            "Energy cost savings from a retrofit are typically the largest financial return — "
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
                    "$0.50–$1.50/sqft/yr for HVAC upgrades; "
                    "$1.00–$2.50/sqft/yr for deep retrofits. "
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

        #Payback metrics — cap at 50 years; beyond that fine avoidance is the wrong frame
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
            "Payback — fine only (low)",
            _fmt_payback(payback_low_fine_only),
        )
        pb_cols[1].metric(
            "Payback — fine only (high)",
            _fmt_payback(payback_high_fine_only),
        )
        pb_cols[2].metric(
            "Payback — fine + energy (low)",
            _fmt_payback(payback_low_combined),
            delta=f"{round(payback_low_fine_only - payback_low_combined, 1)} yrs faster"
                  if 0 < payback_low_fine_only <= PAYBACK_CAP and payback_low_combined <= PAYBACK_CAP and payback_low_fine_only > payback_low_combined
                  else None,
        )
        pb_cols[3].metric(
            "Payback — fine + energy (high)",
            _fmt_payback(payback_high_combined),
            delta=f"{round(payback_high_fine_only - payback_high_combined, 1)} yrs faster"
                  if 0 < payback_high_fine_only <= PAYBACK_CAP and payback_high_combined <= PAYBACK_CAP and payback_high_fine_only > payback_high_combined
                  else None,
        )

        if fine_only_impractical:
            st.warning(
                f"For a building this size ({sqft:,} sqft), BERDO fines alone do not justify "
                "the retrofit cost. This is normal for large commercial buildings — "
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
                name="Low cost — fine avoidance only",
                mode="lines", line=dict(color="#3266ad", width=1.5, dash="dash"),
            ))
            fig.add_trace(go.Scatter(
                x=years, y=cumulative_high_fine,
                name="High cost — fine avoidance only",
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
            "Not an investment projection. Energy savings are estimates — actual savings "
            "depend on building operations, utility rates, and project scope. "
            "Consult a licensed energy auditor for project-specific figures."
        )

        #Payback summary message
        best_payback = payback_low_combined if energy_savings_psf > 0 else payback_low_fine_only
        if best_payback == 0:
            st.success(
                "At the low net cost estimate, the retrofit is fully covered by incentives — "
                "any energy savings and fine avoidance are pure return from day one."
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
                "Consider whether a phased retrofit — higher-ROI measures first — "
                "improves the near-term economics."
            )
        else:
            #Large building: fine avoidance is the wrong frame entirely
            energy_annual_str = _fmt_dollars(energy_savings_annual).replace("$", "USD ")
            st.info(
                "For a building this size, the primary financial drivers are **energy cost savings** "
                f"({energy_annual_str}/yr at current assumptions) and **asset value protection** — "
                "not fine avoidance alone. Consider: lender and investor ESG requirements, "
                "tenant retention in a market increasingly sensitive to building performance, "
                "and the cost trajectory of fines as BERDO limits tighten toward 2050. "
                "Adjust the energy savings input above to model the full return."
            )

    #Retrofit vs. compliance decision
    st.markdown("---")
    st.subheader("Retrofit vs. pay the fine")
    st.caption(
        "Sometimes paying the ACP fine is cheaper than retrofitting — at least in the near term. "
        "This section compares both paths so you can make an informed decision."
    )

    if not annual_fine or annual_fine == 0:
        st.info(
            "Look up your building in the Address Lookup tab or enter your annual fine above "
            "to see the retrofit vs. compliance comparison."
        )
    elif berdo_category and berdo_category in BERDO_STANDARDS:
    
        #Cost of paying the fine across each compliance period
        fine_5yr  = annual_fine * 5

        #Future period fines — limits tighten each period
        limits = BERDO_STANDARDS[berdo_category]
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
            "Fines — cumulative through 2050",
            _fmt_dollars(cumulative_fine_all),
            delta="If no retrofit is ever made",
        )
        d3.metric(
            "Retrofit — net cost (low estimate)",
            "Fully covered by incentives" if net_low == 0 else _fmt_dollars(net_low),
            delta="One-time outlay, fines avoided permanently",
        )

        #Plain-English recommendation
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
                f"**Retrofit now — clear financial case.** The net retrofit cost "
                f"({net_low_str}) is less than or equal to one period of BERDO fines "
                f"({fine_5yr_str} for 2025–29 alone). "
                "And fines only grow from here. Each period the limit tightens and the "
                "gap widens. Retrofitting eliminates all future fine exposure permanently."
            )
        elif net_low <= cum_fine_10yr:
            #Retrofit pays back within 2 periods (10 years) of escalating fines
            st.success(
                f"**Retrofit soon — strong case once fines escalate.** "
                f"The net retrofit cost ({net_low_str}) is less than cumulative fines "
                f"over the first two periods ({cum_10yr_str} through 2030–34). "
                f"Fines increase each period as the BERDO limit tightens — "
                "waiting means paying more before you eventually retrofit anyway."
            )
        elif net_low <= cumulative_fine_all:
            #Retrofit is cheaper than total lifetime fines — crossover at some period
            st.warning(
                f"**Consider phasing — fines will exceed retrofit cost by {crossover_period or 'a future period'}.** "
                f"Paying the fine costs less upfront ({fine_5yr_str} for 2025–29) "
                f"vs. retrofitting now ({net_low_str}). "
                f"However, BERDO limits tighten every 5 years. Your annual fine grows "
                f"each period as the gap between your building's emissions and the limit widens. "
                f"Cumulative fines reach {cum_str} through 2050 if nothing is done. "
                "A phased approach — lower-cost measures now, deeper retrofit before the next "
                "period tightens — may be the most cost-effective path."
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
                "and lender/investor ESG requirements — which for large buildings often "
                "dwarf the fine exposure. Run the numbers with your energy consultant "
                "before ruling out the retrofit."
            )

        #Period-by-period fine escalation table
        if period_fines:
            st.markdown("Fine escalation by period")
            st.caption(
                "Each period the BERDO limit drops. If your building's emissions stay flat, "
                "the gap — and the fine — grows. The right column shows when cumulative "
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
        "**Screening tool only — not professional financial or tax advice.** "
        "Incentive amounts are benchmarks verified June 2026; they change annually. "
        "IRA credit stacking rules are complex — consult a tax advisor for your specific situation. "
        "Do not use these figures for contracts, loan applications, or compliance filings."
    )

    with st.expander("Sources & methodology"):
        st.markdown("""
**Incentive data sources (verified June 2026)**
- Mass Save commercial rebates: masssave.com (amounts reset each January)
- IRA Section 179D: IRS Notice 2023-29, as amended; inflation-indexed annually
- IRA Section 48C: IRS Rev. Proc. 2023-27; competitive allocation rounds
- IRA Section 45L: IRS Notice 2023-65; terminated for homes acquired after June 30, 2026 (P.L. 119-21)
- IRA Section 179D: terminated for property whose construction begins after June 30, 2026 (P.L. 119-21)
- MassDOER / MassCEC: masscec.com and mass.gov/doer (program-dependent)
- Green Communities: mass.gov/green-communities (annual grant rounds)

**Stacking methodology**
Utility rebates (Mass Save) are taxable income and reduce your 179D depreciable basis —
claim them before calculating your 179D deduction. IRA 48C may conflict with other IRA
investment credits applied to the same property — verify with a tax advisor. All other
matched programs stack cleanly for most commercial scenarios.

**Dollar estimates**
Incentive values are estimated using $/sqft proxies derived from published program benchmarks.
Actual awards depend on application outcome, project documentation, and contractor certification.
""")

#EMISSIONS PLANNER — Tab 5

def render_emissions_planner_tab(prefill: dict = None, show_grid_decarb: bool = False, elec_share=None):
    """
    Tab 5 — Emissions Planner.
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
        type_options = ["— select —"] + sorted(BERDO_STANDARDS.keys())
        prefill_cat  = st.session_state.get("ep_btype", "— select —")
        default_idx  = type_options.index(prefill_cat) if prefill_cat in type_options else 0
        selected_type = st.selectbox(
            "Building type (BERDO category)",
            options=type_options, index=default_idx, key="ep_btype",
            help="Pre-filled from Address Lookup if available.",
        )
        berdo_category = selected_type if selected_type != "— select —" else None
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
    elec_share_val = elec_share if elec_share is not None else 0.5

    if apply_grid:
        base_ef = effective_grid_ef(2025)
        ef_2050 = effective_grid_ef(2050)
        st.caption(
            f"Grid decarbonization is ON (sidebar). "
            f"Electricity share: {round(elec_share_val * 100)}%. "
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

    limits             = BERDO_STANDARDS[berdo_category]
    #Use the raw reported GHG emissions total when available (more accurate than
    #Intensity × sqft which suffers from rounding). Fall back to intensity × sqft.
    ghg_emissions_raw = prefill.get("ghg_emissions_kg")
    if ghg_emissions_raw and ghg_emissions_raw > 0:
        total_emissions_kg = float(ghg_emissions_raw)
        st.caption(
            f"Baseline: **{total_emissions_kg:,.0f} kg CO₂e/yr** (from reported BERDO data). "
            f"Derived intensity: {total_emissions_kg / sqft:.3f} kg CO₂e/sqft/yr."
        )
    else:
        total_emissions_kg = ghg_intensity * sqft

    #Grid decarbonization, project intensities per period
    
    if apply_grid:
        projected_intensities = project_ghg_intensities(
            ghg_intensity=ghg_intensity,
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
            erow["Reductions"]       = _fmt_kg(period_reductions_kg[i]) if period_reductions_kg[i] > 0 else "—"
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
            "ACP — baseline":     _fmt_fine(fine_baseline),
        }
        if has_projects:
            frow["ACP — with projects"]  = _fmt_fine(fine_proj)
        if has_grid:
            frow["ACP — grid decarb"]    = _fmt_fine(fine_grid)
        if has_projects and has_grid:
            frow["ACP — grid + projects"] = _fmt_fine(fine_combined)
        fines_rows.append(frow)

    #Table 1: Emissions
    st.markdown("####Projected emissions vs. BERDO limit (kg CO₂e/yr)")
    st.dataframe(pd.DataFrame(emissions_rows), use_container_width=True, hide_index=True)

    #Table 2: ACP fines
    st.markdown("####Estimated ACP fine — annual, per period")
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
        "Annual ACP — current period (2025–29)",
        f"${current_annual_fine:,.0f}",
        delta="at current emissions, this period's cap",
    )
    s_cols[0].metric(
        "Cumulative ACP 2025–2050 — no action",
        f"${baseline_fines_cumul:,.0f}",
        delta="worst case: emissions flat, no retrofit",
    )
    col_idx = 1
    if has_projects:
        savings = baseline_fines_cumul - proj_fines_cumul
        s_cols[col_idx].metric(
            "Cumulative ACP — with projects",
            f"${proj_fines_cumul:,.0f}",
            delta=f"-${savings:,.0f} vs no action" if savings > 0 else "No change",
        )
        col_idx += 1
    if has_grid:
        savings_g = baseline_fines_cumul - grid_fines_cumul
        s_cols[col_idx].metric(
            "Cumulative ACP — grid decarb only",
            f"${grid_fines_cumul:,.0f}",
            delta=f"-${savings_g:,.0f} vs no action" if savings_g > 0 else "No change",
        )
        col_idx += 1
    if has_projects and has_grid:
        savings_c = baseline_fines_cumul - combined_fines_cumul
        s_cols[col_idx].metric(
            "Cumulative ACP — grid + projects",
            f"${combined_fines_cumul:,.0f}",
            delta=f"-${savings_c:,.0f} vs no action" if savings_c > 0 else "No change",
        )
        
        if has_projects:
            total_reduction_mt = period_reductions_kg[0] / 1000
            gap_mt = max(total_emissions_kg - limits[0] * sqft, 0) / 1000
            if gap_mt > 0:
                pct = total_reduction_mt / gap_mt * 100
                st.caption(
                    f"Your projects reduce ~{total_reduction_mt:,.0f} MT/yr — about {pct:.1f}% of the "
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
        name="Worst case — no action",
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
        st.markdown("""
**How emissions are projected**

The baseline uses your building's current reported GHG intensity (kg CO₂e/sqft/yr) 
multiplied by floor area, held flat across all periods — a worst-case assumption, not a forecast —
grid decarbonization would reduce electricity-attributed emissions over time independently of 
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

Source: BERDO 2.0 Phase 1 Regulations (Boston APCC, adopted October 2021); 
EPA Portfolio Manager Emissions Factors (August 2025).
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
        "(Appendix B, BERDO Emissions Factors List, May 2026). "
        "Fossil fuel use is held constant."
    ),
)
if show_grid_decarb:
    elec_share_pct = st.sidebar.slider(
        "Electricity share of GHG emissions (%)",
        min_value=0,
        max_value=100,
        value=50,
        step=5,
        help=(
            "Estimated percentage of this building's total GHG emissions "
            "that come from grid electricity (vs. fossil fuels such as "
            "natural gas). Check the building's energy breakdown in ESPM "
            "or use 50% as a starting estimate for a typical office/mixed-use building."
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

#Tab 1 — single address lookup (unchanged behaviour)

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
                
            with st.expander("What do these fields mean?"):
                st.markdown("""
**Compliance Status**
- **Submitted**: The building owner reported energy and emissions data to the City of Boston for the previous calendar year.
- **Not submitted**: No data was reported. Buildings required to report under BERDO face fines of \$150–\$300/day for missing the annual May 15 reporting deadline (\$300/day for buildings over 35,000 sq ft; \$150/day for smaller covered buildings). Note: the 2026 reporting deadline was extended to August 15, 2026. Separate daily fines of \$1,000/day (buildings over 35,000 sq ft) or \$300/day (smaller covered buildings) apply for failing to meet emissions standards.

**Site EUI (Energy Use Intensity)**
- Measures how much energy a building uses per square foot per year (kBtu/sq ft/yr). A higher EUI means the building uses more energy relative to its size. Missing EUI typically means the building did not submit complete energy data.

**GHG Intensity (kg CO₂e/sq ft/yr)**
- The building's greenhouse gas emissions per square foot per year, calculated from reported fuel and electricity use. This is the value compared against BERDO emissions limits to determine compliance.

**Data Status**
- **Reported**: energy and emissions data submitted and complete enough to evaluate.
- **Incomplete data**: submitted, but property type, floor area, or GHG data is missing or unmappable — compliance can't be calculated.
- **Not submitted**: no data reported. Accruing daily reporting fines.

**BERDO Status**
- **Over 2025–29 limit**: currently exceeds its sector limit and accruing ACP.
- **Fails 2030–34**: compliant now, but over the next limit at current emissions.
- **Compliant through 2034** / **2039+**: how far the current trajectory holds.
- **Not yet covered**: smaller covered building, not subject to an emissions limit until 2030.
- **Unknown — data incomplete**: compliance can't be determined from what was reported.

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
                ghg_val = top.get("GHG Intensity (kgCO2e/sqft)")
                if pd.notna(ghg_val) and ghg_val > 0:
                    projected_intensities = project_ghg_intensities(
                        ghg_intensity=float(ghg_val),
                        elec_share=elec_share,
                        base_year=selected_year,
                    )

            render_compliance_section(
                top,
                prior_year_ghg_intensity=prior_ghg,
                prior_year_label=prior_label,
                projected_intensities=projected_intensities,
                base_year=selected_year,
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
            }

            #Calculate fine for 2025–29 period if possible
            if (
                pd.notna(ghg_val) and ghg_val > 0
                and pd.notna(sqft_val) and sqft_val > 0
                and berdo_cat in BERDO_STANDARDS
            ):
                limit_2025 = BERDO_STANDARDS[berdo_cat][0]
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
                "Building data saved — open the **Retrofit & Incentives** or **Emissions Planner** tabs "
                "to model funding programs and compliance trajectory for this building."
            )


#Tab 2 — owner portfolio lookup

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
                    "A Building Portfolio requires multiple buildings — "
                    "use the Address Lookup tab for single-building analysis."
                )
            else:
                st.markdown("---")
                render_portfolio_section(
                    portfolio_result,
                    selected_year=selected_year,
                    elec_share=elec_share if show_grid_decarb else None,
                    all_years=all_years,
                    show_yoy=show_yoy,
                )
                

#Tab 3 — Retrofit & Incentives (merged Retrofit Estimator + Incentive Optimizer)

with tab_retrofit_optimizer:
    opt_prefill = st.session_state.get("optimizer_prefill", {})
    render_retrofit_optimizer_tab(prefill=opt_prefill)


#Tab 4 — Emissions Planner

with tab_planner:
    planner_prefill = st.session_state.get("planner_prefill", {})
    render_emissions_planner_tab(
        prefill=planner_prefill,
        show_grid_decarb=show_grid_decarb,
        elec_share=elec_share,
    )
