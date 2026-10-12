"""
Score the saved predictions against the City's updated 2026 disclosure.

  1. Convert the City's updated "Buildings & Campuses" sheet to a CSV.
  2. Run:  python analysis/predictions_2026/check_after_update.py path/to/updated_2026.csv

Only buildings that now have an In Compliance or Action Needed result are scored.
"""
import sys
from pathlib import Path
import hashlib
import pandas as pd
from sklearn.metrics import roc_auc_score

HERE = Path(__file__).resolve().parent
saved = HERE / "predictions_2026_pending.csv"
recorded = (HERE / "prediction_hash.txt").read_text().split("SHA-256: ")[1].split()[0]
actual_hash = hashlib.sha256(saved.read_bytes()).hexdigest()
print("Predictions file unchanged since it was saved:", actual_hash == recorded)

pred = pd.read_csv(saved, dtype={"berdo_id": str})
new = pd.read_csv(sys.argv[1], dtype={"BERDO ID": str})
new = new.rename(columns={"BERDO ID": "berdo_id", "Emissions Compliance Status": "new_status"})
m = pred.merge(new[["berdo_id", "new_status"]], on="berdo_id", how="left")
scored = m[m.new_status.isin(["In Compliance", "Action Needed"])].copy()
scored["action_needed"] = (scored.new_status == "Action Needed").astype(int)
print(f"\n{len(scored)} of {len(pred)} predicted buildings now have a City result")
print("\nBy tier (share that turned out Action Needed):")
print(scored.groupby("tier").action_needed.agg(buildings="size", action_needed="sum", share="mean").round(3))
w = scored[scored.probability_action_needed.notna()]
if w.action_needed.nunique() == 2:
    print(f"\nRanking accuracy (AUC): {roc_auc_score(w.action_needed, w.probability_action_needed):.3f}")
print(f"Expected Action Needed (sum of probabilities): {w.probability_action_needed.sum():.0f} | actual: {int(w.action_needed.sum())}")
