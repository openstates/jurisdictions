"""Elections, contests, candidacies, and results.

Elections are dynamic data: the pipeline does not create them. The models
exist so applications can attach elections to the stable graph: a contest is
held in a Division and fills Posts; a candidacy names a Person and a Post; a
result reports a contest's counts for a reporting Division.

Elections, contests, and candidacies follow Open Civic Data's elections
proposal (OCDEP 20). OCDEP 20 leaves results to a later proposal, so results
follow the NIST Election Results Common Data Format (SP 1500-100 v2), whose
vote-count types also cover the OpenElections result columns. As elsewhere in this
repository, references use the referenced record's id, provenance is one
``sourcing`` index, and each relationship is stored once — on the record
that points (a Contest names its Election; an Election lists no Contests).

References: https://github.com/opencivicdata/docs.opencivicdata.org/blob/master/proposals/0020.rst,
https://pages.nist.gov/ElectionResultsReporting/
"""

import datetime as dt
from enum import Enum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.models.division import Identifiers
from src.models.ocdid import OCDIdStr, get_ocdid_type
from src.models.source import Sourcing
from src.utils.deterministic_id import generate_id


def _division_ocdid(value: str) -> str:
    if get_ocdid_type(value) != "ocd-division":
        raise ValueError("division_id must use the 'ocd-division' prefix")
    return value


class _ElectionRecord(BaseModel):
    """Fields shared by election records."""

    model_config = ConfigDict(extra="forbid")

    identifiers: Identifiers | None = Field(
        default=None, description="Ids in other systems, e.g. a state election id."
    )
    accurate_asof: dt.datetime | None = Field(
        default=None, description="When the record was known to be accurate."
    )
    last_updated: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))
    sourcing: Sourcing = Field(
        default_factory=Sourcing,
        description="Provenance for this record, indexed by dotted field path.",
    )

    @model_validator(mode="after")
    def check_sourcing_paths(self):
        self.sourcing.check_paths(type(self))
        return self


class ElectionType(str, Enum):
    """Kind of election (NIST ElectionType)."""

    GENERAL = "general"
    PRIMARY = "primary"
    PARTISAN_PRIMARY_OPEN = "partisan-primary-open"
    PARTISAN_PRIMARY_CLOSED = "partisan-primary-closed"
    RUNOFF = "runoff"
    SPECIAL = "special"
    OTHER = "other"


class Election(_ElectionRecord):
    """A collection of contests held on one date, administered for one Division.

    Populated by: applications. Dynamic data this pipeline never fills.
    """

    id: UUID | None = Field(
        default=None,
        description="UUID5 derived from division_id, date, and name. Derived when omitted.",
    )
    name: str = Field(description="e.g. '2025 General Election'.")
    classification: ElectionType | None = Field(
        default=None, description="Kind of election, e.g. general, primary, runoff."
    )
    date: dt.date = Field(description="Election day: the last day of voting.")
    start_date: dt.date | None = Field(
        default=None,
        description="First day of voting, e.g. when early or mail voting opens. None when voting is on election day only.",
    )
    division_id: OCDIdStr = Field(
        description="The broadest Division the election covers, e.g. the state."
    )
    administrative_organization_id: UUID | None = Field(
        default=None,
        description="id of the Organization that administers the election, e.g. a county elections office.",
    )

    _check_division = field_validator("division_id")(_division_ocdid)

    @model_validator(mode="after")
    def derive_id(self) -> "Election":
        if self.start_date is not None and self.start_date > self.date:
            raise ValueError("start_date cannot be after the election date")
        if self.id is None:
            self.id = generate_id(
                f"election:{self.division_id}/{self.date.isoformat()}/{self.name}"
            )
        return self


class VoteVariation(str, Enum):
    """How votes are cast and counted in a contest (NIST VoteVariation)."""

    PLURALITY = "plurality"
    MAJORITY = "majority"
    SUPER_MAJORITY = "super-majority"
    RCV = "rcv"
    APPROVAL = "approval"
    N_OF_M = "n-of-m"
    CUMULATIVE = "cumulative"
    BORDA = "borda"
    RANGE = "range"
    PROPORTIONAL = "proportional"
    OTHER = "other"


class BallotMeasureType(str, Enum):
    """Kind of ballot measure (NIST BallotMeasureType)."""

    BALLOT_MEASURE = "ballot-measure"
    INITIATIVE = "initiative"
    REFERENDUM = "referendum"
    RECALL = "recall"
    OTHER = "other"


class _ContestBase(_ElectionRecord):
    """Fields shared by every kind of contest."""

    id: UUID | None = Field(
        default=None,
        description="UUID5 derived from election_id and name. Derived when omitted.",
    )
    name: str = Field(description="Name as it appears on the ballot.")
    election_id: UUID = Field(description="id of the Election the contest is part of.")
    division_id: OCDIdStr = Field(
        description="The Division voting in the contest; within the Election's division."
    )
    runoff_for_contest_id: UUID | None = Field(
        default=None, description="id of the contest this one is a runoff for."
    )
    ballot_title: str | None = Field(
        default=None, description="Title as printed on the ballot."
    )
    ballot_subtitle: str | None = Field(
        default=None, description="Subtitle as printed on the ballot."
    )
    sequence_order: int | None = Field(
        default=None, ge=0, description="Position of the contest on the ballot."
    )
    vote_variation: VoteVariation | None = Field(
        default=None,
        description="How votes are cast and counted, e.g. plurality, majority, rcv.",
    )

    _check_division = field_validator("division_id")(_division_ocdid)

    @model_validator(mode="after")
    def derive_id(self):
        if self.id is None:
            self.id = generate_id(f"contest:{self.election_id}/{self.name}")
        return self


class ContestPost(BaseModel):
    """A Post filled by a candidate contest."""

    model_config = ConfigDict(extra="forbid")

    post_id: UUID = Field(description="id of the Post.")
    sort_order: int | None = Field(
        default=None, description="Order of the post among the contest's posts."
    )


class CandidateContest(_ContestBase):
    """A contest among candidates for one or more Posts.

    Populated by: applications. Dynamic data this pipeline never fills.
    """

    contest_type: Literal["candidate"] = "candidate"
    posts: list[ContestPost] = Field(
        min_length=1, description="The Posts this contest fills."
    )
    primary_party_ids: list[UUID] = Field(
        default_factory=list,
        description="ids of the party Organizations whose primary this is; empty for a nonpartisan or general contest.",
    )
    previous_term_unexpired: bool = Field(
        default=False,
        description="True when filling the rest of a term someone else left early.",
    )
    number_elected: int = Field(
        default=1, ge=1, description="How many candidates are elected."
    )
    votes_allowed: int = Field(
        default=1, ge=1, description="How many candidates a voter may choose."
    )
    number_runoff: int | None = Field(
        default=None, ge=0, description="How many candidates advance to a runoff."
    )


class BallotMeasureContest(_ContestBase):
    """A contest on a ballot measure, e.g. a proposition, initiative, or recall.

    Populated by: applications. Dynamic data this pipeline never fills.
    """

    contest_type: Literal["ballot_measure"] = "ballot_measure"
    options: list[str] = Field(
        min_length=2, description="Choices on the ballot, e.g. ['yes', 'no']."
    )
    description: str | None = Field(default=None, description="Text of the measure.")
    summary_text: str | None = Field(
        default=None, description="Summary of the measure as given to voters."
    )
    passage_threshold: str | None = Field(
        default=None, description="Vote needed to pass, e.g. 'two-thirds'."
    )
    classification: BallotMeasureType | None = Field(
        default=None,
        description="Kind of measure, e.g. initiative, referendum, recall.",
    )


class RetentionContest(BallotMeasureContest):
    """A vote on whether an officeholder keeps their seat, e.g. judicial retention.

    Populated by: applications. Dynamic data this pipeline never fills.
    """

    contest_type: Literal["retention"] = "retention"  # type: ignore[assignment]
    membership_id: UUID = Field(
        description="id of the Membership (the officeholder's term) being decided."
    )


class ContestParty(BaseModel):
    """A party on the ballot in a party contest."""

    model_config = ConfigDict(extra="forbid")

    party_id: UUID = Field(description="id of the party Organization.")
    is_incumbent: bool | None = None


class PartyContest(_ContestBase):
    """A contest among parties, e.g. a party-list or party-preference vote.

    Populated by: applications. Dynamic data this pipeline never fills.
    """

    contest_type: Literal["party"] = "party"
    parties: list[ContestParty] = Field(min_length=1)


#: Any contest, loaded by its ``contest_type``.
Contest = Annotated[
    CandidateContest | BallotMeasureContest | RetentionContest | PartyContest,
    Field(discriminator="contest_type"),
]


class PreElectionStatus(str, Enum):
    """A candidacy's status before the vote (NIST CandidatePreElectionStatus, plus write-in)."""

    FILED = "filed"
    QUALIFIED = "qualified"
    WITHDRAWN = "withdrawn"
    WRITE_IN = "write-in"


class Candidacy(_ElectionRecord):
    """A person running for a Post in a candidate contest.

    Populated by: applications. Dynamic data this pipeline never fills.

    ``person_id`` is required: names do not identify people. Two candidates
    can share a name, and one person can run for different offices over
    time under different ballot names; the Person id keeps them apart and
    links one person's candidacies and memberships together.
    """

    id: UUID | None = Field(
        default=None,
        description="UUID5 derived from contest_id, post_id, and person_id. Derived when omitted.",
    )
    person_id: UUID = Field(description="id of the Person running.")
    ballot_name: str = Field(
        description="Name as printed on the ballot, which may differ from the Person's name."
    )
    contest_id: UUID = Field(description="id of the CandidateContest.")
    post_id: UUID = Field(description="id of the Post sought.")
    party_id: UUID | None = Field(
        default=None, description="id of the party Organization."
    )
    filed_date: dt.date | None = None
    pre_election_status: PreElectionStatus | None = Field(
        default=None,
        description="Status before the vote: filed, qualified, withdrawn, or write-in.",
    )
    is_incumbent: bool | None = None
    top_ticket_candidacy_id: UUID | None = Field(
        default=None,
        description="id of the top-of-ticket Candidacy, for a running mate.",
    )

    @model_validator(mode="after")
    def derive_id(self) -> "Candidacy":
        if self.id is None:
            self.id = generate_id(
                f"candidacy:{self.contest_id}/{self.post_id}/{self.person_id}"
            )
        return self


class ResultsStatus(str, Enum):
    """How final a set of results is (NIST ResultsStatus)."""

    PRE_ELECTION = "pre-election"
    UNOFFICIAL_PARTIAL = "unofficial-partial"
    UNOFFICIAL_COMPLETE = "unofficial-complete"
    RECOUNT = "recount"
    CORRECTION = "correction"
    CERTIFIED = "certified"


class CountType(str, Enum):
    """How a set of votes was cast or counted (NIST CountItemType).

    OpenElections columns map to: ``votes`` → total, ``election_day`` →
    election-day, ``early_voting`` → early, ``absentee`` → absentee,
    ``provisional`` → provisional.
    """

    TOTAL = "total"
    ELECTION_DAY = "election-day"
    EARLY = "early"
    ABSENTEE = "absentee"
    ABSENTEE_MAIL = "absentee-mail"
    ABSENTEE_IN_PERSON = "absentee-in-person"
    ABSENTEE_FWAB = "absentee-fwab"
    UOCAVA = "uocava"
    PROVISIONAL = "provisional"
    WRITE_IN = "write-in"
    SEATS = "seats"
    OTHER = "other"


class CandidatePostElectionStatus(str, Enum):
    """A selection's outcome (NIST CandidatePostElectionStatus)."""

    WINNER = "winner"
    PROJECTED_WINNER = "projected-winner"
    ADVANCED_TO_RUNOFF = "advanced-to-runoff"
    DEFEATED = "defeated"
    WITHDRAWN = "withdrawn"


class VoteCount(BaseModel):
    """Votes of one type for one selection (NIST VoteCounts)."""

    model_config = ConfigDict(extra="forbid")

    type: CountType = Field(default=CountType.TOTAL)
    count: int = Field(ge=0)
    is_suppressed_for_privacy: bool = Field(
        default=False,
        description="True when the count is withheld to protect ballot secrecy.",
    )
    round: int | None = Field(
        default=None,
        ge=1,
        description="Tabulation round, for ranked-choice contests. None for a single-round count.",
    )


class SelectionResult(BaseModel):
    """The counts for one choice in a contest (NIST ContestSelection with its VoteCounts).

    Names exactly one choice: a Candidacy, a ballot-measure selection, or a
    party. Aggregated write-ins set ``is_write_in`` and name no candidacy.
    """

    model_config = ConfigDict(extra="forbid")

    candidacy_id: UUID | None = Field(
        default=None, description="id of the Candidacy, in a candidate contest."
    )
    ballot_selection: str | None = Field(
        default=None,
        description="The ballot-measure option, e.g. 'yes'; one of the contest's options.",
    )
    party_id: UUID | None = Field(
        default=None, description="id of the party Organization, in a party contest."
    )
    is_write_in: bool = Field(default=False, description="True for write-in votes.")
    endorsement_party_ids: list[UUID] = Field(
        default_factory=list,
        description="ids of other party Organizations the candidate also appears under (fusion voting).",
    )
    sequence_order: int | None = Field(
        default=None, ge=0, description="Position of the selection on the ballot."
    )
    vote_counts: list[VoteCount] = Field(default_factory=list)
    post_election_status: CandidatePostElectionStatus | None = Field(
        default=None, description="Outcome for this selection, e.g. winner."
    )

    @model_validator(mode="after")
    def check_selection(self) -> "SelectionResult":
        chosen = [
            value
            for value in (self.candidacy_id, self.ballot_selection, self.party_id)
            if value is not None
        ]
        if len(chosen) > 1 or (not chosen and not self.is_write_in):
            raise ValueError(
                "A selection names exactly one of candidacy_id, ballot_selection, "
                "or party_id (or is an aggregated write-in)"
            )
        keys = [(count.type, count.round) for count in self.vote_counts]
        repeated = sorted(
            {
                f"{count_type.value}" + (f" round {rnd}" if rnd else "")
                for count_type, rnd in keys
                if keys.count((count_type, rnd)) > 1
            }
        )
        if repeated:
            raise ValueError(
                f"Each count type appears once per round; repeated: {repeated}"
            )
        return self


class ContestResult(_ElectionRecord):
    """The reported results of one contest for one reporting Division.

    Populated by: applications. Dynamic data this pipeline never fills.

    Results for a precinct, county, or the whole contest are separate records
    (NIST reports counts per GpUnit; here the reporting unit is an OCD
    Division). Each report is its own record, so unofficial and certified
    results for the same contest and Division coexist.
    """

    id: UUID | None = Field(
        default=None,
        description="UUID5 derived from contest_id, division_id, status, and reported_at. Derived when omitted.",
    )
    contest_id: UUID = Field(description="id of the Contest.")
    division_id: OCDIdStr = Field(
        description="The reporting unit: the Division these counts cover, e.g. a precinct, county, or the contest's whole division."
    )
    status: ResultsStatus = Field(default=ResultsStatus.UNOFFICIAL_PARTIAL)
    reported_at: dt.datetime | None = Field(
        default=None, description="When these results were published."
    )
    sub_units_reported: int | None = Field(
        default=None,
        ge=0,
        description="Reporting sub-units (e.g. precincts) counted so far.",
    )
    total_sub_units: int | None = Field(
        default=None, ge=0, description="Reporting sub-units in total."
    )
    ballots_cast: int | None = Field(default=None, ge=0)
    ballots_outstanding: int | None = Field(
        default=None, ge=0, description="Ballots not yet counted."
    )
    ballots_rejected: int | None = Field(default=None, ge=0)
    overvotes: int | None = Field(default=None, ge=0)
    undervotes: int | None = Field(default=None, ge=0)
    write_ins: int | None = Field(
        default=None, ge=0, description="Total write-in votes, when not itemized."
    )
    selections: list[SelectionResult] = Field(default_factory=list)

    _check_division = field_validator("division_id")(_division_ocdid)

    @model_validator(mode="after")
    def check_sub_units(self) -> "ContestResult":
        if (
            self.sub_units_reported is not None
            and self.total_sub_units is not None
            and self.sub_units_reported > self.total_sub_units
        ):
            raise ValueError("sub_units_reported exceeds total_sub_units")
        return self

    @model_validator(mode="after")
    def derive_id(self) -> "ContestResult":
        if self.id is None:
            reported = self.reported_at.isoformat() if self.reported_at else ""
            self.id = generate_id(
                f"result:{self.contest_id}/{self.division_id}/{self.status.value}/{reported}"
            )
        return self
