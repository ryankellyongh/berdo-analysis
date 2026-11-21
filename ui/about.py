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
    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("#### What each page does")
            st.markdown(
                "- **Citywide Overview:** look up any building, then (with the access code) reporting "
                "and emissions status for every covered building, with a map.\n"
                "- **Outreach:** buildings without a 2025 City result, ranked by estimated risk, with a "
                "detail panel and map. Access code required.\n"
                "- **Trends:** how energy use and emissions have changed over time, and how much of "
                "the change comes from a cleaner grid.\n"
                "- **Address Lookup:** one building's evidence, limits, estimated ACP, compliance "
                "pathways, and a one-page PDF summary.\n"
                "- **Owner Portfolio:** the City's approved Building Portfolios, found by portfolio ID, name, "
                "or member owner; owner-name matches are shown as candidates when no approved portfolio fits.\n"
                "- **Retrofit & Incentives:** project cost, avoided ACP, payback, and programs to investigate.\n"
                "- **Emissions Planner:** year-by-year emissions and ACP with planned projects."
            )
    with c2:
        with st.container(border=True):
            st.markdown("#### How the numbers work")
            st.markdown(
                f"- **ACP** (Alternative Compliance Payment) is estimated at ${ACP_RATE} per metric ton "
                "of CO₂e above a building's limit.\n"
                "- **Avoided ACP** is baseline ACP minus the ACP still owed after a project. Payback "
                "uses avoided ACP plus energy savings.\n"
                "- **N/A** means a value can't be estimated (missing data, not yet covered, or not "
                "assessed). It never means $0.\n"
                "- Potential incentives are leads to verify. Only confirmed funding reduces net cost.\n"
                "- Each reporting year holds the previous calendar year's energy and emissions."
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
