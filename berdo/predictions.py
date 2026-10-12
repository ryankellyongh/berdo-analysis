"""
Saved predictions of 2025 compliance results for buildings the City hasn't scored yet
(analysis/predictions_2026). Reading and summarizing them, for the app. No Streamlit.
"""
from pathlib import Path
import pandas as pd

PREDICTIONS_FILE = Path("analysis") / "predictions_2026" / "predictions_2026_pending.csv"
PREDICTIONS_SAVED_ON = "October 12, 2026"
PREDICTIONS_FOR_YEAR = 2026          #reporting year the predictions apply to (2025 energy use)
TIER_ORDER = ["Likely over", "Watch", "Likely compliant", "No earlier data"]

#How each tier turned out on the 809 buildings that already had a City result
#(earlier-year data only; see analysis/predictions_2026/README.md)
TIER_TRACK_RECORD = {
    "Likely over":      {"buildings": 88,  "action_needed": 35},
    "Watch":            {"buildings": 45,  "action_needed": 8},
    "Likely compliant": {"buildings": 676, "action_needed": 4},
}


def load_predictions(path=PREDICTIONS_FILE):
    """The saved predictions, with clean IDs and five-digit ZIP codes. None if the file is missing."""
    path = Path(path)
    if not path.exists():
        return None
    df = pd.read_csv(path, dtype={"berdo_id": str, "zip": str})
    df["zip"] = (df["zip"].fillna("").str.replace(r"\.0$", "", regex=True)
                 .str.strip().map(lambda z: z.zfill(5) if z else None))
    return df


def tier_rate(tier):
    """Share of buildings in this tier that turned out Action Needed, or None."""
    r = TIER_TRACK_RECORD.get(tier)
    return r["action_needed"] / r["buildings"] if r else None


def prediction_summary(df) -> pd.DataFrame:
    """
    One row per group (Pending Reporting, Under City review): buildings, buildings with
    earlier data, counts by tier, and two estimates of how many will be Action Needed:
    the sum of the model's probabilities, and the tier counts times each tier's track record.
    """
    rows = []
    for status, g in df.groupby("city_status"):
        counts = g["tier"].value_counts()
        probs = g["probability_action_needed"].dropna()
        rows.append({
            "Group": "Under City review" if status.startswith("Pending Review") else status,
            "Buildings": len(g),
            "With earlier data": int(probs.size),
            **{t: int(counts.get(t, 0)) for t in TIER_ORDER},
            "Expected Action Needed (model)": round(float(probs.sum())),
            "Expected Action Needed (tier rates)": round(sum(
                counts.get(t, 0) * tier_rate(t) for t in TIER_TRACK_RECORD)),
        })
    return pd.DataFrame(rows)


def at_risk_by_zip(df, top=10) -> pd.DataFrame:
    """ZIP codes with the most buildings in the Likely over or Watch tiers."""
    risk = df[df["tier"].isin(["Likely over", "Watch"]) & df["zip"].notna()]
    out = (risk.groupby("zip").agg(**{"Likely over": ("tier", lambda s: int((s == "Likely over").sum())),
                                      "Watch": ("tier", lambda s: int((s == "Watch").sum()))})
           .assign(**{"At risk": lambda t: t["Likely over"] + t["Watch"]})
           .sort_values("At risk", ascending=False).head(top).reset_index()
           .rename(columns={"zip": "ZIP code"}))
    return out


def prediction_for_building(df, berdo_id):
    """The saved prediction for one building (a dict), or None."""
    if df is None or not berdo_id:
        return None
    m = df[df["berdo_id"] == str(berdo_id)]
    return None if m.empty else m.iloc[0].to_dict()


def format_probability(p) -> str:
    """A probability as text, without implying certainty: 'over 95%', 'under 2%', or e.g. '38%'."""
    if p is None or pd.isna(p):
        return "not estimated"
    if p > 0.95:
        return "over 95%"
    if p < 0.02:
        return "under 2%"
    return f"{p:.0%}"
