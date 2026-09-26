"""Division fixtures, read from the golden sample output.

``tests/sample_output`` is the ground truth a pipeline run is checked
against, so these fixtures load it instead of restating the same records in
Python. Restating them meant two sources that could disagree, and the one
the integration tests actually compare against is the YAML.

To change a fixture, edit its YAML under ``tests/sample_output/divisions``.
"""

from pathlib import Path

from src.models.division import Division

SAMPLE_DIR = Path(__file__).resolve().parents[1] / "sample_output" / "divisions"


def load_divisions() -> dict[str, Division]:
    """Return every sample Division, keyed by its OCD ID."""
    divisions: dict[str, Division] = {}
    for path in sorted(SAMPLE_DIR.rglob("*.yaml")):
        division = Division.load_division(path)
        divisions[str(division.ocdid)] = division
    return divisions


_BY_OCDID = load_divisions()

SEATTLE_DIVISION = _BY_OCDID[
    "ocd-division/country:us/state:wa/place:seattle/council_district:1"
]
TACOMA_DIVISION = _BY_OCDID["ocd-division/country:us/state:wa/place:tacoma"]
AUSTIN_DIVISION = _BY_OCDID[
    "ocd-division/country:us/state:tx/place:austin/council_district:8"
]
ANC_1A_DIVISION = _BY_OCDID[
    "ocd-division/country:us/district:dc/anc:1a/council_district:1"
]
SAUSALITO_DIVISION = _BY_OCDID["ocd-division/country:us/state:ca/place:sausalito"]
MARIN_CITY_DIVISION = _BY_OCDID[
    "ocd-division/country:us/state:ca/county:marin/cdp:marin_city"
]

div_list = [
    SEATTLE_DIVISION,
    TACOMA_DIVISION,
    AUSTIN_DIVISION,
    ANC_1A_DIVISION,
    SAUSALITO_DIVISION,
    MARIN_CITY_DIVISION,
]
