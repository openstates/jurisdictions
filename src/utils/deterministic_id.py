"""UUID5 helpers for ocdid/date-derived identifiers.

UUID5 is a one-way hash-based identifier and cannot be decoded back to
its input fields. This module provides generation and verification helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional
from uuid import NAMESPACE_URL, UUID, uuid5

@dataclass(frozen=True)
class DecodedID:
    identifier: str
    is_decodable: bool
    reason: Optional[str] = None


def _normalize_date(asof_date: date | datetime | str | None) -> date:
    if asof_date is None:
        return datetime.now(timezone.utc).date()
    if isinstance(asof_date, datetime):
        return asof_date.astimezone(timezone.utc).date()
    if isinstance(asof_date, date):
        return asof_date
    return date.fromisoformat(asof_date)


def build_uuid5_name(ocdid: str, asof_date: date | datetime | str | None = None) -> str:
    normalized = _normalize_date(asof_date)
    return f"{ocdid}|{normalized.isoformat()}"


def generate_id(
    ocdid: str,
    asof_date: date | datetime | str | None = None,
) -> UUID:
    """Generate a UUID5 from ocdid and date (UTC normalized)."""
    return uuid5(NAMESPACE_URL, build_uuid5_name(ocdid, asof_date))


def verify_id(
    identifier: str | UUID,
    ocdid: str,
    asof_date: date | datetime | str | None = None,
) -> bool:
    """Check whether an identifier matches ocdid+date UUID5 generation."""
    expected = generate_id(ocdid, asof_date)
    return str(identifier) == str(expected)


def decode_id(identifier: str | UUID) -> DecodedID:
    """Report decode capability for UUID5 identifiers.

    UUID5 values are one-way hashes and cannot be decoded into inputs.
    """
    return DecodedID(
        identifier=str(identifier),
        is_decodable=False,
        reason="UUID5 is one-way; use verify_id(identifier, ocdid, asof_date)",
    )


__all__ = [
    "build_uuid5_name",
    "generate_id",
    "verify_id",
    "decode_id",
    "DecodedID",
]
