import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pathlib import Path

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="BERDO Building Priority & Incentive Tool",
    layout="wide"
)

# ---------------------------------------------------------------------------
# BERDO 2.0 emissions standards
# Source: BERDO 2.0 Draft Phase 1 Regulations (Boston APCC, 2021)
# Units: kg CO2e / sq ft / year
# Periods: 2025-29, 2030-34, 2035-39, 2040-44, 2045-49, 2050+
# ---------------------------------------------------------------------------
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

ACP_RATE = 234  # USD per metric ton CO2e over the limit

# ---------------------------------------------------------------------------
# Projected ISO New England grid emissions factors by year
# Source: BERDO Emissions Factors List, Appendix B (updated May 5, 2026)
# Units: kg CO2e / MWh
# ---------------------------------------------------------------------------
PROJECTED_GRID_EF = {
    2022: 270, 2023: 263, 2024: 256, 2025: 249, 2026: 242,
    2027: 265, 2028: 265, 2029: 264, 2030: 259, 2031: 254,
    2032: 249, 2033: 243, 2034: 237, 2035: 231, 2036: 224,
    2037: 217, 2038: 211, 2039: 204, 2040: 198, 2041: 192,
    2042: 187, 2043: 182, 2044: 177, 2045: 173, 2046: 168,
    2047: 163, 2048: 159, 2049: 155, 2050: 150,
}

# Representative year for each compliance period (midpoint, or period start for 2050+)
PERIOD_REPRESENTATIVE_YEARS = [2027, 2032, 2037, 2042, 2047, 2050]

# ---------------------------------------------------------------------------
# Mapping from Energy Star Portfolio Manager property types → BERDO categories
# ---------------------------------------------------------------------------
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


def map_property_type(raw_type):
    if pd.isna(raw_type) or not isinstance(raw_type, str):
        return None
    key = raw_type.strip().lower()
    return PROPERTY_TYPE_MAP.get(key)


# ---------------------------------------------------------------------------
# Grid decarbonization projection
# ---------------------------------------------------------------------------
def project_ghg_intensities(ghg_intensity, elec_share, base_year):
    """
    Project GHG intensity for each compliance period assuming:
      - Electricity component shrinks as the grid decarbonizes
        (using Appendix B projected grid EFs)
      - Fossil fuel component stays constant (no operational changes)

    Returns a list of 6 projected intensities, one per COMPLIANCE_PERIODS entry.
    Falls back to the base_year EF if base_year is not in PROJECTED_GRID_EF.
    """
    base_ef = PROJECTED_GRID_EF.get(base_year, PROJECTED_GRID_EF[2025])
    if base_ef == 0:
        return [ghg_intensity] * len(COMPLIANCE_PERIODS)

    elec_intensity   = ghg_intensity * elec_share
    fossil_intensity = ghg_intensity * (1.0 - elec_share)

    projected = []
    for yr in PERIOD_REPRESENTATIVE_YEARS:
        future_ef = PROJECTED_GRID_EF.get(yr, base_ef)
        future_elec = elec_intensity * (future_ef / base_ef)
        projected.append(round(fossil_intensity + future_elec, 3))
    return projected


# ---------------------------------------------------------------------------
# Compliance gap calculation
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Compliance gap display
# ---------------------------------------------------------------------------
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

    # Projected gaps (for grid decarb scenario metric cards)
    if projected_intensities is not None:
        proj_gaps = [
            calculate_compliance_gap(pi, sqft, berdo_category)
            for pi in projected_intensities
        ]
        # proj_gaps[i] is a list of 6 period gaps for the projected intensity at period i
        # We only need the gap for each period against its own limit, i.e. proj_gaps[i][i]
        proj_gap_for_period = [proj_gaps[i][i] for i in range(len(COMPLIANCE_PERIODS))]
    else:
        proj_gap_for_period = None

    st.caption(
        f"Current intensity: **{ghg_intensity:.3f} kg CO₂e/sf/yr** · "
        f"Floor area: **{int(sqft):,} sq ft** · "
        f"BERDO category: **{berdo_category}**"
    )

    # --- Metric cards (first 3 periods) ---
    cols = st.columns(3)
    period_labels = ["2025–2029", "2030–2034", "2035–2039"]
    for i, col in enumerate(cols):
        g = gaps[i]
        with col:
            status = "✅ Compliant" if g["compliant"] else "⚠️ Non-compliant"
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
                # Show projected outcome if available
                if proj_gap_for_period is not None:
                    pg = proj_gap_for_period[i]
                    if pg["compliant"]:
                        st.caption("🌱 Grid scenario: compliant")
                    else:
                        st.caption(
                            f"🌱 Grid scenario: +{pg['gap']:.2f} kg over limit "
                            f"(${pg['annual_fine_usd']:,.0f}/yr)"
                        )

    st.markdown("---")

    # --- Chart ---
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

    # Grid decarbonization scenario overlay
    if projected_intensities is not None:
        fig.add_trace(go.Scatter(
            x=COMPLIANCE_PERIODS,
            y=projected_intensities,
            name="Grid decarbonization scenario",
            mode="lines+markers",
            line=dict(color="#2ECC71", width=2),
            marker=dict(size=7, symbol="diamond"),
        ))

    # Optional prior-year intensity overlay
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

    st.plotly_chart(fig, use_container_width=True, key=f"compliance_chart_{id(row)}")

    # --- Fine exposure summary ---
    non_compliant_periods = [g for g in gaps if not g["compliant"]]
    if non_compliant_periods:
        total_5yr_fine = sum(g["annual_fine_usd"] * 5 for g in non_compliant_periods)
        msg = (
            f"**Conservative scenario:** if no emissions reductions are made, this building "
            f"faces an estimated **${total_5yr_fine:,.0f}** in cumulative ACP payments across "
            f"{len(non_compliant_periods)} non-compliant period(s) "
            f"(annual fine × 5 years per period)."
        )
        if projected_intensities is not None:
            proj_non_compliant = [
                proj_gap_for_period[i]
                for i in range(len(COMPLIANCE_PERIODS))
                if not proj_gap_for_period[i]["compliant"]
            ]
            total_proj_fine = sum(g["annual_fine_usd"] * 5 for g in proj_non_compliant)
            if proj_non_compliant:
                msg += (
                    f"\n\n**Grid decarbonization scenario:** estimated **${total_proj_fine:,.0f}** "
                    f"across {len(proj_non_compliant)} non-compliant period(s)."
                )
            else:
                msg += "\n\n**Grid decarbonization scenario:** building achieves compliance in all periods from grid cleaning alone."
        st.info(msg)

    # --- Caption ---
    base_ef = PROJECTED_GRID_EF.get(base_year, PROJECTED_GRID_EF[2025])
    caption = (
        "ACP = Alternative Compliance Payment at $234/metric ton CO₂e over limit. "
        "**Conservative line:** current GHG intensity held flat — no operational changes, "
        "no grid improvement. "
    )
    if projected_intensities is not None:
        caption += (
            f"**Grid decarbonization line:** electricity component scaled by ISO-NE projected "
            f"grid EFs (Appendix B, base year {base_year} = {base_ef} kg/MWh); "
            "fossil fuel use held constant. "
        )
    caption += (
        "Source: BERDO 2.0 Draft Phase 1 Regulations (Boston APCC, 2021); "
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
in 2025. Smaller buildings between 20,000 and 35,000 sq ft begin compliance in 2030.

**How is the priority score calculated?**

Each building is scored on four factors:
- **Not submitted** (3 points): The building did not report data to the City of Boston by the May 15 deadline.
- **Missing property type** (2 points): The building's use category is not recorded, which prevents accurate emissions benchmarking.
- **Missing or above-median Site EUI** (2 points): The building's energy use intensity is missing or higher than the dataset median, indicating potential inefficiency.
- **Large floor area** (1 point): Buildings over 100,000 sq ft have greater emissions impact.

Scores of 6 or above are flagged as High priority. Scores of 3–5 are Moderate. Below 3 is Low.

**How is the compliance gap calculated?**

The tool compares each building's reported GHG intensity (kg CO₂e per square foot per year)
against the BERDO 2.0 emissions limits for its property type. If the building exceeds the limit,
the tool estimates the annual Alternative Compliance Payment (ACP) at $234 per excess metric
ton of CO₂e.

**What is the grid decarbonization scenario?**

The ISO New England electric grid is projected to become cleaner over time as renewable energy
grows. This scenario holds fossil fuel use constant but scales down the electricity-attributed
emissions using the City of Boston's official projected grid emissions factors (Appendix B of the
BERDO Emissions Factors List). Use the sidebar slider to set the share of the building's
emissions that come from electricity. If unknown, 50% is a reasonable starting point for a
mixed-use or office building; electricity-heavy buildings (all-electric, data centers) should
use a higher value.

Source: BERDO 2.0 Draft Phase 1 Regulations (Boston APCC, 2021);
BERDO Emissions Factors List (City of Boston, updated May 5, 2026).
Not an official City of Boston compliance determination.
""")


# ---------------------------------------------------------------------------
# Data loading — supports single file (berdo.csv) or multi-year files
# (berdo_2022.csv, berdo_2023.csv, …) in the data/ folder.
# ---------------------------------------------------------------------------
COLUMN_RENAME_MAP = {
    "Largest Property Type": "property_type",
    "Reported Gross Floor Area (Sq Ft)": "gross_floor_area",
    "Site EUI (Energy Use Intensity kBtu/ft²)": "site_eui",
    "Estimated Total GHG Emissions (kgCO2e)": "ghg_emissions",
    "Estimated Total GHG Emissions e(kgCO2e)": "ghg_emissions",
    "Reporting Compliance Status": "compliance_status",
    "First Emissions Compliance Year (Projected)": "compliance_year",
}

REQUIRED_COLUMNS = [
    "Building Address", "Property Owner Name", "property_type",
    "gross_floor_area", "site_eui", "ghg_emissions",
    "compliance_status", "compliance_year",
]


@st.cache_data
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


@st.cache_data
def load_all_years() -> dict[int, pd.DataFrame]:
    """
    Returns a dict mapping year (int) → DataFrame.

    Discovery rules (in priority order):
      1. berdo_<year>.csv files  →  multi-year mode
      2. berdo.csv               →  single-year fallback (keyed as year 0)
    """
    data_dir = Path("data")
    year_files = sorted(data_dir.glob("berdo_*.csv"))

    year_map: dict[int, pd.DataFrame] = {}
    for fp in year_files:
        stem = fp.stem  # e.g. "berdo_2023"
        try:
            year = int(stem.split("_")[1])
        except (IndexError, ValueError):
            continue
        year_map[year] = _load_single_csv(fp)

    if not year_map:
        # Fallback: single legacy file
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


# ---------------------------------------------------------------------------
# Priority scoring
# ---------------------------------------------------------------------------
def assign_priority(row, median_eui):
    score = 0
    reasons = []

    if row["compliance_status"] == "not submitted":
        score += 3
        reasons.append("Building is marked as not submitted")

    if pd.isna(row["property_type"]):
        score += 2
        reasons.append("Property type is missing")

    if pd.isna(row["site_eui"]):
        score += 2
        reasons.append("Site EUI is missing")
    elif row["site_eui"] >= median_eui:
        score += 2
        reasons.append("Site EUI is above the dataset median")

    if pd.notna(row["gross_floor_area"]) and row["gross_floor_area"] >= 100000:
        score += 1
        reasons.append("Building has a large reported floor area")

    if score >= 6:
        priority = "High"
    elif score >= 3:
        priority = "Moderate"
    else:
        priority = "Low"

    return priority, score, reasons


def lookup_building_priority(df, address):
    import re
    address_clean = re.split(r',', address)[0].strip()
    matches = df[
        df["Building Address"].astype(str).str.contains(address_clean, case=False, na=False)
    ]
    if matches.empty:
        return None

    median_eui = df["site_eui"].median()
    results = []

    for _, row in matches.iterrows():
        priority, score, reasons = assign_priority(row, median_eui)
        results.append({
            "Building Address":            row.get("Building Address"),
            "Property Owner Name":         row.get("Property Owner Name"),
            "Property Type":               row.get("property_type"),
            "Gross Floor Area":            row.get("gross_floor_area"),
            "Site EUI":                    row.get("site_eui"),
            "GHG Intensity (kgCO2e/sqft)": row.get("ghg_intensity_kgco2e_sqft"),
            "Compliance Status":           row.get("compliance_status"),
            "Priority Level":              priority,
            "Priority Score":              score,
            "Reasons":                     "; ".join(reasons),
        })

    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# Owner portfolio lookup
# ---------------------------------------------------------------------------
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

    median_eui = df["site_eui"].median()
    results = []
    for _, row in matches.iterrows():
        priority, score, reasons = assign_priority(row, median_eui)
        results.append({
            "Building Address":            row.get("Building Address"),
            "Property Owner Name":         row.get("Property Owner Name"),
            "Property Type":               row.get("property_type"),
            "Gross Floor Area":            row.get("gross_floor_area"),
            "Site EUI":                    row.get("site_eui"),
            "GHG Intensity (kgCO2e/sqft)": row.get("ghg_intensity_kgco2e_sqft"),
            "GHG Emissions (kgCO2e)":      row.get("ghg_emissions"),
            "Compliance Status":           row.get("compliance_status"),
            "Priority Level":              priority,
            "Priority Score":              score,
            "Reasons":                     "; ".join(reasons),
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


# ---------------------------------------------------------------------------
# Portfolio compliance section
# ---------------------------------------------------------------------------
def render_portfolio_section(buildings_df, selected_year, elec_share, all_years, show_yoy):
    """
    Renders BERDO compliance analysis for a multi-building owner portfolio.
    Shows portfolio-level blended standard, aggregate gap, fine exposure,
    and a per-building surplus/deficit breakdown table.
    """
    st.subheader("Portfolio Compliance Analysis")

    # --- Classify buildings: valid vs excluded (with reason) ---
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
                reason = "State-owned property — exempt from BERDO reporting"
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
        # Still show excluded table so user knows what's missing
        if excluded_rows:
            with st.expander(f"Excluded buildings ({skipped})", expanded=True):
                st.dataframe(pd.DataFrame(excluded_rows), use_container_width=True, hide_index=True)
        return

    # --- Portfolio-level aggregates ---
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

    # Determine current-period compliance status
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
    total_5yr = sum(
        round(max(portfolio_intensity - lim, 0) * total_sqft / 1000, 1) * ACP_RATE * 5
        for _, lim in non_compliant_periods
    )

    # --- Plain-English summary ---
    if current_compliant:
        st.success(
            f"This portfolio is **compliant** in the current 2025–2029 period under the "
            f"blended emissions standard of {current_limit:.3f} kg CO₂e/sf/yr. "
            f"If emissions remain unchanged, it stays compliant through "
            f"{'all periods' if not non_compliant_periods else f'the {COMPLIANCE_PERIODS[non_compliant_periods[0][0]]} period'}."
        )
    else:
        st.error(
            f"This portfolio is **non-compliant** in the current 2025–2029 period. "
            f"At current emissions, it faces an estimated **${current_fine:,.0f}/year** in ACP fines "
            f"and **${total_5yr:,.0f}** in cumulative payments across "
            f"{len(non_compliant_periods)} non-compliant period(s) if no reductions are made."
        )

    # --- Summary header metrics ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Buildings in portfolio", usable_buildings)
    c2.metric("Total floor area", f"{int(total_sqft):,} sq ft")
    c3.metric("Total emissions", f"{int(total_emissions / 1000):,} metric tons CO₂e")
    c4.metric("Portfolio GHG intensity", f"{portfolio_intensity:.3f} kg/sf/yr")

    st.caption(
        "Portfolio intensity = total GHG emissions ÷ total floor area. "
        "Blended standard = area-weighted average of per-building BERDO limits."
    )

    # --- Vacancy warning ---
    zero_emission = valid[
        (valid["GHG Emissions (kgCO2e)"] == 0) &
        (pd.to_numeric(valid["Site EUI"], errors="coerce").fillna(0) == 0)
    ]
    if not zero_emission.empty:
        addresses = ", ".join(zero_emission["Building Address"].astype(str).tolist())
        st.warning(
            f"⚠️ Possible vacant building(s) detected: **{addresses}**. "
            "BERDO Building Portfolios cannot include vacant buildings — "
            "verify before submitting a portfolio application."
        )

    st.markdown("---")

    # --- Metric cards: first 3 compliance periods ---
    st.markdown("#### Portfolio vs. Blended Standard")
    cols = st.columns(3)
    period_labels = ["2025–2029", "2030–2034", "2035–2039"]
    for i, col in enumerate(cols):
        limit     = blended_limits[i]
        gap       = round(portfolio_intensity - limit, 4)
        compliant = gap <= 0
        excess_tons = 0.0 if compliant else round(gap * total_sqft / 1000, 1)
        fine        = 0.0 if compliant else round(excess_tons * ACP_RATE, 0)
        with col:
            status   = "✅ Compliant" if compliant else "⚠️ Non-compliant"
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

    # --- Compliance chart ---
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
            selected_year if selected_year in PROJECTED_GRID_EF else 2025,
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

    st.plotly_chart(fig, use_container_width=True, key="portfolio_compliance_chart")

    st.caption(
        "Blended standard per BERDO 2.0: area-weighted average of each building's sector limit. "
        "ACP = Alternative Compliance Payment at $234/metric ton CO₂e over the limit. "
        "Not an official City of Boston compliance determination."
    )

    # --- What should I do? expander ---
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
            # Find the worst-gap building for owner-facing guidance
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
estimated **${current_fine:,.0f}/year** in ACP payments. To come into compliance:

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

    # --- Per-building surplus/deficit table (sorted by 2025 gap, worst first) ---
    st.markdown("#### Per-Building Surplus / Deficit")
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
            return "✅" if intensity <= lim else "⚠️"

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

    # --- Excluded buildings ---
    if excluded_rows:
        not_reported = sum(
            1 for r in excluded_rows if "did not report" in r["Exclusion Reason"].lower()
        )
        state_exempt = sum(
            1 for r in excluded_rows if "state-owned" in r["Exclusion Reason"].lower()
        )
        label_parts = [f"Excluded buildings ({skipped})"]
        if state_exempt:
            label_parts.append(f"{state_exempt} state-exempt")
        if not_reported:
            label_parts.append(f"{not_reported} did not report")
        expander_label = " — ".join(label_parts)

        auto_expand = (skipped / total_buildings) > 0.3
        with st.expander(expander_label, expanded=auto_expand):
            st.caption(
                "These buildings are not included in the portfolio calculation. "
                "**State-owned** properties are exempt from BERDO and excluded by default. "
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

    # --- Application deadline callout ---
    st.info(
        "📅 **Portfolio application deadline: September 1, 2026** — to apply the Building "
        "Portfolio compliance pathway to your 2025 emissions reporting. "
        "All buildings must have the same owner and no vacant properties may be included. "
        "Approval from the BERDO Review Board is required."
    )


# ---------------------------------------------------------------------------
# Year-over-year trend chart
# ---------------------------------------------------------------------------
def render_yoy_trend(address, all_years: dict[int, pd.DataFrame]):
    """
    Searches every loaded year for the given address and renders a
    year-over-year trend chart for GHG intensity and Site EUI.
    Returns the prior-year GHG intensity (float | None) for use in the
    compliance chart overlay, and the prior-year label string.
    """
    years_sorted = sorted(y for y in all_years if y != 0)
    if len(years_sorted) < 2:
        return None, None  # Nothing to compare

    import re
    address_clean = re.split(r',', address)[0].strip()

    records = []
    for yr in years_sorted:
        df = all_years[yr]
        matches = df[
            df["Building Address"].astype(str).str.contains(
                address_clean, case=False, na=False
            )
        ]
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

    # --- Delta metrics row ---
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
            delta_color="inverse",   # lower is better
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

    # --- Trend chart ---
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

    st.plotly_chart(fig, use_container_width=True, key="yoy_trend_chart")

    if 2022 in [r["year"] for r in records] and trend_df.loc[trend_df["year"] == 2022, "ghg_intensity"].isna().all():
        st.caption(
            "⚠️ 2022 GHG intensity is not shown — the City of Boston did not publish "
            "GHG emissions totals in that year's dataset."
        )

    prior_ghg   = prior["ghg_intensity"] if pd.notna(prior["ghg_intensity"]) else None
    prior_label = str(int(prior["year"]))
    return prior_ghg, prior_label

# ---------------------------------------------------------------------------
# RETROFIT COST BENCHMARKS
# Source: ASHRAE, RSMeans, NBI New Construction Cost Study, DOE BTO
# Units: national baseline USD per sq ft (low, high) — Boston multiplier applied separately
# Last verified: June 2026
# ---------------------------------------------------------------------------
RETROFIT_COST_PER_SQFT = {
    # scope → (low $/sqft national, high $/sqft national, notes)
    "Lighting (LED retrofit + controls)":               (1.5,   4.0,   "LED fixtures, occupancy sensors, daylight controls"),
    "HVAC (tune-up, controls, VFDs)":                   (3.0,   8.0,   "Controls upgrades, VFDs on pumps/fans, recommissioning"),
    "HVAC (full system replacement)":                   (15.0,  35.0,  "Chiller, AHU, or boiler replacement"),
    "Building envelope (windows + insulation)":         (8.0,   20.0,  "Window replacement, roof/wall insulation"),
    "Electrification — HVAC (air-source heat pump)":    (10.0,  22.0,  "Air-source heat pump — lower cost, suitable for most commercial buildings"),
    "Electrification — HVAC (ground-source heat pump)": (20.0,  45.0,  "Ground-source (geothermal) — higher efficiency, significantly higher upfront cost"),
    "Electrification — water heating":                  (2.0,   6.0,   "Heat pump water heaters replacing gas"),
    "Building-wide deep retrofit (all systems)":        (40.0,  100.0, "Comprehensive envelope + MEP overhaul"),
}

# Boston labor cost multiplier vs. national RSMeans baseline
# Source: RSMeans City Cost Index, Boston MA (2024-2025 avg)
BOSTON_LABOR_MULTIPLIER = 1.25

# ---------------------------------------------------------------------------
# INCENTIVE PROGRAMS
# Each entry: name, amount_str, eligibility_notes, expiration, source_url
# Amounts are per-sqft where applicable; lump-sum where noted.
# Last verified: June 2026 — ALWAYS check before advising a client.
# ---------------------------------------------------------------------------
INCENTIVES = [
    {
        "name": "Mass Save — Commercial HVAC Rebates",
        "type": "Utility rebate",
        "scopes": ["HVAC (tune-up, controls, VFDs)", "HVAC (full system replacement)",
                   "Electrification — HVAC (air-source heat pump)", "Electrification — HVAC (ground-source heat pump)"],
        "amount_str": "$50–$300/ton of cooling capacity; heat pump adders available",
        "eligibility": "MA commercial accounts with Eversource, National Grid, or Unitil",
        "expiration": "Program year 2026 (amounts reset annually in Jan)",
        "stacks_with_ira": True,
        "source": "https://www.masssave.com/saving/business-rebates",
    },
    {
        "name": "Mass Save — Lighting Rebates",
        "type": "Utility rebate",
        "scopes": ["Lighting (LED retrofit + controls)"],
        "amount_str": "$0.05–$0.30/kWh saved (estimated); fixture rebates vary by product",
        "eligibility": "MA commercial accounts",
        "expiration": "Program year 2026 (amounts reset annually)",
        "stacks_with_ira": True,
        "source": "https://www.masssave.com/saving/business-rebates",
    },
    {
        "name": "Mass Save — Deep Energy Retrofit",
        "type": "Utility rebate",
        "scopes": ["Building-wide deep retrofit (all systems)", "Building envelope (windows + insulation)"],
        "amount_str": "Up to $400,000 per project; custom incentive based on modeled savings",
        "eligibility": "MA commercial buildings; requires pre-approval and energy model",
        "expiration": "Program year 2026",
        "stacks_with_ira": True,
        "source": "https://www.masssave.com/saving/large-business",
    },
    {
        "name": "IRA Section 179D — Energy Efficient Commercial Buildings Deduction",
        "type": "Federal tax deduction",
        "scopes": ["Lighting (LED retrofit + controls)", "HVAC (tune-up, controls, VFDs)",
                   "HVAC (full system replacement)", "Building envelope (windows + insulation)",
                   "Electrification — HVAC (air-source heat pump)", "Electrification — HVAC (ground-source heat pump)", "Building-wide deep retrofit (all systems)"],
        "amount_str": "Up to $5.81/sqft (2025, prevailing wage + apprenticeship); $0.58-$1.16/sqft (partial). Construction must BEGIN by June 30, 2026.",
        "eligibility": "For-profit building owners; nonprofits/govts can transfer deduction to designer",
        "expiration": "⚠️ Terminates for construction beginning after June 30, 2026 (One Big Beautiful Bill Act, P.L. 119-21, July 4, 2025). Act now.",
        "stacks_with_ira": True,
        "source": "https://www.energy.gov/eere/buildings/179d-commercial-buildings-energy-efficiency-tax-deduction",
        "ownership_restriction": ["For-profit"],
    },
    {
        "name": "IRA Section 48C — Advanced Energy Project Tax Credit",
        "type": "Federal tax credit",
        "scopes": ["Electrification — HVAC (air-source heat pump)", "Electrification — HVAC (ground-source heat pump)", "Electrification — water heating",
                   "Building-wide deep retrofit (all systems)"],
        "amount_str": "6% base credit (30% with prevailing wage + apprenticeship); capped per project",
        "eligibility": "Manufacturing/industrial sites prioritized; limited allocations via competitive application",
        "expiration": "Allocations ongoing; check IRS portal for remaining capacity",
        "stacks_with_ira": False,
        "source": "https://www.irs.gov/credits-deductions/businesses/advanced-energy-project-credit",
        "ownership_restriction": ["For-profit"],
    },
    {
        "name": "IRA Section 45L — New Energy Efficient Home Credit (multifamily)",
        "type": "Federal tax credit",
        "scopes": ["Electrification — HVAC (air-source heat pump)", "Electrification — HVAC (ground-source heat pump)", "Building-wide deep retrofit (all systems)"],
        "amount_str": "$500–$2,500/unit (Energy Star); $1,000–$5,000/unit (Zero Energy Ready)",
        "eligibility": "Multifamily residential buildings; new construction and substantial rehab",
        "expiration": "Through 2032",
        "stacks_with_ira": True,
        "source": "https://www.irs.gov/credits-deductions/energy-efficient-home-credit",
        "ownership_restriction": ["For-profit"],
        "berdo_types": ["Multifamily Housing"],
    },
    {
        "name": "MassDOER — Clean Energy Grants (nonprofits)",
        "type": "State grant",
        "scopes": ["Electrification — HVAC (air-source heat pump)", "Electrification — HVAC (ground-source heat pump)", "Electrification — water heating",
                   "Building-wide deep retrofit (all systems)"],
        "amount_str": "Up to $250,000; varies by program round",
        "eligibility": "Nonprofits and municipal buildings in MA",
        "expiration": "Check MassCEC for current open rounds",
        "stacks_with_ira": True,
        "source": "https://www.masscec.com/program/clean-energy-results-program",
        "ownership_restriction": ["Nonprofit / Government"],
    },
    {
        "name": "Green Communities — Municipal Energy Grants",
        "type": "State grant",
        "scopes": ["Lighting (LED retrofit + controls)", "HVAC (tune-up, controls, VFDs)",
                   "HVAC (full system replacement)", "Building envelope (windows + insulation)",
                   "Electrification — HVAC (air-source heat pump)", "Electrification — HVAC (ground-source heat pump)", "Building-wide deep retrofit (all systems)"],
        "amount_str": "Up to $1.6M per municipality; formula-based on population",
        "eligibility": "MA municipalities that have achieved Green Community designation",
        "expiration": "Annual grant rounds; check DOER for current cycle",
        "stacks_with_ira": True,
        "source": "https://www.mass.gov/green-communities-designation-grant-program",
        "ownership_restriction": ["Nonprofit / Government"],
    },
]

# Ownership types shown in the UI
OWNERSHIP_TYPES = ["For-profit", "Nonprofit / Government", "Not sure"]


def _fmt_dollars(val):
    """Format a dollar value with commas, no decimals."""
    return f"${val:,.0f}"


def _incentive_applies(incentive, scopes_selected, ownership_type, berdo_category):
    """Return True if this incentive is relevant given user inputs."""
    if not any(s in incentive["scopes"] for s in scopes_selected):
        return False
    if "ownership_restriction" in incentive:
        if ownership_type == "Not sure":
            pass
        elif ownership_type not in incentive["ownership_restriction"]:
            return False
    if "berdo_types" in incentive and berdo_category is not None:
        if berdo_category not in incentive["berdo_types"]:
            return False
    return True


def render_retrofit_tab(prefill: dict = None):
    if prefill is None:
        prefill = {}

    st.write(
        "Estimate rough retrofit costs and applicable incentives for a Boston building. "
        "Figures are order-of-magnitude ranges — get a quote from a licensed energy contractor "
        "before making financial decisions."
    )

    st.info(
        "**Incentive amounts are verified as of June 2026.** "
        "Mass Save program-year amounts reset each January. "
        "IRA figures reflect regulations current as of that date. "
        "Always confirm current amounts at the source links before advising a client."
    )

    st.subheader("Building inputs")

    col1, col2 = st.columns(2)

    with col1:
        default_sqft = int(prefill.get("sqft", 0)) if prefill.get("sqft") else None
        sqft = st.number_input(
            "Gross floor area (sq ft)",
            min_value=1_000,
            max_value=5_000_000,
            value=default_sqft or 50_000,
            step=1_000,
            help="Total building area. Pre-filled from address lookup if available.",
        )
        ownership_type = st.selectbox(
            "Ownership type",
            options=OWNERSHIP_TYPES,
            help="Affects eligibility for IRA tax credits (for-profit only) vs. grants (nonprofits/government).",
        )

    with col2:
        prefill_type = prefill.get("property_type")
        berdo_category = None
        if prefill_type:
            berdo_category = map_property_type(prefill_type)

        type_options = ["— select —"] + sorted(BERDO_STANDARDS.keys())
        default_index = 0
        if berdo_category and berdo_category in type_options:
            default_index = type_options.index(berdo_category)

        selected_type = st.selectbox(
            "Building type (BERDO category)",
            options=type_options,
            index=default_index,
            help="Pre-filled from address lookup if available. Used to filter relevant incentives.",
        )
        if selected_type != "— select —":
            berdo_category = selected_type

        fuel_type = st.selectbox(
            "Primary heating fuel",
            options=["Natural gas", "Fuel oil", "Electric", "Mixed / unknown"],
            help="Affects which electrification incentives are most relevant.",
        )

    st.subheader("Retrofit scope")
    st.caption("Select all work you're considering — costs and incentives will be calculated for each.")

    scopes_selected = []
    scope_cols = st.columns(2)
    scope_items = list(RETROFIT_COST_PER_SQFT.items())
    for i, (scope, (low, high, note)) in enumerate(scope_items):
        col = scope_cols[i % 2]
        with col:
            checked = st.checkbox(f"**{scope}**", help=note, key=f"scope_{i}")
            if checked:
                scopes_selected.append(scope)

    if not scopes_selected:
        st.warning("Select at least one retrofit scope above to see estimates.")
        return

    # ── Building condition qualifier ─────────────────────────────────────────
    st.markdown("---")
    st.subheader("Building condition")
    st.caption(
        "These questions narrow the cost range. Answer as many as you can — "
        "each shifts the estimate toward the low or high end."
    )

    cond_cols = st.columns(2)
    with cond_cols[0]:
        occupied = st.radio(
            "Will the building be occupied during construction?",
            options=["Yes — fully occupied", "Partially occupied / phased", "No — vacant during work"],
            index=1,
            key="cond_occupied",
            help="Occupied buildings require phasing, protection, and off-hours work — adding 15–30% to labor cost.",
        )
        system_age = st.radio(
            "Age of existing mechanical systems (HVAC, plumbing)?",
            options=["Under 15 years — modern, reusable infrastructure",
                     "15–30 years — partial reuse likely",
                     "Over 30 years — full replacement expected"],
            index=1,
            key="cond_age",
            help="Older systems often require full replacement of distribution, controls, and electrical — pushing toward the high end.",
        )
    with cond_cols[1]:
        historic = st.radio(
            "Is the building historic or architecturally constrained?",
            options=["Yes — landmark / historic restrictions apply",
                     "No — standard commercial construction"],
            index=1,
            key="cond_historic",
            help="Historic buildings face restrictions on envelope changes and equipment placement, adding 10–25% to certain scopes.",
        )
        prior_audit = st.radio(
            "Has an energy audit or feasibility study been completed?",
            options=["Yes — ASHRAE Level 2 or equivalent",
                     "No — rough estimate only"],
            index=1,
            key="cond_audit",
            help="A completed audit means fewer unknowns, which typically produces more accurate (often lower) bids.",
        )

    # ── Compute condition adjustment factor ──────────────────────────────────
    # Each answer shifts the midpoint estimate up or down within the range.
    # Factor applied to the low end (pushes it up) and high end (pulled down).
    condition_score = 0  # -2 (favorable) to +4 (unfavorable)

    if "fully occupied" in occupied:
        condition_score += 2
    elif "Partially" in occupied:
        condition_score += 1

    if "Over 30" in system_age:
        condition_score += 2
    elif "15–30" in system_age:
        condition_score += 1

    if "landmark" in historic:
        condition_score += 1

    if "No —" in prior_audit:
        condition_score += 1

    # Map score (0–6) to a position fraction within the range (0.0 = low end, 1.0 = high end)
    position = min(condition_score / 6.0, 1.0)

    condition_label = (
        "Favorable — estimate closer to low end"    if condition_score <= 1 else
        "Moderate — mid-range estimate"             if condition_score <= 3 else
        "Challenging — estimate closer to high end"
    )

    st.markdown("---")
    st.subheader("Estimated retrofit cost")

    # Apply Boston labor multiplier to national benchmarks
    apply_boston = st.toggle(
        "Apply Boston labor cost multiplier (1.25x)",
        value=True,
        key="boston_multiplier_toggle",
        help=(
            "Boston construction labor runs ~25% above the national RSMeans baseline "
            "(RSMeans City Cost Index, 2024-2025). Toggle off to see national benchmark figures."
        ),
    )
    multiplier = BOSTON_LABOR_MULTIPLIER if apply_boston else 1.0

    total_low = 0.0
    total_high = 0.0
    total_adjusted = 0.0
    cost_rows = []

    for scope in scopes_selected:
        low_psf_nat, high_psf_nat, _ = RETROFIT_COST_PER_SQFT[scope]
        low_psf  = low_psf_nat  * multiplier
        high_psf = high_psf_nat * multiplier
        low_total  = low_psf  * sqft
        high_total = high_psf * sqft
        # Condition-adjusted point estimate: interpolate within range
        adj_psf   = low_psf + position * (high_psf - low_psf)
        adj_total = adj_psf * sqft
        total_low      += low_total
        total_high     += high_total
        total_adjusted += adj_total
        cost_rows.append({
            "Scope":             scope,
            "Low ($/sqft)":      f"${low_psf:.2f}",
            "High ($/sqft)":     f"${high_psf:.2f}",
            "Adjusted ($/sqft)": f"${adj_psf:.2f}",
            "Low total":         _fmt_dollars(low_total),
            "Adjusted total":    _fmt_dollars(adj_total),
            "High total":        _fmt_dollars(high_total),
        })

    cost_df = pd.DataFrame(cost_rows)
    st.dataframe(cost_df, use_container_width=True, hide_index=True)

    # Condition badge
    badge_color = (
        "🟢" if condition_score <= 1 else
        "🟡" if condition_score <= 3 else
        "🔴"
    )
    st.caption(
        f"{badge_color} **Building condition: {condition_label}** "
        f"(score {condition_score}/6) — "
        f"Adjusted estimate: **{_fmt_dollars(total_adjusted)}** "
        f"(between low {_fmt_dollars(total_low)} and high {_fmt_dollars(total_high)})"
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Low estimate",      _fmt_dollars(total_low),
              delta="National low × Boston multiplier" if apply_boston else "National baseline low")
    c2.metric("Condition-adjusted", _fmt_dollars(total_adjusted),
              delta=condition_label)
    c3.metric("High estimate",     _fmt_dollars(total_high),
              delta="National high × Boston multiplier" if apply_boston else "National baseline high")

    multiplier_note = (
        f"Boston 1.25x multiplier applied to national RSMeans baselines. "
        if apply_boston else
        "National RSMeans baseline (no Boston multiplier). "
    )
    st.caption(
        multiplier_note +
        "Condition-adjusted estimate interpolates within the range based on your answers above. "
        "Get competitive bids before budgeting."
    )

    st.markdown("---")
    st.subheader("Applicable incentives")

    applicable = [
        inc for inc in INCENTIVES
        if _incentive_applies(inc, scopes_selected, ownership_type, berdo_category)
    ]

    if not applicable:
        st.info(
            "No incentives matched your inputs. "
            "Try adjusting the ownership type or retrofit scope, "
            "or check Mass Save and MassCEC directly for current programs."
        )
    else:
        for inc in applicable:
            with st.expander(f"**{inc['name']}** — {inc['type']}", expanded=True):
                col_a, col_b = st.columns([2, 1])
                with col_a:
                    st.markdown(f"**Amount:** {inc['amount_str']}")
                    st.markdown(f"**Eligible for:** {inc['eligibility']}")
                    if ownership_type == "Not sure" and "ownership_restriction" in inc:
                        st.warning(
                            f"⚠️ This incentive is available to: "
                            f"{', '.join(inc['ownership_restriction'])}. "
                            "Confirm your ownership structure before applying."
                        )
                with col_b:
                    st.markdown(f"**Expires / resets:** {inc['expiration']}")
                    stacks = "✅ Yes" if inc["stacks_with_ira"] else "⚠️ May conflict — verify"
                    st.markdown(f"**Stacks with other IRA credits:** {stacks}")
                    st.markdown(f"[Source / apply →]({inc['source']})")

        if any(i["name"].startswith("IRA Section 179D") for i in applicable):
            ira_179d_low  = 0.58 * sqft
            ira_179d_high = 5.81 * sqft
            st.warning(
                f"⚠️ **179D termination alert:** The One Big Beautiful Bill Act (P.L. 119-21, July 4, 2025) "
                f"terminates 179D for construction beginning after **June 30, 2026**. Act immediately if this applies."
            )
            st.info(
                f"**179D rough estimate for this building ({sqft:,} sqft):** "
                f"{_fmt_dollars(ira_179d_low)} – {_fmt_dollars(ira_179d_high)} "
                f"(at $0.58–$5.81/sqft, 2025 inflation-adjusted; prevailing wage + apprenticeship required for maximum). "
                "Requires a qualified third-party certifier. "
                "Source: DOE energy.gov/eere/buildings/179d"
            )

    st.markdown("---")
    st.subheader("Net cost range after incentives")

    conservative_reduction = total_low * 0.10
    optimistic_reduction   = total_high * 0.40
    adj_reduction          = total_adjusted * 0.20  # midpoint proxy

    net_low      = max(total_low      - optimistic_reduction,   0)
    net_adjusted = max(total_adjusted - adj_reduction,          0)
    net_high     = max(total_high     - conservative_reduction, 0)

    fig = go.Figure()

    fig.add_trace(go.Bar(
        name="Gross cost range",
        x=["Low", "Condition-adjusted", "High"],
        y=[total_low, total_adjusted, total_high],
        marker_color="#3266ad",
        text=[_fmt_dollars(total_low), _fmt_dollars(total_adjusted), _fmt_dollars(total_high)],
        textposition="outside",
    ))

    fig.add_trace(go.Bar(
        name="Est. incentive reduction",
        x=["Low", "Condition-adjusted", "High"],
        y=[optimistic_reduction, adj_reduction, conservative_reduction],
        marker_color="#2ECC71",
        text=[_fmt_dollars(optimistic_reduction), _fmt_dollars(adj_reduction), _fmt_dollars(conservative_reduction)],
        textposition="outside",
    ))

    fig.update_layout(
        barmode="overlay",
        yaxis_title="USD",
        height=350,
        margin=dict(t=30, b=40, l=60, r=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.12)")

    st.plotly_chart(fig, use_container_width=True, key="retrofit_net_cost_chart")

    c1, c2, c3 = st.columns(3)
    c1.metric("Net cost (low)",
              _fmt_dollars(net_low),
              delta=f"-{_fmt_dollars(optimistic_reduction)} incentives (optimistic)")
    c2.metric("Net cost (condition-adjusted)",
              _fmt_dollars(net_adjusted),
              delta=f"-{_fmt_dollars(adj_reduction)} incentives (est.)")
    c3.metric("Net cost (high)",
              _fmt_dollars(net_high),
              delta=f"-{_fmt_dollars(conservative_reduction)} incentives (conservative)")

    st.caption(
        "Incentive reduction estimated at 10–40% of gross cost — a rough proxy for typical "
        "Mass Save rebates + 179D deduction combined for a commercial building in Boston. "
        "Actual savings depend on specific program eligibility, project scope, and tax position. "
        "Consult a licensed energy consultant and tax advisor before budgeting."
    )

    st.markdown("---")
    st.subheader("BERDO fine avoidance context")

    if berdo_category and berdo_category in BERDO_STANDARDS:
        st.write(
            "Compare the retrofit net cost against your estimated BERDO fine exposure "
            "from the Address Lookup tab to get a rough payback picture."
        )
        st.info(
            "💡 **Simple payback rule of thumb:** if your estimated annual BERDO fine "
            "is larger than 10–15% of the net retrofit cost, the investment likely pays "
            "back within 7–10 years from fine avoidance alone — before energy savings."
        )
    else:
        st.info(
            "Select a building type above to see how retrofit costs compare to your BERDO fine exposure. "
            "Or look up your building in the Address Lookup tab first."
        )

    st.markdown("---")
    st.warning(
        "⚠️ **This is a screening tool, not a professional estimate.** "
        "Cost benchmarks are national/regional averages and may not reflect current Boston contractor "
        "pricing. Incentive amounts are verified as of June 2026 but change frequently. "
        "Do not use these figures for contracts, loan applications, or compliance filings. "
        "Engage a licensed energy auditor, MEP engineer, or sustainability consultant for a "
        "project-specific assessment."
    )

    with st.expander("Sources & methodology"):
        st.markdown("""
**Retrofit cost benchmarks**
- RSMeans Construction Cost Data (2024–2025 editions)
- ASHRAE Level 2 Energy Audit benchmarks
- DOE Building Technologies Office: *Adoption of Energy Efficiency Technologies: Commercial Buildings* (2023)
- NBI: *Getting to Zero: Commercial Building Cost Study* (2022)

**Incentive programs**
- Mass Save commercial rebates: masssave.com (verified June 2026; reset annually each January)
- IRA Section 179D: IRS Notice 2023-29, as amended; indexed to inflation annually
- IRA Section 48C: IRS Rev. Proc. 2023-27; competitive allocation rounds
- IRA Section 45L: IRS Notice 2023-65; applies through 2032
- MassDOER / MassCEC grants: masscec.com and mass.gov/doer (program-dependent)
- Green Communities: mass.gov/green-communities (annual grant rounds)

**Incentive stacking**
179D deductions may be combined with utility rebates and most IRA credits. 48C credits may
conflict with other IRA investment credits — verify with a tax advisor for your specific project.
Utility rebates are generally taxable income and reduce the basis eligible for 179D.

**Limitations**
Cost ranges span the 20th–80th percentile of typical project costs. Complex retrofits
(occupied buildings, historic structures, unusual systems) often fall above the high end.
Incentive amounts shown are maximums; actual awards depend on program availability,
contractor certification, and project documentation.
""")

# ---------------------------------------------------------------------------
# INCENTIVE OPTIMIZER — data & logic
# ---------------------------------------------------------------------------

# Incentive stacking order: apply these first to preserve basis for later credits.
# Each entry has a priority rank (1 = apply first), conflict notes, and BERDO period relevance.
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
        "amount_str": "$50–$300/ton cooling capacity; heat pump adders available",
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
        "amount_str": "$0.05–$0.30/kWh saved; fixture rebates vary by product",
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
        "amount_str": "Up to $400,000/project; custom incentive based on modeled savings",
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
        "amount_str": "Up to $5.81/sqft (2025, prevailing wage + apprenticeship); $0.58-$1.16/sqft (partial)",
        "eligibility": "For-profit owners; nonprofits/govts transfer deduction to designer",
        "expiration": "⚠️ Terminates for construction beginning after June 30, 2026 (One Big Beautiful Bill Act, P.L. 119-21). Act now.",
        "conflicts": [],
        "stacks_with": ["Mass Save rebates", "IRA 45L"],
        "berdo_periods": ["2025–29"],
        "ownership": ["For-profit"],
        "ownership_transfer": "Nonprofit / Government",
        "ownership_transfer_note": "Nonprofits and government owners can allocate the deduction to the project designer/engineer.",
        "source": "https://www.energy.gov/eere/buildings/179d-commercial-buildings-energy-efficiency-tax-deduction",
        "checklist": [
            "⚠️ Construction must BEGIN by June 30, 2026 — confirm timeline immediately",
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
        "amount_str": "$500–$2,500/unit (Energy Star); $1,000–$5,000/unit (Zero Energy Ready)",
        "eligibility": "Multifamily residential; new construction and substantial rehab",
        "expiration": "Through 2032",
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
        "amount_str": "6% base (30% with prevailing wage + apprenticeship); capped per project",
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
        "amount_str": "Up to $250,000/project; varies by program round",
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
        "amount_str": "Up to $1.6M/municipality; formula-based on population",
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
FUEL_TYPES_OPT = ["Natural gas", "Fuel oil", "Electric", "Mixed / unknown"]
OWNERSHIP_TYPES_OPT = ["For-profit", "Nonprofit / Government", "Not sure"]


def _opt_incentive_applies(inc, scopes, fuel, ownership, berdo_category):
    """Return True if this incentive matches the user's inputs."""
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
    """Return (low, high) dollar estimate for an incentive."""
    return (
        round(inc["amount_psf_low"] * sqft, 0),
        round(inc["amount_psf_high"] * sqft, 0),
    )


def render_incentive_optimizer_tab(prefill: dict = None):
    """
    Tab 4 — Incentive Optimizer.
    Pre-fills from address lookup session state where available.
    """
    if prefill is None:
        prefill = {}

    st.write(
        "Find the right incentives for your building, in the right order. "
        "This tool matches your building to available programs, ranks them by dollar value, "
        "flags conflicts, and gives you a step-by-step application checklist."
    )
    st.info(
        "**Incentive data verified June 2026.** Mass Save program-year amounts reset each January. "
        "IRA figures reflect current regulations. Always confirm amounts at source links before advising a client."
    )

    # ── Inputs ──────────────────────────────────────────────────────────────
    st.subheader("Building inputs")
    col1, col2 = st.columns(2)

    with col1:
        default_sqft = int(prefill.get("sqft", 50_000)) if prefill.get("sqft") else 50_000
        sqft = st.number_input(
            "Gross floor area (sq ft)",
            min_value=1_000, max_value=5_000_000,
            value=default_sqft, step=1_000,
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
        prefill_cat = prefill.get("berdo_category")
        default_idx = type_options.index(prefill_cat) if prefill_cat in type_options else 0
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

    # ── Fine exposure context (pre-filled from address lookup) ──────────────
    prefill_fine = prefill.get("annual_fine_usd")
    prefill_ghg  = prefill.get("ghg_intensity")
    prefill_addr = prefill.get("address", "")

    if prefill_fine and prefill_fine > 0:
        st.info(
            f"📍 Pre-filled from **{prefill_addr}**: "
            f"estimated annual BERDO fine **${prefill_fine:,.0f}/yr** "
            f"(2025–29 period, at {prefill_ghg:.3f} kg CO₂e/sqft/yr). "
            "Use the payback section below to compare against net retrofit cost."
        )

    # ── Retrofit scope ───────────────────────────────────────────────────────
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

    # ── Match incentives ─────────────────────────────────────────────────────
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

    # ── Dollar estimates ─────────────────────────────────────────────────────
    for inc in matched:
        inc["_est_low"], inc["_est_high"] = _estimate_incentive_value(inc, sqft)

    total_incentive_low  = sum(i["_est_low"]  for i in matched)
    total_incentive_high = sum(i["_est_high"] for i in matched)

    # Gross retrofit cost
    total_cost_low  = sum(RETROFIT_COST_PER_SQFT[s][0] * sqft for s in scopes_selected)
    total_cost_high = sum(RETROFIT_COST_PER_SQFT[s][1] * sqft for s in scopes_selected)

    # Net cost (incentives capped at gross cost)
    net_low  = max(total_cost_low  - total_incentive_high, 0)
    net_high = max(total_cost_high - total_incentive_low,  0)

    st.markdown("---")

    # ── Summary metric cards ─────────────────────────────────────────────────
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
        "Gross cost benchmarks from RSMeans / ASHRAE / DOE BTO (2024–2026)."
    )

    # ── Ranked incentive table ────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Incentives ranked by estimated value")

    ranked = sorted(matched, key=lambda x: x["_est_high"], reverse=True)

    rank_rows = []
    for inc in ranked:
        conflict_flag = "⚠️ " + "; ".join(inc["conflicts"]) if inc["conflicts"] else "✅ None"
        rank_rows.append({
            "Priority": f"Step {inc['priority']}",
            "Program": inc["short"],
            "Type": inc["type"],
            "Est. value (low)": f"${inc['_est_low']:,.0f}",
            "Est. value (high)": f"${inc['_est_high']:,.0f}",
            "Applies in": ", ".join(inc["berdo_periods"][:2]),
            "Conflicts": conflict_flag,
        })

    st.dataframe(pd.DataFrame(rank_rows), use_container_width=True, hide_index=True)

    # ── Stacking strategy ─────────────────────────────────────────────────────
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
                        f"⚠️ **Potential conflicts:** {', '.join(inc['conflicts'])}. "
                        "Verify with a tax advisor before claiming both."
                    )
                else:
                    stacks = ", ".join(inc["stacks_with"]) if inc["stacks_with"] else "No conflicts identified"
                    st.success(f"✅ **Stacks cleanly with:** {stacks}")
                if ownership == "Not sure" and "For-profit" in inc["ownership"] and "Nonprofit / Government" not in inc["ownership"]:
                    st.warning("⚠️ This incentive is available to for-profit owners only. Confirm your ownership structure.")
                if "ownership_transfer_note" in inc:
                    st.info(f"ℹ️ {inc['ownership_transfer_note']}")
            with col_b:
                st.markdown(f"**Expires:** {inc['expiration']}")
                st.markdown(f"[Apply / learn more →]({inc['source']})")

    # ── Application checklist ─────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Application checklist")
    st.caption("Complete these steps for each matched program.")

    for inc in steps:
        with st.expander(f"**{inc['name']}** — checklist", expanded=False):
            for step in inc["checklist"]:
                st.checkbox(step, key=f"chk_{inc['short']}_{step[:20]}")
            st.markdown(f"[Source / apply →]({inc['source']})")

    # ── Cash flow & payback ───────────────────────────────────────────────────
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
        col_pb1, col_pb2 = st.columns(2)

        payback_low  = round(net_low  / annual_fine, 1) if net_low  > 0 else 0.0
        payback_high = round(net_high / annual_fine, 1) if net_high > 0 else 0.0

        col_pb1.metric(
            "Payback — fine avoidance only (low net cost)",
            f"{payback_low} yrs" if payback_low > 0 else "< 1 yr",
        )
        col_pb2.metric(
            "Payback — fine avoidance only (high net cost)",
            f"{payback_high} yrs" if payback_high > 0 else "< 1 yr",
        )

        # Cumulative cash flow chart
        years = list(range(0, 16))
        cumulative_low  = [-net_low  + annual_fine * y for y in years]
        cumulative_high = [-net_high + annual_fine * y for y in years]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=years, y=cumulative_low,
            name="Optimistic (low net cost)",
            mode="lines", line=dict(color="#1D9E75", width=2),
            fill="tozeroy", fillcolor="rgba(29,158,117,0.08)",
        ))
        fig.add_trace(go.Scatter(
            x=years, y=cumulative_high,
            name="Conservative (high net cost)",
            mode="lines", line=dict(color="#3266ad", width=2, dash="dash"),
        ))
        fig.add_hline(y=0, line_width=1, line_dash="dot",
                      line_color="rgba(128,128,128,0.5)",
                      annotation_text="Break-even", annotation_position="right")
        fig.update_layout(
            xaxis_title="Years from retrofit",
            yaxis_title="Cumulative cash flow (USD)",
            height=320,
            margin=dict(t=30, b=40, l=60, r=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(gridcolor="rgba(128,128,128,0.12)")
        st.plotly_chart(fig, use_container_width=True, key="opt_cashflow_chart")

        st.caption(
            "Cash flow assumes annual fine avoidance is the only return — "
            "energy cost savings (typically $0.50–$2.00/sqft/yr) would improve payback further. "
            "Not an investment projection. Consult a financial advisor."
        )

        if payback_low <= 10:
            st.success(
                f"✅ At the low net cost estimate, this retrofit pays back in "
                f"**{payback_low} years** from BERDO fine avoidance alone — "
                "generally considered favourable for commercial real estate."
            )
        else:
            st.info(
                f"At the low net cost estimate, payback is {payback_low} years from fine avoidance alone. "
                "Energy cost savings and carbon credit value (if applicable) would shorten this further."
            )

    # ── Phasing by BERDO period ───────────────────────────────────────────────
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

    # ── Disclaimer ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.warning(
        "⚠️ **Screening tool only — not professional financial or tax advice.** "
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
- IRA Section 45L: IRS Notice 2023-65; applies through 2032
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


# ---------------------------------------------------------------------------
# App layout
# ---------------------------------------------------------------------------
all_years = load_all_years()
years_sorted = sorted(y for y in all_years if y != 0)
multi_year_mode = len(years_sorted) >= 2

# --- Sidebar: year selector ---
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
    show_yoy = st.sidebar.toggle("Show year-over-year comparison", value=True)
else:
    selected_year = years_sorted[0] if years_sorted else 0
    df_full = all_years[selected_year]
    show_yoy = False

# --- Sidebar: grid decarbonization scenario ---
st.sidebar.header("Grid decarbonization scenario")
show_grid_decarb = st.sidebar.toggle(
    "Show grid decarbonization scenario",
    value=False,
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
    base_ef = PROJECTED_GRID_EF.get(selected_year, PROJECTED_GRID_EF[2025])
    st.sidebar.caption(
        f"Base year grid EF ({selected_year}): **{base_ef} kg/MWh** "
        f"(Appendix B). Projected EF at 2050: **{PROJECTED_GRID_EF[2050]} kg/MWh** "
        f"({round((1 - PROJECTED_GRID_EF[2050] / base_ef) * 100)}% cleaner)."
    )
else:
    elec_share = None

# --- Page header ---
st.title("BERDO Building Priority & Incentive Tool")
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

tab_address, tab_portfolio, tab_retrofit, tab_optimizer = st.tabs([
    "Address Lookup", "Owner Portfolio", "Retrofit Estimator", "Incentive Optimizer"
])

# ---------------------------------------------------------------------------
# Tab 1 — single address lookup (unchanged behaviour)
# ---------------------------------------------------------------------------
with tab_address:
    address_input = st.text_input(
        "Enter building address",
        placeholder="Example: 1047 Commonwealth Ave"
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

            st.subheader("Priority Result")

            display_cols = [
                "Building Address", "Property Owner Name", "Property Type",
                "Site EUI", "GHG Intensity (kgCO2e/sqft)",
                "Compliance Status", "Priority Level", "Priority Score", "Reasons",
            ]
            st.dataframe(result[display_cols], use_container_width=True, hide_index=True)

            top = result.iloc[0]
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Priority Level", top["Priority Level"])
            with col2:
                st.metric("Priority Score", int(top["Priority Score"]))

            st.write("**Reasons:**", top["Reasons"])

            with st.expander("What do these fields mean?"):
                st.markdown("""
**Compliance Status**
- **Submitted**: The building owner reported energy and emissions data to the City of Boston for the previous calendar year.
- **Not submitted**: No data was reported. Buildings required to report under BERDO face fines of $300/day (buildings over 35,000 sq ft) for missing the May 15 annual deadline.

**Site EUI (Energy Use Intensity)**
- Measures how much energy a building uses per square foot per year (kBtu/sq ft/yr). A higher EUI means the building uses more energy relative to its size. Missing EUI typically means the building did not submit complete energy data.

**GHG Intensity (kg CO₂e/sq ft/yr)**
- The building's greenhouse gas emissions per square foot per year, calculated from reported fuel and electricity use. This is the value compared against BERDO emissions limits to determine compliance.

**Priority Score**
- A screening score (0–8) used to flag buildings that may need outreach, reporting support, or retrofit planning. Higher scores indicate more urgent attention.
""")

            st.markdown("---")

            # --- Year-over-year trend (multi-year mode only) ---
            prior_ghg, prior_label = None, None
            if show_yoy and multi_year_mode:
                prior_ghg, prior_label = render_yoy_trend(address_input, all_years)
                st.markdown("---")

            # --- Grid decarbonization projection ---
            projected_intensities = None
            if show_grid_decarb and elec_share is not None:
                ghg_val = top.get("GHG Intensity (kgCO2e/sqft)")
                if pd.notna(ghg_val) and ghg_val > 0:
                    projected_intensities = project_ghg_intensities(
                        ghg_intensity=float(ghg_val),
                        elec_share=elec_share,
                        base_year=selected_year if selected_year in PROJECTED_GRID_EF else 2025,
                    )

            render_compliance_section(
                top,
                prior_year_ghg_intensity=prior_ghg,
                prior_year_label=prior_label,
                projected_intensities=projected_intensities,
                base_year=selected_year if selected_year in PROJECTED_GRID_EF else 2025,
            )

            # ── Store prefill data for Incentive Optimizer tab ──
            ghg_val = top.get("GHG Intensity (kgCO2e/sqft)")
            sqft_val = top.get("Gross Floor Area")
            raw_type = top.get("Property Type")
            berdo_cat = map_property_type(raw_type)

            opt_prefill = {
                "address":       top.get("Building Address", address_input),
                "sqft":          int(sqft_val) if pd.notna(sqft_val) and sqft_val > 0 else 50_000,
                "berdo_category": berdo_cat,
            }

            # Calculate fine for 2025–29 period if possible
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
            st.info(
                "💡 Building data saved — open the **Incentive Optimizer** tab "
                "to see matched funding programs for this building."
            )

# ---------------------------------------------------------------------------
# Tab 2 — owner portfolio lookup
# ---------------------------------------------------------------------------
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
                "Compliance Status", "Priority Level",
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
                
# ---------------------------------------------------------------------------
# Tab 3 — Retrofit Cost & Incentive Estimator
# ---------------------------------------------------------------------------
with tab_retrofit:
    prefill = {}
    render_retrofit_tab(prefill=prefill)

# ---------------------------------------------------------------------------
# Tab 4 — Incentive Optimizer
# ---------------------------------------------------------------------------
with tab_optimizer:
    opt_prefill = st.session_state.get("optimizer_prefill", {})
    render_incentive_optimizer_tab(prefill=opt_prefill)
