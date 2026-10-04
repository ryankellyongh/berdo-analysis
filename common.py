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
    Values that are None are skipped.
    """
    if building_key and building_key != st.session_state.get(marker_key, ""):
        for key, value in values.items():
            if value is not None:
                st.session_state[key] = value
        st.session_state[marker_key] = building_key
