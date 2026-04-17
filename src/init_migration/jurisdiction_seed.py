"""
Jurisdiction creation decision tree.

Implements the logic to determine whether a Jurisdiction
should be created for a given Division, and what classification it should have.

Decision tree (in priority order):
  1. Exact override always wins
  2. Statistical LSADs → no jurisdiction
  3. Legislative district types → legislature jurisdiction
  4. School district types → school_system jurisdiction
  5. Known non-governing types → no jurisdiction
  6. General government types (place, county, anc, etc.) → government jurisdiction
  7. Unknown → no jurisdiction, flag for manual review

NOTE: Council_district is handled by stripping it from the OCD ID and using the
parent entity type. A council_district division creates a jurisdiction for its
parent (e.g., a city council district creates a city government jurisdiction).


Def of a Jurisdiction:
https://open-civic-data.readthedocs.io/en/latest/data/jurisdiction.html
Here are the reference documents:

https://www.census.gov/library/reference/code-lists/legal-status-codes.html

https://www.census.gov/library/reference/code-lists/class-codes.html

https://www.census.gov/library/reference/code-lists/functional-status-codes.html

https://www2.census.gov/geo/pdfs/reference/mtfccs2025.pdf (edit

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.utils.ocdid import ocdid_parser


@dataclass
class JurisdictionSeed:
    has_jurisdiction: bool
    classification: Optional[str] = None
    jurisdiction_name: Optional[str] = None
    jurisdiction_type_suffix: Optional[str] = None
    reason: Optional[str] = None


# LSAD codes that indicate purely statistical geographies with no governing body.
# Source: https://www2.census.gov/geo/pdfs/reference/LSADCodes.pdf
STATISTICAL_LSADS = {
    "05",  # AK Census Area
    "15",  # CDP (Census Designated Place — unincorporated, no government)
    "28", "29", "30", "31", "32", "33", "34", "35", "36", "37", "38",
    "39", "42", "46", "47", "54", "55", "56",
}

# OCD division segment keys that indicate a legislative district.
LEGISLATIVE_TYPES = {"cd", "sldu", "sldl"}

# Division types that are purely geographic / statistical with no governing body.
NON_JURISDICTION_DIVISION_TYPES = {
    "vtd", "zcta", "tract", "blockgroup", "block",
    "ua", "msa", "csa", "division", "region",
}

# Division types that correspond to elected school boards.
SCHOOL_CLASSES = {
    "elementary_school_district",
    "secondary_school_district",
    "unified_school_district",
    "school_district",
    "special_school_administrative_area",
}

# Division types that create a general government jurisdiction.
# `anc` = DC Advisory Neighborhood Commission — an elected governing body.
GOVERNMENT_TYPES = {
    "country", "state", "county", "place",
    "cousub", "submcd", "aiannh", "aits", "anc",
}

# Division segment keys that indicate a sub-division whose jurisdiction belongs
# to the PARENT entity (not to itself). Strip these before resolving type.
PARENT_ENTITY_TYPES = {"council_district"}


def _extract_primary_division_type(parsed_ocdid: dict) -> str:
    """Return the most-specific governing division type, ignoring parent-entity
    sub-types (e.g. council_district).

    Args:
        parsed_ocdid: Dict produced by ``ocdid_parser()``.

    Returns:
        The primary division type string (e.g. "place", "anc", "county").
    """
    # Skip metadata keys that don't represent geographic division types.
    meta_keys = {"base", "country", "state", "district", "territory"}
    div_keys = [k for k in parsed_ocdid.keys() if k not in meta_keys]

    # Strip council_district (and other parent-entity sub-types) so the parent
    # type is used for classification decisions.
    div_keys = [k for k in div_keys if k not in PARENT_ENTITY_TYPES]

    return div_keys[-1] if div_keys else "unknown"


def infer_jurisdiction_seed(
    ocdid: str,
    lsad_code: str | None = None,
    is_statistical: bool | None = None,
    exact_override: dict | None = None,
) -> JurisdictionSeed:
    """Determine whether and what kind of Jurisdiction to create for a Division.

    Implements a decision tree to determine if a Division should have a
    corresponding Jurisdiction, and if so, what classification it should have.
    The decision is based on the Division's OCD ID, LSAD code, FUNCSTAT code,  and any explicit
    flags or overrides provided.

    Args:
        ocdid: The Division OCD ID.
        lsad_code: Census LSAD code for the Division (optional).
        is_statistical: Explicit flag marking division as statistical (optional).
        exact_override: Dict with keys ``has_jurisdiction``, ``classification``,
            ``jurisdiction_name``, ``jurisdiction_type_suffix`` — always wins.

    Returns:
        JurisdictionSeed with classification and creation decision.
    """
    # 1. Exact override always wins.
    if exact_override:
        return JurisdictionSeed(
            has_jurisdiction=exact_override["has_jurisdiction"],
            classification=exact_override.get("classification"),
            jurisdiction_name=exact_override.get("jurisdiction_name"),
            jurisdiction_type_suffix=exact_override.get("jurisdiction_type_suffix"),
            reason="exact override",
        )

    # 2. Explicit statistical flags or statistical LSAD code.
    if is_statistical is True or (lsad_code and lsad_code in STATISTICAL_LSADS):
        return JurisdictionSeed(
            has_jurisdiction=False,
            reason="statistical geography",
        )

    parsed = ocdid_parser(ocdid)
    division_type = _extract_primary_division_type(parsed)

    # 3. Legislative district.
    if division_type in LEGISLATIVE_TYPES:
        return JurisdictionSeed(
            has_jurisdiction=True,
            classification="legislature",
            jurisdiction_type_suffix="legislature",
            reason="legislative district",
        )

    # 4. School district.
    if division_type in SCHOOL_CLASSES:
        return JurisdictionSeed(
            has_jurisdiction=True,
            classification="school_system",
            jurisdiction_type_suffix="school_board",
            reason="school district geography",
        )

    # 5. Known non-governing types.
    if division_type in NON_JURISDICTION_DIVISION_TYPES:
        return JurisdictionSeed(
            has_jurisdiction=False,
            reason="non-governing geography",
        )

    # 6: LSAD code "52"

    # 6. General government fallback.
    if division_type in GOVERNMENT_TYPES:
        return JurisdictionSeed(
            has_jurisdiction=True,
            classification="government",
            jurisdiction_type_suffix="government",
            reason="general government fallback",
        )

    # 7. Unknown — safest default is no automatic jurisdiction.
    return JurisdictionSeed(
        has_jurisdiction=False,
        reason=f"unknown division type '{division_type}'; manual review required",
    )
