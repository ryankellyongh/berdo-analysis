"""
Time series analysis of Boston BERDO energy use and emissions, energy years 2020-2025.

Run from the repository root:  python analysis/time_series/time_series.py

Reads data/berdo_<reporting year>.csv through berdo.data.prepare_dataframe (the same
loader the app uses). Each reporting year holds the PREVIOUS calendar year's energy use,
so results are labeled by energy year (reporting year - 1).

Writes figures to analysis/time_series/figures/ and tables to analysis/time_series/tables/.

Design choices
- Balanced panels: trends use the same buildings in every year, linked by BERDO ID, so a
  change in which buildings reported can't masquerade as a change in performance.
- Floor-area-weighted intensity (total emissions / total floor area) is the citywide figure;
  medians are reported alongside because a few very large buildings dominate totals.
- The grid effect is separated from building-level change by restating electricity emissions
  at a fixed grid factor (BERDO-effective factor: Appendix B x (1 - RPS Class I)).
- Energy year 2025 (reporting year 2026) is provisional: the City withheld data for buildings
  under review or still reporting, so it is shown separately and never mixed into the panels.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from berdo.data import prepare_dataframe                     # noqa: E402
from berdo.emissions import building_limits, effective_grid_ef  # noqa: E402

FIG, TAB = HERE / "figures", HERE / "tables"
FIG.mkdir(exist_ok=True)
TAB.mkdir(exist_ok=True)
BLUE, GREY, RED, ORANGE = "#288BE4", "#8B8D98", "#E5484D", "#F76B15"
plt.rcParams.update({"figure.dpi": 150, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25, "font.size": 9})


# ---------------------------------------------------------------------------
# Load every year
# ---------------------------------------------------------------------------
def load():
    frames = []
    for fp in sorted((ROOT / "data").glob("berdo_*.csv")):
        stem = fp.stem.split("_", 1)[1]
        if not stem.isdigit():
            continue
        d = prepare_dataframe(pd.read_csv(fp, low_memory=False))
        d = d[~d["is_campus_summary"]].copy()               #buildings only
        d["reporting_year"] = int(stem)
        d["energy_year"] = int(stem) - 1
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    df["berdo_id"] = df["berdo_id"].astype("string")
    sqft = pd.to_numeric(df["gross_floor_area"], errors="coerce")
    df["sqft"] = sqft.where(sqft > 0)
    df["ghg"] = pd.to_numeric(df["ghg_emissions"], errors="coerce")
    df["energy"] = pd.to_numeric(df.get("total_site_energy_kbtu"), errors="coerce")
    df["eui"] = pd.to_numeric(df["site_eui"], errors="coerce")
    df["elec"] = pd.to_numeric(df.get("elec_emissions_kg"), errors="coerce")
    df["intensity"] = df["ghg"] / df["sqft"]
    return df


def limit_2025(row):
    lim = building_limits(row.get("property_type"), row.get("all_property_types"))["limits"]
    return lim[0] if lim else np.nan


def balanced(df, years, need):
    """Buildings (by BERDO ID) with every `need` column present in every year."""
    d = df[df["energy_year"].isin(years) & df["berdo_id"].notna()]
    d = d.dropna(subset=need)
    d = d.drop_duplicates(["berdo_id", "energy_year"])
    counts = d.groupby("berdo_id")["energy_year"].nunique()
    keep = counts[counts == len(years)].index
    return d[d["berdo_id"].isin(keep)]


def main():
    df = load()
    out = {}

    # 1. Coverage ------------------------------------------------------------
    cov = df.groupby("energy_year").agg(
        buildings=("berdo_id", "size"),
        with_energy_use=("eui", lambda s: int(s.notna().sum())),
        with_emissions=("ghg", lambda s: int(s.notna().sum())),
        with_electricity_emissions=("elec", lambda s: int(s.notna().sum())))
    cov.to_csv(TAB / "coverage.csv")
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    x = cov.index.values
    ax.bar(x - 0.2, cov["with_energy_use"], 0.4, color=BLUE, label="With energy use (EUI)")
    ax.bar(x + 0.2, cov["with_emissions"], 0.4, color=ORANGE, label="With emissions")
    ax.plot(x, cov["buildings"], "o-", color=GREY, label="Buildings in disclosure")
    ax.set_xticks(x, [f"{y}{'*' if y == 2025 else ''}" for y in x])
    ax.set_title("Data coverage by energy year (* provisional)", loc="left")
    ax.set_ylabel("Buildings")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout(); fig.savefig(FIG / "1_coverage.png"); plt.close(fig)

    # 2. Energy use, balanced panel 2021-2024 ----------------------------------
    ey = [2021, 2022, 2023, 2024]
    pe = balanced(df, ey, ["eui", "sqft", "energy"])
    e = pe.groupby("energy_year").agg(buildings=("berdo_id", "nunique"), energy=("energy", "sum"),
                                       sqft=("sqft", "sum"), median_eui=("eui", "median"))
    e["weighted_eui"] = e["energy"] / e["sqft"]
    e.to_csv(TAB / "energy_panel.csv")
    out["energy_panel_n"] = int(e["buildings"].iloc[0])
    out["energy_change"] = e["weighted_eui"].iloc[-1] / e["weighted_eui"].iloc[0] - 1

    # 3. Emissions, balanced panel 2022-2024, with grid decomposition -----------
    gy = [2022, 2023, 2024]
    pg = balanced(df, gy, ["ghg", "sqft"])
    g = pg.groupby("energy_year").agg(buildings=("berdo_id", "nunique"), ghg=("ghg", "sum"),
                                       sqft=("sqft", "sum"), median_intensity=("intensity", "median"))
    g["weighted_intensity"] = g["ghg"] / g["sqft"]
    g.to_csv(TAB / "emissions_panel.csv")
    out["emissions_panel_n"] = int(g["buildings"].iloc[0])
    out["emissions_change"] = g["ghg"].iloc[-1] / g["ghg"].iloc[0] - 1

    #Grid vs. building: 2023-2024 energy years both report electricity emissions
    dy = [2023, 2024]
    pd_ = balanced(df, dy, ["ghg", "sqft", "elec"])
    base_ef = effective_grid_ef(2023)
    pd_ = pd_.assign(ghg_fixed_grid=pd_["ghg"] - pd_["elec"]
                     + pd_["elec"] * base_ef / pd_["energy_year"].map(effective_grid_ef))
    dec = pd_.groupby("energy_year")[["ghg", "ghg_fixed_grid", "elec"]].sum()
    total = dec.loc[2024, "ghg"] - dec.loc[2023, "ghg"]
    building = dec.loc[2024, "ghg_fixed_grid"] - dec.loc[2023, "ghg_fixed_grid"]
    grid = total - building
    decomp = pd.DataFrame({"tons": [total / 1000, grid / 1000, building / 1000]},
                          index=["Total change", "Cleaner grid", "Buildings (energy use and fuel mix)"])
    decomp["share_of_2023_emissions"] = decomp["tons"] * 1000 / dec.loc[2023, "ghg"]
    decomp.to_csv(TAB / "grid_decomposition_2023_2024.csv")
    out.update(decomp_n=int(pd_["berdo_id"].nunique()), decomp=decomp,
               elec_share_2023=dec.loc[2023, "elec"] / dec.loc[2023, "ghg"],
               ef_2023=base_ef, ef_2024=effective_grid_ef(2024))

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.6, 3.4), gridspec_kw={"width_ratios": [1, 1.15]})
    #Both series indexed to 2022, the first year both exist
    idx_e = e["weighted_eui"] / e.loc[2022, "weighted_eui"] * 100
    idx_g = g["weighted_intensity"] / g.loc[2022, "weighted_intensity"] * 100
    a1.plot(e.index, idx_e, "o-", color=BLUE, label=f"Energy use per sq ft ({out['energy_panel_n']:,} buildings)")
    a1.plot(g.index, idx_g, "s-", color=ORANGE, label=f"Emissions per sq ft ({out['emissions_panel_n']:,} buildings)")
    for x_, y_ in zip(e.index, idx_e):
        a1.annotate(f"{y_:.0f}", (x_, y_), textcoords="offset points", xytext=(0, 6), ha="center", fontsize=7, color=BLUE)
    for x_, y_ in zip(g.index, idx_g):
        a1.annotate(f"{y_:.0f}", (x_, y_), textcoords="offset points", xytext=(0, -12), ha="center", fontsize=7, color=ORANGE)
    a1.axhline(100, color=GREY, lw=0.6, ls=":")
    a1.set_xticks(ey); a1.set_ylabel("Index (2022 = 100)")
    lo = min(idx_e.min(), idx_g.min()); a1.set_ylim(lo - 3, 103)
    a1.set_title("Same buildings every year, floor-area weighted", loc="left")
    a1.legend(frameon=False, fontsize=7.5, loc="lower left")
    labels = ["Total change", "Cleaner grid", "Buildings (energy use, fuel mix)"]
    vals = decomp["tons"].values
    a2.barh(labels[::-1], vals[::-1], color=[GREY, BLUE, ORANGE][::-1])
    big = abs(vals).max()
    for i, (v, sh) in enumerate(zip(vals[::-1], decomp["share_of_2023_emissions"].values[::-1])):
        txt = f"{v:,.0f} t ({sh:+.1%})"
        if abs(v) > big * 0.45:      #label inside long bars
            a2.text(v / 2, i, txt, va="center", ha="center", fontsize=7.5, color="white", fontweight="bold")
        else:                        #label beside short bars
            a2.text(v - big * 0.02, i, txt, va="center", ha="right", fontsize=7.5)
    a2.axvline(0, color="black", lw=0.6)
    a2.set_xlim(vals.min() * 1.05, big * 0.03)
    a2.set_title(f"2023→2024 emissions change ({out['decomp_n']:,} bldgs)", loc="left")
    a2.set_xlabel("Metric tons CO₂e")
    fig.tight_layout(); fig.savefig(FIG / "2_trends_and_grid.png"); plt.close(fig)

    # 4. Share over the 2025-29 limit ---------------------------------------
    pl = pg.copy()
    pl["limit"] = pl.apply(limit_2025, axis=1)
    pl = pl.dropna(subset=["limit"])
    pl["over"] = pl["intensity"] > pl["limit"]
    share = pl.groupby("energy_year")["over"].mean()
    allb = df[df["energy_year"].between(2022, 2025)].dropna(subset=["intensity"]).copy()
    allb["limit"] = allb.apply(limit_2025, axis=1)
    allb = allb.dropna(subset=["limit"])
    share_all = (allb["intensity"] > allb["limit"]).groupby(allb["energy_year"]).mean()
    pd.DataFrame({"panel_share_over": share, "all_reporting_share_over": share_all}).to_csv(
        TAB / "share_over_2025_limit.csv")
    out["share_over"] = share
    out["share_over_2025"] = share_all.get(2025)
    fig, ax = plt.subplots(figsize=(6.4, 3.1))
    ax.plot(share.index, share * 100, "o-", color=RED, label="Same buildings every year")
    ax.plot(share_all.index, share_all * 100, "s--", color=GREY, label="All buildings reporting that year")
    ax.set_xticks([2022, 2023, 2024, 2025], ["2022", "2023", "2024", "2025*"])
    ax.set_ylabel("% above the 2025–29 limit"); ax.set_ylim(0, None)
    ax.set_title("Buildings that would exceed the 2025–29 limit (* provisional)", loc="left")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "3_share_over_limit.png"); plt.close(fig)

    # 5. Persistence: does last year predict this year? ---------------------
    a = df[df["energy_year"] == 2023].dropna(subset=["intensity"]).drop_duplicates("berdo_id")
    b = df[df["energy_year"] == 2024].dropna(subset=["intensity"]).drop_duplicates("berdo_id")
    m = a.merge(b, on="berdo_id", suffixes=("_23", "_24"))
    m = m[(m["intensity_23"] > 0) & (m["intensity_24"] > 0)]
    m["limit"] = m.apply(lambda r: limit_2025({"property_type": r["property_type_24"],
                                                "all_property_types": r["all_property_types_24"]}), axis=1)
    m = m.dropna(subset=["limit"])
    r = np.corrcoef(np.log(m["intensity_23"]), np.log(m["intensity_24"]))[0, 1]
    over23, over24 = m["intensity_23"] > m["limit"], m["intensity_24"] > m["limit"]
    trans = pd.crosstab(over23.map({True: "Over in 2023", False: "Under in 2023"}),
                        over24.map({True: "Over in 2024", False: "Under in 2024"}))
    trans.to_csv(TAB / "over_limit_transitions_2023_2024.csv")
    out.update(persist_n=len(m), persist_r=r,
               stay_over=(over23 & over24).sum() / over23.sum(),
               become_over=(~over23 & over24).sum() / (~over23).sum())
    fig, ax = plt.subplots(figsize=(4.6, 4.2))
    ax.scatter(m["intensity_23"], m["intensity_24"], s=5, alpha=0.35, color=BLUE, linewidths=0)
    lim = [0.3, 60]
    ax.plot(lim, lim, color=GREY, lw=0.8)
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("2023 emissions intensity (kg CO₂e/sq ft)")
    ax.set_ylabel("2024 emissions intensity")
    ax.set_title(f"Year-to-year persistence (r = {r:.2f}, log scale)", loc="left")
    fig.tight_layout(); fig.savefig(FIG / "4_persistence.png"); plt.close(fig)

    # 6. By building category ---------------------------------------------
    from berdo.emissions import map_property_type
    pc = pg.assign(category=pg["property_type"].map(map_property_type)).dropna(subset=["category"])
    cat = pc.groupby(["category", "energy_year"]).agg(ghg=("ghg", "sum"), sqft=("sqft", "sum"),
                                                     n=("berdo_id", "nunique")).reset_index()
    cat["intensity"] = cat["ghg"] / cat["sqft"]
    w = cat.pivot(index="category", columns="energy_year", values="intensity")
    n = cat[cat["energy_year"] == 2022].set_index("category")["n"]
    w["buildings"] = n
    w["change_2022_2024"] = w[2024] / w[2022] - 1
    w = w[w["buildings"] >= 30].sort_values("change_2022_2024")
    w.to_csv(TAB / "intensity_by_category.csv")
    out["by_category"] = w
    fig, ax = plt.subplots(figsize=(6.4, 0.32 * len(w) + 0.9))
    ax.barh(w.index, w["change_2022_2024"] * 100,
            color=[BLUE if v < 0 else RED for v in w["change_2022_2024"]])
    for i, (v, k) in enumerate(zip(w["change_2022_2024"], w["buildings"])):
        ax.text(v * 100, i, f" {v:+.0%} ({int(k)})", va="center", fontsize=7.5)
    ax.axvline(0, color="black", lw=0.6)
    ax.set_xlabel("Change in emissions per sq ft, 2022→2024 (%)")
    ax.set_title("By building category (same buildings; categories with 30+)", loc="left")
    fig.tight_layout(); fig.savefig(FIG / "5_by_category.png"); plt.close(fig)

    # Summary -----------------------------------------------------------------
    print("COVERAGE\n", cov.to_string(), "\n")
    print(f"Energy use panel ({out['energy_panel_n']:,} buildings, 2021-2024):\n{e.round(2).to_string()}")
    print(f"  floor-area-weighted EUI change 2021->2024: {out['energy_change']:+.1%}\n")
    print(f"Emissions panel ({out['emissions_panel_n']:,} buildings, 2022-2024):\n{g.round(3).to_string()}")
    print(f"  total emissions change 2022->2024: {out['emissions_change']:+.1%}\n")
    print(f"Grid decomposition 2023->2024 ({out['decomp_n']:,} buildings; electricity "
          f"{out['elec_share_2023']:.0%} of 2023 emissions; grid factor {out['ef_2023']:.0f} -> "
          f"{out['ef_2024']:.0f} kg/MWh):\n{out['decomp'].round(3).to_string()}\n")
    print("Share over the 2025-29 limit (panel):", (out["share_over"] * 100).round(1).to_dict(),
          "| 2025 provisional, all reporting:", round(out["share_over_2025"] * 100, 1) if out["share_over_2025"] else None)
    print(f"\nPersistence 2023->2024 ({out['persist_n']:,} buildings): log-intensity r = {out['persist_r']:.3f}; "
          f"over->over {out['stay_over']:.0%}; under->over {out['become_over']:.1%}")
    print("\nBy category (2022->2024):\n", w[["buildings", 2022, 2024, "change_2022_2024"]].round(3).to_string())


if __name__ == "__main__":
    main()
