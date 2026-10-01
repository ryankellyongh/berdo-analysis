import pandas as pd
from types import SimpleNamespace
import re
import plotly.graph_objects as go
import streamlit as st
from pathlib import Path

from berdo.regulations import (
    SOURCES_REGISTER,
    SOURCES_VERIFIED_ON,
)
from berdo.emissions import (
    effective_grid_ef,
)
from berdo.data import (
    MissingColumnsError,
    detect_data_year,
    lookup_owner_portfolio,
    prepare_dataframe,
)
from ui.address_lookup import (
    render_address_lookup_tab,
)
from ui.portfolio import (
    render_portfolio_section,
)
from ui.retrofit import (
    render_retrofit_optimizer_tab,
)
from ui.planner import (
    render_emissions_planner_tab,
)

#PROJECT MAP: where to find things
#berdo/regulations.py   Official tables: limits, grid factors, RPS, fuel factors, links,
#                       deadlines, REC prices, incentives, units, Sources & verification
#berdo/schema.py        The City's column names by field (add new names here)
#berdo/emissions.py     Rules and calculations: limits, blended standards, coverage,
#                       compliance gaps, City statuses, screening, grid, RECs, planner model
#berdo/data.py          Loading and preparing data, year detection, campus rows,
#                       linking buildings across years, lookups
#berdo/pdf_export.py    The one-page PDF summary
#ui/address_lookup.py   Address Lookup tab
#ui/portfolio.py        Owner Portfolio tab
#ui/retrofit.py         Retrofit & Incentives tab
#ui/planner.py          Emissions Planner tab
#ui/common.py           Small helpers the tabs share
#app.py (this file)     Page setup, cached data loading, sidebar, and tabs
#tests/                 Run with: python run_tests.py

#Page config

st.set_page_config(
    page_title="BERDO Priority Screening Tool",
    layout="wide"
)


@st.cache_data(show_spinner=False)
def _load_single_csv(file_path: Path) -> pd.DataFrame:
    try:
        return prepare_dataframe(pd.read_csv(file_path))
    except MissingColumnsError as e:
        st.error(f"Missing required columns in {file_path.name}:")
        st.write(e.missing)
        st.write("Available columns:", e.available)
        st.stop()


@st.cache_data(show_spinner=False)
def load_all_years() -> dict[int, pd.DataFrame]:
    """
    Returns a dict mapping year (int) → DataFrame.

    Discovery rules (in priority order):
      1. berdo_<year>.csv files  →  multi-year mode
      2. berdo.csv               →  single-year fallback (keyed as year 0)
    """
    #Streamlit Cloud runs from repo root, so data/ resolves correctly.
    #Also check relative to app.py location as fallback.
    
    data_dir = Path("data")
    if not data_dir.exists() or not any(data_dir.glob("berdo_*.csv")):
        data_dir = Path(__file__).parent.parent / "data"
    year_files = sorted(data_dir.glob("berdo_*.csv"))

    year_map: dict[int, pd.DataFrame] = {}
    for fp in year_files:
        stem = fp.stem  #e.g. "berdo_2023"
        try:
            year = int(stem.split("_")[1])
        except (IndexError, ValueError):
            continue
        #Datasets are labeled by reporting year and cover the prior calendar year's energy
        #use. The energy-use year is read from the data when possible (see
        #detect_data_year), so a misnamed file is still labeled correctly; otherwise it
        #comes from the file name (reporting year - 1).
        df_year = _load_single_csv(fp)
        detected = detect_data_year(df_year)
        reporting_year = detected + 1 if detected else year
        df_year = df_year.assign(data_year=reporting_year - 1, source_file=fp.name)
        if reporting_year in year_map:
            #Two files cover the same year: keep the one whose name matches it
            kept = year_map[reporting_year]
            if kept["source_file"].iat[0] == f"berdo_{reporting_year}.csv":
                year_map[reporting_year] = kept.assign(duplicate_file=fp.name)
                continue
            df_year = df_year.assign(duplicate_file=kept["source_file"].iat[0])
        year_map[reporting_year] = df_year

    if not year_map:
        #Fallback: single legacy file
        
        legacy = data_dir / "berdo.csv"
        if not legacy.exists():
            st.error(
                "Dataset not found. Place a CSV at data/berdo.csv, "
                "or use per-year files named data/berdo_<year>.csv "
                "(e.g. data/berdo_2023.csv)."
            )
            st.stop()
        year_map[0] = _load_single_csv(legacy)

    return year_map

#App layout

all_years = load_all_years()
years_sorted = sorted(y for y in all_years if y != 0)
multi_year_mode = len(years_sorted) >= 2

#Sidebar: year selector -
if multi_year_mode:
    st.sidebar.header("Data year")
    #Flag files whose name doesn't match the year their data covers
    for _yr, _df in all_years.items():
        if "source_file" not in _df.columns or _yr == 0:
            continue
        _fname = _df["source_file"].iat[0]
        if _fname != f"berdo_{_yr}.csv":
            st.sidebar.warning(
                f"{_fname} contains {_yr - 1} energy use, so it's shown as reporting year {_yr}. "
                f"Rename it berdo_{_yr}.csv to avoid confusion."
            )
        if "duplicate_file" in _df.columns:
            st.sidebar.warning(
                f"{_df['duplicate_file'].iat[0]} covers the same year as {_fname} and isn't shown. "
                "Remove or rename one of them."
            )
    selected_year = st.sidebar.radio(
        "Select reporting year to screen:",
        options=years_sorted,
        index=len(years_sorted) - 1,
        format_func=lambda y: f"{y} ({y - 1} energy use)",
        horizontal=False,
    )
    df_full = all_years[selected_year]
    show_yoy = st.sidebar.checkbox("Show year-over-year comparison", value=True, key="sidebar_show_yoy")
else:
    selected_year = years_sorted[0] if years_sorted else 0
    df_full = all_years[selected_year]
    show_yoy = False

#Sidebar: grid decarbonization scenario
st.sidebar.header("Grid decarbonization scenario")
show_grid_decarb = st.sidebar.checkbox(
    "Show grid decarbonization scenario",
    value=False,
    key="sidebar_grid_decarb",
    help=(
        "Projects future GHG intensity assuming the ISO-NE grid cleans up "
        "per the City of Boston's official projected emissions factors "
        "(Appendix B, BERDO Policies & Procedures v5, September 2026). "
        "Fossil fuel use is held constant."
    ),
)
use_reported_share = True   #also applies to the REC comparison when the scenario is off
if show_grid_decarb:
    use_reported_share = st.sidebar.checkbox(
        "Use each building's reported electricity share",
        value=True,
        key="sidebar_use_reported_share",
        help=(
            "Uses the City-reported electricity emissions ÷ total emissions "
            "(available from the 2024 dataset onward). Buildings without a "
            "breakdown use the slider below. Uncheck to apply the slider to every building."
        ),
    )
    elec_share_pct = st.sidebar.slider(
        "Electricity share of GHG emissions (%)",
        min_value=0,
        max_value=100,
        value=50,
        step=5,
        key="sidebar_elec_share",
        help=(
            "Used when a building has no reported electricity breakdown, or for "
            "every building if the option above is unchecked. For reference, the "
            "median 2024–2025 building gets about 37% of its emissions from electricity."
        ),
    )
    elec_share = elec_share_pct / 100.0
    _data_year = (selected_year - 1) if selected_year else 2025
    base_ef = effective_grid_ef(_data_year)
    ef_2050 = effective_grid_ef(2050)
    st.sidebar.caption(
        f"Base year grid EF ({_data_year}, the year of energy use): **{base_ef:.0f} kg/MWh** "
        f"(Appendix B × RPS Class I). Projected EF at 2050: **{ef_2050:.0f} kg/MWh** "
        f"({round((1 - ef_2050 / base_ef) * 100)}% cleaner)."
    )
else:
    elec_share = None

with st.sidebar.expander("Sources & verification"):
    st.caption(
        f"Each constant this tool uses, checked against official sources on {SOURCES_VERIFIED_ON}. "
        "Corrected = the value was wrong and has been fixed. Unverified = no official source "
        "was found, so treat the figure as an estimate."
    )
    st.dataframe(
        pd.DataFrame(SOURCES_REGISTER, columns=["Item", "Status", "Source"]),
        hide_index=True, use_container_width=True,
    )

#Page header
st.title("BERDO Priority Screening Tool")
st.write(
    "Enter a Boston building address to see its BERDO compliance status, fine exposure, "
    "and a matched incentive plan for funding decarbonization."
)

if multi_year_mode:
    year_range_str = f"{years_sorted[0]}–{years_sorted[-1]}"
    st.info(
        f"Showing reporting year **{selected_year}**, which covers **{selected_year - 1}** energy use. "
        f"Multi-year data loaded: {year_range_str}. "
        "Use the sidebar to switch years or toggle the trend view."
    )
else:
    st.info(
        "This is a screening tool for analysis purposes. "
        "It is not an official City of Boston BERDO compliance determination."
    )

#Everything the tabs need from the page: the data and the sidebar settings
page = SimpleNamespace(
    df_full=df_full, all_years=all_years, selected_year=selected_year,
    multi_year_mode=multi_year_mode, show_yoy=show_yoy, show_grid_decarb=show_grid_decarb,
    elec_share=elec_share, use_reported_share=use_reported_share,
)

tab_address, tab_portfolio, tab_retrofit_optimizer, tab_planner = st.tabs([
    "Address Lookup", "Owner Portfolio", "Retrofit & Incentives", "Emissions Planner"
])


    #Tab 2: owner portfolio lookup


with tab_address:
    render_address_lookup_tab(page)


with tab_portfolio:
    st.write(
        "Enter a property owner name to group all their buildings into a BERDO "
        "Building Portfolio and see combined compliance exposure under the blended "
        "emissions standard."
    )
    owner_input = st.text_input(
        "Enter property owner name",
        placeholder="Example: City of Boston",
        key="owner_input",
    )

    if owner_input:
        portfolio_result = lookup_owner_portfolio(df_full, owner_input)

        if portfolio_result is None:
            st.warning("No buildings found for that owner name in the dataset.")
        else:
            st.subheader(f"Buildings found: {len(portfolio_result)}")

            display_cols = [
                "Building Address", "Property Owner Name", "Property Type",
                "Gross Floor Area", "Site EUI", "GHG Intensity (kgCO2e/sqft)",
                "Compliance Status", "Data Status", "BERDO Status",
            ]
            st.dataframe(portfolio_result[display_cols], use_container_width=True, hide_index=True)

            if len(portfolio_result) == 1:
                st.info(
                    "Only one building found for this owner. "
                    "A Building Portfolio requires multiple buildings. "
                    "Use the Address Lookup tab for single-building analysis."
                )
            else:
                st.markdown("---")
                render_portfolio_section(
                    portfolio_result,
                    selected_year=selected_year,
                    elec_share=elec_share if show_grid_decarb else None,
                    all_years=all_years,
                    show_yoy=show_yoy,
                    use_reported_share=use_reported_share,
                )
                

#Tab 3: Retrofit & Incentives (merged Retrofit Estimator + Incentive Optimizer)

with tab_retrofit_optimizer:
    opt_prefill = st.session_state.get("optimizer_prefill", {})
    render_retrofit_optimizer_tab(page, prefill=opt_prefill)


#Tab 4: Emissions Planner

with tab_planner:
    planner_prefill = st.session_state.get("planner_prefill", {})
    render_emissions_planner_tab(
        prefill=planner_prefill,
        show_grid_decarb=show_grid_decarb,
        elec_share=elec_share,
        use_reported_share=use_reported_share,
    )
