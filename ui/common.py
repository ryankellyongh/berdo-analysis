"""
Small helpers shared by the tabs.
"""
import streamlit as st


def _fmt_dollars(val):
    """Format a dollar value with commas, no decimals."""
    return f"${val:,.0f}"

class _EndTab(Exception):
    """Raised inside a tab section to stop drawing the rest of the tab (like an early return)."""


def apply_prefill_once(marker_key: str, building_key: str, values: dict):
    """
    Write a looked-up building's values into a tab's input fields, but only when a
    different building (or data year) arrives, so a user's edits survive reruns.
    Every value is written, including None: an unknown value clears the field rather
    than leaving the previous building's number in place. Callers pass the selectbox
    placeholder (not None) for an unknown category.
    """
    if building_key and building_key != st.session_state.get(marker_key, ""):
        for key, value in values.items():
            st.session_state[key] = value
        st.session_state[marker_key] = building_key


def open_in_address_lookup(address: str):
    """
    Button callback: fill in Address Lookup with this address and switch to that tab.
    Streamlit can't select a tab from Python, so switch_tab_if_requested() (called at the
    end of app.py) clicks the tab in the browser on the rerun that follows.
    """
    st.session_state["lookup_address"] = address
    st.session_state["goto_tab"] = "Address Lookup"


def switch_tab_if_requested():
    """Click the requested tab in the page's menu, once, and scroll to the top."""
    label = st.session_state.pop("goto_tab", None)
    if not label:
        return
    import json
    import streamlit.components.v1 as components
    components.html(
        f"""<script>
        const doc = window.parent.document;
        const go = () => {{
          const tab = [...doc.querySelectorAll('[role="tab"]')]
            .find(t => t.innerText.trim() === {json.dumps(label)});
          if (!tab) return false;
          tab.click();
          window.parent.scrollTo({{top: 0, behavior: "smooth"}});
          return true;
        }};
        if (!go()) setTimeout(go, 300);
        </script>""",
        height=0,
    )
