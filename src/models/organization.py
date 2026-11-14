from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

from src.models.contact import ContactDetail
from src.models.division import Identifiers
from src.models.ocdid import OCDIdStr, get_ocdid_type
from src.models.post import Post
from src.utils.deterministic_id import generate_id


class OrganizationClassificationEnum(str, Enum):
    """Popolo-compliant organization classification types.

    Reference: https://www.popoloproject.com/specs/organization.html
    """

    # Government entities
    GOVERNMENT = "government"
    LEGISLATURE = "legislature"
    UPPER = "upper"  # upper chamber of a bicameral legislature, e.g. a state senate
    LOWER = "lower"  # lower chamber of a bicameral legislature, e.g. a state house
    EXECUTIVE = "executive"
    JUDICIARY = "judiciary"

    # Bodies and subdivisions
    LEGISLATIVE_BODY = "legislative_body"
    DEPARTMENT = "department"
    AGENCY = "agency"
    AUTHORITY = "authority"

    # Committees and boards
    COMMITTEE = "committee"
    BOARD = "board"
    COMMISSION = "commission"
    ADVISORY_BOARD = "advisory_board"

    # Political parties, referenced by Membership.on_behalf_of_id
    PARTY = "party"


class TermRules(BaseModel):
    """How terms work for the seats of one body, as set by charter or statute."""

    model_config = ConfigDict(extra="forbid")

    length_years: int | None = Field(
        default=None, ge=1, description="Length of one term, in years."
    )
    staggered: bool | None = Field(
        default=None,
        description="True when the body's seats are not all elected at the same election.",
    )
    max_consecutive_terms: int | None = Field(
        default=None,
        ge=1,
        description="Most consecutive terms one person may serve. None when unlimited or unknown.",
    )
    description: str | None = Field(
        default=None,
        description="The charter or statute's own wording on terms and limits.",
    )
    last_known_term_end_date: datetime | None = Field(
        default=None,
        description="End of the most recent known term, from which later term dates can be computed.",
    )


def organization_id(
    jurisdiction_id: str, name: str, parent_id: UUID | None = None
) -> UUID:
    """UUID5 for an organization, derived from its jurisdiction, parent, and name.

    A top-level organization (no parent) is keyed by jurisdiction and name; a
    nested one also by its parent, so same-named committees of different
    bodies stay distinct.
    """
    if parent_id is None:
        return generate_id(f"{jurisdiction_id}/organization:{name}")
    return generate_id(f"{jurisdiction_id}/organization:{parent_id}/{name}")


class Organization(BaseModel):
    """A body within a government, or a party.

    Populated by: this pipeline.

    Example organizations: City Council, Mayor's Office, Parks Department,
    Planning Commission, County Board of Supervisors, etc.

    Provenance is cited in the owning Jurisdiction's sourcing under
    ``organizations.<id>``.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID | None = Field(
        default=None,
        description="UUID5 derived from jurisdiction_id and name. Derived by the owning Jurisdiction when omitted.",
    )
    jurisdiction_id: OCDIdStr | None = Field(
        default=None,
        description="OCD ID of the Jurisdiction this organization belongs to. Set by the owning Jurisdiction when omitted.",
    )
    parent_id: UUID | None = Field(
        default=None,
        description="id of the organization this one sits under, e.g. a committee's council. None for a top-level organization.",
    )
    name: str
    classification: OrganizationClassificationEnum | None = Field(
        default=None,
        description="An organization category. See OrganizationClassificationEnum.",
    )
    other_names: list[str] = Field(
        default_factory=list,
        description="Commonly used names for the organization, if different from the official name. Provide as a list of strings to support search functionality and matching.",
    )
    identifiers: Identifiers | None = Field(
        default=None,
        description="Ids in other systems, e.g. an FEC committee id or a Census government-unit id.",
    )
    url: HttpUrl | None = Field(
        None,
        description="URL pointing to organization's official website. Internal links within government websites to a specific page permitted.",
    )
    contact_details: list[ContactDetail] = Field(
        default_factory=list,
        description="Contact details for the body, e.g. the council clerk's phone or a board's email.",
    )
    posts: list[Post] | None = Field(
        default=None,
        description="Seats in this organization, e.g. council districts and at-large positions.",
    )
    total_seats: int | None = Field(
        default=None,
        ge=1,
        description="Number of positions on this body, e.g. 9 for a nine-member council, 1 for a mayor.",
    )
    district_seats: int | None = Field(
        default=None, ge=0, description="Positions elected by district."
    )
    at_large_seats: int | None = Field(
        default=None, ge=0, description="Positions elected at large."
    )
    selection: Literal["elected", "appointed", "mixed"] | None = Field(
        default=None, description="How the body's members are chosen."
    )
    term: TermRules | None = Field(
        default=None, description="Term rules for this body's seats."
    )
    valid_from: datetime | None = Field(
        default=None,
        description="Date the body was, or will be, established. None for an open-ended start.",
    )
    valid_to: datetime | None = Field(
        default=None,
        description="Date the body was, or will be, dissolved. None while active.",
    )

    @field_validator("jurisdiction_id")
    @classmethod
    def jurisdiction_id_is_a_jurisdiction(cls, value: str | None) -> str | None:
        if value is not None and get_ocdid_type(value) != "ocd-jurisdiction":
            raise ValueError("jurisdiction_id must use the 'ocd-jurisdiction' prefix")
        return value

    @model_validator(mode="after")
    def derive_id(self) -> "Organization":
        """Derive the id when the jurisdiction is known.

        An organization nested in a Jurisdiction gets its jurisdiction_id, and
        so its id, from the Jurisdiction.
        """
        if self.id is None and self.jurisdiction_id is not None:
            self.id = organization_id(self.jurisdiction_id, self.name, self.parent_id)
        return self

    @model_validator(mode="after")
    def check_validity_window(self) -> "Organization":
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to < self.valid_from
        ):
            raise ValueError("valid_to cannot be before valid_from")
        return self

    @model_validator(mode="after")
    def check_seat_counts(self) -> "Organization":
        if (
            self.total_seats is not None
            and (self.district_seats or 0) + (self.at_large_seats or 0)
            > self.total_seats
        ):
            raise ValueError("district_seats and at_large_seats exceed total_seats")
        return self
