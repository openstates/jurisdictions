---
id: source-snapshots
type: rework-guide
owner: rework
status: active
last_updated: 2026-09-18
tags: [rework, phase-4, sources, snapshots, provenance]
task: "Phase 4 — Tasks 4.1–4.4 (issue #135)"
scope: "How external source files are fetched once, verified, cached under data/raw/, described by a metadata sidecar, and turned into SourceObj provenance."
---

# Source Snapshots (Phase 4)

The pipeline reads bulk files from three providers: the Census Government
Units Survey, Census TIGER, and the Open Civic Data division-id repository.
Each file is downloaded once per provider release, verified, and cached
with a metadata sidecar. Everything after the download runs offline from
the cache, and the golden tests run from checked-in fixture snapshots that
use the same sidecar format. `src/sources/snapshot.py` is the shared base;
the per-provider adapters (`census_governments.py`, `census_tiger.py`,
`ocd_master.py`) build on it and own parsing.

This replaces the download half of `DownloadManager`, which fetched the OCD
CSVs into DuckDB tables on every run (`current_pipeline.md` §2, §4). The
DuckDB file is not part of this layer and nothing here reads or writes it.

## 1. Four concerns, kept apart

| Concern | Where | Notes |
| --- | --- | --- |
| Fetch | `AsyncDownloader` (`src/init_migration/downloader.py`) | Reused as-is: retries, backoff, HTML-body guard, GitHub decoding. `SnapshotStore.fetch` calls `fetch_bytes(url, force=True)` because a cache miss here means the bytes are needed whatever the server's validators say. |
| Verify | `verify_snapshot`, `SnapshotSpec.expected_sha256` | Size and SHA-256 must match the sidecar. A caller that already knows the checksum pins it on the spec; a mismatch raises before anything is written. |
| Cache | `SnapshotStore` | `<root>/<source>/<release>/<filename>` plus `<filename>.meta.json`. Default root `data/raw/`. Files are written to a `.tmp` name and renamed, so a partial download never sits at the final path. |
| Parse | adapters | `Snapshot.read_bytes()` / `read_text()`; the base never interprets content. |

Timestamps are always injected. `SnapshotStore.fetch` and `put` take
`retrieved_at` as a keyword argument, and both `SnapshotSpec` and
`SnapshotMetadata` reject naive datetimes. Nothing under `src/sources/`
calls `datetime.now()`, so identical inputs yield identical sidecars.

## 2. Layout

```text
data/
  raw/
    census_governments/
      2022/
        <file>               bulk download, ignored by git
        <file>.meta.json     sidecar, committed
    tiger/
      2025/
        ...
    ocd_master/
      <release>/
        country-us.csv
        country-us.csv.meta.json
  cache/                     derived intermediates (Parquet etc.), ignored
```

`<release>` is the provider's own label: a GUS survey year, a TIGER/Line
vintage, or for the OCD repository a git ref or commit. Different releases
are different directories and never overwrite one another.

Fixture snapshots under `tests/fixtures/<source>/` use the same pair, file
plus sidecar, without the release directory. `load_snapshot(path)` opens
either layout: it reads the sidecar next to the file and verifies the
checksum by default.

## 3. The metadata record

`SnapshotMetadata` is the sidecar, serialized as JSON with sorted keys and
ISO 8601 timestamps:

| Field | Meaning |
| --- | --- |
| `source` | Cache directory key: `census_governments`, `tiger`, `ocd_master`. |
| `source_name` | Provider name as it appears in `SourceObj.source_name`. |
| `dataset` | Product within the provider (`SourceObj.dataset`). |
| `release` | Provider release, vintage, or version (`SourceObj.release`). |
| `filename` | Bare file name; must equal the name of the file the sidecar sits beside. |
| `url` | Exact URL fetched. |
| `sha256` | Hex digest of the file as stored. |
| `size_bytes` | Byte length of the file as stored. |
| `retrieved_at` | When this pipeline fetched it. Injected. |
| `publication_date` | When the provider published the release, when known. Null otherwise. |

Example:

```json
{
  "dataset": "Government Units Survey",
  "filename": "gus_2022.csv",
  "publication_date": null,
  "release": "2022",
  "retrieved_at": "2026-09-18T12:00:00+00:00",
  "sha256": "…",
  "size_bytes": 12345,
  "source": "census_governments",
  "source_name": "U.S. Census Bureau",
  "url": "https://…"
}
```

## 4. From snapshot to `SourceObj`

`source_obj_from_snapshot(metadata, field=[...])` is the only place
provenance is assembled from a snapshot. It fills:

| `SourceObj` field | From |
| --- | --- |
| `source_name` | `metadata.source_name` |
| `source_url` | `metadata.url` |
| `dataset` | `metadata.dataset` |
| `release` | `metadata.release` |
| `publication_date` | `metadata.publication_date` |
| `retrieval_date` | `metadata.retrieved_at` |
| `field`, `source_type`, `source_description` | caller; `source_type` defaults to `programmatically_generated` |

`release`, `publication_date`, and `retrieval_date` describe the source and
the observation. They never describe real-world validity: a TIGER/Line 2025
boundary is `valid_from` 2025-01-01 because that is the series' as-of date,
and `valid_to` stays null while the boundary is active. Those two fields
live on `Geometry`, not on the source (design §21, instruction §20).

## 5. Fetch behaviour

`SnapshotStore.fetch(spec, downloader, retrieved_at=...)`:

1. If the file and sidecar exist and verify, return them without touching
   the network. The recorded `retrieved_at` is the original download's.
2. If the cached file fails verification, log a warning and download again.
3. `refresh=True` downloads regardless.
4. A download whose SHA-256 differs from `spec.expected_sha256` raises
   `SnapshotIntegrityError` and writes nothing.
5. An HTML body where data was expected raises from the downloader
   (`UnexpectedContentError`) and writes nothing.

Errors are `SnapshotIntegrityError` (bytes do not match) and
`SnapshotMetadataError` (sidecar missing or malformed), both under
`SnapshotError` in `src/errors.py`.

## 6. Git policy for `data/raw/` and `data/cache/`

Bulk source files are never committed (instruction §17). The sidecars are
small and are what make a run reproducible: they pin the URL, release, and
checksum that produced the output. `.gitignore` therefore ignores everything
under `data/raw/` except `*.meta.json`, and ignores `data/cache/` entirely:

```gitignore
data/raw/**
!data/raw/**/
!data/raw/**/*.meta.json
data/cache/
```

A fresh checkout with committed sidecars can re-fetch each file and verify
it against the recorded checksum; a changed upstream file fails
verification instead of silently changing output.

## 7. Adapters

### 7.1 Census government listings

The Census Bureau publishes two listings of the government universe from
its Governments Master Address File (GMAF), both under
`https://www2.census.gov/programs-surveys/gus/datasets/<year>/`:

| Listing | Years | File | Module | Cache key |
| --- | --- | --- | --- | --- |
| Census of Governments: Organization (benchmark) | ending in 2 and 7 | `govt_units_<year>.ZIP` | `src/sources/census_governments.py` | `census_governments` |
| Annual Government Units listing (GMAF snapshot) | other years, 2024 on | `gov_units_<year>.zip` | `src/sources/census_gus.py` | `census_gus` |

The benchmark is what the pipeline builds from every five years; the
annual listing updates it in between. The two modules are independent:
each has its own spec, fetch, and parse entry points and neither imports
the other, so a benchmark year can be re-run on its own. They share only
`src/sources/government_units.py`: the `CensusGovernmentRecord` type, the
row validator, and the workbook/CSV readers, driven by a per-listing
`Layout` (sheet names, skipped sheets, column aliases).

Each ZIP holds one Excel workbook with a sheet per government class. The
record keeps the sheet as `kind` and the sheet's own classification column
verbatim:

| Sheet | `kind` | Classification column |
| --- | --- | --- |
| General Purpose | `general_purpose` | `UNIT_TYPE` (`1 - COUNTY`, `2 - MUNICIPAL`, `3 - TOWNSHIP`) |
| Special District | `special_district` | `FUNCTION_NAME` |
| School District | `school_district` | `SCHOOL_LEVEL_DESCRIPTION` |
| DEP School Dist | `dependent_school_system` | `UNIT_TYPE` of the parent and `SCHOOL_LEVEL_DESCRIPTION` |
| Public Pension Sys (annual, 2025 on) | `public_pension_system` | `ACTIVITY_NAME`; a dependent retirement board, not a government. Exported to `data/cache/` as its own dataset for other consumers; the pipeline does not read it. |

Layout differences the annual module's aliases absorb: `ACTIVE` for
`IS_ACTIVE`, `POPULATION_SOURCE_YEAR` for `POPULATION_YEAR`,
`SCHOOL_ENROLLMENT` for `ENROLLMENT`; the annual listing drops the legacy
`CENSUS_ID_GIDID`, adds `POLITICAL_CODE_DESCRIPTION`, puts `UNIT_TYPE` on
every sheet, and from 2025 gives dependent units `PARENT_CENSUS_ID_PID6`
and `PARENT_UNIT_NAME`. Population and enrollment cells may carry
thousands separators; the validator strips them.

`CENSUS_ID_PID6`, `FIPS_STATE`, `FIPS_COUNTY`, `FIPS_PLACE` are strings
exactly as published. A row whose required cells fail validation (six-digit
id, non-empty name, two-letter state, two-digit state FIPS, `Y`/`N` active
flag, well-formed optional county/place/parent codes and integer counts)
becomes a `CensusRowError` naming the sheet, line, id and every problem;
the rest of the sheet still loads. Columns the record does not name stay
in `attributes`.

Reading `.xlsx` needs `openpyxl`, added as a project dependency for these
adapters. The ZIPs are about 11 MB, so fixtures are CSV excerpts of each
sheet with the upstream header
(`tests/fixtures/census_governments/govt_units_2022_<sheet>.csv`,
`tests/fixtures/census_gus/gov_units_<year>_<sheet>.csv`), parsed by the
same validator through each module's `parse_sheet_snapshot`. Each
excerpt's sidecar records the ZIP's URL, the year as `release`, the ZIP's
`Last-Modified` as `publication_date`, and the checksum of the excerpt
itself.

### 7.2 Census TIGER (`src/sources/census_tiger.py`, `config/tiger_layers.yaml`)

TIGER supplies Division geography: the GEOID, the geography class, and the
boundary reference. The configuration file lists, per layer, the TIGER/Line
shapefile that carries the attribute table and the TIGERweb MapServer layer
that serves the boundary as GeoJSON:

| Layer key | Geography | TIGER/Line file | TIGERweb service / layer | GEOID digits |
| --- | --- | --- | --- | --- |
| `state` | state | `STATE/tl_<year>_us_state.zip` | `State_County` / 0 | 2 |
| `county` | county | `COUNTY/tl_<year>_us_county.zip` | `State_County` / 1 | 5 |
| `place` | place | `PLACE/tl_<year>_<state>_place.zip` | `Places_CouSub_ConCity_SubMCD` / 4 | 7 |
| `census_designated_place` | place | same PLACE file (CLASSFP U1/U2, LSAD 57) | `Places_CouSub_ConCity_SubMCD` / 5 | 7 |
| `county_subdivision` | county_subdivision | `COUSUB/tl_<year>_<state>_cousub.zip` | `Places_CouSub_ConCity_SubMCD` / 1 | 10 |
| `school_district_unified` | school_district | `UNSD/tl_<year>_<state>_unsd.zip` | `School` / 0 | 7 |
| `school_district_secondary` | school_district | `SCSD/tl_<year>_<state>_scsd.zip` | `School` / 1 | 7 |
| `school_district_elementary` | school_district | `ELSD/tl_<year>_<state>_elsd.zip` | `School` / 2 | 7 |

Layer ids are the current-vintage layers of each MapServer, the ones listed
ahead of the vintage-specific "BAS", "ACS" and "Census 2020" groups.

The adapter fetches a TIGER/Line zip through the snapshot store and reads
only its `.dbf` attribute table (`src/sources/dbf.py`, a small dBASE
reader; no geometry library is needed and no polygon is read). Each row
becomes a `TigerRecord` with `geoid`, `name`, `namelsad`, the FIPS
components, `lsad`, `classfp`, `funcstat` and `mtfcc` as strings; a row
whose GEOID has the wrong length, does not start with its STATEFP, or has
malformed codes becomes a `TigerRowError`.

`tigerweb_query_url(config, layer_key, geoid)` builds the GeoJSON query
without any request:

```
https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer/4/query?where=GEOID%3D'0670364'&outFields=*&outSR=4326&f=geojson
```

That string, with `%3D` and literal apostrophes, is what the golden
Sausalito geometry cites. `geometry_url(config, record)` picks the CDP
layer for PLACE rows that are census designated places. A geometry's
`Source` cites the MapServer URL (`tigerweb_service_url`), release = the
TIGER/Line year, and `valid_from` = `series_as_of(year)`, January 1 of the
release year.

Fixtures under `tests/fixtures/tiger/` are attribute-table excerpts, one
CSV per layer, with no geometry. National layers cite the exact zip; the
per-state layers cite the layer directory and name the state files the
rows came from in `dataset`.

## 8. What this layer does not do

- It does not normalize, resolve, or classify anything. Adapters return
  plain records; later phases consume them.
- It does not touch `data/ocdid_pipeline.duckdb`, `.etag_cache.json`
  semantics, `DownloadManager`, or `OCDidMatcher`. Those stay until the
  cleanup phase.
- It is not wired into `GeneratePipeline` or the CLI. The golden harness's
  `run_pipeline` still runs the existing generate stage; integration of the
  adapters is a later phase.
