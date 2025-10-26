"""
Deterministic, decodable, uuid-like identifiers for YAML filenames.

Design goals
- Deterministic: same input (ocdid + version) → same id
- Decodable: anyone can recover the ocdid, version, and optional random element
- UUID-like: hyphenated, filesystem- and URL-friendly

Format
- Prefix: "oid1-" (OpenStates ID, format version 1)
- Body: base32 (lowercase, no padding) of zlib(json({fv,o,v[,r]})) with hyphen grouping
    where payload json is: {"fv": 1, "o": <ocdid>, "v": <version_string>, "r": <random_element?>}

Notes
- The random element is optional and NOT included by default. Pass it explicitly
    only when additional entropy is desired while keeping the id decodable.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import json
import zlib
from hashlib import sha256
from typing import Optional


PREFIX = "oid1-"  # openstates id, format version 1


@dataclass(frozen=True)
class DecodedID:
    format_version: int
    ocdid: str
    version: str
    random_element: Optional[str]


def _derive_random_element(ocdid: str, length: int = 10) -> str:
    """Legacy helper retained for callers that wish to derive a deterministic
    random-like element from the ocdid. Not used by default.

    We use the first 6 bytes of SHA-256(ocdid) and base32 encode to ~10 chars.
    Returns lowercase base32 (no padding).
    """
    digest = sha256(ocdid.encode("utf-8")).digest()
    raw = digest[:6]
    b32 = base64.b32encode(raw).decode("ascii").rstrip("=")
    return b32.lower()[:length]


def _group_uuid_like(s: str) -> str:
    """Add hyphens to look uuid-like without enforcing 36-char length.

    We'll use a repeating pattern of 8-4-4-4-12 groups; any remaining tail is
    appended in groups of 12.
    """
    groups = []
    pattern = [8, 4, 4, 4, 12]
    i = 0
    p_idx = 0
    n = len(s)
    while i < n:
        size = pattern[p_idx]
        groups.append(s[i : i + size])
        i += size
        p_idx = (p_idx + 1) % len(pattern)
    return "-".join([g for g in groups if g])


def _ungroup_uuid_like(s: str) -> str:
    return s.replace("-", "")


def generate_id(
    ocdid: str,
    version: str = "v1",
    random_element: Optional[str | bytes | int] = None,
) -> str:
    """Generate a deterministic, decodable, uuid-like identifier string.

    Inputs
    - ocdid: full OCD ID string (e.g., 'ocd-division/country:us/state:wa/place:seattle')
    - version: a string you control to version the object (e.g., 'v1'). Same
      ocdid+version always yields the same id.
    - random_element: optional extra entropy. If provided, it is embedded and
      decodable; by default it is omitted.

    Output
    - A string beginning with 'oid1-' followed by a uuid-like hyphenated token.
    """
    payload = {"fv": 1, "o": ocdid, "v": version}
    if isinstance(random_element, bytes):
        r_str = base64.b32encode(random_element).decode("ascii").rstrip("=").lower()
        payload["r"] = r_str
    elif isinstance(random_element, int):
        payload["r"] = str(random_element)
    elif isinstance(random_element, str):
        payload["r"] = random_element

    # Stable JSON encoding (no spaces) then zlib compress and base32 encode
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    comp = zlib.compress(data, level=9)
    token = base64.b32encode(comp).decode("ascii").rstrip("=").lower()
    grouped = _group_uuid_like(token)
    return f"{PREFIX}{grouped}"


def decode_id(identifier: str) -> DecodedID:
    """Decode an identifier created by generate_id back to its components.

    Raises ValueError if the format is invalid or the payload cannot be decoded.
    """
    if not identifier.startswith(PREFIX):
        raise ValueError("Invalid id prefix; expected 'oid1-'")
    body = identifier[len(PREFIX) :]
    compact = _ungroup_uuid_like(body)
    # Add base32 padding to multiple of 8 chars
    pad_len = (-len(compact)) % 8
    padded = compact.upper() + ("=" * pad_len)
    try:
        comp = base64.b32decode(padded, casefold=True)
        raw = zlib.decompress(comp)
        payload = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise ValueError("Failed to decode identifier") from e

    fv = payload.get("fv")
    o = payload.get("o")
    v = payload.get("v")
    r = payload.get("r") if "r" in payload else None
    if fv != 1 or not isinstance(o, str) or not isinstance(v, str):
        raise ValueError("Invalid payload structure")
    return DecodedID(format_version=fv, ocdid=o, version=v, random_element=r)


__all__ = [
    "generate_id",
    "decode_id",
    "DecodedID",
]
