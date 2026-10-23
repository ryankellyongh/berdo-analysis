"""
Website-style presentation for the BERDO app: hides Streamlit's default chrome,
adds a site header and footer, and restyles tabs, panels, inputs, and buttons in City of Boston blue.

Presentation only. No calculations live here. Colours use translucent greys and
inherit text colour (blue is the only accent), so the same CSS reads well in Streamlit's light and dark themes.
"""
import html

import streamlit as st

#City of Boston brand colours: Optimistic Blue (accent) and Charles Blue (deep navy).
ACCENT = "#288BE4"
NAVY = "#091F2F"

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {{
  --site-accent: {ACCENT};
  --site-navy: {NAVY};
  --site-border: rgba(127, 127, 127, 0.24);
  --site-panel: rgba(127, 127, 127, 0.06);
  --site-muted: rgba(127, 127, 127, 0.95);
  --site-radius: 12px;
}}

/* Typography */
.stApp, .stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp input, .stApp textarea, .stApp button, .stApp table {{
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
}}
/* Keep Streamlit's icon font on icons (expander arrows, etc.) */
[data-testid="stIconMaterial"], .material-symbols-rounded {{
  font-family: 'Material Symbols Rounded' !important;
}}
h1, h2, h3, h4 {{ letter-spacing: -0.01em; font-weight: 600 !important; }}

/* Hide Streamlit's default chrome so the page reads as a website */
/* (the header itself stays, transparent, because it holds the sidebar open button) */
header[data-testid="stHeader"] {{ background: transparent; }}
/* Hide only the toolbar's actions (Fork, GitHub, menu, deploy), never the whole
   toolbar: in some Streamlit versions it also holds the sidebar open button. */
[data-testid="stToolbarActions"], [data-testid="stMainMenu"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], #MainMenu, footer, .stDeployButton,
[data-testid="stAppDeployButton"] {{ display: none !important; }}
[data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"] {{
  display: flex !important; visibility: visible !important;
}}

/* Centred content column with generous spacing */
.block-container, [data-testid="stMainBlockContainer"] {{
  max-width: 1240px; padding-top: 1.25rem !important; padding-bottom: 3rem !important;
}}

/* Workspace navigation shares one header row with the reporting badge and About. */
.st-key-workspace_header {{
  box-sizing: border-box; width: 100%; padding: 18px 0 22px;
  margin-bottom: 26px; background: #ffffff;
  border-bottom: 1px solid var(--site-border);
}}
@supports (width: 100cqw) {{
  .st-key-workspace_header {{
    width: 100cqw; margin-inline: calc((100% - 100cqw) / 2);
    padding-inline: calc((100cqw - 100%) / 2);
  }}
}}
.st-key-workspace_header [data-testid="stHorizontalBlock"] {{ align-items: center; gap: 16px; }}
.st-key-workspace_header .site-brand-title {{
  font-family: 'Inter', Arial, sans-serif !important;
  font-size: 28px; font-weight: 700; line-height: 1.1; color: var(--site-accent);
}}
.st-key-workspace_header .site-brand-subtitle {{ font-size: 10px; letter-spacing: 1.6px; }}
.st-key-workspace_header .site-badge {{ color: var(--site-accent); white-space: nowrap; font-size: 0.73rem; }}
.st-key-header_navigation [role="radiogroup"] {{
  display: flex; align-items: center; justify-content: flex-end; gap: 12px; flex-wrap: wrap;
}}
.st-key-header_navigation [role="radiogroup"] label {{
  margin: 0; padding: 10px 0; border-bottom: 3px solid transparent; cursor: pointer;
}}
.st-key-header_navigation [role="radiogroup"] label > div:first-child {{ display: none; }}
.st-key-header_navigation [role="radiogroup"] label p {{
  font-size: 0.8rem !important; font-weight: 500; white-space: nowrap;
}}
.st-key-header_navigation [role="radiogroup"] label:has(input:checked) {{
  border-bottom-color: var(--site-accent);
}}
.st-key-header_navigation [role="radiogroup"] label:has(input:checked) p {{
  color: var(--site-accent); font-weight: 600;
}}
.st-key-header_navigation [role="radiogroup"] label:has(input:focus-visible) {{
  outline: 2px solid var(--site-accent); outline-offset: 3px;
}}
.st-key-workspace_header .stButton > button {{ color: var(--site-accent); border-color: var(--site-accent); }}

/* Site header */
[data-testid="stMain"] {{ container-type: inline-size; }}
.site-topbar {{
  display: flex; align-items: center; justify-content: space-between; gap: 24px;
  box-sizing: border-box; width: 100%;
  padding: 20px 0; margin-bottom: 26px; flex-wrap: wrap;
  background: #ffffff; color: var(--site-accent);
  border-bottom: 1px solid var(--site-border);
}}
@supports (width: 100cqw) {{
  .site-topbar {{
    width: 100cqw; margin-inline: calc((100% - 100cqw) / 2);
    padding-inline: calc((100cqw - 100%) / 2);
  }}
}}
.site-brand {{ display: flex; align-items: center; gap: 22px; min-width: 0; }}
.site-topbar .site-brand-title {{
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif !important;
  font-size: 32px; font-weight: 700; line-height: 1.1;
  letter-spacing: -0.6px; color: var(--site-accent);
}}
.site-brand-subtitle {{
  margin-top: 5px; font-family: 'Inter', Arial, sans-serif;
  font-size: 12px; font-weight: 700; line-height: 1.4;
  letter-spacing: 2px; text-transform: uppercase; color: var(--site-accent);
}}
.site-topbar-actions {{
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
}}
a.site-about-button, a.site-about-button:visited {{
  display: inline-block; padding: 6px 14px; border: 1px solid var(--site-accent);
  border-radius: 8px; color: var(--site-accent); background: #ffffff;
  font-family: 'Inter', Arial, sans-serif; font-size: 0.85rem;
  font-weight: 600; text-decoration: none; line-height: 1.4;
}}
a.site-about-button:hover {{ background: rgba(40, 139, 228, 0.08); }}
a.site-about-button:focus-visible {{ outline: 2px solid var(--site-accent); outline-offset: 3px; }}
.site-badge {{
  display: inline-block; max-width: 100%; font-size: 0.8rem;
  padding: 6px 12px; border: 1px solid var(--site-border); border-radius: 8px;
  color: inherit; background: var(--site-panel); line-height: 1.4;
}}
@media (max-width: 640px) {{
  .site-topbar {{ padding-block: 18px; gap: 16px; }}
  .site-brand {{ gap: 15px; }}
  .site-topbar .site-brand-title {{ font-size: 28px; }}
  .site-brand-subtitle {{ font-size: 12px; letter-spacing: 2px; }}
}}
.site-hero h1 {{ font-size: 2rem; margin: 0 0 6px; padding: 0; line-height: 1.2; }}
.site-hero p {{ margin: 0 0 18px; opacity: 0.75; font-size: 1rem; }}

/* Tabs: muted labels, blue underline on the selected tab.
   Targets both the older BaseWeb tab markup and newer role-based markup, and
   overrides Streamlit's own selected-tab colour, which otherwise uses primaryColor. */
[data-testid="stTabs"] [role="tablist"], [data-baseweb="tab-list"] {{
  gap: 6px; border-bottom: 1px solid var(--site-border);
}}
[data-testid="stTabs"] [role="tab"], [data-baseweb="tab"] {{
  padding: 10px 12px !important; height: auto !important; background: transparent !important;
  color: inherit !important; border-bottom: 3px solid transparent !important;
}}
[data-testid="stTabs"] [role="tab"] p, [data-baseweb="tab"] p {{
  font-size: 0.98rem !important; opacity: 0.8; color: inherit !important;
}}
[data-testid="stTabs"] [role="tab"][aria-selected="true"], [data-baseweb="tab"][aria-selected="true"] {{
  border-bottom-color: var(--site-accent) !important;
}}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] p,
[data-baseweb="tab"][aria-selected="true"] p {{ opacity: 1; font-weight: 600; }}
[data-testid="stTabs"] [role="tab"]:hover p, [data-baseweb="tab"]:hover p {{ opacity: 1; }}
/* Use City blue for both native tab indicators and selected-tab borders. */
[data-testid="stTabs"] {{
  --primary-color: var(--site-accent);
  --st-primary-color: var(--site-accent);
}}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {{
  border-bottom: 3px solid var(--site-accent) !important;
  box-shadow: none !important;
}}
[data-testid="stTabs"] [role="tab"][aria-selected="true"]::after {{
  background-color: var(--site-accent) !important;
  border-color: var(--site-accent) !important;
}}
[data-testid="stTabs"] [data-baseweb="tab-highlight"],
[data-testid="stTabs"] [data-testid="stTabHighlight"],
[data-testid="stTabs"] [data-testid="stTabsHighlight"] {{
  background-color: var(--site-accent) !important;
  border-color: var(--site-accent) !important;
}}
/* React Aria tabs render an additional selection indicator inside the tab. */
[data-testid="stTabs"] .react-aria-SelectionIndicator {{
  display: none !important;
}}
/* Streamlit's own moving underline and divider: hidden in favour of the border above */
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] {{ display: none !important; }}
[data-testid="stTabs"] [role="tabpanel"], [data-baseweb="tab-panel"] {{ padding-top: 22px; }}

/* Panels: metrics, bordered containers, expanders, alerts, tables, charts */
[data-testid="stMetric"] {{
  border: 1px solid var(--site-border); border-radius: var(--site-radius);
  background: var(--site-panel); padding: 16px 18px;
}}
[data-testid="stMetricLabel"] p {{ font-size: 0.85rem !important; opacity: 0.8; }}
[data-testid="stMetricValue"] {{ font-weight: 600; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: var(--site-radius) !important; }}
[data-testid="stExpander"] details {{
  border: 1px solid var(--site-border) !important; border-radius: var(--site-radius) !important;
  background: var(--site-panel);
}}
[data-testid="stAlert"] {{ border-radius: 10px; }}
[data-testid="stDataFrame"], [data-testid="stTable"] {{
  border: 1px solid var(--site-border); border-radius: var(--site-radius); overflow: hidden;
}}
[data-testid="stPlotlyChart"] {{
  border: 1px solid var(--site-border); border-radius: var(--site-radius);
  padding: 8px; background: var(--site-panel);
}}
hr {{ border-color: var(--site-border) !important; margin: 1.6rem 0 !important; }}

/* Inputs */
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {{
  border-radius: 10px !important;
}}
[data-testid="stWidgetLabel"] p {{ font-size: 0.88rem; opacity: 0.85; }}

/* Buttons: outlined by default, solid red for primary and form submit */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {{
  border-radius: 10px; border: 1px solid var(--site-border); padding: 0.5rem 1rem; font-weight: 500;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{
  border-color: var(--site-accent); color: var(--site-accent);
}}
.stButton > button[kind="primary"], [data-testid="stFormSubmitButton"] > button {{
  background: var(--site-accent); border-color: var(--site-accent); color: #fff; font-weight: 600;
}}
.stButton > button:focus-visible, .stDownloadButton > button:focus-visible {{
  outline: 2px solid var(--site-accent); outline-offset: 2px;
}}

/* Sidebar */
[data-testid="stSidebar"] {{ border-right: 1px solid var(--site-border); }}

/* Site footer */
.site-footer {{
  display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap;
  margin-top: 48px; padding-top: 14px; border-top: 1px solid var(--site-border);
  font-size: 0.82rem; opacity: 0.75;
}}

@media (max-width: 640px) {{
  .site-hero h1 {{ font-size: 1.55rem; }}
  [data-baseweb="tab"] {{ padding: 8px 8px !important; }}
}}
</style>
"""


def apply_theme():
    st.markdown(_CSS, unsafe_allow_html=True)


def render_topbar(badge: str, brand: str = "Outreach workspace", on_about: bool = False):
    #Built without indentation: Markdown treats indented lines as a code block.
    page_url = "?page=workspace" if on_about else "?page=about"
    page_label = "Back to workspace" if on_about else "About"
    st.markdown(
        '<div class="site-topbar" role="banner">'
        '<div class="site-brand">'
        '<div class="site-brand-copy">'
        '<div class="site-brand-title">BERDO</div>'
        f'<div class="site-brand-subtitle">{html.escape(brand)}</div>'
        '</div></div>'
        '<div class="site-topbar-actions">'
        f'<span class="site-badge">{html.escape(badge)}</span>'
        f'<a class="site-about-button" href="{page_url}" target="_self">{page_label}</a>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def _open_about():
    st.query_params["page"] = "about"


def render_workspace_header(badge: str):
    """Render native navigation controls alongside the brand, badge, and About."""
    labels = ["Citywide Overview", "Address Lookup", "Owner Portfolio",
              "Retrofit & Incentives", "Emissions Planner"]
    with st.container(key="workspace_header"):
        brand_col, navigation_col, badge_col, about_col = st.columns(
            [1.25, 5.3, 2.0, 0.65], vertical_alignment="center"
        )
        with brand_col:
            st.markdown(
                '<div class="site-brand-copy"><div class="site-brand-title">BERDO</div>'
                '<div class="site-brand-subtitle">OUTREACH WORKSPACE</div></div>',
                unsafe_allow_html=True,
            )
        with navigation_col:
            selected = st.radio(
                "Workspace navigation", labels, horizontal=True,
                label_visibility="collapsed", key="header_navigation",
            )
        with badge_col:
            st.markdown(f'<span class="site-badge">{html.escape(badge)}</span>', unsafe_allow_html=True)
        with about_col:
            st.button("About", key="header_about", on_click=_open_about)
    return selected


def render_hero(heading: str = "Building support, with a clear next step.",
                subheading: str = "Find an outreach need, verify the evidence, and prepare an owner conversation."):
    st.markdown(
        '<div class="site-hero">'
        f'<h1>{html.escape(heading)}</h1>'
        f'<p>{html.escape(subheading)}</p>'
        '</div>',
        unsafe_allow_html=True,
    )


def render_header(badge: str, **kw):
    """Top bar and hero together (kept for convenience)."""
    render_topbar(badge)
    render_hero(**kw)


def render_footer(left: str, right: str):
    st.markdown(
        f'<div class="site-footer" role="contentinfo"><span>{html.escape(left)}</span>'
        f'<span>{html.escape(right)}</span></div>',
        unsafe_allow_html=True,
    )
