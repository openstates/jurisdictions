# Data Model Relationship Map

## High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     JURISDICTIONS ECOSYSTEM                          │
└─────────────────────────────────────────────────────────────────────┘

                    OCDidParsed
                        │
                        │ (represents)
                        │
        ┌───────────────┴───────────────┐
        │                               │
        ▼                               ▼
    Division ◄──────────────────────► Jurisdiction
        │                               │
        │ (references)                  │ (references)
        │                               │
        ├─► GovernmentIdentifiers      ├─► JurisdictionMetadata
        │                               │
        ├─► Geometry[]                  ├─► SourceObj[]
        │                               │
        ├─► SourceObj[]                 ├─► SessionDetail[]
        │                               │
        └─► DivisionMetadata            ├─► TermDetail
                                        │
                                        └─► ClassificationEnum
```

---

## Detailed Model Relationships

### 1. **OCDidParsed** (Foundation)
```
OCDidParsed
├── country: str = "us"
├── state: Optional[str]
├── county: Optional[str]
├── place: Optional[str]
├── subdivision: Optional[str]
└── raw_ocdid: str (primary input)

PURPOSE:
  ▪ Parses OCD ID strings into structured components
  ▪ Used for matching and validating OCD identifiers
  ▪ Bridges between raw OCD IDs and structured models
```

---

### 2. **Division** ⟷ **Jurisdiction** (Symbiotic Relationship)

```
Division                                  Jurisdiction
├── id: UUID5                             ├── id: UUID5
├── ocdid: str ◄────────────────────────► ├── ocdid: str
│   (e.g., ocd-division/us/ca/...) │      │   (e.g., ocd-jurisdiction/...)
├── country: str                          ├── name: str
├── display_name: str                     ├── url: str
├── jurisdiction_id: str ─────────────┐   ├── classification: ClassificationEnum
│                                      └──► │ (GOVERNMENT, LEGISLATURE, etc.)
└── [SHARED FIELDS BELOW]                 │
                                          └── [SHARED FIELDS BELOW]

SHARED FIELDS:
├── accurate_asof: datetime
├── last_updated: datetime
├── sourcing: SourceObj[]
└── metadata: Optional[Metadata]

KEY RELATIONSHIP:
  Division.jurisdiction_id ──► Jurisdiction.ocdid
  (Each Division must reference a Jurisdiction)
```

---

### 3. **Division-Specific Fields**

```
Division
├── geometries: Geometry[] ◄─────────── Boundary Data
│   │
│   └── Geometry (historical tracking)
│       ├── start: datetime (boundary effective date)
│       ├── end: Optional[datetime] (boundary replaced date)
│       ├── boundary: Boundary
│       │   ├── centroid: Optional[Centroid]
│       │   │   ├── geo_type: "Point"
│       │   │   └── coordinates: [lon, lat]
│       │   └── extent: Optional[Extent]
│       │       └── extent: [left, lower, right, upper]
│       ├── children: List[str] (child division IDs)
│       └── arcGIS_address: str (GIS query URL)
│
├── also_known_as: List[str]
│   └── Alternate OCD ID formats
│
├── government_identifiers: GovernmentIdentifiers
│   ├── namelsad: str (Census legal name)
│   ├── statefp: str (State FIPS code)
│   ├── sldust: List[str] (State Senate districts)
│   ├── sldlst: List[str] (State House districts)
│   ├── countyfp: List[str] (County FIPS codes)
│   ├── county_names: List[str]
│   ├── cousubfp: Optional[str] (County subdivision)
│   ├── placefp: Optional[str] (Place FIPS code)
│   ├── lsad: str (Legal/Statistical Area Description)
│   ├── geoid: str (Combined FIPS code)
│   ├── geoid_12: Optional[str] (2010 vintage)
│   ├── geoid_14: Optional[str] (2014 vintage)
│   └── common_name: Optional[List[str]] (Alternative names)
│
└── metadata: DivisionMetadata
    └── population: Optional[Population]
        └── population: int
```

---

### 4. **Jurisdiction-Specific Fields**

```
Jurisdiction
├── classification: ClassificationEnum
│   ├── GOVERNMENT (city council)
│   ├── LEGISLATURE (state legislature)
│   ├── SCHOOL_SYSTEM (school board)
│   ├── EXECUTIVE (mayor)
│   ├── TRANSIT_AUTHORITY (port authority)
│   ├── JUDICIAL
│   ├── PROSECUTORIAL
│   ├── ADVISORY_BOARD
│   └── SPECIAL_PURPOSE_DISTRICT
│
├── metadata: JurisdictionMetadata
│   └── urls: URLObject[]
│       ├── url_type: URLEnum | str (PEOPLE, MEETINGS, or custom)
│       └── url: str
│
├── legislative_sessions: SessionDetail[]
│   ├── name: str (e.g., "2023-2024")
│   ├── identifiers: str (session ID)
│   ├── classification: str (primary, special)
│   ├── start_date: datetime
│   └── end_date: datetime
│
├── term: TermDetail
│   ├── duration: int (years)
│   ├── term_description: str (legal language)
│   ├── number_of_positions: int (elected seats)
│   ├── term_limits: Optional[str]
│   ├── source_url: str (.gov source)
│   └── last_known_term_end_date: Optional[datetime]
│
└── feature_flags: Dict (capabilities/features)
```

---

### 5. **Shared Metadata & Sourcing**

```
Both Division and Jurisdiction share:

├── SourceObj[]
│   └── Data provenance tracking
│       ├── field: List[str] (which fields this source applies to)
│       ├── source_name: str (e.g., "Census Bureau")
│       ├── source_type: SourceType
│       │   ├── AI (ai_generated)
│       │   ├── HUMAN (human_researched)
│       │   └── SCRAPED (programmatically_generated)
│       ├── source_url: Dict[str, URL] (source location)
│       └── source_description: str (how it was sourced)
│
└── Timestamp Fields (data lifecycle)
    ├── accurate_asof: datetime (when known to be accurate)
    ├── last_updated: datetime (last modification)
    ├── valid_asof: Optional[datetime] (when new data becomes active)
    └── valid_thru: Optional[datetime] (when data expires)
```

---

## Data Flow Relationships

```
┌──────────────────────────────────────────────────────────────┐
│               CREATION & GENERATION FLOW                      │
└──────────────────────────────────────────────────────────────┘

Raw OCD Data
    │
    ▼
OCDidParsed (parse & validate OCD ID)
    │
    ├─────────────────────────┬─────────────────────────┐
    │                         │                         │
    ▼                         ▼                         ▼
Create Division      Create Jurisdiction      Link Relationship
    │                     │                         │
    ├─ Parse OCDID        ├─ Parse OCDID           ├─ Division.jurisdiction_id
    ├─ Get Geometry       ├─ Get Classification     │   ↓ references
    ├─ Get Identifiers    ├─ Get Legislative Info  └─ Jurisdiction.ocdid
    ├─ Add SourceObj      ├─ Get Metadata URLs
    └─ Set Timestamps     ├─ Add SourceObj
                          └─ Set Timestamps

    ▼
Output to YAML
    │
    ├─ divisions/<state>/local/<name>.yaml
    └─ jurisdictions/<state>/local/<name>.yaml
```

---

## Cardinality & Multiplicity

```
Division ──1──────────────────┬─────────────∞── Geometry
                              │ (0 or more geometries per Division)
                              │ (tracks historical boundaries)

Division ──1──────────────────┬─────────────∞── SourceObj
                              │ (multiple sources per Division)

Jurisdiction ──1──────────────┬─────────────∞── SessionDetail
                              │ (multiple legislative sessions)

Jurisdiction ──1──────────────┬─────────────∞── URLObject
                              │ (multiple URLs per Jurisdiction)

Division ◄─junction_id─────1──1───ocdid► Jurisdiction
         │                            │
         └────────────────────────────┘
         (bidirectional reference)
```

---

## Key Relationships Summary

| Relationship | From | To | Type | Purpose |
|---|---|---|---|---|
| Defines Location | Division | Geometry[] | 1:Many | Historical boundary tracking |
| References | Division | Jurisdiction | 1:1 | Links geographic area to governing entity |
| Tracks Origin | Division/Jurisdiction | SourceObj[] | 1:Many | Data provenance & AI tracking |
| Classifies | Jurisdiction | ClassificationEnum | 1:1 | Categorizes jurisdiction type |
| Provides Contact | Jurisdiction | URLObject[] | 1:Many | Official online presence |
| Defines Terms | Jurisdiction | TermDetail | 1:1 | Electoral/governance rules |
| Logs Sessions | Jurisdiction | SessionDetail[] | 1:Many | Legislative calendar |

---

## Critical Linking Field

```
THE BINDING RELATIONSHIP:

Division.jurisdiction_id (string)
         │
         └──► References ──► Jurisdiction.ocdid (string)

Example:
  Division.jurisdiction_id = "ocd-jurisdiction/us/ca/place/06000/government"
  └─ Matches ──► Jurisdiction.ocdid = "ocd-jurisdiction/us/ca/place/06000/government"

This is the PRIMARY KEY for relating the two models.
```

---

## Validation Dependencies

```
When creating a Division, you MUST:
  ✓ Provide valid ocdid (parsed via OCDidParsed)
  ✓ Provide existing jurisdiction_id
  ✓ Ensure government_identifiers.geoid is populated
  ✓ Ensure sourcing explains data origin

When creating a Jurisdiction, you MUST:
  ✓ Provide valid ocdid (references division without "ocd-division/" prefix)
  ✓ Provide classification (must be in ClassificationEnum)
  ✓ Provide metadata.urls (cannot be empty)
  ✓ Provide sourcing explains data origin
  ✓ Match structure with related Division
```

