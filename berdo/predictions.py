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
#acted_to_comply: buildings found In Compliance that, between years, cut emissions by more
#than 10%, bought renewable electricity, or used a flexibility measure. Not counted for
#Likely compliant buildings, which were already under their limit.
TIER_TRACK_RECORD = {
    "Likely over":      {"buildings": 88,  "action_needed": 35, "acted_to_comply": 52},
    "Watch":            {"buildings": 45,  "action_needed": 8,  "acted_to_comply": 33},
    "Likely compliant": {"buildings": 676, "action_needed": 4,  "acted_to_comply": None},
}


def needed_to_act_share(tier):
    """Share of a tier that was Action Needed or came in compliant only after acting, or None."""
    r = TIER_TRACK_RECORD.get(tier)
    if not r or r["acted_to_comply"] is None:
        return None
    return (r["action_needed"] + r["acted_to_comply"]) / r["buildings"]


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


#Data-use policy
#- The public view shows totals by tier, ZIP code, and building type, never specific buildings.
#- Counts below SMALL_GROUP_MIN are shown as "fewer than 3", so a small group can't identify a building.
#- Buildings under City review are never labeled individually: the City says they are not
#  considered out of compliance while under review.
#- Building-level lists are for the City's BERDO team (with an access code) and for owners on request.
SMALL_GROUP_MIN = 3
UNDER_REVIEW = "Pending Review from BERDO Team"


def suppress_small(n: int) -> str:
    """A count as text, hiding small groups that could identify a building."""
    n = int(n)
    return "0" if n == 0 else (f"fewer than {SMALL_GROUP_MIN}" if n < SMALL_GROUP_MIN else f"{n:,}")


def building_label_allowed(prediction) -> bool:
    """Whether a building's own predicted label may be shown (never for buildings under City review)."""
    return bool(prediction) and prediction.get("city_status") != UNDER_REVIEW


def labelable_buildings(df) -> pd.DataFrame:
    """Buildings whose predicted label may be shown individually (excludes those under City review)."""
    return df[df["city_status"] != UNDER_REVIEW]


def zip_risk_summary(df) -> pd.DataFrame:
    """
    Public, ZIP-level view: the combined at-risk count (Likely over + Watch), small counts suppressed,
    and each ZIP code's average building location for placing one map circle per ZIP.
    """
    d = df[df["zip"].notna()]
    rows = []
    for z, g in d.groupby("zip"):
        over, watch = int((g.tier == "Likely over").sum()), int((g.tier == "Watch").sum())
        #Only the combined count is public: showing both parts and a total would let
        #anyone recover a suppressed small count by subtraction.
        rows.append({"ZIP code": z, "at_risk": over + watch, "At risk": suppress_small(over + watch),
                     "latitude": g["latitude"].mean(), "longitude": g["longitude"].mean()})
    out = pd.DataFrame(rows)
    return out.sort_values("at_risk", ascending=False).reset_index(drop=True) if not out.empty else out


def type_risk_summary(df) -> pd.DataFrame:
    """Public view by building type: buildings without a result and how many are at risk (small counts suppressed)."""
    rows = []
    for t, g in df[df["property_type"].notna()].groupby("property_type"):
        risk = int(g.tier.isin(["Likely over", "Watch"]).sum())
        rows.append({"Building type": t, "n": len(g), "risk": risk,
                     "Buildings without a result": suppress_small(len(g)), "At risk": suppress_small(risk)})
    out = pd.DataFrame(rows)
    return (out.sort_values("risk", ascending=False).drop(columns=["n", "risk"]).reset_index(drop=True)
            if not out.empty else out)
