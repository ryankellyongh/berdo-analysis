"""Reading and summarizing the saved 2026 predictions (analysis/predictions_2026)."""
import pandas as pd

from berdo.predictions import (
    TIER_TRACK_RECORD, building_label_allowed, needed_to_act_share, format_probability, labelable_buildings, load_predictions, prediction_for_building,
    prediction_summary, suppress_small, tier_rate, type_risk_summary, zip_risk_summary,
)


def _df():
    return pd.DataFrame({
        "berdo_id": ["1", "2", "3", "4", "5"],
        "zip": ["02119", "02119", "02215", None, "02215"],
        "city_status": ["Pending Reporting"] * 3 + ["Pending Review from BERDO Team"] * 2,
        "tier": ["Likely over", "Watch", "Likely compliant", "No earlier data", "Likely over"],
        "probability_action_needed": [0.4, 0.2, 0.01, None, 0.5],
        "latitude": [42.31, 42.32, 42.34, None, 42.35], "longitude": [-71.08, -71.09, -71.10, None, -71.10],
    })


def test_tier_track_record():
    # Likely over + Watch found 43 of the 47 Action Needed buildings with earlier data
    assert TIER_TRACK_RECORD["Likely over"]["action_needed"] + TIER_TRACK_RECORD["Watch"]["action_needed"] == 43
    assert abs(tier_rate("Likely over") - 35 / 88) < 1e-12 and tier_rate("No earlier data") is None


def test_prediction_summary():
    s = prediction_summary(_df()).set_index("Group")
    assert s.loc["Pending Reporting", "Buildings"] == 3 and s.loc["Under City review", "Buildings"] == 2
    assert s.loc["Pending Reporting", "Expected Action Needed (model)"] == round(0.4 + 0.2 + 0.01)   # 1
    # tier rates: 35/88 + 8/45 + 4/676 = 0.58 -> 1
    assert s.loc["Pending Reporting", "Expected Action Needed (tier rates)"] == 1
    assert s.loc["Under City review", "With earlier data"] == 1


def test_zip_summary_shows_only_combined_counts():
    z = zip_risk_summary(_df()).set_index("ZIP code")
    assert z.loc["02119", "at_risk"] == 2 and z.loc["02119", "At risk"] == "fewer than 3"
    # no separate Likely over / Watch columns, so suppressed counts can't be recovered by subtraction
    assert not {"Likely over", "Watch"} & set(z.columns)


def test_small_counts_suppressed():
    assert suppress_small(0) == "0" and suppress_small(2) == "fewer than 3" and suppress_small(1234) == "1,234"
    t = type_risk_summary(_df().assign(property_type="Office"))
    assert t.loc[0, "At risk"] == "3" and t.loc[0, "Buildings without a result"] == "5"
    t2 = type_risk_summary(_df().head(2).assign(property_type="Office"))
    assert t2.loc[0, "At risk"] == "fewer than 3"         # 2 at-risk buildings


def test_buildings_under_review_never_labeled():
    df = _df()
    assert building_label_allowed(prediction_for_building(df, "1"))
    assert not building_label_allowed(prediction_for_building(df, "5"))        # under City review
    assert not building_label_allowed(None)
    assert set(labelable_buildings(df)["berdo_id"]) == {"1", "2", "3"}


def test_prediction_for_building():
    assert prediction_for_building(_df(), "2")["tier"] == "Watch"
    assert prediction_for_building(_df(), "999") is None and prediction_for_building(None, "1") is None


def test_saved_predictions_file():
    d = load_predictions()
    assert d is not None and len(d) == 1359
    assert (d["tier"] == "Likely over").sum() == 163 and (d["tier"] == "Watch").sum() == 54
    assert d["zip"].dropna().str.len().eq(5).all()                       # five-digit ZIP codes
    assert load_predictions("does/not/exist.csv") is None


def test_probabilities_never_shown_as_certain():
    assert format_probability(0.997) == "over 95%" and format_probability(0.005) == "under 2%"
    assert format_probability(0.384) == "38%" and format_probability(None) == "not estimated"


def test_needed_to_act_share():
    # Likely over: 35 Action Needed + 52 came in compliant after acting = 87 of 88
    assert round(needed_to_act_share("Likely over"), 3) == round(87 / 88, 3)
    assert round(needed_to_act_share("Watch"), 3) == round(41 / 45, 3)
    assert needed_to_act_share("Likely compliant") is None and needed_to_act_share("Unknown") is None
