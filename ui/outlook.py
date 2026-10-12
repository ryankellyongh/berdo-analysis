"""
Citywide Outlook tab: the saved predictions of 2025 compliance results for buildings
the City hasn't scored yet, with a map, filters, and the model's track record.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from berdo.predictions import (
    PREDICTIONS_FOR_YEAR,
    PREDICTIONS_SAVED_ON,
    TIER_ORDER,
    TIER_TRACK_RECORD,
    at_risk_by_zip,
    format_probability,
    prediction_summary,
)

TIER_COLORS = {"Likely over": "#C0392B", "Watch": "#E67E22", "Likely compliant": "#27AE60"}
BOSTON_CENTER = {"lat": 42.325, "lon": -71.085}


def _map(df):
    """Building locations colored by tier. Works with older (mapbox) and newer Plotly map traces."""
    trace = getattr(go, "Scattermap", None) or go.Scattermapbox
    fig = go.Figure()
    for tier in ["Likely compliant", "Watch", "Likely over"]:
        sub = df[(df["tier"] == tier) & df["latitude"].notna() & df["longitude"].notna()]
        if sub.empty:
            continue
        hover = (sub["address"].fillna("Address not reported") + "<br>" + sub["property_type"].fillna("")
                 + "<br>" + tier + ": " + sub["probability_action_needed"].map(format_probability)
                 + " chance of Action Needed")
        fig.add_trace(trace(lat=sub["latitude"], lon=sub["longitude"], mode="markers", name=tier,
                            marker=dict(size=8 if tier == "Likely compliant" else 11, color=TIER_COLORS[tier],
                                        opacity=0.55 if tier == "Likely compliant" else 0.9),
                            text=hover, hovertemplate="%{text}<extra></extra>"))
    view = dict(style="open-street-map", center=BOSTON_CENTER, zoom=10.6)
    fig.update_layout(height=520, margin=dict(t=10, b=10, l=10, r=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0),
                      **({"map": view} if trace is getattr(go, "Scattermap", None) else {"mapbox": view}))
    return fig


def render_outlook_tab(page):
    """Predicted 2025 results for buildings without a published City result."""
    st.write(
        "Which buildings without a published City result are likely to be marked **Action Needed** "
        "for 2025? Each building is placed in a tier based on how its previous year's emissions, "
        "restated at the 2025 grid factor, compared with its 2025–29 limit."
    )
    df = page.predictions
    if df is None:
        st.warning("Predictions file not found (analysis/predictions_2026/predictions_2026_pending.csv).")
        return
    if page.selected_year != PREDICTIONS_FOR_YEAR:
        st.info(f"These predictions are for reporting year {PREDICTIONS_FOR_YEAR} (2025 energy use). "
                "Select that year in the sidebar to match the rest of the app.")
    st.caption(
        f"Predictions saved {PREDICTIONS_SAVED_ON}, before the City's planned update after October 15, "
        "so they can be checked against results published later. Screening estimates, not City determinations."
    )

    summary = prediction_summary(df)
    risk = df[df["tier"].isin(["Likely over", "Watch"])]
    exp_low = int(summary[["Expected Action Needed (model)", "Expected Action Needed (tier rates)"]].min(axis=1).sum())
    exp_high = int(summary[["Expected Action Needed (model)", "Expected Action Needed (tier rates)"]].max(axis=1).sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Buildings without a City result", f"{len(df):,}")
    c2.metric("Likely over", f"{int((df['tier'] == 'Likely over').sum()):,}")
    c3.metric("Watch", f"{int((df['tier'] == 'Watch').sum()):,}")
    c4.metric("Expected Action Needed", f"about {exp_low} to {exp_high}")
    st.dataframe(summary, use_container_width=True, hide_index=True)
    st.caption("Two estimates of how many will be Action Needed: the sum of the model's probabilities, "
               "and each tier's count times its track record (below). The model runs slightly high for "
               "low-risk buildings. Buildings with no earlier data can't be predicted individually.")

    st.markdown("---")
    st.subheader("Where the at-risk buildings are")
    f1, f2, f3 = st.columns(3)
    with f1:
        tiers = st.multiselect("Tiers", TIER_ORDER[:3], default=["Likely over", "Watch"], key="outlook_tiers")
    with f2:
        group = st.selectbox("Group", ["All", "Pending Reporting", "Under City review"], key="outlook_group")
    with f3:
        zips = ["All"] + sorted(z for z in df["zip"].dropna().unique())
        zip_pick = st.selectbox("ZIP code", zips, key="outlook_zip")
    view = df[df["tier"].isin(tiers)]
    if group == "Pending Reporting":
        view = view[view["city_status"] == "Pending Reporting"]
    elif group == "Under City review":
        view = view[view["city_status"].str.startswith("Pending Review", na=False)]
    if zip_pick != "All":
        view = view[view["zip"] == zip_pick]

    if view.empty:
        st.info("No buildings match these filters.")
    else:
        st.plotly_chart(_map(view), use_container_width=True)
        missing_xy = int(view[["latitude", "longitude"]].isna().any(axis=1).sum())
        if missing_xy:
            st.caption(f"{missing_xy} of {len(view)} buildings have no coordinates in the City's data and aren't on the map.")
        table = view.assign(**{
            "Chance of Action Needed": view["probability_action_needed"].map(format_probability),
            "Last year vs. limit": (view["ratio_to_limit"] * 100).round(0).astype("Int64").astype(str) + "%",
            "Group": view["city_status"].str.replace("Pending Review from BERDO Team", "Under City review", regex=False),
        })[["address", "zip", "property_type", "Group", "tier", "Last year vs. limit", "Chance of Action Needed"]]
        table.columns = ["Address", "ZIP", "Property type", "Group", "Tier", "Last year vs. limit", "Chance of Action Needed"]
        st.dataframe(table, use_container_width=True, hide_index=True)
        st.download_button("Download these buildings (CSV)", view.to_csv(index=False).encode(),
                           file_name="berdo_predicted_at_risk.csv", mime="text/csv", key="outlook_download")

    st.markdown("**ZIP codes with the most at-risk buildings**")
    st.dataframe(at_risk_by_zip(df), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("How well the tiers have worked")
    record = pd.DataFrame([{"Tier": t, "Buildings": r["buildings"], "Turned out Action Needed": r["action_needed"],
                            "Share": f"{r['action_needed'] / r['buildings']:.1%}"} for t, r in TIER_TRACK_RECORD.items()])
    st.dataframe(record, use_container_width=True, hide_index=True)
    st.caption("Tested on the 809 buildings that already have a City result, using only their previous year's data. "
               "Likely over and Watch together found 43 of 47 Action Needed buildings.")
    with st.expander("Method and limitations"):
        st.markdown(
            "- **Method:** last year's emissions restated at the 2025 grid factor and compared with the "
            "building's 2025–29 limit; a logistic regression adds electricity share, size, mixed use, and "
            "City ownership. Details in `analysis/predictions_2026/README.md`.\n"
            "- **Late reporters may differ** from buildings that reported on time, so estimates could be low.\n"
            "- **Under City review:** the City says these buildings are not considered out of compliance while under review.\n"
            "- **Few examples:** only 47 Action Needed buildings to learn from.\n"
            "- **One year of change:** predictions assume 2025 emissions resemble the previous year's."
        )
