"""
BERDO Compliance Planner: the Streamlit entry point.

This file only loads data, builds the shared `page` context, and lays out the tabs.
Every calculation lives in berdo/ (tested by tests/), and every tab's interface
lives in ui/. Nothing here computes compliance, ACP, or payback.
"""
import re
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import streamlit as st

import site_theme
from berdo.data import MissingColumnsError, lookup_owner_portfolio, prepare_dataframe
from berdo.emissions import effective_grid_ef
from berdo.predictions import load_predictions
from ui.about import render_about
from ui.address_lookup import render_address_lookup_tab
from ui.citywide import render_citywide_tab
from ui.outlook import render_outlook_tab
from ui.planner import render_emissions_planner_tab
from ui.portfolio import render_portfolio_section
from ui.retrofit import render_retrofit_optimizer_tab

st.set_page_config(page_title="BERDO · Outreach workspace", layout="wide")

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"


#Only files named exactly berdo_<year>.csv are yearly disclosures. Exports and lookups
#such as berdo_2026_unmapped_buildings.csv or berdo_coordinates.csv are not loaded.
YEAR_FILE = re.compile(r"^berdo_(\d{4})\.csv$")


@st.cache_data(show_spinner="Loading BERDO data…")
def load_all_years(data_dir: str):
    """
    (reporting year -> prepared DataFrame, list of problems). A file that can't be
    loaded is skipped and reported, so one bad file never stops the whole app.
    """
    years, problems = {}, []
    for fp in sorted(Path(data_dir).glob("berdo_*.csv")):
        m = YEAR_FILE.match(fp.name)
        if not m:
            continue
        try:
            years[int(m.group(1))] = prepare_dataframe(pd.read_csv(fp, low_memory=False))
        except MissingColumnsError as e:
            problems.append(f"{fp.name}: missing required columns {', '.join(map(str, e.missing))}")
        except Exception as e:                  # noqa: BLE001 - report, don't crash
            problems.append(f"{fp.name}: {type(e).__name__}: {e}")
    return years, problems


all_years, load_problems = load_all_years(str(DATA_DIR))
if load_problems:
    st.warning("Some data files were skipped:\n\n" + "\n".join(f"- {p}" for p in load_problems))
if not all_years:
    st.error("No usable data found. Add data/berdo_<year>.csv files (see convert_berdo_2026.py).")
    st.stop()
years_sorted = sorted(all_years)
multi_year_mode = len(years_sorted) >= 2

#Shared settings. Several tabs show the same control (reporting year, grid scenario);
#each copy has its own widget key and they are kept in sync through one shared value,
#so changing a control on any tab changes it everywhere.
TAB_IDS = ["citywide", "lookup", "portfolio", "retrofit", "planner"]
SHARED = {"selected_year": years_sorted[-1], "grid_on": False, "grid_reported_mix": True, "grid_share": 50}
for _k, _v in SHARED.items():
    st.session_state.setdefault(_k, _v)
if st.session_state["selected_year"] not in all_years:
    st.session_state["selected_year"] = years_sorted[-1]


def _sync(shared_key, src):
    st.session_state[shared_key] = st.session_state[f"{shared_key}_{src}"]
    for t in TAB_IDS:
        if t != src:
            st.session_state[f"{shared_key}_{t}"] = st.session_state[shared_key]


def _bind(shared_key, tab_id):
    """Widget key for one tab's copy of a shared control, seeded from the shared value."""
    k = f"{shared_key}_{tab_id}"
    if k not in st.session_state:
        st.session_state[k] = st.session_state[shared_key]
    return k


def page_heading(tab_id):
    """Heading and reporting-year selector at the top of each tab."""
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    with c1:
        site_theme.render_hero()
    with c2:
        st.selectbox("Reporting year", years_sorted, format_func=str,
                     key=_bind("selected_year", tab_id), on_change=_sync, args=("selected_year", tab_id),
                     help="Applies to every tab. Each reporting year holds the previous calendar year's data.")


def projection_settings(tab_id):
    """Grid decarbonization settings, shown on the tabs whose projections use them."""
    ey = st.session_state["selected_year"] - 1
    with st.expander("Projection settings: grid decarbonization", expanded=st.session_state["grid_on"]):
        c1, c2, c3 = st.columns([1.2, 1.4, 1.4], vertical_alignment="center")
        with c1:
            st.toggle("Grid decarbonization scenario", key=_bind("grid_on", tab_id),
                      on_change=_sync, args=("grid_on", tab_id),
                      help="Projects future emissions as the ISO-NE grid cleans up (BERDO Appendix B × "
                           "RPS Class I). Only electricity emissions change; fuels are held constant.")
        with c2:
            st.toggle("Use each building's reported energy mix", key=_bind("grid_reported_mix", tab_id),
                      on_change=_sync, args=("grid_reported_mix", tab_id),
                      help="Uses the building's reported electricity emissions. The share at right is "
                           "used only for buildings without a breakdown.")
        with c3:
            st.slider("Electricity share when not reported (%)", 0, 100, step=5,
                      key=_bind("grid_share", tab_id), on_change=_sync, args=("grid_share", tab_id),
                      disabled=not st.session_state["grid_on"])
        _b, _e = effective_grid_ef(ey), effective_grid_ef(2050)
        st.caption(f"Grid factor {_b:.0f} kg/MWh in {ey} (the emissions year) → {_e:.0f} kg/MWh in 2050 "
                   f"({round((1 - _e / _b) * 100)}% cleaner). Shared by Address Lookup, Owner Portfolio, "
                   "and Emissions Planner.")


selected_year = st.session_state["selected_year"]
show_grid_decarb = bool(st.session_state["grid_on"])
use_reported_share = bool(st.session_state["grid_reported_mix"])
elec_share = st.session_state["grid_share"] / 100.0

page = SimpleNamespace(
    selected_year=selected_year,
    all_years=all_years,
    df_full=all_years[selected_year],
    multi_year_mode=multi_year_mode,
    show_yoy=multi_year_mode,
    show_grid_decarb=show_grid_decarb,
    elec_share=elec_share if show_grid_decarb else None,
    use_reported_share=use_reported_share,
    predictions=load_predictions(ROOT / "analysis" / "predictions_2026" / "predictions_2026_pending.csv"),
)

#Header row: brand at left; the page tabs are styled into the same row (site_theme)
site_theme.apply_theme()
with st.container(key="site_header"):
    site_theme.render_brand()
with st.container(key="site_nav"):
    tabs = st.tabs(["Citywide Overview", "Address Lookup", "Owner Portfolio",
                    "Retrofit & Incentives", "Emissions Planner", "About"])

with tabs[0]:
    page_heading("citywide")
    render_citywide_tab(page, coords_path=str(DATA_DIR / "berdo_coordinates.csv"))
    if st.session_state.get("city_access_granted"):
        st.markdown("---")
        with st.expander("2025 Outlook: predicted results for buildings without a City result"):
            render_outlook_tab(page)

with tabs[1]:
    page_heading("lookup")
    projection_settings("lookup")
    render_address_lookup_tab(page)

with tabs[2]:
    page_heading("portfolio")
    projection_settings("portfolio")
    owner = st.text_input("Enter property owner name", placeholder="Example: City of Boston", key="owner_input")
    if owner:
        result = lookup_owner_portfolio(page.df_full, owner)
        if result is None:
            st.warning("No buildings found for that owner name.")
        else:
            st.caption(f"{len(result)} buildings whose owner name contains “{owner}”. Name matches are "
                       "candidates: confirm common ownership before treating them as a portfolio.")
            st.dataframe(result[[c for c in ("Building Address", "Property Owner Name", "Property Type",
                                             "Gross Floor Area", "BERDO Status") if c in result.columns]],
                         use_container_width=True, hide_index=True)
            if len(result) > 1:
                render_portfolio_section(result, selected_year, page.elec_share, all_years,
                                         page.show_yoy, use_reported_share=use_reported_share)
            else:
                st.info("Only one building found; use Address Lookup for single-building analysis.")

with tabs[3]:
    page_heading("retrofit")
    render_retrofit_optimizer_tab(page, st.session_state.get("optimizer_prefill", {}))

with tabs[4]:
    page_heading("planner")
    projection_settings("planner")
    render_emissions_planner_tab(st.session_state.get("planner_prefill", {}),
                                 show_grid_decarb=show_grid_decarb, elec_share=page.elec_share,
                                 use_reported_share=use_reported_share)

with tabs[5]:
    render_about(years_sorted)

site_theme.render_footer(
    "Screening tool · Not an official City of Boston BERDO compliance determination",
    f"Data: City of Boston BERDO disclosure ({years_sorted[0]}–{years_sorted[-1]})",
)
