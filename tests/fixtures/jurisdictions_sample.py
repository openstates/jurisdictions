"""Jurisdiction fixtures, read from the golden sample output.

``tests/sample_output`` is the ground truth a pipeline run is checked
against, so these fixtures load it instead of restating the same records in
Python. Restating them meant two sources that could disagree, and the one
the integration tests actually compare against is the YAML.

To change a fixture, edit its YAML under
``tests/sample_output/jurisdictions``.
"""

from pathlib import Path

from src.models.jurisdiction import Jurisdiction

SAMPLE_DIR = Path(__file__).resolve().parents[1] / "sample_output" / "jurisdictions"


def load_jurisdictions() -> dict[str, Jurisdiction]:
    """Return every sample Jurisdiction, keyed by its OCD ID."""
    jurisdictions: dict[str, Jurisdiction] = {}
    for path in sorted(SAMPLE_DIR.rglob("*.yaml")):
        jurisdiction = Jurisdiction.load_jurisdiction(path)
        jurisdictions[str(jurisdiction.ocdid)] = jurisdiction
    return jurisdictions


_BY_OCDID = load_jurisdictions()

SEATTLE_JURISDICTION = _BY_OCDID[
    "ocd-jurisdiction/country:us/state:wa/place:seattle/government"
]
TACOMA_JURISDICTION = _BY_OCDID[
    "ocd-jurisdiction/country:us/state:wa/place:tacoma/government"
]
AUSTIN_JURISDICTION = _BY_OCDID[
    "ocd-jurisdiction/country:us/state:tx/place:austin/government"
]
ANC_1A_JURISDICTION = _BY_OCDID[
    "ocd-jurisdiction/country:us/district:dc/anc:1a/government"
]
SAUSALITO_JURISDICTION = _BY_OCDID[
    "ocd-jurisdiction/country:us/state:ca/place:sausalito/government"
]
MARIN_CITY_CSD_JURISDICTION = _BY_OCDID[
    "ocd-jurisdiction/country:us/state:ca/county:marin/cdp:marin_city"
    "/special_district:marin_city_community_services_district/special_purpose_district"
]

jur_list = [
    SEATTLE_JURISDICTION,
    TACOMA_JURISDICTION,
    AUSTIN_JURISDICTION,
    ANC_1A_JURISDICTION,
    SAUSALITO_JURISDICTION,
    MARIN_CITY_CSD_JURISDICTION,
]
