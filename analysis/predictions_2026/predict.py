import hashlib, datetime as dt, numpy as np, pandas as pd, warnings
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
warnings.filterwarnings("ignore")
F = pd.read_csv(HERE / "features.csv", dtype={"berdo_id": str})
COLS = ["ratio_to_limit", "elec_share", "log_sqft", "mixed_use", "city_owned"]
def X_of(df):
    X = df[COLS].copy(); X["log_ratio"] = np.log(X.pop("ratio_to_limit").clip(0.05, 10))
    X = X.astype(float); return X.fillna(MED)
def tier(r): return "Likely over" if r > 1 else ("Watch" if r > 0.9 else "Likely compliant")

lab = F[F.city_status.isin(["In Compliance", "Action Needed"]) & F.has_prior].copy()
y = (lab.city_status == "Action Needed").astype(int).values
MED = lab[COLS].assign(log_ratio=np.log(lab.ratio_to_limit.clip(0.05, 10))).drop(columns="ratio_to_limit").astype(float).median()

# How the tiers performed on buildings with known results
lab["tier"] = lab.ratio_to_limit.apply(tier)
t = lab.groupby("tier").apply(lambda g: pd.Series({"buildings": len(g), "action_needed": int((g.city_status == "Action Needed").sum())}), include_groups=False)
t["share_action_needed"] = (t.action_needed / t.buildings).round(3)
print("TIERS ON KNOWN RESULTS\n", t.loc[["Likely over", "Watch", "Likely compliant"]])

model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)).fit(X_of(lab), y)

targets = F[((F.city_status == "Pending Reporting") & (F.compliance_year == 2025)) |
            (F.city_status == "Pending Review from BERDO Team")].copy()
withp = targets[targets.has_prior].copy()
withp["probability_action_needed"] = model.predict_proba(X_of(withp))[:, 1].round(3)
withp["tier"] = withp.ratio_to_limit.apply(tier)
out = pd.concat([withp, targets[~targets.has_prior].assign(tier="No earlier data")], ignore_index=True)
out = out[["berdo_id", "address", "zip", "latitude", "longitude", "property_type", "sqft", "city_status", "reporting_status",
           "prior_energy_year", "adj_intensity", "limit_2025", "ratio_to_limit", "tier", "probability_action_needed"]]
out = out.sort_values(["probability_action_needed"], ascending=False, na_position="last")
out.to_csv(HERE / "predictions_2026_pending.csv", index=False)

print("\nPREDICTIONS FOR BUILDINGS WITHOUT A PUBLISHED RESULT")
for grp, g in out.groupby("city_status"):
    gp = g[g.probability_action_needed.notna()]
    mean, var = gp.probability_action_needed.sum(), (gp.probability_action_needed * (1 - gp.probability_action_needed)).sum()
    print(f"{grp}: {len(g)} buildings, {len(gp)} with earlier data")
    print("   tiers:", g.tier.value_counts().to_dict())
    print(f"   expected Action Needed among those with data: {mean:.0f} (likely range {max(0, mean - 1.96 * var ** .5):.0f} to {mean + 1.96 * var ** .5:.0f})")
z = out[out.tier.isin(["Likely over", "Watch"])].groupby("zip").size().sort_values(ascending=False).head(6)
print("\nZIP codes with the most 'Likely over' or 'Watch' buildings:", z.to_dict())
h = hashlib.sha256(open(HERE / "predictions_2026_pending.csv", "rb").read()).hexdigest()
print("\nSHA-256 of predictions file:", h)
open(HERE / "prediction_hash.txt", "w").write(f"predictions_2026_pending.csv\nSHA-256: {h}\nCreated: {dt.date.today().isoformat()}\n")
