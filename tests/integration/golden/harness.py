"""Golden-file harness for ``tests/sample_output/``.

Three jobs, all offline:

1. Regenerate the golden records from the hand-authored fixture objects in
   ``tests/fixtures/`` into a caller-supplied directory, using the same
   serializer and the same ``<kind>/test/<state>/local/<slug>_<id>.yaml``
   layout as the checked-in files.
2. Run the real generate stage (``GeneratePipeline``) over the OCDid roster
   in ``tests/fixtures/ocd_master/country-us.csv`` with the validation CSVs
   in ``tests/fixtures/sources/`` into a caller-supplied directory.
3. Diff two YAML trees structurally and report every difference as
   (file, dotted field path, expected, actual). A key present with ``null``
   is not the same as an absent key.

Nothing here writes under ``tests/sample_output/``; every writer refuses a
target inside it.
"""

from __future__ import annotations

import asyncio
import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from src.init_migration.generate_pipeline import GeneratePipeline
from src.init_migration.pipeline_models import (
    GeneratorReq,
    GeneratorResp,
    OCDidIngestResp,
)
from src.models.division import Division
from src.models.jurisdiction import Jurisdiction
from src.models.ocdid import OCDIdParsed
from src.normalize_government import NormalizationResult, normalize_records
from src.sources import census_gus
from src.sources.government_units import GovernmentKind
from src.sources.snapshot import load_snapshot, source_obj_from_snapshot
from src.utils.deterministic_id import generate_id

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLDEN_ROOT = REPO_ROOT / "tests" / "sample_output"
FIXTURES_ROOT = REPO_ROOT / "tests" / "fixtures"
ROSTER_CSV = FIXTURES_ROOT / "ocd_master" / "country-us.csv"
VALIDATION_CSVS = (
    FIXTURES_ROOT / "sources" / "civicdata_divisions.csv",
    FIXTURES_ROOT / "sources" / "civicdata_states.csv",
    FIXTURES_ROOT / "sources" / "civicdata_counties.csv",
)

DIVISIONS = "divisions"
JURISDICTIONS = "jurisdictions"
QUARANTINE = "quarantine"

# Field path used for whole-file differences (missing, unexpected, renamed).
FILE_PATH_FIELD = "<path>"


class _Absent:
    """Marker for a key or list index that exists on one side only."""

    def __repr__(self) -> str:
        return "<absent>"


ABSENT = _Absent()


@dataclass(frozen=True)
class Difference:
    """One structural difference between an expected and an actual record."""

    file: str
    field_path: str
    expected: Any
    actual: Any

    def __str__(self) -> str:
        return (
            f"{self.file}: {self.field_path}: expected {self.expected!r}, "
            f"got {self.actual!r}"
        )


@dataclass
class PipelineRun:
    """What one ``GeneratePipeline.run()`` produced for one OCDid."""

    ocdid: str
    response: GeneratorResp
    quarantine: list[dict] = field(default_factory=list)


# --------------------------------------------------------------------------- diff


def diff_structures(
    expected: Any, actual: Any, path: str = ""
) -> list[tuple[str, Any, Any]]:
    """Return ``(field_path, expected, actual)`` for every leaf that differs.

    Dicts are compared key by key, lists index by index. A value of a
    different type (``48`` vs ``"048"``) is a difference even when the two
    compare equal.
    """
    out: list[tuple[str, Any, Any]] = []
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual)):
            sub = f"{path}.{key}" if path else str(key)
            if key not in expected:
                out.append((sub, ABSENT, actual[key]))
            elif key not in actual:
                out.append((sub, expected[key], ABSENT))
            else:
                out.extend(diff_structures(expected[key], actual[key], sub))
        return out
    if isinstance(expected, list) and isinstance(actual, list):
        for index in range(max(len(expected), len(actual))):
            sub = f"{path}[{index}]"
            if index >= len(expected):
                out.append((sub, ABSENT, actual[index]))
            elif index >= len(actual):
                out.append((sub, expected[index], ABSENT))
            else:
                out.extend(diff_structures(expected[index], actual[index], sub))
        return out
    if type(expected) is not type(actual) or expected != actual:
        out.append((path, expected, actual))
    return out


def _strip_ignored(data: Any, ignore_fields: tuple[str, ...]) -> Any:
    if not ignore_fields or not isinstance(data, dict):
        return data
    return {k: v for k, v in data.items() if k not in ignore_fields}


def compare_records(
    expected_file: Path,
    actual_file: Path,
    *,
    label: str,
    ignore_fields: tuple[str, ...] = (),
) -> list[Difference]:
    """Diff two YAML files; ``ignore_fields`` drops top-level keys from both."""
    expected = _strip_ignored(yaml.safe_load(expected_file.read_text()), ignore_fields)
    actual = _strip_ignored(yaml.safe_load(actual_file.read_text()), ignore_fields)
    return [
        Difference(label, field_path, exp, act)
        for field_path, exp, act in diff_structures(expected, actual)
    ]


def load_yaml_tree(root: Path) -> dict[tuple[str, str], list[tuple[Path, dict]]]:
    """Index every ``*.yaml`` under ``root`` by ``(kind, ocdid)``.

    ``kind`` is the first path segment below ``root`` (``divisions``,
    ``jurisdictions``, ...). More than one file for a key is preserved so the
    caller can report it.
    """
    tree: dict[tuple[str, str], list[tuple[Path, dict]]] = {}
    for path in sorted(root.rglob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        relative = path.relative_to(root)
        key = (relative.parts[0], data["ocdid"])
        tree.setdefault(key, []).append((relative, data))
    return tree


def compare_trees(
    expected_root: Path,
    actual_root: Path,
    *,
    ignore_fields: tuple[str, ...] = (),
    kinds: tuple[str, ...] | None = None,
) -> list[Difference]:
    """Diff two output trees, pairing files by ``(kind, ocdid)``.

    The relative path is compared as the field ``<path>`` so a record whose
    id (and therefore filename) changed is reported once for the rename and
    then field by field for its content. ``kinds`` restricts the comparison
    to those top-level directories.
    """
    expected = load_yaml_tree(expected_root)
    actual = load_yaml_tree(actual_root)
    differences: list[Difference] = []

    keys = set(expected) | set(actual)
    if kinds is not None:
        keys = {key for key in keys if key[0] in kinds}
    for key in sorted(keys):
        exp_entries = expected.get(key, [])
        act_entries = actual.get(key, [])
        if not act_entries:
            for relative, _ in exp_entries:
                differences.append(
                    Difference(str(relative), FILE_PATH_FIELD, str(relative), ABSENT)
                )
            continue
        if not exp_entries:
            for relative, _ in act_entries:
                differences.append(
                    Difference(str(relative), FILE_PATH_FIELD, ABSENT, str(relative))
                )
            continue
        if len(exp_entries) > 1 or len(act_entries) > 1:
            differences.append(
                Difference(
                    str(exp_entries[0][0]),
                    FILE_PATH_FIELD,
                    [str(r) for r, _ in exp_entries],
                    [str(r) for r, _ in act_entries],
                )
            )
            continue

        (exp_rel, exp_data), (act_rel, act_data) = exp_entries[0], act_entries[0]
        label = str(exp_rel)
        if exp_rel != act_rel:
            differences.append(
                Difference(label, FILE_PATH_FIELD, str(exp_rel), str(act_rel))
            )
        for field_path, exp, act in diff_structures(
            _strip_ignored(exp_data, ignore_fields),
            _strip_ignored(act_data, ignore_fields),
        ):
            differences.append(Difference(label, field_path, exp, act))
    return differences


def format_differences(differences: list[Difference]) -> str:
    """Group differences by file for a readable failure message."""
    lines: list[str] = []
    current: str | None = None
    for diff in differences:
        if diff.file != current:
            current = diff.file
            lines.append(f"--- {current}")
        lines.append(
            f"    {diff.field_path}: expected {diff.expected!r}, got {diff.actual!r}"
        )
    return "\n".join(lines)


# ----------------------------------------------------------------- golden layout


def refuse_golden_root(path: Path) -> None:
    """Raise if ``path`` is ``tests/sample_output`` or anything inside it."""
    resolved = path.resolve()
    if resolved == GOLDEN_ROOT or GOLDEN_ROOT in resolved.parents:
        raise ValueError(
            f"refusing to write under {GOLDEN_ROOT}: regenerate into another "
            "directory and copy the result over deliberately"
        )


def slugify(name: str) -> str:
    """Filename slug used by the checked-in golden files."""
    return name.lower().replace(" ", "_")


def state_segment(ocdid: str) -> str:
    """Two-letter state directory for an OCDid (``district:dc`` counts)."""
    parsed = OCDIdParsed.parse_ocdid(ocdid)
    state = parsed.state or getattr(parsed, "district", None)
    if not state:
        raise ValueError(f"no state or district segment in {ocdid}")
    return state.lower()


def golden_relative_path(record: Division | Jurisdiction) -> Path:
    """``<kind>/test/<state>/local/<slug>_<id>.yaml`` for a fixture object."""
    if isinstance(record, Division):
        kind, name = DIVISIONS, record.display_name
    else:
        kind, name = JURISDICTIONS, record.name
    return (
        Path(kind)
        / "test"
        / state_segment(record.ocdid)
        / "local"
        / f"{slugify(name)}_{record.id}.yaml"
    )


def dump_golden_record(record: Division | Jurisdiction, root: Path) -> Path:
    """Write one record the way the golden files were written.

    ``model_dump(mode="json", exclude_none=False)`` through ``yaml.safe_dump``
    with its default sorted keys, at the golden layout under ``root``.
    """
    refuse_golden_root(root)
    path = root / golden_relative_path(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = record.model_dump(mode="json", exclude_none=False)
    path.write_text(yaml.safe_dump(data))
    return path


# ------------------------------------------------------------------- fixtures


def load_division_fixtures() -> list[Division]:
    from tests.fixtures.divisions_sample import div_list

    return list(div_list)


def load_jurisdiction_fixtures() -> list[Jurisdiction]:
    """The Jurisdiction fixture objects that construct under the current model.

    The module is executed only up to the first object that fails validation
    (its OCDid ends in a segment that is not a classification value), so the
    objects defined before it are recovered without importing the module.
    """
    source = (FIXTURES_ROOT / "jurisdictions_sample.py").read_text()
    head = source.split("MARIN_CITY_CSD_JURISDICTION =")[0]
    namespace: dict[str, Any] = {}
    exec(compile(head, "jurisdictions_sample.py", "exec"), namespace)
    return [obj for obj in namespace.values() if isinstance(obj, Jurisdiction)]


def regenerate_from_fixtures(root: Path) -> list[Path]:
    """Dump every constructible fixture object into ``root``."""
    refuse_golden_root(root)
    written = [dump_golden_record(d, root) for d in load_division_fixtures()]
    written += [dump_golden_record(j, root) for j in load_jurisdiction_fixtures()]
    return written


def load_roster() -> list[str]:
    """Division OCDids from the OCD master fixture, in file order."""
    with ROSTER_CSV.open(newline="") as handle:
        return [row["id"] for row in csv.DictReader(handle)]


def load_normalized_government_fixtures() -> NormalizationResult:
    """Run the Phase 5 normalizer over the controlled annual Census fixture."""
    snapshot = load_snapshot(
        FIXTURES_ROOT / "census_gus" / "gov_units_2026_general_purpose.csv"
    )
    parsed = census_gus.parse_sheet_snapshot(
        snapshot,
        GovernmentKind.GENERAL_PURPOSE,
    )
    if parsed.metadata is None:
        raise ValueError("Census fixture did not carry snapshot metadata")

    source = source_obj_from_snapshot(
        parsed.metadata,
        field=["government"],
        source_description="Census government normalization input",
    )
    return normalize_records(
        parsed.records,
        source=source,
        source_errors=parsed.errors,
    )


# ------------------------------------------------------------------- pipeline


def build_request(
    ocdid: str,
    asof: datetime,
    validation_csvs: tuple[Path, Path, Path] = VALIDATION_CSVS,
) -> GeneratorReq:
    """A ``GeneratorReq`` for one OCDid against the fixture validation CSVs."""
    divisions, states, counties = validation_csvs
    return GeneratorReq(
        data=OCDidIngestResp(
            uuid=generate_id(ocdid),
            ocdid=OCDIdParsed.parse_ocdid(ocdid),
            raw_record={},
        ),
        validation_data_division_filepath=str(divisions),
        validation_data_states_filepath=str(states),
        validation_data_counties_filepath=str(counties),
        build_base_object=True,
        jurisdiction_ai_url=False,
        division_geo_req=False,
        division_population_req=False,
        asof_datetime=asof,
    )


def quarantine_record(run: PipelineRun) -> dict[str, Any]:
    """The structured outcome of a quarantined run, as stored in the golden tree.

    Combines the response status with the pipeline's own quarantine entry so
    the record is independent of the wall clock.
    """
    if len(run.quarantine) != 1:
        raise ValueError(
            f"{run.ocdid}: expected one quarantine entry, got {run.quarantine}"
        )
    entry = run.quarantine[0]
    return {
        "ocdid": run.ocdid,
        "status": run.response.status.status.value,
        "error": run.response.status.error,
        "reason": entry["reason"],
        "matched_records": entry["matched_records"],
    }


def quarantine_relative_path(ocdid: str, slug: str) -> Path:
    """``quarantine/test/<state>/local/<slug>.yaml``."""
    return Path(QUARANTINE) / "test" / state_segment(ocdid) / "local" / f"{slug}.yaml"


def run_pipeline(
    ocdids: list[str],
    root: Path,
    asof: datetime,
    validation_csvs: tuple[Path, Path, Path] = VALIDATION_CSVS,
) -> list[PipelineRun]:
    """Run ``GeneratePipeline`` for each OCDid, writing under ``root`` only.

    One pipeline instance per OCDid, as the CLI does. ``last_updated`` on the
    written records is the wall clock; callers comparing two runs pass
    ``ignore_fields=("last_updated",)`` to the comparison.
    """
    refuse_golden_root(root)
    root.mkdir(parents=True, exist_ok=True)
    runs: list[PipelineRun] = []
    for ocdid in ocdids:
        pipeline = GeneratePipeline(
            build_request(ocdid, asof, validation_csvs),
            division_output_dir=root,
            jurisdiction_output_dir=root,
        )
        response = asyncio.run(pipeline.run())
        runs.append(
            PipelineRun(
                ocdid=ocdid,
                response=response,
                quarantine=list(pipeline.quarantine.ocdid_no_validation_div),
            )
        )
    return runs
