"""A person's term in a seat or body.

Memberships are dynamic data: the pipeline does not create them. The model
exists so applications can attach who holds a seat to the stable graph.
Field names follow the Popolo and Open Civic Data Membership and the Open
States role, so records exchange with those projects.

Reference: https://www.popoloproject.com/specs/membership.html
"""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.models.contact import ContactDetail, Link
from src.models.dates import PartialDate
from src.models.source import Sourcing
from src.utils.deterministic_id import generate_id


def membership_id(
    person_id: UUID,
    organization_id: UUID | None,
    post_id: UUID | None,
    valid_from: str | None,
) -> UUID:
    """UUID5 for a membership, derived from who, where, and when it began."""

    return generate_id(
        f"membership:{person_id}/{organization_id or ''}/{post_id or ''}/{valid_from or ''}"
    )


class Membership(BaseModel):
    """A Person's membership in an Organization, usually holding one of its Posts.

    Populated by: applications. Dynamic data this pipeline never fills.

    The edges Person→Post, Person→Organization, and Person→party are stored
    here, once: a Person, Post, or Organization does not list its memberships.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID | None = Field(
        default=None,
        description="UUID5 derived from person_id, organization_id, post_id, and valid_from. Derived when omitted.",
    )
    person_id: UUID = Field(description="id of the Person.")
    organization_id: UUID | None = Field(
        default=None, description="id of the Organization the person is a member of."
    )
    post_id: UUID | None = Field(
        default=None, description="id of the Post (seat) the person holds."
    )
    on_behalf_of_id: UUID | None = Field(
        default=None,
        description="id of the Organization the person represents in this role, usually a party.",
    )
    role: str | None = Field(
        default=None, description="Role held, e.g. 'Councilmember', 'Chair'."
    )
    label: str | None = Field(default=None, description="Human-readable label.")
    valid_from: PartialDate | None = Field(
        default=None,
        description="Date the membership began (YYYY, YYYY-MM, or YYYY-MM-DD).",
    )
    valid_to: PartialDate | None = Field(
        default=None, description="Date the membership ended. None while current."
    )
    end_reason: str | None = Field(
        default=None, description="Why it ended, e.g. 'term ended', 'resigned'."
    )
    contact_details: list[ContactDetail] = Field(
        default_factory=list,
        description="Contact details that belong to the seat while held, e.g. a council office.",
    )
    links: list[Link] = Field(default_factory=list)
    accurate_asof: datetime | None = Field(
        default=None, description="When the record was known to be accurate."
    )
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sourcing: Sourcing = Field(
        default_factory=Sourcing,
        description="Provenance for this record, indexed by dotted field path.",
    )

    @model_validator(mode="after")
    def check_membership(self) -> "Membership":
        if self.organization_id is None and self.post_id is None:
            raise ValueError("A membership needs an organization_id or post_id")
        if (
            self.valid_from
            and self.valid_to
            and self.valid_to < self.valid_from[: len(self.valid_to)]
        ):
            raise ValueError("valid_to precedes valid_from")
        if self.id is None:
            self.id = membership_id(
                self.person_id, self.organization_id, self.post_id, self.valid_from
            )
        self.sourcing.check_paths(type(self))
        return self
