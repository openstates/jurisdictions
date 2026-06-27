# Jurisdictions FAQ

## Why does the OpenStates/Jurisdictions project exist?

Traditionally, when civic tech developers begin building an application to support local civic engagement, they run into a wall: accurate, comprehensive local data about U.S. counties, municipalities, schoools, and special districts is complex, time-consuming to collect and difficult to maintain. 

Across the United States, the same types of governing entities are described in different ways. Names overlap, structures vary, and datasets often blur the line between a place and the entity that governs it.

[Census](https://www.census.gov/data/developers/data-sets.html) data is complete, but requires domain expertise to navigate and lacks local references, such as links to local government websites. 

[Open Civic Data division identifiers](https://github.com/opencivicdata/ocd-division-ids/tree/master/identifiers/country-us)  are simple, short, easy to use, and make gathering geographically-relevant data for individual users fast and reliable, but they lack identifiers that associate them with the Census data they represent and describe. 

We thought: What if we extended Open Civic Data Division identifiers to include metadata that describes the government identifiers from which they are sourced? That would allow application builders to easily gather the Census data, information from local government websites, and the geospatial data they need to build their applications—all from one source.  

That is what this project is all about. It focuses on building a comprehensive, accurate and human-verified jurisdiction layer to support application development and agentic use-cases. 

---

## Frequently Asked Questions

### How many government entities are there in the United States? 

Well, that's a good question. There are approximately 90,888 government entities in the United States. This video from [USA Facts](https://usafacts.org) provides the best breakdown and most accurate count we have seen so far. 

[https://usafacts.org/just-the-facts/who-pays-for-what/](https://usafacts.org/just-the-facts/who-pays-for-what/) 

Each of those entities can have jurisdiction over one or more geographic areas (Divisions). Within a county there are cities, towns, and townships. Within a city, there can be any number of wards and precincts. Congressional Districts overlap county and [places](#what-is-a-place) boundaries. Some cities are also considered counties. Counties can include unincorporated [places](#what-is-a-place). Things get complex fast. Read on... 

### What is a jurisdiction?

A **jurisdiction** is a governing entity with authority and legal power.

Examples include:

* a state government
* a county government
* a municipal government

It represents **governance**, not geography.

**See also:** [What is a division?](#what-is-a-division) | [What is the difference between a jurisdiction and a division?](#what-is-the-difference-between-a-jurisdiction-and-a-division)

---

### What is a division?

A **division** is a geographic area.

Examples include:

* a state boundary
* a county boundary
* a city boundary
* a [place](#what-is-a-place) boundary (census-designated area)

It represents **land**, not authority.

**See also:** [What is a jurisdiction?](#what-is-a-jurisdiction) | [What is the difference between a jurisdiction and a division?](#what-is-the-difference-between-a-jurisdiction-and-a-division)

---

### What is a place?

A **place** is a U.S. Census Bureau geographic classification for a populated locality.

From the [U.S. Census Bureau](https://www.census.gov/content/dam/Census/data/developers/understandingplace.pdf):
> Places are geographic entities used by the U.S. Census Bureau for data collection and tabulation. They represent concentrations of population, economic activity, or administrative centers.

**Types of places include:**
* **Incorporated cities** - Legally established municipalities with their own government
* **Census-designated places (CDPs)** - Unincorporated communities recognized by the Census Bureau
* **Towns** - In some states, legally incorporated towns
* **Villages** - In some states, smaller incorporated municipalities

**Important distinctions:**
* A **place** is a Census Bureau geographic unit (for statistics and data)
* A **division** in our system is the geographic boundary in the OCD system
* A **jurisdiction** is the government that manages that area

Many places are also jurisdictions (incorporated cities), but not all. Census-designated places (CDPs) are geographic areas without their own government—they don't have a corresponding jurisdiction.

**Example:**
- **Place:** "Los Angeles" (Census Bureau definition of the city's population center)
- **Division:** `ocd-division/country:us/state:ca/place:los_angeles` (the geographic boundary)
- **Jurisdiction:** `ocd-jurisdiction/country:us/state:ca/place:los_angeles/government` (the city government)

**See also:** 
- [U.S. Census Bureau - Understanding Place](https://www.census.gov/content/dam/Census/data/developers/understandingplace.pdf)
- [What is a division?](#what-is-a-division)
- [What is the difference between a jurisdiction and a division?](#what-is-the-difference-between-a-jurisdiction-and-a-division)

---

### What is the difference between a jurisdiction and a division?

* **Division** = where something is (geographic boundary)
* **Jurisdiction** = who governs it (governing entity)

They are related, but not interchangeable.

**Example:**
- **Division:** The geographic boundary of Los Angeles County
- **Jurisdiction:** The Los Angeles County Board of Supervisors (the entity that governs that area)

A jurisdiction governs one or more divisions. A division may be governed by multiple jurisdictions (overlapping authorities).

**For a detailed visual overview of these relationships,** see [docs/data_model_relationships.md](../docs/data_model_relationships.md).

**See also:** [README.md - Core Concepts](README.md#core-concepts)

---

### Why not just use geographic data?

Geography alone does not describe governance.

A map can show where something is, but it cannot tell you:

* who governs it
* how authority is structured
* what decisions are made there

**Divisions** provide the geographic layer. **Jurisdictions** provide the governance layer.

---

### Why not just use names?

Names are ambiguous.

The same name can refer to:

* a geographic area (division)
* a governing entity (jurisdiction)
* multiple different entities in different contexts

The system must distinguish between them explicitly.

**Example:** "Los Angeles" could refer to:
- The city boundary (division)
- The city government (jurisdiction)
- The county (different jurisdiction)
- A region (broader geographic area)

---

### Do jurisdictions always match geographic boundaries?

Often, but not always.

Examples where they diverge:

* **Overlapping authorities:** A city may span multiple counties
* **Multi-jurisdictional entities:** A regional authority governs parts of several counties
* **Special districts:** Fire districts, water districts, park districts have boundaries that don't match county or city lines

A jurisdiction may relate to multiple divisions, and a division may be governed by multiple jurisdictions.

---

### What types of jurisdictions are included?

This project focuses on core governing entities:

* **States** - State governments
* **Counties** - County governments
* **Municipalities** - City and town governments
* **Special Districts** - Fire, water, park, transit authorities
* **Other** - Legislative bodies, executive offices, judicial bodies

See also: [Classification Types](#what-classification-types-are-supported)

---

### What is not a jurisdiction?

A jurisdiction is not:

* a geographic area alone (that's a **division**)
* an office or individual person
* an election or voting precinct
* a dataset label or administrative category

It must represent a **governing entity with actual authority**.

---

### How are jurisdictions identified?

Jurisdictions use standardized identifiers where available.

The system uses:

* **OCDIDs** (Open Civic Data IDs) for divisions where available
* **OCDIDs with governance suffix** for jurisdictions (e.g., `/government` for municipal governments)
* **UUIDs** generated deterministically from the OCDID for data consistency

If an identifier is missing:

* do not invent identifiers
* flag the gap with clear documentation
* use human-readable names as temporary identifiers

---

### Can I create a new identifier?

No.

Inventing identifiers breaks consistency and interoperability.

---

### What if I am unsure something is a jurisdiction?

Ask:

* Does it govern?
* Does it have authority?
* Is it a recognized public body?

If unclear, open an issue.

---

### How precise does this need to be?

Very.

Small inconsistencies create large downstream issues.

---

### What sources should I use?

Prefer:

* official government sources
* authoritative documentation

Do not guess.

---

### Can I include offices, elections, or candidates?

No.

This project is jurisdiction-focused only.

---

### How should I structure my contribution?

* keep it small
* match existing patterns exactly
* ensure verifiability

---

### What is the most common mistake?

Confusing jurisdictions with divisions.

---

### What should I check before submitting?

* Is this a governing entity?
* Are identifiers valid?
* Does it match existing structure?
* Is it verified?

---

## OCDID vs Jurisdiction Model

### OCDID (Geography)

```
ocd-division/country:us/state:tx/county:travis
```

Represents a geographic area.

---

### Jurisdiction (Governance)

```
name: Travis County government
type: county
division_ref: ocd-division/country:us/state:tx/county:travis
```

Represents the governing entity.

---

### Key Difference

| Concept    | OCD Model | This Project |
| ---------- | --------- | ------------ |
| Geography  | OCDID     | Division     |
| Governance | Implicit  | Jurisdiction |
| Separation | Combined  | Explicit     |

---

### Rule

Do not replace OCDIDs.

Use them for divisions and link jurisdictions to them.

---

## Python Development FAQ

### What language is used?

Python.

---

### Do I need Python to contribute?

No.

* Data contributors: no code required
* Engineering contributors: Python

---

### Where should I start?

* Review data models
* Understand jurisdiction vs division
* Pick an issue

---

### What is the key concept?

Separation of:

* geography (division)
* governance (jurisdiction)

---

### What work is needed?

* validation
* pipelines
* relationship modeling
* testing

---

### Should I change the data model?

No.

Open an issue first.

---

### How important are tests?

Critical.

They enforce consistency and prevent regressions.

---

### Common dev mistake?

Confusing division and jurisdiction in logic.

---

### What if unclear?

Ask before implementing.

---

## Good vs Bad Pull Requests

### Example 1: Division vs Jurisdiction

❌ Bad:
Treats a place as a governing entity

✅ Good:
Models the governing body and links to geography

---

### Example 2: Identifiers

❌ Bad:
Invents IDs

✅ Good:
Uses standards or flags gaps

---

### Example 3: Consistency

❌ Bad:
Introduces new patterns

✅ Good:
Matches existing records exactly

---

### Example 4: Scope

❌ Bad:
Adds elections or offices

✅ Good:
Keeps jurisdiction layer clean

---

### Example 5: Verification

❌ Bad:
Assumes structure

✅ Good:
Uses real sources

---

## What a Strong PR Looks Like

A strong PR:

* models a real governing entity
* follows existing patterns
* uses valid identifiers
* stays within schema
* is small and reviewable
* is verifiable
