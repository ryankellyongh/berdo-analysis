"""BERDO presentation layer. Compatible with the Archive.zip app entry points."""
import html

import streamlit as st

ACCENT = "#288BE4"
NAVY = "#091F2F"

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;650;700;750&display=swap');

:root {
  --site-accent: #288BE4;
  --site-navy: #091F2F;
  --site-border: rgba(125, 137, 151, .22);
  --site-panel: rgba(125, 137, 151, .045);
  --site-radius: 16px;
}

.stApp, .stApp p, .stApp li, .stApp label,
.stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp input, .stApp textarea, .stApp button, .stApp table {
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
}
[data-testid="stIconMaterial"], .material-symbols-rounded {
  font-family: 'Material Symbols Rounded' !important;
}
.stApp { -webkit-font-smoothing: antialiased; }
.stApp h1, .stApp h2, .stApp h3, .stApp h4 {
  letter-spacing: -.035em; font-weight: 650 !important;
}
.stApp h2 { font-size: 1.65rem; line-height: 1.3; padding-top: 1.4rem; }
.stApp h3 { font-size: 1.25rem; line-height: 1.4; }
.stApp p, .stApp li { line-height: 1.65; }

/*Keep Settings and theme controls accessible.*/
header[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stDecoration"], .stDeployButton,
[data-testid="stAppDeployButton"], footer { display: none !important; }
[data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"] {
  visibility: visible !important;
}
.block-container, [data-testid="stMainBlockContainer"] {
  max-width: 1480px;
  padding: 2.5rem clamp(1.15rem, 3.7vw, 4.4rem) 3rem !important;
}

/*The masthead shares the content's left and right alignment.*/
.st-key-workspace_header {
  padding: 1.1rem 0 1.65rem;
  margin-bottom: 2.1rem;
  border-bottom: 1px solid var(--site-border);
  background: transparent !important;
  color: inherit;
}
.st-key-workspace_header [data-testid="stHorizontalBlock"]:has(.site-brand-copy) {
  align-items: center;
  flex-wrap: nowrap !important;
  gap: clamp(1.5rem, 3.8vw, 4rem) !important;
}
.st-key-workspace_header [data-testid="stColumn"]:has(.site-brand-copy) {
  flex: 0 0 215px !important; width: 215px !important; min-width: 215px !important;
}
.st-key-workspace_header [data-testid="stColumn"]:has(.st-key-workspace_navigation) {
  flex: 1 1 0 !important; width: auto !important; min-width: 0 !important;
}
.site-brand-copy { padding: 2px 0; }
.site-brand-title {
  color: var(--site-accent); font-size: 2.05rem; font-weight: 750;
  line-height: 1.05; letter-spacing: -.055em; white-space: nowrap;
}
.site-brand-subtitle {
  color: var(--site-accent); font-size: .62rem; font-weight: 700;
  letter-spacing: .14em; line-height: 1.65; margin-top: .4rem;
  white-space: nowrap; text-transform: uppercase;
}
.st-key-workspace_navigation {
  width: 100%; min-width: 0; overflow-x: auto; overflow-y: hidden;
  scrollbar-width: thin; scrollbar-color: var(--site-border) transparent;
  padding: 5px 2px 8px;
}
.st-key-workspace_navigation [data-testid="stHorizontalBlock"] {
  align-items: center; flex-wrap: nowrap !important; gap: .25rem !important;
}
.st-key-workspace_navigation [data-testid="stColumn"] {
  flex: 1 0 auto !important; width: auto !important; min-width: max-content !important;
}
.st-key-workspace_navigation .stButton > button {
  width: 100%; min-height: 46px; padding: .65rem .65rem;
  border: 0 !important; border-bottom: 2px solid transparent !important;
  border-radius: 0 !important; background: transparent !important;
  color: inherit !important; box-shadow: none !important;
}
.st-key-workspace_navigation .stButton > button p {
  font-size: .78rem !important; font-weight: 500; line-height: 1.4;
  white-space: nowrap; margin: 0; opacity: .8;
}
.st-key-workspace_navigation .stButton > button[kind="primary"] {
  border-bottom-color: var(--site-accent) !important;
  color: var(--site-accent) !important;
}
.st-key-workspace_navigation .stButton > button[kind="primary"] p {
  font-weight: 700; opacity: 1;
}
.st-key-workspace_navigation .stButton > button:hover {
  color: var(--site-accent) !important;
  background: rgba(40, 139, 228, .055) !important;
}
.st-key-header_about .stButton > button {
  margin-left: .4rem; border: 1px solid var(--site-border) !important;
  border-radius: 9px !important; padding-inline: .95rem;
}

/*About page and compatibility header.*/
.site-topbar {
  display: flex; align-items: center; justify-content: space-between;
  gap: 2rem; flex-wrap: wrap; padding: 1.1rem 0 1.65rem;
  margin-bottom: 2.1rem; border-bottom: 1px solid var(--site-border);
  background: transparent !important;
}
.site-brand { display: flex; align-items: center; }
.site-about-button, .site-about-button:visited {
  color: inherit; font-size: .84rem; font-weight: 600; text-decoration: none;
  border: 1px solid var(--site-border); border-radius: 9px;
  display: inline-flex; align-items: center; min-height: 42px; padding: 0 1rem;
}
.site-about-button:hover { color: var(--site-accent); border-color: var(--site-accent); }

/*A concise introduction above each workspace.*/
.site-hero { max-width: 850px; margin: .4rem 0 2.1rem; }
.site-hero h1 {
  font-size: clamp(1.9rem, 2.7vw, 2.65rem) !important;
  font-weight: 650 !important; letter-spacing: -.045em;
  line-height: 1.2; padding: 0; margin: 0 0 .85rem;
  text-wrap: balance;
}
.site-hero p { font-size: .99rem; opacity: .7; margin: 0; max-width: 700px; }

/*Consistent dashboard cards with room for two label lines.*/
[data-testid="stMetric"] {
  box-sizing: border-box; height: 100%; min-height: 165px;
  padding: 1.35rem 1.4rem; border: 1px solid var(--site-border);
  border-radius: var(--site-radius); background: var(--site-panel);
  box-shadow: 0 2px 4px rgba(9, 31, 47, .025);
}
[data-testid="stMetricLabel"] {
  min-height: 2.7rem; align-items: flex-start !important;
}
[data-testid="stMetricLabel"] p {
  font-size: .79rem !important; line-height: 1.45; opacity: .75;
  white-space: normal !important; overflow-wrap: anywhere;
}
[data-testid="stMetricValue"] {
  font-size: clamp(1.5rem, 2.3vw, 2.15rem) !important;
  font-weight: 650; letter-spacing: -.045em; line-height: 1.2;
}
[data-testid="stMetricDelta"] { font-size: .75rem; margin-top: .5rem; }
[data-testid="stVerticalBlockBorderWrapper"] { border-radius: var(--site-radius) !important; }
[data-testid="stExpander"] details {
  background: var(--site-panel); border: 1px solid var(--site-border) !important;
  border-radius: 12px !important;
}
[data-testid="stExpander"] summary { padding: .9rem 1rem; }
[data-testid="stAlert"] { border-radius: 12px; }
[data-testid="stAlert"] p { font-size: .9rem; }
[data-testid="stDataFrame"], [data-testid="stTable"] {
  border: 1px solid var(--site-border); border-radius: 12px; overflow: hidden;
}
[data-testid="stPlotlyChart"] {
  box-sizing: border-box; padding: .8rem; border: 1px solid var(--site-border);
  border-radius: var(--site-radius); background: var(--site-panel);
}
hr { border-color: var(--site-border) !important; margin: 1.9rem 0 !important; }

/*Search, filter and action controls.*/
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div {
  border-radius: 9px !important;
}
[data-baseweb="input"], [data-baseweb="select"] > div { min-height: 44px; }
[data-testid="stWidgetLabel"] p { font-size: .81rem; font-weight: 500; }
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {
  min-height: 43px; border-radius: 9px; padding: .6rem 1rem;
  border: 1px solid var(--site-border); font-weight: 600;
}
.stButton > button:hover, .stDownloadButton > button:hover {
  border-color: var(--site-accent); color: var(--site-accent);
}
.stButton > button[kind="primary"], [data-testid="stFormSubmitButton"] > button {
  background: var(--site-accent); border-color: var(--site-accent); color: white;
}
.stButton > button:focus-visible, .stDownloadButton > button:focus-visible,
.site-about-button:focus-visible {
  outline: 3px solid var(--site-accent); outline-offset: 3px;
}
[data-testid="stSidebar"] { border-right: 1px solid var(--site-border); }

/*Preserve blue indicators for any native tabs used inside the app.*/
[data-testid="stTabs"] [role="tablist"] { gap: .8rem; border-bottom: 1px solid var(--site-border); }
[data-testid="stTabs"] [role="tab"] {
  color: inherit !important; border-bottom: 2px solid transparent !important;
  background: transparent !important; padding: .75rem .6rem;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
  color: var(--site-accent) !important; border-bottom-color: var(--site-accent) !important;
}
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"],
[data-testid="stTabs"] .react-aria-SelectionIndicator,
[data-testid="stTabHighlight"], [data-testid="stTabsHighlight"] { display: none !important; }
[data-testid="stTabs"] [role="tabpanel"] { padding-top: 1.5rem; }

.site-footer {
  display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap;
  padding-top: 1.25rem; margin-top: 3.5rem; border-top: 1px solid var(--site-border);
  font-size: .76rem; line-height: 1.6; opacity: .65;
}

/*Theme colours come from Streamlit; no OS theme override or fixed white panels.*/
@supports (color: color-mix(in srgb, currentColor, transparent)) {
  .stApp {
    --site-border: color-mix(in srgb, currentColor 15%, transparent);
    --site-panel: color-mix(in srgb, currentColor 3%, transparent);
  }
}
@media (max-width: 1180px) {
  .st-key-workspace_header [data-testid="stHorizontalBlock"]:has(.site-brand-copy) {
    flex-wrap: wrap !important; gap: .9rem !important;
  }
  .st-key-workspace_header [data-testid="stColumn"]:has(.site-brand-copy),
  .st-key-workspace_header [data-testid="stColumn"]:has(.st-key-workspace_navigation) {
    flex: 1 1 100% !important; width: 100% !important; min-width: 0 !important;
  }
  .st-key-workspace_navigation [data-testid="stColumn"] {
    flex: 0 0 auto !important;
  }
  .st-key-workspace_navigation [data-testid="stHorizontalBlock"] {
    width: max-content !important; min-width: 100%;
  }
}
@media (max-width: 640px) {
  .block-container, [data-testid="stMainBlockContainer"] { padding-top: 2.25rem !important; }
  .st-key-workspace_header { padding-top: .5rem; margin-bottom: 1.35rem; }
  .site-brand-title { font-size: 1.9rem; }
  .site-hero { margin-bottom: 1.5rem; }
  .st-key-workspace_navigation .stButton > button { padding-inline: .7rem; }
  [data-testid="stMetric"] { min-height: 150px; padding: 1.1rem; }
  [data-testid="stPlotlyChart"] { padding: .2rem; }
}
@media (prefers-reduced-motion: reduce) {
  .stApp *, .stApp *::before, .stApp *::after {
    scroll-behavior: auto !important; transition: none !important; animation: none !important;
  }
}

/*Use one blue underline; suppress native moving selection indicators.*/
.stTabs, [data-testid="stTabs"] {
  --primary-color: #288BE4;
  --st-primary-color: #288BE4;
}
[role="tablist"] [role="tab"][aria-selected="true"],
[data-baseweb="tab"][aria-selected="true"] {
  border-bottom: 3px solid #288BE4 !important;
  box-shadow: none !important;
}
[role="tablist"] [role="tab"]::before,
[role="tablist"] [role="tab"]::after {
  display: none !important;
}
[data-baseweb="tab-highlight"],
[data-testid="stTabHighlight"],
[data-testid="stTabsHighlight"],
[data-testid="stTabsSelectionIndicator"],
.react-aria-SelectionIndicator,
.stTabs [class*="SelectionIndicator"],
[data-testid="stTabs"] [class*="SelectionIndicator"] {
  display: none !important;
  background: #288BE4 !important;
  background-color: #288BE4 !important;
}

</style>
"""


def apply_theme():
    st.markdown(_CSS, unsafe_allow_html=True)


def _brand_markup(brand="Priority screening tool"):
    return (
        '<div class="site-brand-copy">'
        '<div class="site-brand-title">BERDO</div>'
        f'<div class="site-brand-subtitle">{html.escape(brand)}</div>'
        '</div>'
    )



def render_brand(brand: str = "Priority screening tool"):
    """Render the standalone BERDO brand used by app.py."""
    st.markdown(_brand_markup(brand), unsafe_allow_html=True)


def _open_about():
    st.query_params["page"] = "about"


def _select_workspace_page(label):
    st.session_state["workspace_page"] = label


def render_workspace_header(badge: str):
    """Native buttons retain session state when switching workspace views."""
    labels = ["Citywide Overview", "Address Lookup", "Owner Portfolio",
              "Retrofit & Incentives", "Emissions Planner"]
    selected = st.session_state.get("workspace_page", labels[0])
    if selected not in labels:
        selected = labels[0]
    with st.container(key="workspace_header"):
        brand_column, navigation_column = st.columns([2, 8], gap="large", vertical_alignment="center")
        with brand_column:
            st.markdown(_brand_markup(), unsafe_allow_html=True)
        with navigation_column:
            with st.container(key="workspace_navigation"):
                columns = st.columns([1.45, 1.2, 1.25, 1.6, 1.35, .65], gap="small",
                                     vertical_alignment="center")
                for index, label in enumerate(labels):
                    with columns[index]:
                        st.button(label, key=f"header_page_{index}",
                                  type="primary" if selected == label else "secondary",
                                  on_click=_select_workspace_page, args=(label,))
                with columns[5]:
                    with st.container(key="header_about"):
                        st.button("About", key="header_about_button", on_click=_open_about)
    return selected


def render_topbar(badge: str, brand: str = "Priority screening tool", on_about: bool = False):
    page_url = "?page=workspace" if on_about else "?page=about"
    page_label = "Back to workspace" if on_about else "About"
    st.markdown(
        '<div class="site-topbar" role="banner">'
        f'<div class="site-brand">{_brand_markup(brand)}</div>'
        f'<a class="site-about-button" href="{page_url}" target="_self">{page_label}</a>'
        '</div>', unsafe_allow_html=True,
    )


def render_hero(heading: str = "Building support, with a clear next step.",
                subheading: str = "Find an outreach need, verify the evidence, and prepare an owner conversation."):
    st.markdown(
        '<div class="site-hero">'
        f'<h1>{html.escape(heading)}</h1>'
        f'<p>{html.escape(subheading)}</p>'
        '</div>', unsafe_allow_html=True,
    )


def render_header(badge: str, **kw):
    render_topbar(badge)
    render_hero(**kw)


def render_footer(left: str, right: str):
    st.markdown(
        '<div class="site-footer" role="contentinfo">'
        f'<span>{html.escape(left)}</span><span>{html.escape(right)}</span>'
        '</div>', unsafe_allow_html=True,
    )
