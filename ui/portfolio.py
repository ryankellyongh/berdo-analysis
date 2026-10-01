"""
Owner Portfolio tab.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from berdo.regulations import (
    ACP_RATE,
    COMPLIANCE_PERIODS,
)
from berdo.emissions import (
    _fmt_deadline,
    building_elec_share,
    building_limits,
    calculate_blended_standard,
    coverage_for,
    fmt_share,
    government_status,
    period_covered,
    project_ghg_intensities,
)
from ui.common import (
    _EndTab,
)


#Portfolio compliance section

def _portfolio_classify(buildings_df):
    """Split buildings into those included and those excluded, with reasons."""
    #Classify buildings: valid vs excluded (with reason)
    
    excluded_rows = []
    valid_rows = []
    for _, row in buildings_df.iterrows():
        ghg   = pd.to_numeric(row.get("GHG Emissions (kgCO2e)"), errors="coerce")
        sqft  = pd.to_numeric(row.get("Gross Floor Area"), errors="coerce")
        missing_ghg  = pd.isna(ghg)
        missing_sqft = pd.isna(sqft) or sqft <= 0

        status = str(row.get("Compliance Status", "")).strip().lower()
        gov = government_status(status)
        if gov:
            excluded_rows.append({
                "Building Address":  row.get("Building Address"),
                "Property Type":     row.get("Property Type"),
                "Compliance Status": row.get("Compliance Status"),
                "Exclusion Reason":  f"{gov} record: BERDO treatment unconfirmed, so left out of the portfolio",
            })
            continue
        _pcov = coverage_for(row.get("First Compliance Year"), status, row.get("Property Owner Name"))
        if not period_covered(_pcov, 0):
            excluded_rows.append({
                "Building Address":  row.get("Building Address"),
                "Property Type":     row.get("Property Type"),
                "Compliance Status": row.get("Compliance Status"),
                "Exclusion Reason":  (f"Not yet covered: no emissions limit until {_pcov['applies_from']} emissions"
                                      if _pcov["known"] else "First compliance year not reported"),
            })
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
        _n_gov = sum(1 for r in excluded_rows if " record: berdo treatment" in r["Exclusion Reason"].lower())
        if _n_gov == len(excluded_rows) and _n_gov > 0:
            st.info(
                f"All {_n_gov} buildings for this owner are state or federal records in the City's "
                "data. BERDO's treatment of these buildings is unconfirmed, so this tool doesn't "
                "calculate portfolio compliance for them. Look up individual buildings in the "
                "Address Lookup tab to see their emissions for reference."
            )
        else:
            st.error("No buildings with sufficient data to calculate portfolio compliance.")
        
        #Still show excluded table so user knows what's missing
        
        if excluded_rows:
            with st.expander(f"Excluded buildings ({skipped})", expanded=True):
                st.dataframe(pd.DataFrame(excluded_rows), use_container_width=True, hide_index=True)
        raise _EndTab
    return excluded_rows, skipped, total_buildings, usable_buildings, valid


def _portfolio_totals(valid):
    """Portfolio intensity, blended standard, and the plain-English summary."""
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
        raise _EndTab

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
    return blended_limits, current_compliant, current_fine, current_limit, portfolio_intensity, total_emissions, total_sqft, valid


def _portfolio_metrics(usable_buildings, total_sqft, total_emissions, portfolio_intensity, valid, blended_limits):
    """Headline metrics, vacancy warning, and period cards."""
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


def _portfolio_chart(blended_limits, portfolio_intensity, elec_share, use_reported_share, total_emissions, valid, selected_year, total_sqft):
    """Blended limit vs. portfolio intensity chart."""
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
            (selected_year - 1) if selected_year else 2025,
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


def _portfolio_guidance(current_compliant, current_limit, valid, current_fine):
    """Guidance for owners and policymakers."""
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


def _portfolio_breakdown(valid):
    """Each building's surplus or deficit against its own limit."""
    #Per-building surplus/deficit table (sorted by 2025 gap, worst first)
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


def _portfolio_exclusions(excluded_rows, skipped, total_buildings):
    """Excluded buildings and the application deadline note."""
    #Excluded buildings
    if excluded_rows:
        not_reported = sum(
            1 for r in excluded_rows if "did not report" in r["Exclusion Reason"].lower()
        )
        state_exempt = sum(
            1 for r in excluded_rows if " record: berdo treatment" in r["Exclusion Reason"].lower()
        )
        label_parts = [f"Excluded buildings ({skipped})"]
        if state_exempt:
            label_parts.append(f"{state_exempt} state/federal")
        if not_reported:
            label_parts.append(f"{not_reported} did not report")
        expander_label = " · ".join(label_parts)

        auto_expand = (skipped / total_buildings) > 0.3
        with st.expander(expander_label, expanded=auto_expand):
            st.caption(
                "These buildings are not included in the portfolio calculation. "
                "**State and federal** buildings are left out because their BERDO treatment is unconfirmed. "
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


def render_portfolio_section(buildings_df, selected_year, elec_share, all_years, show_yoy,
                             use_reported_share=True):
    """
    Renders BERDO compliance analysis for a multi-building owner portfolio.
    Shows portfolio-level blended standard, aggregate gap, fine exposure,
    and a per-building surplus/deficit breakdown table.
    """
    st.subheader("Portfolio Compliance Analysis")

    try:
        excluded_rows, skipped, total_buildings, usable_buildings, valid = _portfolio_classify(buildings_df)
        blended_limits, current_compliant, current_fine, current_limit, portfolio_intensity, total_emissions, total_sqft, valid = _portfolio_totals(valid)
        _portfolio_metrics(usable_buildings, total_sqft, total_emissions, portfolio_intensity, valid, blended_limits)
        _portfolio_chart(blended_limits, portfolio_intensity, elec_share, use_reported_share, total_emissions, valid, selected_year, total_sqft)
        _portfolio_guidance(current_compliant, current_limit, valid, current_fine)
        _portfolio_breakdown(valid)
        _portfolio_exclusions(excluded_rows, skipped, total_buildings)
    except _EndTab:
        return
