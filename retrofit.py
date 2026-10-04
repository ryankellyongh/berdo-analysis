"""
Retrofit & Incentives tab.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from berdo.regulations import (
    BERDO_STANDARDS,
    COMPLIANCE_PERIODS,
    FUEL_TYPES_OPT,
    FUEL_UNIT_OPTIONS,
    INCENTIVE_STACK,
    OWNERSHIP_TYPES_OPT,
    REC_CONNECTOR_DEADLINE,
    REC_CONNECTOR_PRICES_VALID_THROUGH,
    REC_DEFAULT_PRICE,
    RETROFIT_COST_PER_SQFT,
)
from berdo.emissions import (
    _opt_incentive_applies,
    coverage_from_prefill,
    fmt_share,
    limits_for_category,
    rec_connector_price,
    rec_pathway,
    resolve_elec_share,
)
from berdo.retrofit import (
    PAYBACK_CAP_YEARS,
    acp_schedule,
    acp_totals,
    estimate_incentives,
    first_year_reduction_kg,
    headline_payback,
    net_retrofit_cost,
    payback_estimates,
    planned_project_impact,
    rec_break_even_price,
    rec_inputs,
    retrofit_cost_estimate,
    retrofit_recommendation,
)
from ui.common import (
    _EndTab,
    _fmt_dollars,
    apply_prefill_once,
)


def _retrofit_inputs(prefill):
    """Building inputs, pre-fill from Address Lookup, and retrofit scope selection."""
    #Inputs
    
    #Inject prefill into session state when a new address lookup arrives.
    #We detect a "fresh" prefill by comparing the prefill address to the
    #last address we injected: if different, overwrite widget state.
    
    apply_prefill_once("opt_last_injected_key",
                       prefill.get("building_key") or prefill.get("address", ""), {
        "opt_sqft":  int(prefill["sqft"]) if prefill.get("sqft") else None,
        "opt_btype": prefill.get("berdo_category") if prefill.get("berdo_category") in BERDO_STANDARDS else None,
        "opt_fuel":  prefill.get("primary_fuel") if prefill.get("primary_fuel") in FUEL_TYPES_OPT else None,
    })

    st.subheader("Building inputs")
    col1, col2 = st.columns(2)

    with col1:
        sqft = st.number_input(
            "Gross floor area (sq ft)",
            min_value=1, max_value=50_000_000,
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
        raise _EndTab
    return berdo_category, fuel, ownership, prefill_fine, scopes_selected, sqft


def _retrofit_cost_estimate(scopes_selected, sqft):
    """Condition-adjusted cost ranges for the selected scopes."""
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
    condition_label = ("Audit complete: estimate toward low end" if has_audit
                       else "No audit: mid-range estimate (actual scope may run higher)")

    apply_boston = st.checkbox(
        "Apply Boston labor cost multiplier (1.25x)",
        value=True, key="opt_boston_multiplier",
        help=(
            "Boston construction labor runs ~25% above the national RSMeans baseline "
            "(RSMeans City Cost Index, 2024–2025). Uncheck to see national benchmark figures."
        ),
    )
    est = retrofit_cost_estimate(scopes_selected, sqft, has_audit, apply_boston)
    cost_rows = [{
        "Scope":             r["scope"],
        "Low ($/sqft)":      f"${r['low_psf']:.2f}",
        "Adjusted ($/sqft)": f"${r['adj_psf']:.2f}",
        "High ($/sqft)":     f"${r['high_psf']:.2f}",
        "Low total":         _fmt_dollars(r["low_total"]),
        "Adjusted total":    _fmt_dollars(r["adj_total"]),
        "High total":        _fmt_dollars(r["high_total"]),
    } for r in est["rows"]]
    total_cost_low, total_cost_high = est["total_low"], est["total_high"]
    total_cost_adjusted = est["total_adjusted"]

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
    return total_cost_high, total_cost_low


def _retrofit_planned_project(sqft, prefill, berdo_category):
    """Whether a planned energy reduction closes the 2025-29 gap."""
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
            options=list(FUEL_UNIT_OPTIONS),
            key="proj_fuel_type",
            help="Select the fuel your retrofit will reduce or eliminate.",
        )
    with proj_cols[1]:
        units = FUEL_UNIT_OPTIONS.get(proj_fuel, ["kBtu", "MMBtu"])
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
        proj_emission_reduction_kg  = first_year_reduction_kg(proj_fuel, proj_unit, proj_amount)  #kg CO₂e/yr
        proj_emission_reduction_mt  = proj_emission_reduction_kg / 1000                          #metric tons
        proj_intensity_reduction    = proj_emission_reduction_kg / sqft                           #kg/sqft/yr

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
            limit_2025 = limits_for_category(berdo_category, prefill)[0]
            impact = planned_project_impact(proj_emission_reduction_kg, sqft, prefill_ghg_proj, limit_2025)
            new_intensity = impact["new_intensity"]
            gap_before, gap_after = impact["gap_before"], impact["gap_after"]

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
                pct_closed, remaining_mt = impact["pct_closed"], impact["remaining_mt"]
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


def _retrofit_incentives(scopes_selected, fuel, ownership, berdo_category, sqft, total_cost_low, total_cost_high, prefill):
    """Matched incentives: headline, summary, ranking, stacking order, and checklist."""
    #Match incentives
    matched = [
        inc for inc in INCENTIVE_STACK
        if _opt_incentive_applies(inc, scopes_selected, fuel, ownership, berdo_category)
    ]

    if not matched:
        st.info(
            "No incentives matched your inputs. "
            "Try adjusting ownership type, fuel, or scope, "
            "or check masssave.com and mass.gov directly."
        )
        raise _EndTab

    #Dollar estimates
    matched, total_incentive_low, total_incentive_high = estimate_incentives(matched, sqft)

    #Gross retrofit cost. Reuse the Boston-multiplier + condition-adjusted totals
    #Computed in the "Estimated retrofit cost" section above, so the cost shown
    #There and the net cost here are consistent. (Previously this recomputed raw
    #National baselines, understating cost whenever the Boston multiplier applied.)
    #total_cost_low / total_cost_high already set above.

    #Net cost (incentives capped at gross cost)
    net_low, net_high = net_retrofit_cost(total_cost_low, total_cost_high,
                                          total_incentive_low, total_incentive_high)

    #Headline summary card
    st.markdown("---")

    #Build the headline sentence
    incentive_str   = _fmt_dollars(total_incentive_high).replace("$", "USD ")
    net_low_display = "fully covered by incentives" if net_low == 0 else _fmt_dollars(net_low).replace("$", "USD ")
    prefill_fine_val = prefill.get("annual_fine_usd", 0) or 0
    _kind, _years = headline_payback(net_low, prefill_fine_val, sqft)
    if _kind == "years":
        payback_str = f", with an estimated {_years}-year payback including energy savings"
    elif _kind == "energy_driven":
        payback_str = ". Energy savings are the primary return driver for a building this size"
    elif _kind == "covered":
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
    return matched, net_high, net_low


def _retrofit_payback(prefill_fine, sqft, net_low, net_high):
    """Payback from avoided ACP and energy savings, with the cash flow chart."""
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
        pb = payback_estimates(net_low, net_high, annual_fine, energy_savings_annual)
        total_annual_benefit = pb["total_annual_benefit"]

        #Payback metrics: cap at 50 years; beyond that avoided ACP is the wrong frame
        PAYBACK_CAP = PAYBACK_CAP_YEARS
        payback_low_fine_only, payback_high_fine_only = pb["low_acp_only"], pb["high_acp_only"]
        payback_low_combined, payback_high_combined = pb["low_combined"], pb["high_combined"]

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
        years = pb["years"]
        cumulative_low_fine, cumulative_high_fine = pb["cash_low_acp"], pb["cash_high_acp"]
        cumulative_low_total, cumulative_high_total = pb["cash_low_total"], pb["cash_high_total"]

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
    return annual_fine


def _retrofit_three_paths(page, annual_fine, berdo_category, prefill, sqft, net_low, net_high):
    """Retrofit vs. RECs vs. ACP, with a recommendation and the fine escalation table."""
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
    
        #ACP across each compliance period, if emissions stay flat
        limits = limits_for_category(berdo_category, prefill)
        prefill_ghg_val = prefill.get("ghg_intensity")
        period_fines = (acp_schedule(prefill_ghg_val, sqft, limits, coverage_from_prefill(prefill))
                        if prefill_ghg_val else [])
        _totals = acp_totals(annual_fine, period_fines, net_low)
        fine_5yr = _totals["fine_5yr"]

        #Decision matrix
        st.markdown("Cost comparison. Retrofit now vs. pay escalating fines")
        st.caption(
            "BERDO fines grow every five years as the emissions limit tightens. "
            "The comparison below uses cumulative fines through 2050, not just the current period."
        )

        cumulative_fine_all = _totals["cumulative_all"]
        cum_fine_10yr = _totals["cumulative_10yr"]

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
        _rec_share, _rec_share_src = resolve_elec_share(prefill, page.elec_share, page.use_reported_share)
        _rec_gap_kg, _rec_elec_kg = rec_inputs(prefill_ghg_val, sqft, limits[0], _rec_share)
        #RECs needed doesn't depend on price, so size the purchase first, then price it
        _rec_sizing = rec_pathway(_rec_gap_kg, _rec_elec_kg, 2025, 0.0)
        _recs_needed = _rec_sizing["recs_needed"] if _rec_sizing else 0
        with rc1:
            _price_source = st.radio(
                "REC price",
                ["City REC Connector (tiered)", "Enter my own price"],
                key="opt_rec_price_source",
                help="REC Connector prices are all-inclusive and depend on quantity. "
                     "Choose your own price to model a broker quote.",
            )
            if _price_source == "Enter my own price":
                rec_price = st.number_input(
                    "Price (USD/REC)", min_value=0.0, max_value=200.0,
                    value=REC_DEFAULT_PRICE, step=1.0, key="opt_rec_price",
                )
            else:
                rec_price = rec_connector_price(_recs_needed)
                st.caption(
                    f"USD {rec_price:.0f}/REC for about {_recs_needed:,.0f} RECs "
                    f"(Connector tier, valid through {REC_CONNECTOR_PRICES_VALID_THROUGH})."
                )
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
                    f"break-even falls to {rec_break_even_price(2050):.2f} USD/REC by 2050 "
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
                f"For 2025 compliance: buy through the City's REC Connector Program (Green Energy "
                f"Consumers Alliance) by **{REC_CONNECTOR_DEADLINE}**, or through an independent broker. "
                "Either way, RECs must be generated between January 1, 2024 and June 30, 2026, and "
                "retired by December 31, 2026. Only non-emitting MA Class I RECs count (solar, wind, "
                "small hydro, geothermal); biomass and landfill methane do not. Connector prices are from "
                "berdo.greenenergyconsumers.org; the Connector retires RECs by December 15 and "
                "proof must reach the City by December 31."
            )
        else:
            rec = None

        #Recommendation
        st.markdown("Recommendation")

        #Key insight: fines escalate, so compare retrofit against cumulative fines
        #not just one period. Also compute crossover period.
        crossover_period = _totals["crossover_period"]
        _rec_choice = retrofit_recommendation(net_low, fine_5yr, cum_fine_10yr, cumulative_fine_all)

        net_low_str      = "fully covered by incentives" if net_low == 0 else _fmt_dollars(net_low).replace("$", "USD ")
        fine_5yr_str     = _fmt_dollars(fine_5yr).replace("$", "USD ")
        cum_str          = _fmt_dollars(cumulative_fine_all).replace("$", "USD ")
        cum_10yr_str     = _fmt_dollars(cum_fine_10yr).replace("$", "USD ")

        if _rec_choice == "retrofit_now":
            #Retrofit cost is zero or cheaper than even one period of fines
            st.success(
                f"**Retrofit now: clear financial case.** The net retrofit cost "
                f"({net_low_str}) is less than or equal to one period of BERDO fines "
                f"({fine_5yr_str} for 2025–29 alone). "
                "And fines only grow from here. Each period the limit tightens and the "
                "gap widens. Retrofitting eliminates all future fine exposure permanently."
            )
        elif _rec_choice == "retrofit_soon":
            #Retrofit pays back within 2 periods (10 years) of escalating fines
            st.success(
                f"**Retrofit soon: strong case once fines escalate.** "
                f"The net retrofit cost ({net_low_str}) is less than cumulative fines "
                f"over the first two periods ({cum_10yr_str} through 2030–34). "
                f"Fines increase each period as the BERDO limit tightens, "
                "so waiting means paying more before you eventually retrofit anyway."
            )
        elif _rec_choice == "phase":
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


def _retrofit_phasing_and_notes(matched):
    """Incentives available in each compliance period, the disclaimer, and sources."""
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


def render_retrofit_optimizer_tab(page, prefill: dict = None):
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

    try:
        berdo_category, fuel, ownership, prefill_fine, scopes_selected, sqft = _retrofit_inputs(prefill)
        total_cost_high, total_cost_low = _retrofit_cost_estimate(scopes_selected, sqft)
        _retrofit_planned_project(sqft, prefill, berdo_category)
        matched, net_high, net_low = _retrofit_incentives(scopes_selected, fuel, ownership, berdo_category, sqft, total_cost_low, total_cost_high, prefill)
        annual_fine = _retrofit_payback(prefill_fine, sqft, net_low, net_high)
        _retrofit_three_paths(page, annual_fine, berdo_category, prefill, sqft, net_low, net_high)
        _retrofit_phasing_and_notes(matched)
    except _EndTab:
        return
