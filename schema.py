"""
Column names in the City's BERDO disclosures, mapped to the names the tool uses.

When the City renames a column, add the new name to that field's list in
CITY_COLUMN_NAMES. Nothing else needs to change. Older names stay, so earlier
years keep loading.
"""

#Each row: the tool's field name, every name the City has used for it, and what it is.
CITY_COLUMN_NAMES = [
    #Identifiers
    ("berdo_id",               ["BERDO ID"], "City's building ID (2022 onward)"),
    ("tax_parcel_id",          ["Tax Parcel ID"], "Assessing parcel ID"),
    ("campus_id",              ["Corresponding Campus ID"], "Campus a building belongs to"),
    ("portfolio_id",           ["Corresponding Portfolio ID"], "Approved Building Portfolio (2026 onward)"),
    ("Property Owner Name",    ["Parcel Owner Name"], "Owner (named 'Property Owner Name' before 2026)"),
    #Building description
    ("property_type",          ["Largest Property Type"], "Largest Portfolio Manager property type"),
    ("all_property_types",     ["All Property Types and GFAs", "All Property Types and GFAs (sq ft)"],
                               "Every use with its floor area"),
    ("gross_floor_area",       ["Reported Gross Floor Area (Sq Ft)", "Gross Floor Area (sq ft)"], "Floor area"),
    ("city_notes",             ["Notes"], "City's note on the record (through 2025)"),
    #Energy and emissions
    ("site_eui",               ["Site EUI (Energy Use Intensity kBtu/ft²)"], "Site EUI as published (recalculated when total energy is available)"),
    ("total_site_energy_kbtu", ["Total Site Energy Usage (kBtu)"], "Total site energy"),
    ("ghg_emissions",          ["Estimated Total GHG Emissions (kgCO2e)", "Estimated Total GHG Emissions e(kgCO2e)",
                                "Total GHG Emissions (kgCO2e)"], "Total GHG emissions"),
    ("elec_emissions_kg",      ["Electricity Emissions (kgCO2e)"], "Electricity emissions"),
    #Status and compliance
    ("compliance_status",      ["Reporting Compliance Status"], "Annual reporting status"),
    ("compliance_year",        ["First Emissions Compliance Year (Projected)", "First Emissions Compliance Year"],
                               "First year emissions limits apply"),
    ("emissions_status",       ["Emissions Compliance Status"], "City's emissions compliance result (2026 onward)"),
    ("official_standard",      ["Applicable Emissions Compliance Standard (kgCO2e/sq ft)"], "City's applicable limit (2026 onward)"),
    ("flexibility_measures",   ["Flexibility Measures"], "Flexibility measures on file (2026 onward)"),
    #Fuel usage (kBtu, except electricity in kWh)
    ("fuel_natural_gas_kbtu",        ["Natural Gas Usage (kBtu)"], ""),
    ("fuel_electricity_kwh",         ["Electricity Usage (kWh)"], ""),
    ("fuel_district_steam_kbtu",     ["District Steam Usage (kBtu)"], ""),
    ("fuel_district_hot_water_kbtu", ["District Hot Water Usage (kBtu)"], ""),
    ("fuel_oil1_kbtu",               ["Fuel Oil 1 Usage (kBtu)"], ""),
    ("fuel_oil2_kbtu",               ["Fuel Oil 2 Usage (kBtu)"], ""),
    ("fuel_oil4_kbtu",               ["Fuel Oil 4 Usage (kBtu)"], ""),
    ("fuel_oil56_kbtu",              ["Fuel Oil 5 and 6 Usage (kBtu)"], ""),
    ("fuel_propane_kbtu",            ["Propane Usage (kBtu)"], ""),
    ("fuel_diesel_kbtu",             ["Diesel Usage (kBtu)"], ""),
    ("fuel_kerosene_kbtu",           ["Kerosene Usage (kBtu)"], ""),
]

#City column name -> tool field name, built from the table above
COLUMN_RENAME_MAP = {city: field for field, names, _ in CITY_COLUMN_NAMES for city in names}

#Fields every disclosure must provide (after renaming)
REQUIRED_COLUMNS = [
    "Building Address", "Property Owner Name", "property_type",
    "gross_floor_area", "site_eui", "ghg_emissions",
    "compliance_status", "compliance_year",
]

FUEL_USAGE_COLUMNS = [
    "fuel_natural_gas_kbtu", "fuel_electricity_kwh", "fuel_district_steam_kbtu",
    "fuel_district_hot_water_kbtu", "fuel_oil1_kbtu", "fuel_oil2_kbtu", "fuel_oil4_kbtu",
    "fuel_oil56_kbtu", "fuel_propane_kbtu", "fuel_diesel_kbtu", "fuel_kerosene_kbtu",
]
