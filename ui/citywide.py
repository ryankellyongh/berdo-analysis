"""
Citywide Overview tab: headline counts, status breakdown, map, and sector table.

Calculations come from berdo (evaluate_building, headline_counts). Every count uses one
population: buildings. Campus summary rows (a whole campus's totals) are counted
separately as campus assessments, so no card mixes the two.
"""
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from berdo.data import buildings_only, headline_counts
from berdo.emissions import evaluate_building, map_property_type
from ui.outlook import city_access

#Status groups for colour. Reporting gaps and emissions gaps stay separate; no risk score.
STATUS_GROUPS = [
    ("Over its 2025–29 limit", "#D62728", {"Over 2025–29 limit", "Action needed (City)"}),
    ("Fails 2030–34",          "#FF7F0E", {"Fails 2030–34"}),
    ("Compliant through 2034", "#E3B505", {"Compliant through 2034"}),
    ("Compliant through 2039+", "#2CA02C", {"Compliant through 2039+", "Meets 2025 limit (City)"}),
    ("Not yet covered",        "#9467BD", {"Not yet covered"}),
    ("Assessed with a portfolio or campus", "#17BECF",
     {"Assessed in a Building Portfolio", "Assessed at campus level", "Campus member (water only)"}),
    ("Under City review or pending", "#8C564B", {"Under City review", "Pending reporting (City)"}),
]
OTHER_GROUP, OTHER_COLOR = "Not assessed or data incomplete", "#9E9E9E"
HIDDEN_BY_DEFAULT = {OTHER_GROUP, "Not yet covered", "Assessed with a portfolio or campus"}


def status_group(status: str) -> str:
    for name, _, members in STATUS_GROUPS:
        if status in members:
            return name
    return OTHER_GROUP


def _color(group):
    return next((c for n, c, _ in STATUS_GROUPS if n == group), OTHER_COLOR)


def _money(v):
    v = float(v or 0)
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:,.1f}M"
    if abs(v) >= 100_000:
        return f"${v / 1_000:,.0f}K"
    return f"${v:,.0f}"


@st.cache_data(show_spinner="Evaluating every building…")
def evaluate_year(df: pd.DataFrame) -> pd.DataFrame:
    out = df.apply(evaluate_building, axis=1, result_type="expand")
    out.columns = ["data_status", "berdo_status", "est_acp", "notes"]
    df = pd.concat([df.reset_index(drop=True), out.reset_index(drop=True)], axis=1)
    df["status_group"] = df["berdo_status"].map(status_group)
    df["berdo_category"] = df["property_type"].map(map_property_type).fillna("Unmapped or missing")
    return df


@st.cache_data(show_spinner=False)
def load_coordinates(path: str):
    fp = Path(path)
    if not fp.exists():
        return None
    c = pd.read_csv(fp, dtype={"berdo_id": str})
    c["tax_parcel_id"] = pd.to_numeric(c["tax_parcel_id"], errors="coerce")
    return c


def attach_coordinates(df, coords):
    df = df.copy()
    df["lat"] = float("nan")
    df["lon"] = float("nan")
    if coords is None:
        return df
    by_id = coords.dropna(subset=["berdo_id"]).drop_duplicates("berdo_id", keep="last").set_index("berdo_id")
    ids = df["berdo_id"].astype(str) if "berdo_id" in df.columns else pd.Series("", index=df.index)
    df["lat"], df["lon"] = ids.map(by_id["lat"]), ids.map(by_id["lon"])
    if "tax_parcel_id" in df.columns:
        by_p = coords.dropna(subset=["tax_parcel_id"]).drop_duplicates("tax_parcel_id", keep="last").set_index("tax_parcel_id")
        parcels = pd.to_numeric(df["tax_parcel_id"], errors="coerce")
        miss = df["lat"].isna()
        df.loc[miss, "lat"] = parcels[miss].map(by_p["lat"])
        df.loc[miss, "lon"] = parcels[miss].map(by_p["lon"])
    return df


def _map(b: pd.DataFrame):
    st.markdown("#### Map")
    if b["lat"].notna().sum() == 0:
        st.info("No coordinates available. Add data/berdo_coordinates.csv to enable the map.")
        return
    present = [n for n, _, _ in STATUS_GROUPS if n in set(b["status_group"])]
    if OTHER_GROUP in set(b["status_group"]):
        present.append(OTHER_GROUP)
    c1, c2 = st.columns([3, 1])
    with c1:
        show = st.multiselect("Status", present, key="cw_map_status",
                              default=[g for g in present if g not in HIDDEN_BY_DEFAULT])
    with c2:
        cats = ["All categories"] + sorted(c for c in b["berdo_category"].unique() if c != "Unmapped or missing")
        cat = st.selectbox("Building category", cats, key="cw_map_cat")
    m = b[b["status_group"].isin(show) & b["lat"].notna()]
    if cat != "All categories":
        m = m[m["berdo_category"] == cat]
    if m.empty:
        st.caption("No buildings match these filters.")
        return
    #One dot per location, coloured by the most serious status there
    order = {n: i for i, (n, _, _) in enumerate(STATUS_GROUPS)}
    m = m.assign(_r=m["status_group"].map(order).fillna(len(order)),
                 _k=m["lat"].round(5).astype(str) + "," + m["lon"].round(5).astype(str),
                 _addr=m["Building Address"].fillna("Address not reported").astype(str)).sort_values("_r")
    pts = m.groupby("_k", sort=False).agg(
        lat=("lat", "first"), lon=("lon", "first"), group=("status_group", "first"),
        n=("_addr", "size"), names=("_addr", lambda s: "<br>".join(list(s)[:6])))
    Scatter = getattr(go, "Scattermap", None) or go.Scattermapbox
    key = "map" if Scatter is getattr(go, "Scattermap", None) else "mapbox"
    fig = go.Figure()
    for g in reversed([n for n in present if n in show]):
        p = pts[pts["group"] == g]
        if p.empty:
            continue
        hover = "<b>" + p["names"] + "</b><br>" + g + p["n"].map(lambda k: f"<br>{k} buildings here" if k > 1 else "")
        fig.add_trace(Scatter(lat=p["lat"], lon=p["lon"], mode="markers", hoverinfo="skip", showlegend=False,
                              legendgroup=g, marker=dict(size=13, color="#000000")))
        fig.add_trace(Scatter(lat=p["lat"], lon=p["lon"], mode="markers", name=f"{g} ({len(p):,})",
                              legendgroup=g, marker=dict(size=9, color=_color(g)),
                              hovertext=hover, hoverinfo="text"))
    fig.update_layout(**{key: dict(style="open-street-map", center=dict(lat=42.32, lon=-71.08), zoom=11.2),
                         "height": 620, "margin": dict(t=0, b=70, l=0, r=0),
                         "legend": dict(orientation="h", yanchor="top", y=-0.01, x=0, traceorder="reversed")})
    st.plotly_chart(fig, use_container_width=True)
    unmapped = int((b["status_group"].isin(show) & b["lat"].isna()).sum())
    st.caption(f"{len(m):,} buildings at {len(pts):,} locations."
               + (f" {unmapped:,} matching buildings have no coordinates." if unmapped else ""))


def render_citywide_tab(page, coords_path="data/berdo_coordinates.csv"):
    st.markdown("### Who needs support?")
    st.caption("Reporting support and emissions planning are shown separately. There is no combined risk score.")
    if not city_access():
        return
    ev = evaluate_year(page.df_full)
    ev = attach_coordinates(ev, load_coordinates(coords_path))
    b = buildings_only(ev)                                  #buildings only, never campus summaries
    counts = headline_counts(ev, ev["berdo_status"])
    emissions_year = (page.selected_year - 1) if page.selected_year else 2025
    pre_limits = emissions_year < 2025
    if pre_limits:
        st.info(f"**Reporting year {page.selected_year} contains {emissions_year} emissions, before BERDO "
                f"limits took effect.** Figures show what would be owed if {emissions_year} emissions repeated.")

    reporting = b["data_status"].isin(["Not submitted", "Extension granted", "Incomplete data"])
    over = b["status_group"] == "Over its 2025–29 limit"
    acp = pd.to_numeric(b.loc[over, "est_acp"], errors="coerce")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Buildings", f"{counts['buildings']:,}",
              help=f"Excludes {counts['campus_assessments']} campus summary records, counted separately.")
    c2.metric("Need reporting support", f"{int(reporting.sum()):,}",
              help="Not submitted, extension, or incomplete data.")
    c3.metric("Would exceed 2025–29 limit" if pre_limits else "Over 2025–29 limit", f"{int(over.sum()):,}")
    c4.metric(f"Projected annual ACP (if {emissions_year} repeats)" if pre_limits else "Est. annual ACP (2025–29)",
              _money(acp.sum()) if acp.notna().any() else "N/A",
              help=(f"Exact: ${acp.sum():,.0f}/yr across {int(acp.notna().sum())} buildings with an estimate. "
                    f"{int(acp.isna().sum())} over-limit buildings have no estimate and are not included.")
              if acp.notna().any() else "No building has an ACP estimate.")
    st.caption(f"All counts are buildings. The City's data also has {counts['campus_assessments']} campus "
               "summary records (a whole campus's totals); they are not added to building counts.")

    st.markdown("---")
    _map(b)
    st.markdown("---")
    st.markdown("#### By BERDO building category")
    rows = []
    for cat, g in b.groupby("berdo_category"):
        acp_g = pd.to_numeric(g.loc[g["status_group"] == "Over its 2025–29 limit", "est_acp"], errors="coerce")
        rows.append({"Category": cat, "Buildings": len(g),
                     "Need reporting support": int(g["data_status"].isin(
                         ["Not submitted", "Extension granted", "Incomplete data"]).sum()),
                     "Over 2025–29 limit": int((g["status_group"] == "Over its 2025–29 limit").sum()),
                     "Fails 2030–34": int((g["status_group"] == "Fails 2030–34").sum()),
                     "Est. annual ACP": acp_g.sum() if acp_g.notna().any() else None})
    table = pd.DataFrame(rows).sort_values("Buildings", ascending=False)
    st.dataframe(table, use_container_width=True, hide_index=True,
                 column_config={"Est. annual ACP": st.column_config.NumberColumn(format="$%d")})
    st.caption("Empty ACP cells mean no estimate is available, not $0.")
