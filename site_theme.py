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

/* Site header */
.site-topbar {{
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 14px 0 16px; border-bottom: 1px solid var(--site-border); margin-bottom: 26px;
  flex-wrap: wrap;
}}
.site-brand {{ font-weight: 600; font-size: 1.02rem; }}
.site-brand .accent {{ color: var(--site-accent); font-weight: 700; }}
.site-badge {{
  display: inline-block; font-size: 0.8rem; padding: 4px 10px; border-radius: 8px;
  background: rgba(127, 127, 127, 0.16); line-height: 1.4;
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


def render_topbar(badge: str, brand: str = "Outreach workspace"):
    #Built without indentation: Markdown treats indented lines as a code block.
    st.markdown(
        '<div class="site-topbar" role="banner">'
        f'<div class="site-brand"><span class="accent">BERDO</span> / {html.escape(brand)}</div>'
        f'<span class="site-badge">{html.escape(badge)}</span>'
        '</div>',
        unsafe_allow_html=True,
    )


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
