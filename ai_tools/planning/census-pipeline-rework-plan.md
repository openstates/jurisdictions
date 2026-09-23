---
id: census-pipeline-rework-plan
type: planning
owner: maintainers
status: active
last_updated: 2026-09-23
tags: [planning, rework, census, pipeline]
---

# Census GUS Pipeline Rework — Phased Plan

## Scope and Precedence

This plan governs the Census Government Units Survey (GUS) pipeline rework.
It is **subordinated to root `AGENTS.md`**, works alongside the task
instruction at `ai_tools/tasks/census-pipeline-rework.instruction.md`, and
tracks issue #131.

Authoritative design reference:
- `docs/rework/openstates-jurisdictions-data-pipeline.pdf`
- `docs/rework/openstates-jurisdictions-data-pipeline.md` (grep-friendly)

## Ticket Convention (Required)

**Every issue that tracks work under this plan MUST use the `[Rework]`
prefix in its title**, e.g.:

- `[Rework] Phase 1.1 — Map existing pipeline`
- `[Rework] Phase 2.1 — Stable UUID identity`
- `[Rework] Phase 3 — Golden sample integration harness`

The prefix tells collaborators the PR targets the rework branch
(`131-gus-pipeline-rework`), not `main`. Any PR under this plan must set the
rework branch as its base.

## Working Branch

`131-gus-pipeline-rework` (branched from `main`). Keep `main` available as a
reference implementation and behavioral baseline.

## Global Success Criteria

1. Pipeline runs from cached snapshots without normal network access.
2. Existing canonical OCDIDs remain stable.
3. Supported Census governments resolve deterministically.
4. TIGER-backed Divisions contain authoritative identifiers and GeoJSON references.
5. Unknown OCDIDs quarantine.
6. Existing exceptions are reused or intentionally migrated.
7. UUIDs remain stable when mutable facts change.
8. Temporal geometry and provenance are preserved.
9. Golden sample output regenerates deterministically.
10. CI fails on unexplained golden drift.
11. California pilot fully categorizes inputs.
12. National high-confidence generation is reproducible.
13. Graph state rebuilds entirely from YAML.

## Sample Output Change Control

`tests/sample_output/` is a **golden contract**, not permanently frozen
data. It changes rarely, only with explicit maintainer approval, and
the new files become the baseline every downstream phase tests against.
The lifecycle spans four of the phases below:

1. **Read-only baseline (every phase, every normal test run):** golden
   tests compare against these fixtures and never mutate them (see
   Task 3.3, Task 3.5; root `AGENTS.md` §"Testing Rules"). No phase
   edits YAML under `tests/sample_output/` as a side effect of doing
   its own work.
2. **Phase 2 model changes (#133):** land alongside a documented
   structural migration in
   `docs/rework/sample_output_migration.md` (Task 2.7). The doc
   describes the intended change; the YAML files themselves stay
   untouched at this point.
3. **Phase 3 golden harness (#134):** regenerates output from
   controlled fixtures and diffs against the checked-in files. After
   Phase 2 those diffs are expected to be non-empty — that failure is
   the signal that Phase 11 work is due, **not** a fixture to patch
   to make the test pass.
4. **Phase 11 regeneration (#142, Task 11.3):** a maintainer runs the
   explicit regeneration command (Task 3.5), reviews the diff,
   classifies every change per §35 (`STRUCTURAL`, `SOURCE_CORRECTION`,
   `BUG_FIX`, `TEMPORAL_UPDATE`, `IDENTIFIER_MIGRATION`,
   `EXPECTED_NEW_FIELD`, `REGRESSION`), and approves the update.
   Agents do not run this command autonomously and never hand-edit
   the YAML. Once committed, the regenerated files are the new golden
   contract — Phases 12–20 test against them.
5. **Phase 12 CI (#143):** unexplained drift in `tests/sample_output/`
   fails PR CI. The only sanctioned path to drift is step 4.

Invariants every phase respects:

- **Never silently edit** `tests/sample_output/`. A failing golden
  test is a signal to file a Phase 11 work-item and stop — not a
  fixture to correct so the test passes. (Root `AGENTS.md`
  §"Testing Rules", "never fake-it"; task instruction §29,
  §33–§36.)
- **Reading is always fine.** Inventory, diff, and comparison
  activities never need approval.

Per-file observations, suspicious values, and coverage gaps against
this contract are catalogued in
`docs/rework/sample_output_inventory.md` §6.

## Phase 0 — Establish Rework Environment

### Task 0.1 — Rework branch
Target: `131-gus-pipeline-rework`. **Done** (this branch).

### Task 0.2 — Preserve existing AGENTS.md baseline
Inspect: `git show main:AGENTS.md`, `git log -- AGENTS.md`.
Root `AGENTS.md` is **not replaced**; this rework's guidance lives in
`ai_tools/tasks/census-pipeline-rework.instruction.md` and defers to root
for engineering conventions.

Success:
- Existing root policy read in full.
- Meaningful rules captured or explicitly deferred to root.
- No rule silently discarded.

### Task 0.3 — Documentation area
Create as needed:
- `docs/rework/current_pipeline.md`
- `docs/rework/reuse_inventory.md`
- `docs/rework/sample_output_migration.md`
- `docs/rework/architecture_decisions.md`
- `docs/rework/comparison_reports/`

## Phase 1 — Repository Archaeology

### Task 1.1 — Map existing pipeline
Document source → intermediate state → matching → models → YAML.

Targets: CLI, DuckDB/state, source acquisition, Census/TIGER, OCDID
generation, rendering, validation.

### Task 1.2 — Reuse inventory
Classify modules: `REUSE`, `ADAPT`, `REPLACE`, `UNDECIDED`. Every major
subsystem gets a disposition and associated tests.

### Task 1.3 — OCDID inventory
Document parsers, slug rules, path builders, matching, exception logic,
legacy IDs. Root `AGENTS.md` requires `OCDIdParsed.parse_ocdid()` — the
inventory must record every place we currently use string splits or regex.

### Task 1.4 — Model inventory
Field matrix for Division, Jurisdiction, Geometry, Source, identifiers, URL
models, relationships, temporal fields, UUID logic. Identify model
migration risks.

### Task 1.5 — Sample-output inventory
Inventory every `tests/sample_output/` file and its semantics. Per root
`AGENTS.md`, this data is read-only; the inventory documents intent, not
edits.

### Phase 1 Gate
Required deliverables:
- `docs/rework/current_pipeline.md`
- `docs/rework/reuse_inventory.md`
- Sample inventory
- OCD inventory

No major subsystem replacement before this gate.

## Phase 2 — Domain Model Stabilization

Per root `AGENTS.md`, changes to Pydantic model contracts in `src/models/`
require explicit maintainer approval. Every task here needs sign-off before
merge.

### Task 2.1 — Stable UUID identity
UUID derived from stable OCD identity, not mutable timestamps.
Tests: website change, source release change, geometry change, retrieval
date change all retain UUID.

### Task 2.2 — Source/Sourcing
Represent: source name, dataset, release/vintage/version, URL, publication
date, retrieval date. Different releases distinguishable; release metadata
does not change entity identity.

### Task 2.3 — Geometry representation
Support `valid_from`, `valid_to`, Source, external identifier, geometry
URL, provider neutrality. Multiple geometry versions coexist.

### Task 2.4 — External identifiers
Preserve GEOIDs/FIPS/LEA and leading zeros. Serialization round-trip exact.

### Task 2.6 — Nullable website
Valid Jurisdiction can serialize with no website.

### Task 2.7 — Document model migration
Update `docs/rework/sample_output_migration.md` with fixture-affecting
structural changes.

## Phase 3 — Golden Sample Integration Harness

Per root `AGENTS.md`, `tests/sample_output/` is immutable and
`tests/integration/` changes require approval. Design the harness so tests
never mutate expected sample output.

**Done** (issue #134): `55524c2` (3.1–3.2), `76a044d` (3.3–3.5),
`ecbb938` (3.6–3.8). Harness: `tests/integration/golden/`; regeneration
command: `scripts/regenerate_sample_output.py`; docs:
`docs/rework/golden_input_mapping.md`, `docs/rework/golden_harness.md`.
The 12 golden comparisons are `xfail(strict=True)` until Phase 11
regenerates the files.

### Task 3.1 — Controlled fixture layout
Create:
- `tests/fixtures/census_governments/`
- `tests/fixtures/tiger/`
- `tests/fixtures/ocd_master/`
- `tests/fixtures/sources/`

### Task 3.2 — Map golden output to inputs
Every golden record has a controlled input where feasible.

### Task 3.3 — Temporary output runner
Tests never mutate golden files.

### Task 3.4 — Semantic/YAML comparison
Failures identify changed file and field.

### Task 3.5 — Explicit fixture regeneration command
Expected output updates require an explicit maintainer command.

### Task 3.6 — Quarantine fixture
Unknown OCD candidate deterministically quarantines.

### Task 3.7 — Stable identity golden test
Mutable fact changes retain identity.

### Task 3.8 — Temporal geometry golden test
Two geometry periods serialize correctly with source provenance.

Scope note: a Division file holds geometry from one Census series only;
historical series are separate runs and separate files. The golden test
therefore covers one geometry's validity window (`valid_from` = series
as-of date, `valid_to` null while active) and source release. A record
with more than one geometry (a genuinely multi-part special-district
boundary) is a Phase 15 edge case, Task 15.1.

## Phase 4 — Source Snapshot Layer

The government universe comes from two Census Bureau listings. The Census
of Governments: Organization benchmark (years ending in 2 and 7) is what
the pipeline builds from; the annual Government Units listing (2024 on,
other years) updates it in between. The two are fetched and parsed by
independent modules so a benchmark year can be re-run alone; a merge step
diffs them by Census ID and writes the current universe plus a change
report under `data/cache/`.

**Done** (issue #135): `e12a000` (4.4), `5c36bc6` (4.3), `663881f` (4.1),
`bfaade7` (4.2), `21ac381` (4.5), `fcccc3a` (4.6). Adapters:
`src/sources/`; layer config: `config/tiger_layers.yaml`; fixtures:
`tests/fixtures/{census_governments,census_gus,tiger,ocd_master}/`; docs:
`docs/rework/source_snapshots.md`. The adapters are not yet wired into
`GeneratePipeline`; Phase 5.5 and 6.9 integrate them.

### Task 4.1 — Census Government adapter
Separate: fetch, verify, cache, parse. Fixture parse offline; malformed
rows handled structurally. Reads the Census of Governments benchmark
(`govt_units_<year>.ZIP`).

### Task 4.2 — TIGER adapter
Initial coverage: state, county, place, county subdivision, school district.
Metadata resolves offline without PostGIS.

### Task 4.3 — OCD master adapter
Exact membership lookup; optional nearest suggestions for review. Exact
positive/negative tests pass offline.

### Task 4.4 — Snapshot metadata
Retain URL, release/version, download date, checksum where practical.

### Task 4.5 — Annual Government Units listing adapter
Independent of the benchmark adapter: own fetch, layout, parse, fixtures
(`gov_units_<year>.zip`). Public pension systems are parsed and exported
to `data/cache/` as their own dataset; the pipeline does not read them.

### Task 4.6 — Benchmark/annual merge
Diff by Census ID: `unchanged`, `filled`, `changed`, `added`, `removed`.
Annual values win; benchmark-only fields carried forward; benchmark
records missing from the annual listing kept and flagged, never dropped.
Merged dataset and field-level change report written under `data/cache/`
with sidecars naming both releases.

## Phase 5 — Normalized Government Layer

### Task 5.1 — `GovernmentRecord`
Census ID, raw/normalized name, type, subtype, state/county identifiers,
website if present, Source.

### Task 5.2 — Name normalization
Deterministic; source name preserved.

### Task 5.3 — Government type classification
Initial categories: `STATE`, `COUNTY`, `MUNICIPAL`, `TOWNSHIP/MCD`,
`SCHOOL_DISTRICT`, `SPECIAL_DISTRICT`, `OTHER/UNKNOWN`. Every fixture gets
a deterministic class or `UNKNOWN`.

### Task 5.4 — Structured source errors
No silent parser drops.

### Task 5.5 — Integrate normalization into golden harness

## Phase 6 — Government-to-Geography Resolver

### Task 6.1 — Common resolver interface
Typed outcomes: `RESOLVED`, `NO_GEOGRAPHY`, `DIVISION_NOT_FOUND`, `AMBIGUOUS`.

### Task 6.2 — State resolver — target 100% fixture resolution.
### Task 6.3 — County resolver — target 100% ordinary fixture resolution.
### Task 6.4 — Municipal resolver
Tests: same name across states; county implications; cross-county place
where relevant. No wrong-state or wrong-type matches.

### Task 6.5 — MCD resolver
Governmental MCD resolves; statistical-only geography not misclassified.

### Task 6.6 — School resolver
Prefer state + LEA/district IDs. Fixture districts resolve without
fuzzy-only matching.

### Task 6.7 — Special district routing
No fabricated Census geography.

### Task 6.8 — TIGERweb GeoJSON URL builder
Inputs: geography type, GEOID, configured service/layer. Correct URL with
`f=geojson`, no request required in unit tests.

### Task 6.9 — Integrate resolver into golden harness

## Phase 7 — OCDID Rule Engine

### Task 7.1 — Candidate structure
Retain candidate, rule, version, transformations, hierarchy, exception.

### Task 7.2 — Salvage parser/slug code
Existing behavior/tests preserved or explicitly documented.

### Task 7.3 — General hierarchy rules
Initial: state, county, municipality/place, MCD, school district. Ordinary
fixtures generate expected paths.

### Task 7.4 — Migrate exceptions
Known exception fixtures retain canonical OCDIDs.

### Task 7.5 — Exception precedence tests
### Task 7.6 — Candidate provenance tests

## Phase 8 — OCD Validation and Quarantine

### Task 8.1 — Exact canonical match — known paths `VERIFIED`.
### Task 8.2 — Unknown quarantine — 100% unknown fixture IDs quarantine.
### Task 8.3 — Review suggestions — never auto-canonicalize.
### Task 8.4 — Quarantine serialization
Reviewer can understand record without rerun.
### Task 8.5 — Golden quarantine integration

## Phase 9 — Canonical Model Construction

### Task 9.1 — Build Division
Stable UUID, canonical OCDID, names, classification, external identifiers,
temporal geometry reference, Source, relationships.

### Task 9.2 — Build Jurisdiction
Stable UUID, OCD identity, official name, class, Census government ID,
Division relationship, website if known, Source.

### Task 9.3 — Offline model validation — zero network calls.

## Phase 10 — YAML Rendering

### Task 10.1 — Deterministic serializer
Byte-identical output on two unchanged runs.

### Task 10.2 — Stable file naming/path policy
### Task 10.3 — Renderer has no resolution logic
### Task 10.4 — Complete golden end-to-end path
Fixture source → parse → normalize → resolve → OCD candidate → canonical
validation → models → YAML → compare. 100% expected success and quarantine
fixtures pass.

## Phase 11 — Existing Sample Output Migration

### Task 11.1 — Diff new vs main
Classify all changes: `STRUCTURAL`, `SOURCE_CORRECTION`, `BUG_FIX`,
`TEMPORAL_UPDATE`, `IDENTIFIER_MIGRATION`, `EXPECTED_NEW_FIELD`,
`REGRESSION`. Zero unexplained material differences.

### Task 11.2 — Verify changed facts
Use authoritative source per field. 100% factual changes verified.

### Task 11.3 — Explicitly regenerate approved golden files
Requires maintainer approval per root `AGENTS.md`.

## Phase 12 — CI

### Task 12.1 — Offline unit CI
### Task 12.2 — Golden integration CI — unexplained drift fails CI.
### Task 12.3 — Separate live-source refresh tests
Normal PR CI does not depend on fragile live services.

## Phase 13 — California Pilot

### Task 13.1 — Snapshot California-relevant sources
### Task 13.2 — Normalize all government records
Metrics: input, normalized, errors, classification counts. No silent drops.

### Task 13.3 — Geography resolution
Track by type. Targets: state 100%; counties 100%; municipalities near-total
with inspectable misses; supported school districts near-total deterministic
resolution.

### Task 13.4 — OCD validation
Track canonical, new, ambiguous, exception usage. Zero unknown silently
accepted.

### Task 13.5 — Compare with main
Create `docs/rework/comparison_reports/california.md`.

### Task 13.6 — California gate
Requires: golden suite green; no silent loss; every input has terminal
status; unresolved records categorized; second run reproducible.

## Phase 14 — National High-Confidence Run

### Task 14.1 — Run supported classes nationally
Track per-state and national counts.
### Task 14.2 — Reproducibility run — zero output diff.
### Task 14.3 — Coverage report
Create `docs/rework/comparison_reports/national_high_confidence.md`. 100%
inputs in documented terminal state.

## Phase 15 — Special District Strategy

### Task 15.1 — Taxonomy of unresolved special governments
### Task 15.2 — Provider-neutral official geometry discovery framework
### Task 15.3 — Multi-Division relationships (`SERVES`/`OVERLAPS`/`CONTAINED_BY`)
### Task 15.4 — Representative special-district adapter
Official source; no fake GEOID; provenance preserved; golden fixture added.

## Phase 16 — Graph Projection

### Task 16.1 — Graph schema
### Task 16.2 — OCD hierarchy projection
### Task 16.3 — Jurisdiction↔Division projection
### Task 16.4 — Temporal geometry projection
### Task 16.5 — Disposable graph test
Delete graph, rebuild from YAML, compare expected facts. No graph-only
canonical state.

## Phase 17 — Code Refinement

The repository standard for record and message types is Pydantic
(`src/models/`, `src/init_migration/pipeline_models.py`). The source
layer built in Phase 4 used `dataclasses` for its snapshot metadata,
adapter records, parse results and merge results, and earlier utilities
(`src/utils/deterministic_id.py`, `src/utils/parquet.py`, `src/clients/`)
did the same. This phase brings every type onto one model infrastructure
before legacy code is deleted, without changing behaviour or output bytes.

### Task 17.1 — Standardize model infrastructure on Pydantic
Convert every `@dataclass` record type under `src/` to a Pydantic
`BaseModel` (frozen where the dataclass was frozen): `SnapshotSpec`,
`SnapshotMetadata`, `Snapshot`; `CensusGovernmentRecord`,
`CensusRowError`, `ParseResult`, `Layout`; `TigerRecord`,
`TigerRowError`, `TigerConfig` and its layer types; `OCDMasterEntry`,
`OCDRowError`, `Suggestion`; `MergedRecord`, `FieldChange`,
`MergeResult`; and the utility and client types. Sidecar JSON goes
through `model_dump`/`model_validate`. Success: unit and integration
suites unchanged and green; fixture sidecars and the CSV exports under
`data/cache/` are byte-identical before and after.

### Task 17.2 — Shared validation primitives
One module of `Annotated` string types for Census identifiers (six-digit
Census ID, two-digit state FIPS, three-digit county FIPS, five-digit place
and LEA codes, GEOID by layer length) replacing the per-module regexes in
`government_units.py` and `census_tiger.py`. Leading zeros preserved;
malformed values still become structured row errors, never exceptions.

### Task 17.3 — Consistent module conventions
`from src...` imports everywhere; no duplicated helpers (CSV writers,
cell coercion, checksum helpers) across adapters; structured logging
extras named consistently; every public function typed. Record any
deliberate exceptions in `docs/rework/architecture_decisions.md`.

### Task 17.4 — Static typing gate
Add a type checker run (`mypy` or `pyright`) to the pre-commit checklist
and CI over `src/` and `tests/`, clean on the converted modules.

## Phase 18 — Cleanup

### Task 18.1 — Identify dead legacy modules
### Task 18.2 — Verify behavior coverage before deletion
### Task 18.3 — Remove obsolete hidden state dependencies
Fresh checkout + snapshots can regenerate outputs.

## Phase 19 — Final Documentation

Create/update runbooks for:
- Architecture
- Source refresh
- Quarantine review
- Golden fixture update
- Redistricting/temporal updates

## Phase 20 — Final Acceptance Suite

**Functional**: GUS loads; TIGER loads; OCD master loads; supported
governments resolve; unknown IDs quarantine; YAML deterministic.

**Model**: stable UUID; provenance preserved; temporal geometry preserved;
website nullable; no fake GEOIDs.

**Testing**: unit green; golden green; quarantine golden green; fixtures
immutable during tests; offline suite passes.

**Pilot**: California fully categorized.

**National**: supported run complete; all records terminally categorized;
second run zero diff.

**Graph**: fully reconstructable from YAML.

## Recommended Sub-Agent / Owner Assignment

- **A — Models and Temporality** — Phase 2, canonical model construction
- **B — Golden Integration** — Phase 3, sample migration, golden CI
- **C — Census Government** — Government source adapter and normalization
- **D — TIGER and Geometry** — TIGER adapter and geometry URL builder
- **E — Resolution** — Government-to-Division resolvers
- **F — OCDID** — OCD master, candidate engine, exceptions, validation, quarantine
- **G — Rendering/CLI** — Deterministic YAML and command wiring
- **H — Evaluation** — California/national runs and reports
- **I — Special Districts** — Special-district strategy
- **J — Graph** — Graph projection

## Final Metrics

- Golden sample reproduction: 100%
- Unexplained golden differences: 0
- Uncategorized source governments: 0
- Silent record drops: 0
- Unknown OCDIDs silently accepted: 0
- Fabricated Census GEOIDs: 0
- Normal processing requiring PostGIS: 0
- Normal fixture integration requiring network: 0
- Second-run generated YAML differences: 0
- Graph-only canonical facts: 0

The system is correct when every record is processed deterministically,
every decision is explainable, every unresolved case is explicit, every
canonical output is reproducible, and the repository's established
engineering rules (per root `AGENTS.md`) remain preserved.
