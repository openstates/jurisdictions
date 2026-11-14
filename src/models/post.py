from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.models.contact import ContactDetail
from src.models.ocdid import OCDIdStr, get_ocdid_type
from src.utils.deterministic_id import generate_id


def post_id(organization_id: UUID, label: str) -> UUID:
    """UUID5 for a post, derived from its organization and label."""

    return generate_id(f"{organization_id}/post:{label}")


class Post(BaseModel):
    """A seat in an Organization, e.g. "District 1" on a city council.

    Populated by: this pipeline.

    Follows the Popolo/Open Civic Data Post: a post cannot exist outside an
    organization. ``division_id`` is the district the seat represents, usually
    a representation subdivision (council district, ward, sldu). A person's
    term in the seat is a membership, not part of the Post.

    Provenance is cited in the owning Jurisdiction's sourcing under
    ``organizations.<organization id>.posts.<post id>``.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID | None = Field(
        default=None,
        description="UUID5 derived from organization_id and label. Derived by the owning Jurisdiction when omitted.",
    )
    organization_id: UUID | None = Field(
        default=None,
        description="id of the Organization this seat belongs to. Set by the owning Jurisdiction when omitted.",
    )
    label: str = Field(
        description="Name of the seat, unique within its organization, e.g. 'District 1' or 'Position 8 (At-Large)'."
    )
    role: str | None = Field(
        default=None,
        description="Title of the person holding the seat, e.g. 'Councilmember', 'Mayor'.",
    )
    division_id: OCDIdStr | None = Field(
        default=None,
        description="OCD ID of the Division this seat represents. None when the seat represents the whole jurisdiction (at-large).",
    )
    contact_details: list[ContactDetail] = Field(
        default_factory=list,
        description="Contact details for the seat's office, e.g. a district council office, independent of who holds it.",
    )
    is_partisan: bool | None = Field(
        default=None,
        description="False when the seat is officially nonpartisan by charter or statute.",
    )
    maximum_memberships: int = Field(
        default=1,
        ge=1,
        description="How many people can hold this seat at once, e.g. 2 for a two-member district.",
    )
    valid_from: datetime | None = Field(
        default=None,
        description="Date the seat was, or will be, created. None for an open-ended start.",
    )
    valid_to: datetime | None = Field(
        default=None,
        description="Date the seat was, or will be, abolished. None while active.",
    )

    @model_validator(mode="after")
    def check_validity_window(self) -> "Post":
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to < self.valid_from
        ):
            raise ValueError("valid_to cannot be before valid_from")
        return self

    @field_validator("division_id")
    @classmethod
    def division_id_is_a_division(cls, value: str | None) -> str | None:
        if value is not None and get_ocdid_type(value) != "ocd-division":
            raise ValueError("division_id must use the 'ocd-division' prefix")
        return value
