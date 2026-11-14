"""A person who holds or has held a seat.

People are dynamic data: the pipeline does not create them. The model exists
so applications can attach people to the stable graph (Posts, Organizations)
through Memberships. Field names follow the Popolo and Open Civic Data
Person, so records exchange with Open States and similar projects.

References: https://www.popoloproject.com/specs/person.html,
https://open-civic-data.readthedocs.io/en/latest/data/person.html
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    model_validator,
)

from src.models.contact import ContactDetail, Link
from src.models.dates import PartialDate
from src.models.division import Identifiers
from src.models.source import Sourcing


class OtherName(BaseModel):
    """An alternate or former name (Popolo other name)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    note: str | None = None
    start_date: PartialDate | None = None
    end_date: PartialDate | None = Field(
        default=None, description="Set when the name is no longer used."
    )


class Person(BaseModel):
    """A person who holds or has held a seat (Post) in an Organization.

    Populated by: applications. Dynamic data this pipeline never fills.

    A Person stores no list of memberships: each Membership names its
    person_id, so the relationship is recorded once.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(
        default_factory=uuid4,
        description="Opaque UUID; a person's identity is not derived from their name. Ids from other systems (e.g. an Open States ocd-person id) go in identifiers.",
    )
    name: str = Field(description="Full name as commonly written.")
    sort_name: str | None = Field(default=None, description="e.g. 'Doe, Jane'.")
    given_name: str | None = None
    family_name: str | None = None
    additional_name: str | None = Field(default=None, description="Middle name(s).")
    honorific_prefix: str | None = Field(default=None, description="e.g. 'Dr.'.")
    honorific_suffix: str | None = Field(default=None, description="e.g. 'Jr.'.")
    nickname: str | None = Field(
        default=None,
        description="Name commonly used instead of the given name, e.g. 'Bob'; often what appears on a ballot.",
    )
    other_names: list[OtherName] = Field(default_factory=list)
    gender: str | None = None
    pronouns: str | None = None
    birth_date: PartialDate | None = None
    death_date: PartialDate | None = None
    image: HttpUrl | None = Field(default=None, description="URL of a photo.")
    summary: str | None = Field(default=None, description="A one-line account.")
    biography: str | None = Field(default=None, description="An extended account.")
    contact_details: list[ContactDetail] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    identifiers: Identifiers | None = Field(
        default=None,
        description="Ids in other systems, e.g. authority 'openstates', id_type 'person'. Popolo's identifier scheme maps to authority.",
    )
    accurate_asof: datetime | None = Field(
        default=None,
        description="When the record was known to be accurate.",
    )
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sourcing: Sourcing = Field(
        default_factory=Sourcing,
        description="Provenance for this record, indexed by dotted field path.",
    )

    @model_validator(mode="after")
    def check_sourcing_paths(self) -> "Person":
        self.sourcing.check_paths(type(self))
        return self
