"""Validate generated OCDID candidates against the canonical OCD corpus."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from src.normalize_government import GovernmentRecord
from src.ocdid_rule_engine import OCDIDCandidate
from src.resolve_government import CensusDivisionRecord
from src.sources.ocd_master import OCDMasterIndex


class OCDIDValidationStatus(str, Enum):
    """Terminal status for canonical OCDID validation."""

    VERIFIED = "VERIFIED"
    QUARANTINED = "QUARANTINED"


class OCDIDReviewSuggestion(BaseModel):
    """A possible canonical OCDID shown only for human review."""

    model_config = ConfigDict(frozen=True)

    ocdid: str
    name: str
    score: float


class OCDIDValidationResult(BaseModel):
    """Result of validating one generated candidate against canonical OCD."""

    model_config = ConfigDict(frozen=True)

    status: OCDIDValidationStatus
    candidate: OCDIDCandidate
    canonical_ocdid: str | None
    canonical_name: str | None
    reason: str | None = None
    review_suggestions: tuple[OCDIDReviewSuggestion, ...] = ()


class OCDIDReviewStatus(str, Enum):
    """Human-review state for a quarantined candidate."""

    PENDING = "pending"


class OCDIDReview(BaseModel):
    """Human-review fields carried with a quarantine record."""

    model_config = ConfigDict(frozen=True)

    status: OCDIDReviewStatus = OCDIDReviewStatus.PENDING
    decision: str | None = None
    canonical_ocdid: str | None = None
    notes: str | None = None


class OCDIDQuarantineRecord(BaseModel):
    """Self-contained review record for one unknown OCDID candidate."""

    model_config = ConfigDict(frozen=True)

    government: GovernmentRecord
    division: CensusDivisionRecord
    candidate: OCDIDCandidate
    reason: str
    nearest_master_ids: tuple[OCDIDReviewSuggestion, ...]
    review: OCDIDReview = Field(default_factory=OCDIDReview)


def _review_suggestions(
    candidate: OCDIDCandidate,
    index: OCDMasterIndex,
) -> tuple[OCDIDReviewSuggestion, ...]:
    return tuple(
        OCDIDReviewSuggestion(
            ocdid=suggestion.ocdid,
            name=suggestion.name,
            score=suggestion.score,
        )
        for suggestion in index.suggest(candidate.value)
    )


def validate_candidate(
    candidate: OCDIDCandidate,
    index: OCDMasterIndex,
) -> OCDIDValidationResult:
    """Validate by exact membership; suggestions are review context only."""
    entry = index.get(candidate.value)

    if entry is None:
        return OCDIDValidationResult(
            status=OCDIDValidationStatus.QUARANTINED,
            candidate=candidate,
            canonical_ocdid=None,
            canonical_name=None,
            reason="not_in_canonical_corpus",
            review_suggestions=_review_suggestions(candidate, index),
        )

    return OCDIDValidationResult(
        status=OCDIDValidationStatus.VERIFIED,
        candidate=candidate,
        canonical_ocdid=entry.ocdid,
        canonical_name=entry.name,
    )


def build_quarantine_record(
    *,
    government: GovernmentRecord,
    division: CensusDivisionRecord,
    validation: OCDIDValidationResult,
) -> OCDIDQuarantineRecord:
    """Build a self-contained review record from a quarantined validation."""
    if validation.status is not OCDIDValidationStatus.QUARANTINED:
        raise ValueError("quarantine record requires a quarantined validation result")

    if validation.reason is None:
        raise ValueError("quarantined validation result requires a reason")

    return OCDIDQuarantineRecord(
        government=government,
        division=division,
        candidate=validation.candidate,
        reason=validation.reason,
        nearest_master_ids=validation.review_suggestions,
    )
