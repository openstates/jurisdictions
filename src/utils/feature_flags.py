"""Feature-flag baseline for Jurisdiction records.

``Jurisdiction.feature_flags`` records which eligible top-level fields a
record had when it was first generated. Flags only ever grow: a later run that
loses a flagged field still carries the flag, so validation can fail the
record instead of the data silently regressing.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.models.jurisdiction import Jurisdiction
from src.utils.yaml_manager import YamlManager, find_ocdid_paths

logger = logging.getLogger(__name__)

ELIGIBLE_FIELDS: tuple[str, ...] = (
    "url",
    "term",
    "metadata",
    "sourcing",
    "legislative_sessions",
    "organizations",
    "governing_charter",
    "census_government_id",
    "division_relationships",
)

_PLACEHOLDER_HOST = "github.com"
_PLACEHOLDER_PATH_PREFIX = "/openstates/jurisdictions"


def _is_placeholder_url(value: Any) -> bool:
    parsed = urlparse(str(value))
    return parsed.netloc.lower() in {
        _PLACEHOLDER_HOST,
        f"www.{_PLACEHOLDER_HOST}",
    } and (parsed.path.rstrip("/").lower().startswith(_PLACEHOLDER_PATH_PREFIX))


def _is_populated(field: str, value: Any) -> bool:
    if value is None:
        return False
    if field in {"url", "governing_charter"}:
        return not _is_placeholder_url(value)
    if field == "metadata":
        return bool(value.urls)
    if field == "census_government_id":
        return bool(str(value).strip())
    if field == "term":
        return True
    return bool(value)


def _populated_fields(jurisdiction: Jurisdiction) -> list[str]:
    return [
        field
        for field in ELIGIBLE_FIELDS
        if _is_populated(field, getattr(jurisdiction, field))
    ]


def compute_feature_flags(jurisdiction: Jurisdiction) -> list[str]:
    """Sorted names of the eligible top-level fields that are populated.

    Existing ``feature_flags`` on the input are ignored; carrying flags
    forward is ``merge_feature_flags``'s job.
    """
    return sorted(_populated_fields(jurisdiction))


def merge_feature_flags(prior: Iterable[str] | None, new: Iterable[str]) -> list[str]:
    """Union of prior and new flags, sorted. A flag is never removed."""
    return sorted(set(prior or ()) | set(new))


def missing_flagged_fields(jurisdiction: Jurisdiction) -> list[str]:
    """Flagged eligible fields that are no longer populated, sorted.

    Flag names outside ``ELIGIBLE_FIELDS`` are ignored.
    """
    populated = set(_populated_fields(jurisdiction))
    return sorted(
        flag
        for flag in set(jurisdiction.feature_flags)
        if flag in ELIGIBLE_FIELDS and flag not in populated
    )


def load_prior_jurisdiction(ocdid: str, root: Path) -> Jurisdiction | None:
    """Load the existing Jurisdiction YAML for ``ocdid`` under ``root``, if any."""
    matches = find_ocdid_paths(ocdid, root)
    if not matches:
        return None
    if len(matches) > 1:
        logger.error(
            "Prior Jurisdiction lookup is ambiguous",
            extra={"ocdid": ocdid, "paths": [str(path) for path in matches]},
        )
        raise ValueError(
            f"more than one YAML under {root} has ocdid {ocdid}; "
            "cannot carry feature flags forward"
        )
    return YamlManager(root).load_jurisdiction(matches[0])
