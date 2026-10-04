"""
Official values, checked against the City's documents:
  - BERDO Emissions Factors List (updated September 18, 2026)
  - BERDO Policies & Procedures Version 5 (adopted September 14, 2026), Appendix B
  - BERDO ordinance, Table 1 and section (m)(d)
If the City publishes new values, these tests should fail until the tables are updated.
"""
from berdo.regulations import (
    ACP_RATE, BERDO_STANDARDS, FUEL_EF_KG_PER_KBTU, PROJECTED_GRID_EF, RPS_CLASS_I,
    DISTRICT_STEAM_EF, REC_CONNECTOR_TIERS,
)


def test_acp_rate_matches_ordinance():
    assert ACP_RATE == 234


def test_emissions_standards_match_ordinance_table_1():
    table_1 = {
        "Assembly": [7.8, 4.6, 3.3, 2.1, 1.1, 0], "College/University": [10.2, 5.3, 3.8, 2.5, 1.2, 0],
        "Education": [3.9, 2.4, 1.8, 1.2, 0.6, 0], "Food Sales & Service": [17.4, 10.9, 8.0, 5.4, 2.7, 0],
        "Healthcare": [15.4, 10.0, 7.4, 4.9, 2.4, 0], "Lodging": [5.8, 3.7, 2.7, 1.8, 0.9, 0],
        "Manufacturing/Industrial": [23.9, 15.3, 10.9, 6.7, 3.2, 0], "Multifamily Housing": [4.1, 2.4, 1.8, 1.1, 0.6, 0],
        "Office": [5.3, 3.2, 2.4, 1.6, 0.8, 0], "Retail": [7.1, 3.4, 2.4, 1.5, 0.7, 0],
        "Services": [7.5, 4.5, 3.3, 2.2, 1.1, 0], "Storage": [5.4, 2.8, 1.8, 1.0, 0.4, 0],
        "Technology/Science": [19.2, 11.1, 7.8, 5.1, 2.5, 0],
    }
    assert {k: [float(x) for x in v] for k, v in BERDO_STANDARDS.items()} == \
           {k: [float(x) for x in v] for k, v in table_1.items()}


def test_projected_grid_factors_match_city_appendix_b():
    appendix_b = {2022: 270, 2023: 263, 2024: 256, 2025: 249, 2026: 242, 2027: 265, 2028: 265,
                  2029: 264, 2030: 259, 2031: 254, 2032: 249, 2033: 243, 2034: 237, 2035: 231,
                  2036: 224, 2037: 217, 2038: 211, 2039: 204, 2040: 198, 2041: 192, 2042: 187,
                  2043: 182, 2044: 177, 2045: 173, 2046: 168, 2047: 163, 2048: 159, 2049: 155, 2050: 150}
    assert PROJECTED_GRID_EF == appendix_b


def test_rps_class_i_matches_225_cmr_14_07():
    expected = [20, 22, 24, 27, 30, 33, 36, 39, 40] + list(range(41, 61))
    assert [round(RPS_CLASS_I[y] * 100) for y in range(2022, 2051)] == expected


def test_fuel_factors_match_city_emissions_factors_list():
    city = {"Natural gas": 53.11, "Propane": 64.25, "Fuel oil #1": 73.50, "Fuel oil #2": 74.21,
            "Fuel oil #4": 75.29, "Fuel oil #5/#6": 75.35, "Diesel": 74.21, "Kerosene": 77.69,
            "District steam": 66.40}
    for fuel, kg_per_mmbtu in city.items():
        assert abs(FUEL_EF_KG_PER_KBTU[fuel] * 1000 - kg_per_mmbtu) < 1e-9, fuel


def test_named_district_steam_factors_match_city_list():
    assert round(DISTRICT_STEAM_EF["Vicinity District Steam (Boston)"] * 1000, 1) == 58.1
    assert round(DISTRICT_STEAM_EF["MATEP District Steam"] * 1000, 1) == 62.2


def test_rec_connector_tiers_are_sorted_and_complete():
    mins = [m for m, _ in REC_CONNECTOR_TIERS]
    assert mins == sorted(mins, reverse=True) and mins[-1] == 1
