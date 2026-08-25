# BERDO Analysis

*Identifying reporting gaps, energy performance risks, and emissions reduction pathways in Boston buildings*

Boston's Building Emissions Reduction and Disclosure Ordinance (BERDO 2.0) sets declining greenhouse gas limits for large buildings through 2050. Compliance is not only an energy performance challenge, it is also a data visibility, reporting capacity, and ownership coordination problem. The buildings most in need of support are often not the highest energy users; they are the ones with missing property types, unreported energy data, or no record of submission at all.

This project analyzes Boston's BERDO public reporting data and includes a live screening tool that estimates compliance exposure, models decarbonization pathways, and compares the cost of retrofitting, buying renewable energy certificates, or paying the fine.

---

## Interactive tool

**Live app:** https://berdo-building-priority-screening-tool.streamlit.app

A Streamlit app with four tabs.

### Address Lookup

Enter a Boston address and get:

- **Two independent status flags** — Data Status and BERDO Status (see below)
- **A compliance gap estimate** across all six BERDO periods (2025–29 through 2050+), showing how far the building sits from its sector limit and what the Alternative Compliance Payment would cost annually and cumulatively
- **A year-over-year trend view** tracking GHG intensity and Site EUI across available reporting years, with delta metrics and a dual-axis chart
- **A grid decarbonization scenario** projecting how a cleaner ISO New England grid moves the building's compliance position through 2050
- **A fuel breakdown** inferring the building's primary heating fuel from reported usage

### Owner Portfolio

Enter a property owner name to group their buildings under BERDO's Building Portfolio pathway. Calculates the area-weighted **blended emissions standard**, shows which buildings run a surplus and which a deficit, flags possible vacancies (which disqualify a portfolio application), and lists every excluded building with the reason it was excluded.

### Retrofit & Incentives

Condition-adjusted retrofit cost ranges across eight scopes, with a Boston labor multiplier applied to national RSMeans baselines. Matches the project against eight federal, state, and utility incentive programs, ranks them by estimated value, and sequences them in the order they must be claimed — utility rebates reduce your 179D basis, so order matters.

Then compares **three paths** to closing a gap:

1. Retrofit the building
2. Retire MA Class I RECs to offset electricity emissions
3. Pay the Alternative Compliance Payment

The REC comparison reports a break-even price: RECs beat the ACP below **$58.27/REC** at the 2025 grid factor, falling to **$35.10 by 2050** as the grid cleans up and each REC avoids less CO₂e. RECs offset electricity emissions only — any fossil-fuel residual still pays ACP.

### Emissions Planner

Model planned emission reduction projects — fuel type, quantity, and implementation year — and see their effect on compliance and cumulative ACP exposure across every period through 2050. Compares four scenarios: baseline, with projects, grid decarbonization alone, and combined.

### Who it's for

City sustainability staff, outreach coordinators, community organizations, and retrofit planners triaging a large portfolio with limited resources — and building owners who want to understand their exposure, estimate fine risk, and evaluate whether grouping buildings into a portfolio reduces their obligations.

This is a screening tool, not an official City of Boston compliance determination.

### Why it exists

The City's official BERDO Emissions Calculator projects compliance for a single building given specific retrofit interventions. It is a depth tool. This is a breadth tool, built to answer a different question: *which buildings should we focus on first, and how do portfolio grouping, grid decarbonization, and REC purchases change the picture?*

No publicly available City tool currently provides multi-year trend analysis, blended portfolio standards, incentive stacking, or a three-way cost comparison across the full BERDO portfolio.

---

## How buildings are evaluated

Each building receives **two independent flags** rather than one blended score, because a building that didn't report needs a different intervention than one that reported and is over its limit — outreach versus retrofit capital.

**Data Status** — whether data was submitted, and whether property type, floor area, and GHG intensity are present and mappable to a BERDO category.

| Value | Meaning |
|---|---|
| Reported | Complete enough to evaluate |
| Incomplete data | Submitted, but a required field is missing or unmappable |
| Not submitted | No data reported; accruing daily reporting fines |

**BERDO Status** — the building's actual GHG intensity against *its own sector limit*, not a dataset average, so an energy-intensive hospital isn't penalized for using more energy than a warehouse.

| Value | Meaning |
|---|---|
| Over 2025–29 limit | Currently exceeds its limit and accruing ACP |
| Fails 2030–34 | Compliant now, over the next limit at current emissions |
| Compliant through 2034 / 2039+ | How far the current trajectory holds |
| Not yet covered | Smaller covered building, no limit until 2030 |
| Unknown — data incomplete | Cannot be determined from what was reported |

> **Note on an earlier version.** This project originally used a point-based priority score (Low / Moderate / High) that summed indicators like non-submission, missing property type, and above-median Site EUI. It was removed. Collapsing "didn't report" and "high energy use" into one number obscured that they call for entirely different responses, and Site EUI is not the metric BERDO compliance is actually assessed on.

---

## Methodology

### Compliance gap

Each building's reported GHG intensity (kg CO₂e/sq ft/yr) is compared against BERDO 2.0 limits for its property type, covering all **13 large property type categories** from the Boston APCC Phase 1 Regulations. A mapping layer translates Energy Star Portfolio Manager property type names to BERDO categories. Buildings over their limit receive an estimated ACP at **$234 per excess metric ton CO₂e**.

### Electricity emissions

Electricity is calculated using the City's published formula from Appendix A of the BERDO Emissions Factors List:

```
Electric Grid Emissions = Electricity consumed × (100% − RPS Class I) × Projected Grid Emissions Factor
```

Both terms are implemented against primary source: the 29-year Appendix B projected grid factor schedule and the Appendix C RPS Class I minimum requirement schedule, verified against the City's May 5, 2026 publication.

**The RPS Class I term is frequently omitted in secondary summaries of BERDO.** Including it matters: the Massachusetts RPS Class I minimum rises from 27% in 2025 to 60% by 2050, which stacks a second decarbonization curve on top of the declining grid factor. Omitting it overstates projected 2050 electricity-attributed emissions by roughly 80% — and correspondingly overstates long-run fine exposure.

Fossil fuel and district energy factors come from the same document's 2025 emissions factors table. District steam is published per operator, ranging from 0 kg/mmBtu (Vicinity e-steam) to 66.4 (default), so a single default is a known simplification.

### Retrofit costs and incentives

Cost ranges are order-of-magnitude benchmarks from RSMeans, ASHRAE, and DOE BTO, adjusted by a 1.25× Boston labor multiplier (RSMeans City Cost Index) and narrowed by whether an ASHRAE Level 2 audit has been completed.

Incentive estimates are $/sq ft proxies. Tax **deductions** are shown at after-tax cash value rather than face value — IRA 179D at $5.81/sq ft is worth roughly $1.22/sq ft to a taxpayer at the 21% corporate rate, and treating it as cash overstates available funding roughly fourfold. Programs terminated by the One Big Beautiful Bill Act (P.L. 119-21) for work beginning after June 30, 2026 — IRA 179D and 45L — are flagged and excluded from totals.

### Key deadlines encoded

- **August 15, 2026** — extended 2026 reporting deadline
- **September 1, 2026** — Building Portfolio application deadline
- **October 31, 2026** — MA Class I REC purchase deadline for 2025 compliance, via the City's REC Connector Program

---

## Key takeaway

BERDO compliance is not only an energy performance challenge. It is also a data visibility, reporting capacity, and ownership coordination issue. The buildings most in need of support are not limited to those with high Site EUI — they include buildings missing basic reporting information, especially property type and energy use data. Treating missing data as an early warning signal, rather than a data quality problem, is what distinguishes a triage tool from a compliance tracker.

---

## Key findings

- **3,569 buildings** are listed as in compliance in the 2025 reporting dataset
- **223 buildings** remain in pending revisions; **116** are under the State Pathway
- **Multifamily housing** is the largest category, with more than 2,000 buildings
- Buildings with high Site EUI need deeper performance review; buildings with missing data need reporting support, these are distinct intervention types
- Natural gas usage appears across many submitted records, suggesting electrification potential
- Preliminary location patterns suggest some neighborhoods have higher concentrations of non-submitted buildings, pointing to reporting gaps that may reflect capacity barriers rather than indifference

---

## Dataset

**Source:** City of Boston BERDO Public Reporting Data — 2025 Reported Energy and Water Metrics

```
data/2025-reported-energy-and-water-metrics.xlsx
```

The multi-year trend view draws on five normalized CSVs covering 2021–2025, standardized from the City's annual public releases. Each year required custom column mapping and unit handling — notably, 2021 GHG emissions were published in MTCO₂e and converted to kgCO₂e, and 2022 did not include a GHG emissions column.

**Emissions factors:** BERDO Emissions Factors List (City of Boston, last updated May 5, 2026), Appendices A–E.

**Key variables:** Compliance status · Property type · Site EUI · Total site energy use · GHG emissions · Gross floor area · Per-fuel usage · Building location · Inferred ownership category

---

## Methods

Analysis conducted in Python.

**Data preparation:** standardized column names across five reporting years, consolidated compliance labels, normalized per-fuel usage columns, separated complete performance records from missing-data analysis.

**Analysis:** compliance distribution, property type frequency, average EUI by compliance status, correlation between building size and energy intensity, missing data pattern analysis, and per-building compliance gap projection across all six BERDO periods.

---

## Tools

Python · pandas · NumPy · matplotlib · Streamlit · Plotly · openpyxl · Jupyter

---

## Setup

### Analysis notebook

```bash
git clone https://github.com/ryankellyongh/BERDO-Analysis.git
cd BERDO-Analysis
pip install -r requirements.txt
```

Download the 2025 dataset from the City of Boston BERDO Public Reporting Data and save it to `data/2025-reported-energy-and-water-metrics.xlsx`, then:

```bash
jupyter notebook "analysis/BERDO Analysis.ipynb"
```

Run all cells top to bottom.

### Screening tool

```bash
pip install -r requirements.txt
streamlit run app.py
```

Enter any Boston address — for example, `20 Gillette Park` — to see the building's compliance status, gap analysis, and ACP exposure.

---

## Limitations

- Screening and prioritization only; not an official City of Boston compliance determination
- Grid decarbonization scenarios use the City's *projected* factors, which are reviewed at least every five years and subject to change
- Incentive amounts are benchmarks and change annually; IRA stacking rules are complex and warrant a tax advisor
- The electricity share of a building's emissions is currently user-supplied rather than derived from reported fuel data
- District steam uses a single default factor; BERDO publishes per-operator values

---

## Author

**Ryan Kelly**
Data Analytics, Northeastern University

Focused on sustainability analytics, building performance, and using data to support climate policy and operational decision-making.

[GitHub](https://github.com/ryankellyongh) · [LinkedIn](https://linkedin.com/in/ryankelly10)
