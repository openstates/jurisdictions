# Census Government Units 2025 Source Contract

## Purpose

This document records the verified source contract for the Census Bureau’s
2025 Government Units public-use archive used by #135 Task 4.1. It separates
what the source actually contains from downstream normalization and geography
resolution assumptions.

## Source Files

Official archive:

```text
https://www2.census.gov/programs-surveys/gus/datasets/2025/gov_units_2025.zip
```

Verified uploaded archive SHA-256:

```text
e8b17c3928fb95fa7355a1ce7795fc7de8874c64e9ac7cd9506d6a6515d953f8
```

The archive contains exactly:

| Member | Size | SHA-256 |
| --- | ---: | --- |
| `Govt_Units_2025_Final.xlsx` | 10,736,081 bytes | `840e8b65e5e65325c0a42fb842ea81c0491eae3abd8a41953764044ee9e2a56e` |
| `Government_Units_List_Documentation_2025.pdf` | 140,249 bytes | `d12278a7382943cc12ad501631374bc5c8688ba66292b61b0fe7eff9f4191f6d` |

The documentation describes the workbook as a snapshot of the Census Bureau
Governments Master Address File retrieved August 28, 2025, covering independent
government units, dependent school systems, and public pension systems active
or dormant as of the fiscal year ending June 30, 2025.

## Workbook Inventory

| Worksheet | Excel dimension | Data rows | Columns |
| --- | --- | ---: | ---: |
| `General Purpose` | `A1:S38705` | 38,704 | 19 |
| `Special District` | `A1:P40200` | 40,199 | 16 |
| `School District` | `A1:R12536` | 12,535 | 18 |
| `DEP School Dist` | `A1:T1319` | 1,318 | 20 |
| `Public Pension Sys` | `A1:R4486` | 4,485 | 18 |
| **Total** |  | **97,241** |  |

The PDF calls the final tab “Public Pensions Sys”; the workbook’s actual tab
name is `Public Pension Sys`. Code must follow the workbook value.

## Exact Headers

### General Purpose

```text
CENSUS_ID_PID6
UNIT_NAME
UNIT_TYPE
TITLE
ADDRESS1
ADDRESS2
CITY
STATE
ZIP
ZIP4
WEB_ADDRESS
POLITICAL_CODE_DESCRIPTION
POPULATION
POPULATION_SOURCE_YEAR
FIPS_STATE
FIPS_COUNTY
FIPS_PLACE
COUNTY_AREA_NAME
ACTIVE
```

### Special District

```text
CENSUS_ID_PID6
UNIT_NAME
UNIT_TYPE
FUNCTION_NAME
TITLE
ADDRESS1
ADDRESS2
CITY
STATE
ZIP
ZIP4
WEB_ADDRESS
FIPS_STATE
FIPS_COUNTY
COUNTY_AREA_NAME
ACTIVE
```

### School District

```text
CENSUS_ID_PID6
UNIT_NAME
UNIT_TYPE
TITLE
ADDRESS1
ADDRESS2
CITY
STATE
ZIP
ZIP4
WEB_ADDRESS
SCHOOL_ENROLLMENT
ENROLLMENT_YEAR
SCHOOL_LEVEL_DESCRIPTION
FIPS_STATE
FIPS_COUNTY
COUNTY_AREA_NAME
ACTIVE
```

### DEP School Dist

Uses the School District columns plus:

```text
PARENT_CENSUS_ID_PID6
PARENT_UNIT_NAME
```

### Public Pension Sys

```text
CENSUS_ID_PID6
UNIT_NAME
UNIT_TYPE
ACTIVITY_NAME
TITLE
ADDRESS1
ADDRESS2
CITY
STATE
ZIP
ZIP4
WEB_ADDRESS
FIPS_STATE
FIPS_COUNTY
COUNTY_AREA_NAME
ACTIVE
PARENT_CENSUS_ID_PID6
PARENT_UNIT_NAME
```

## Observed 2025 Counts

### General Purpose

- 38,620 `ACTIVE=Y`; 84 `ACTIVE=N`.
- 19,489 municipal governments.
- 16,184 township governments.
- 3,031 county governments.
- Population is populated on all rows.
- 22,513 website values are blank.

### Special District

- 39,854 `ACTIVE=Y`; 345 `ACTIVE=N`.
- All rows use the special-district unit type.
- 38 distinct Census function classifications.
- 28,450 website values are blank.

### School District

- 12,535 `ACTIVE=Y`; no dormant rows in this release.
- All rows use the school-district/educational-agency unit type.
- Enrollment is populated on all rows and uses enrollment year 2023.
- Six school-level classifications.
- 809 website values are blank.

### DEP School Dist

- 1,318 `ACTIVE=Y`.
- Parent classifications: 570 county, 479 township, 225 municipal, 44 state.
- All parent PID fields are populated.
- 44 state-dependent rows reference state-government PIDs that are not present
  as rows in this workbook.

### Public Pension Sys

- 4,483 `ACTIVE=Y`; 2 `ACTIVE=N`.
- All rows are defined-benefit public employee retirement systems.
- All parent PID fields are populated.
- Parent references resolve to 3,849 General Purpose rows, 303 Special District
  rows, and 19 School District rows.
- 314 parent references do not resolve inside this workbook: 313 are
  state-government parents and one is a municipal parent reference.

## Identifier Findings

- All 97,241 `CENSUS_ID_PID6` values are populated.
- Every PID is exactly six digits.
- Every PID is globally unique across all five worksheets.
- Every parent PID is exactly six digits.
- `FIPS_STATE` is populated with two digits on all rows.
- `FIPS_COUNTY` is three digits where present; it is blank on state-dependent
  school and pension rows.
- `FIPS_PLACE` is five digits on every General Purpose row, including 99xxx
  values on county governments.

## Source Semantics

The documentation defines:

- `CENSUS_ID_PID6` as the Census Bureau internal unit identifier.
- `PARENT_CENSUS_ID_PID6` as the parent-government identifier for dependent
  school systems and public pension systems.
- `ACTIVE=N` as dormant, not disincorporated. Dormant units remain counted in
  the Census government inventory.
- `COUNTY_AREA_NAME` as the county most served or the headquarters county when
  a government crosses county boundaries.
- websites as primarily self-reported with limited quality control.
- population as applicable only to general purpose governments.
- enrollment as applicable only to school districts.
- public pension systems as defined-benefit plans only.

## Data-Quality Observations

The source adapter must preserve published values rather than reject or repair
them:

- 23 ZIP values contain four digits rather than five.
- 33 nonblank ZIP4 values contain one or three digits rather than four.
- Some dormant special-district rows have blank contact-address fields.
- Website values may be missing, stale, malformed, or lack a URL scheme.
- Parent references can legitimately point outside this workbook.

These are source facts for downstream review. They are not reasons to drop the
row at the acquisition layer.

## Resolver Boundaries

This file is an authoritative government-unit inventory, but it is not a
complete government-to-geography crosswalk.

- `FIPS_STATE` and `FIPS_COUNTY` provide administrative context.
- `FIPS_PLACE` is available only on General Purpose rows and is not uniformly
  an incorporated-place geography identifier.
- Special districts and school districts do not expose direct TIGER district
  GEOIDs in this workbook.
- County-area values can represent headquarters or the county most served,
  rather than the full service area.

Therefore:

```text
Task 4.1: preserve and verify source rows
Phase 5: normalize and classify governments
Phase 6: resolve supported governments to TIGER geography
Later: produce PID-to-Division relationships and explicit unresolved outcomes
```

The source adapter must not fabricate GEOIDs, infer one-to-one geography, or
silently convert county context into jurisdiction boundaries.
