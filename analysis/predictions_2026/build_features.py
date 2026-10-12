"""Features for predicting each building's 2025 compliance result from its earlier-year data."""
import sys, numpy as np, pandas as pd
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "berdo_app"))
from berdo.data import prepare_dataframe
from berdo.emissions import building_limits, effective_grid_ef, is_city_building

d26 = prepare_dataframe(pd.read_csv(ROOT / "data" / "berdo_2026.csv"))
prior = {2025: prepare_dataframe(pd.read_csv(ROOT / "data" / "berdo_2025.csv")),   # 2024 energy use
         2024: prepare_dataframe(pd.read_csv(ROOT / "data" / "berdo_2024.csv"))}   # 2023 energy use

def latest_prior(bid):
    """Most recent earlier record with emissions: (record, energy-use year, older record or None)."""
    found = []
    for file_year in (2025, 2024):
        d = prior[file_year]
        m = d[(d.berdo_id == bid) & d.ghg_intensity_kgco2e_sqft.notna() & ~d.is_campus_summary]
        if not m.empty:
            found.append((m.iloc[0], file_year - 1))
    if not found: return None, None, None
    return found[0][0], found[0][1], (found[1][0] if len(found) > 1 else None)

rows = []
for _, b in d26[~d26.is_campus_summary].iterrows():
    status = b.get("emissions_status")
    rec, energy_year, older = latest_prior(b.berdo_id)
    #Buildings that haven't reported yet have a blank 2026 property type; use the earlier record's
    ptype, uses = b.property_type, b.get("all_property_types")
    if (not isinstance(ptype, str) or not ptype.strip()) and rec is not None:
        ptype, uses = rec.property_type, rec.get("all_property_types")
    bl = building_limits(ptype, uses)
    limit = bl["limits"][0] if bl["limits"] else np.nan
    #Location: 2026 leaves ZIP blank for buildings that haven't reported; earlier files have ZIP and coordinates
    zip_code = b.get("Building Address Zip Code")
    if (zip_code is None or pd.isna(zip_code)) and rec is not None:
        zip_code = rec.get("Building Address Zip Code")
    address = b.get("Building Address")
    if (not isinstance(address, str) or not address.strip()) and rec is not None:
        address = rec.get("Building Address")
    r = {"berdo_id": b.berdo_id, "address": address, "zip": zip_code,
         "latitude": rec.get("Latitude") if rec is not None else np.nan,
         "longitude": rec.get("Longitude") if rec is not None else np.nan,
         "property_type": ptype, "sqft": b.gross_floor_area, "city_status": status,
         "reporting_status": b.compliance_status, "compliance_year": b.compliance_year,
         "limit_2025": limit, "has_prior": rec is not None}
    if rec is not None:
        ghg, sqft_p = rec.ghg_emissions, rec.gross_floor_area
        elec = rec.get("elec_emissions_kg")
        elec = elec if pd.notna(elec) and elec > 0 else 0.0
        # Restate last year's emissions at the 2025 grid factor (same energy use, cleaner grid)
        adj = ghg - elec + elec * effective_grid_ef(2025) / effective_grid_ef(energy_year)
        r.update({
            "prior_energy_year": energy_year,
            "prior_intensity": rec.ghg_intensity_kgco2e_sqft,
            "adj_intensity": adj / sqft_p,
            "ratio_to_limit": (adj / sqft_p) / limit if limit and limit > 0 else np.nan,
            "elec_share": min(max(elec / ghg, 0), 1) if ghg and ghg > 0 else np.nan,
            "eui_change": (rec.site_eui / older.site_eui - 1) if older is not None and older.site_eui and older.site_eui > 0 else np.nan,
            "mixed_use": bool(bl.get("blended")),
            "city_owned": is_city_building(rec.get("Property Owner Name")),
            "log_sqft": np.log10(sqft_p) if sqft_p and sqft_p > 0 else np.nan,
        })
    rows.append(r)
F = pd.DataFrame(rows)
F.to_csv(HERE / "features.csv", index=False)
lab = F[F.city_status.isin(["In Compliance", "Action Needed"]) & F.has_prior]
print("training rows:", len(lab), "| Action Needed:", int((lab.city_status == "Action Needed").sum()))
pend = F[(F.city_status == "Pending Reporting") & (F.compliance_year == 2025)]
rev = F[F.city_status == "Pending Review from BERDO Team"]
print("pending reporting (covered 2025):", len(pend), "| with prior data:", int(pend.has_prior.sum()))
print("under review:", len(rev), "| with prior data:", int(rev.has_prior.sum()))
