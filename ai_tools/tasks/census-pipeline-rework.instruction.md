---
id: census-pipeline-rework-task
type: instruction
owner: maintainers
status: active
last_updated: 2026-08-08
tags: [workflow, execution, rework, census, pipeline]
---

# Census Government Units Survey (GUS) Pipeline Rework — Task Instruction

## Scope and Precedence

This is a **task-scoped** instruction for the multi-phase rework that swaps the
pipeline's canonical source from the OCD ID corpus to the Census Government
Units Survey (GUS), matching GUS → OCD IDs rather than the reverse.

This instruction is **subordinated to root `AGENTS.md`**. Where anything below
appears to conflict with root policy, root `AGENTS.md` wins. In particular,
these repo-wide rules already live in root `AGENTS.md` and are not restated
here:

- Instruction precedence and routing
- Git safety and change control
- Commands and environment (`uv run …`)
- Testing rules (TDD, `tests/sample_output` immutability, `tests/integration` approval, no output hiding)
- Data and model rules (Pydantic contracts in `src/models/`, OCD ID format)
- Logging, code style, and contributor workflow

For this rework only, this instruction **supersedes** the generic workflow in
`ai_tools/tasks/feature-delivery.instruction.md`.

## Working Branch and Ticket Conventions

- All rework happens on the `131-gus-pipeline-rework` branch (or a
  successor `rework/*` branch). `main` remains the reference baseline.
- Every issue tracking work for this rework MUST use the `[Rework]` prefix in
  the title, e.g. `[Rework] Phase 2.1 — Stable UUID identity`, so
  collaborators can identify which PRs merge into the rework branch rather
  than `main`.
- Phased plan and per-phase tasks live in
  `ai_tools/planning/census-pipeline-rework-plan.md`.
- Authoritative design reference:
  `docs/rework/openstates-jurisdictions-data-pipeline.pdf` (with
  grep-friendly source at `docs/rework/openstates-jurisdictions-data-pipeline.md`).

### Phase Tracking (issues #132–#150)

Each phase in the plan has a corresponding `[Rework]` issue. Keep this
checklist in sync with issue state; the issues themselves remain authoritative.

- [ ] Phase 1 — Repository Archaeology — #132
- [ ] Phase 2 — Domain Model Stabilization — #133
- [ ] Phase 3 — Golden Sample Integration Harness — #134
- [ ] Phase 4 — Source Snapshot Layer — #135
- [ ] Phase 5 — Normalized Government Layer — #136
- [ ] Phase 6 — Government-to-Geography Resolver — #137
- [ ] Phase 7 — OCDID Rule Engine — #138
- [ ] Phase 8 — OCD Validation and Quarantine — #139
- [ ] Phase 9 — Canonical Model Construction — #140
- [ ] Phase 10 — YAML Rendering — #141
- [ ] Phase 11 — Existing Sample Output Migration — #142
- [ ] Phase 12 — CI — #143
- [ ] Phase 13 — California Pilot — #144
- [ ] Phase 14 — National High-Confidence Run — #145
- [ ] Phase 15 — Special District Strategy — #146
- [ ] Phase 16 — Graph Projection — #147
- [ ] Phase 17 — Cleanup — #148
- [ ] Phase 18 — Final Documentation — #149
- [ ] Phase 19 — Final Acceptance Suite — #150

## Repository Mission (Rework Framing)

This repository builds and maintains a comprehensive, reproducible
representation of U.S. government entities and the geopolitical divisions
over which they exercise jurisdiction.

Canonical outputs are version-controlled YAML records:

- `Jurisdiction`: a government entity exercising authority.
- `Division`: a geopolitical or administrative area.

Downstream graph databases, relational databases, APIs, search indexes, and
other derived systems must be reproducible from the repository.

Open Civic Data Division Identifiers remain core identifiers because their
hierarchical, human-readable paths encode useful civic and administrative
structure.

## 1. This Is a Rework, Not a Greenfield Rewrite

The repository already contains a working pipeline. The rework must actively
inspect `main`, salvage useful models, source adapters, OCDID logic, exception
handling, validation, fixtures, normalization, and domain knowledge, while
replacing architectural coupling that conflicts with this design.

Before replacing an existing subsystem, inspect its implementation and history
on `main`.

## 2. Primary Pipeline

```
SOURCE → NORMALIZE → RESOLVE → GENERATE CANDIDATE OCDID
       → VALIDATE AGAINST CANONICAL OCD
       → QUARANTINE IF NECESSARY
       → BUILD CANONICAL MODELS → VALIDATE → RENDER YAML
```

Pipeline stages must be independently testable and, where practical,
independently rerunnable. Network acquisition must be separated from local
processing.

## 3. Authoritative Source Responsibilities

### Census Government Organization / Government Units Survey

Primary source for the government universe: existence, official name, type,
Census government identifier, and administrative information.

### Census TIGER / TIGERweb

Primary geography source where applicable: Division existence, Census GEOID,
geography class, and authoritative boundary reference.

### Open Civic Data Division IDs

Canonical source for existing OCD Division identity, human-readable civic
hierarchy, recursive navigation, and compatibility with OpenStates / Open
Civic Data.

### Other official government sources

Use state, local, district, or agency sources when Census does not provide
required information, especially for special-purpose district geometry.

## 4. Identifier Semantics

- **OCD Division ID**: human-readable hierarchical civic identity.
- **Census GEOID**: Census geographic identity.
- **Census Government ID**: government-entity identity.
- **UUID**: stable repository-internal identity.
- **Geometry URL**: authoritative boundary retrieval location.

Do not replace OCDIDs with GEOIDs or fabricate OCDIDs from GEOIDs.

## 5. Stable Identity

Prefer stable UUIDs derived from stable identity, e.g. `UUID5(OCDID)`.

Mutable facts such as website, source release, geometry, retrieval time, or
update date must not change entity identity.

## 6. Domain Semantics

A `Division` is a geopolitical, administrative, electoral, or
jurisdictionally meaningful geographic area.

A `Jurisdiction` is a government entity exercising authority over one or more
Divisions.

Do not equate office location with jurisdiction.

## 7. Relationships

Prefer explicit directional relationships such as:

```
Jurisdiction --GOVERNS--> Division
```

Support `SERVES`, `OVERLAPS`, and `CONTAINED_BY` where justified. Do not
force regional governments into false containment hierarchies.

## 8. OCDID Policy

Preserve existing canonical OCDIDs. A newly generated candidate does not
establish canonical identity.

- Existing canonical OCDID → preserve.
- Absent candidate → quarantine and review.

## 9. OCDID Rule Engine

OCDID generation must be isolated behind a dedicated rule engine. Rules
should encode hierarchy components, segment types, slug rules, required
parents, and geography-specific conventions.

Candidates must retain provenance such as rule name/version and
transformations.

## 10. Existing OCD Code

Before creating new OCD behavior, inspect current repository code and
canonical Open Civic Data tooling for parsers, slug normalizers, path
builders, matching utilities, exceptions, validation, and hierarchy
conventions. See root `AGENTS.md` for the mandatory use of
`OCDIdParsed.parse_ocdid()`.

## 11. Exceptions

Keep general rules and exceptions separate. Support explicit categories such
as identifier override, hierarchy override, slug/name override, and geography
mapping override.

## 12. Canonical OCD Validation

Exact match against the canonical OCD corpus is the acceptance test. Fuzzy
matching may assist review only and must never silently canonicalize
identity.

## 13. Quarantine

Unknown and ambiguous records are first-class outputs, not log warnings.
Quarantine records must include enough government, Division, candidate
OCDID, rule, transformation, source, and possible-match context for human
review.

## 14. Human Review

Human review should improve normalization, resolution, rules, exceptions, or
upstream OCD data. Avoid manual patches to generated YAML when a
reproducible rule can solve the problem.

## 15. New OCDIDs

Legitimate new OCDIDs should be reviewed and, by default, contributed
upstream to the canonical Open Civic Data repository before becoming
accepted canonical identifiers here.

## 16. Source Acquisition vs Processing

Prefer bulk source snapshots. Once downloaded, normal development and tests
should run without repeated network access. DuckDB or other query engines
may be used, but must not become hidden mutable state required for
reproducibility.

## 17. TIGER Strategy

Do not require local PostGIS or local TIGER infrastructure. Store enough
metadata to construct TIGERweb GeoJSON URLs directly where applicable. Do
not check massive polygon data into Git.

## 18. Geometry

Geometry references must be provider-neutral and support:

- external identifier;
- URL;
- Source;
- `valid_from`;
- `valid_to`.

ArcGIS is an implementation detail, not the core geometry abstraction.

## 19. Source / Sourcing

Reuse the repository's existing Source/Sourcing model. Extend it only when
necessary to represent source name, dataset, release/vintage/version,
publication date, retrieval date, and URL.

Do not duplicate `vintage` when Source already represents it.

## 20. Temporality

Distinguish real-world validity time from source/observation time. Git
history is not a substitute for explicit validity.

## 21. Geometry History

A Division may retain identity while geometry changes. Store multiple
temporal geometry versions without changing stable Division identity.

## 22. External Identifiers

Treat Census identifiers as external, source-specific identifiers and
preserve leading zeros. Keep OCD identity distinct.

## 23. URLs Are Enrichment

Missing official websites must not invalidate otherwise valid Jurisdictions.
Website resolution is a separate enrichment concern.

## 24. Special Districts

Do not assume a Census government record has a TIGER polygon. Never
fabricate GEOIDs. Special districts may use other authoritative geometry
providers and may initially remain unresolved geographically.

## 25. YAML Is Canonical

Version-controlled YAML is the durable source of truth. Graph databases,
relational stores, search indexes, and APIs must be rebuildable from YAML.

## 26. Graph Semantics

The model should project naturally to nodes such as Jurisdiction, Division,
Source, GeometryVersion, and ExternalIdentifier, with edges such as
GOVERNS, PARENT_OF, SERVES, OVERLAPS, CONTAINED_BY, HAS_GEOMETRY,
IDENTIFIED_BY, and SOURCED_FROM.

## 27. Dependency Direction

Keep dependencies approximately one-way:

```
sources → normalize → resolution → ocdid → canonical models → validation / rendering
```

Rendering must not contain resolution logic. Model validation must not
perform network requests.

## 28. Processing Status

Every input government must end in a structured terminal status such as
`COMPLETE`, `NO_GEOGRAPHY`, `NEW_OCDID`, `AMBIGUOUS_OCDID`,
`DIVISION_NOT_FOUND`, or `SOURCE_ERROR`.

## 29. Sample Output Is a Pipeline Contract

`tests/sample_output/` is a golden integration contract. Per root
`AGENTS.md`, agents do not have permission to change data in
`tests/sample_output/`.

The rewritten pipeline is not considered working until it can regenerate the
expected sample outputs from controlled fixture inputs.

Where models remain semantically unchanged, expected values should remain
unchanged. Where models intentionally change, fixture structure may change
only after explicit migration, verification, and review.

## 30. Golden-File Integration Testing

Controlled source fixtures must run through the real internal pipeline and
generate temporary output that is compared against checked-in golden files.

Tests must never mutate expected sample output automatically.

## 31. Controlled Integration Inputs

Maintain local fixture inputs for Census Governments, TIGER, OCD master, and
relevant sources. Normal golden tests must not depend on live external
endpoints.

## 32. Determinism

Identical fixtures, rules, exceptions, source metadata, and code must yield
identical output. Freeze or inject timestamps where required.

## 33. Existing Sample Values Are a Baseline

Inventory all existing sample output from `main`. Do not update expected
fixtures merely to make tests pass. Investigate differences.

## 34. Model Changes and Sample Migration

Document structural fixture migrations and preserve semantic values where
possible. Verify factual changes against authoritative sources.

## 35. Classify Sample Changes

Classify material changes as `STRUCTURAL`, `SOURCE_CORRECTION`, `BUG_FIX`,
`TEMPORAL_UPDATE`, `IDENTIFIER_MIGRATION`, `EXPECTED_NEW_FIELD`, or
`REGRESSION`.

## 36. Sample Coverage

Golden fixtures should cover representative states, counties, municipalities,
MCDs where relevant, school districts, OCD exceptions, special districts,
temporal geometry, new-OCDID quarantine, and unresolved geography.

## 37. Quarantine Golden Tests

Expected unresolved behavior should also be golden-tested.

## 38. Stable Identity Regression

Tests must prove mutable facts do not change UUID identity.

## 39. Fixture Regeneration

Provide an explicit maintainer command to regenerate sample output. Test
execution must never do this implicitly.

## 40. CI

Golden-output integration tests must run in CI and fail on unexplained
output drift.

## 41. Coding-Agent Working Rules

When making changes:

1. Inspect corresponding code on `main` first.
2. Search for existing helpers before creating new ones.
3. Inspect relevant golden fixtures before changing behavior.
4. Preserve useful tests and fixtures.
5. Add tests for behavioral changes.
6. Prefer small architectural seams over massive one-shot rewrites.
7. Keep generated output separate from handwritten rules/configuration.
8. Do not manually repair generated YAML when reusable logic can solve the issue.
9. Do not silently downgrade provenance.
10. Do not introduce network access into model validation or rendering.
11. Do not auto-create canonical IDs from fuzzy matches.
12. Document intentional incompatibilities.
13. Run comparisons against `main` throughout the rework.
14. Never update golden files merely because a test failed.
15. Classify and verify material fixture changes.
16. Keep golden integration green as stages are replaced.
17. Flag any change that conflicts with or requires updating root `AGENTS.md`.

## 42. Preferred Migration Style

Avoid a big-bang rewrite. Progressively replace:

```
sample integration harness → source layer → normalized representation
  → resolver → OCDID engine → canonical models → renderer.
```

Delete legacy code only after its replacement exists, tests cover it, domain
knowledge is salvaged, and fixture behavior is understood.

## 43. Definition of Done

The rework is complete when:

- GUS/Census Government data can be ingested as the government universe.
- Supported governments resolve deterministically to appropriate TIGER Divisions.
- OCD candidates are generated by reusable rules.
- Existing canonical OCDIDs are preserved.
- Unknown OCDIDs are quarantined.
- Existing exception knowledge is salvaged or intentionally replaced.
- Models represent stable identity and temporal facts.
- Source objects represent release/vintage provenance.
- Geometry can be retrieved without local GIS infrastructure.
- YAML is reproducible from source snapshots.
- Every input government has a terminal status.
- Graph databases remain downstream projections.
- Normal tests run offline.
- Unchanged inputs generate zero output diff.
- Controlled fixtures regenerate `tests/sample_output/`.
- Golden drift is explicitly reviewed.

## References

- Root policy: `AGENTS.md`
- Design reference (PDF): `docs/rework/openstates-jurisdictions-data-pipeline.pdf`
- Design reference (text): `docs/rework/openstates-jurisdictions-data-pipeline.md`
- Phased plan: `ai_tools/planning/census-pipeline-rework-plan.md`
- Generic (superseded on this branch): `ai_tools/tasks/feature-delivery.instruction.md`
