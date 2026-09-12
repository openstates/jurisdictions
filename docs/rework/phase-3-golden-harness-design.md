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

Build a reusable golden-comparison harness that runs controlled inputs
through a pipeline seam, renders YAML into a temporary directory, and
compares that output against the checked-in golden contract in
`tests/sample_output/`. The harness never mutates golden files; only an
explicit maintainer command regenerates them.

The Census-first pipeline (Phases 4–10) does not exist yet, so the seam is
pluggable. Today it is wired to the existing model-fixture path, which makes
the suite green now. Later phases implement the same seam interface without
changing the comparison layer.

## 2. Scope

In scope for this phase:

- Task 3.1 — Controlled fixture layout.
- Task 3.3 — Temporary output runner (never mutates golden).
- Task 3.4 — Semantic / YAML comparison.
- Task 3.5 — Explicit fixture regeneration command.
- Task 3.7 — Stable identity golden test.
- Task 3.8 — Temporal geometry golden test.

Deferred until upstream stages exist:

- Task 3.2 — Full input-to-golden mapping (needs the Phase 4–10 pipeline).
- Task 3.6 — Quarantine fixture (needs Phase 8 validation/quarantine).

## 3. Constraints (root `AGENTS.md`)

- `tests/sample_output/` is an immutable golden contract. Tests never write
  it. It is regenerated only by an explicit maintainer command, never
  autonomously, and never patched to make a failing test pass.
- New `tests/integration/` files require maintainer approval.
- Test-driven development; never fake a pass. A failing golden test is a
  signal, not a fixture to correct.
- Prefer mocked network boundaries. The harness runs fully offline.
- Reuse existing modules before adding abstractions. The runner reuses the
  existing sample fixtures and the models' own dump methods.
- Use `src` package-root imports. Parse OCD IDs with
  `OCDIdParsed.parse_ocdid()` where parsing is needed.

## 4. Architecture

```text
tests/fixtures/*_sample.py        deterministic model objects (existing)
        |  GoldenRunner.run(output_dir)   [seam]
        v
tmp/{divisions,jurisdictions}/**.yaml     actual output
        |  compare_trees(expected=tests/sample_output, actual=tmp)
        v
list[Diff]        empty  -> pass
                  non-empty -> fail (file + field path)
```

The seam decouples "how output is produced" from "how output is verified".
The comparison layer is the durable contract; the runner behind the seam is
replaced as the rework progresses.

## 5. File layout

```text
tests/golden/
  __init__.py
  runner.py                       # GoldenRunner protocol, RunResult, ModelFixtureRunner
  compare.py                      # Diff, compare_trees()
  regenerate.py                   # maintainer-only CLI: python -m tests.golden.regenerate
  test_runner.py                  # unit tests (offline, fast)
  test_compare.py                 # unit tests (offline, fast)

tests/fixtures/
  README.md                       # documents input formats + mapping convention (Task 3.2)
  census_governments/             # created now, populated later
  tiger/
  ocd_master/
  sources/

tests/integration/
  test_golden_harness.py          # end-to-end: seam -> compare -> assert no diffs
  test_golden_stable_identity.py  # Task 3.7
  test_golden_temporal_geometry.py# Task 3.8
```

`tests/golden/` holds harness support code plus its own fast unit tests.
The end-to-end golden tests live in `tests/integration/` and carry the
`integration` marker.

## 6. Components

### 6.1 GoldenRunner seam (`runner.py`)

A `Protocol` defining the interface later phases implement:

```python
class GoldenRunner(Protocol):
    def run(self, output_dir: Path) -> RunResult: ...
```

`RunResult` is a dataclass recording what was produced: the division and
jurisdiction paths written, and per-record counts. The count fields leave
room for the spec §27 pipeline statuses (COMPLETE, NO_GEOGRAPHY, and so on)
once resolution and quarantine exist.

### 6.2 ModelFixtureRunner (`runner.py`)

The initial seam implementation. It imports the existing object lists from
`tests/fixtures/divisions_sample.py` and
`tests/fixtures/jurisdictions_sample.py` and dumps each record into
`output_dir` using the models' own `dump_division(base_dir=...)` and
`dump_jurisdiction(base_dir=...)`. This reproduces exactly the tree under
`tests/sample_output/`. It adds no new serialization logic.

### 6.3 Semantic comparison (`compare.py`)

`compare_trees(expected_dir, actual_dir) -> list[Diff]`:

- Walk both trees; match files by path relative to their root.
- Report a `Diff` for each missing file and each extra file.
- For each matched pair, parse both with `yaml.safe_load` and compare
  structurally.
  - Mapping keys: order-insensitive.
  - Sequences: order-significant (deterministic output preserves list order).
  - Report a `Diff` for each value mismatch, missing key, extra key, and
    type mismatch, with the dotted field path.

`Diff` fields: `file` (relative path), `path` (dotted field path or empty),
`kind` (`VALUE_MISMATCH`, `MISSING_FILE`, `EXTRA_FILE`, `MISSING_KEY`,
`EXTRA_KEY`, `TYPE_MISMATCH`), `expected`, `actual`.

Comparison is **strict on every field with no masking of volatile fields.**
Rationale: the rework's goal is deterministic, reproducible output (design
§18–19; plan Global Success Criteria 9 and 12). Any nondeterminism is a
real defect the harness must surface, not hide. Comparison is semantic
(parsed structure), so YAML formatting differences do not cause false
failures; byte-identical output is a separate Phase 10 concern.

### 6.4 Controlled fixture layout (`tests/fixtures/`)

Create the four input directories now, with a `README.md` documenting the
intended file formats (source-shaped CSV or JSON) and the input-to-golden
mapping convention. Full population is Task 3.2, deferred until the pipeline
stages that consume these inputs exist.

### 6.5 Regeneration CLI (`regenerate.py`)

Invoked as `uv run python -m tests.golden.regenerate [--yes]`.

- Runs the current `GoldenRunner` into a temporary directory.
- Prints a diff summary against `tests/sample_output/` and lists every file
  it would add, overwrite, or remove.
- Writes into `tests/sample_output/` only when `--yes` is passed.
- Prints a banner: overwriting the golden contract requires maintainer
  approval.
- No test imports or invokes it. It never runs during `pytest`.

## 7. Golden tests

### 7.1 Harness end-to-end (`test_golden_harness.py`)

Run `ModelFixtureRunner` into `tmp_path`, call `compare_trees` against
`tests/sample_output/`, and assert the diff list is empty. This proves the
seam, the comparison, and the current golden contract agree. Green today.

### 7.2 Stable identity (Task 3.7, `test_golden_stable_identity.py`)

Build a division from a fixture, mutate a mutable fact without changing the
OCD ID, rebuild, and assert the UUID (`id`) is unchanged.

Current UUID derivation is `uuid5(NAMESPACE_URL, f"{ocdid}|{last_updated_date}")`
(`src/models/division.py`). Consequences:

- Change website, source, or geometry (leave `last_updated` untouched):
  UUID is stable. These cases are **green now**.
- Change the retrieval date (`last_updated`): UUID changes today. This
  violates design §18 and is exactly Phase 2 Task 2.1 (Stable UUID), which
  is not yet done (#133).

The retrieval-date-invariance case is written as
`xfail(strict=True, reason="blocked on #133 Task 2.1 — stable UUID")`.
It encodes the target contract, keeps the suite honest and green, and flips
to a real failure the moment Task 2.1 lands — signalling that the xfail
should be removed. This follows the `AGENTS.md` "never fake it" rule: the
contract is stated, not the code bent to pass.

### 7.3 Temporal geometry (Task 3.8, `test_golden_temporal_geometry.py`)

Phase 2 Task 2.3 (geometry temporality) is merged. Build a division with two
geometry periods (`valid_from`/`valid_to`, each with a Source), serialize,
and assert both periods and their provenance are present and the division
UUID is stable. Green today.

## 8. Testing strategy

- Unit tests (`tests/golden/test_*.py`): offline, fast, not marked
  `integration`. They cover `compare_trees` (value mismatch, missing key,
  extra file, list-order difference) and `ModelFixtureRunner` (writes the
  expected file set into a temp directory).
- Integration tests (`tests/integration/test_golden_*.py`): marked
  `integration`, offline. They exercise the full seam-to-comparison path and
  the two golden behaviours. These files need maintainer approval before
  merge.
- The default developer run stays fast:
  `uv run pytest -m "not integration and not slow"`. Golden integration runs
  under `-m integration`, which Phase 12 wires into CI.

## 9. Coordination and open items

- New `tests/integration/` files need maintainer approval. This design doc is
  the proposal to accompany that request.
- Task 3.7's retrieval-date case depends on Phase 2 Task 2.1 (owned within
  #133). Coordinate removal of the `xfail` when Task 2.1 merges.
- Task 3.2 and Task 3.6 are deferred; the fixture layout and the seam are
  designed so both drop in without reworking the comparison layer.

## 10. Out of scope

- Implementing any Phase 4–10 pipeline stage.
- Changing `src/models/` contracts (Task 2.1 belongs to Phase 2).
- Editing any file under `tests/sample_output/`.
- Byte-identical serialization guarantees (Phase 10, Task 10.1).
