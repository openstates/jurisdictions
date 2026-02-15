# Stage 1: Verification Analysis

Date: 2026-02-15

## Purpose

Line-by-line verification of the Stage 1 design document and implementation
plan against the original pipeline specification (`docs/init_research_pipeline.md`)
to ensure no requirements were lost in translation.

## Documents Compared

1. **Original spec**: `docs/init_research_pipeline.md` — working notes describing
   the full three-stage pipeline architecture
2. **Design doc**: `docs/plans/2026-02-13-stage1-ocdid-pipeline-design.md` —
   architectural decisions for Stage 1 only
3. **Implementation plan**: `docs/plans/2026-02-15-stage1-ocdid-pipeline-implementation.md` —
   10-task TDD plan for building Stage 1

## Stage 1 Requirements — Coverage Matrix

| # | Spec Requirement | Design Doc | Impl Task | Status |
|---|---|---|---|---|
| 1 | `main.py = orchestrator` | main.py "Pure orchestrator. No business logic." | Task 8 | Covered |
| 2 | `Takes a state as an argument (run by state)` | `--state wa`, `--state wa,tx,oh` CLI | Task 8 `parse_args()` | Covered |
| 3 | `calls parent pipeline (ocdid_pipeline.py)` | Calls `DownloadManager` then `OCDidMatcher` (split into two modules instead of one) | Tasks 5-7 | Covered (restructured) |
| 4 | Pull master list of OCDids (`us.csv`) | `master_url()` → `country-us.csv` | Task 5 | Covered |
| 5 | Pull per-state local CSVs | `local_urls()` → `state-{st}-local_gov.csv` | Task 5 | Covered |
| 6 | For each local record, pull full data from master | Inner join on `id` column | Task 7 SQL join | Covered |
| 7 | "We will work from the master list" | `raw_record` contains master columns only | Task 7 `m.*` select | Covered |
| 8 | Parse OCDid in OCDidParsed model | `ocdid_parser()` → `OCDidParsed` | Task 7 | Covered |
| 9 | Generate a UUID | `deterministic_id.generate_id()` → `oid1-` string | Task 7 | Covered (see note A) |
| 10 | Store UUID/OCD-ID in DuckDB lookup table | `ocdid_uuid_lookup` table | Task 7 `_store_lookup_table()` | Covered |
| 11 | "Can be run once, skipped in future runs" | `INSERT ... WHERE NOT EXISTS` idempotency | Task 7 | Covered |
| 12 | "Backup to a .csv file as well" | `data/ocdid_uuid_lookup.csv` | Task 7 `COPY ... TO` | Covered |
| 13 | Return `OCDidIngestResp(UUID, OCDidParsed, raw_record)` | Model with `uuid: str`, `ocdid: OCDidParsed`, `raw_record: dict` | Task 2 + Task 7 | Covered |

### Notes

**A. UUID generation** — The spec says "Generate a UUID (timestamp)." During
design, the team decided to use the existing `deterministic_id.py` system
(`oid1-` prefixed, deterministic, decodable IDs) instead of standard timestamp
UUIDs. The `OCDidIngestResp.uuid` field type was changed from `UUID` to `str`
to hold these IDs. If the team later reverts to standard UUIDs, only this one
field changes.

**B. File naming** — The spec references `us.csv` as a shorthand. The actual
file on GitHub is `country-us.csv`. The design doc uses the correct filename.

**C. Module naming** — The spec references `ocd_pipeline.py` as a single
module. The design splits this into `download_manager.py` (fetch + DuckDB load)
and `ocdid_matcher.py` (join + UUID generation) for separation of concerns.

## Stage 2+ Requirements — Confirmed Deferred

These items appear in the spec but are intentionally **not** part of Stage 1.
They will be addressed in later stages.

| Spec Requirement | Stage | Notes |
|---|---|---|
| "Convert this into a stub for a Division record" | 2 | Stage 1 produces `OCDidIngestResp` only, no Division stubs |
| Sourcing: "Initial ingest of master OCDids maintained by the Open Civic Data project" | 2 | Sourcing metadata goes on the Division model |
| "Map fields in master list to Division model" | 2 | Division model mapping uses `DivGenerator` |
| "Convert the model to .yaml and store with UUID only as the name" | 2 | YAML serialization via Division/Jurisdiction generators |
| "Calls Child Pipeline (GeneratorReq →)" | 2 | `generate_pipeline.py` already exists, will be wired in Stage 2 |
| Fuzzy matching against research CSV (Creyton's spreadsheet) | 2 | `generate_pipeline.py` already has rapidfuzz matching |
| Division + Jurisdiction generation | 2 | `DivGenerator` + `JurGenerator` already exist |
| Quarantine to Creyton's spreadsheet tab | 2 | Currently uses NoMatch quarantine CSV |
| Stats / resolve match pipeline | 3 | Post-processing after all child workflows complete |

## Enhancements Beyond Original Spec

These were added during design discussions and are not in the original spec.

| Enhancement | Rationale |
|---|---|
| Three-outcome matching (match, local orphan, master orphan) | Data quality: detect temporal drift between state and national files |
| Orphan quarantine tables in DuckDB (`local_orphans`, `master_orphans`) | Quarantine unmatched records for human review |
| Rich progress bars (3 phases: download, load, match) | UX: visibility into pipeline progress for long-running state-by-state processing |
| ETag/Last-Modified caching with `--force` override | Performance: skip re-downloading unchanged files on repeat runs |
| Loguru logging with `--log-dir` CLI flag | Standardization: team decision to migrate from stdlib `logging` to loguru |
| `models.py` renamed to `pipeline_models.py` | Clarity: distinguish pipeline DTOs from domain models in `src/models/` |
| `state_lookup.json` moved to `src/data/` | Convention: data files belong in a data directory, not alongside source code |

## Decision Log: `raw_record` Contains Master Data Only

**Date:** 2026-02-15
**Context:** During verification, it was noted that the Task 7 SQL query
originally selected a mix of local and master columns into `raw_record`:

```sql
-- Original (mixed local + master data)
SELECT l.id, l.name, l.state, m.name AS master_name
FROM local_ocdids l
INNER JOIN master_ocdids m ON l.id = m.id
```

**Decision:** The `raw_record` field in `OCDidIngestResp` must contain the
**master** record's data only. The master list is the source of truth. Local
state files serve as a cross-check to verify that the national list captured
all state OIDs and to detect temporal drift (OIDs added to state files that
haven't yet been derived into the national file, or vice versa).

**Changes made:**

1. **Design doc** (`2026-02-13-stage1-ocdid-pipeline-design.md`) — Updated the
   OCDidMatcher section to explicitly state that the master list is the source
   of truth, local files are a cross-check, and `raw_record` contains master
   columns only.

2. **Implementation plan** (`2026-02-15-stage1-ocdid-pipeline-implementation.md`)
   — Updated Task 7:
   - SQL query changed to `SELECT m.*, l.state AS _local_state` — selects all
     master columns, uses local state only for filtering
   - Column names read dynamically from `conn.description` instead of hardcoded
   - `_local_state` is popped from the dict before building `raw_record`
   - Added new test `test_raw_record_contains_master_data` verifying that
     `raw_record` has master columns (`id`, `name`) and does not contain
     `_local_state`

**Updated query:**

```sql
-- Corrected (master data only in raw_record)
SELECT m.*, l.state AS _local_state
FROM local_ocdids l
INNER JOIN master_ocdids m ON l.id = m.id
```

## Verification Result

**All Stage 1 requirements from `init_research_pipeline.md` are accounted for.**
Every requirement either has a direct mapping to a design section and
implementation task, or is explicitly documented as deferred to Stage 2+. No
requirements were lost in translation.
