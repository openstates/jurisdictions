"""End-to-end golden path through Phase 10 canonical YAML rendering."""

from __future__ import annotations

from src.render_yaml import render_yaml
from tests.integration.golden.harness import (
    DIVISIONS,
    JURISDICTIONS,
    compare_trees,
    render_canonical_golden_fixtures,
)

VERIFIED_CENSUS_IDS = {"161205", "176868"}  # Sausalito, Tacoma
QUARANTINED_CENSUS_IDS = {"176394", "184255"}  # Austin, Seattle
UNRESOLVED_CENSUS_IDS = {"124214"}  # Washington, DC fixture place is nonfunctioning


def test_complete_canonical_path_renders_deterministically(tmp_path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"

    first_models, first_quarantines, first_unresolved, first_written = (
        render_canonical_golden_fixtures(first_root)
    )
    second_models, second_quarantines, second_unresolved, second_written = (
        render_canonical_golden_fixtures(second_root)
    )

    assert set(first_models) == VERIFIED_CENSUS_IDS
    assert set(second_models) == VERIFIED_CENSUS_IDS
    assert len(first_written) == len(second_written) == 4

    assert compare_trees(
        first_root,
        second_root,
        kinds=(DIVISIONS, JURISDICTIONS),
    ) == []

    first_quarantine_yaml = {
        record.government.census_government_id: render_yaml(record)
        for record in first_quarantines
    }
    second_quarantine_yaml = {
        record.government.census_government_id: render_yaml(record)
        for record in second_quarantines
    }
    assert set(first_quarantine_yaml) == QUARANTINED_CENSUS_IDS
    assert first_quarantine_yaml == second_quarantine_yaml

    assert set(first_unresolved) == UNRESOLVED_CENSUS_IDS
    assert first_unresolved == second_unresolved
