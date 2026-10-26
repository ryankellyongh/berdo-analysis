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
from berdo.emissions import building_limits, calculate_compliance_gap, evaluate_building, map_property_type
from ui.outlook import city_access

#Status groups for colour. Reporting gaps and emissions gaps stay separate; no risk score.
#Status groups and colours. A warm-to-cool ramp carries the meaning (red over the
#limit -> orange -> amber -> green compliant), and other groups use distinct, softer
#hues. Reporting gaps and emissions gaps stay separate; there is no risk score.
STATUS_GROUPS = [
    ("Over its 2025–29 limit", "#E5484D", {"Over 2025–29 limit", "Action needed (City)"}),
    ("Fails 2030–34",          "#F76B15", {"Fails 2030–34"}),
    ("Compliant through 2034", "#FFB224", {"Compliant through 2034"}),
    ("Compliant through 2039+", "#30A46C", {"Compliant through 2039+"}),
    ("Not yet covered",        "#8E4EC6", {"Not yet covered"}),
    ("Assessed with a portfolio or campus", "#0090FF",
     {"Assessed in a Building Portfolio", "Assessed at campus level", "Campus member (water only)"}),
    ("Under City review or pending", "#D6409F", {"Under City review", "Pending reporting (City)"}),
]
OTHER_GROUP, OTHER_COLOR = "Not assessed or data incomplete", "#8B8D98"
OUTLINE = "rgba(28, 32, 36, 0.85)"     #soft charcoal edge around each dot
#Basemaps (first is the default). Voyager needs plotly's newer map traces.
BASEMAPS = {"Voyager": "carto-voyager", "Street map": "open-street-map",
            "Light": "carto-positron", "Dark": "carto-darkmatter"}
HIDDEN_BY_DEFAULT = {OTHER_GROUP, "Not yet covered", "Assessed with a portfolio or campus",
                     "Under City review or pending"}
CITY_COMPLIANT = "Meets 2025 limit (City)"


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
    #The City's "In Compliance" covers 2025-29 only. Place those buildings on the same
    #ramp as the rest by checking their reported emissions against later limits.
    for i in df.index[df["berdo_status"] == CITY_COMPLIANT]:
        r = df.loc[i]
        lim = building_limits(r.get("property_type"), r.get("all_property_types"))["limits"]
        ghg, sqft = r.get("ghg_intensity_kgco2e_sqft"), r.get("gross_floor_area")
        if lim is None or pd.isna(ghg) or pd.isna(sqft) or sqft <= 0:
            df.at[i, "status_group"] = "Compliant through 2034"     #2025-29 confirmed; later unknown
            continue
        g = calculate_compliance_gap(float(ghg), float(sqft), None, limits=lim)
        df.at[i, "status_group"] = ("Fails 2030–34" if not g[1]["compliant"] else
                                    "Compliant through 2034" if not g[2]["compliant"] else
                                    "Compliant through 2039+")
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
    Scatter = getattr(go, "Scattermap", None) or go.Scattermapbox
    newer = Scatter is getattr(go, "Scattermap", None)
    key = "map" if newer else "mapbox"
    basemaps = BASEMAPS if newer else {k: v for k, v in BASEMAPS.items() if k != "Voyager"}

    present = [n for n, _, _ in STATUS_GROUPS if n in set(b["status_group"])]
    if OTHER_GROUP in set(b["status_group"]):
        present.append(OTHER_GROUP)
    c1, c2, c3 = st.columns([3, 1.2, 1])
    with c1:
        show = st.multiselect("Status", present, key="cw_map_status",
                              default=[g for g in present if g not in HIDDEN_BY_DEFAULT])
    with c2:
        cats = ["All categories"] + sorted(c for c in b["berdo_category"].unique() if c != "Unmapped or missing")
        cat = st.selectbox("Building category", cats, key="cw_map_cat")
    with c3:
        base = st.selectbox("Basemap", list(basemaps), key="cw_map_base")
    m = b[b["status_group"].isin(show) & b["lat"].notna()]
    if cat != "All categories":
        m = m[m["berdo_category"] == cat]
    if m.empty:
        st.caption("No buildings match these filters.")
        return

    #One dot per location, coloured by the most serious status there and sized by
    #the combined floor area of the buildings at that spot.
    order = {n: i for i, (n, _, _) in enumerate(STATUS_GROUPS)}
    m = m.assign(_r=m["status_group"].map(order).fillna(len(order)),
                 _k=m["lat"].round(5).astype(str) + "," + m["lon"].round(5).astype(str),
                 _addr=m["Building Address"].fillna("Address not reported").astype(str),
                 _sqft=pd.to_numeric(m["gross_floor_area"], errors="coerce").fillna(0)).sort_values("_r")
    pts = m.groupby("_k", sort=False).agg(
        lat=("lat", "first"), lon=("lon", "first"), group=("status_group", "first"),
        n=("_addr", "size"), sqft=("_sqft", "sum"), names=("_addr", lambda s: "<br>".join(list(s)[:6])))
    pts["size"] = 7 + (pts["sqft"].clip(upper=1_500_000) / 1_500_000) ** 0.5 * 17

    fig = go.Figure()
    #Lowest-priority groups first, so red and orange are drawn on top
    for g in reversed([n for n in present if n in show]):
        p = pts[pts["group"] == g]
        if p.empty:
            continue
        hover = ("<b>" + p["names"] + "</b><br>" + g
                 + p["sqft"].map(lambda v: f"<br>{v:,.0f} sq ft" if v > 0 else "")
                 + p["n"].map(lambda k: f"<br>{k} buildings here" if k > 1 else ""))
        fig.add_trace(Scatter(lat=p["lat"], lon=p["lon"], mode="markers", hoverinfo="skip",
                              showlegend=False, legendgroup=g,
                              marker=dict(size=p["size"] + 3, color=OUTLINE)))
        fig.add_trace(Scatter(lat=p["lat"], lon=p["lon"], mode="markers", name=f"{g} ({len(p):,})",
                              legendgroup=g, marker=dict(size=p["size"], color=_color(g), opacity=0.92),
                              hovertext=hover, hoverinfo="text",
                              hoverlabel=dict(bgcolor="white", bordercolor=_color(g),
                                              font=dict(color="#1C2024", size=12))))
    fig.update_layout(**{key: dict(style=basemaps[base], center=dict(lat=42.32, lon=-71.08), zoom=11.2),
                         "height": 640, "margin": dict(t=0, b=80, l=0, r=0),
                         "legend": dict(orientation="h", yanchor="top", y=-0.01, x=0,
                                        traceorder="reversed", itemsizing="constant",
                                        font=dict(size=12))})
    st.plotly_chart(fig, use_container_width=True)
    unmapped = int((b["status_group"].isin(show) & b["lat"].isna()).sum())
    st.caption(f"{len(m):,} buildings at {len(pts):,} locations. Dot size shows floor area."
               + (f" {unmapped:,} matching buildings have no coordinates." if unmapped else ""))


def render_citywide_tab(page, coords_path="data/berdo_coordinates.csv"):
    year = page.selected_year
    st.write(f"A citywide picture of BERDO reporting and emissions compliance for every covered "
             f"building in the {year} dataset.")
    if not city_access():
        return
    ev = evaluate_year(page.df_full)
    ev = attach_coordinates(ev, load_coordinates(coords_path))
    b = buildings_only(ev)                                  #buildings only, never campus summaries
    counts = headline_counts(ev, ev["berdo_status"])
    emissions_year = (year - 1) if year else 2025
    pre_limits = emissions_year < 2025

    if pre_limits:
        st.info(f"**Reporting year {year} contains {emissions_year} emissions, before BERDO emissions "
                f"limits took effect.** Limits first apply to 2025 emissions (reported in 2026). The "
                f"figures below show which buildings would exceed the 2025–29 limit, and the ACP they "
                f"would owe, if their {emissions_year} emissions repeated.")
    elif "emissions_status" in ev.columns and ev["emissions_status"].notna().any():
        st.warning("**Provisional data.** In this disclosure the City withheld energy and emissions data "
                   "for buildings under review, with extensions, or with pending revisions. Buildings over "
                   "their limit are routinely flagged for review, so the number of over-limit buildings "
                   "below is likely an **undercount**.")

    status = b["berdo_status"].astype(str)
    over = b["status_group"] == "Over its 2025–29 limit"
    acp = pd.to_numeric(b.loc[over, "est_acp"], errors="coerce")
    not_subject = status.str.startswith("Not assessed") | status.eq("Vacant (exempt)")
    unknown = (status.str.startswith("Unknown") | status.eq("Coverage year not reported")
               | status.isin(["Under City review", "Pending reporting (City)"]))

    r1 = st.columns(4)
    r1[0].metric("Covered buildings", f"{counts['buildings']:,}",
                 delta=f"+{counts['campus_assessments']} campus records" if counts["campus_assessments"] else None,
                 delta_color="off",
                 help="Buildings only. Campus records hold a whole campus's totals and are counted "
                      "separately, never added to the building counts on this page.")
    r1[1].metric("Reported, usable data", f"{int((b['data_status'] == 'Reported').sum()):,}")
    r1[2].metric("Did not report", f"{int((b['data_status'] == 'Not submitted').sum()):,}")
    r1[3].metric("Would exceed 2025–29 limit" if pre_limits else "Over 2025–29 limit", f"{int(over.sum()):,}")
    r2 = st.columns(4)
    r2[0].metric(f"Projected annual ACP (if {emissions_year} repeats)" if pre_limits else "Est. annual ACP (2025–29)",
                 _money(acp.sum()) if acp.notna().any() else "N/A",
                 help=(f"Exact: ${acp.sum():,.0f}/yr. Uses each building's official 2025–29 standard where the "
                       "City publishes one, otherwise its sector default, at $234 per metric ton. Excludes "
                       "State-owned and vacant buildings." if acp.notna().any() else
                       "No building has an ACP estimate."))
    r2[1].metric("Not yet covered (2030)", f"{int(status.eq('Not yet covered').sum()):,}")
    r2[2].metric("Not subject (State / Vacant)", f"{int(not_subject.sum()):,}")
    r2[3].metric("Compliance unknown", f"{int(unknown.sum()):,}",
                 help="Data incomplete, coverage year missing, under City review, or pending reporting.")
    st.caption("Not an official City of Boston determination.")

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
