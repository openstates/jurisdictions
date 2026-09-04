from pydantic import BaseModel, Field, ConfigDict, HttpUrl, model_validator
from typing import List, Optional
from datetime import datetime, timezone
from src.models.source import SourceObj
import yaml
from uuid import NAMESPACE_URL, UUID, uuid5
from pathlib import Path
import logging
from src.models.ocdid import OCDIdStr

logger = logging.getLogger(__name__)

PROJECT_PATH = "divisions/"


class Centroid(BaseModel):
    geo_type: str = Field(default="Point")
    coordinates: List[float] = Field(
        ...,
        description="A two-item array defining the centroid (center) of the geometry. Example: [-176.59989528409687, 51.88215100813731]",
    )


class Extent(BaseModel):
    extent: List[float] = Field(
        ...,
        description="Object describing the extents. [left-most, lower-most, right-most, upper-most]",
    )


class Boundary(BaseModel):
    centroid: Optional[Centroid] = None
    extent: Optional[Extent] = None


class Population(BaseModel):
    population: int


class DivisionMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")
    population: Optional[Population] = None


class Identifier(BaseModel):
    """A single external identifier from a specific authority.

    ``value`` is always a string so leading-zero identifiers (Census FIPS,
    GEOIDs, LEA IDs) round-trip exactly.
    """

    authority: str = Field(
        description="Authority/provider slug (e.g. 'census', 'nces', 'dcgis')."
    )
    id_type: str = Field(
        description="Identifier type within the authority (e.g. 'geoid', 'statefp', 'placefp', 'lea')."
    )
    value: str = Field(
        description="Identifier value as a string; leading zeros preserved."
    )
    source: SourceObj = Field(description="Provenance for this identifier.")


Identifiers = list[Identifier]


def find_identifier(
    identifiers: Identifiers | None,
    id_type: str,
    authority: str = "census",
) -> str | None:
    """Return the first matching identifier value, or None."""
    if not identifiers:
        return None
    for ident in identifiers:
        if ident.authority == authority and ident.id_type == id_type:
            return ident.value
    return None


class Geometry(BaseModel):
    """A provider-neutral, temporally-scoped reference to a boundary geometry.

    A Division keeps its stable identity while its geometry changes over time
    (rework §21), so a Division carries a list of these versions. Each version
    owns its validity window, its retrieval URL, its external identifiers, and
    its own provenance. ArcGIS/TIGERweb is one provider among several, not the
    abstraction (rework §18).
    """

    valid_from: datetime | None = Field(
        default=None,
        description="Best approximation of the date this boundary became effective. None for an open-ended start.",
    )
    valid_to: datetime | None = Field(
        default=None,
        description="Best approximation of the date this boundary was replaced or made obsolete. None for a current boundary.",
    )
    boundary: Boundary = Field(
        ..., description="The centroid and extent of the geometry."
    )
    url: HttpUrl | None = Field(
        default=None,
        description="Provider-neutral retrieval URL for this geometry (e.g. a GeoJSON query endpoint). Ideally granular to the layer defined by the division id.",
    )
    identifiers: Identifiers | None = Field(
        default=None,
        description="External identifiers for this geometry (Census GEOID, DCGIS ANC ID, etc.). Each entry carries its own SourceObj.",
    )
    source: SourceObj | None = Field(
        default=None,
        description="Provenance for this geometry version — which dataset/release it was retrieved from.",
    )


def sort_geometries(geometries: list[Geometry] | None) -> list[Geometry]:
    """Return geometry versions ordered oldest-first by ``valid_from``.

    An open-ended (``None``) ``valid_from`` sorts first: an unbounded start
    precedes every dated one. Ordering is stable, so equal ``valid_from``
    values keep their input order and serialization stays deterministic
    (rework §32).
    """
    if not geometries:
        return []
    return sorted(
        geometries,
        key=lambda geometry: (
            geometry.valid_from is not None,
            geometry.valid_from or datetime.min.replace(tzinfo=timezone.utc),
        ),
    )


class Division(BaseModel):
    id: UUID | None = Field(
        default=None, description="UUID5 derived from ocdid and generation date."
    )
    ocdid: OCDIdStr = Field(
        ...,
        description="The canonical OpenCivicData id for the political geo division. Should be sourced from the Open Civic Data repo (https://github.com/opencivicdata/ocd-division-ids). Example: ocd-division/country:us/state:wa/place:seattle/",
    )
    country: str = Field(
        ..., description="Two-letter ISO-3166 alpha-2 country code. (e.g. 'us', 'ca')"
    )
    display_name: str = Field(
        ...,
        description="Human-readable name for division. Should be sourced from the Open Civic Data repo.",
    )
    geometries: Optional[List[Geometry]] = Field(
        default_factory=list,
        description="A list of associated geometries, as defined by the Geometry model. Empty array if not set.",
    )
    also_known_as: List[str] = Field(
        default_factory=list,
        description="A list of alternate formatted OCDids that refer to the same geo political divisions.",
    )
    children: List[OCDIdStr] = Field(
        default_factory=list,
        description="A list of child division ids — the OCDids of the Divisions contained by this one. Validated as OCDids. Projects to the PARENT_OF graph edge.",
    )
    valid_thru: Optional[datetime] = Field(
        default=None,
        description="If a division is set to be retired, use this date to indicate when the division is no longer valid.",
    )
    valid_asof: Optional[datetime] = Field(
        default=None,
        description="If a new division is created use this date to indicate when the division will become active.",
    )
    accurate_asof: Optional[datetime] = Field(
        default=None,
        description="The datetime ('2025-05-01:00:00:00' ISO 8601 standard format when the data for the record is known to be accurate by the researcher. This may or may not be the same data as the 'last_updated' date below.",
    )
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="The datetime that the data in the record was last updated by the researcher (or it's agent).",
    )
    sourcing: List[SourceObj] = Field(
        default_factory=list,
        description="Describe how the data was sourced. Used to identify AI generated data.",
    )
    metadata: Optional[DivisionMetadata] = Field(
        None,
        description="Any other useful information that a researcher feels should be included.",
    )
    government_identifiers: Optional[Identifiers] = Field(
        None,
        description="Provider-neutral list of external identifiers (Census FIPS/GEOIDs, LEA IDs, DCGIS ANC IDs, etc.). Each entry carries its own SourceObj.",
    )
    jurisdiction_id: str

    @model_validator(mode="after")
    def ensure_uuid5_id(self):
        if self.id is None:
            asof_date = self.last_updated.astimezone(timezone.utc).date().isoformat()
            self.id = uuid5(NAMESPACE_URL, f"{self.ocdid}|{asof_date}")
        return self

    # Untested
    @classmethod
    def load_division(cls, filepath):
        try:
            data = yaml.safe_load(filepath)
            cls = cls(**data)
        except Exception as error:
            logger.error(
                "Failed to load division object", extras={"error": error}, exc_info=True
            )
            raise ValueError("Failed to load division. Check filepath") from error

    # Untested
    def dump_division(self, base_dir: str | Path = PROJECT_PATH):
        geoid = find_identifier(self.government_identifiers, "geoid")
        if not geoid:
            raise ValueError("A census geoid identifier is required to store a division object.")
        base_path = Path(base_dir)
        base_path.mkdir(parents=True, exist_ok=True)
        filepath = base_path / f"{self.display_name}_{geoid}_{self.id}.yaml"
        data = self.model_dump(exclude_none=False, mode="json")
        with open(filepath, "w") as f:
            yaml.safe_dump(data, f)
        return filepath

    def flatten(self) -> dict:
        """A method for converting a nested Division object, to a flat record(s) in LongTidy format for export to csv."""
        raise NotImplementedError

    def to_csv(self, include_children: bool = True) -> str:
        """A method to export the flattend record(s) to .csv"""
        raise NotImplementedError
