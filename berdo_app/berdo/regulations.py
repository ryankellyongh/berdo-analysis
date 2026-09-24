"""
Official BERDO tables and program data used by the tool.

Every value here should trace to a source listed in SOURCES_REGISTER.
"""



#BERDO 2.0 emissions standards
#Source: BERDO ordinance (City of Boston Code 7-2.2), Table 1 (adopted October 2021).
#VERIFIED September 22, 2026: every value matches Table 1 of the ordinance text.
#Units: kg CO2e / sq ft / year
#Periods: 2025-29, 2030-34, 2035-39, 2040-44, 2045-49, 2050+

BERDO_STANDARDS = {
    "Assembly":                [7.8,  4.6,  3.3,  2.1, 1.1, 0.0],
    "College/University":      [10.2, 5.3,  3.8,  2.5, 1.2, 0.0],
    "Education":               [3.9,  2.4,  1.8,  1.2, 0.6, 0.0],
    "Food Sales & Service":    [17.4, 10.9, 8.0,  5.4, 2.7, 0.0],
    "Healthcare":              [15.4, 10.0, 7.4,  4.9, 2.4, 0.0],
    "Lodging":                 [5.8,  3.7,  2.7,  1.8, 0.9, 0.0],
    "Manufacturing/Industrial":[23.9, 15.3, 10.9, 6.7, 3.2, 0.0],
    "Multifamily Housing":     [4.1,  2.4,  1.8,  1.1, 0.6, 0.0],
    "Office":                  [5.3,  3.2,  2.4,  1.6, 0.8, 0.0],
    "Retail":                  [7.1,  3.4,  2.4,  1.5, 0.7, 0.0],
    "Services":                [7.5,  4.5,  3.3,  2.2, 1.1, 0.0],
    "Storage":                 [5.4,  2.8,  1.8,  1.0, 0.4, 0.0],
    "Technology/Science":      [19.2, 11.1, 7.8,  5.1, 2.5, 0.0],
}

COMPLIANCE_PERIODS = ["2025–29", "2030–34", "2035–39", "2040–44", "2045–49", "2050+"]

#ACP rate: USD 234 per metric ton CO2e, per ordinance section (m)(d). The Review Board
#reviews it every five years and it may be adjusted by regulation.
#VERIFIED September 22, 2026.
ACP_RATE = 234  #USD per metric ton CO2e over the limit


#Projected ISO New England grid emissions factors by year, kg CO2e/MWh.
#Sources: BERDO Policies & Procedures Version 5 (adopted September 14, 2026), Appendix B,
#unchanged since Version 3 (September 17, 2025); and the BERDO Emissions Factors List
#(updated September 18, 2026), Appendix B, which adds 2022 to 2024. VERIFIED September 23, 2026.
#CORRECTED September 22, 2026: the previous schedule (a straight-line decline to 71 kg/MWh in 2050)
#matched the official values only for 2025 and 2026.
PROJECTED_GRID_EF = {
    2022: 270, 2023: 263, 2024: 256,
    2025: 249, 2026: 242, 2027: 265, 2028: 265, 2029: 264,
    2030: 259, 2031: 254, 2032: 249, 2033: 243, 2034: 237,
    2035: 231, 2036: 224, 2037: 217, 2038: 211, 2039: 204,
    2040: 198, 2041: 192, 2042: 187, 2043: 182, 2044: 177,
    2045: 173, 2046: 168, 2047: 163, 2048: 159, 2049: 155,
    2050: 150,
}

#MA RPS Class I minimum standard, per 225 CMR 14.07(1).
#VERIFIED September 22, 2026 against the regulation's table: 27% in 2025, +3 points a year to
#39% in 2029, 40% in 2030, then +1 point a year "unless modified by law".
#BERDO electricity formula (Policies & Procedures v5, section 5.B):
#Emissions = Electricity Use × (100% − RPS Class I) × Emissions Factor
#Schedule: +3 pp/yr 2025–2029, 40% in 2030, +1 pp/yr thereafter.
RPS_CLASS_I = {
    2022: 0.20, 2023: 0.22, 2024: 0.24, 2025: 0.27, 2026: 0.30,
    2027: 0.33, 2028: 0.36, 2029: 0.39, 2030: 0.40,
}
for _y in range(2031, 2051):
    RPS_CLASS_I[_y] = round(0.40 + 0.01 * (_y - 2030), 2)

_EF_MIN_YR,  _EF_MAX_YR  = min(PROJECTED_GRID_EF), max(PROJECTED_GRID_EF)
_RPS_MIN_YR, _RPS_MAX_YR = min(RPS_CLASS_I),       max(RPS_CLASS_I)

#Representative year for each compliance period (midpoint, or period start for 2050)
PERIOD_REPRESENTATIVE_YEARS = [2027, 2032, 2037, 2042, 2047, 2050]


#Mapping from Energy Star Portfolio Manager property types → BERDO categories

#Mapping from Energy Star Portfolio Manager property types → BERDO categories

PROPERTY_TYPE_MAP = {
    #Assembly (2025-29 limit: 7.8)
    "aquarium":                             "Assembly",
    "convention center":                    "Assembly",
    "fitness center/health club/gym":       "Assembly",
    "heated swimming pool":                 "Assembly",
    "indoor arena":                         "Assembly",
    "ice/curling rink":                     "Assembly",
    "museum":                               "Assembly",
    "movie theater":                        "Assembly",
    "other - entertainment/public assembly":"Assembly",
    "other - recreation":                   "Assembly",
    "other - stadium":                      "Assembly",
    "performing arts":                      "Assembly",
    "race track":                           "Assembly",
    "social/meeting hall":                  "Assembly",
    "stadium (open)":                       "Assembly",
    "stadium (closed)":                     "Assembly",
    "swimming pool":                        "Assembly",
    "worship facility":                     "Assembly",
    "bowling alley":                        "Assembly",
    "casino":                               "Assembly",
    "roller rink":                          "Assembly",
    "zoo":                                  "Assembly",
    "boat marinas":                         "Assembly",
    "movie production studios":             "Assembly",
    "tv/radio broadcast studios":           "Assembly",

    #College/University (10.2)
    "college/university":                   "College/University",

    #Education (3.9)
    "adult education":                      "Education",
    "k-12 school":                          "Education",
    "other - education":                    "Education",
    "pre-school/daycare":                   "Education",
    "vocational school":                    "Education",

    #Food Sales & Service (17.4)
    "bar/nightclub":                        "Food Sales & Service",
    "fast food restaurant":                 "Food Sales & Service",
    "food sales":                           "Food Sales & Service",
    "food service":                         "Food Sales & Service",
    "other - restaurant/bar":               "Food Sales & Service",
    "restaurant":                           "Food Sales & Service",
    "supermarket/grocery store":            "Food Sales & Service",

    #Healthcare (15.4)
    "ambulatory surgical center":           "Healthcare",
    "hospital (general medical & surgical)":"Healthcare",
    "medical office":                       "Healthcare",
    "other - specialty hospital":           "Healthcare",
    "outpatient rehabilitation/physical therapy": "Healthcare",
    "urgent care/clinic/other outpatient":  "Healthcare",
    "veterinary office":                    "Healthcare",
    "residential care facility":            "Healthcare",
    "senior care community":                "Healthcare",
    "senior living community":              "Healthcare",
    "nursing home":                         "Healthcare", #legacy name

    #Lodging (5.8)
    "barracks":                             "Lodging",
    "hotel":                                "Lodging",
    "other - lodging/residential":          "Lodging",
    "residence hall/dormitory":             "Lodging",
    "single family home":                   "Lodging",
    "prison/incarceration":                 "Lodging", 

    #Manufacturing/Industrial (23.9)
    "manufacturing/industrial plant":       "Manufacturing/Industrial",
    "hydroponic, greenhouse and other growing facilities": "Manufacturing/Industrial",

    #Multifamily Housing (4.1)
    "multifamily housing":                  "Multifamily Housing",

    #Office (5.3)
    "financial office":                     "Office",
    "office":                               "Office",

    #Retail (7.1)
    "automobile dealership":                "Retail",
    "bank branch":                          "Retail",
    "enclosed mall":                        "Retail",
    "lifestyle center":                     "Retail",
    "other - mall":                         "Retail",
    "retail store":                         "Retail",
    "strip mall":                           "Retail",
    "wholesale club/supercenter":           "Retail",

    #Services (7.5)
    "convenience store without gas station":"Services",
    "courthouse":                           "Services",
    "energy/power station":                 "Services",
    "fire station":                         "Services",
    "library":                              "Services",
    "other - public services":              "Services",
    "other - services":                     "Services",
    "other - utility":                      "Services",
    "personal services (health/beauty, dry cleaning, etc.)": "Services",
    "police station":                       "Services",
    "repair services (vehicle, shoe, locksmith, etc.)":      "Services",
    "drinking water treatment & distribution": "Services",
    "mailing center/post office":           "Services",
    "transportation terminal/station":      "Services",
    "wastewater treatment plant":           "Services",

    #Storage (5.4)
    "distribution center":                  "Storage",
    "non-refrigerated warehouse":           "Storage",
    "parking":                              "Storage",
    "refrigerated warehouse":               "Storage",
    "self-storage facility":                "Storage",

    #Technology/Science (19.2)
    "data center":                          "Technology/Science",
    "laboratory":                           "Technology/Science",
    "other - technology/science":           "Technology/Science",
}

PROPERTY_TYPE_ALIASES = {
    "college / university":         "College/University",
    "residence hall / dormitory":   "Lodging",
    "manufacturing/industrial":     "Manufacturing/Industrial",
    #City data sometimes writes "etc" without the period
    "personal services (health/beauty, dry cleaning, etc)": "Services",
    "personal services (health/beauty dry cleaning etc.)":  "Services",   #Appendix A spelling
    "repair services (vehicle, shoe, locksmith, etc)":      "Services",
}
PROPERTY_TYPE_MAP.update(PROPERTY_TYPE_ALIASES)


#Emissions Planner model (pure: no Streamlit), so it can be tested directly
PLANNER_PERIOD_START_YEARS = [2025, 2030, 2035, 2040, 2045, 2050]
#BERDO compliance is annual: each five-year period is modeled year by year;
#"2050+" is modeled as the single year 2050.
PLANNER_PERIOD_YEARS = ([list(range(s, s + 5)) for s in PLANNER_PERIOD_START_YEARS[:-1]]
                        + [[PLANNER_PERIOD_START_YEARS[-1]]])

#Compliance gap calculation

#Coverage: does an emissions limit apply to this building in this period?
#One source of truth used by every tab, the portfolio, and the PDF.
PERIOD_START_YEARS = [2025, 2030, 2035, 2040, 2045, 2050]



#Priority scoring

#The City's "Reporting Compliance Status" marks some records "state" or "federal".
#Owners are mostly state and federal agencies (e.g., Massachusetts Port Authority).
#A city ordinance generally can't compel those owners like private ones, and no
#City statement on their treatment was found, so the tool reports their emissions
#for reference only and doesn't flag them as noncompliant.
GOVERNMENT_STATUSES = {"state": "State", "federal": "Federal"}


#RETROFIT COST BENCHMARKS
#Source: ASHRAE, RSMeans, NBI New Construction Cost Study, DOE BTO
#Units: national baseline USD per sq ft (low, high), Boston multiplier applied separately
#NOT VERIFIED against a current source; treat as order-of-magnitude benchmarks.

RETROFIT_COST_PER_SQFT = {
    #scope → (low $/sqft national, high $/sqft national, notes)
    "Lighting (LED retrofit + controls)":               (1.5,   4.0,   "LED fixtures, occupancy sensors, daylight controls"),
    "HVAC (tune-up, controls, VFDs)":                   (3.0,   8.0,   "Controls upgrades, VFDs on pumps/fans, recommissioning"),
    "HVAC (full system replacement)":                   (15.0,  35.0,  "Chiller, AHU, or boiler replacement"),
    "Building envelope (windows + insulation)":         (8.0,   20.0,  "Window replacement, roof/wall insulation"),
    "Electrification: HVAC (air-source heat pump)":    (10.0,  22.0,  "Air-source heat pump: lower cost, suitable for most commercial buildings"),
    "Electrification: HVAC (ground-source heat pump)": (20.0,  45.0,  "Ground-source (geothermal): higher efficiency, significantly higher upfront cost"),
    "Electrification: water heating":                  (2.0,   6.0,   "Heat pump water heaters replacing gas"),
    "Building-wide deep retrofit (all systems)":        (40.0,  100.0, "Comprehensive envelope + MEP overhaul"),
}

#Boston labor cost multiplier vs. national RSMeans baseline
#Source: RSMeans City Cost Index, Boston MA (2024-2025 avg)
BOSTON_LABOR_MULTIPLIER = 1.25

#BERDO EMISSIONS FACTORS FOR FUELS
#Source: BERDO Emissions Factors List (City of Boston, updated September 18, 2026),
#"2025 Emissions Factors". The City uses Portfolio Manager factors "as adopted in January
#2025", which differ slightly from Portfolio Manager's August 2025 technical reference.
#The City's list governs BERDO, so those values are used here.
#VERIFIED September 23, 2026. Units: kg CO2e per kBtu (= kg/mmBtu ÷ 1000).

FUEL_EF_KG_PER_KBTU = {
    "Natural gas":      0.05311,   #53.11
    "Propane":          0.06425,   #64.25
    "Fuel oil #1":      0.07350,   #73.50
    "Fuel oil #2":      0.07421,   #74.21, distillate / home heating oil
    "Fuel oil #4":      0.07529,   #75.29
    "Fuel oil #5/#6":   0.07535,   #75.35, residual
    "Diesel":           0.07421,   #74.21
    "Kerosene":         0.07769,   #77.69
    "District steam":   0.06640,   #Default District Steam; named systems differ, see below
    "Electricity":      None,      #use effective_grid_ef(): Appendix B × (1 − RPS Class I)
}

#District energy system factors, kg CO2e/kBtu.
#VERIFIED September 23, 2026 against the BERDO Emissions Factors List (September 18, 2026).
#Not currently used in any calculation.
DISTRICT_STEAM_EF = {
    "Default (unknown system)":              0.06640,
    "Vicinity District Steam (Boston)":      0.05810,
    "Vicinity District Steam (Longfellow)":  0.05110,
    "Vicinity District e-steam":             0.0,
    "MATEP District Steam":                  0.06220,
}

#Official City of Boston BERDO links. Verified September 22, 2026.
PATHWAYS_VERIFIED = "September 22, 2026"
BERDO_LINKS = {
    "berdo_home":         "https://www.boston.gov/departments/environment/berdo",
    "review_board":       "https://www.boston.gov/departments/environment/berdo-review-board",
    "flex_guide":         "https://www.boston.gov/sites/default/files/berdo/BERDO_FlexibilityMeasures.pdf",
    "compliance_guide":   "https://www.boston.gov/sites/default/files/berdo/BERDO_EmissionsCompliance.pdf",
    "apply_portal":       "https://bostonopendata.knack.com/air-pollution-control-commission#berdo-home-page/",
    "blended_template":   "https://docs.google.com/spreadsheets/d/1kZ4flS4Dr0u2U5wMDH9h3Q_xwVlcr5ANo3_Wnc81mNs/edit?usp=sharing",
    "portfolio_template": "https://docs.google.com/spreadsheets/d/1Z1fD6vUdyvJl3OS66p00auXBx4KsEXlxmzjCYTOGzNU/edit?usp=sharing",
    "ics_template":       "https://docs.google.com/spreadsheets/d/1lHr4RMHERfzDaQtruZARovwTi3YELdXZDIIRIxI60fE/edit?usp=sharing",
    "hcp_guide":          "https://docs.google.com/document/d/1G5hdDeFVSbTRmivYXtfaTOBeVrwJHQUlesyZpNBlsNs/edit?usp=sharing",
    "hcp_streamlined":    "https://docs.google.com/document/d/1T4hWz9LM_MNnFO5sQ77bYbDjKRpvFD5Fcx3MEyMSoUs/edit?usp=sharing",
    "retrofit_hub":       "https://www.boston.gov/departments/environment/retrofit-resource-hub",
    "renewable_guide":    "https://www.boston.gov/sites/default/files/berdo/BERDO_RenewableEnergy.pdf",
    "rec_connector":      "https://www.boston.gov/departments/environment/berdo/how-purchase-ma-class-i-recs-berdo-compliance",
    "eeif":               "https://www.boston.gov/departments/environment/equitable-emissions-investment-fund",
    "out_of_compliance":  "https://www.boston.gov/node/16572006",
    "one_on_one":         "https://www.boston.gov/departments/environment/berdo#support",
    "advisor_program":    "https://www.boston.gov/departments/environment/building-decarbonization-advisor-program",
    "city_calculator":    "https://berdocalculator.touchstoneiq.com/",
    "approved_flex":      "https://docs.google.com/spreadsheets/d/1txTR6pdCedSiuN04uuh8p64atlTfjIbHImJDi0YGas4/edit?usp=sharing",
}

#Recurring annual Review Board application deadlines (month, day), per the
#BERDO Review Board page. Stored as month/day so the "next deadline" never goes stale.
FLEX_DEADLINES = {
    "long_term_hcp":  (7, 1),
    "portfolio_ics":  (9, 1),
    "short_term_hcp": (10, 1),
}


#MA Class I REC pathway (BERDO Renewable Energy Quick Guide; City REC Connector Program).
#Retiring 1 MA Class I REC covers 1 MWh of otherwise-unmatched grid electricity,
#avoiding PROJECTED_GRID_EF[year] kg CO2e. RECs offset ELECTRICITY emissions only.
REC_CONNECTOR_DEADLINE = "October 31, 2026"   #for 2025 emissions compliance
#REC Connector pricing (Green Energy Consumers Alliance, berdo.greenenergyconsumers.org),
#all-inclusive of admin fees, valid through December 31, 2026. VERIFIED September 23, 2026.
#(minimum quantity, USD per REC)
REC_CONNECTOR_TIERS = [(2500, 42.0), (1000, 44.0), (500, 46.0), (100, 50.0), (50, 52.0), (1, 54.0)]
REC_CONNECTOR_PRICES_VALID_THROUGH = "December 31, 2026"
REC_DEFAULT_PRICE = 54.0   #1-49 tier; used only as the starting value for a custom price

#Convenient billing unit → kBtu conversions (EPA Portfolio Manager)
FUEL_UNIT_TO_KBTU = {
    "therms":   100.0,      #natural gas
    "ccf":      102.6,      #natural gas (hundred cubic feet)
    "mcf":      1026.0,     #natural gas, thousand cubic feet (Portfolio Manager calls this "Kcf")
    "gallons_oil2":  138.0, #fuel oil #2
    "gallons_oil4":  146.0, #fuel oil #4
    "gallons_oil56": 150.0,  #fuel oil #5/#6
    "gallons_propane": 92.0,
    "gallons_diesel":  138.0,
    "gallons_kerosene": 135.0,
    "kbtu":     1.0,
    "mmbtu":    1000.0,
    "kwh":      3.412,      #electricity
    "mwh":      3412.0,     #electricity
}

#INCENTIVE OPTIMIZER. data & logic

#Incentive stacking order: apply these first to preserve basis for later credits.
#Each entry has a priority rank (1 = apply first), conflict notes, and BERDO period relevance.
INCENTIVE_STACK = [
    {
        "name": "Mass Save: Commercial HVAC Rebates",
        "short": "Mass Save HVAC",
        "type": "Utility rebate",
        "priority": 1,
        "apply_first_reason": "Utility rebates are taxable income and reduce your 179D basis. Claim after filing taxes, but negotiate before project start.",
        "scopes": ["HVAC (tune-up, controls, VFDs)", "HVAC (full system replacement)",
                   "Electrification: HVAC (air-source heat pump)", "Electrification: HVAC (ground-source heat pump)"],
        "fuels": ["Natural gas", "Fuel oil", "Mixed / unknown", "Electric"],
        "amount_psf_low": 0.50,
        "amount_psf_high": 2.00,
        "amount_str": "Varies by equipment; see Mass Save's Heating & Cooling page for current rates. This tool's dollar estimate is unverified.",
        "eligibility": "MA commercial accounts with Eversource, National Grid, or Unitil",
        "expiration": "Program year 2026 (resets each January)",
        "conflicts": [],
        "stacks_with": ["IRA 179D", "IRA 45L"],
        "berdo_periods": ["2025–29", "2030–34"],
        "ownership": ["For-profit", "Nonprofit / Government"],
        "source": "https://www.masssave.com/en/business/rebates-offers-services/heating-and-cooling",
        "checklist": [
            "Contact your utility (Eversource / National Grid / Unitil) before project start",
            "Get pre-approval from Mass Save (required before installation)",
            "Select a Mass Save Trade Ally contractor",
            "Complete installation and submit documentation",
            "Receive rebate check (typically 6–8 weeks post-completion)",
        ],
    },
    {
        "name": "Mass Save: Lighting Rebates",
        "short": "Mass Save Lighting",
        "type": "Utility rebate",
        "priority": 1,
        "apply_first_reason": "Pre-approval required before installation: start here.",
        "scopes": ["Lighting (LED retrofit + controls)"],
        "fuels": ["Natural gas", "Fuel oil", "Mixed / unknown", "Electric"],
        "amount_psf_low": 0.10,
        "amount_psf_high": 0.60,
        "amount_str": "Varies by fixture and controls; see Mass Save's Lighting & Controls page for current rates. This tool's dollar estimate is unverified.",
        "eligibility": "MA commercial accounts",
        "expiration": "Program year 2026 (resets each January)",
        "conflicts": [],
        "stacks_with": ["IRA 179D"],
        "berdo_periods": ["2025–29", "2030–34"],
        "ownership": ["For-profit", "Nonprofit / Government"],
        "source": "https://www.masssave.com/en/business/rebates-offers-services/lighting-and-controls",
        "checklist": [
            "Contact Mass Save or your utility for pre-approval",
            "Select eligible LED fixtures from the approved product list",
            "Complete installation with a Trade Ally contractor",
            "Submit lighting inventory and rebate application",
        ],
    },
    {
        "name": "Mass Save: Deep Energy Retrofit",
        "short": "Mass Save Deep Retrofit",
        "type": "Utility rebate",
        "priority": 1,
        "apply_first_reason": "Requires energy model and pre-approval. Begin 3–6 months before construction.",
        "scopes": ["Building-wide deep retrofit (all systems)",
                   "Building envelope (windows + insulation)"],
        "fuels": ["Natural gas", "Fuel oil", "Mixed / unknown", "Electric"],
        "amount_psf_low": 0.50,
        "amount_psf_high": 3.00,
        "amount_str": "Custom incentive based on modeled savings; see Mass Save's Deep Energy Retrofit page. This tool's dollar estimate is unverified.",
        "eligibility": "MA commercial buildings; requires pre-approval and energy model",
        "expiration": "Program year 2026",
        "conflicts": [],
        "stacks_with": ["IRA 179D", "IRA 48C"],
        "berdo_periods": ["2025–29", "2030–34", "2035–39"],
        "ownership": ["For-profit", "Nonprofit / Government"],
        "source": "https://www.masssave.com/en/business/rebates-offers-services/deep-energy-retrofit",
        "checklist": [
            "Submit a pre-application to Mass Save Large Business program",
            "Commission an ASHRAE Level 2 energy audit",
            "Develop an energy model (EnergyPlus or eQUEST)",
            "Receive custom incentive offer from Mass Save",
            "Execute project and submit final documentation",
        ],
    },
    {
        "name": "IRA Section 179D",
        "short": "IRA 179D",
        "type": "Federal tax deduction",
        "priority": 2,
        "apply_first_reason": "Claim after utility rebates are received. Rebates reduce your depreciable basis, which affects 179D calculation.",
        "scopes": ["Lighting (LED retrofit + controls)", "HVAC (tune-up, controls, VFDs)",
                   "HVAC (full system replacement)", "Building envelope (windows + insulation)",
                   "Electrification: HVAC (air-source heat pump)", "Electrification: HVAC (ground-source heat pump)", "Building-wide deep retrofit (all systems)"],
        "fuels": ["Natural gas", "Fuel oil", "Mixed / unknown", "Electric"],
        "amount_psf_low": 0.59,   #2026 base (IRS Form 7205 instructions; Rev. Proc. 2025-32)
        "amount_psf_high": 5.94,  #2026 maximum with prevailing wage and apprenticeship
        "cash_value_factor": 0.21,   #deduction, not credit: worth marginal rate × amount
        "closed_to_new_projects": True,
        "amount_str": "Up to USD 5.94/sqft (2026, prevailing wage and apprenticeship, Rev. Proc. 2025-32); USD 0.59–1.19/sqft base",
        "eligibility": "For-profit owners; nonprofits/govts transfer deduction to designer",
        "expiration": "Only available for construction that began on or before June 30, 2026 (One Big Beautiful Bill Act, P.L. 119-21). Confirm with a tax advisor if your project started before that date.",
        "conflicts": [],
        "stacks_with": ["Mass Save rebates", "IRA 45L"],
        "berdo_periods": ["2025–29"],
        "ownership": ["For-profit"],
        "ownership_transfer": "Nonprofit / Government",
        "ownership_transfer_note": "Nonprofits and government owners can allocate the deduction to the project designer/engineer.",
        "source": "https://www.energy.gov/eere/buildings/179d-commercial-buildings-energy-efficiency-tax-deduction",
        "checklist": [
            "179D only applies to construction that began on or before June 30, 2026. Confirm your project start date with a tax advisor",
            "Engage a qualified third-party certifier (licensed engineer or contractor)",
            "Commission a 179D energy model demonstrating qualifying energy savings",
            "Ensure prevailing wage + apprenticeship compliance for the enhanced rate",
            "Obtain signed certification from the certifier",
            "Claim deduction on federal tax return (Form 3115 if prior year)",
        ],
    },
    {
        "name": "IRA Section 45L (multifamily)",
        "short": "IRA 45L",
        "type": "Federal tax credit",
        "priority": 2,
        "apply_first_reason": "Claim alongside 179D: these stack. Document unit-level improvements during construction.",
        "scopes": ["Electrification: HVAC (air-source heat pump)", "Electrification: HVAC (ground-source heat pump)",
                   "Building-wide deep retrofit (all systems)"],
        "fuels": ["Natural gas", "Fuel oil", "Mixed / unknown", "Electric"],
        "amount_psf_low": 0.50,
        "amount_psf_high": 5.00,
        "closed_to_new_projects": True,
        "amount_str": "USD 500–USD 2,500/unit (Energy Star); USD 1,000–USD 5,000/unit (Zero Energy Ready)",
        "eligibility": "Multifamily residential; new construction and substantial rehab",
        "expiration": "Terminated for homes acquired after June 30, 2026 (One Big Beautiful Bill Act, P.L. 119-21). Confirm eligibility with a tax advisor.",
        "conflicts": [],
        "stacks_with": ["Mass Save rebates", "IRA 179D"],
        "berdo_periods": ["2025–29", "2030–34"],
        "ownership": ["For-profit"],
        "berdo_types": ["Multifamily Housing"],
        "source": "https://www.irs.gov/credits-deductions/energy-efficient-home-credit",
        "checklist": [
            "Determine unit count and confirm project qualifies as 'substantial rehab'",
            "Select Energy Star or DOE Zero Energy Ready Home certification path",
            "Commission third-party Energy Star rater during construction",
            "Obtain Energy Star or ZERH certification for each unit",
            "Claim credit on federal return (Form 8908)",
        ],
    },
    {
        "name": "IRA Section 48C",
        "short": "IRA 48C",
        "type": "Federal tax credit",
        "priority": 3,
        "apply_first_reason": "Competitive allocation: apply early via IRS portal. May conflict with other IRA investment credits.",
        "scopes": ["Electrification: HVAC (air-source heat pump)", "Electrification: HVAC (ground-source heat pump)", "Electrification: water heating",
                   "Building-wide deep retrofit (all systems)"],
        "fuels": ["Natural gas", "Fuel oil", "Mixed / unknown"],
        "closed_to_new_projects": True,   #manufacturing-facility allocation; $10B fully allocated 2024
        "amount_psf_low": 0.60,
        "amount_psf_high": 3.00,
        "amount_str": "6% base (30% with prevailing wage and apprenticeship); capped per project",
        "eligibility": "Competitive allocation; manufacturing/industrial sites prioritized",
        "expiration": "Closed. The full USD 10B was allocated across two rounds (about USD 4B in March 2024, about USD 6B in January 2025). OBBBA sec. 70515 (P.L. 119-21) caps allocations at USD 10B, so no further rounds are expected.",
        "conflicts": ["IRA 48E", "Other IRA investment credits on same property"],
        "stacks_with": ["Mass Save rebates"],
        "berdo_periods": ["2025–29", "2030–34"],
        "ownership": ["For-profit"],
        "source": "https://www.irs.gov/credits-deductions/businesses/advanced-energy-project-credit",
        "checklist": [
            "No open allocation rounds: the USD 10B cap is fully allocated. Listed for reference only.",
            "Prepare project application (technology description, cost, job creation)",
            "Submit application during open window (allocations are competitive)",
            "If awarded, begin construction within required timeframe",
            "Comply with prevailing wage + apprenticeship for 30% rate",
            "Claim credit on federal return (Form 3468)",
        ],
    },
    {
        "name": "MassDEP Gap Energy Grant",
        "short": "MassDEP Gap Grant",
        "type": "State grant",
        "priority": 1,
        "apply_first_reason": "Competitive rounds with fixed deadlines; the grant fills the last funding gap after utility incentives.",
        "scopes": ["Lighting (LED retrofit + controls)", "HVAC (tune-up, controls, VFDs)",
                   "HVAC (full system replacement)", "Electrification: HVAC (air-source heat pump)",
                   "Electrification: HVAC (ground-source heat pump)", "Electrification: water heating",
                   "Building-wide deep retrofit (all systems)"],
        "fuels": ["Natural gas", "Fuel oil", "Mixed / unknown", "Electric"],
        "amount_psf_low": 0.0,
        "amount_psf_high": 0.0,   #per-project grant (USD 75,000 to 350,000); no $/sqft proxy
        "amount_str": "Gap IV round: USD 75,000 to 350,000 per grantee; USD 5M total program",
        "eligibility": "Narrow: publicly owned drinking water and wastewater facilities, food or agricultural nonprofits, and small food distribution or processing businesses. Most BERDO buildings will not qualify.",
        "expiration": "Periodic competitive rounds run by MassDEP's Clean Energy Results Program; check mass.gov for the current round",
        "conflicts": [],
        "stacks_with": ["Mass Save rebates"],
        "berdo_periods": ["2025–29", "2030–34"],
        "ownership": ["Nonprofit / Government", "For-profit"],
        "source": "https://mass.gov/info-details/massachusetts-gap-energy-grant-program",
        "checklist": [
            "Confirm your facility type is eligible for the current round",
            "Line up utility incentives (e.g., Mass Save) first; the grant fills the remaining gap",
            "Submit the application by the round's deadline",
            "Complete the project and submit documentation for reimbursement",
        ],
    },
    {
        "name": "Green Communities Grant",
        "short": "Green Communities",
        "type": "State grant",
        "priority": 1,
        "apply_first_reason": "Annual grant cycle: apply in the current round.",
        "scopes": ["Lighting (LED retrofit + controls)", "HVAC (tune-up, controls, VFDs)",
                   "HVAC (full system replacement)", "Building envelope (windows + insulation)",
                   "Electrification: HVAC (air-source heat pump)", "Electrification: HVAC (ground-source heat pump)",
                   "Building-wide deep retrofit (all systems)"],
        "fuels": ["Natural gas", "Fuel oil", "Mixed / unknown", "Electric"],
        "amount_psf_low": 0.0,
        "amount_psf_high": 0.0,   #per-municipality formula grant: no $/sqft proxy is meaningful
        "amount_str": "Competitive grants capped at USD 250,000 per municipality, or USD 500,000 for comprehensive building decarbonization",
        "eligibility": "Municipally owned buildings in MA communities with Green Community designation. Not available to private nonprofits.",
        "expiration": "Annual grant rounds; check DOER for current cycle",
        "conflicts": [],
        "stacks_with": ["Mass Save rebates"],
        "berdo_periods": ["2025–29", "2030–34", "2035–39"],
        "ownership": ["Nonprofit / Government"],
        "source": "https://www.mass.gov/info-details/green-communities-grants",
        "checklist": [
            "Confirm your municipality has Green Community designation",
            "Identify eligible measures in your approved Green Communities plan",
            "Submit application to DOER during open grant round",
            "Execute grant agreement and comply with reporting requirements",
        ],
    },
]

RETROFIT_SCOPES_OPT = list(RETROFIT_COST_PER_SQFT.keys())
FUEL_TYPES_OPT = ["Natural gas", "Fuel oil", "Electric", "District steam", "Mixed / unknown"]
OWNERSHIP_TYPES_OPT = ["For-profit", "Nonprofit / Government", "Not sure"]

#Sources & verification register
SOURCES_REGISTER = [
    ("Emissions standards (limits by use and period)", "Verified", "BERDO ordinance, Table 1"),
    ("ACP rate: USD 234 per metric ton", "Verified", "BERDO ordinance, section (m)(d); reviewed every 5 years"),
    ("Projected grid emissions factors, 2022 to 2050", "Corrected", "Policies & Procedures v5 (Sep 2026) and Emissions Factors List (Sep 18, 2026), Appendix B"),
    ("Electricity formula: use × (1 − RPS) × factor", "Verified", "BERDO Policies & Procedures v5, section 5.B"),
    ("RPS Class I schedule", "Verified", "225 CMR 14.07(1); Emissions Factors List, Appendix C"),
    ("Fuel and default district steam factors", "Verified", "BERDO Emissions Factors List (Sep 18, 2026)"),
    ("Property type to building use mapping", "Verified", "BERDO Policies & Procedures v5, Appendix A"),
    ("Blended standard formula and 10% primary-use rule", "Corrected", "BERDO ordinance (i); Policies & Procedures v5, section 6"),
    ("Daily fines: reporting and emissions", "Verified", "BERDO ordinance, section (r)"),
    ("Flexibility measure, REC Connector, and 2026 reporting deadlines", "Verified", "boston.gov BERDO and Review Board pages"),
    ("179D and 45L termination; 179D 2026 amounts", "Verified", "P.L. 119-21; IRS Form 7205 instructions"),
    ("48C: fully allocated, no new rounds", "Verified", "DOE 48C program page; P.L. 119-21 sec. 70515"),
    ("Green Communities grant caps", "Corrected", "Mass. DOER announcements"),
    ("MassDEP Gap Energy Grant (was mislabeled MassDOER)", "Corrected", "mass.gov Gap IV request for responses"),
    ("Dataset year = reporting year; energy use is the prior calendar year", "Verified", "BERDO reporting rule; City's estimated electricity emissions match prior-year grid factors exactly"),
    ("Reporting status definitions (in compliance, pending revisions, not submitted)", "Verified", "City 2024 Detailed Data Dictionary"),
    ("State and federal status values", "Unverified", "Not defined in the City's 2024 Data Dictionary"),
    ("First emissions compliance year: 35,000+ sq ft or 35+ units start with 2025 data", "Verified", "City 2024 Detailed Data Dictionary"),
    ("Parking left out of blended standard by default", "Unverified", "Not confirmed in City documents"),
    ("Mass Save rebate $/sqft estimates", "Unverified", "Mass Save business pages list programs but not dollar amounts; links updated"),
    ("Retrofit cost ranges and Boston labor multiplier", "Unverified", "Order-of-magnitude benchmarks"),
    ("REC Connector prices (USD 42 to 54 per REC by quantity)", "Corrected", "berdo.greenenergyconsumers.org, valid through Dec 31, 2026 (was a USD 40 placeholder)"),
    ("REC eligibility, generation window, and retirement deadline", "Verified", "boston.gov: How to Purchase MA Class I RECs for BERDO Compliance"),
    ("Fuel unit conversions (therms, ccf, Mcf, gallons)", "Corrected", "Portfolio Manager Thermal Energy Conversions, Fig. 3 (fuel oil #1: 139 kBtu/gal)"),
    ("Named district steam factors (Vicinity, MATEP)", "Verified", "BERDO Emissions Factors List (Sep 18, 2026); not used in calculations"),
]
SOURCES_VERIFIED_ON = "September 23, 2026"
