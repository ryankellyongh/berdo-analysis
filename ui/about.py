"""
About tab: what the tool is for, how its numbers are calculated, sources, and limits.
"""
import streamlit as st

from berdo.regulations import ACP_RATE, SOURCES_VERIFIED_ON


def render_about(years):
    st.markdown("## About this tool")
    st.write(
        "The BERDO Priority Screening Tool helps outreach staff and building owners understand "
        "Boston's Building Emissions Reduction and Disclosure Ordinance (BERDO): who needs help "
        "reporting, which buildings may exceed their emissions limits, and what owners can do next."
    )
    #The two cards sit in a keyed container so site_theme.py can give them equal heights
    with st.container(key="about_cards"):
        c1, c2 = st.columns(2)
        with c1:
            with st.container(border=True):
                st.markdown("#### What each page provides")
                st.markdown(
                    "- **Address Lookup:** a building-level profile with reported energy use and emissions, "
                    "applicable limits by compliance period, estimated ACP exposure, compliance pathways, "
                    "and a one-page PDF summary.\n"
                    "- **Outreach:** a prioritized list of buildings that may require follow-up: City "
                    "Action Needed results, buildings estimated to be at risk, and buildings that did not "
                    "report. Restricted to authorized users.\n"
                    "- **Citywide:** aggregate reporting and compliance status for the selected year, "
                    "buildings by compliance period, and multi-year trends in energy use and emissions.\n"
                    "- **Portfolios:** approved City Building Portfolios and owner-level summaries with "
                    "blended emissions standards.\n"
                    "- **Retrofits:** retrofit cost ranges, avoided ACP, simple payback, and incentive "
                    "programs to evaluate.\n"
                    "- **Planner:** year-by-year emissions and ACP projections through 2050, including "
                    "planned projects and grid decarbonization."
                )
        with c2:
            with st.container(border=True):
                st.markdown("#### How the figures are calculated")
                st.markdown(
                    f"- **Alternative Compliance Payment (ACP):** estimated at ${ACP_RATE} per metric ton "
                    "of CO₂e above the applicable emissions standard, as set by the BERDO ordinance.\n"
                    "- **Avoided ACP:** baseline ACP less the ACP remaining after a project. Simple payback "
                    "combines avoided ACP with estimated energy savings.\n"
                    "- **Reporting years:** each reporting year contains the previous calendar year's "
                    "energy use and emissions.\n"
                    "- **Missing values:** shown as N/A or “—” when a figure cannot be estimated (incomplete "
                    "data, not yet covered, or not assessed); never shown as $0.\n"
                    "- **Incentives:** listed programs are leads to verify. Only confirmed funding reduces "
                    "net project cost.\n"
                    "- **Projections:** emissions are held at last reported levels unless a scenario is "
                    "applied. Predictions are screening estimates, not City determinations."
                )
    with st.container(border=True):
        st.markdown("#### Sources")
        st.markdown(
            f"- City of Boston BERDO data disclosures, reporting years {years[0]}–{years[-1]} (Analyze Boston).\n"
            "- BERDO 2.0 emissions standards and the BERDO Emissions Factors List (City of Boston).\n"
            "- City of Boston Street Address Management (SAM) addresses, for map locations.\n"
            f"- Regulations, pathways, and program details last verified {SOURCES_VERIFIED_ON}."
        )
    st.warning(
        "**Screening tool, not an official determination.** Results are estimates from public data "
        "and may differ from the City's assessment. Confirm compliance questions with the BERDO team "
        "before acting. Not financial, legal, or tax advice."
    )
