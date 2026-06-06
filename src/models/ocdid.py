from typing import Annotated, Literal, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from src.utils.ocdid import ocdid_parser
from src.errors import OCDIdParsingError


def validate_ocdid(value: str) -> str:
    if not value.startswith(("ocd-division/", "ocd-jurisdiction/")):
        raise ValueError(
            "OCD ID must start with 'ocd-division/' or 'ocd-jurisdiction/'"
        )
    if not value.count("/") >= 2:
        _, _, country_segment = value.partition("/")
        if country_segment.startswith("country:") and country_segment.removeprefix(
            "country:"
        ):
            return value
        raise ValueError(
            "OCD ID must have at least two segments (e.g., 'ocd-division/country:us/state:wa')"
        )
    return value


OCDIdStr = Annotated[str, AfterValidator(validate_ocdid)]
OCDIdType = Literal["ocd-division", "ocd-jurisdiction"]


def get_ocdid_type(raw_ocdid: OCDIdStr) -> OCDIdType:
    """Derive OCD ID type from the validated OCD ID string."""
    return raw_ocdid.split("/", 1)[0]  # type: ignore[return-value]


class OCDIdParsed(BaseModel):
    """
    Parsed OCDid used for string matching on import records. Handles Division
    OCDids, not Jurisdiction OCDids (which have a slightly different structure)

    Examples:
        - ocd-division/country:us/state:ca
        - ocd-division/country:us/state:ca/county:marin
        - ocd-division/country:us/state:ca/county:marin/place:sausalito
        - ocd-division/country:us/state:wa/place:seattle/council_district:1
        - ocd-division/country:us/msa:multistate-area
        - ocd-division/country:us/state:wa
    """

    model_config = ConfigDict(extra="allow")

    type: Optional[OCDIdType] = Field(
        default=None,
        description="The Open Civic Data identifier namespace: 'ocd-division' or 'ocd-jurisdiction'.",
    )
    country: str = "us"
    state: Optional[str] = None
    county: Optional[str] = None
    place: Optional[str] = None
    subdivision: Optional[str] = None
    raw_ocdid: OCDIdStr = Field(
        description="Validated OCD ID string. Must start with 'ocd-division/' or 'ocd-jurisdiction/' and have at least two segments."
    )

    @model_validator(mode="after")
    def populate_ocdid_type(self) -> "OCDIdParsed":
        derived_type = get_ocdid_type(self.raw_ocdid)
        if self.type is None:
            self.type = derived_type
            return self

        if self.type != derived_type:
            raise ValueError("OCD ID type must match the raw_ocdid prefix")

        return self

    @classmethod
    def parse_ocdid(cls, raw_ocdid: str) -> "OCDIdParsed":
        try:
            ocdid_dict = ocdid_parser(raw_ocdid)
            return cls(**ocdid_dict, raw_ocdid=raw_ocdid)
        except Exception as error:
            raise OCDIdParsingError(error) from error

    @classmethod
    def get_last_segment(cls, ocdid: "OCDIdParsed | OCDIdStr") -> str:
        """
        Extract the last segment from an OCD ID, handling edge cases. This
        handler accepts both parsed OCDidParsed objects and valid OCD ID
        strings.
        """
        raw_ocdid: str = ocdid.raw_ocdid if isinstance(ocdid, cls) else str(ocdid)
        parts = raw_ocdid.rstrip("/").split("/")
        return parts[-1]

    @classmethod
    def build_ancestor_ocdids(cls, parsed_ocdid: "OCDIdParsed") -> list["OCDIdParsed"]:
        """Return ancestor OCD IDs as parsed models, excluding country root and leaf."""
        try:
            parts = parsed_ocdid.raw_ocdid.split("/")
            base = parts[0] if len(parts) > 0 else "ocd-division"
            country_segment = (
                parts[1] if len(parts) > 1 else f"country:{parsed_ocdid.country}"
            )
            hierarchy_segments = parts[2:]

            ancestors: list[OCDIdParsed] = []
            for end in range(1, len(hierarchy_segments)):
                ancestor_segments = "/".join(hierarchy_segments[:end])
                ancestor_ocdid = f"{base}/{country_segment}/{ancestor_segments}"
                ancestors.append(cls.parse_ocdid(ancestor_ocdid))
            return ancestors
        except Exception as error:
            raise OCDIdParsingError(error) from error
