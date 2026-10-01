"""
Preparing and searching the City's BERDO data: cleaning, year detection, campus rows,
linking buildings across years, and lookups. No Streamlit.
"""
import pandas as pd
import re
from berdo.regulations import (
    PROJECTED_GRID_EF,
)
from berdo.schema import (
    COLUMN_RENAME_MAP,
    FUEL_USAGE_COLUMNS,
    REQUIRED_COLUMNS,
)
from berdo.emissions import (
    effective_grid_ef,
    evaluate_building,
)


    
def standardize_address_series(series):
    """
    This section addresses standardization.
    IT also strips out full address details (like city, state, zip) after a comma.
    """
    extracted = series.fillna("").astype(str).str.split(",").str[0]
    
    cleaned = (
        extracted
        .str.strip()
        .str.upper()
        .str.replace(".", "", regex=False)
        .str.replace(" STREET", " ST", regex=False)
        .str.replace(" AVENUE", " AVE", regex=False)
        .str.replace(" ROAD", " RD", regex=False)
    )
    return cleaned

def infer_primary_fuel(row) -> str:
    """
    Infer a building's primary heating fuel from BERDO reported usage columns.
    All values converted to kBtu for comparison.
    Electricity: kWh × 3.412 → kBtu.
    Fuel oils combined into one bucket.
    Returns dominant fuel if >60% of total, else 'Mixed / unknown'.
    Maps to the dropdown options used in the Retrofit Estimator and Incentive Optimizer.
    """
    import math

    def _get(col):
        v = row.get(col)
        try:
            f = float(v)
            return 0.0 if math.isnan(f) else f
        except (TypeError, ValueError):
            return 0.0

    gas_kbtu   = _get("fuel_natural_gas_kbtu")
    elec_kbtu  = _get("fuel_electricity_kwh") * 3.412
    steam_kbtu = _get("fuel_district_steam_kbtu") + _get("fuel_district_hot_water_kbtu")
    oil_kbtu   = (_get("fuel_oil1_kbtu") + _get("fuel_oil2_kbtu") +
                  _get("fuel_oil4_kbtu") + _get("fuel_oil56_kbtu"))
    other_kbtu = _get("fuel_propane_kbtu") + _get("fuel_diesel_kbtu") + _get("fuel_kerosene_kbtu")

    total = gas_kbtu + elec_kbtu + steam_kbtu + oil_kbtu + other_kbtu
    if total <= 0:
        return "Mixed / unknown"

    buckets = {
        "Natural gas":    gas_kbtu,
        "Electric":       elec_kbtu,
        "District steam": steam_kbtu,
        "Fuel oil":       oil_kbtu,
        "Mixed / unknown": other_kbtu,
    }
    dominant_fuel  = max(buckets, key=buckets.get)
    dominant_share = buckets[dominant_fuel] / total

    if dominant_share >= 0.60:
        return dominant_fuel
    return "Mixed / unknown"


def get_fuel_breakdown(row) -> list:
    """
    Returns a list of (label, kBtu, pct) tuples for non-zero fuels,
    sorted descending by kBtu. Used to display the fuel breakdown in the UI.
    """
    import math

    def _get(col):
        v = row.get(col)
        try:
            f = float(v)
            return 0.0 if math.isnan(f) else f
        except (TypeError, ValueError):
            return 0.0

    buckets = {
        "Natural gas":    _get("fuel_natural_gas_kbtu"),
        "Electricity":    _get("fuel_electricity_kwh") * 3.412,
        "District steam": _get("fuel_district_steam_kbtu") + _get("fuel_district_hot_water_kbtu"),
        "Fuel oil":       (_get("fuel_oil1_kbtu") + _get("fuel_oil2_kbtu") +
                           _get("fuel_oil4_kbtu") + _get("fuel_oil56_kbtu")),
        "Other":          _get("fuel_propane_kbtu") + _get("fuel_diesel_kbtu") + _get("fuel_kerosene_kbtu"),
    }
    total = sum(buckets.values())
    if total <= 0:
        return []
    return sorted(
        [(label, kbtu, kbtu / total * 100)
         for label, kbtu in buckets.items() if kbtu > 0],
        key=lambda x: x[1], reverse=True
    )


class MissingColumnsError(ValueError):
    """Raised when a BERDO CSV lacks columns the tool requires."""
    def __init__(self, missing, available):
        super().__init__(f"Missing required columns: {missing}")
        self.missing, self.available = missing, available


def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize one year's BERDO disclosure: rename columns, clean IDs, mark campus
    rows, convert numbers, fix Site EUI, and compute GHG intensity. Pure (no Streamlit).
    Raises MissingColumnsError if required columns are absent.
    """
    df = df.copy()
    df.columns = df.columns.astype(str).str.strip()
    df = df.rename(columns=COLUMN_RENAME_MAP)
    #Stable identifiers for linking the same building across years
    for _id_col in ("berdo_id", "tax_parcel_id", "campus_id"):
        if _id_col in df.columns:
            df[_id_col] = df[_id_col].map(normalize_id)
    df = mark_campus_rows(df)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise MissingColumnsError(missing, list(df.columns))

    df["gross_floor_area"] = pd.to_numeric(df["gross_floor_area"], errors="coerce")
    df["site_eui"]         = pd.to_numeric(df["site_eui"],         errors="coerce")
    df["ghg_emissions"]    = pd.to_numeric(df["ghg_emissions"],    errors="coerce")
    df["compliance_year"]  = pd.to_numeric(df["compliance_year"],  errors="coerce")

    #Load fuel usage columns as numeric
    fuel_cols = [
        "fuel_natural_gas_kbtu", "fuel_electricity_kwh",
        "fuel_district_steam_kbtu", "fuel_district_hot_water_kbtu",
        "fuel_oil1_kbtu", "fuel_oil2_kbtu", "fuel_oil4_kbtu", "fuel_oil56_kbtu",
        "fuel_propane_kbtu", "fuel_diesel_kbtu", "fuel_kerosene_kbtu",
    ]
    for col in fuel_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
            
            #Deductions block for _load_single_csv
    
    #Reported electricity emissions. Missing stays missing (not 0), so buildings
    #without a breakdown fall back to the sidebar estimate instead of 0%.
    if "elec_emissions_kg" in df.columns:
        df["elec_emissions_kg"] = pd.to_numeric(df["elec_emissions_kg"], errors="coerce")

    #Zero-out negative electricity net metering (prevents negative roll-over)
    if "fuel_electricity_kwh" in df.columns:
        df["fuel_electricity_kwh"] = df["fuel_electricity_kwh"].clip(lower=0)
        
    #Subtract excluded EV emissions (requires 'ev_charging_kwh' column mapped)
    if "ev_charging_kwh" in df.columns:
        df["ev_charging_kwh"] = pd.to_numeric(df["ev_charging_kwh"], errors="coerce").fillna(0)
        ev_deduction_kg = df["ev_charging_kwh"] * (effective_grid_ef(2025) / 1000) # Assumes 2025 base EF
        df["ghg_emissions"] = (df["ghg_emissions"] - ev_deduction_kg).clip(lower=0)

    valid = (
        df["ghg_emissions"].notna() &
        df["gross_floor_area"].notna() &
        (df["gross_floor_area"] > 0)
    )
    df["ghg_intensity_kgco2e_sqft"] = pd.NA
    df.loc[valid, "ghg_intensity_kgco2e_sqft"] = (
        df.loc[valid, "ghg_emissions"] / df.loc[valid, "gross_floor_area"]
    )

    df["compliance_status"] = (
        df["compliance_status"].astype(str).str.lower().str.strip()
    )

    #Site EUI: in the 2026 disclosure the City's Site EUI column repeats the GHG
    #intensity for most buildings, so calculate it from total site energy instead.
    if "total_site_energy_kbtu" in df.columns:
        energy = pd.to_numeric(df["total_site_energy_kbtu"], errors="coerce")
        ok = energy.notna() & df["gross_floor_area"].notna() & (df["gross_floor_area"] > 0)
        df.loc[ok, "site_eui"] = energy[ok] / df.loc[ok, "gross_floor_area"]
        df["site_eui_calculated"] = ok

    #The City's own emissions compliance results (2026 disclosure onward)
    if "emissions_status" in df.columns:
        df["emissions_status"] = df["emissions_status"].where(df["emissions_status"].notna(), None)
        df["emissions_status"] = df["emissions_status"].map(
            lambda v: str(v).strip() if isinstance(v, str) and v.strip() else None)
        #"State" moved from reporting status to emissions status in 2026; keep one rule
        is_state = df["emissions_status"].fillna("").str.lower().eq("state")
        df.loc[is_state, "compliance_status"] = "state"
    if "official_standard" in df.columns:
        df["official_standard"] = pd.to_numeric(df["official_standard"], errors="coerce")
    return df


def detect_data_year(df: pd.DataFrame):
    """
    Year of energy use a dataset covers, read from the data itself.
    The City calculates electricity emissions as kWh x (1 - RPS Class I) x that year's
    projected grid factor, so the most common emissions-per-MWh value identifies the
    year (2025 file: 194.56 = 2024; 2026 file: 181.77 = 2025). Buildings that bought
    renewables have other values, but the year's factor is still the most common.
    Returns None for files without electricity emissions (2022 and 2023 disclosures).
    """
    if "elec_emissions_kg" not in df.columns or "fuel_electricity_kwh" not in df.columns:
        return None
    kwh = pd.to_numeric(df["fuel_electricity_kwh"], errors="coerce")
    kg = pd.to_numeric(df["elec_emissions_kg"], errors="coerce")
    factor = (kg / (kwh / 1000))[(kwh > 100_000) & (kg > 0)].round(2)
    if len(factor) < 50:
        return None
    counts = factor.value_counts()
    if counts.iloc[0] < 0.15 * len(factor):
        return None
    most_common = counts.index[0]
    for yr in sorted(PROJECTED_GRID_EF):
        if abs(effective_grid_ef(yr) - most_common) < 0.05:
            return yr
    return None


def mark_campus_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Campus reporting in the City's disclosure has two kinds of rows:
      - summary rows: totals for a whole campus (not a building). Identified by a
        City note starting "This is a campus", or a BERDO ID that is one of the
        year's campus IDs (e.g. "C10002").
      - member rows: individual buildings with a Corresponding Campus ID. Per the
        City, these rows "may not reflect the full building's energy and water use."
    Adds is_campus_summary, is_campus_member, and campus_key (the campus ID to join on).
    """
    df = df.copy()
    campus_col = df["campus_id"] if "campus_id" in df.columns else pd.Series(None, index=df.index)
    ids = df["berdo_id"] if "berdo_id" in df.columns else pd.Series(None, index=df.index)
    notes = (df["city_notes"] if "city_notes" in df.columns
             else pd.Series("", index=df.index)).fillna("").astype(str)
    campus_ids = set(campus_col.dropna())
    id_is_campus = ids.isin(campus_ids) & ids.notna()
    df["is_campus_summary"] = notes.str.strip().str.startswith("This is a campus") | id_is_campus
    df["campus_key"] = ids.where(id_is_campus, campus_col)
    df["is_campus_member"] = campus_col.notna() & ~df["is_campus_summary"]
    return df


def buildings_only(df: pd.DataFrame) -> pd.DataFrame:
    """Drop campus summary rows, which hold campus totals rather than a building."""
    if "is_campus_summary" in df.columns:
        return df[~df["is_campus_summary"].fillna(False).astype(bool)]
    return df


def campus_context(df: pd.DataFrame, campus_id):
    """Summary totals and member buildings for one campus in one year's data."""
    campus_id = normalize_id(campus_id)
    if not campus_id or "campus_key" not in df.columns:
        return None
    rows = df[df["campus_key"] == campus_id]
    summary = rows[rows["is_campus_summary"]]
    members = rows[rows["is_campus_member"]]
    out = {"campus_id": campus_id, "members": members, "summary": None}
    if not summary.empty:
        s = summary.iloc[0]
        gfa = pd.to_numeric(s.get("gross_floor_area"), errors="coerce")
        ghg = pd.to_numeric(s.get("ghg_emissions"), errors="coerce")
        out["summary"] = {
            "gfa": gfa, "ghg": ghg,
            "intensity": (ghg / gfa) if pd.notna(ghg) and pd.notna(gfa) and gfa > 0 else None,
            "property_type": s.get("property_type"),
        }
    return out


def normalize_id(v):
    """Clean an ID to a string ('100182.0' -> '100182'); None if missing."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    s = str(v).strip()
    if s.lower() in ("", "nan", "none"):
        return None
    return s[:-2] if s.endswith(".0") else s


def _standardize_one(address) -> str:
    return standardize_address_series(pd.Series([address])).iloc[0]


def _pick_record(matches: pd.DataFrame):
    """
    When one building has several records in a year, prefer the record with GHG
    data, then the larger floor area. Returns (row, had_duplicates).
    """
    if len(matches) == 1:
        return matches.iloc[0], False
    ranked = matches.assign(
        _has_ghg=pd.to_numeric(matches.get("ghg_intensity_kgco2e_sqft"), errors="coerce").notna(),
        _gfa=pd.to_numeric(matches.get("gross_floor_area"), errors="coerce").fillna(0),
    ).sort_values(["_has_ghg", "_gfa"], ascending=False)
    return ranked.iloc[0], True


def find_building_in_year(df: pd.DataFrame, berdo_id=None, parcel_id=None, address=None):
    """
    Find one building's record in one year's data.

    1. BERDO ID, when the year has IDs (2022 onward).
    2. Tax Parcel ID, for years without BERDO IDs (2021), only when that parcel
       has a single building; parcels can contain several buildings.
    3. Exact standardized address, as a last resort.

    Returns (row, matched_by, had_duplicates) or None.
    """
    berdo_id, parcel_id = normalize_id(berdo_id), normalize_id(parcel_id)
    df = buildings_only(df)
    year_has_ids = "berdo_id" in df.columns and df["berdo_id"].notna().any()

    if year_has_ids and berdo_id:
        m = df[df["berdo_id"] == berdo_id]
        if not m.empty:
            row, dup = _pick_record(m)
            return row, "BERDO ID", dup

    addr_std = (_standardize_one(address)
                if isinstance(address, str) and address.strip() else None)
    if not year_has_ids and parcel_id and "tax_parcel_id" in df.columns:
        m = df[df["tax_parcel_id"] == parcel_id]
        if not m.empty:
            n_buildings = standardize_address_series(m["Building Address"]).nunique()
            if n_buildings == 1:
                row, dup = _pick_record(m)
                return row, "Tax parcel", dup
            if addr_std:
                m2 = m[standardize_address_series(m["Building Address"]) == addr_std]
                if not m2.empty:
                    row, dup = _pick_record(m2)
                    return row, "Tax parcel + address", dup

    if addr_std:
        m = df[standardize_address_series(df["Building Address"]) == addr_std]
        if not m.empty:
            row, dup = _pick_record(m)
            return row, "Address (exact)", dup
    return None


def lookup_result_row(row, include_fuel=True) -> dict:
    """
    One lookup result: the building's fields plus its screening result.
    Used by both the address lookup (with fuel detail) and the owner lookup.
    """
    data_status, berdo_status, acp_2025, notes = evaluate_building(row)
    out = {
        "Building Address":            row.get("Building Address"),
        "Property Owner Name":         row.get("Property Owner Name"),
        "BERDO ID":                    row.get("berdo_id"),
        "Tax Parcel ID":               row.get("tax_parcel_id"),
        "First Compliance Year":       row.get("compliance_year"),
        "City Emissions Status":       row.get("emissions_status"),
        "Official Standard":           row.get("official_standard"),
        "Flexibility Measures":        row.get("flexibility_measures"),
        "Portfolio ID":                row.get("portfolio_id"),
        "Campus ID":                   row.get("campus_id") if row.get("is_campus_member") else None,
        "City Note":                   row.get("city_notes"),
        "Property Type":               row.get("property_type"),
        "All Property Types":          row.get("all_property_types"),
        "Gross Floor Area":            row.get("gross_floor_area"),
        "Site EUI":                    row.get("site_eui"),
        "Site EUI Calculated":         bool(row.get("site_eui_calculated", False)),
        "GHG Intensity (kgCO2e/sqft)": row.get("ghg_intensity_kgco2e_sqft"),
        "GHG Emissions (kgCO2e)":      row.get("ghg_emissions"),
        "Electricity Emissions (kgCO2e)": row.get("elec_emissions_kg"),
    }
    if include_fuel:
        out["Primary Fuel"] = infer_primary_fuel(row)
        for col in FUEL_USAGE_COLUMNS:
            out[col] = row.get(col)
    out.update({
        "Compliance Status":           row.get("compliance_status"),
        "Data Status":                 data_status,
        "BERDO Status":                berdo_status,
        "Est. ACP (2025–29)":          acp_2025,
        "Notes":                       "; ".join(notes),
    })
    return out


def lookup_building_priority(df, address):
    if not address or not isinstance(address, str):
        return None
        
    #Isolate the street component if a full address with commas is entered
    search_clean = address.split(",")[0].strip()
    search_std = (
        search_clean.upper()
        .replace(".", "")
        .replace(" STREET", " ST")
        .replace(" AVENUE", " AVE")
        .replace(" ROAD", " RD")
    )
    
    if not search_std:
        return None

    #Standardize the dataframe's address column using your updated series function
    df = buildings_only(df)
    df_addresses_std = standardize_address_series(df["Building Address"])
    
    #Filter matches where the standardized address contains the search query
    matches = df[df_addresses_std.str.startswith(search_std, na=False)]
    
    if matches.empty:
        return None
    #Exact address matches first, so "20 Gillette Park" beats "20 Gillette Park Rear"
    matches = (matches.assign(_exact=(df_addresses_std.loc[matches.index] == search_std))
               .sort_values("_exact", ascending=False))
        
    results = []

    for _, row in matches.iterrows():
        results.append(lookup_result_row(row, include_fuel=True))

    return pd.DataFrame(results)


#Owner portfolio lookup

def lookup_owner_portfolio(df, owner_name):
    """
    Returns a DataFrame of all buildings matching the given owner name
    (case-insensitive substring match), enriched with the same fields
    used by the single-building lookup.
    """
    import re
    owner_clean = owner_name.strip()
    df = buildings_only(df)
    matches = df[
        df["Property Owner Name"].astype(str).str.contains(
            re.escape(owner_clean), case=False, na=False
        )
    ]
    if matches.empty:
        return None

    results = []
    for _, row in matches.iterrows():
        results.append(lookup_result_row(row, include_fuel=False))
    return pd.DataFrame(results)
