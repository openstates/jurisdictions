"""
Utilities to map Census NAMELSAD fields to Open Civic Data Division Identifiers.

The Census NAMELSAD field is composed of “current name + legal/statistical area description,” so removing the LSAD phrase yields the plain display name (e.g., dropping “city,” “village,” “metropolitan government (balance),” etc.).

Open Civic Data’s identifiers use the Census “place” concept for
cities/towns/etc., and the associated CSV stores the human-readable names (what
we’re deriving above).

When the record's two-digit LSAD code is known, the affix to remove is looked up
in ``src/data/lsad_map.json`` (generated from the Census code list by
``src/data/lsad_mapper.py``). That is exact: the code says whether the affix is a
prefix or a suffix and what its text is.

``LSAD_RE`` remains as a fallback for records whose LSAD code is absent or not in
the map. It only covers the most common suffixes, so prefer passing ``lsad_code``.

Examples removed: "city", "town", "village", "borough", "municipality",
"city and borough", "city and county", "charter township", "consolidated city", "metropolitan government (balance)", "CDP", "CCD", "plantation"
"""

import csv
import json
import re
from functools import lru_cache
from pathlib import Path

LSAD_MAP_PATH = Path(__file__).resolve().parents[1] / "data" / "lsad_map.json"

LSAD_RE = re.compile(
    r"""
    \s+(
        city\ and\ borough|
        city\ and\ county|
        metropolitan\ government\ \(balance\)|
        metropolitan\ government|
        consolidated\ (?:government|city)|
        charter\ (?:township|town)|
        municipality|
        borough|
        township|
        plantation|
        village|
        town|
        city|
        CDP|
        CCD
    )\s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


@lru_cache(maxsize=1)
def load_lsad_map() -> dict[str, dict]:
    """Load the Census LSAD code table, keyed by two-digit code."""
    with LSAD_MAP_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def coerce_lsad_code(raw: object) -> str:
    """Normalise an LSAD cell into a bare code.

    The validation CSV stores LSAD as a bare code ("25"), the string "None"/"null",
    or a Python list repr ("['25', '43']") when a record spans several codes. Only
    the first code of a list is meaningful for naming.
    """
    if raw is None:
        return ""
    value = str(raw).strip()
    if value in ("", "None", "null"):
        return ""
    if value.startswith("["):
        inner = value.strip("[]").replace("'", "").replace('"', "").strip()
        value = inner.split(",")[0].strip() if inner else ""
    return value


def _strip_suffix(name: str, suffix: str) -> str:
    return re.sub(rf"\s+{re.escape(suffix)}\s*$", "", name, flags=re.IGNORECASE).strip()


def _strip_prefix(name: str, prefix: str) -> str:
    return re.sub(rf"^\s*{re.escape(prefix)}\s+", "", name, flags=re.IGNORECASE).strip()


def namelsad_to_display_name(namelsad: str, lsad_code: object = None) -> str:
    """
    Strip the LSAD phrase from a Census NAMELSAD to get the human display name.

    Pass ``lsad_code`` (the record's LSAD column) whenever it is available: the
    affix is then removed by table lookup rather than by regex guesswork, which
    is the only way to handle the long tail of codes such as CCD.

    Examples:
      "Aberdeen city" -> "Aberdeen"
      "Abbeville CCD" (lsad_code="22") -> "Abbeville"
      "Nashville-Davidson metropolitan government (balance)" -> "Nashville-Davidson"
      "Juneau city and borough" -> "Juneau"
      "Anchorage municipality" -> "Anchorage"

    A name whose affix cannot be identified is returned unchanged, never
    reformatted — callers rely on the original casing ("McAllen", "ST. LOUIS").
    """
    s = namelsad.strip()
    if not s:
        return ""

    code = coerce_lsad_code(lsad_code)
    if code:
        definition = load_lsad_map().get(code)
        if definition:
            suffix = definition.get("lsad_suffix")
            if suffix:
                stripped = _strip_suffix(s, suffix)
                if stripped != s:
                    return stripped
            prefix = definition.get("lsad_prefix")
            if prefix:
                stripped = _strip_prefix(s, prefix)
                if stripped != s:
                    return stripped

    return LSAD_RE.sub("", s).strip()


def build_place_names_by_state(country_us_csv: Path):
    """
    Returns dict like: {'wa': {'aberdeen', 'seattle', ...}, 'sd': {...}, ...}
    Names are lowercase for easy matching.
    """
    by_state = {}
    with country_us_csv.open(newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            ocd_id = row["id"]
            name = row["name"]
            # Only keep place-level rows (cities, towns, etc. use 'place:' in OCD IDs)
            # e.g., ocd-division/country:us/state:wa/place:aberdeen
            parts = ocd_id.split("/")
            if any(p.startswith("place:") for p in parts):
                # extract state code
                for p in parts:
                    if p.startswith("state:") and len(p.split(":")[-1]) == 2:
                        st = p.split(":")[-1]
                        by_state.setdefault(st, set()).add(name.lower())
                        break
    return by_state
