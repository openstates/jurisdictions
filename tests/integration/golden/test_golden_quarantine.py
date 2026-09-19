"""An OCDid with no validation match quarantines the same way every time.

ANC 1A District 1 has no row in the validation CSVs. The pipeline must
return the same structured status and the same quarantine record on every
run, and that record must equal the checked-in golden file.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from src.init_migration.pipeline_models import Status
from tests.integration.golden.harness import (
    GOLDEN_ROOT,
    compare_records,
    format_differences,
    quarantine_record,
    quarantine_relative_path,
    run_pipeline,
)

ANC_1A = "ocd-division/country:us/district:dc/anc:1a/council_district:1"
ASOF = datetime(2025, 10, 27, 1, 29, 51, tzinfo=timezone.utc)
GOLDEN_RECORD = GOLDEN_ROOT / quarantine_relative_path(ANC_1A, "anc_1a_district_1")


@pytest.mark.integration
@pytest.mark.golden
def test_no_match_ocdid_quarantines_deterministically(tmp_path):
    first = run_pipeline([ANC_1A], tmp_path / "run1", ASOF)[0]
    second = run_pipeline([ANC_1A], tmp_path / "run2", ASOF)[0]

    assert first.response.status.status == Status.PARTIAL
    assert first.response.status == second.response.status
    assert first.quarantine == second.quarantine
    assert first.response.jurisdiction_path is None

    # The stub Division written alongside the quarantine entry is identical
    # apart from last_updated, which the generator takes from the wall clock.
    stub1, stub2 = (
        Path(first.response.division_path),
        Path(second.response.division_path),
    )
    assert stub1.relative_to(tmp_path / "run1") == stub2.relative_to(tmp_path / "run2")
    differences = compare_records(
        stub1, stub2, label=stub1.name, ignore_fields=("last_updated",)
    )
    assert not differences, "\n" + format_differences(differences)


@pytest.mark.integration
@pytest.mark.golden
def test_quarantine_record_matches_golden_file(tmp_path):
    run = run_pipeline([ANC_1A], tmp_path, ASOF)[0]

    expected = yaml.safe_load(GOLDEN_RECORD.read_text())
    assert quarantine_record(run) == expected
