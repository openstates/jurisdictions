"""
Recursively ensure ancestor Divisions and Jurisdictions exist for a given OCDid.

When the pipeline processes a local-government OCDid (e.g. place:seattle under
state:wa), this module guarantees that each ancestor level (state, county, etc.)
has at least a placeholder Division and Jurisdiction YAML file on disk.

Ancestors are stub quality — a separate enrichment pipeline is responsible for
filling in their full data.  The only contract enforced here is:
  - The `ocdid` field is correct and matches the OCD hierarchy.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.models.division import Division, GovernmentIdentifiers
from src.models.jurisdiction import ClassificationEnum, Jurisdiction
from src.models.ocdid import OCDidParsed
from src.models.source import SourceObj, SourceType
from src.utils.state_lookup import load_state_code_lookup

logger = logging.getLogger(__name__)

# Segment keys that identify a governing-body ancestor level, checked in priority
# order so that the most-specific level is selected for each ancestor.
_LEVEL_KEYS: tuple[str, ...] = ("county", "state", "district", "territory")

_OCD_REPO_URL = (
    "https://raw.githubusercontent.com/opencivicdata/ocd-division-ids"
    "/master/identifiers/country-us.csv"
)
_STUB_SOURCE = SourceObj(
    field=["ocdid"],
    source_name="ocdid_recursive_stub",
    source_url={"ocd_repo": _OCD_REPO_URL},
    source_type=SourceType.HUMAN,
    source_description="Placeholder stub — created by recursive ancestor traversal",
)


def stub_exists(ocdid: str, search_dir: Path) -> bool:
    """Return True if a YAML file in `search_dir` has a matching `ocdid`.

    Scans only the immediate contents of ``search_dir`` (non-recursive).

    Args:
        ocdid: The OCD ID string to search for.
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
    """Return `(div_dir, jur_dir)` for the given ancestor level.

    Mirrors the `DivGenerator.dump_division` convention of prepending
    `"divisions"` / `"jurisdictions"` to the shared output-directory root.
    State/district/territory stubs sit directly under `{state}/`.
    County stubs sit under `{state}/county/`.
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
    ancestor: OCDidParsed,
    display_name: str,
    state_fips: str,
    div_dir: Path,
) -> Path:
    """Build a stub Division via the Division model and write it as YAML.

    Args:
        ancestor: OCDidParsed for this ancestor level.
        display_name: Human-readable name derived from the ancestor (e.g. "Washington").
        state_fips: Two-digit FIPS code for the ancestor's state.
        div_dir: Target directory for the YAML file.

    Returns:
        Path to the written file.
    """
    div_ocdid = ancestor.raw_ocdid
    jur_part = div_ocdid.replace("ocd-division/", "")
    now = datetime.now(timezone.utc)

    gov_ids = GovernmentIdentifiers(
        namelsad=display_name,
        statefp=state_fips,
        sldust=[],
        sldlst=[],
        countyfp=[],
        county_names=[],
        lsad="",
        geoid=state_fips,
    )

    division = Division(
        ocdid=div_ocdid,
        country=ancestor.country,
        display_name=display_name,
        jurisdiction_id=f"ocd-jurisdiction/{jur_part}/government",
        government_identifiers=gov_ids,
        sourcing=[_STUB_SOURCE],
        accurate_asof=now,
        last_updated=now,
    )

    data = division.model_dump(mode="json", exclude_none=True)
    div_dir.mkdir(parents=True, exist_ok=True)
    safe_name = display_name.lower().replace(" ", "_")
    path = div_dir / f"{safe_name}_stub.yaml"
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8")
    return path


def _write_stub_jurisdiction(
    ancestor: OCDidParsed,
    display_name: str,
    jur_dir: Path,
) -> Path:
    """Build a stub Jurisdiction via the Jurisdiction model and write it as YAML.

    Args:
        ancestor: OCDidParsed for this ancestor level.
        display_name: Human-readable name derived from the ancestor.
        jur_dir: Target directory for the YAML file.

    Returns:
        Path to the written file.
    """
    div_ocdid = ancestor.raw_ocdid
    div_part = div_ocdid.replace("ocd-division/", "")
    jur_ocdid = f"ocd-jurisdiction/{div_part}/government"

    jur_source = SourceObj(
        field=["ocdid", "name", "classification"],
        source_name="ocdid_recursive_stub",
        source_url={"ocd_repo": _OCD_REPO_URL},
        source_type=SourceType.HUMAN,
        source_description="Placeholder stub — created by recursive ancestor traversal",
    )

    now = datetime.now(timezone.utc)
    jurisdiction = Jurisdiction(
        ocdid=jur_ocdid,
        name=f"{display_name} Government",
        url=f"https://opencivicdata.org/division/{div_ocdid}",
        classification=ClassificationEnum.GOVERNMENT,
        legislative_sessions={},
        feature_flags=[],
        metadata={"urls": []},
        sourcing=[jur_source],
        accurate_asof=now,
        last_updated=now,
    )

    data = jurisdiction.model_dump(mode="json", exclude_none=True)
    jur_dir.mkdir(parents=True, exist_ok=True)
    safe_name = display_name.lower().replace(" ", "_")
    path = jur_dir / f"{safe_name}_stub.yaml"
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8")
    return path


def ensure_ancestor_stubs(
    parsed_ocdid: OCDidParsed,
    division_output_dir: Path,
    jurisdiction_output_dir: Path,
) -> list[dict]:
    """Walk the OCD ID hierarchy and write stubs for any missing ancestor.

    Calls `parsed_ocdid.build_ancestors()` to obtain the list of ancestor
    OCDidParsed objects, then for each one checks whether Division and
    Jurisdiction YAML files already exist on disk.

    Args:
        parsed_ocdid: OCDidParsed for the leaf OCD ID being processed by the
            main pipeline (i.e. `self.parsed_ocdid` from GeneratePipeline).
        division_output_dir: Same `self.division_output_dir` used by
            GeneratePipeline.
        jurisdiction_output_dir: Same `self.jurisdiction_output_dir` used by
            GeneratePipeline.

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
    ancestors = parsed_ocdid.build_ancestors()
    results: list[dict] = []

    for ancestor in ancestors:
        # Detect the deepest governing-body level present in this ancestor.
        level = next(
            (k for k in _LEVEL_KEYS if getattr(ancestor, k, None)),
            None,
        )
        if not level:
            logger.debug("No recognised level in ancestor %s — skipping", ancestor.raw_ocdid)
            continue

        state_code = (ancestor.state or getattr(ancestor, "district", None) or "").lower()
        if not state_code:
            logger.debug("No state code in ancestor %s — skipping", ancestor.raw_ocdid)
            continue

        state_fips, state_full = _resolve_state_info(state_code, state_lookup)
        level_value: str = getattr(ancestor, level, "") or ""

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
            f"ocd-jurisdiction/{ancestor.raw_ocdid.replace('ocd-division/', '')}/government"
        )
        div_exists = stub_exists(ancestor.raw_ocdid, div_dir)
        jur_exists = stub_exists(jur_ocdid, jur_dir)

        if div_exists and jur_exists:
            logger.debug("Ancestor stubs already exist for %s", ancestor.raw_ocdid)
            results.append(
                {
                    "ocdid": ancestor.raw_ocdid,
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
            div_path = _write_stub_division(ancestor, display_name, state_fips, div_dir)
            logger.info(
                "Stub Division created for ancestor %s",
                ancestor.raw_ocdid,
                extra={"path": str(div_path)},
            )

        if not jur_exists:
            jur_path = _write_stub_jurisdiction(ancestor, display_name, jur_dir)
            logger.info(
                "Stub Jurisdiction created for ancestor %s",
                ancestor.raw_ocdid,
                extra={"path": str(jur_path)},
            )

        results.append(
            {
                "ocdid": ancestor.raw_ocdid,
                "level": level,
                "action": "created",
                "division_path": str(div_path) if div_path else None,
                "jurisdiction_path": str(jur_path) if jur_path else None,
            }
        )

    return results
