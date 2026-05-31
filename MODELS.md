# Data Models Guide

This document describes the core data models used in the OpenStates Jurisdictions project.

## Quick Reference

| Model | Purpose | Represents | File Location |
|-------|---------|-----------|--|
| **Division** | Geographic area | Where something is | `src/models/division.py` |
| **Jurisdiction** | Governing entity | Who governs it | `src/models/jurisdiction.py` |
| **OCDidParsed** | OCD ID breakdown | Standardized identifier | `src/models/ocdid.py` |
| **SourceObj** | Data provenance | Where data came from | `src/models/source.py` |

---

## Division Model

**Purpose:** Represents a geographic area (a piece of land with defined boundaries).

**Related Concepts:**
- [FAQ: What is a division?](FAQ.md#what-is-a-division)
- [FAQ: Division vs Jurisdiction](FAQ.md#what-is-the-difference-between-a-jurisdiction-and-a-division)

### Key Fields

```python
class Division(BaseModel):
    id: UUID | None              # UUID5 derived from ocdid
    ocdid: OCDIdStr              # Open Civic Data identifier
    name: str                    # Geographic name (e.g., "Los Angeles County")
    geometry: GeoJSON | None     # Geographic boundaries (GeoJSON)
    population: int | None       # Latest known population
    area_km2: float | None       # Size in square kilometers
    centroid: Centroid | None    # Center point of the area
    sources: list[SourceObj]     # Data provenance
```

### OCDID Format

Divisions use OCD IDs with the `ocd-division/` prefix:

```
ocd-division/country:us/state:ca/county:los_angeles
ocd-division/country:us/state:wa/place:seattle
```

**See also:** [OCDidParsed Model](#ocdidparsed-model)

**What is a "place"?** A place is a U.S. Census Bureau geographic classification. See [FAQ: What is a place?](FAQ.md#what-is-a-place) or the [Census Bureau documentation](https://www.census.gov/content/dam/Census/data/developers/understandingplace.pdf).

### Examples

**State Division:**
```yaml
id: "12345678-1234-5678-1234-567812345678"
ocdid: "ocd-division/country:us/state:ca"
name: "California"
geometry: {...GeoJSON...}
```

**County Division:**
```yaml
id: "87654321-4321-8765-4321-876543218765"
ocdid: "ocd-division/country:us/state:ca/county:los_angeles"
name: "Los Angeles County"
population: 10014000
area_km2: 12561.3
```

---

## Jurisdiction Model

**Purpose:** Represents a governing entity with authority over a defined scope.

**Related Concepts:**
- [FAQ: What is a jurisdiction?](FAQ.md#what-is-a-jurisdiction)
- [FAQ: Division vs Jurisdiction](FAQ.md#what-is-the-difference-between-a-jurisdiction-and-a-division)

### Key Fields

```python
class Jurisdiction(BaseModel):
    id: UUID | None                  # UUID5 derived from ocdid
    ocdid: OCDIdStr                  # Open Civic Data identifier (with /government suffix)
    name: str                        # Official name (e.g., "Los Angeles County Board of Supervisors")
    classification: ClassificationEnum  # Type of governing entity
    url: str | None                  # Official website
    metadata: dict                   # Additional attributes
    sources: list[SourceObj]         # Data provenance
    last_updated: datetime           # When this record was last verified/updated
```

### Classification Types

Valid classification types for jurisdictions:

```python
class ClassificationEnum(StrEnum):
    GOVERNMENT = "government"           # City council, board of supervisors, etc.
    LEGISLATURE = "legislature"         # State legislature, bicameral bodies
    SCHOOL_SYSTEM = "school_system"    # School district boards
    EXECUTIVE = "executive"             # Mayor, governor, county executive
    TRANSIT_AUTHORITY = "transit_authority"  # Regional transit authorities
    JUDICIAL = "judicial"               # Courts, judicial bodies
    PROSECUTORIAL = "prosecutorial"     # District attorneys, prosecutors
    ADVISORY_BOARD = "advisory_board"   # Advisory bodies with limited authority
    SPECIAL_PURPOSE_DISTRICT = "special_purpose_district"  # Fire, water, park districts
```

### OCDID Format

Jurisdictions use OCD IDs with the `ocd-jurisdiction/` prefix and governance type suffix:

```
ocd-jurisdiction/country:us/state:ca/government
ocd-jurisdiction/country:us/state:ca/county:los_angeles/government
ocd-jurisdiction/country:us/state:ca/county:los_angeles/place:los_angeles/government
```

**See also:** [OCDidParsed Model](#ocdidparsed-model)

### Examples

**State Government Jurisdiction:**
```yaml
id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
ocdid: "ocd-jurisdiction/country:us/state:ca/government"
name: "State of California"
classification: "government"
url: "https://www.ca.gov"
```

**County Government Jurisdiction:**
```yaml
id: "bbbbbbbb-cccc-dddd-eeee-aaaaaaaaaaaa"
ocdid: "ocd-jurisdiction/country:us/state:ca/county:los_angeles/government"
name: "Los Angeles County Board of Supervisors"
classification: "government"
url: "https://bos.lacounty.gov"
```

**City Council Jurisdiction:**
```yaml
id: "cccccccc-dddd-eeee-aaaa-bbbbbbbbbbbb"
ocdid: "ocd-jurisdiction/country:us/state:ca/county:los_angeles/place:los_angeles/government"
name: "Los Angeles City Council"
classification: "government"
url: "https://www.lacity.gov"
```

---

## OCDidParsed Model

**Purpose:** Breaks down an Open Civic Data identifier into its component parts.

**Related Documentation:**
- [Open Civic Data Project](https://opencivicdata.org/)
- [OCD ID Documentation](docs/ocdid_matching_criteria.md)

### Key Fields

```python
class OCDidParsed(BaseModel):
    type: OCDidType                    # "ocd-division" or "ocd-jurisdiction"
    country: str                       # Country code (usually "us")
    state: str | None                 # State abbreviation (e.g., "ca", "wa")
    county: str | None                # County name/code
    place: str | None                 # Place name/code (census place, incorporated city, town, or village)
    subdivision: str | None           # Other geographic subdivision
    raw_ocdid: str                    # Original OCDID string
```

**About "place":** The `place` field contains the U.S. Census Bureau classification for a populated locality. This can be:
- An incorporated city (e.g., "Los Angeles", "Seattle")
- A census-designated place (CDP) - an unincorporated community
- A town (in states that use this classification)
- A village (in states that use this classification)

**For detailed information, see:**
- [FAQ: What is a place?](FAQ.md#what-is-a-place)
- [U.S. Census Bureau - Understanding Place](https://www.census.gov/content/dam/Census/data/developers/understandingplace.pdf)

### Validation

The model automatically:
- Validates that `raw_ocdid` starts with `ocd-division/` or `ocd-jurisdiction/`
- Parses the hierarchical structure
- Populates the `type` field from the raw OCDID
- Checks that explicit `type` matches the OCDID prefix

### Examples

**Division OCDID:**
```python
OCDidParsed(
    type="ocd-division",
    country="us",
    state="ca",
    county="los_angeles",
    raw_ocdid="ocd-division/country:us/state:ca/county:los_angeles"
)
```

**Jurisdiction OCDID:**
```python
OCDidParsed(
    type="ocd-jurisdiction",
    country="us",
    state="wa",
    place="seattle",
    raw_ocdid="ocd-jurisdiction/country:us/state:wa/place:seattle/government"
)
```

---

## SourceObj Model

**Purpose:** Documents the origin and reliability of data, enabling tracking of data provenance.

**Related Concepts:**
- Data quality tracking
- Attribution and citation
- Data verification status

### Key Fields

```python
class SourceObj(BaseModel):
    field: list[str]                   # Which fields this source applies to
    note: str | None                   # Additional context about the source
    url: str | FileUrl | FtpUrl        # Source URL (HTTP, file, or FTP)
    date_accessed: date | None         # When the source was accessed
```

### Types

```python
class SourceType(StrEnum):
    AI = "ai_generated"                # Generated/verified by AI system
    HUMAN = "human_researched"         # Researched and verified by human
    SCRAPED = "programmatically_generated"  # Automated scraping
```

### Examples

**Human-researched source:**
```yaml
field: ["name", "url"]
note: "Official government website, verified 2026-05-31"
url: "https://www.ca.gov"
date_accessed: "2026-05-31"
type: "human_researched"
```

**AI-generated source:**
```yaml
field: ["population", "area_km2"]
note: "Extracted from Census data by OpenStates AI pipeline"
url: "https://data.census.gov"
date_accessed: "2026-05-15"
type: "ai_generated"
```

---

## Relationships Between Models

```
Division (geographic area)
    ↓
    └─→ has an ocdid (OCDidParsed)
    └─→ has sources (SourceObj)
    └─→ has geometry (GeoJSON)

Jurisdiction (governing entity)
    ↓
    └─→ has an ocdid (OCDidParsed)
    └─→ has classification (ClassificationEnum)
    └─→ has sources (SourceObj)
    └─→ governs one or more divisions
```

### Key Relationship Rules

1. **One Division = One Geographic Area**
   - Has exactly one OCDID starting with `ocd-division/`
   - May be governed by multiple jurisdictions

2. **One Jurisdiction = One Governing Entity**
   - Has exactly one OCDID starting with `ocd-jurisdiction/`
   - Governs one or more divisions

3. **OCDID Hierarchy**
   - Division OCDIDs build hierarchy: `country → state → county → place → ...`
   - Jurisdiction OCDIDs match their governing scope + `/government` suffix

### Example: Los Angeles

**Division (Geographic Area):**
```
ocd-division/country:us/state:ca/county:los_angeles/place:los_angeles
```

**Jurisdiction (Governing Entity):**
```
ocd-jurisdiction/country:us/state:ca/county:los_angeles/place:los_angeles/government
```

---

## Geographic Terms Reference

### Place

A **place** is a U.S. Census Bureau geographic classification for a populated locality.

**Types of places:**
- **Incorporated cities** - Legally established municipalities with their own government (e.g., Los Angeles, Seattle)
- **Census-designated places (CDPs)** - Unincorporated communities recognized by the Census Bureau for statistical purposes
- **Towns** - In some states (especially New England), legally incorporated municipalities
- **Villages** - In some states, smaller incorporated municipalities

**In OCD IDs:**
- Appears as `place:<place_name>` in the hierarchy
- Example: `ocd-division/country:us/state:ca/place:los_angeles`

**Important note:** Not all places have governments (no corresponding jurisdiction). Census-designated places are geographic areas for statistical purposes, but they don't have their own jurisdiction. Incorporated cities, however, typically have both a division and a jurisdiction.

**For detailed information:**
- [FAQ: What is a place?](FAQ.md#what-is-a-place)
- [U.S. Census Bureau - Understanding Place](https://www.census.gov/content/dam/Census/data/developers/understandingplace.pdf)

### County

A county is a primary political subdivision within a state. 

**In OCD IDs:**
- Appears as `county:<county_name>` in the hierarchy
- Example: `ocd-division/country:us/state:ca/county:los_angeles`
- Counties are typically the second level in the geographic hierarchy (after state)

### State

A state is a primary political subdivision of the United States.

**In OCD IDs:**
- Appears as `state:<state_abbreviation>` in the hierarchy
- Example: `ocd-division/country:us/state:ca`
- Always the first level after country

### Hierarchy

OCD IDs follow a strict hierarchy from broadest to most specific:

```
country → state → county → place → [other subdivisions]
```

**Examples:**

State-level:
```
ocd-division/country:us/state:ca
```

County-level:
```
ocd-division/country:us/state:ca/county:los_angeles
```

Place-level (incorporated city):
```
ocd-division/country:us/state:ca/county:los_angeles/place:los_angeles
```

Place-level (unincorporated, CDP):
```
ocd-division/country:us/state:ca/county:kern/place:delano_shafter
```

---

## File Locations

| Model | File | Imports |
|-------|------|---------|
| Division | `src/models/division.py` | `from src.models.division import Division` |
| Jurisdiction | `src/models/jurisdiction.py` | `from src.models.jurisdiction import Jurisdiction` |
| OCDidParsed | `src/models/ocdid.py` | `from src.models.ocdid import OCDidParsed` |
| SourceObj | `src/models/source.py` | `from src.models.source import SourceObj, SourceType` |

---

## Further Reading

- [FAQ.md](FAQ.md) - Conceptual questions about divisions and jurisdictions
- [README.md](README.md) - Project overview and setup
- [docs/ocdid_matching_criteria.md](docs/ocdid_matching_criteria.md) - OCDID structure details
- [CONTRIBUTING.md](CONTRIBUTING.md) - How to contribute data or improvements
