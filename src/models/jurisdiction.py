import logging
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from uuid import UUID

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from src.models.administrative_level import AdministrativeLevelName
from src.models.contact import ContactDetail
from src.models.division import (
    Identifiers,
    missing_item_citations,
)
from src.models.ocdid import OCDIdParsed, OCDIdStr, get_ocdid_type
from src.utils.datetime import ymd
from src.utils.deterministic_id import generate_id

from .organization import Organization, organization_id
from .post import post_id
from .source import Sourcing

logger = logging.getLogger(__name__)


PROJECT_PATH = "jurisdictions/"


# Session factories with exact dates
def session_calendar_year(year: int) -> "SessionDetail":
    return SessionDetail(
        name=str(year),
        classification="primary",
        start_date=ymd(year, 1, 1),
        end_date=ymd(year, 12, 31),
    )


def session_span(name_slug: str, start: datetime, end: datetime) -> "SessionDetail":
    return SessionDetail(
        name=name_slug,
        classification="primary",
        start_date=start,
        end_date=end,
    )


# United states only
class ClassificationEnum(str, Enum):
    """Kinds of government a Jurisdiction can be.

    A Jurisdiction is a government: the entity that governs a Division.
    Branches, bodies, and offices within it (legislature and its chambers,
    executive, courts, prosecutors, commissions) are Organizations.
    """

    GOVERNMENT = "government"  # e.g. a city, county, or state government
    SCHOOL_SYSTEM = (
        "school_system"  # e.g. a school district or community college district
    )
    TRANSIT_AUTHORITY = (
        "transit_authority"  # e.g. Port Authority of New York and New Jersey
    )
    SPECIAL_PURPOSE_DISTRICT = "special_purpose_district"  # e.g. fire, water, or park districts with their own governing body
    ADVISORY_BOARD = "advisory_board"  # e.g. an elected advisory council for a county subdivision under county fiscal oversight


class URLEnum(str, Enum):
    """These are the allowed defined types for jurisdiction urls"""

    PEOPLE = "people"
    MEETINGS = "meetings"


class URLObject(BaseModel):
    """A URL object for defining known url types for a jurisdiction."""

    url_type: URLEnum = Field(..., description="The type of url being defined.")
    description: str | None = Field(
        default=None,
        description="Optional description of the URL.",
    )
    url: HttpUrl = Field(
        ...,
        description="The url associated with the url type. Validated as an http(s) URL.",
    )


class JurisdictionMetadata(BaseModel):
    """Optional, typed facts about a Jurisdiction.

    Extra keys are allowed so third parties can attach their own lookups and
    comments.
    """

    model_config = ConfigDict(extra="allow")
    urls: list[URLObject] = Field(
        default_factory=list,
        description="List of URLs related to the jurisdiction.",
    )


class SessionDetail(BaseModel):
    """Appears in the 'legislative_sessions' as a value for each session key."""

    name: str = Field(
        ...,
        description="Name of session, typically a year span like 2011-2012. **(required)**",
    )
    identifiers: Identifiers | None = Field(
        default=None,
        description="Ids for the session, e.g. authority 'openstates', id_type 'session'.",
    )
    classification: str = Field(..., description="Type of session: primary or special")
    start_date: datetime = Field(..., description="Start date of session.")
    end_date: datetime = Field(..., description="End date of session.")


class Jurisdiction(BaseModel):
    """A government that governs a Division.

    Populated by: this pipeline.

    Reference: https://github.com/opencivicdata/docs.opencivicdata.org/blob/master/data/datatypes.rst#id3
    """

    id: UUID | None = Field(
        default=None,
        description="UUID5 derived from the ocdid alone. Stable across regenerations: no other field, including last_updated, affects it. Derived when omitted.",
    )
    ocdid: OCDIdStr = Field(
        ...,
        description="Jurisdictions IDs take the form ocd-jurisdiction/<jurisdiction_id>/<jurisdiction_type> where jurisdiction_id is the ID for the related division without the ocd-division/ prefix and jurisdiction_type is council, legislature, etc.",
    )
    administrative_level: AdministrativeLevelName | None = Field(
        default=None,
        description="Level of government this jurisdiction operates at, using the Google Civic Information API levels vocabulary (e.g. country, administrativeArea1, locality). A jurisdiction governing a subdivision (council district, ward) takes the level of the unit that governs it.",
    )
    name: str = Field(
        ...,
        description="Name of jurisdiction (e.g. North Carolina General Assembly). Should be sourced from official gov source data (i.e. Census) **(required)**",
    )
    display_name: str | None = Field(
        default=None,
        description="Display name of the jurisdiction, which may differ from the official name.",
    )
    contact_details: list[ContactDetail] = Field(
        default_factory=list,
        description="Contact details for the government itself, e.g. city hall's address and main phone.",
    )
    url: HttpUrl | None = Field(
        default=None,
        description="URL pointing to jurisdiction's website, if known. Validated as an http(s) URL. None when no official website has been resolved — website resolution is a separate enrichment concern and its absence must not invalidate an otherwise valid Jurisdiction.",
    )
    classification: ClassificationEnum = Field(
        ...,
        description="A jurisdiction category. **(required)** See ClassificationEnum.",
    )
    identifiers: Identifiers | None = Field(
        default=None,
        description="External identifiers for the government entity, e.g. the Census government-unit ID (authority 'census', id_type 'gu_id').",
    )
    legislative_sessions: dict[str, SessionDetail] = Field(
        default_factory=dict,
        description="Dictionary describing sessions, each key is a session slug that must also appear in one ``sessions`` list in ``terms``.  Values consist of several fields giving more detail about the session. **(required)**",
    )
    feature_flags: list[str] = Field(
        default_factory=list,
        description="A way to mark certain features as available on a per-jurisdiction basis. Each element in feature_flags is of type (string) **(required, minItems: 0)** ",
    )
    valid_from: datetime | None = Field(
        default=None,
        description="Date the government was, or will be, established. None for an open-ended start.",
    )
    valid_to: datetime | None = Field(
        default=None,
        description="Date the government was, or will be, dissolved or merged. None while active.",
    )
    accurate_asof: datetime = Field(
        description="The datetime ('2025-05-01:00:00:00' ISO 8601 standard format when the data for the record is known to be accurate by the researcher. This may or may not be the same data as the 'last_updated' date below.",
    )
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="The datetime that the data in the record was last updated by the researcher (or it's agent).",
    )
    sourcing: Sourcing = Field(
        default_factory=Sourcing,
        description="Provenance for this record, indexed by dotted field path. Used to identify AI generated data.",
    )
    organizations: list[Organization] = Field(
        default_factory=list,
        description="The organizing bodies that govern a jurisdiction. Examples: City Council Committee, Parks and Recreation, Library Board, etc.",
    )
    governing_charter: HttpUrl | None = Field(
        default=None,
        description="The legal written policy document that clearly defines the respective roles, responsibilities and authorities of the jurisdiction. Example: City Charter, State Constitution, etc.",
    )
    metadata: JurisdictionMetadata | None = Field(
        default=None,
        description="Any other useful information that a researcher feels should be included.",
    )

    @model_validator(mode="after")
    def check_validity_window(self) -> "Jurisdiction":
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to < self.valid_from
        ):
            raise ValueError("valid_to cannot be before valid_from")
        return self

    @model_validator(mode="after")
    def link_organizations(self) -> "Jurisdiction":
        """Fill each organization's jurisdiction_id and id, and check parent links."""
        for organization in self.organizations or []:
            if organization.jurisdiction_id is None:
                organization.jurisdiction_id = self.ocdid
            elif organization.jurisdiction_id != self.ocdid:
                raise ValueError(
                    f"Organization {organization.name!r} belongs to "
                    f"{organization.jurisdiction_id!r}, not {self.ocdid!r}"
                )
            if organization.id is None:
                organization.id = organization_id(
                    self.ocdid, organization.name, organization.parent_id
                )
            labels: set[str] = set()
            for post in organization.posts or []:
                if post.label in labels:
                    raise ValueError(
                        f"Organization {organization.name!r} has more than one "
                        f"post labelled {post.label!r}"
                    )
                labels.add(post.label)
                if post.organization_id is None:
                    post.organization_id = organization.id
                elif post.organization_id != organization.id:
                    raise ValueError(
                        f"Post {post.label!r} belongs to organization "
                        f"{post.organization_id}, not {organization.name!r}"
                    )
                if post.id is None:
                    post.id = post_id(organization.id, post.label)
        seen: dict[UUID, str] = {}
        for organization in self.organizations or []:
            if organization.id in seen:
                raise ValueError(
                    f"Organizations {seen[organization.id]!r} and "
                    f"{organization.name!r} share an id: the same name under the "
                    "same parent in one jurisdiction"
                )
            seen[organization.id] = organization.name
        ids = set(seen)
        for organization in self.organizations or []:
            if organization.parent_id is not None and organization.parent_id not in ids:
                raise ValueError(
                    f"Organization {organization.name!r} has a parent_id that is "
                    "not an organization of this jurisdiction"
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
        missing += missing_item_citations(
            self.sourcing, "organizations", {(str(org_id),) for org_id in ids}
        )
        if missing:
            raise ValueError(
                f"Sourcing cites items this Jurisdiction does not have: {', '.join(missing)}"
            )
        return self

    @model_validator(mode="after")
    def validate_jurisdiction_id(self) -> "Jurisdiction":
        """Jurisdictions IDs take the form
        ocd-jurisdiction/<jurisdiction_id>/<jurisdiction_type> where
        jurisdiction_id is the ID for the related division without the
        ocd-division/ prefix and jurisdiction_type is council, legislature, as
        defined in the ClassificationEnum. This validator checks that the ocdid field is compliant with this structure and raises an error if not."""
        if get_ocdid_type(self.ocdid) != "ocd-jurisdiction":
            raise ValueError(
                "Jurisdiction ocdid must use the 'ocd-jurisdiction' prefix"
            )

        jurisdiction_type = OCDIdParsed.get_jurisdiction_classification(self.ocdid)
        if jurisdiction_type != self.classification.value:
            raise ValueError(
                "Jurisdiction ocdid suffix must match the classification value"
            )

        return self

    @model_validator(mode="after")
    def ensure_uuid5_id(self):
        if self.id is None:
            self.id = generate_id(self.ocdid)
        return self

    @classmethod
    def load_jurisdiction(cls, filepath: str | Path) -> "Jurisdiction":
        try:
            data = yaml.safe_load(Path(filepath).read_text())
            return cls(**data)
        except Exception as error:
            logger.exception(
                "Failed to load jurisdiction object",
                extra={"filepath": str(filepath)},
            )
            raise ValueError("Failed to load jurisdiction. Check filepath") from error

    def dump_jurisdiction(self, base_dir: str | Path = PROJECT_PATH):
        base_path = Path(base_dir)
        base_path.mkdir(parents=True, exist_ok=True)
        filepath = base_path / f"{self.name}_{self.id}.yaml"
        # Convert model to dict using JSON mode to convert enums to strings
        data = self.model_dump(exclude_none=False, mode="json")
        with open(filepath, "w") as f:
            yaml.safe_dump(data, f, sort_keys=False)
        return filepath

    def flatten(self) -> dict:
        """A method for converting a nested Jurisdiction object, to a flat record(s) in LongTidy format for export to csv."""
        raise NotImplementedError

    def to_csv(self) -> str:
        """A method to export the flattend record(s) to .csv"""
        raise NotImplementedError
