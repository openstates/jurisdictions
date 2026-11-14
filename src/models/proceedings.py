"""Meetings, motions, votes, and speeches.

Proceedings are dynamic data: the pipeline does not create them. The models
exist so applications can attach what happens in a body's meetings to the
stable graph through Organization, Person, and Post ids.

Follows the Popolo Event, Motion, Vote event, Count, Vote, and Speech
specifications. As elsewhere in this repository, references use the
referenced record's id, provenance is one ``sourcing`` index, and each
relationship is stored once — on the record that points (a Vote names its
VoteEvent; a VoteEvent lists no Votes). Code lists that Popolo leaves open
accept other values as plain strings.

Reference: https://www.popoloproject.com/specs/
"""

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from src.models.dates import FuzzyDateTime
from src.models.division import Identifiers
from src.models.source import Sourcing
from src.utils.deterministic_id import generate_id


class _ProceedingRecord(BaseModel):
    """Fields shared by proceedings records."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4, description="Opaque UUID.")
    accurate_asof: datetime | None = Field(
        default=None, description="When the record was known to be accurate."
    )
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sourcing: Sourcing = Field(
        default_factory=Sourcing,
        description="Provenance for this record, indexed by dotted field path.",
    )

    @model_validator(mode="after")
    def check_sourcing_paths(self):
        self.sourcing.check_paths(type(self))
        return self


def _open_code_list(description: str):
    """A field taking a code-list value, or any other string."""
    return Field(default=None, union_mode="left_to_right", description=description)


class EventStatus(str, Enum):
    CONFIRMED = "confirmed"
    TENTATIVE = "tentative"
    CANCELLED = "cancelled"
    POSTPONED = "postponed"
    RESCHEDULED = "rescheduled"


class Event(_ProceedingRecord):
    """An occurrence that people may attend, e.g. a meeting or hearing (Popolo Event).

    Populated by: applications. Dynamic data this pipeline never fills.
    """

    id: UUID | None = Field(  # type: ignore[assignment]
        default=None,
        description="UUID5 derived from organization_id, start_date, and name; random when the event has neither a start date nor a name. Derived when omitted.",
    )
    name: str | None = None
    description: str | None = None
    classification: str | None = Field(
        default=None,
        description="e.g. 'committee-meeting', 'hearing', 'legislative session'.",
    )
    start_date: FuzzyDateTime | None = None
    end_date: FuzzyDateTime | None = None
    location: str | None = None
    status: EventStatus | str | None = _open_code_list(
        "e.g. confirmed, tentative, cancelled, postponed, rescheduled."
    )
    organization_id: UUID = Field(
        description="id of the Organization holding the event; its link to the graph."
    )
    parent_id: UUID | None = Field(
        default=None, description="id of the Event this one is part of."
    )
    attendee_ids: list[UUID] = Field(
        default_factory=list, description="ids of the People who attended."
    )
    identifiers: Identifiers | None = None

    @model_validator(mode="after")
    def derive_id(self) -> "Event":
        if self.id is None:
            if self.start_date is None and self.name is None:
                self.id = uuid4()
            else:
                self.id = generate_id(
                    f"event:{self.organization_id}/{self.start_date or ''}/{self.name or ''}"
                )
        return self


class MotionResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"


class Motion(_ProceedingRecord):
    """A formal proposal put to a body for a decision (Popolo Motion).

    Populated by: applications. Dynamic data this pipeline never fills.
    """

    organization_id: UUID | None = Field(
        default=None, description="id of the Organization the motion is put to."
    )
    legislative_session_id: UUID | None = Field(
        default=None, description="id of the Event (session) it was made in."
    )
    creator_id: UUID | None = Field(
        default=None, description="id of the Person who made the motion."
    )
    text: str | None = None
    identifier: str | None = Field(default=None, description="e.g. a motion number.")
    classification: str | None = None
    date: datetime | None = None
    requirement: str | None = Field(
        default=None, description="Vote needed to pass, e.g. 'majority'."
    )
    result: MotionResult | str | None = _open_code_list("e.g. pass, fail.")

    @model_validator(mode="after")
    def check_link(self) -> "Motion":
        if self.organization_id is None and self.legislative_session_id is None:
            raise ValueError(
                "A motion needs an organization_id or legislative_session_id"
            )
        return self


class VoteOption(str, Enum):
    YES = "yes"
    NO = "no"
    ABSTAIN = "abstain"
    ABSENT = "absent"
    NOT_VOTING = "not voting"
    PAIRED = "paired"


class Count(BaseModel):
    """The number of votes for one option in a vote event (Popolo Count)."""

    model_config = ConfigDict(extra="forbid")

    option: VoteOption | str = Field(
        union_mode="left_to_right",
        description="e.g. yes, no, abstain, absent, not voting, paired.",
    )
    value: int = Field(ge=0)
    group_id: UUID | None = Field(
        default=None, description="id of the Organization (e.g. party) counted, if any."
    )


class VoteEvent(_ProceedingRecord):
    """A single vote on a motion, with its tallies (Popolo Vote event).

    Populated by: applications. Dynamic data this pipeline never fills.
    """

    organization_id: UUID | None = Field(
        default=None, description="id of the Organization voting."
    )
    legislative_session_id: UUID | None = Field(
        default=None, description="id of the Event (session) the vote was held in."
    )
    motion_id: UUID | None = Field(default=None, description="id of the Motion.")
    identifier: str | None = None
    classification: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    result: MotionResult | str | None = _open_code_list("e.g. pass, fail.")
    counts: list[Count] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_link(self) -> "VoteEvent":
        if (
            self.organization_id is None
            and self.motion_id is None
            and self.legislative_session_id is None
        ):
            raise ValueError(
                "A vote event needs an organization_id, motion_id, or "
                "legislative_session_id"
            )
        return self


class Vote(BaseModel):
    """One voter's vote in a vote event (Popolo Vote).

    Populated by: applications. Dynamic data this pipeline never fills.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID | None = Field(
        default=None,
        description="UUID5 derived from vote_event_id and voter_id; random when the voter is unknown. Derived when omitted.",
    )
    vote_event_id: UUID = Field(description="id of the VoteEvent.")
    voter_id: UUID | None = Field(
        default=None, description="id of the Person (or Organization) voting."
    )
    option: VoteOption | str | None = _open_code_list(
        "e.g. yes, no, abstain, absent, not voting, paired."
    )
    group_id: UUID | None = Field(
        default=None, description="id of the voter's group, e.g. party Organization."
    )
    role: str | None = None
    weight: float = Field(default=1, description="Weight of the vote.")
    pair_id: UUID | None = Field(
        default=None, description="id of the Person this voter is paired with."
    )

    @model_validator(mode="after")
    def derive_id(self) -> "Vote":
        if self.id is None:
            self.id = (
                generate_id(f"vote:{self.vote_event_id}/{self.voter_id}")
                if self.voter_id is not None
                else uuid4()
            )
        return self


class SpeechType(str, Enum):
    SPEECH = "speech"
    QUESTION = "question"
    ANSWER = "answer"
    SCENE = "scene"
    NARRATIVE = "narrative"
    SUMMARY = "summary"
    OTHER = "other"


class Speech(_ProceedingRecord):
    """A speech, question, or answer given at an event (Popolo Speech).

    Populated by: applications. Dynamic data this pipeline never fills.
    """

    creator_id: UUID | None = Field(
        default=None, description="id of the Person speaking."
    )
    role: str | None = Field(default=None, description="e.g. chair, speaker.")
    attribution_text: str | None = Field(
        default=None, description="Speaker as written, when not a known Person."
    )
    audience_id: UUID | None = Field(
        default=None, description="id of the Person addressed."
    )
    text: str | None = None
    audio: HttpUrl | None = None
    video: HttpUrl | None = None
    date: datetime | None = None
    title: str | None = None
    type: SpeechType | str | None = _open_code_list(
        "e.g. speech, question, answer, scene, narrative, summary, other."
    )
    position: int | None = Field(
        default=None, description="Order of the speech within its event."
    )
    event_id: UUID = Field(
        description="id of the Event the speech was given at; its link to the graph."
    )
