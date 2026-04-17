# ---------------------------------------------------------------------------
# Umbrella GEOID exception mapping
# ---------------------------------------------------------------------------
# Some divisions (e.g. DC Advisory Neighborhood Commissions) have no specific
# Census GEOID. For these we fall back to the GEOID of the containing
# geographic area (state → county → place) as the umbrella identifier.
#
# Keyed by (district_or_state_code, division_type) → umbrella GEOID.
# When no GEOID is found in the validation record, _resolve_umbrella_geoid()
# checks this table before deciding to quarantine the record.


UMBRELLA_GEOID_MAP: dict[tuple[str, str], str] = {
    # DC Advisory Neighborhood Commission districts have no Census GEOID.
    # The umbrella GEOID is the DC county FIPS (state 11, county 001 → "11001").
    ("dc", "anc"): "11001",
}

def _resolve_umbrella_geoid(parsed_ocdid: dict) -> str | None:
    """Return an umbrella GEOID for divisions that lack a specific Census GEOID.

    Checks UMBRELLA_GEOID_MAP against the parsed OCD ID components.  Returns
    None when no umbrella mapping exists (caller should quarantine the record).

    Args:
        parsed_ocdid: Dict produced by ocdid_parser() for the division OCD ID.

    Returns:
        Umbrella GEOID string, or None if no mapping is defined.
    """
    district = (parsed_ocdid.get("district") or "").lower()
    state = (parsed_ocdid.get("state") or district).lower()

    for (geo_key, div_type), umbrella_geoid in UMBRELLA_GEOID_MAP.items():
        if state == geo_key and div_type in parsed_ocdid:
            return umbrella_geoid

    return None