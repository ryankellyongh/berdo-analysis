"""
Address Lookup tab.
"""
import pandas as pd
import re
import plotly.graph_objects as go
import streamlit as st
from berdo.regulations import (
    BERDO_LINKS,
    BERDO_STANDARDS,
    COMPLIANCE_PERIODS,
    PATHWAYS_VERIFIED,
)
from berdo.emissions import (
    acp_exposure,
    current_period_acp,
    limits_with_city_standard,
    period_status_rows,
    _is_parking,
    blend_limits_by_area,
    building_elec_share,
    building_limits,
    calculate_compliance_gap,
    coverage_for,
    coverage_label,
    effective_grid_ef,
    fmt_share,
    get_compliance_pathways,
    government_status,
    map_property_type,
    period_covered,
    project_ghg_intensities,
    reporting_status_label,
)
from berdo.data import (
    campus_context,
    find_building_in_year,
    get_fuel_breakdown,
    lookup_building_priority,
)
from berdo.pdf_export import (
    build_building_summary_pdf,
)


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


#Mixed-use editor

def _bl_default_limits(top):
    """Default (largest-use) limits for a lookup row, or None."""
    return building_limits(top.get("Property Type"), top.get("All Property Types"))["limits"]


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

def _compliance_cards(gaps, cov, proj_gap_for_period):
    """Status, ACP, and gap cards for the first three periods."""
    #Metric cards (first 3 periods)
    cols = st.columns(3)
    period_labels = ["2025–2029", "2030–2034", "2035–2039"]
    for i, col in enumerate(cols):
        g = gaps[i]
        with col:
            if not g["covered"]:
                st.metric(
                    label=f"{period_labels[i]}  |  {coverage_label(cov, i)}",
                    value="$0",
                    delta=(f"for reference: {'+' if g['gap'] > 0 else '−'}{abs(g['gap']):.2f} kg "
                           f"{'over' if g['gap'] > 0 else 'under'}"),
                    delta_color="off",
                )
                continue
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


def _compliance_chart(gaps, ghg_intensity, projected_intensities, prior_year_ghg_intensity, prior_year_label, sqft, berdo_category, cov):
    """Limits vs. intensity chart, with grid scenario and prior-year overlays."""
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
        name="Annual ACP, no reductions (USD)",
        mode="lines+markers",
        yaxis="y2",
        line=dict(color="#BA7517", width=1.5, dash="dot"),
        marker=dict(size=6),
        visible="legendonly",
    ))

    if projected_intensities is not None:
        proj_fines = [
            calculate_compliance_gap(pi, sqft, berdo_category, limits=limits, coverage=cov)[i]["annual_fine_usd"]
            for i, pi in enumerate(projected_intensities)
        ]
        fig.add_trace(go.Scatter(
            x=COMPLIANCE_PERIODS,
            y=proj_fines,
            name="Annual ACP, grid scenario (USD)",
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
            title="Annual ACP (USD)",
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


def _compliance_exposure_summary(gaps, projected_intensities, proj_gap_for_period):
    """Cumulative ACP exposure under the conservative and grid scenarios."""
    #Fine exposure summary
    exposure = acp_exposure(gaps)
    if exposure["any"]:
        msg = (
            f"**Conservative scenario:** if no emissions reductions are made, this building "
            f"faces an estimated USD {exposure['total_5yr']:,.0f} in cumulative ACP payments across "
            f"{exposure['periods_over']} five-year non-compliant period(s) through 2050 "
            f"(annual ACP × 5 years per period)"
        )
        if exposure["annual_2050"] is not None:
            msg += (
                f" From 2050 onward, an additional estimated USD "
                f"{exposure['annual_2050']:,.0f}/year applies indefinitely if the "
                f"building remains non-compliant."
            )
        if projected_intensities is not None:
            proj_exposure = acp_exposure(proj_gap_for_period)
            if proj_exposure["any"]:
                msg += (
                    f"\n\n**Grid decarbonization scenario:** estimated USD {proj_exposure['total_5yr']:,.0f} "
                    f"across {proj_exposure['periods_over']} five-year non-compliant period(s) through 2050."
                )
            else:
                msg += "\n\n**Grid decarbonization scenario:** building achieves compliance in all periods from grid cleaning alone."
        st.info(msg)


def _compliance_caption(base_year, projected_intensities):
    """Method caption and the About this tool expander."""
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


def render_compliance_section(
    row,
    prior_year_ghg_intensity=None,
    prior_year_label=None,
    projected_intensities=None,
    base_year=2025,
    limits=None,
    limits_label=None,
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
        st.warning("Floor area is missing, so ACP exposure can't be calculated.")
        return

    if berdo_category is None and limits is None:
        st.warning(
            f"Property type **{raw_type}** could not be mapped to a BERDO "
            "emissions category. Add it to the PROPERTY_TYPE_MAP to enable "
            "gap calculations."
        )
        return

    cov = coverage_for(row.get("First Compliance Year"), row.get("Compliance Status"),
                       row.get("Property Owner Name"))
    gaps = calculate_compliance_gap(ghg_intensity, sqft, berdo_category, limits=limits, coverage=cov)
    category_label = (limits_label or "Blended Emissions Standard") if limits is not None else berdo_category

    #Projected gaps (for grid decarb scenario metric cards)
    if projected_intensities is not None:
        proj_gaps = [
            calculate_compliance_gap(pi, sqft, berdo_category, limits=limits, coverage=cov)
            for pi in projected_intensities
        ]
        #proj_gaps[i] is a list of 6 period gaps for the projected intensity at period i
        #We only need the gap for each period against its own limit, i.e. proj_gaps[i][i]
        proj_gap_for_period = [proj_gaps[i][i] for i in range(len(COMPLIANCE_PERIODS))]
    else:
        proj_gap_for_period = None

    if cov["known"] and cov["applies_from"] > 2025:
        st.caption(
            f"This building isn't subject to an emissions limit until {cov['applies_from']} "
            "emissions. Earlier periods are shown for reference, with no ACP."
        )
    elif not cov["known"] and not cov["gov"]:
        st.caption(
            "The first compliance year isn't reported, so the tool doesn't estimate ACP. "
            "Gaps are shown for reference."
        )
    if cov["city"]:
        st.caption("City building: the ordinance's daily fines don't apply; emissions standards and "
                   "the ACP option still do.")

    st.caption(
        f"Current intensity: **{ghg_intensity:.3f} kg CO₂e/sf/yr** · "
        f"Floor area: **{int(sqft):,} sq ft** · "
        f"BERDO category: **{category_label}**"
    )

    _compliance_cards(gaps, cov, proj_gap_for_period)
    _compliance_chart(gaps, ghg_intensity, projected_intensities, prior_year_ghg_intensity, prior_year_label, sqft, berdo_category, cov)
    _compliance_exposure_summary(gaps, projected_intensities, proj_gap_for_period)
    _compliance_caption(base_year, projected_intensities)



#Year-over-year trend chart

def render_yoy_trend(building, all_years: dict[int, pd.DataFrame]):
    """
    Finds the same building in every loaded year, by BERDO ID first (see
    find_building_in_year), and renders a year-over-year trend chart for GHG
    intensity and Site EUI. `building` is the selected lookup row.
    Returns the prior-year GHG intensity (float | None) for use in the
    compliance chart overlay, and the prior-year label string.
    """
    years_sorted = sorted(y for y in all_years if y != 0)
    if len(years_sorted) < 2:
        return None, None  #Nothing to compare

    records = []
    for yr in years_sorted:
        found = find_building_in_year(
            all_years[yr],
            berdo_id=building.get("BERDO ID"),
            parcel_id=building.get("Tax Parcel ID"),
            address=building.get("Building Address"),
        )
        if found is None:
            continue
        row, matched_by, dup = found
        ghg = pd.to_numeric(row.get("ghg_intensity_kgco2e_sqft"), errors="coerce")
        eui = pd.to_numeric(row.get("site_eui"), errors="coerce")
        records.append({"year": yr, "ghg_intensity": ghg, "site_eui": eui,
                        "matched_by": matched_by, "duplicates": dup,
                        "address_that_year": row.get("Building Address")})

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

    #How each year was matched, so users can judge the trend
    by_method = {}
    for r in records:
        by_method.setdefault(r["matched_by"], []).append(str(int(r["year"])))
    st.caption("Years linked by " + "; ".join(
        f"{method}: {', '.join(yrs)}" for method, yrs in by_method.items()) + ".")
    weaker = [r for r in records if r["matched_by"] != "BERDO ID"]
    if weaker:
        st.caption(
            "Years not linked by BERDO ID are matched by tax parcel or exact address, "
            "which is less certain. Check that the floor area and use look consistent."
        )
    dups = [str(int(r["year"])) for r in records if r["duplicates"]]
    if dups:
        st.caption(
            f"More than one record for this building in {', '.join(dups)}; the record with "
            "emissions data (or the larger floor area) is shown."
        )
    renamed = {r["address_that_year"] for r in records if r["address_that_year"]}
    if len(renamed) > 1:
        st.caption("The address is written differently across years: " +
                   "; ".join(sorted(str(a) for a in renamed)) + ".")

    prior_ghg   = prior["ghg_intensity"] if pd.notna(prior["ghg_intensity"]) else None
    prior_label = str(int(prior["year"]))
    return prior_ghg, prior_label

#Tab 1: single address lookup (unchanged behaviour)

def _lookup_building_result(page, result, address_input):
    """Building picker, results table, status metrics, notes, and campus panel."""
    top = None
    #Building result
    result["Site EUI"] = result["Site EUI"].round(1)
    result["GHG Intensity (kgCO2e/sqft)"] = (
        pd.to_numeric(result["GHG Intensity (kgCO2e/sqft)"], errors="coerce")
        .round(3)
    )

    st.subheader("Building Result")
    if page.selected_year and page.selected_year >= 2026:
        st.caption(
            f"Reporting year {page.selected_year}: energy use from calendar year {page.selected_year - 1}. "
                    "Statuses marked (City) are the City's own emissions compliance results. The City "
                    "describes this disclosure as provisional: buildings with extensions or under review "
                    "have no energy or emissions data yet, and an update is planned after October 15, 2026."
        )
    elif page.selected_year:
        st.caption(
            f"Reporting year {page.selected_year}: energy use from calendar year {page.selected_year - 1}. "
                    "BERDO's first emissions compliance year is 2025 energy use, reported in 2026, so "
                    "flags based on earlier data are a preview."
        )

    display_cols = [
        "Building Address", "Property Owner Name", "Property Type",
        "Site EUI", "GHG Intensity (kgCO2e/sqft)",
        "Data Status", "BERDO Status", "Est. ACP (2025–29)", "Notes",
    ]
    st.dataframe(result[display_cols], use_container_width=True, hide_index=True)

    if len(result) > 1:
        def _label(r):
            owner = r.get("Property Owner Name")
            owner = owner if isinstance(owner, str) and owner.strip() else "owner not reported"
            bid = r.get("BERDO ID") or "no BERDO ID"
            return f"{r.get('Building Address')} · {owner} · BERDO ID {bid}"
        _labels = [_label(r) for _, r in result.iterrows()]
        _pick = st.selectbox(
            f"{len(result)} buildings match this search. Choose one:",
            options=list(range(len(result))),
            format_func=lambda i: _labels[i],
            key=f"lookup_pick_{address_input}",
        )
        top = result.iloc[_pick]
    else:
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

    _city_note = top.get("City Note")
    if isinstance(_city_note, str) and _city_note.strip():
        st.caption(f"**City note:** {_city_note.strip()}")

    if top.get("Campus ID"):
        _ctx = campus_context(page.df_full, top.get("Campus ID"))
        if _ctx:
            _s = _ctx["summary"]
            _row_i = pd.to_numeric(top.get("GHG Intensity (kgCO2e/sqft)"), errors="coerce")
            _msg = (f"**Part of campus {_ctx['campus_id']}** with "
                            f"{len(_ctx['members'])} buildings in this year's data. The City says "
                            "campus rows may not reflect a building's full energy use, so this "
                            "building's emissions intensity, and any flag based on it, is less certain.")
            if _s and _s["intensity"] is not None:
                _msg += (f" Campus totals: {_s['gfa']:,.0f} sq ft, "
                                 f"{_s['ghg'] / 1000:,.0f} metric tons CO₂e, "
                                 f"{_s['intensity']:.2f} kg CO₂e/sf/yr")
                if pd.notna(_row_i):
                    _msg += f" (this building's row: {_row_i:.2f})"
                _msg += "."
            st.info(_msg)
            with st.expander(f"Buildings on campus {_ctx['campus_id']}"):
                _m = _ctx["members"]
                st.dataframe(pd.DataFrame({
                    "Address": _m["Building Address"],
                    "BERDO ID": _m.get("berdo_id"),
                    "Floor area (sq ft)": pd.to_numeric(_m["gross_floor_area"], errors="coerce").round(0),
                    "GHG intensity (kg/sf/yr)": pd.to_numeric(
                        _m["ghg_intensity_kgco2e_sqft"], errors="coerce").round(2),
                    "Property type": _m["property_type"],
                }), hide_index=True, use_container_width=True)
                st.caption("Rows as reported in the City's disclosure. Campus totals come "
                                   "from the campus summary row in the same dataset.")
    return bldg_share, bldg_share_note, top


def _lookup_fuel_breakdown(page, top, bldg_share, bldg_share_note):
    """Energy use by fuel and the field definitions."""
    #Fuel breakdown
    fuel_breakdown = get_fuel_breakdown(top)
    primary_fuel   = top.get("Primary Fuel", "Mixed / unknown")
    if fuel_breakdown:
        n_cols = min(len(fuel_breakdown), 5)  #cap at 5 cols
        st.markdown(f"**Energy usage by fuel ({page.selected_year} reported)**")
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
- **Campus buildings**: Some buildings are reported as part of a campus. The City notes these rows may not reflect the full building's energy use; the tool flags them and shows the campus totals.
- **State / Federal**: The City's data marks the building as owned by a state or federal agency. This tool shows its emissions for reference only, because BERDO's treatment of these buildings is unconfirmed.

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


def _lookup_trend(page, top):
    """Year-over-year trend, linked by BERDO ID."""
    #Year-over-year trend (multi-year mode only)
    prior_ghg, prior_label = None, None
    if page.show_yoy and page.multi_year_mode:
        prior_ghg, prior_label = render_yoy_trend(top, page.all_years)
        st.markdown("---")
    return prior_ghg, prior_label


def _lookup_compliance(page, bldg_share, top, prior_ghg, prior_label):
    """Grid scenario, building uses and limits, and the compliance gap analysis."""
    #Grid decarbonization projection 
    projected_intensities = None
    if page.show_grid_decarb and page.elec_share is not None:
        year_txt = f"{page.selected_year} data" if page.selected_year else "reported data"
        if page.use_reported_share and bldg_share is not None:
            share_for_grid = bldg_share
            st.caption(
                f"Grid scenario uses this building's reported electricity share: "
                        f"**{fmt_share(bldg_share)}** ({year_txt})."
            )
        else:
            share_for_grid = page.elec_share
            why = ("the reported-share option is off in the sidebar"
                   if not page.use_reported_share
                   else "this year's data has no electricity breakdown for this building")
            st.caption(
                f"Grid scenario uses the sidebar estimate of **{fmt_share(page.elec_share)}** "
                        f"because {why}."
            )
        ghg_val = top.get("GHG Intensity (kgCO2e/sqft)")
        if pd.notna(ghg_val) and ghg_val > 0:
            projected_intensities = project_ghg_intensities(
                ghg_intensity=float(ghg_val),
                elec_share=share_for_grid,
                base_year=(page.selected_year - 1) if page.selected_year else 2025,
            )

    _gov = government_status(top.get("Compliance Status"))
    _cov = coverage_for(top.get("First Compliance Year"), top.get("Compliance Status"),
                        top.get("Property Owner Name"))
    if _gov:
        st.info(
            f"**{_gov} building.** The City's data marks this as a {_gov.lower()} building. "
                    "A city ordinance generally can't require state or federal agencies to comply "
                    "the way it requires private owners, and the City hasn't published how BERDO "
                    "applies to them. The analysis below compares its emissions to the BERDO limit "
                    "for reference only. It is not a finding of noncompliance, and ACP estimates "
                    "may not apply."
        )

    use_mix_limits = render_use_mix_editor(top)
    _limits_source = "blend" if use_mix_limits is not None else None
    #When the City publishes a building's applicable standard (it already reflects
    #blended standards), use it as the 2025-29 limit; later periods use the default.
    _city_limits = limits_with_city_standard(_bl_default_limits(top), top.get("Official Standard"))
    if use_mix_limits is None and _city_limits:
        use_mix_limits = _city_limits
        _limits_source = "official"
        _off_std = _city_limits[0]
        st.caption(f"2025–29 limit uses the City's applicable standard for this building "
                           f"({float(_off_std):.2f} kg/sf/yr). Later periods use the default standards.")
    _city_status = top.get("City Emissions Status")
    if isinstance(_city_status, str) and _city_status:
        st.info(f"**City emissions compliance status (2025 energy use):** {_city_status}")

    render_compliance_section(
        top,
        prior_year_ghg_intensity=prior_ghg,
        prior_year_label=prior_label,
        projected_intensities=projected_intensities,
        base_year=(page.selected_year - 1) if page.selected_year else 2025,
        limits=use_mix_limits,
        limits_label=("City's applicable standard" if _limits_source == "official" else None),
    )
    return _cov, _gov, _limits_source, projected_intensities, use_mix_limits


def _lookup_pathways(page, top, bldg_share):
    """BERDO compliance pathways for this building."""
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
        _n_owned = int((page.df_full["Property Owner Name"].astype(str)
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
    return _bl_ctx, _ghg_ctx, _pathways_ctx, _sqft_ctx


def _lookup_pdf(page, use_mix_limits, _bl_ctx, _ghg_ctx, _sqft_ctx, _cov, projected_intensities, top, bldg_share, _gov, _limits_source, address_input, _pathways_ctx):
    """The one-page PDF summary and its download button."""
    #One-page PDF summary for a board, lender, or consultant
    _pdf_limits = use_mix_limits or _bl_ctx["limits"]
    _periods = []
    if _pdf_limits and pd.notna(_ghg_ctx) and pd.notna(_sqft_ctx) and _sqft_ctx > 0:
        _periods = period_status_rows(_ghg_ctx, _sqft_ctx, _pdf_limits, _cov, projected_intensities)

    def _num(v, fmt):
        v = pd.to_numeric(v, errors="coerce")
        return fmt.format(v) if pd.notna(v) else "Not reported"

    _facts = [
        ("BERDO category", _bl_ctx["label"] or "Not mappable", "Calculated"),
        ("Reported property type", top.get("Property Type") if isinstance(top.get("Property Type"), str)
         and top.get("Property Type").strip() else "Not reported", "Reported"),
        ("Gross floor area", _num(top.get("Gross Floor Area"), "{:,.0f} sq ft"), "Reported"),
        ("Total GHG emissions", _num(pd.to_numeric(top.get("GHG Emissions (kgCO2e)"),
                                                   errors="coerce") / 1000,
                                     "{:,.0f} metric tons CO2e"), "Reported (City estimate)"),
        ("GHG intensity", _num(_ghg_ctx, "{:.2f} kg CO2e/sf/yr"), "Calculated"),
        ("Electricity share of emissions",
         fmt_share(bldg_share), "Calculated"),
        ("Site EUI", _num(top.get("Site EUI"), "{:.1f} kBtu/sf/yr"),
         "Calculated" if top.get("Site EUI Calculated") else "Reported"),
        ("Annual reporting", reporting_status_label(top.get("Compliance Status")), "Reported"),
        ("Screening result", top.get("BERDO Status"), "Calculated"),
        ("Est. annual ACP (2025–29)",
         f"Not estimated ({_gov.lower()} record)" if _gov else
         "Not applicable (not yet covered)" if (_cov["known"] and not period_covered(_cov, 0)) else
         "Not estimated (coverage year not reported)" if not _cov["known"] else
         (f"USD {top['Est. ACP (2025–29)']:,.0f}" if top["Est. ACP (2025–29)"] else "USD 0"),
         "Estimated"),
    ]
    _limit_basis = (
        "The 2025–29 limit is the City's applicable standard for this building; later "
                "periods use the default standards."
        if _limits_source == "official" else
        "Limits shown use the Blended Emissions Standard, an option the owner may adopt "
                "(estimated by this tool from floor area by use)."
        if use_mix_limits else
        f"Limits shown are the default for the building's largest use ({_bl_ctx['label']})."
    )
    if _cov["known"] and not period_covered(_cov, 0):
        _limit_basis = (f"No emissions limit applies until {_cov['applies_from']} emissions; "
                                "earlier periods are shown for reference only. " + _limit_basis)
    if _cov["city"]:
        _limit_basis += " City building: the ordinance's daily fines don't apply."
    if _gov:
        _limit_basis = (f"Reference only: the City's data marks this as a {_gov.lower()} "
                                "building, and BERDO's treatment of it is unconfirmed. " + _limit_basis)
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
    _cn = top.get("City Note")
    if isinstance(_cn, str) and _cn.strip():
        _cn = _cn.strip()
        _notes.append("City note: " + (_cn if len(_cn) <= 240 else _cn[:237] + "..."))

    try:
        _pdf_bytes = build_building_summary_pdf({
            "address":     top.get("Building Address", address_input),
            "owner":       top.get("Property Owner Name"),
            "data_year":   (f"{page.selected_year} reporting year ({page.selected_year - 1} energy use)"
                            if page.selected_year else None),
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
            file_name=f"BERDO_summary_{_slug}_{page.selected_year or 'data'}.pdf",
            mime="application/pdf",
            help="Status, limits by period, screening notes, and compliance options "
                         "on one page, for a board, lender, or consultant. Reflects the "
                         "settings currently shown (blended standard, grid scenario).",
        )
    except ImportError:
        st.caption(
            "PDF export needs the reportlab package. Add `reportlab` to requirements.txt."
        )


def _lookup_prefill(page, top, address_input, use_mix_limits, _cov, bldg_share):
    """Pass this building to the Retrofit & Incentives and Emissions Planner tabs."""
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
        "building_key":  f"{top.get('BERDO ID') or ''}|{top.get('Building Address', address_input)}|{page.selected_year}",
        "limits":        use_mix_limits,
        "coverage":      _cov,
        "elec_share":    bldg_share,
        "elec_share_year": page.selected_year or None,
    }

    #Calculate fine for 2025–29 period if possible
    if (
        pd.notna(ghg_val) and ghg_val > 0
        and pd.notna(sqft_val) and sqft_val > 0
        and (use_mix_limits is not None or berdo_cat in BERDO_STANDARDS)
    ):
        limit_2025 = (use_mix_limits or BERDO_STANDARDS[berdo_cat])[0]
        _acp = current_period_acp(ghg_val, sqft_val, limit_2025, _cov, top.get("City Emissions Status"))
        if _acp is not None:
            opt_prefill["annual_fine_usd"] = _acp
            opt_prefill["ghg_intensity"] = float(ghg_val)

    st.session_state["optimizer_prefill"] = opt_prefill

    #Also pre-fill the Emissions Planner tab
    ghg_emissions_raw = top.get("GHG Emissions (kgCO2e)")
    planner_prefill = {
        "address":          opt_prefill.get("address", address_input),
        "sqft":             opt_prefill.get("sqft", 50_000),
        "berdo_category":   berdo_cat,
        "limits":           use_mix_limits,
        "coverage":         _cov,
        "elec_share":       bldg_share,
        "elec_share_year":  page.selected_year or None,
        "data_year":        (page.selected_year - 1) if page.selected_year else None,
        #Full-precision intensity from reported totals, so the planner's editable
        #field reproduces the reported baseline exactly
        "ghg_intensity":    (float(ghg_emissions_raw) / float(sqft_val)
                             if pd.notna(ghg_emissions_raw) and ghg_emissions_raw > 0
                             and pd.notna(sqft_val) and sqft_val > 0
                             else float(ghg_val) if pd.notna(ghg_val) and ghg_val > 0 else 0.0),
        "ghg_emissions_kg": float(ghg_emissions_raw) if pd.notna(ghg_emissions_raw) and ghg_emissions_raw > 0 else None,
        #Identifies this building and data year; the planner pre-fills its fields
        #only when this changes, so user edits aren't overwritten on reruns
        "building_key":     f"{top.get('BERDO ID') or ''}|{top.get('Building Address', address_input)}|{page.selected_year}",
    }
    st.session_state["planner_prefill"] = planner_prefill

    st.info(
        "Building data saved: open the **Retrofit & Incentives** or **Emissions Planner** tabs "
                "to model funding programs and compliance trajectory for this building."
    )


def render_address_lookup_tab(page):
    """Address Lookup tab: search, building result, trend, compliance, pathways, PDF, and pre-fill."""
    address_input = st.text_input(
        "Enter building address",
        placeholder="Example: 20 Gillette Park"
    )

    if not address_input:
        return

    result = lookup_building_priority(page.df_full, address_input)

    if result is None:
        st.warning("No matching address found in the dataset.")
        return

    bldg_share, bldg_share_note, top = _lookup_building_result(page, result, address_input)
    _lookup_fuel_breakdown(page, top, bldg_share, bldg_share_note)
    prior_ghg, prior_label = _lookup_trend(page, top)
    _cov, _gov, _limits_source, projected_intensities, use_mix_limits = _lookup_compliance(page, bldg_share, top, prior_ghg, prior_label)
    _bl_ctx, _ghg_ctx, _pathways_ctx, _sqft_ctx = _lookup_pathways(page, top, bldg_share)
    _lookup_pdf(page, use_mix_limits, _bl_ctx, _ghg_ctx, _sqft_ctx, _cov, projected_intensities, top, bldg_share, _gov, _limits_source, address_input, _pathways_ctx)
    _lookup_prefill(page, top, address_input, use_mix_limits, _cov, bldg_share)
