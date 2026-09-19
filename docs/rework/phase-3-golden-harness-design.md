---
id: phase-3-golden-harness-design
type: design
owner: rework
status: draft
last_updated: 2026-09-12
tags: [rework, phase-3, golden, testing, harness, design]
task: "Phase 3 — Golden Sample Integration Harness (issue #134)"
scope: design for the golden harness on branch 131-gus-pipeline-rework
---

# Phase 3 — Golden Sample Integration Harness (Design)

Design contract for issue #134. Implementation targets base branch
`131-gus-pipeline-rework` (not `main`). New `tests/integration/` files
require maintainer approval per root `AGENTS.md`.

## 1. Objective

Build a reusable golden-comparison harness: a runner that renders records
into a temporary directory behind a pluggable pipeline seam, and a semantic
comparison engine that reports the exact file and field where two YAML trees
differ. An explicit, maintainer-only command regenerates the golden tree; no
test ever mutates it.

The harness makes drift **visible**, not green. The Census-first pipeline
(Phases 4–10) does not exist yet, and the checked-in golden tree predates the
Phase 2 model changes (see §3). Per the rework plan's Sample Output Change
Control, a non-empty diff against golden after Phase 2 is the **expected**
state and the signal that Phase 11 regeneration is due — it is not a failure
to patch. The harness therefore proves itself with unit tests on synthetic
trees and with model-level golden tests; it does not assert "no diff" against
the checked-in golden tree.

## 2. Scope

In scope for this phase:

- Task 3.1 — Controlled fixture layout.
- Task 3.3 — Temporary output runner behind a pluggable seam (never mutates
  golden).
- Task 3.4 — Semantic / YAML comparison engine.
- Task 3.5 — Explicit, maintainer-only regeneration command (a drift
  diagnostic today; the real renderer and golden regeneration are Phase 10
  and Phase 11).
- Task 3.7 — Stable identity golden test (model-level).
- Task 3.8 — Temporal geometry golden test (model-level).

Deferred until upstream stages exist:

- Task 3.2 — Full input-to-golden mapping (needs the Phase 4–10 pipeline).
- Task 3.6 — Quarantine fixture (needs Phase 8 validation/quarantine).

Out of scope and reported as work-items, not fixed here (see §9):

- The stale golden tree (Phase 11 regenerates it, with maintainer approval).
- The broken jurisdiction fixture module (a Phase 2 follow-up).

## 3. Findings that shape this design

Verified empirically on `131-gus-pipeline-rework` at commit `c6e8e4c`:

1. **The golden tree is stale relative to the Phase 2 models.** Re-serializing
   the six division fixtures and diffing against
   `tests/sample_output/divisions/` shows drift in every record:
   `government_identifiers` (golden is the old flat dict; the model now uses a
   list of `Identifier` — Task 2.4), `geometries` (golden uses
   `arcGIS_address`/`start`/`end`; the model now uses
   `url`/`valid_from`/`valid_to`/`source` — Task 2.3), and `sourcing`
   (Task 2.2). This is exactly the post-Phase-2 drift the plan anticipates.
2. **No current code reproduces the golden layout.** Golden paths are
   `divisions/test/<state>/local/<slug>_<uuid>.yaml`; `Division.dump_division`
   writes flat `"<display name> <geoid> <uuid>.yaml"`. File naming and path
   policy is Phase 10 (Task 10.2), not Phase 3.
3. **The jurisdiction fixture module does not import under the current model.**
   `tests/fixtures/jurisdictions_sample.py` raises `ValidationError` building
   `MARIN_CITY_CSD_JURISDICTION` (ocdid suffix `governing_board` does not match
   classification `special_purpose_district`). No active test imports it, so
   the suite still passes; the harness must not depend on it.

Consequence: the harness cannot and must not be wired to "reproduce the golden
tree and go green." It renders records to a temp dir, compares trees
semantically, and surfaces drift for review.

## 4. Architecture

```text
records (model objects, injected)
        |  GoldenRunner.run(records, output_dir)   [seam]
        v
tmp/**.yaml            actual output (temp dir; golden never touched)
        |  compare_trees(expected_dir, actual_dir)
        v
list[Diff]             file + field-path differences
```

The comparison engine is the durable asset and is independent of the pipeline.
The runner is a thin seam: today a `FixtureRunner` dumps injected model
objects; later phases provide a `PipelineRunner` implementing the same
Protocol without touching the comparison layer.

## 5. File layout

`tests/` uses implicit namespace packages (no `__init__.py`); new modules
follow that. Support modules are not named `test_*` so pytest does not collect
them as tests.

```text
tests/golden/
  runner.py                          # GoldenRunner Protocol, RunResult, FixtureRunner
  compare.py                         # Diff, compare_trees()
  regenerate.py                      # maintainer-only CLI: python -m tests.golden.regenerate
  records.py                         # small set of VALID model records for harness tests
  test_compare.py                    # unit tests (offline, fast)
  test_runner.py                     # unit tests (offline, fast)

tests/fixtures/
  README.md                          # input formats + mapping convention (Task 3.2)
  census_governments/  tiger/  ocd_master/  sources/    # created now, populated later

tests/integration/
  test_golden_stable_identity.py     # Task 3.7 (model-level)
  test_golden_temporal_geometry.py   # Task 3.8 (model-level)
```

`tests/golden/test_*.py` are fast offline unit tests. The two golden
behaviours live in `tests/integration/` with the `integration` marker and
need maintainer approval before merge.

## 6. Components

### 6.1 GoldenRunner seam (`runner.py`)

```python
class GoldenRunner(Protocol):
    def run(self, output_dir: Path) -> RunResult: ...
```

`RunResult` is a dataclass recording division and jurisdiction paths written
and per-record counts. Count fields leave room for the spec §27 pipeline
statuses once resolution and quarantine exist.

`FixtureRunner` is the initial implementation. It is constructed with explicit
lists of `Division` and `Jurisdiction` objects (injected, not imported from
the broken fixture module) and dumps each into `output_dir` using the models'
own `dump_division` / `dump_jurisdiction`. It adds no serialization logic and
never writes outside `output_dir`.

### 6.2 Semantic comparison (`compare.py`)

`compare_trees(expected_dir, actual_dir) -> list[Diff]`:

- Match files by path relative to their root; emit a `Diff` for each missing
  and each extra file.
- Parse each matched pair with `yaml.safe_load` and compare structurally:
  mapping keys order-insensitive, sequences order-significant.
- Emit a `Diff` for each value mismatch, missing key, extra key, and type
  mismatch, each with a dotted field path.

`Diff` fields: `file` (relative path), `path` (dotted field path or empty),
`kind` (`VALUE_MISMATCH`, `MISSING_FILE`, `EXTRA_FILE`, `MISSING_KEY`,
`EXTRA_KEY`, `TYPE_MISMATCH`), `expected`, `actual`.

Comparison is strict on every field with no masking of volatile fields.
Rationale: the rework's goal is deterministic, reproducible output (design
§18–19; plan Global Success Criteria 9 and 12). Comparison is semantic
(parsed structure), so formatting differences do not cause false diffs;
byte-identical output is a separate Phase 10 concern.

### 6.3 Controlled fixture layout (`tests/fixtures/`)

Create the four input directories now, with a `README.md` documenting the
intended source-shaped file formats and the input-to-golden mapping
convention. Population is Task 3.2, deferred.

### 6.4 Regeneration CLI (`regenerate.py`)

`uv run python -m tests.golden.regenerate [--yes]`. It runs the current
`GoldenRunner` into a temp dir, prints a `compare_trees` drift summary against
`tests/sample_output/`, and lists every file it would add, overwrite, or
remove. It writes into `tests/sample_output/` only with `--yes`, behind a
banner stating maintainer approval is required. No test imports or invokes it;
it never runs during `pytest`. Today it is a drift diagnostic; once Phase 10
lands a real renderer, the same command regenerates golden for Phase 11.

### 6.5 Valid harness records (`records.py`)

A small module exposing valid `Division` and `Jurisdiction` objects built
inline (correct ocdid/classification pairing, explicit `last_updated`). Used
by the runner unit tests and the model-level golden tests, so the harness
never depends on the stale golden tree or the broken jurisdiction fixture.

## 7. Golden tests (model-level)

### 7.1 Stable identity (Task 3.7, `test_golden_stable_identity.py`)

Build a division from `records.py`, mutate a mutable fact without changing the
OCD ID, rebuild, and assert the UUID (`id`) is unchanged.

Current UUID derivation is `uuid5(NAMESPACE_URL, f"{ocdid}|{last_updated_date}")`.
Consequences:

- Change display name, geometry, or sourcing (leave `last_updated` untouched):
  UUID stable. Green now.
- Change the retrieval date (`last_updated`): UUID changes today. This
  violates design §18 and is Phase 2 Task 2.1 (Stable UUID), still open.

The retrieval-date-invariance case is written as
`xfail(strict=True, reason="blocked on #133 Task 2.1 — stable UUID")`. It
states the target contract, keeps the suite honest and green, and flips to a
real failure when Task 2.1 lands. This follows the `AGENTS.md` "never fake it"
rule.

### 7.2 Temporal geometry (Task 3.8, `test_golden_temporal_geometry.py`)

Phase 2 Task 2.3 is merged. Build a division with two geometry periods
(`valid_from`/`valid_to`, each with a `SourceObj`), serialize with
`model_dump(mode="json")`, and assert both periods and their provenance are
present and the division UUID is stable. Green now.

## 8. Testing strategy

- Unit tests (`tests/golden/test_*.py`): offline, fast, not `integration`.
  Cover `compare_trees` (value mismatch, missing key, extra file, list-order
  difference) and `FixtureRunner` (writes the expected file set into a temp
  dir; never writes elsewhere).
- Integration tests (`tests/integration/test_golden_*.py`): marked
  `integration`, offline. Cover the two model-level golden behaviours. These
  files need maintainer approval before merge.
- The default developer run stays fast:
  `uv run pytest -m "not integration and not slow"`. Golden integration runs
  under `-m integration`, which Phase 12 wires into CI.
- No asserting test targets the checked-in golden tree; that tree is touched
  only by the regenerate CLI (maintainer diagnostic/tool).

## 9. Coordination and work-items

- New `tests/integration/` files need maintainer approval. This design doc
  accompanies that request.
- Report as separate work-items (not fixed here):
  - `tests/fixtures/jurisdictions_sample.py` fails to import under the current
    jurisdiction model (§3, finding 3).
  - The golden tree is stale versus Phase 2 (§3, finding 1); regeneration is
    Phase 11 (#142) and needs a maintainer.
- Task 3.7's retrieval-date case depends on Phase 2 Task 2.1 (#133); remove
  the `xfail` when 2.1 merges.
- Task 3.2 and Task 3.6 are deferred; the fixture layout and seam are designed
  so both drop in without reworking the comparison layer.

## 10. Out of scope

- Implementing any Phase 4–10 pipeline stage or renderer.
- Changing `src/models/` contracts (Task 2.1 belongs to Phase 2).
- Editing or regenerating any file under `tests/sample_output/`.
- Repairing `tests/fixtures/jurisdictions_sample.py` (reported as a work-item).
- Byte-identical serialization guarantees (Phase 10, Task 10.1).
