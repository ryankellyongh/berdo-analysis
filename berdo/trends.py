"""
Citywide trends in energy use and emissions across reporting years. No Streamlit.

Same method as analysis/time_series/time_series.py:
- results are labeled by ENERGY year (reporting year - 1);
- trends use balanced panels (the same buildings every year, linked by BERDO ID);
- citywide figures are floor-area weighted (total / total floor area);
- the grid effect restates electricity emissions at a fixed grid factor;
- campus records are excluded, and the provisional latest year is kept out of the panels.
"""
import numpy as np
import pandas as pd

from berdo.emissions import building_limits, effective_grid_ef, map_property_type


def combine_years(all_years: dict) -> pd.DataFrame:
    """One long table of buildings (no campus records) across reporting years, with derived columns."""
    frames = []
    for year, d in all_years.items():
        if not year:
            continue
        d = d[~d["is_campus_summary"]] if "is_campus_summary" in d.columns else d
        d = d.copy()
        d["energy_year"] = int(year) - 1
        frames.append(d)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["berdo_id"] = df["berdo_id"].astype("string") if "berdo_id" in df.columns else pd.NA
    sqft = pd.to_numeric(df.get("gross_floor_area"), errors="coerce")
    df["_sqft"] = sqft.where(sqft > 0)
    df["_ghg"] = pd.to_numeric(df.get("ghg_emissions"), errors="coerce")
    df["_energy"] = pd.to_numeric(df.get("total_site_energy_kbtu"), errors="coerce")
    df["_elec"] = pd.to_numeric(df.get("elec_emissions_kg"), errors="coerce")
    df["_intensity"] = df["_ghg"] / df["_sqft"]
    return df


def balanced(df, years, need):
    """Rows for buildings (by BERDO ID) with every `need` column present in every year."""
    d = df[df["energy_year"].isin(years) & df["berdo_id"].notna()].dropna(subset=need)
    d = d.drop_duplicates(["berdo_id", "energy_year"])
    n = d.groupby("berdo_id")["energy_year"].nunique()
    return d[d["berdo_id"].isin(n[n == len(years)].index)]


def _years_with(df, col, minimum=500):
    """Energy years with at least `minimum` buildings reporting `col`."""
    #Only years with BERDO IDs can be linked across years (the 2021 disclosure has none)
    c = df[df["berdo_id"].notna()].dropna(subset=[col]).groupby("energy_year").size()
    return sorted(int(y) for y in c[c >= minimum].index)


def _limit_2025(row):
    lim = building_limits(row.get("property_type"), row.get("all_property_types"))["limits"]
    return lim[0] if lim else np.nan


def compute_trends(all_years: dict, provisional_year=None) -> dict:
    """
    Everything the Citywide trends section shows. `provisional_year` is an ENERGY year left out
    of the panels (default: the latest year, whose disclosure is provisional).
    Returns {} when there isn't enough multi-year data.
    """
    df = combine_years(all_years)
    if df.empty or df["energy_year"].nunique() < 3:
        return {}
    latest = int(df["energy_year"].max())
    prov = latest if provisional_year is None else provisional_year
    out = {"provisional_year": prov}

    #Coverage by energy year
    out["coverage"] = df.groupby("energy_year").agg(
        buildings=("berdo_id", "size"),
        with_energy=("_energy", lambda s: int(s.notna().sum())),
        with_emissions=("_ghg", lambda s: int(s.notna().sum()))).reset_index()

    #Energy and emissions panels (complete years only)
    ey = [y for y in _years_with(df, "_energy") if y != prov]
    gy = [y for y in _years_with(df, "_ghg") if y != prov]
    if len(gy) >= 2:
        pe = balanced(df, ey, ["_energy", "_sqft"]) if len(ey) >= 2 else df.iloc[0:0]
        pg = balanced(df, gy, ["_ghg", "_sqft"])
        base = gy[0]
        e = pe.groupby("energy_year").agg(energy=("_energy", "sum"), sqft=("_sqft", "sum"))
        g = pg.groupby("energy_year").agg(ghg=("_ghg", "sum"), sqft=("_sqft", "sum"))
        e_idx = (e["energy"] / e["sqft"]) / (e.loc[base, "energy"] / e.loc[base, "sqft"]) * 100 \
            if base in e.index else pd.Series(dtype=float)
        g_idx = (g["ghg"] / g["sqft"]) / (g.loc[base, "ghg"] / g.loc[base, "sqft"]) * 100
        out["index"] = {"base_year": base, "energy": e_idx, "emissions": g_idx,
                        "n_energy": int(pe["berdo_id"].nunique()), "n_emissions": int(pg["berdo_id"].nunique())}
        out["emissions_change"] = float(g_idx.iloc[-1] / 100 - 1)

        #Share over the 2025-29 limit, same buildings
        pl = pg.assign(_limit=pg.apply(_limit_2025, axis=1)).dropna(subset=["_limit"])
        out["share_over"] = (pl["_intensity"] > pl["_limit"]).groupby(pl["energy_year"]).mean()

        #By building category, first to last panel year
        pc = pg.assign(category=pg["property_type"].map(map_property_type)).dropna(subset=["category"])
        cat = pc.groupby(["category", "energy_year"]).agg(ghg=("_ghg", "sum"), sqft=("_sqft", "sum"),
                                                          n=("berdo_id", "nunique")).reset_index()
        cat["intensity"] = cat["ghg"] / cat["sqft"]
        w = cat.pivot(index="category", columns="energy_year", values="intensity")
        w["buildings"] = cat[cat["energy_year"] == gy[0]].set_index("category")["n"]
        w["change"] = w[gy[-1]] / w[gy[0]] - 1
        out["by_category"] = w[w["buildings"] >= 30].sort_values("change")[["buildings", "change"]]
        out["category_years"] = (gy[0], gy[-1])

    #Grid vs. building change: the last two complete years with electricity emissions
    ly = [y for y in _years_with(df, "_elec") if y != prov and y in gy]
    if len(ly) >= 2:
        y0, y1 = ly[-2], ly[-1]
        pdx = balanced(df, [y0, y1], ["_ghg", "_sqft", "_elec"])
        ef0 = effective_grid_ef(y0)
        pdx = pdx.assign(_fixed=pdx["_ghg"] - pdx["_elec"]
                         + pdx["_elec"] * ef0 / pdx["energy_year"].map(effective_grid_ef))
        s = pdx.groupby("energy_year")[["_ghg", "_fixed", "_elec"]].sum()
        total = s.loc[y1, "_ghg"] - s.loc[y0, "_ghg"]
        building = s.loc[y1, "_fixed"] - s.loc[y0, "_fixed"]
        out["grid"] = {"years": (y0, y1), "n": int(pdx["berdo_id"].nunique()),
                       "total_t": total / 1000, "grid_t": (total - building) / 1000, "building_t": building / 1000,
                       "total_pct": total / s.loc[y0, "_ghg"], "grid_pct": (total - building) / s.loc[y0, "_ghg"],
                       "building_pct": building / s.loc[y0, "_ghg"],
                       "elec_share": s.loc[y0, "_elec"] / s.loc[y0, "_ghg"],
                       "ef": (effective_grid_ef(y0), effective_grid_ef(y1))}

        #Persistence between the same two years
        a = df[df["energy_year"] == y0].dropna(subset=["_intensity"]).drop_duplicates("berdo_id")
        b = df[df["energy_year"] == y1].dropna(subset=["_intensity"]).drop_duplicates("berdo_id")
        m = a.merge(b, on="berdo_id", suffixes=("_0", "_1"))
        m = m[(m["_intensity_0"] > 0) & (m["_intensity_1"] > 0)]
        m["_limit"] = [_limit_2025({"property_type": p, "all_property_types": u})
                       for p, u in zip(m["property_type_1"], m["all_property_types_1"])]
        m = m.dropna(subset=["_limit"])
        if len(m) > 30:
            o0, o1 = m["_intensity_0"] > m["_limit"], m["_intensity_1"] > m["_limit"]
            out["persistence"] = {
                "years": (y0, y1), "n": len(m),
                "r": float(np.corrcoef(np.log(m["_intensity_0"]), np.log(m["_intensity_1"]))[0, 1]),
                "stay_over": float((o0 & o1).sum() / o0.sum()) if o0.sum() else None,
                "become_over": float((~o0 & o1).sum() / (~o0).sum()) if (~o0).sum() else None,
                "points": m[["_intensity_0", "_intensity_1"]].rename(
                    columns={"_intensity_0": "before", "_intensity_1": "after"})}
    return out
