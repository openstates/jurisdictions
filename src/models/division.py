import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    RootModel,
    model_serializer,
    model_validator,
)

from src.models.administrative_level import DivisionClassificationEnum
from src.models.ocdid import OCDIdParsed, OCDIdStr, get_ocdid_type
from src.models.source import Sourcing
from src.utils.deterministic_id import generate_id

logger = logging.getLogger(__name__)

PROJECT_PATH = "divisions/"


class Centroid(BaseModel):
    geo_type: str = Field(default="Point")
    coordinates: list[float] = Field(
        ...,
        min_length=2,
        max_length=2,
        description="[longitude, latitude] of the centroid (center) of the geometry. Example: [-176.59989528409687, 51.88215100813731]",
    )


class Extent(BaseModel):
    extent: list[float] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Bounding box: [west, south, east, north] (left-most, lower-most, right-most, upper-most).",
    )


class Boundary(BaseModel):
    centroid: Centroid | None = None
    extent: Extent | None = None


class Population(BaseModel):
    """A population count and the date it describes.

    Its provenance is cited in the record's sourcing under ``metadata.population``.
    """

    value: int | None = Field(default=None, description="Number of residents.")
    as_of: datetime | None = Field(
        default=None,
        description="Date the count describes, e.g. the estimate or census year.",
    )


class DivisionMetadata(BaseModel):
    """Optional, typed facts about a Division.

    Extra keys are allowed so third parties can attach their own lookups and
    comments.
    """

    model_config = ConfigDict(extra="allow")
    population: Population | None = Field(
        default=None, description="Population of the division."
    )


class Identifier(BaseModel):
    """A single external identifier from a specific authority.

    ``value`` is always a string so leading-zero identifiers (Census FIPS,
    GEOIDs, LEA IDs) are not mutated. Provenance is cited in the owning
    record's sourcing under ``<field>.<authority>.<id_type>``.
    """

    model_config = ConfigDict(extra="forbid")

    authority: str = Field(
        description="Authority/provider slug (e.g. 'census', 'nces', 'dcgis')."
    )
    id_type: str = Field(
        description="Identifier type within the authority (e.g. 'geoid', 'statefp', 'placefp', 'lea')."
    )
    value: str = Field(
        description="Identifier value as a string; leading zeros preserved."
    )


IdentifierKey = tuple[str, str]


class Identifiers(RootModel[dict[IdentifierKey, list[Identifier]]]):
    """External identifiers indexed by ``(authority, id_type)``.

    Validates from and serializes to a flat list of ``Identifier`` so the
    YAML shape is a list. A key may hold several entries (e.g. a division
    carrying two ``sldlst`` codes); entries sharing a key serialize
    together, in first-seen key order.
    """

    root: dict[IdentifierKey, list[Identifier]] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def index_by_key(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return data
        indexed: dict[IdentifierKey, list[Identifier]] = {}
        for item in data:
            identifier = Identifier.model_validate(item)
            key = (identifier.authority, identifier.id_type)
            indexed.setdefault(key, []).append(identifier)
        return indexed

    @model_serializer
    def serialize_as_list(self) -> list[Identifier]:
        return list(self)

    def __iter__(self) -> Iterator[Identifier]:  # type: ignore[override]
        for entries in self.root.values():
            yield from entries

    def __len__(self) -> int:
        return sum(len(entries) for entries in self.root.values())

    def __getitem__(self, key: IdentifierKey) -> list[Identifier]:
        return self.root[key]

    def __contains__(self, key: object) -> bool:
        return key in self.root

    def get(self, id_type: str, authority: str = "census") -> Identifier | None:
        """Return the first entry for ``(authority, id_type)``, or None."""
        entries = self.root.get((authority, id_type))
        return entries[0] if entries else None


def find_identifier(
    identifiers: Identifiers | list[Identifier] | None,
    id_type: str,
    authority: str = "census",
) -> str | None:
    """Return the matching identifier value, or None."""
    if not identifiers:
        return None
    indexed = (
        identifiers
        if isinstance(identifiers, Identifiers)
        else Identifiers.model_validate(identifiers)
    )
    identifier = indexed.get(id_type, authority)
    return identifier.value if identifier else None


def missing_item_citations(
    sourcing: Sourcing, field: str, keys: set[tuple[str, ...]]
) -> list[str]:
    """Sourcing paths under ``field`` that name an item the record does not have.

    An item is addressed by the path segments after ``field``, e.g.
    ``identifiers.census.geoid`` → ``("census", "geoid")``. A
    shorter path cites every item it prefixes (``identifiers.census``).
    """
    missing = []
    for path in sourcing.fields:
        if not path.startswith(f"{field}."):
            continue
        item = tuple(path.split(".")[1:])
        if not any(key[: len(item)] == item[: len(key)] for key in keys):
            missing.append(path)
    return missing


class Geometry(BaseModel):
    """A provider-neutral reference to a boundary geometry from one series.

    A Division file holds geometry from a single Census series; boundary
    history is kept by versioning files across runs, not on the record.
    Several geometries on one Division are parts of the same boundary and
    share one validity window. Provenance is cited in the Division's sourcing
    under ``geometries``.
    """

    model_config = ConfigDict(extra="forbid")

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

    @model_validator(mode="after")
    def check_validity_window(self) -> "Geometry":
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to < self.valid_from
        ):
            raise ValueError("valid_to cannot be before valid_from")
        return self


class Division(BaseModel):
    """A geo-political division: an area identified by an OCD Division id.

    Populated by: this pipeline.
    """

    id: UUID | None = Field(
        default=None,
        description="UUID5 derived from the ocdid alone. Stable across regenerations.",
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
    other_names: list[str] = Field(
        default_factory=list,
        description="A list of alternate display names that refer to the same geo political division.",
    )
    classification: DivisionClassificationEnum | None = Field(
        default=None,
        description="The OCD segment type of this division: the type in the last segment of its ocdid (place, county, ward, anc, ...). Derived from the ocdid when omitted. Census subtypes (incorporated place vs CDP, town vs township) belong in identifiers (census.lsad).",
    )
    geometries: list[Geometry] = Field(
        default_factory=list,
        description="Geometries from one series: the parts of this division's boundary. All share one validity window. Empty array if not set.",
    )
    valid_from: datetime | None = Field(
        default=None,
        description="Date the division became, or will become, active. None for an open-ended start.",
    )
    valid_to: datetime | None = Field(
        default=None,
        description="Date the division was, or will be, retired. None while active.",
    )
    accurate_asof: datetime = Field(
        description="The datetime ('2025-05-01:00:00:00' ISO 8601 standard format when the data for the record is known to be accurate by the researcher. This may or may not be the same data as the 'last_updated' date below.",
    )
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="The datetime that the data in the record was last updated by the researcher (or it's agent).",
    )
    identifiers: Identifiers | None = Field(
        None,
        description="Provider-neutral list of external identifiers (Census FIPS/GEOIDs, LEA IDs, DCGIS ANC IDs, etc.). A Census GEOID is unique only within its layer; join on census.geoidfq. See docs/census_identifiers.md.",
    )
    sourcing: Sourcing = Field(
        default_factory=Sourcing,
        description="Provenance for this record, indexed by dotted field path. Used to identify AI generated data.",
    )
    metadata: DivisionMetadata | None = Field(
        None,
        description="Any other useful information that a researcher feels should be included.",
    )
    jurisdiction_id: OCDIdStr | None = Field(
        default=None,
        description="OCD ID of the Jurisdiction that governs this division. The only record of the Division→Jurisdiction relationship.",
    )

    @model_validator(mode="after")
    def check_references(self) -> "Division":
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to < self.valid_from
        ):
            raise ValueError("valid_to cannot be before valid_from")
        parsed = OCDIdParsed.parse_ocdid(self.ocdid)
        if parsed.type != "ocd-division":
            raise ValueError("Division ocdid must use the 'ocd-division' prefix")
        if self.country != parsed.country:
            raise ValueError(
                f"country {self.country!r} does not match the ocdid country {parsed.country!r}"
            )
        leaf_type = parsed.get_segments()[-1][0]
        known = {member.value for member in DivisionClassificationEnum}
        if self.classification is None:
            if leaf_type in known:
                self.classification = DivisionClassificationEnum(leaf_type)
        elif self.classification.value != leaf_type:
            raise ValueError(
                f"classification {self.classification.value!r} does not match the "
                f"ocdid segment type {leaf_type!r}"
            )
        if self.jurisdiction_id and get_ocdid_type(self.jurisdiction_id) != (
            "ocd-jurisdiction"
        ):
            raise ValueError("jurisdiction_id must use the 'ocd-jurisdiction' prefix")
        windows = {(g.valid_from, g.valid_to) for g in self.geometries or []}
        if len(windows) > 1:
            raise ValueError(
                "geometries must come from one series and share one validity "
                "window; boundary history belongs in versioned files"
            )
        self.sourcing.check_paths(type(self))
        missing = missing_item_citations(
            self.sourcing,
            "identifiers",
            {
                (identifier.authority, identifier.id_type)
                for identifier in self.identifiers or []
            },
        )
        missing += missing_item_citations(self.sourcing, "geometries", set())
        if missing:
            raise ValueError(
                f"Sourcing cites items this Division does not have: {', '.join(missing)}"
            )
        return self

    @model_validator(mode="after")
    def ensure_uuid5_id(self):
        if self.id is None:
            self.id = generate_id(self.ocdid)
        return self

    @property
    def parent_ocdid(self) -> str | None:
        """OCD ID of the containing Division, derived from this one's ocdid.

        The parent→child edge is not stored; it is derived from each child.
        None for a country.
        """
        parts = OCDIdParsed.parse_ocdid(self.ocdid).get_ocdid_parts()
        return "/".join(parts[:-1]) if len(parts) > 2 else None

    @classmethod
    def load_division(cls, filepath: str | Path) -> "Division":
        try:
            data = yaml.safe_load(Path(filepath).read_text())
            return cls(**data)
        except Exception as error:
            logger.exception(
                "Failed to load division object",
                extra={"filepath": str(filepath)},
            )
            raise ValueError("Failed to load division. Check filepath") from error

    def dump_division(self, base_dir: str | Path = PROJECT_PATH):
        geoid = find_identifier(self.identifiers, "geoid")
        if not geoid:
            raise ValueError(
                "A census geoid identifier is required to store a division object."
            )
        base_path = Path(base_dir)
        base_path.mkdir(parents=True, exist_ok=True)
        filepath = base_path / f"{self.display_name}_{geoid}_{self.id}.yaml"
        data = self.model_dump(exclude_none=False, mode="json")
        with open(filepath, "w") as f:
            yaml.safe_dump(data, f, sort_keys=False)
        return filepath

    def flatten(self) -> dict:
        """A method for converting a nested Division object, to a flat record(s) in LongTidy format for export to csv."""
        raise NotImplementedError

    def to_csv(self, include_children: bool = True) -> str:
        """A method to export the flattend record(s) to .csv"""
        raise NotImplementedError
