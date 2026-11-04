"""
Citywide trends section (shown on Citywide Overview, outside the access code: citywide totals only).
Calculations come from berdo.trends; this module only displays them.
"""
import plotly.graph_objects as go
import streamlit as st

from berdo.trends import compute_trends

BLUE, ORANGE, GREY, RED = "#288BE4", "#F76B15", "#8B8D98", "#E5484D"


@st.cache_data(show_spinner="Calculating citywide trends…")
def _trends(_all_years, years_key):
    """Cached by the tuple of reporting years; the data itself isn't hashed."""
    return compute_trends(_all_years)


def _layout(fig, height=300, **kw):
    fig.update_layout(height=height, margin=dict(t=10, b=10, l=10, r=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", **kw)
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.15)")
    return fig


def render_trends(all_years):
    st.markdown("#### Citywide trends")
    t = _trends(all_years, tuple(sorted(all_years)))
    if not t or "index" not in t:
        st.info("Trends need at least three years of data.")
        return
    i, prov = t["index"], t["provisional_year"]
    first, last = int(i["emissions"].index.min()), int(i["emissions"].index.max())
    st.caption(f"Energy years {first}–{last}, using the same buildings every year so changes in who "
               f"reported don't skew the trend. Energy year {prov} (reporting year {prov + 1}) is "
               "provisional and left out. Citywide totals only; no building is identified.")

    #Headline numbers
    c = st.columns(4)
    c[0].metric(f"Emissions per sq ft, {first}→{last}", f"{t['emissions_change']:+.0%}",
                help=f"{i['n_emissions']:,} buildings reporting every year, floor-area weighted.")
    if "grid" in t:
        g = t["grid"]
        share = g["grid_pct"] / g["total_pct"] if g["total_pct"] else None
        c[1].metric(f"Share of {g['years'][0]}→{g['years'][1]} drop from a cleaner grid",
                    f"{share:.0%}" if share is not None else "N/A",
                    help=f"{g['n']:,} buildings. Electricity emissions restated at the "
                         f"{g['years'][0]} grid factor to separate the grid from the buildings.")
    so = t["share_over"]
    c[2].metric(f"Over the 2025–29 limit, {first}→{last}",
                f"{so.loc[first]:.0%} → {so.loc[last]:.0%}",
                help="Same buildings every year, compared with their sector's 2025–29 limit.")
    if "persistence" in t:
        p = t["persistence"]
        c[3].metric(f"Over the limit in {p['years'][0]} and still over in {p['years'][1]}",
                    f"{p['stay_over']:.0%}" if p["stay_over"] is not None else "N/A",
                    help=f"{p['n']:,} buildings. Year-to-year correlation of emissions intensity: "
                         f"r = {p['r']:.2f} (log scale).")

    #Trend and grid charts
    left, right = st.columns(2)
    with left:
        st.markdown(f"**Energy use and emissions per sq ft** ({i['base_year']} = 100)")
        fig = go.Figure()
        if len(i["energy"]):
            fig.add_trace(go.Scatter(x=i["energy"].index, y=i["energy"].round(1), mode="lines+markers",
                                     name=f"Energy use ({i['n_energy']:,} buildings)",
                                     line=dict(color=BLUE, width=2.5)))
        fig.add_trace(go.Scatter(x=i["emissions"].index, y=i["emissions"].round(1), mode="lines+markers",
                                 name=f"Emissions ({i['n_emissions']:,} buildings)",
                                 line=dict(color=ORANGE, width=2.5)))
        fig.update_xaxes(dtick=1)
        st.plotly_chart(_layout(fig), width="stretch")
    with right:
        if "grid" in t:
            g = t["grid"]
            st.markdown(f"**What drove the {g['years'][0]}→{g['years'][1]} change**")
            labels = ["Total change", "Cleaner grid", "Buildings (energy use, fuel mix)"]
            vals = [g["total_t"], g["grid_t"], g["building_t"]]
            pcts = [g["total_pct"], g["grid_pct"], g["building_pct"]]
            fig = go.Figure(go.Bar(x=vals, y=labels, orientation="h", marker_color=[GREY, BLUE, ORANGE],
                                   text=[f"{v:,.0f} t ({p:+.1%})" for v, p in zip(vals, pcts)],
                                   textposition="auto", hovertemplate="%{y}: %{x:,.0f} metric tons<extra></extra>"))
            fig.update_yaxes(autorange="reversed")
            fig.update_xaxes(title="Metric tons CO₂e")
            st.plotly_chart(_layout(fig, showlegend=False), width="stretch")

    #Share over limit and categories
    left, right = st.columns(2)
    with left:
        st.markdown("**Buildings above the 2025–29 limit**")
        fig = go.Figure(go.Scatter(x=so.index, y=(so * 100).round(1), mode="lines+markers+text",
                                   text=[f"{v:.0%}" for v in so], textposition="top center",
                                   line=dict(color=RED, width=2.5), hovertemplate="%{x}: %{y:.1f}%<extra></extra>"))
        fig.update_xaxes(dtick=1)
        fig.update_yaxes(title="% of buildings", rangemode="tozero")
        st.plotly_chart(_layout(fig, showlegend=False), width="stretch")
    with right:
        w = t.get("by_category")
        if w is not None and len(w):
            y0, y1 = t["category_years"]
            st.markdown(f"**Emissions per sq ft by category, {y0}→{y1}**")
            fig = go.Figure(go.Bar(x=(w["change"] * 100).round(1), y=w.index, orientation="h",
                                   marker_color=[BLUE if v < 0 else RED for v in w["change"]],
                                   text=[f"{v:+.0%} ({int(n)})" for v, n in zip(w["change"], w["buildings"])],
                                   textposition="auto",
                                   hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
            fig.update_xaxes(title="% change (buildings in parentheses)")
            st.plotly_chart(_layout(fig, height=max(260, 28 * len(w)), showlegend=False), width="stretch")

    with st.expander("How to read these trends"):
        st.markdown(
            "- **Same buildings every year:** each chart follows only buildings that reported in every "
            "year shown, linked by BERDO ID.\n"
            "- **Floor-area weighted:** total energy or emissions divided by total floor area, so larger "
            "buildings count more.\n"
            "- **Cleaner grid vs. buildings:** electricity emissions are restated at a fixed grid factor. "
            "What remains is the buildings' own change in energy use and fuel mix.\n"
            "- **Persistence:** buildings over their limit one year are usually over the next, which is "
            "why last year's emissions are the strongest predictor in the 2025 Outlook.\n"
            "- **Caution:** the drop from the first to the second emissions year is larger than energy use "
            "and the grid explain, and may partly reflect a change in how the City calculated emissions.\n"
            "- Weather isn't adjusted for. Details and code: `analysis/time_series/`."
        )
