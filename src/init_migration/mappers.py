"""
Dictionaries representing file mappings for initial data migration.
"""

from pydantic import BaseModel
import json
from pathlib import Path


ROOT = Path(__file__).parent.parent.parent

ocdid_master_mapper = {
    "id": "id",
    "name": "display_name",
    "sameAs": "also_known_as",
    "sameAsNote": "metadata.also_known_as_note",
    "validThrough": "valid_asof",
    "census_geoid": "geometries.government_identifiers.geoid",
    "census_geoid_12": "geometries.government_identifiers.geoid_12",
    "census_geoid_14": "geometries.government_identifiers.geoid_14",
    "openstates_district": "metadata.openstates_district",
    "placeholder_id": "metadata.placeholder_id",  # Only 5284 values
    "sch_dist_stateid": "metadata.sch_dist_stateid",  # 15438 values
    "state_id": "geometries.government_identifiers.stusps",  # IS IT STATE CODE?
    "validFrom": "valid_thru",
}


class LSADDefinition(BaseModel):
    """
    LSAD code definitions, as defined by the Census Bureau. Used for
    jurisdiction inference rules.
    Reference: https://www.census.gov/library/reference/code-lists/legal-status-codes.html
    Source: https://www2.census.gov/geo/pdfs/reference/LSADCodes.pdf
    """

    lsad_description: str
    lsad_prefix: str | None
    lsad_suffix: str | None
    associated_geographic_entity: list[str]


def convert_lsad_definitions(input_path: str) -> dict[str, LSADDefinition]:
    """
    Returns a dictionary of LSAD code definitions, keyed by the LSAD code.
    key value pairs are the two-digit code and the definition as a LSADDefinition object.

    TODO: Code to export the LSAD code definitions from the Census Bureau PDF into a dictionary format that can be used for jurisdiction inference rules.
    """
    ### Write code here
    lsad_map: dict[str, LSADDefinition] = {}
    return lsad_map


def export_lsad_definitions_to_json():
    """
    Exports the LSAD code definitions to a JSON file for use in jurisdiction inference rules.
    """
    source_path = "https://www2.census.gov/geo/pdfs/reference/LSADCodes.pdf"
    output_path = ROOT / "data" / "lsad_definitions.json"

    lsad_definitions = convert_lsad_definitions(input_path=source_path)

    lsad_definitions_dict = {
        lsad_code: lsad_def.model_dump()
        for lsad_code, lsad_def in lsad_definitions.items()
    }

    with open(output_path, "w") as f:
        json.dump(lsad_definitions_dict, f, indent=4)
