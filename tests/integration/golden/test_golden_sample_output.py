"""One comparison per checked-in golden file.

Each file under ``tests/sample_output/`` is regenerated from its fixture
object into a temporary directory and compared field by field, including
its relative path. The checked-in files were written under an earlier model
contract, so every comparison is expected to fail until a maintainer
regenerates them; ``xfail(strict=True)`` keeps the suite green now and turns
into a loud failure the moment a file starts matching, which is the signal
to drop the marker for that file.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.integration.golden.harness import (
    DIVISIONS,
    FILE_PATH_FIELD,
    GOLDEN_ROOT,
    JURISDICTIONS,
    Difference,
    diff_structures,
    format_differences,
    load_yaml_tree,
    regenerate_from_fixtures,
)

PREDATES_MODELS = (
    "checked-in file predates the current models; awaiting approved regeneration"
)
NO_FIXTURE_OBJECT = (
    "fixture object does not construct: its OCDid ends in a segment that is not a "
    "classification value, so there is no regenerated counterpart; the checked-in "
    "file also predates the current models"
)


def _reason(relative: Path) -> str:
    if "marin_city_community_services_district" in relative.name:
        return NO_FIXTURE_OBJECT
    return PREDATES_MODELS


# Division and Jurisdiction records regenerate from fixture objects; quarantine
# records are produced by the pipeline and have their own test.
GOLDEN_FILES = sorted(
    p.relative_to(GOLDEN_ROOT)
    for kind in (DIVISIONS, JURISDICTIONS)
    for p in (GOLDEN_ROOT / kind).rglob("*.yaml")
)


@pytest.fixture(scope="module")
def regenerated(tmp_path_factory):
    root = tmp_path_factory.mktemp("golden_regen")
    regenerate_from_fixtures(root)
    return load_yaml_tree(root)


@pytest.mark.integration
@pytest.mark.golden
@pytest.mark.parametrize(
    "relative",
    [
        pytest.param(
            rel,
            id=str(rel),
            marks=pytest.mark.xfail(strict=True, reason=_reason(rel)),
        )
        for rel in GOLDEN_FILES
    ],
)
def test_golden_file_matches_regenerated_record(relative: Path, regenerated):
    expected = yaml.safe_load((GOLDEN_ROOT / relative).read_text())
    key = (relative.parts[0], expected["ocdid"])
    counterparts = regenerated.get(key, [])
    assert counterparts, (
        f"{relative}: no regenerated counterpart for {expected['ocdid']}"
    )
    assert len(counterparts) == 1, f"{relative}: more than one regenerated file"

    actual_relative, actual = counterparts[0]
    differences: list[Difference] = []
    if actual_relative != relative:
        differences.append(
            Difference(
                str(relative), FILE_PATH_FIELD, str(relative), str(actual_relative)
            )
        )
    differences += [
        Difference(str(relative), path, exp, act)
        for path, exp, act in diff_structures(expected, actual)
    ]
    assert not differences, "\n" + format_differences(differences)
