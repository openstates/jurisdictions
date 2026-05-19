from pydantic import BaseModel, ConfigDict
from typing import Optional
from src.utils.ocdid import ocdid_parser
from src.errors import OCDIdParsingError


class OCDidParsed(BaseModel):
    """
    Parsed OCDid used for string matching on import records. Handles Division
    OCDids, not Jurisdiction OCDids (which have a slightly different structure)

    Examples:
        - ocd-division/country:us/state:ca/county:marin/place:sausalito
        - ocd-division/country:us/state:wa/place:seattle/council_district:1
        - ocd-division/country:us/state:wa
    """

    model_config = ConfigDict(extra="allow")

    country: str = "us"
    state: Optional[str] = None
    county: Optional[str] = None
    place: Optional[str] = None
    subdivision: Optional[str] = None
    raw_ocdid: str

    @classmethod
    def build_ancestor_ocdids(cls, parsed_ocdid: "OCDidParsed") -> list["OCDidParsed"]:
        """Return ancestor OCD IDs as parsed models, excluding country root and leaf."""
        try:
            parts = parsed_ocdid.raw_ocdid.split("/")
            base = parts[0] if len(parts) > 0 else "ocd-division"
            country_segment = (
                parts[1] if len(parts) > 1 else f"country:{parsed_ocdid.country}"
            )
            hierarchy_segments = parts[2:]

            ancestors: list[OCDidParsed] = []
            for end in range(1, len(hierarchy_segments)):
                ancestor_segments = "/".join(hierarchy_segments[:end])
                ancestor_ocdid = f"{base}/{country_segment}/{ancestor_segments}"
                ancestors.append(cls.parse_ocdid(ancestor_ocdid))
            return ancestors
        except Exception as error:
            raise OCDIdParsingError(error) from error

    @classmethod
    def parse_ocdid(cls, raw_ocdid: str) -> "OCDidParsed":
        try:
            ocdid_dict = ocdid_parser(raw_ocdid)
            return cls(**ocdid_dict, raw_ocdid=raw_ocdid)
        except Exception as error:
            raise OCDIdParsingError(error) from error
