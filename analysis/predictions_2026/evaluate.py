import numpy as np, pandas as pd, warnings
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import RepeatedStratifiedKFold
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
warnings.filterwarnings("ignore")
F = pd.read_csv(HERE / "features.csv")
lab = F[F.city_status.isin(["In Compliance", "Action Needed"]) & F.has_prior].copy()
y = (lab.city_status == "Action Needed").astype(int).values

def X_of(df, cols):
    X = df[cols].copy()
    if "eui_change" in cols:
        X["eui_change_missing"] = X.eui_change.isna().astype(int); X["eui_change"] = X.eui_change.fillna(0).clip(-0.5, 0.5)
    if "ratio_to_limit" in cols: X["log_ratio"] = np.log(X.pop("ratio_to_limit").clip(0.05, 10))
    return X.fillna(X.median(numeric_only=True)).astype(float).values

SETS = {
    "Ratio to limit only": ["ratio_to_limit"],
    "Ratio + building traits": ["ratio_to_limit", "elec_share", "log_sqft", "mixed_use", "city_owned"],
    "All features": ["ratio_to_limit", "elec_share", "log_sqft", "mixed_use", "city_owned", "eui_change"],
}
cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=20, random_state=7)
# Baseline rule: over the limit last year (at the 2025 grid factor)
rule = (lab.ratio_to_limit > 1).astype(int).values
tp, fp = int(((rule == 1) & (y == 1)).sum()), int(((rule == 1) & (y == 0)).sum())
print(f"RULE 'over limit last year': flags {rule.sum()} | catches {tp} of {y.sum()} Action Needed (recall {tp/y.sum():.0%}) | "
      f"precision {tp/rule.sum():.0%}")
results = {}
for name, cols in SETS.items():
    X = X_of(lab, cols); aucs, aps, briers = [], [], []
    oof = np.zeros(len(y)); counts = np.zeros(len(y))
    for tr, te in cv.split(X, y):
        m = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, class_weight=None, max_iter=1000)).fit(X[tr], y[tr])
        p = m.predict_proba(X[te])[:, 1]
        aucs.append(roc_auc_score(y[te], p)); aps.append(average_precision_score(y[te], p)); briers.append(brier_score_loss(y[te], p))
        oof[te] += p; counts[te] += 1
    oof /= counts; results[name] = oof
    print(f"{name:26s} AUC {np.mean(aucs):.3f} (±{np.std(aucs):.3f}) | avg precision {np.mean(aps):.3f} | Brier {np.mean(briers):.4f}")
# compare rule vs model at the same number of flags
oof = results["Ratio to limit only"]
k = rule.sum()
top = np.argsort(-oof)[:k]
print(f"Ratio-only model flagging the same {k} buildings: catches {y[top].sum()} of {y.sum()}")

# The model the app uses (ratio + building traits), compared with the rule at several
# outreach capacities: sort buildings by risk, contact the top k, count Action Needed found.
# The rule ranks by last year's emissions relative to the limit, highest first.
oof_model = results["Ratio + building traits"]
ratio = lab.ratio_to_limit.values
print("\nOUTREACH CAPACITY: Action Needed found among the top k (of", y.sum(), ")")
print(f"{'top k':>6} | {'rule':>12} | {'model':>12}")
for k in (25, 50, 88, 133, 200):
    r, m_ = y[np.argsort(-ratio)[:k]].sum(), y[np.argsort(-oof_model)[:k]].sum()
    print(f"{k:>6} | {r:>4} ({r/k:>4.0%}) | {m_:>4} ({m_/k:>4.0%})")

# 95% interval for the model's AUC: bootstrap the pooled out-of-fold predictions
rng = np.random.default_rng(0)
boot = []
for _ in range(2000):
    i = rng.integers(0, len(y), len(y))
    if y[i].min() != y[i].max():
        boot.append(roc_auc_score(y[i], oof_model[i]))
print(f"\nModel AUC (pooled out-of-fold): {roc_auc_score(y, oof_model):.3f}, "
      f"95% bootstrap interval {np.percentile(boot, 2.5):.2f}-{np.percentile(boot, 97.5):.2f}")
print("base rate (Brier of always guessing 5.8%):", round(brier_score_loss(y, np.full(len(y), y.mean())), 4))
# calibration check: predicted vs actual by bin
print("\nCALIBRATION (model with building traits): predicted vs actual by bin")
bins = pd.cut(oof_model, [0, .02, .05, .1, .3, .6, 1.0], include_lowest=True)
print(pd.DataFrame({"pred": oof_model, "y": y, "bin": bins}).groupby("bin", observed=True).agg(n=("y", "size"), predicted=("pred", "mean"), actual=("y", "mean")).round(3))
pd.DataFrame({"berdo_id": lab.berdo_id, "y": y, "oof": oof_model, "ratio": lab.ratio_to_limit}).to_csv(HERE / "oof.csv", index=False)
