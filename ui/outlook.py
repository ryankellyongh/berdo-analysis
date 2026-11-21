"""
2025 Outlook (behind the City access code): find buildings the City hasn't scored yet
that may need support. One filter row drives a building list, a detail panel for the
selected building, and a map; the model's track record and method follow.

Data-use policy (berdo/predictions.py): building-level estimates appear only here, behind
the access code, and never for buildings under City review.
"""
import hmac
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui.common import open_in_address_lookup
from berdo.predictions import (
    PREDICTIONS_FOR_YEAR,
    PREDICTIONS_SAVED_ON,
    TIER_TRACK_RECORD,
    format_probability,
    UNDER_REVIEW,
    needed_to_act_share,
    prediction_summary,
    type_risk_summary,
    zip_risk_summary,
)

CITY_AN = "Action Needed (City)"
TIER_COLORS = {CITY_AN: "#7A1E1E", "Likely over": "#C0392B", "Watch": "#E67E22",
               "Likely compliant": "#27AE60", "No estimate": "#8B8D98"}
TIER_TEXT = {CITY_AN: "#7A1E1E", "Likely over": "#B42318", "Watch": "#B54708", "Likely compliant": "#067647"}
#Why a building is on the Outreach list, most certain need first
REASONS = ["Action Needed (City result)", "Estimated at risk", "Did not report",
           "Under City review", "No result yet, lower risk or no estimate"]
BOSTON_CENTER = {"lat": 42.325, "lon": -71.085}
ESTIMATED = "Estimated"
STATUS_LABELS = {"No earlier data": "No earlier data", "No limit mapped": "No limit mapped"}


def _display_table(df):
    """
    One row per building, with what may be shown: buildings under City review and those
    without a usable estimate get "No estimate" and no probability.
    """
    d = df.copy()
    review = d["city_status"].eq(UNDER_REVIEW)
    no_est = review | d["tier"].isin(["No earlier data", "No limit mapped"])
    d["Tier"] = d["tier"].where(~no_est, "No estimate")
    d["Chance"] = d["probability_action_needed"].where(~no_est)
    d["Estimate status"] = ESTIMATED
    d.loc[review, "Estimate status"] = "Under City review"
    for t, label in STATUS_LABELS.items():
        d.loc[~review & d["tier"].eq(t), "Estimate status"] = label
    d["address"] = d["address"].fillna("Address not reported")
    order = {"Likely over": 0, "Watch": 1, "Likely compliant": 2, "No estimate": 3}
    d = d.assign(_o=d["Tier"].map(order), _p=d["Chance"].fillna(-1))
    return d.sort_values(["_o", "_p"], ascending=[True, False]).drop(columns=["_o", "_p"])


def _zip5(z):
    z = "" if z is None or (isinstance(z, float) and pd.isna(z)) else str(z).replace(".0", "").strip()
    return z.zfill(5) if z else None


def _outreach_rows(pred, ev):
    """
    Every building that may need contact, one row each: the City's Action Needed results,
    the estimates for buildings without a result, and buildings that didn't report.
    `ev` is the evaluated 2026 disclosure (buildings only, with coordinates).
    """
    d = _display_table(pred)
    d["est_acp"] = float("nan")
    ids = ev["berdo_id"].astype(str)
    no_report = set(ids[ev["data_status"].eq("Not submitted")])
    d["did_not_report"] = d["berdo_id"].astype(str).isin(no_report)
    review = d["Estimate status"].eq("Under City review")
    d["Reason"] = REASONS[4]
    d.loc[d["did_not_report"] & ~review, "Reason"] = REASONS[2]
    d.loc[review, "Reason"] = REASONS[3]
    d.loc[d["Tier"].isin(["Likely over", "Watch"]), "Reason"] = REASONS[1]

    def city_rows(mask, tier, status, reason, did_not_report):
        c = ev[mask]
        return pd.DataFrame({
            "berdo_id": c["berdo_id"].astype(str).values,
            "address": c["Building Address"].fillna("Address not reported").astype(str).values,
            "zip": [_zip5(z) for z in c.get("Building Address Zip Code", pd.Series(None, index=c.index))],
            "latitude": c["lat"].values, "longitude": c["lon"].values,
            "property_type": c["property_type"].values, "sqft": c["gross_floor_area"].values,
            "city_status": c["emissions_status"].values, "tier": None, "Tier": tier, "Chance": float("nan"),
            "Estimate status": status, "Reason": reason,
            "est_acp": pd.to_numeric(c["est_acp"], errors="coerce").values,
            "did_not_report": did_not_report, "ratio_to_limit": float("nan"), "prior_energy_year": float("nan")})

    action = city_rows(ev["emissions_status"].eq("Action Needed"), CITY_AN, "City result", REASONS[0], False)
    extra_nr = city_rows(ev["data_status"].eq("Not submitted") & ~ids.isin(set(d["berdo_id"].astype(str))),
                         "No estimate", "Did not report", REASONS[2], True)
    out = pd.concat([action, d, extra_nr], ignore_index=True)
    order = {r: i for i, r in enumerate(REASONS)}
    tier_order = {CITY_AN: 0, "Likely over": 1, "Watch": 2, "Likely compliant": 3, "No estimate": 4}
    out = out.assign(_r=out["Reason"].map(order), _a=out["est_acp"].fillna(-1),
                     _t=out["Tier"].map(tier_order), _p=out["Chance"].fillna(-1))
    return (out.sort_values(["_r", "_a", "_t", "_p"], ascending=[True, False, True, False])
               .drop(columns=["_r", "_a", "_t", "_p"]).reset_index(drop=True))


def _filters(d):
    """Filter row: address search, tier, property type, ZIP, and estimate status."""
    def reset():
        for k in ("ol_q", "ol_tier", "ol_type", "ol_zip", "ol_status"):
            st.session_state.pop(k, None)
        st.session_state.pop("ol_table", None)

    c = st.columns([2.2, 1.2, 1.6, 1.1, 1.5, 1], vertical_alignment="bottom")
    q = c[0].text_input("Search by address", key="ol_q", placeholder="Enter a street address")
    tier = c[1].selectbox("Tier", ["All tiers", CITY_AN, "Likely over", "Watch", "Likely compliant",
                                   "No estimate"], key="ol_tier")
    ptype = c[2].selectbox("Property type", ["All property types"] +
                           sorted(d["property_type"].dropna().unique()), key="ol_type")
    zips = c[3].selectbox("ZIP code", ["All ZIPs"] + sorted(d["zip"].dropna().unique()), key="ol_zip")
    status = c[4].selectbox("Reason", ["All reasons"] + REASONS, key="ol_status")
    c[5].button("Reset filters", on_click=reset, use_container_width=True)

    m = pd.Series(True, index=d.index)
    if q.strip():
        m &= d["address"].str.contains(q.strip(), case=False, regex=False)
    if tier != "All tiers":
        m &= d["Tier"].eq(tier)
    if ptype != "All property types":
        m &= d["property_type"].eq(ptype)
    if zips != "All ZIPs":
        m &= d["zip"].eq(zips)
    if status != "All reasons":
        m &= d["Reason"].eq(status)
    active = sum([bool(q.strip()), tier != "All tiers", ptype != "All property types",
                  zips != "All ZIPs", status != "All reasons"])
    return d[m], active


def _detail_panel(row):
    """The selected building: why it's listed, the City status, any estimate, and the next step."""
    reason = row["Reason"]
    with st.container(border=True):
        top = st.columns([4, 1], vertical_alignment="center")
        top[0].markdown(f"**{row['address']}**")
        top[1].button("Close", key="ol_close", on_click=lambda: st.session_state.pop("ol_table", None))
        st.caption(" · ".join(str(x) for x in (row.get("zip"), row.get("property_type"), reason)
                              if pd.notna(x) and x))

        #City status
        if reason == REASONS[0]:
            acp = row.get("est_acp")
            city = ("**Action Needed.** The City's 2025 result: this building is over its emissions "
                    "standard." + (f" Estimated ACP about **${acp:,.0f} per year** at $234 per metric ton."
                                   if pd.notna(acp) and acp > 0 else ""))
        elif row["city_status"] == UNDER_REVIEW:
            city = ("Under City review. The City says buildings under review are not considered out "
                    "of compliance while under review.")
        else:
            city = "No City result yet for reporting year 2026. This is unknown, not zero."
        if row.get("did_not_report"):
            city += ("  \n**Did not report** 2025 energy data. Reporting comes first: the ordinance sets "
                     "fines for failing to report, and no emissions result is possible without it.")
        with st.container(border=True):
            st.markdown(f"**City reported status**  \n{city}")

        #Estimate
        with st.container(border=True):
            if reason == REASONS[0]:
                st.markdown("**Model estimate**  \nNot needed: the City has published this building's result.")
            elif row["Tier"] == "No estimate":
                why = {"Under City review": "Estimates are never shown for buildings under City review.",
                       "No earlier data": "There is no earlier year of emissions data to estimate from.",
                       "Did not report": "There is no earlier year of emissions data to estimate from.",
                       "No limit mapped": "This building's use has no mapped BERDO standard, so it "
                                          "can't be compared with a limit."}.get(row["Estimate status"], "")
                st.markdown(f"**Model estimate (not a City result)**  \nNo estimate. {why}")
            else:
                color = TIER_TEXT.get(row["Tier"], "inherit")
                st.markdown(
                    f"**Model estimate (not a City result)**  \n"
                    f"<span style='color:{color};font-weight:700'>{row['Tier']}</span>"
                    f" &nbsp;·&nbsp; {format_probability(row['Chance'])} chance of Action Needed",
                    unsafe_allow_html=True)
                ratio = row.get("ratio_to_limit")
                st.caption(
                    (f"Last year's emissions were {ratio:.0%} of the 2025–29 limit at the 2025 grid factor, "
                     "which sets the tier. " if pd.notna(ratio) else "") +
                    "The chance comes from a separate model that also weighs electricity share, size, "
                    "mixed use, and City ownership, so the two can differ.")

        if reason == REASONS[0]:
            st.markdown("**Source and year:** the City's 2026 disclosure (2025 energy use).  \n"
                        "**Next step:** compliance options (pathways, retrofits, RECs, flexibility measures) "
                        "are on the Address Lookup tab.")
        else:
            year = row.get("prior_energy_year")
            st.markdown(
                f"**Source and year:** City disclosures"
                + (f"; estimate from {int(year)} energy use, saved {PREDICTIONS_SAVED_ON}" if pd.notna(year) else "")
                + ".  \n**Missing information:** the City's 2025 result"
                + (", and 2025 energy data" if row.get("did_not_report") else ", and confirmed 2025 energy use")
                + ".")

        st.button("Open in Address Lookup (next step)", type="primary", use_container_width=True,
                  on_click=open_in_address_lookup, args=(row["address"],), key="ol_handoff")


def _building_map(d, selected):
    """Building locations colored by tier, with a ring on the selected building."""
    trace = getattr(go, "Scattermap", None) or go.Scattermapbox
    newer = trace is getattr(go, "Scattermap", None)
    fig = go.Figure()
    for tier in ["No estimate", "Likely compliant", "Watch", "Likely over", CITY_AN]:
        sub = d[(d["Tier"] == tier) & d["latitude"].notna() & d["longitude"].notna()]
        if sub.empty:
            continue
        hover = (sub["address"] + "<br>Tier: " + tier
                 + sub["Chance"].map(lambda p: "" if pd.isna(p) else
                                     f"<br>Chance of Action Needed: {format_probability(p)}"))
        fig.add_trace(trace(lat=sub["latitude"], lon=sub["longitude"], mode="markers", name=tier,
                            marker=dict(size=7 if tier in ("No estimate", "Likely compliant") else 10,
                                        color=TIER_COLORS[tier],
                                        opacity=0.5 if tier in ("No estimate", "Likely compliant") else 0.9),
                            text=hover, hovertemplate="%{text}<extra></extra>"))
    if selected is not None and pd.notna(selected.get("latitude")):
        for size, color in ((26, "#1F4E99"), (19, "white")):    #ring: blue outer, white inner
            fig.add_trace(trace(lat=[selected["latitude"]], lon=[selected["longitude"]], mode="markers",
                                marker=dict(size=size, color=color), hoverinfo="skip", showlegend=False))
        fig.add_trace(trace(lat=[selected["latitude"]], lon=[selected["longitude"]], mode="markers",
                            marker=dict(size=12, color=TIER_COLORS.get(selected["Tier"], "#8B8D98")),
                            text=[selected["address"]], hovertemplate="%{text}<extra></extra>",
                            showlegend=False))
        center, zoom = {"lat": selected["latitude"], "lon": selected["longitude"]}, 13
    else:
        center, zoom = BOSTON_CENTER, 10.8
    view = dict(style="open-street-map", center=center, zoom=zoom)
    fig.update_layout(height=520, margin=dict(t=10, b=10, l=10, r=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0,
                                  traceorder="reversed"),
                      **({"map": view} if newer else {"mapbox": view}))
    return fig


def _zip_map(z):
    """One circle per ZIP code, placed at the average location of its buildings."""
    trace = getattr(go, "Scattermap", None) or go.Scattermapbox
    z = z[z["latitude"].notna() & z["longitude"].notna() & (z["at_risk"] > 0)]
    size = z["at_risk"].clip(lower=3).pow(0.5) * 7          #small counts all get the smallest circle
    fig = go.Figure(trace(lat=z["latitude"], lon=z["longitude"], mode="markers",
                          marker=dict(size=size, color=TIER_COLORS["Likely over"], opacity=0.55),
                          text="ZIP " + z["ZIP code"] + ": " + z["At risk"] + " at-risk buildings",
                          hovertemplate="%{text}<extra></extra>"))
    view = dict(style="open-street-map", center=BOSTON_CENTER, zoom=10.6)
    fig.update_layout(height=520, margin=dict(t=10, b=10, l=10, r=10), showlegend=False,
                      **({"map": view} if trace is getattr(go, "Scattermap", None) else {"mapbox": view}))
    return fig


def city_access(where: str = "citywide"):
    """
    The Citywide Outlook tab is shown only after the access code is entered. The code is set in
    Streamlit's secrets (CITY_ACCESS_CODE), never in the code or the repository. Returns True when
    access is granted; otherwise shows the code box (or a note if no code is configured).
    """
    if st.session_state.get("city_access_granted"):
        return True
    try:
        code = st.secrets.get("CITY_ACCESS_CODE")
    except Exception:
        code = None
    if not code:
        st.info("Predictions are available to the City's BERDO team. Access hasn't been set up "
                "for this app yet.")
        return False
    st.info("Predictions are available to Building Owners and the City of Boston on request. "
            "Enter your access code to view them.")
    #One code box per tab (each needs its own widget key); entering it on either tab unlocks both
    entered = st.text_input("Access code", type="password", key=f"city_access_code_{where}")
    if entered and hmac.compare_digest(str(entered), str(code)):
        st.session_state["city_access_granted"] = True
        st.success("Access granted.")
        return True
    if entered:
        st.error("That code isn't correct.")
    return False


def render_outlook_tab(page, coords_path="data/berdo_coordinates.csv"):
    """Every building that may need contact: City results, estimates, and non-reporters."""
    if not city_access("outreach"):
        return
    df = page.predictions
    city_df = page.all_years.get(PREDICTIONS_FOR_YEAR)
    if df is None or city_df is None:
        st.warning("Outreach needs the 2026 disclosure (data/berdo_2026.csv) and the saved predictions "
                   "(analysis/predictions_2026/predictions_2026_pending.csv).")
        return
    from berdo.data import buildings_only                                    #here to avoid a circular import
    from ui.citywide import attach_coordinates, evaluate_year, load_coordinates
    ev = buildings_only(attach_coordinates(evaluate_year(city_df), load_coordinates(coords_path)))
    st.write("Every building that may need contact, most certain need first: the City's Action Needed "
             "results, buildings estimated to be at risk, and buildings that didn't report. Estimates are "
             f"screening results from earlier-year data, not City determinations. Uses reporting year "
             f"{PREDICTIONS_FOR_YEAR} (2025 energy use), whichever year is selected.")

    #Headline counts
    summary = prediction_summary(df)
    exp_low = int(summary[["Expected (model)", "Expected (tier rates)"]].min(axis=1).sum())
    exp_high = int(summary[["Expected (model)", "Expected (tier rates)"]].max(axis=1).sum())
    at_risk = int(df["tier"].isin(["Likely over", "Watch"]).sum())
    in_review = int((df["tier"].isin(["Likely over", "Watch"]) & df["city_status"].eq(UNDER_REVIEW)).sum())
    c = st.columns(4)
    c[0].metric("Action Needed (City result)", f"{int(ev['emissions_status'].eq('Action Needed').sum()):,}")
    c[1].metric("Estimated at risk", f"{at_risk:,}",
                help=f"Likely over or Watch, among buildings without a City result. Includes {in_review} "
                     "under City review, which are counted here but never listed individually.")
    c[2].metric("Did not report", f"{int(ev['data_status'].eq('Not submitted').sum()):,}")
    c[3].metric("Expected Action Needed (about)", f"{exp_low}–{exp_high}",
                help="Among buildings without a City result. Low end: each tier's count times its track "
                     "record. High end: the sum of the model's probabilities. Buildings with no earlier "
                     "data aren't included.")
    with st.expander("Counts by group (buildings without a City result)"):
        st.dataframe(summary, use_container_width=True, hide_index=True)
        st.caption("Pending Reporting: buildings covered in 2025 that haven't reported. Under City review: "
                   "the City is checking their data. Buildings with no earlier data can't be estimated.")

    #Find a building
    st.markdown("---")
    st.subheader("Find a building")
    d = _outreach_rows(df, ev)
    view, n_filters = _filters(d)
    #A selection points at a row of the filtered list, so clear it whenever the filters change
    sig = (len(view), tuple(view["berdo_id"].head(50)))
    if st.session_state.get("ol_sig") != sig:
        st.session_state["ol_sig"] = sig
        st.session_state.pop("ol_table", None)
    left, right = st.columns([1.75, 1], gap="medium")
    with left:
        note = "No filters applied." if n_filters == 0 else f"{n_filters} filter{'s' if n_filters > 1 else ''} applied."
        on_map = int(view[["latitude", "longitude"]].notna().all(axis=1).sum())
        st.markdown(f"**{len(view):,} of {len(d):,} buildings match**, {on_map:,} with a map location. {note} "
                    "The list and the map use the same filters.")
        table = view[["address", "Reason", "Tier", "Chance"]].rename(columns={"address": "Address"})
        table["Chance"] = table["Chance"].map(lambda p: "No estimate" if pd.isna(p) else format_probability(p))
        styled = table.style.map(lambda t: f"color: {TIER_TEXT[t]}; font-weight: 600" if t in TIER_TEXT else "",
                                 subset=["Tier"])
        event = st.dataframe(
            styled, key="ol_table", on_select="rerun", selection_mode="single-row",
            use_container_width=True, hide_index=True, height=420,
            column_config={
                "Chance": st.column_config.TextColumn(
                    "Chance",
                    help="Model estimate of the chance the City marks the building Action Needed. "
                         "The tier comes from last year's emissions vs. the limit, so the two can differ."),
                "Tier": st.column_config.TextColumn(help="Action Needed (City): the City's published result. "
                                                         "Likely over: above the 2025–29 limit last year. "
                                                         "Watch: within 10%. Likely compliant: more than 10% under."),
                "Reason": st.column_config.TextColumn(help="Why the building is listed, most certain need first."),
            })
        st.caption("Select a row to see the building's details and its place on the map.")
        rows = event.selection.rows if event and event.selection else []
        picked = bool(rows) and rows[0] < len(view)
        #Until a row is picked, show the highest-ranked building so the panel is never empty
        selected = view.iloc[rows[0]] if picked else (view.iloc[0] if len(view) else None)
        export = view.drop(columns=["Tier", "Chance", "Estimate status", "Reason"]).assign(
            reason=view["Reason"], tier=view["Tier"], probability_action_needed=view["Chance"],
            estimate_status=view["Estimate status"])
        st.download_button("Download filtered results (CSV)", export.to_csv(index=False).encode(),
                           file_name="berdo_outreach_filtered.csv", mime="text/csv",
                           key="outlook_download", type="primary")
    with right:
        if selected is not None:
            if not picked:
                st.caption("Showing the highest-ranked building. Select a row to see another.")
            _detail_panel(selected)
        else:
            with st.container(border=True):
                st.markdown("**No buildings match these filters**")
                st.caption("Change or reset the filters to see buildings.")

    #Map
    st.subheader("Map")
    mode = st.segmented_control("Map view", ["Individual buildings", "ZIP code"], default="Individual buildings",
                                key="ol_map_mode", label_visibility="collapsed") or "Individual buildings"
    if mode == "ZIP code":
        st.plotly_chart(_zip_map(zip_risk_summary(df)), use_container_width=True)
        st.caption("At-risk buildings (Likely over or Watch) by ZIP code; counts under 3 aren't shown exactly. "
                   "This view ignores the filters above.")
        c1, c2 = st.columns(2)
        with c1:
            z = zip_risk_summary(df)
            st.dataframe(z[z["at_risk"] > 0][["ZIP code", "At risk"]], use_container_width=True, hide_index=True)
        with c2:
            st.dataframe(type_risk_summary(df), use_container_width=True, hide_index=True)
    elif view[["latitude", "longitude"]].notna().all(axis=1).any():
        st.plotly_chart(_building_map(view, selected), use_container_width=True)
        missing = int(view["latitude"].isna().sum())
        st.caption("The ringed marker is the building shown in the panel. Map data © OpenStreetMap contributors." +
                   (f" {missing:,} matching building{'s' if missing != 1 else ''} without a location "
                    "aren't on the map." if missing else ""))
    else:
        st.info("None of the matching buildings has a map location.")

    st.markdown("---")
    st.subheader("How well the tiers have worked")
    record = pd.DataFrame([{
        "Tier": t,
        "Buildings": r["buildings"],
        "Action Needed": (f"{r['action_needed']} "
                          f"({r['action_needed'] / r['buildings']:.{1 if r['action_needed'] / r['buildings'] < 0.01 else 0}%})"),
        "Came in compliant after acting": (str(r["acted_to_comply"]) if r["acted_to_comply"] is not None
                                           else "Not applicable"),
        "Needed to act": (f"{needed_to_act_share(t):.0%}" if needed_to_act_share(t) is not None
                          else "Not applicable"),
    } for t, r in TIER_TRACK_RECORD.items()])
    st.dataframe(record, use_container_width=True, hide_index=True)
    st.caption(
        "Tested on the 809 buildings that already have a City result, using only their previous year's data. "
        "Likely over and Watch together found 43 of 47 Action Needed buildings. Most buildings in those tiers "
        "that came in compliant did so by acting between years: cutting emissions by more than 10%, buying "
        "renewable electricity, or using a flexibility measure such as a blended standard. Of the 88 Likely "
        "over buildings, 87 were Action Needed or acted to avoid it. The tiers flag buildings that need to act; "
        "they can't foresee which owners will act in time."
    )
    with st.expander("Method and limitations"):
        st.markdown(
            "- **Method:** last year's emissions restated at the 2025 grid factor and compared with the "
            "building's 2025–29 limit; a logistic regression adds electricity share, size, mixed use, and "
            "City ownership. Details in `analysis/predictions_2026/README.md`.\n"
            "- **Late reporters may differ** from buildings that reported on time, so estimates could be low.\n"
            "- **Under City review:** the City says these buildings are not considered out of compliance while under review.\n"
            "- **Few examples:** only 47 Action Needed buildings to learn from.\n"
            "- **One year of change:** predictions assume 2025 emissions resemble the previous year's.\n"
            "- **Data use:** predictions are shared only with the City's BERDO team (by access code) and "
            "with owners for their own buildings. Buildings under City review are never labeled individually."
        )
