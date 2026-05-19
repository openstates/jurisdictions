"""
Recursively ensures ancestor Divisions and Jurisdictions exist for a given OCDid.

When the pipeline processes a local-government OCDid (e.g. place:seattle under
state:wa), this module guarantees that each ancestor level (state, county, etc.)
has at least a placeholder Division and Jurisdiction YAML file on disk.

Ancestors are stub quality — a separate enrichment pipeline is responsible for
filling in their full data.  The only contract enforced here is:
  - The `ocdid` field is correct and matches the OCD hierarchy.
  - Stubs are idempotent: running twice produces no second write.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.models.division import Division
from src.models.ocdid import OCDidParsed
from src.models.source import SourceType
from src.utils.state_lookup import load_state_code_lookup

logger = logging.getLogger(__name__)

# Ancestor segment keys, in priority order used to detect the deepest level.
_LEVEL_KEYS = ("county", "state", "district", "territory")


def stub_exists(ocdid: str, search_dir: Path) -> bool:
    """Return True if a YAML file in `search_dir` has an `ocdid` matching `ocdid`.

    Scans only the immediate contents of `search_dir` (non-recursive).

    Args:
        ocdid: The OCD ID to search for.
        search_dir: Directory to scan for YAML files.

    Returns:
        True if a matching file is found, False otherwise.
    """
    if not search_dir.exists():
        return False
    for yaml_path in search_dir.glob("*.yaml"):
        try:
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("ocdid") == ocdid:
                return True
        except Exception:
            logger.debug("Could not read %s during stub check", yaml_path)
    return False


def _resolve_state_info(state_code: str, state_lookup: list[dict]) -> tuple[str, str]:
    """Return `(state_fips_2digit, full_name)` for a lower-case state abbreviation."""
    for item in state_lookup:
        abbr = (item.get("stusps") or item.get("stateusps") or "").lower()
        if abbr == state_code:
            fips = str(item.get("statefp") or item.get("statefps") or "").zfill(2)
            name = item.get("name") or state_code.upper()
            return fips, name
    return "", state_code.upper()


def _ancestor_dirs(
    level: str,
    state_code: str,
    division_output_dir: Path,
    jurisdiction_output_dir: Path,
) -> tuple[Path, Path]:
    """Return ``(div_dir, jur_dir)` for the given ancestor level.

    Mirrors the `DivGenerator.dump_division` convention of prepending
    "divisions" / "jurisdictions" to the shared output directory root.
    State stubs go directly under {state}.
    County (and other sub-state) stubs go under `{state}/{level}/`.
    """
    if level in ("state", "district", "territory"):
        return (
            division_output_dir / "divisions" / state_code,
            jurisdiction_output_dir / "jurisdictions" / state_code,
        )
    return (
        division_output_dir / "divisions" / state_code / level,
        jurisdiction_output_dir / "jurisdictions" / state_code / level,
    )


def _write_stub_division(
    ocdid: str,
    display_name: str,
    state_fips: str,
    div_dir: Path,
) -> Path:
    """Write a placeholder Division YAML and return the file path."""
    jur_part = ocdid.replace("ocd-division/", "")
    now = datetime.now(timezone.utc)
    division = Division(
        ocdid=ocdid,
        country="us",
        display_name=display_name,
        geometries=[],
        also_known_as=[],
        jurisdiction_id=f"ocd-jurisdiction/{jur_part}/government",
        government_identifiers={
            "namelsad": display_name,
            "statefp": state_fips,
            "sldust": [],
            "sldlst": [],
            "countyfp": [],
            "county_names": [],
            "lsad": "",
            "geoid": state_fips,
        },
        sourcing=[
            {
                "field": ["ocdid"],
                "source_name": "ocdid_recursive_stub",
                "source_url": {
                    "ocd_repo": "https://raw.githubusercontent.com/opencivicdata/ocd-division-ids/master/identifiers/country-us.csv"
                },
                "source_type": SourceType.HUMAN,
                "source_description": "Placeholder stub — created by recursive ancestor traversal",
            }
        ],
        accurate_asof=now,
        last_updated=now,
    )
    data = division.model_dump(exclude_none=False, mode="json")
    div_dir.mkdir(parents=True, exist_ok=True)
    safe_name = display_name.lower().replace(" ", "_")
    path = div_dir / f"{safe_name}_stub.yaml"
    path.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8"
    )
    return path


def _write_stub_jurisdiction(div_ocdid: str, display_name: str, jur_dir: Path) -> Path:
    """Write a placeholder Jurisdiction YAML and return the file path."""
    div_part = div_ocdid.replace("ocd-division/", "")
    jur_ocdid = f"ocd-jurisdiction/{div_part}/government"
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "ocdid": jur_ocdid,
        "name": f"{display_name} Government",
        "url": f"https://opencivicdata.org/division/{div_ocdid}",
        "classification": "government",
        "legislative_sessions": {},
        "feature_flags": [],
        "metadata": {"urls": []},
        "sourcing": [
            {
                "field": ["ocdid", "name", "classification"],
                "source_name": "ocdid_recursive_stub",
                "source_url": {
                    "ocd_repo": "https://raw.githubusercontent.com/opencivicdata/ocd-division-ids/master/identifiers/country-us.csv"
                },
                "source_type": SourceType.HUMAN.value,
                "source_description": "Placeholder stub — created by recursive ancestor traversal",
            }
        ],
        "accurate_asof": now,
        "last_updated": now,
    }
    jur_dir.mkdir(parents=True, exist_ok=True)
    safe_name = display_name.lower().replace(" ", "_")
    path = jur_dir / f"{safe_name}_stub.yaml"
    path.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8"
    )
    return path


def ensure_ancestor_stubs(
    ocdid: str,
    division_output_dir: Path,
    jurisdiction_output_dir: Path,
) -> list[dict]:
    """Walk the OCD ID hierarchy and write stubs for any missing ancestor.

    For each ancestor level (state, county, etc.) between the country root and
    the leaf, checks whether Division and Jurisdiction YAML files already exist.
    Creates placeholder files for any that are missing.

    Args:
        ocdid: Leaf OCDid being processed by the main pipeline.
        division_output_dir: Path to save division files.
        jurisdiction_output_dir: Path to save jurisdiction files.

    Returns:
        Ordered list of result dicts, one per ancestor::

            {
                "ocdid": "ocd-division/country:us/state:wa",
                "level": "state",
                "action": "created" | "skipped",
                "division_path": "/path/to/div.yaml" | None,
                "jurisdiction_path": "/path/to/jur.yaml" | None,
            }
    """
    state_lookup = load_state_code_lookup()
    parsed_ocdid = OCDidParsed.parse_ocdid(ocdid)
    ancestors = OCDidParsed.build_ancestor_ocdids(parsed_ocdid)
    results: list[dict] = []

    for ancestor in ancestors:
        ancestor_ocdid = ancestor.raw_ocdid
        parsed = ancestor.model_dump(exclude_none=True)

        level = next((k for k in _LEVEL_KEYS if k in parsed), None)
        if not level:
            logger.debug(
                "No recognised level in ancestor %s — skipping", ancestor_ocdid
            )
            continue

        state_code = (parsed.get("state") or parsed.get("district") or "").lower()
        if not state_code:
            logger.debug("No state code in ancestor %s — skipping", ancestor_ocdid)
            continue

        state_fips, state_full = _resolve_state_info(state_code, state_lookup)
        level_value: str = parsed[level]

        if level in ("state", "district", "territory"):
            display_name = state_full
        elif level == "county":
            display_name = f"{level_value.replace('_', ' ').title()} County"
        else:
            display_name = level_value.replace("_", " ").title()

        div_dir, jur_dir = _ancestor_dirs(
            level, state_code, division_output_dir, jurisdiction_output_dir
        )

        jur_ocdid = (
            f"ocd-jurisdiction/{ancestor_ocdid.replace('ocd-division/', '')}/government"
        )
        div_exists = stub_exists(ancestor_ocdid, div_dir)
        jur_exists = stub_exists(jur_ocdid, jur_dir)

        if div_exists and jur_exists:
            logger.debug("Ancestor stubs already exist for %s", ancestor_ocdid)
            results.append(
                {
                    "ocdid": ancestor_ocdid,
                    "level": level,
                    "action": "skipped",
                    "division_path": None,
                    "jurisdiction_path": None,
                }
            )
            continue

        div_path: Path | None = None
        jur_path: Path | None = None

        if not div_exists:
            div_path = _write_stub_division(
                ancestor_ocdid, display_name, state_fips, div_dir
            )
            logger.info(
                "Stub Division created for ancestor %s",
                ancestor_ocdid,
                extra={"path": str(div_path)},
            )

        if not jur_exists:
            jur_path = _write_stub_jurisdiction(ancestor_ocdid, display_name, jur_dir)
            logger.info(
                "Stub Jurisdiction created for ancestor %s",
                ancestor_ocdid,
                extra={"path": str(jur_path)},
            )

        results.append(
            {
                "ocdid": ancestor_ocdid,
                "level": level,
                "action": "created",
                "division_path": str(div_path) if div_path else None,
                "jurisdiction_path": str(jur_path) if jur_path else None,
            }
        )

    return results
