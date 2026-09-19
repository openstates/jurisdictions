"""A record's id and filename depend on its OCDid alone.

Changing what the pipeline is told (the as-of date, the validation row's
mutable columns) or what a fixture object carries (last_updated, website,
source release and retrieval date, geometry) must not move the id or the
filename. The id is always ``generate_id(ocdid)``.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from pydantic import HttpUrl

from src.models.division import Boundary, Geometry
from src.utils.deterministic_id import generate_id
from tests.integration.golden.harness import (
    VALIDATION_CSVS,
    dump_golden_record,
    load_division_fixtures,
    load_jurisdiction_fixtures,
    run_pipeline,
)

SAUSALITO = "ocd-division/country:us/state:ca/place:sausalito"
SAUSALITO_GOV = "ocd-jurisdiction/country:us/state:ca/place:sausalito/government"
ASOF_A = datetime(2025, 10, 27, 1, 29, 51, tzinfo=timezone.utc)
ASOF_B = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)


def _with_changed_row(tmp_path: Path, **changes: str) -> tuple[Path, Path, Path]:
    """Copy the validation CSVs, altering the Sausalito row's mutable columns."""
    divisions, states, counties = VALIDATION_CSVS
    with divisions.open(newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames
    for row in rows:
        if row["NAMELSAD"] == "Sausalito city":
            row.update(changes)
    target = tmp_path / "civicdata_divisions.csv"
    with target.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return target, states, counties


@pytest.mark.integration
@pytest.mark.golden
def test_pipeline_output_keeps_id_and_filename_when_inputs_change(tmp_path):
    run_a = run_pipeline([SAUSALITO], tmp_path / "a", ASOF_A)[0]
    changed = _with_changed_row(
        tmp_path, SLDUST_list="002", SLDLST_list="012", COUNTY_NAMES="Marin County"
    )
    run_b = run_pipeline([SAUSALITO], tmp_path / "b", ASOF_B, changed)[0]

    for kind, path_a, path_b, ocdid in (
        (
            "division",
            run_a.response.division_path,
            run_b.response.division_path,
            SAUSALITO,
        ),
        (
            "jurisdiction",
            run_a.response.jurisdiction_path,
            run_b.response.jurisdiction_path,
            SAUSALITO_GOV,
        ),
    ):
        rel_a = Path(path_a).relative_to(tmp_path / "a")
        rel_b = Path(path_b).relative_to(tmp_path / "b")
        assert rel_a == rel_b, kind
        data_a = yaml.safe_load(Path(path_a).read_text())
        data_b = yaml.safe_load(Path(path_b).read_text())
        assert data_a["id"] == data_b["id"] == str(generate_id(ocdid)), kind
        assert data_a["accurate_asof"] != data_b["accurate_asof"], kind

    # The changed inputs did reach the output; only identity stayed put.
    div_b = yaml.safe_load(Path(run_b.response.division_path).read_text())
    values = {i["id_type"]: i["value"] for i in div_b["government_identifiers"]}
    assert values["sldust"] == "002"
    assert values["county_names"] == "Marin County"


@pytest.mark.integration
@pytest.mark.golden
def test_fixture_dump_keeps_filename_when_mutable_facts_change(tmp_path):
    division = next(d for d in load_division_fixtures() if d.ocdid == SAUSALITO)
    jurisdiction = next(
        j for j in load_jurisdiction_fixtures() if j.ocdid == SAUSALITO_GOV
    )

    later_source = division.sourcing[0].model_copy(
        update={"release": "2025", "retrieval_date": ASOF_B}
    )
    changed_division = division.model_copy(
        update={
            "last_updated": ASOF_B,
            "sourcing": [later_source, *division.sourcing[1:]],
            "geometries": [
                Geometry(
                    valid_from=ASOF_B,
                    valid_to=None,
                    boundary=Boundary(),
                    url="https://example.gov/boundary.geojson",
                    identifiers=[],
                    source=later_source,
                )
            ],
        }
    )
    changed_jurisdiction = jurisdiction.model_copy(
        update={
            "last_updated": ASOF_B,
            "url": HttpUrl("https://sausalito.example.gov/"),
            "sourcing": [
                jurisdiction.sourcing[0].model_copy(update={"release": "2025"}),
                *jurisdiction.sourcing[1:],
            ],
        }
    )

    for original, changed in (
        (division, changed_division),
        (jurisdiction, changed_jurisdiction),
    ):
        path_original = dump_golden_record(original, tmp_path / "before")
        path_changed = dump_golden_record(changed, tmp_path / "after")
        assert path_original.relative_to(
            tmp_path / "before"
        ) == path_changed.relative_to(tmp_path / "after")
        assert changed.id == original.id == generate_id(original.ocdid)
        assert yaml.safe_load(path_changed.read_text()) != yaml.safe_load(
            path_original.read_text()
        )
