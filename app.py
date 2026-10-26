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

#Header: reporting year applies to every tab, so it sits beside the heading
site_theme.apply_theme()
_topbar = st.container()
_hero, _year_col = st.columns([3, 1], vertical_alignment="bottom")
with _hero:
    site_theme.render_hero()
with _year_col:
    selected_year = st.selectbox(
        "Reporting year", years_sorted, index=len(years_sorted) - 1, key="settings_year",
        help="Applies to every tab. Each reporting year holds the previous calendar year's data.")
emissions_year = selected_year - 1

#Projection settings shared by Address Lookup, Owner Portfolio, and Emissions Planner
with st.expander("Projection settings: grid decarbonization", expanded=False):
    c1, c2, c3 = st.columns([1.2, 1.4, 1.4], vertical_alignment="center")
    with c1:
        show_grid_decarb = st.toggle(
            "Grid decarbonization scenario", key="grid_on",
            help="Projects future emissions as the ISO-NE grid cleans up (BERDO Appendix B × RPS "
                 "Class I). Only electricity emissions change; fuels are held constant.")
    with c2:
        use_reported_share = st.toggle(
            "Use each building's reported energy mix", value=True, key="grid_reported_mix",
            help="Uses the building's reported electricity emissions. The share below is used only "
                 "for buildings without a breakdown.")
    with c3:
        elec_share = st.slider("Electricity share when not reported (%)", 0, 100, 50, 5,
                               key="grid_share", disabled=not show_grid_decarb) / 100.0
    _b, _e = effective_grid_ef(emissions_year), effective_grid_ef(2050)
    st.caption(f"Grid factor {_b:.0f} kg/MWh in {emissions_year} (the emissions year) → {_e:.0f} kg/MWh "
               f"in 2050 ({round((1 - _e / _b) * 100)}% cleaner).")

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

with _topbar:
    site_theme.render_topbar(f"Reporting year {selected_year} · {emissions_year} energy use")

tabs = st.tabs(["Citywide Overview", "Address Lookup", "Owner Portfolio",
                "Retrofit & Incentives", "Emissions Planner", "2025 Outlook"])

with tabs[0]:
    render_citywide_tab(page, coords_path=str(DATA_DIR / "berdo_coordinates.csv"))

with tabs[1]:
    render_address_lookup_tab(page)

with tabs[2]:
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
    render_retrofit_optimizer_tab(page, st.session_state.get("optimizer_prefill", {}))

with tabs[4]:
    render_emissions_planner_tab(st.session_state.get("planner_prefill", {}),
                                 show_grid_decarb=show_grid_decarb, elec_share=page.elec_share,
                                 use_reported_share=use_reported_share)

with tabs[5]:
    render_outlook_tab(page)

site_theme.render_footer(
    "Screening tool · Not an official City of Boston BERDO compliance determination",
    f"Data: City of Boston BERDO disclosure ({years_sorted[0]}–{years_sorted[-1]})",
)
