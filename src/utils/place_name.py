"""
Utilities to map Census NAMELSAD fields to Open Civic Data Division Identifiers.

The Census NAMELSAD field is composed of “current name + legal/statistical area description,” so removing the LSAD phrase yields the plain display name (e.g., dropping “city,” “village,” “metropolitan government (balance),” etc.).

Open Civic Data’s identifiers use the Census “place” concept for
cities/towns/etc., and the associated CSV stores the human-readable names (what
we’re deriving above).

Regex removes the LSAD phrase that Census puts into NAMELSAD.

Examples removed: "city", "town", "village", "borough", "municipality",
"city and borough", "city and county", "charter township", "consolidated city", "metropolitan government (balance)", "CDP", "plantation"
"""

import csv
import re
from pathlib import Path

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
        CDP
    )\s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

def namelsad_to_display_name(namelsad: str) -> str:
    """
    Strip the LSAD phrase from a Census NAMELSAD to get the human display name.
    Examples:
      "Aberdeen city" -> "Aberdeen"
      "Nashville-Davidson metropolitan government (balance)" -> "Nashville-Davidson"
      "Juneau city and borough" -> "Juneau"
      "Anchorage municipality" -> "Anchorage"
    """
    s = namelsad.strip()
    # Remove one trailing LSAD phrase if present
    s2 = LSAD_RE.sub("", s)
    # If nothing changed (e.g., odd capitalization), try a case-normalized pass
    if s2 == s:
        s2 = LSAD_RE.sub("", s.title())
    return s2.strip()

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