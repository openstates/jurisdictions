"""UUID5 helpers for OCDid-derived record identifiers.

A record's identifier is ``uuid5(NAMESPACE_URL, ocdid)``: a one-way hash of
the OCDid alone. The same OCDid always yields the same identifier, and no
mutable fact about the record (timestamps, website, geometry, provenance)
affects it. UUID5 values cannot be decoded back to their input; use
``verify_id`` to check a candidate against an OCDid.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5


@dataclass(frozen=True)
class DecodedID:
    identifier: str
    is_decodable: bool
    reason: str | None = None


def generate_id(ocdid: str) -> UUID:
    """Return the UUID5 identifier for an OCDid."""
    return uuid5(NAMESPACE_URL, ocdid)


def verify_id(identifier: str | UUID, ocdid: str) -> bool:
    """Check whether ``identifier`` is the UUID5 identifier of ``ocdid``."""
    return str(identifier) == str(generate_id(ocdid))


def decode_id(identifier: str | UUID) -> DecodedID:
    """Report decode capability for UUID5 identifiers.

    UUID5 values are one-way hashes and cannot be decoded into inputs.
    """
    return DecodedID(
        identifier=str(identifier),
        is_decodable=False,
        reason="UUID5 is one-way; use verify_id(identifier, ocdid)",
    )


__all__ = [
    "generate_id",
    "verify_id",
    "decode_id",
    "DecodedID",
]
