# Deterministic, decodable, uuid-like identifiers

To support stable, shareable filenames that can be decoded back to the original OCD ID and a random element, we provide a reversible, deterministic ID format.

- Library: `src/utils/deterministic_id.py`
- API:
  - `generate_id(ocdid: str, version: str = "v1", random_element: str|bytes|int|None = None) -> str`
  - `decode_id(identifier: str) -> DecodedID` (fields: `format_version`, `ocdid`, `version`, `random_element`)

## Format

- Prefix: `oid1-` (OpenStates ID, format version 1)
- Payload: JSON `{fv, o, v[, r]}` where:
  - `fv`: format version = `1`
  - `o`: full `ocdid` string
  - `v`: an explicit object version string you control (e.g., `"v1"`)
  - `r`: optional random element (only present if provided)
- Encoding: UTF-8 JSON → zlib (level 9) → Base32 (lowercase, no padding)
- Presentation: hyphen-grouped to look uuid-like (8-4-4-4-12 repeating)

Example ID:

```
oid1-df2b0c38-76fd-6c8b-5fcb-6b1a6e8811b3-93f0b7d0
```

## Determinism, versioning, and the random element

- The identifier is deterministic by default and depends on `(ocdid, version)`.
  Repeated calls with the same `(ocdid, version)` return the same identifier.
- Use the `version` string to control file-level versions per object. For example,
  `v1` and `v2` will produce distinct, decodable IDs for the same `ocdid`.
- If you need extra entropy, pass your own `random_element` (string, bytes, or int).
  It is embedded verbatim (after serialization) and recovered by `decode_id`. It is
  not included by default.

## Usage

```python
from src.utils.deterministic_id import generate_id, decode_id

ocdid = "ocd-division/country:us/state:wa/place:seattle"
custom_id = generate_id(ocdid, version="v1")  # deterministic for the given (ocdid, version)
print(custom_id)

decoded = decode_id(custom_id)
assert decoded.ocdid == ocdid
assert decoded.version == "v1"
print(decoded.random_element)  # deterministic default or your provided value
```

## Filenames

- Suggested filename pattern (Division): `<display_name>_<geoid>_<custom_id>.yaml`
- Suggested filename pattern (Jurisdiction): `<name>_<custom_id>.yaml`

Example:

```
divisions/wa/local/Seattle_5363000_oid1-df2b0c38-76fd-6c8b-5fcb-6b1a6e8811b3.yaml
jurisdictions/wa/local/Seattle_City_Council_oid1-b7aa2c1f-5cf1-4a86-94a1-0cfe2b9a.yaml
```

## Notes

- The ID is intentionally longer than a classical UUID because it embeds the full OCD ID (compressed) plus your object `version`.
- The format is versioned via `fv` and prefixed with `oid1-`. Future format versions can evolve encoding while keeping backward compatibility.
- The output contains only lowercase letters, digits, and hyphens—safe for filenames and URLs.
