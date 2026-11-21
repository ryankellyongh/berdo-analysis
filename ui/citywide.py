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
    #City confirms 2025-29 compliance, but the data can't be checked against later limits
    ("Meets 2025–29 limit; later periods unknown", "#7C8DA6", {"Meets 2025–29 limit; later periods unknown"}),
    ("Not yet covered",        "#8E4EC6", {"Not yet covered"}),
    ("Assessed with a portfolio or campus", "#0090FF",
     {"Assessed in a Building Portfolio", "Assessed at campus level", "Campus member (water only)"}),
    ("Under City review or pending", "#D6409F", {"Under City review", "Pending reporting (City)"}),
]
OTHER_GROUP, OTHER_COLOR = "Not assessed or data incomplete", "#8B8D98"

#The map shows five plain-language groups; the detailed groups above stay in the data,
#the headline counts, and the category table.
MAP_GROUPS = [
    ("Over its 2025–29 limit now", "#E5484D", {"Over its 2025–29 limit"}),
    ("Over the 2030–34 limit", "#F76B15", {"Fails 2030–34"}),
    ("On track through 2030–34", "#30A46C", {"Compliant through 2034", "Compliant through 2039+"}),
    ("Not yet covered", "#8E4EC6", {"Not yet covered"}),
    ("Other or unknown", "#8B8D98", None),        #everything else, including later-unknown
]
MAP_HIDDEN_BY_DEFAULT = {"Not yet covered", "Other or unknown"}
NO_TYPE = "No property type (mostly not reported)"
UNMAPPED_TYPE = "Type not in the BERDO list"


def map_group(status_group: str) -> str:
    for name, _, members in MAP_GROUPS:
        if members and status_group in members:
            return name
    return MAP_GROUPS[-1][0]


def _map_color(group):
    return next((c for n, c, _ in MAP_GROUPS if n == group), OTHER_COLOR)
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
            #2025-29 confirmed by the City; later periods can't be assessed without a
            #limit, intensity, and floor area, so don't imply a 2030-34 result.
            df.at[i, "status_group"] = "Meets 2025–29 limit; later periods unknown"
            continue
        g = calculate_compliance_gap(float(ghg), float(sqft), None, limits=lim)
        df.at[i, "status_group"] = ("Fails 2030–34" if not g[1]["compliant"] else
                                    "Compliant through 2034" if not g[2]["compliant"] else
                                    "Compliant through 2039+")
    #Category: the BERDO use, or why there isn't one (no type reported vs. a type not in Appendix A)
    has_type = df["property_type"].fillna("").astype(str).str.strip().ne("")
    df["berdo_category"] = df["property_type"].map(map_property_type)
    df.loc[df["berdo_category"].isna() & ~has_type, "berdo_category"] = NO_TYPE
    df["berdo_category"] = df["berdo_category"].fillna(UNMAPPED_TYPE)
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

    b = b.assign(map_group=b["status_group"].map(map_group))
    present = [n for n, _, _ in MAP_GROUPS if n in set(b["map_group"])]
    #Two dropdowns share one row; the status filter gets its own full-width row as pills,
    #so long status names are never cut off and every control lines up.
    c1, c2 = st.columns(2, vertical_alignment="bottom")
    with c1:
        cats = ["All categories"] + sorted(c for c in b["berdo_category"].unique() if c not in (NO_TYPE, UNMAPPED_TYPE))
        cat = st.selectbox("Building category", cats, key="cw_map_cat")
    with c2:
        base = st.selectbox("Basemap", list(basemaps), key="cw_map_base")
    show = st.pills("Status", present, selection_mode="multi", key="cw_map_status",
                    default=[g for g in present if g not in MAP_HIDDEN_BY_DEFAULT]) or []
    m = b[b["map_group"].isin(show) & b["lat"].notna()]
    if cat != "All categories":
        m = m[m["berdo_category"] == cat]
    if m.empty:
        st.caption("No buildings match these filters.")
        return

    #One dot per location, coloured by the most serious status there and sized by
    #the combined floor area of the buildings at that spot.
    order = {n: i for i, (n, _, _) in enumerate(MAP_GROUPS)}
    m = m.assign(_r=m["map_group"].map(order).fillna(len(order)),
                 _k=m["lat"].round(5).astype(str) + "," + m["lon"].round(5).astype(str),
                 _addr=m["Building Address"].fillna("Address not reported").astype(str),
                 _sqft=pd.to_numeric(m["gross_floor_area"], errors="coerce").fillna(0)).sort_values("_r")
    pts = m.groupby("_k", sort=False).agg(
        lat=("lat", "first"), lon=("lon", "first"), group=("map_group", "first"),
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
                              legendgroup=g, marker=dict(size=p["size"], color=_map_color(g), opacity=0.92),
                              hovertext=hover, hoverinfo="text",
                              hoverlabel=dict(bgcolor="white", bordercolor=_map_color(g),
                                              font=dict(color="#1C2024", size=12))))
    fig.update_layout(**{key: dict(style=basemaps[base], center=dict(lat=42.32, lon=-71.08), zoom=11.2),
                         "height": 640, "margin": dict(t=0, b=80, l=0, r=0),
                         "legend": dict(orientation="h", yanchor="top", y=-0.01, x=0,
                                        traceorder="reversed", itemsizing="constant",
                                        font=dict(size=12))})
    st.plotly_chart(fig, use_container_width=True)
    unmapped = int((b["map_group"].isin(show) & b["lat"].isna()).sum())
    n_bldg, n_dots = len(m), len(pts)
    caption = f"Showing {n_bldg:,} building{'s' if n_bldg != 1 else ''}"
    if n_dots < n_bldg:
        caption += (f" as {n_dots:,} dots. Buildings at the same location share one dot; "
                    "hover over a dot to see them all.")
    else:
        caption += "."
    caption += " Larger dots are larger buildings."
    if unmapped:
        caption += (f" {unmapped:,} matching building{'s' if unmapped != 1 else ''} "
                    f"{'aren’t' if unmapped != 1 else 'isn’t'} shown because "
                    f"{'they have' if unmapped != 1 else 'it has'} only a street name, with no number to map.")
    st.caption(caption)


def building_search_box(key="cw_lookup"):
    """
    "Look up a building" at the top of the Overview, open to everyone: it fills in the
    Address Lookup tab, so an owner's first step doesn't need the access code.
    """
    def send():
        q = st.session_state.get(key, "").strip()
        if q:
            st.session_state["lookup_address"] = q

    with st.container(border=True):
        c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
        c1.text_input("Look up a building", key=key, placeholder="Enter a street address, e.g. 1 Beacon St",
                      on_change=send)
        c2.button("Look up", key=f"{key}_go", on_click=send, use_container_width=True, type="primary")
        if st.session_state.get(key, "").strip() and \
                st.session_state.get("lookup_address") == st.session_state[key].strip():
            st.caption("Open the **Address Lookup** tab to see this building's evidence, limits, and options.")


def render_citywide_tab(page, coords_path="data/berdo_coordinates.csv",
                        show_lookup=False, require_access=False, show_map=False):
    """
    Citywide "Now": headline counts and the category table, for the selected reporting year.
    Totals only, so no access code by default. The building map now lives on the Outreach
    tab; show_map, show_lookup, and require_access restore the old standalone Overview.
    """
    year = page.selected_year
    if show_lookup:
        building_search_box()
    st.write(f"Reporting and emissions status for every covered building in the {year} dataset. "
             "Totals only: no building is identified here.")
    if require_access and not city_access():
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
    #No delta badge: it made this card taller than the rest. The campus count is in the caption.
    r1[0].metric("Covered buildings", f"{counts['buildings']:,}",
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
    note = "Not an official City of Boston determination."
    if counts["campus_assessments"]:
        note = (f"Building counts exclude {counts['campus_assessments']:,} campus records, which hold a "
                f"whole campus's totals. {note}")
    st.caption(note)

    if show_map:
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
                     "_acp": acp_g.sum() if acp_g.notna().any() else None})
    table = pd.DataFrame(rows)
    #Named categories first (largest first), then the two rows without a BERDO use
    table["_last"] = table["Category"].isin([NO_TYPE, UNMAPPED_TYPE])
    table = table.sort_values(["_last", "Buildings"], ascending=[True, False])
    table["Est. annual ACP"] = table["_acp"].map(lambda v: "—" if pd.isna(v) else f"${v:,.0f}")
    st.dataframe(table.drop(columns=["_acp", "_last"]), use_container_width=True, hide_index=True,
                 column_config={"Est. annual ACP": st.column_config.TextColumn(
                     help="Annual ACP for buildings over their 2025–29 limit. — means no building in the "
                          "category has an estimate; it does not mean $0.")})
    st.caption("— means no ACP estimate is available, not $0. Buildings with no property type mostly did "
               "not report; a type not in the BERDO list needs a person to classify it.")
