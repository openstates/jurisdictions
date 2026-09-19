# Phase 3 Golden Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a drift-visible golden-comparison harness — a semantic YAML comparison engine, a temporary-output runner behind a pluggable pipeline seam, a controlled fixture layout, a maintainer-only regeneration diagnostic, and model-level golden tests for stable identity and temporal geometry.

**Architecture:** A pure comparison engine (`compare_trees`) diffs two YAML trees by file and field. A `GoldenRunner` Protocol renders injected records into a temp directory; `FixtureRunner` is today's implementation. Golden tests assert model-level invariants from valid inline records, never against the stale checked-in golden tree. Design: `docs/rework/phase-3-golden-harness-design.md`.

**Tech Stack:** Python 3.12, pydantic v2, PyYAML, pytest, `uv`.

## Global Constraints

- Base branch is `131-gus-pipeline-rework`; do not target or merge to `main`.
- Never write to, regenerate, or hand-edit `tests/sample_output/` (root `AGENTS.md`). Only the regenerate CLI may, and only with `--yes`; its `main()` refuses to apply until Phase 10.
- New `tests/integration/` files need maintainer approval before merge (Tasks 6, 7).
- TDD; never fake a pass. Do not patch a fixture or golden file to make a test green.
- Do not run any `git push` without explicit user authorization.
- Do not hide test output (no `2>&1`, no tail-only logs) when debugging.
- Use `uv run` for all Python commands. Use `src`-root imports (`from src.models... import`). Parse OCD IDs only via `OCDIdParsed.parse_ocdid()`.
- `tests/` uses implicit namespace packages — do not add `__init__.py`. `tests/conftest.py` already puts the repo root on `sys.path`.
- Unit test files are fast and offline (not `integration`-marked); they mirror the harness modules under `tests/golden/`.

---

### Task 1: Semantic comparison engine

**Files:**
- Create: `tests/golden/compare.py`
- Test: `tests/golden/test_compare.py`

**Interfaces:**
- Consumes: nothing (pure; stdlib + `yaml`).
- Produces:
  - `Diff` dataclass: `file: str`, `path: str`, `kind: str`, `expected`, `actual`. `kind` ∈ {`VALUE_MISMATCH`, `MISSING_FILE`, `EXTRA_FILE`, `MISSING_KEY`, `EXTRA_KEY`, `TYPE_MISMATCH`}.
  - `compare_trees(expected_dir: Path, actual_dir: Path) -> list[Diff]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/golden/test_compare.py
from pathlib import Path

import yaml

from tests.golden.compare import compare_trees


def _write(root: Path, rel: str, data) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data))


def test_identical_trees_have_no_diffs(tmp_path):
    exp, act = tmp_path / "exp", tmp_path / "act"
    _write(exp, "a/x.yaml", {"k": 1, "n": {"a": "01"}})
    _write(act, "a/x.yaml", {"n": {"a": "01"}, "k": 1})  # key order differs
    assert compare_trees(exp, act) == []


def test_value_mismatch_reports_field_path(tmp_path):
    exp, act = tmp_path / "exp", tmp_path / "act"
    _write(exp, "x.yaml", {"geoid": "0645820"})
    _write(act, "x.yaml", {"geoid": "645820"})
    diffs = compare_trees(exp, act)
    assert len(diffs) == 1
    d = diffs[0]
    assert (d.file, d.path, d.kind) == ("x.yaml", "geoid", "VALUE_MISMATCH")
    assert d.expected == "0645820" and d.actual == "645820"


def test_missing_and_extra_keys(tmp_path):
    exp, act = tmp_path / "exp", tmp_path / "act"
    _write(exp, "x.yaml", {"a": 1, "b": 2})
    _write(act, "x.yaml", {"a": 1, "c": 3})
    seen = {(d.kind, d.path) for d in compare_trees(exp, act)}
    assert ("MISSING_KEY", "b") in seen
    assert ("EXTRA_KEY", "c") in seen


def test_missing_and_extra_files(tmp_path):
    exp, act = tmp_path / "exp", tmp_path / "act"
    _write(exp, "only_expected.yaml", {"a": 1})
    _write(act, "only_actual.yaml", {"a": 1})
    seen = {(d.kind, d.file) for d in compare_trees(exp, act)}
    assert ("MISSING_FILE", "only_expected.yaml") in seen
    assert ("EXTRA_FILE", "only_actual.yaml") in seen


def test_list_order_is_significant(tmp_path):
    exp, act = tmp_path / "exp", tmp_path / "act"
    _write(exp, "x.yaml", {"xs": [1, 2, 3]})
    _write(act, "x.yaml", {"xs": [1, 3, 2]})
    assert any(d.kind == "VALUE_MISMATCH" for d in compare_trees(exp, act))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/golden/test_compare.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tests.golden.compare'`.

- [ ] **Step 3: Write the implementation**

```python
# tests/golden/compare.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Diff:
    file: str
    path: str
    kind: str
    expected: Any = None
    actual: Any = None


def _yaml_files(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*.yaml")}


def _child(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _compare_values(file: str, path: str, expected: Any, actual: Any) -> list[Diff]:
    if type(expected) is not type(actual):
        return [Diff(file, path, "TYPE_MISMATCH", expected, actual)]
    if isinstance(expected, dict):
        diffs: list[Diff] = []
        for key in expected:
            if key not in actual:
                diffs.append(Diff(file, _child(path, key), "MISSING_KEY", expected[key], None))
            else:
                diffs.extend(_compare_values(file, _child(path, key), expected[key], actual[key]))
        for key in actual:
            if key not in expected:
                diffs.append(Diff(file, _child(path, key), "EXTRA_KEY", None, actual[key]))
        return diffs
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return [Diff(file, path, "VALUE_MISMATCH", expected, actual)]
        diffs = []
        for i, (e, a) in enumerate(zip(expected, actual)):
            diffs.extend(_compare_values(file, f"{path}[{i}]", e, a))
        return diffs
    if expected != actual:
        return [Diff(file, path, "VALUE_MISMATCH", expected, actual)]
    return []


def compare_trees(expected_dir: Path, actual_dir: Path) -> list[Diff]:
    expected_dir, actual_dir = Path(expected_dir), Path(actual_dir)
    expected_files, actual_files = _yaml_files(expected_dir), _yaml_files(actual_dir)
    diffs: list[Diff] = []
    for rel in sorted(expected_files - actual_files):
        diffs.append(Diff(rel, "", "MISSING_FILE"))
    for rel in sorted(actual_files - expected_files):
        diffs.append(Diff(rel, "", "EXTRA_FILE"))
    for rel in sorted(expected_files & actual_files):
        expected_doc = yaml.safe_load((expected_dir / rel).read_text())
        actual_doc = yaml.safe_load((actual_dir / rel).read_text())
        diffs.extend(_compare_values(rel, "", expected_doc, actual_doc))
    return diffs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/golden/test_compare.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Lint**

Run: `uv run ruff check tests/golden/compare.py tests/golden/test_compare.py`
Expected: All checks passed.

- [ ] **Step 6: Commit**

```bash
git add tests/golden/compare.py tests/golden/test_compare.py
git commit -m "[Rework] Phase 3.4 — Semantic YAML comparison engine (#134)" \
  -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Controlled fixture layout

**Files:**
- Create: `tests/fixtures/README.md`
- Create: `tests/fixtures/census_governments/.gitkeep`, `tests/fixtures/tiger/.gitkeep`, `tests/fixtures/ocd_master/.gitkeep`, `tests/fixtures/sources/.gitkeep`

**Interfaces:**
- Consumes: nothing.
- Produces: the directory contract later phases (Task 3.2, Phases 4–8) populate. No code imports it yet.

- [ ] **Step 1: Create the directories with tracked placeholders**

Run:
```bash
mkdir -p tests/fixtures/census_governments tests/fixtures/tiger tests/fixtures/ocd_master tests/fixtures/sources
touch tests/fixtures/census_governments/.gitkeep tests/fixtures/tiger/.gitkeep tests/fixtures/ocd_master/.gitkeep tests/fixtures/sources/.gitkeep
```

- [ ] **Step 2: Write the README**

```markdown
<!-- tests/fixtures/README.md -->
# Golden harness input fixtures

Controlled, offline inputs for the Phase 3 golden harness (issue #134).
Each directory holds source-shaped fixtures for one adapter. They are
populated as the upstream pipeline stages land; today the harness runs on
inline model records (`tests/golden/records.py`).

## Directories

- `census_governments/` — Census Government Units Survey rows (Phase 4.1).
- `tiger/` — TIGER metadata rows for state/county/place/county-subdivision/
  school-district (Phase 4.2).
- `ocd_master/` — OCD master membership samples for exact-match lookup
  (Phase 4.3).
- `sources/` — `SourceObj` provenance fixtures shared across the above.

## Input-to-golden mapping (Task 3.2, deferred)

When the Phase 4–10 pipeline exists, every golden record under
`tests/sample_output/` maps back to a controlled input here, so the golden
tree is reproducible offline. Until then this layout only reserves the
contract; do not wire it into tests.

## Rules

- Fixtures are read-only inputs. Never regenerate `tests/sample_output/` from
  a test (root `AGENTS.md`).
- Keep fixtures minimal and human-readable; prefer the real source column
  names so adapters can be tested against realistic shapes.
```

- [ ] **Step 3: Verify the layout is tracked by git**

Run: `git add tests/fixtures && git status --short tests/fixtures`
Expected: five new files listed (README.md + four `.gitkeep`).

- [ ] **Step 4: Commit**

```bash
git commit -m "[Rework] Phase 3.1 — Controlled fixture layout + README (#134)" \
  -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Valid harness records

**Files:**
- Create: `tests/golden/records.py`
- Test: `tests/golden/test_records.py`

**Interfaces:**
- Consumes: `src.models.division` (`Division`, `Geometry`, `Boundary`, `Identifier`), `src.models.jurisdiction` (`Jurisdiction`, `ClassificationEnum`), `src.models.source` (`SourceObj`, `SourceType`).
- Produces:
  - `FIXED_TS: datetime`, `DIVISION_OCDID: str`, `JURISDICTION_OCDID: str`.
  - `make_source(field: list[str], name: str = ...) -> SourceObj`
  - `make_geoid_identifier(value: str = "5363000") -> Identifier`
  - `make_geometry(valid_from: datetime | None, valid_to: datetime | None) -> Geometry`
  - `make_division(*, ocdid=..., display_name=..., last_updated=..., geometries=None, geoid="5363000") -> Division`
  - `make_jurisdiction(*, ocdid=..., classification=ClassificationEnum.GOVERNMENT, name=..., last_updated=...) -> Jurisdiction`

- [ ] **Step 1: Write the failing test**

```python
# tests/golden/test_records.py
from tests.golden.records import make_division, make_jurisdiction


def test_records_build_and_have_stable_ids():
    division = make_division()
    jurisdiction = make_jurisdiction()
    assert division.id is not None
    assert jurisdiction.id is not None
    # Rebuilding the same record yields the same UUID (deterministic identity).
    assert make_division().id == division.id
    assert make_jurisdiction().id == jurisdiction.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/golden/test_records.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tests.golden.records'`.

- [ ] **Step 3: Write the implementation**

```python
# tests/golden/records.py
from __future__ import annotations

from datetime import datetime, timezone

from src.models.division import Boundary, Division, Geometry, Identifier
from src.models.jurisdiction import ClassificationEnum, Jurisdiction
from src.models.source import SourceObj, SourceType

FIXED_TS = datetime(2025, 10, 27, 1, 29, 51, tzinfo=timezone.utc)
DIVISION_OCDID = "ocd-division/country:us/state:wa/place:seattle"
JURISDICTION_OCDID = "ocd-jurisdiction/country:us/state:wa/place:seattle/government"


def make_source(field: list[str], name: str = "Census TIGER/Line") -> SourceObj:
    return SourceObj(
        field=field,
        source_name=name,
        source_type=SourceType.HUMAN,
        source_url="https://www.census.gov/",
        source_description=None,
    )


def make_geoid_identifier(value: str = "5363000") -> Identifier:
    return Identifier(
        authority="census",
        id_type="geoid",
        value=value,
        source=make_source(["government_identifiers"]),
    )


def make_geometry(
    valid_from: datetime | None, valid_to: datetime | None
) -> Geometry:
    return Geometry(
        valid_from=valid_from,
        valid_to=valid_to,
        boundary=Boundary(),
        url="https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer/5/query?f=geojson",
        source=make_source(["geometries"]),
    )


def make_division(
    *,
    ocdid: str = DIVISION_OCDID,
    display_name: str = "Seattle",
    last_updated: datetime = FIXED_TS,
    geometries: list[Geometry] | None = None,
    geoid: str = "5363000",
) -> Division:
    return Division(
        ocdid=ocdid,
        country="us",
        display_name=display_name,
        geometries=geometries if geometries is not None else [make_geometry(None, None)],
        government_identifiers=[make_geoid_identifier(geoid)],
        sourcing=[make_source(["geometries"])],
        jurisdiction_id=JURISDICTION_OCDID,
        accurate_asof=last_updated,
        last_updated=last_updated,
    )


def make_jurisdiction(
    *,
    ocdid: str = JURISDICTION_OCDID,
    classification: ClassificationEnum = ClassificationEnum.GOVERNMENT,
    name: str = "Seattle City Government",
    last_updated: datetime = FIXED_TS,
) -> Jurisdiction:
    return Jurisdiction(
        ocdid=ocdid,
        name=name,
        classification=classification,
        accurate_asof=last_updated,
        last_updated=last_updated,
        metadata={"urls": []},
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/golden/test_records.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Lint**

Run: `uv run ruff check tests/golden/records.py tests/golden/test_records.py`
Expected: All checks passed.

- [ ] **Step 6: Commit**

```bash
git add tests/golden/records.py tests/golden/test_records.py
git commit -m "[Rework] Phase 3 — Valid inline harness records (#134)" \
  -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Runner seam and FixtureRunner

**Files:**
- Create: `tests/golden/runner.py`
- Test: `tests/golden/test_runner.py`

**Interfaces:**
- Consumes: `tests.golden.records` (`make_division`, `make_jurisdiction`), `src.models.division.Division`, `src.models.jurisdiction.Jurisdiction`.
- Produces:
  - `RunResult` dataclass: `division_paths: list[Path]`, `jurisdiction_paths: list[Path]`; properties `division_count`, `jurisdiction_count`.
  - `GoldenRunner` Protocol: `run(self, output_dir: Path) -> RunResult`.
  - `FixtureRunner(divisions: list[Division], jurisdictions: list[Jurisdiction])` implementing `GoldenRunner`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/golden/test_runner.py
import yaml

from tests.golden.records import make_division, make_jurisdiction
from tests.golden.runner import FixtureRunner


def test_fixture_runner_writes_expected_files(tmp_path):
    result = FixtureRunner([make_division()], [make_jurisdiction()]).run(tmp_path)
    assert result.division_count == 1
    assert result.jurisdiction_count == 1
    assert result.division_paths[0].exists()
    assert result.jurisdiction_paths[0].exists()


def test_fixture_runner_writes_only_under_output_dir(tmp_path):
    FixtureRunner([make_division()], [make_jurisdiction()]).run(tmp_path)
    written = list(tmp_path.rglob("*.yaml"))
    assert len(written) == 2
    assert all(str(p).startswith(str(tmp_path)) for p in written)


def test_fixture_runner_output_is_reparseable(tmp_path):
    result = FixtureRunner([make_division()], []).run(tmp_path)
    doc = yaml.safe_load(result.division_paths[0].read_text())
    assert doc["ocdid"].startswith("ocd-division/")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/golden/test_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tests.golden.runner'`.

- [ ] **Step 3: Write the implementation**

```python
# tests/golden/runner.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from src.models.division import Division
from src.models.jurisdiction import Jurisdiction


@dataclass
class RunResult:
    division_paths: list[Path] = field(default_factory=list)
    jurisdiction_paths: list[Path] = field(default_factory=list)

    @property
    def division_count(self) -> int:
        return len(self.division_paths)

    @property
    def jurisdiction_count(self) -> int:
        return len(self.jurisdiction_paths)


class GoldenRunner(Protocol):
    def run(self, output_dir: Path) -> RunResult: ...


class FixtureRunner:
    """Initial GoldenRunner: dumps injected model records into a temp dir."""

    def __init__(
        self, divisions: list[Division], jurisdictions: list[Jurisdiction]
    ) -> None:
        self._divisions = divisions
        self._jurisdictions = jurisdictions

    def run(self, output_dir: Path) -> RunResult:
        output_dir = Path(output_dir)
        div_dir = output_dir / "divisions"
        jur_dir = output_dir / "jurisdictions"
        result = RunResult()
        for division in self._divisions:
            result.division_paths.append(division.dump_division(base_dir=div_dir))
        for jurisdiction in self._jurisdictions:
            result.jurisdiction_paths.append(
                jurisdiction.dump_jurisdiction(base_dir=jur_dir)
            )
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/golden/test_runner.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint**

Run: `uv run ruff check tests/golden/runner.py tests/golden/test_runner.py`
Expected: All checks passed.

- [ ] **Step 6: Commit**

```bash
git add tests/golden/runner.py tests/golden/test_runner.py
git commit -m "[Rework] Phase 3.3 — GoldenRunner seam + FixtureRunner (#134)" \
  -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Regeneration CLI (drift diagnostic)

**Files:**
- Create: `tests/golden/regenerate.py`
- Test: `tests/golden/test_regenerate.py`

**Interfaces:**
- Consumes: `tests.golden.compare.compare_trees`, `tests.golden.runner` (`FixtureRunner`, `GoldenRunner`), `tests.golden.records` (`make_division`, `make_jurisdiction`).
- Produces:
  - `regenerate(golden_dir: Path, runner: GoldenRunner, apply: bool, out=sys.stdout) -> int` — prints a drift summary; overwrites `golden_dir` only when `apply` is True.
  - `main(argv: list[str] | None = None) -> int` — CLI entry; runs a dry-run drift report against `tests/sample_output/` and refuses to apply until Phase 10.

- [ ] **Step 1: Write the failing tests**

```python
# tests/golden/test_regenerate.py
import yaml

from tests.golden.records import make_division
from tests.golden.regenerate import regenerate
from tests.golden.runner import FixtureRunner


def _golden(tmp_path):
    golden = tmp_path / "golden"
    (golden / "divisions").mkdir(parents=True)
    (golden / "divisions" / "old.yaml").write_text(yaml.safe_dump({"a": 1}))
    return golden


def test_dry_run_does_not_touch_golden(tmp_path):
    golden = _golden(tmp_path)
    before = (golden / "divisions" / "old.yaml").read_text()
    rc = regenerate(golden, FixtureRunner([make_division()], []), apply=False)
    assert rc == 0
    assert (golden / "divisions" / "old.yaml").read_text() == before


def test_apply_replaces_golden(tmp_path):
    golden = _golden(tmp_path)
    rc = regenerate(golden, FixtureRunner([make_division()], []), apply=True)
    assert rc == 0
    assert not (golden / "divisions" / "old.yaml").exists()
    assert list(golden.rglob("*.yaml"))  # runner output is present
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/golden/test_regenerate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tests.golden.regenerate'`.

- [ ] **Step 3: Write the implementation**

```python
# tests/golden/regenerate.py
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from tests.golden.compare import compare_trees
from tests.golden.records import make_division, make_jurisdiction
from tests.golden.runner import FixtureRunner, GoldenRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO_ROOT / "tests" / "sample_output"

BANNER = (
    "=" * 72
    + "\nGOLDEN REGENERATION — overwrites tests/sample_output/.\n"
    + "Maintainer-approved change-control step only (AGENTS.md).\n"
    + "=" * 72
)


def default_runner() -> GoldenRunner:
    return FixtureRunner([make_division()], [make_jurisdiction()])


def regenerate(
    golden_dir: Path, runner: GoldenRunner, apply: bool, out=sys.stdout
) -> int:
    print(BANNER, file=out)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        runner.run(tmp_path)
        diffs = compare_trees(Path(golden_dir), tmp_path)
        print(f"{len(diffs)} difference(s) vs golden:", file=out)
        for d in diffs:
            print(f"  {d.kind:14} {d.file}:{d.path}", file=out)
        if not apply:
            print("\nDry run. No files written.", file=out)
            return 0
        golden_dir = Path(golden_dir)
        if golden_dir.exists():
            shutil.rmtree(golden_dir)
        shutil.copytree(tmp_path, golden_dir)
        print(f"\nGolden regenerated at {golden_dir}.", file=out)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tests.golden.regenerate")
    parser.add_argument(
        "--yes", action="store_true", help="Overwrite golden (disabled until Phase 10)."
    )
    args = parser.parse_args(argv)
    if args.yes:
        print(
            "Refusing to overwrite golden: the deterministic renderer (Phase 10) "
            "is not implemented, so regenerated layout is not final. "
            "Showing drift only.",
            file=sys.stderr,
        )
    return regenerate(GOLDEN_DIR, default_runner(), apply=False)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/golden/test_regenerate.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Verify the CLI runs as a drift diagnostic and never applies**

Run: `uv run python -m tests.golden.regenerate --yes`
Expected: prints the banner, the refusal notice on stderr, a difference count, and "Dry run. No files written." Then confirm golden is untouched:
Run: `git status --short tests/sample_output`
Expected: no output (clean).

- [ ] **Step 6: Lint**

Run: `uv run ruff check tests/golden/regenerate.py tests/golden/test_regenerate.py`
Expected: All checks passed.

- [ ] **Step 7: Commit**

```bash
git add tests/golden/regenerate.py tests/golden/test_regenerate.py
git commit -m "[Rework] Phase 3.5 — Maintainer-only golden regeneration diagnostic (#134)" \
  -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Stable identity golden test (Task 3.7)

> **Maintainer approval required** before merging this file (`tests/integration/`, per root `AGENTS.md`).

**Files:**
- Create: `tests/integration/test_golden_stable_identity.py`

**Interfaces:**
- Consumes: `tests.golden.records` (`make_division`, `make_geometry`, `FIXED_TS`).
- Produces: nothing (test-only).

- [ ] **Step 1: Write the tests (two green invariants + one strict xfail)**

```python
# tests/integration/test_golden_stable_identity.py
from datetime import datetime, timezone

import pytest

from tests.golden.records import FIXED_TS, make_division, make_geometry


@pytest.mark.integration
def test_uuid_stable_when_display_name_changes():
    a = make_division(display_name="Seattle")
    b = make_division(display_name="City of Seattle")
    assert a.ocdid == b.ocdid
    assert a.id == b.id


@pytest.mark.integration
def test_uuid_stable_when_geometry_changes():
    a = make_division(geometries=[make_geometry(None, None)])
    b = make_division(geometries=[])
    assert a.id == b.id


@pytest.mark.integration
@pytest.mark.xfail(strict=True, reason="blocked on #133 Task 2.1 — stable UUID")
def test_uuid_stable_when_retrieval_date_changes():
    a = make_division(last_updated=FIXED_TS)
    b = make_division(last_updated=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert a.id == b.id
```

- [ ] **Step 2: Run and confirm the intended states**

Run: `uv run pytest tests/integration/test_golden_stable_identity.py -v -m integration`
Expected: two PASS, one XFAIL (`test_uuid_stable_when_retrieval_date_changes`). No failures. (If the xfail ever XPASSes, Task 2.1 has landed — remove the `xfail` marker.)

- [ ] **Step 3: Lint**

Run: `uv run ruff check tests/integration/test_golden_stable_identity.py`
Expected: All checks passed.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_golden_stable_identity.py
git commit -m "[Rework] Phase 3.7 — Stable identity golden test (#134)" \
  -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Temporal geometry golden test (Task 3.8)

> **Maintainer approval required** before merging this file (`tests/integration/`, per root `AGENTS.md`).

**Files:**
- Create: `tests/integration/test_golden_temporal_geometry.py`

**Interfaces:**
- Consumes: `tests.golden.records` (`make_division`, `make_geometry`).
- Produces: nothing (test-only).

- [ ] **Step 1: Write the tests**

```python
# tests/integration/test_golden_temporal_geometry.py
from datetime import datetime, timezone

import pytest

from tests.golden.records import make_division, make_geometry


@pytest.mark.integration
def test_two_geometry_periods_serialize_with_provenance():
    closed = make_geometry(
        valid_from=datetime(2012, 1, 1, tzinfo=timezone.utc),
        valid_to=datetime(2022, 12, 4, tzinfo=timezone.utc),
    )
    current = make_geometry(
        valid_from=datetime(2022, 12, 5, tzinfo=timezone.utc),
        valid_to=None,
    )
    data = make_division(geometries=[closed, current]).model_dump(mode="json")
    geoms = data["geometries"]
    assert len(geoms) == 2
    valid_tos = [g["valid_to"] for g in geoms]
    assert None in valid_tos                       # one open-ended current period
    assert any(v is not None for v in valid_tos)   # one closed historical period
    assert all(g["source"] is not None for g in geoms)


@pytest.mark.integration
def test_division_uuid_stable_across_geometry_versions():
    one = make_division(geometries=[make_geometry(None, None)])
    two = make_division(
        geometries=[
            make_geometry(datetime(2012, 1, 1, tzinfo=timezone.utc), None),
            make_geometry(datetime(2022, 1, 1, tzinfo=timezone.utc), None),
        ]
    )
    assert one.id == two.id
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_golden_temporal_geometry.py -v -m integration`
Expected: PASS (2 tests).

- [ ] **Step 3: Lint**

Run: `uv run ruff check tests/integration/test_golden_temporal_geometry.py`
Expected: All checks passed.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_golden_temporal_geometry.py
git commit -m "[Rework] Phase 3.8 — Temporal geometry golden test (#134)" \
  -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Final verification (after all tasks)

- [ ] **Full suite, default profile:** `uv run pytest -m "not integration and not slow"` → all pass, including the new `tests/golden/` unit tests.
- [ ] **Integration profile:** `uv run pytest -m integration` → all pass; exactly one XFAIL (`test_uuid_stable_when_retrieval_date_changes`).
- [ ] **Whole suite:** `uv run pytest` → green (no regressions to the existing 193).
- [ ] **Lint:** `uv run ruff check .` → All checks passed.
- [ ] **Golden untouched:** `git status --short tests/sample_output` → empty.

---

## Follow-ups (not code; require user approval before any external action)

Two work-items surfaced during design verification. Do NOT file them on GitHub without the user's explicit go-ahead; drafts are prepared for review first.

1. **Broken jurisdiction fixture** — `tests/fixtures/jurisdictions_sample.py` fails to import under the current jurisdiction model (`MARIN_CITY_CSD_JURISDICTION`: ocdid suffix `governing_board` ≠ classification `special_purpose_district`). No active test imports it, so the suite still passes. Likely a Phase 2 follow-up.
2. **Stale golden tree** — `tests/sample_output/` predates Phase 2 model changes (`government_identifiers`, `geometries`, `sourcing`). Regeneration is Phase 11 (#142) and needs a maintainer with the Phase 10 renderer in place.
