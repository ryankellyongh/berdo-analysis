"""
Emissions Planner tab.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from berdo.regulations import (
    BERDO_STANDARDS,
    COMPLIANCE_PERIODS,
    FUEL_UNIT_OPTIONS,
)
from berdo.emissions import (
    coverage_from_prefill,
    effective_grid_ef,
    fmt_share,
    fuel_to_kbtu,
    limits_for_category,
    period_covered,
    planner_model,
    resolve_elec_share,
)
from berdo.retrofit import (
    first_year_reduction_kg,
)
from ui.common import (
    _EndTab,
    apply_prefill_once,
)


#EMISSIONS PLANNER, Tab 5

def _planner_inputs(prefill):
    """Floor area, building type, and GHG intensity, pre-filled from Address Lookup."""
    #Building inputs
    st.subheader("Building inputs")

    #Pre-fill the fields only when a different building (or data year) is looked up.
    #This is the only place planner fields are set, so edits survive reruns.
    prefill_addr_key = prefill.get("address", "")
    apply_prefill_once("ep_last_injected_key", prefill.get("building_key") or prefill_addr_key, {
        "ep_sqft":  int(prefill["sqft"]) if prefill.get("sqft") else None,
        "ep_btype": prefill.get("berdo_category") or None,
        "ep_ghg":   float(prefill["ghg_intensity"]) if prefill.get("ghg_intensity") else None,
    })

    col1, col2, col3 = st.columns(3)
    with col1:
        sqft = st.number_input(
            "Gross floor area (sq ft)",
            min_value=1, max_value=50_000_000,
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
            min_value=0.0, max_value=1000.0,
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
        raise _EndTab
    return berdo_category, ghg_intensity, prefill_addr_key, sqft


def _planner_projects():
    """The table where users add, edit, and remove planned projects."""
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
    def calc_reduction_kg(fuel, unit, amount, year=2025):
        """First-year reduction, shown in the project table. The projection recalculates
        electricity savings each year from the MWh saved (see reduction_in_year)."""
        return round(first_year_reduction_kg(fuel, unit, amount, year), 2)

    projects_to_remove = []
    projects = st.session_state["ep_projects"]

    if projects:
        header_cols = st.columns([3, 1.5, 2, 1.5, 2, 1.5, 1])
        header_cols[0].caption("Project name")
        header_cols[1].caption("Year")
        header_cols[2].caption("Fuel type")
        header_cols[3].caption("Amount")
        header_cols[4].caption("Unit")
        header_cols[5].caption("First-year reduction (kg CO₂e)")
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
                fuel_list = list(FUEL_UNIT_OPTIONS)
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
                unit_list = FUEL_UNIT_OPTIONS.get(proj["fuel"], ["kBtu"])
                curr_unit = proj.get("unit", unit_list[0])
                u_idx = unit_list.index(curr_unit) if curr_unit in unit_list else 0
                proj["unit"] = st.selectbox(
                    "Unit", options=unit_list, index=u_idx,
                    key=f"ep_proj_unit_{idx}", label_visibility="collapsed"
                )
            with row[5]:
                proj["reduction_kg"] = calc_reduction_kg(proj["fuel"], proj["unit"], proj["amount"], proj["year"])
                proj["elec_mwh"] = (fuel_to_kbtu(proj["fuel"], proj["unit"], proj["amount"]) / 3412.0
                                    if proj["fuel"] == "Electricity" else 0.0)
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


def _planner_projection(berdo_category, show_grid_decarb, prefill, elec_share, use_reported_share, ghg_intensity, sqft, prefill_addr_key):
    """Baseline, grid scenario, and project reductions year by year, as table rows."""
    #Grid decarbonization, read from sidebar
     
    st.markdown("---")
    st.subheader("Emissions Compliance Projection")

    if berdo_category not in BERDO_STANDARDS:
        st.warning("Select a valid building type above to see the compliance projection.")
        raise _EndTab

    apply_grid = show_grid_decarb
    elec_share_val, elec_share_src = resolve_elec_share(prefill, elec_share, use_reported_share)

    limits = limits_for_category(berdo_category, prefill)

    _ep_base = int(prefill.get("data_year") or 2025)
    if apply_grid:
        base_ef = effective_grid_ef(_ep_base)
        ef_2050 = effective_grid_ef(2050)
        st.caption(
            f"Grid decarbonization is ON (sidebar). "
            f"Electricity share: {fmt_share(elec_share_val)} ({elec_share_src}). "
            f"Base year grid EF ({_ep_base}): {base_ef:.0f} kg/MWh → {ef_2050:.0f} kg/MWh at 2050 "
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
    #The editable fields are the baseline, so user edits always take effect.
    baseline_intensity = ghg_intensity
    total_emissions_kg = baseline_intensity * sqft
    _rep_i = prefill.get("ghg_intensity")
    _rep_sqft = prefill.get("sqft")
    if _rep_i and prefill_addr_key:
        if abs(ghg_intensity - _rep_i) < 5e-4 and _rep_sqft and int(sqft) == int(_rep_sqft):
            st.caption(
                f"Baseline: **{total_emissions_kg:,.0f} kg CO₂e/yr**, from the building's reported "
                f"BERDO data ({baseline_intensity:.3f} kg CO₂e/sqft/yr). Edit the fields above to "
                "model a different starting point."
            )
        else:
            st.caption(
                f"Baseline: **{total_emissions_kg:,.0f} kg CO₂e/yr**, from the values entered above. "
                f"The building's reported intensity is {_rep_i:.3f} kg CO₂e/sqft/yr on "
                f"{int(_rep_sqft or 0):,} sq ft."
            )

    #All planner numbers come from planner_model (tested in tests/test_planner.py)
    _ep_cov = coverage_from_prefill(prefill)
    _covered = [period_covered(_ep_cov, i) for i in range(len(COMPLIANCE_PERIODS))]
    _active_projects = [p for p in st.session_state.get("ep_projects", []) if p.get("reduction_kg", 0) > 0]
    _m = planner_model(baseline_intensity, sqft, limits, _active_projects, _covered,
                       apply_grid=apply_grid, elec_share=elec_share_val, base_year=_ep_base)
    grid_emissions_kg    = _m["grid_emissions_kg"]
    period_reductions_kg = _m["period_reductions_kg"]
    reduction_in_year    = _m["reduction_in_year"]
    _elec_capped_years   = _m["elec_capped_years"]
    has_projects = _m["has_projects"]
    has_grid     = apply_grid

    #Build two stacked tables
    emissions_rows = []
    fines_rows     = []

    if not all(_covered):
        st.caption(
            (f"This building isn't subject to an emissions limit until {_ep_cov['applies_from']} "
             "emissions, so earlier periods show no ACP."
             if _ep_cov["known"] else
             f"{_ep_cov['reason']}: ACP isn't estimated for this building.")
        )

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

        fine_baseline = _m["fines"]["baseline"][i]
        fine_grid     = _m["fines"]["grid"][i]
        fine_proj     = _m["fines"]["projects"][i]
        fine_combined = _m["fines"]["combined"][i]

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
    return _active_projects, _elec_capped_years, _m, apply_grid, elec_share_val, emissions_rows, fines_rows, grid_emissions_kg, has_grid, has_projects, limits, period_reductions_kg, reduction_in_year, total_emissions_kg


def _planner_tables(has_projects, emissions_rows, _elec_capped_years, elec_share_val, _active_projects, apply_grid, fines_rows):
    """The emissions and ACP tables."""
    #Table 1: Emissions
    st.markdown("#### Projected emissions vs. BERDO limit (kg CO₂e/yr)")
    if has_projects:
        st.caption("Project columns show the average year in each period: a project counts only "
                   "from its implementation year, so a 2033 project counts for 2 of the 5 years in 2030–34.")
    st.dataframe(pd.DataFrame(emissions_rows), use_container_width=True, hide_index=True)

    if _elec_capped_years:
        st.warning(
            f"Electricity savings entered exceed this building's estimated electricity emissions "
            f"(at {elec_share_val:.0%} of emissions) in {min(_elec_capped_years)}–{max(_elec_capped_years)}, "
            "so they were capped. Check the amount entered or the electricity share."
        )
    if any(p.get("elec_mwh") for p in _active_projects):
        st.caption(
            "Electricity savings are recalculated each year from the MWh saved and the same grid "
            "factor the baseline uses" + (", so they shrink as the grid gets cleaner." if apply_grid
                                          else " (today's grid, since the grid scenario is off).")
        )

    #Table 2: ACP fines
    st.markdown("#### Estimated ACP fine: annual, per period")
    st.caption("Alternative Compliance Payment at $234/metric ton CO₂e over limit.")
    st.dataframe(pd.DataFrame(fines_rows), use_container_width=True, hide_index=True)

    st.caption(
        "ACP = $234/metric ton CO₂e over limit. "
        "Not an official City of Boston BERDO compliance determination."
    )


def _planner_summary(_m, has_projects, has_grid, reduction_in_year, total_emissions_kg, limits, sqft):
    """Cumulative ACP metrics and compliant-period counts."""
    #Summary metrics
    baseline_fines_cumul = _m["cumulative"]["baseline"]
    proj_fines_cumul     = _m["cumulative"]["projects"]
    grid_fines_cumul     = _m["cumulative"]["grid"]
    combined_fines_cumul = _m["cumulative"]["combined"]

    st.markdown("---")
    num_cols = 1 + (1 if has_projects else 0) + (1 if has_grid else 0) + (1 if has_projects and has_grid else 0)
    s_cols = st.columns(max(num_cols, 2))

    current_annual_fine = _m["current_annual_fine"]
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
            total_reduction_mt = reduction_in_year(2050) / 1000   #all projects in place
            gap_mt = max(total_emissions_kg - limits[0] * sqft, 0) / 1000
            if gap_mt > 0:
                pct = total_reduction_mt / gap_mt * 100
                st.caption(
                    f"Once in place, your projects reduce ~{total_reduction_mt:,.0f} MT/yr, about {pct:.1f}% of the "
                    f"{gap_mt:,.0f} MT the building is over its 2025–29 cap. "
                    + ("Nowhere near enough to affect compliance." if pct < 5 else
                       "Still short of compliance." if pct < 100 else
                       "Enough to reach compliance this period.")
                )

    _cp = _m["compliant_periods"]
    compliant_periods_baseline  = _cp["baseline"]
    compliant_periods_proj      = _cp["projects"] if has_projects else None
    compliant_periods_grid      = _cp["grid"] if has_grid else None
    compliant_periods_combined  = _cp["combined"] if (has_projects and has_grid) else None

    _all_compliant = [v for v in [compliant_periods_baseline, compliant_periods_proj, compliant_periods_grid, compliant_periods_combined] if v is not None]
    st.caption(
        f"Compliant periods: baseline {compliant_periods_baseline}"
        + (f" | with projects {compliant_periods_proj}" if compliant_periods_proj is not None else "")
        + (f" | grid decarb only {compliant_periods_grid}" if compliant_periods_grid is not None else "")
        + (f" | grid + projects {compliant_periods_combined}" if compliant_periods_combined is not None else "")
        + f" (out of {len(COMPLIANCE_PERIODS)} periods)."
    )


def _planner_chart(limits, sqft, total_emissions_kg, period_reductions_kg, grid_emissions_kg, has_projects, has_grid):
    """Emissions vs. limit chart and the method explanation."""
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
the BERDO emissions factors) counts from its implementation year onward, never earlier.
Fossil fuel savings are fixed per unit of fuel. Electricity savings are recalculated each year
from the MWh saved and the same grid factor used for the baseline, so with the grid scenario on
they shrink as the grid gets cleaner, and they can never exceed the building's electricity emissions. BERDO
compliance is annual, so each five-year period is modeled year by year: a project implemented
in 2033 reduces emissions in 2033 and 2034, and the 2030–34 row shows the average of those five
years. Cumulative ACP with projects is summed year by year rather than multiplying one year by five.

**ACP fines**

Alternative Compliance Payments are assessed at \$234 per metric ton of CO₂e above the 
building's emissions limit. The table shows annual fines; the summary metrics multiply by 
5 years per period for cumulative exposure.

Sources: BERDO ordinance Table 1 and ACP rate; ENERGY STAR Portfolio Manager
BERDO Emissions Factors List (September 18, 2026) for fuel factors; BERDO Policies &
Procedures v5, Appendix B, for projected grid factors.
Not an official City of Boston BERDO compliance determination.
""")


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

    try:
        berdo_category, ghg_intensity, prefill_addr_key, sqft = _planner_inputs(prefill)
        _planner_projects()
        _active_projects, _elec_capped_years, _m, apply_grid, elec_share_val, emissions_rows, fines_rows, grid_emissions_kg, has_grid, has_projects, limits, period_reductions_kg, reduction_in_year, total_emissions_kg = _planner_projection(berdo_category, show_grid_decarb, prefill, elec_share, use_reported_share, ghg_intensity, sqft, prefill_addr_key)
        _planner_tables(has_projects, emissions_rows, _elec_capped_years, elec_share_val, _active_projects, apply_grid, fines_rows)
        _planner_summary(_m, has_projects, has_grid, reduction_in_year, total_emissions_kg, limits, sqft)
        _planner_chart(limits, sqft, total_emissions_kg, period_reductions_kg, grid_emissions_kg, has_projects, has_grid)
    except _EndTab:
        return
