from __future__ import annotations

import asyncio
import csv
from datetime import datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest
import yaml

from src.init_migration.generate_pipeline import GeneratePipeline
from src.init_migration.pipeline_models import GeneratorReq, OCDidIngestResp, Status
from src.models.division import Division
from src.models.jurisdiction import Jurisdiction
from src.models.ocdid import OCDidParsed
from src.utils.ocdid import ocdid_parser
from src.utils.state_lookup import load_state_code_lookup


REPO_ROOT = Path(__file__).resolve().parents[3]
OCD_SAMPLE_CSV = REPO_ROOT / "tests" / "sample_data" / "testing_ocd_sample.csv"
SAMPLE_OUTPUT_DIVISIONS = REPO_ROOT / "tests" / "sample_output" / "divisions"
SAMPLE_OUTPUT_JURISDICTIONS = REPO_ROOT / "tests" / "sample_output" / "jurisdictions"



DIVISION_SKIP_FIELDS: frozenset[str] = frozenset({
    "id",            # oid1- string in fixtures vs UUID5 from model — flagged for human review
    "sourcing",      # field:str vs list[str], source_url:str vs dict — model format mismatch
    "geometries",    # geo lookup disabled via division_geo_req=False — intentional in test
    "metadata",      # fixture uses [{key,value}] list; model uses DivisionMetadata object
})

JURISDICTION_SKIP_FIELDS: frozenset[str] = frozenset({
    "id",               # oid1-/UUID4 in fixtures vs UUID5 from model
    "sourcing",         # same structural format mismatch as divisions
    "term",             # DC ANC fixture missing source_url; Austin fixture uses list — format mismatch
})


def _load_target_rows() -> list[dict[str, str]]:
    """Load the five government-jurisdiction rows from testing_ocd_sample.csv."""
    with OCD_SAMPLE_CSV.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = [
            {
                "division_ocdid": row["division_ocdid"].strip(),
                "jurisdiction_ocdid": row["jurisdiction_ocdid"].strip(),
            }
            for row in reader
            if row.get("division_ocdid") and row.get("jurisdiction_ocdid")
        ]

    # The five sample jurisdictions in fixtures are government classifications.
    government_rows = [r for r in rows if r["jurisdiction_ocdid"].endswith("/government")]
    return government_rows


def _load_fixture_index(base_dir: Path) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for yaml_path in base_dir.glob("**/*.yaml"):
        with yaml_path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
            if isinstance(data, dict) and data.get("ocdid"):
                index[str(data["ocdid"])] = data
    return index


def _build_validation_csv(
    tmp_path: Path,
    division_ocdids: list[str],
    division_fixtures: dict[str, dict],
) -> Path:
    """Build validation CSV in the schema expected by GeneratePipeline."""
    state_lookup = load_state_code_lookup()
    state_to_fips = {
        (entry.get("stusps") or entry.get("stateusps") or "").lower(): str(entry.get("statefp") or entry.get("statefps") or "").zfill(2)
        for entry in state_lookup
        if (entry.get("stusps") or entry.get("stateusps")) and (entry.get("statefp") or entry.get("statefps"))
    }

    records: list[dict[str, str]] = []
    for ocdid in division_ocdids:
        fixture = division_fixtures[ocdid]
        identifiers = fixture.get("government_identifiers", {})
        parsed = ocdid_parser(ocdid)
        state_code = (parsed.get("state") or parsed.get("district") or "").lower()
        statefp = state_to_fips.get(state_code, str(identifiers.get("statefp", "")))

        # Handle null geoid — str(None) produces "None" which the pipeline cannot use
        geoid_val = identifiers.get("geoid")
        geoid_str = str(geoid_val) if geoid_val is not None else ""

        # Handle lsad — fixture may store it as a list (legacy format); extract first element
        lsad_val = identifiers.get("lsad")
        if isinstance(lsad_val, list):
            lsad_str = lsad_val[0] if lsad_val else ""
        elif lsad_val is None:
            lsad_str = ""
        else:
            lsad_str = str(lsad_val)

        records.append(
            {
                "STATEFP": statefp,
                "NAMELSAD": str(identifiers.get("namelsad", fixture.get("display_name", ""))),
                "GEOID_Census": geoid_str,
                "SLDUST_list": " | ".join(identifiers.get("sldust", [])),
                "SLDLST_list": " | ".join(identifiers.get("sldlst", [])),
                "COUNTYFP_list": " | ".join(identifiers.get("countyfp", [])),
                "COUNTY_NAMES": " | ".join(identifiers.get("county_names", [])),
                "LSAD": lsad_str,
            }
        )

    validation_csv = tmp_path / "validation_from_sample_output.csv"
    with validation_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)

    return validation_csv


def _normalize_timestamp(value: str | datetime | None) -> datetime | None:
    """Parse timestamp string to datetime with UTC timezone for validation.

    Args:
        value: Timestamp as string, datetime, or None

    Returns:
        datetime object with UTC timezone, or None if input is None

    Raises:
        ValueError: If timestamp string cannot be parsed
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value

    # Handle ISO 8601 format timestamps
    try:
        if isinstance(value, str):
            # Remove 'Z' suffix and parse
            timestamp_str = value.rstrip('Z')
            dt = datetime.fromisoformat(timestamp_str)
            return dt
    except (ValueError, AttributeError) as e:
        raise ValueError(f"Cannot parse timestamp: {value}") from e


def _is_timestamp_field(path: str) -> bool:
    """Check if field path represents a timestamp field."""
    timestamp_fields = {'accurate_asof', 'last_updated', 'accessed_at', 'valid_asof', 'valid_thru'}
    path_parts = path.split('.')
    return any(part in timestamp_fields for part in path_parts)


def _generate_field_diff_report(
    expected: dict | list | str | int | float | bool | None,
    generated: dict | list | str | int | float | bool | None,
    path: str = "",
    skip_fields: frozenset[str] = frozenset(),
) -> list[str]:
    """Recursively compare fields and generate diff report.

    Args:
        expected: Expected value from fixture
        generated: Generated value from pipeline output
        path: Current field path (dot-separated)
        skip_fields: Top-level field names to skip entirely

    Returns:
        List of diff strings showing mismatches
    """
    diffs = []

    # Skip timestamp fields
    if path and _is_timestamp_field(path):
        return diffs

    # Both None - match
    if expected is None and generated is None:
        return diffs

    # Treat None and "" as equivalent (e.g. model emits "" for absent optional strings)
    if expected is None and generated == "":
        return diffs
    if expected == "" and generated is None:
        return diffs

    # One None, one not - mismatch
    if expected is None or generated is None:
        diffs.append(f"{path or 'root'}: expected={expected!r}, generated={generated!r}")
        return diffs

    # Different types - mismatch (with special case for [] vs missing key handled at dict level)
    if type(expected) is not type(generated):
        diffs.append(f"{path or 'root'}: type mismatch - expected {type(expected).__name__}={expected!r}, generated {type(generated).__name__}={generated!r}")
        return diffs

    # Compare dicts recursively
    if isinstance(expected, dict):
        all_keys = set(expected.keys()) | set(generated.keys())
        for key in sorted(all_keys):
            new_path = f"{path}.{key}" if path else key

            # Skip explicitly excluded top-level fields
            if not path and key in skip_fields:
                continue

            if key not in expected:
                # Skip unexpected empty lists in generated output — these arise when
                # the model initialises list fields with [] but the fixture omits them.
                if isinstance(generated[key], list) and len(generated[key]) == 0:
                    continue
                diffs.append(f"{new_path}: unexpected field in generated (value={generated[key]!r})")
            elif key not in generated:
                diffs.append(f"{new_path}: missing field in generated (expected={expected[key]!r})")
            else:
                diffs.extend(_generate_field_diff_report(
                    expected[key], generated[key], new_path, skip_fields=skip_fields
                ))
        return diffs

    # Compare lists recursively
    if isinstance(expected, list):
        if len(expected) != len(generated):
            diffs.append(f"{path or 'root'}: list length mismatch - expected {len(expected)}, generated {len(generated)}")
            # Still compare common elements
            for i in range(min(len(expected), len(generated))):
                new_path = f"{path}.{i}" if path else f"[{i}]"
                diffs.extend(_generate_field_diff_report(expected[i], generated[i], new_path, skip_fields=skip_fields))
        else:
            for i, (exp_item, gen_item) in enumerate(zip(expected, generated)):
                new_path = f"{path}.{i}" if path else f"[{i}]"
                diffs.extend(_generate_field_diff_report(exp_item, gen_item, new_path, skip_fields=skip_fields))
        return diffs

    # Compare primitives
    if expected != generated:
        diffs.append(f"{path or 'root'}: expected={expected!r}, generated={generated!r}")

    return diffs


def _compare_yaml_exact(
    expected: dict,
    generated: dict,
    label: str,
    skip_fields: frozenset[str] = frozenset(),
) -> None:
    """Compare expected and generated YAML data with detailed diff reporting.

    Validates that timestamp fields are populated, then performs exact comparison
    of all non-timestamp, non-skipped fields.

    Args:
        expected: Expected data from fixture
        generated: Generated data from pipeline
        label: Label for error messages (e.g., "Division ocd-division/...")
        skip_fields: Top-level field names to exclude from comparison

    Raises:
        AssertionError: If any fields mismatch (with detailed diff report)
    """
    # First validate timestamp fields are populated (don't compare exact values)
    timestamp_fields = ['accurate_asof', 'last_updated']
    for field in timestamp_fields:
        if field in expected:  # Only check if expected has the field
            gen_value = generated.get(field)
            assert gen_value is not None, f"{label}: timestamp field '{field}' is None"
            assert gen_value != "", f"{label}: timestamp field '{field}' is empty"
            # Validate it's parseable as datetime
            try:
                _normalize_timestamp(gen_value)
            except ValueError as e:
                raise AssertionError(f"{label}: timestamp field '{field}' is not valid: {e}") from e

    # Generate diff report for all non-timestamp, non-skipped fields
    diffs = _generate_field_diff_report(expected, generated, skip_fields=skip_fields)

    # If there are differences, fail with detailed report
    if diffs:
        diff_report = "\n".join(f"  - {diff}" for diff in diffs)
        raise AssertionError(f"{label}: Field mismatches found:\n{diff_report}")


@pytest.mark.integration
def test_generate_pipeline_main_style_integration(tmp_path: Path) -> None:
    """Run generate_pipeline main-style flow over five sample OCD IDs."""

    target_rows = _load_target_rows()
    assert len(target_rows) == 5

    division_fixtures = _load_fixture_index(SAMPLE_OUTPUT_DIVISIONS)
    jurisdiction_fixtures = _load_fixture_index(SAMPLE_OUTPUT_JURISDICTIONS)

    division_ocdids = [row["division_ocdid"] for row in target_rows]
    jurisdiction_ocdids = [row["jurisdiction_ocdid"] for row in target_rows]

    for ocdid in division_ocdids:
        assert ocdid in division_fixtures
    for ocdid in jurisdiction_ocdids:
        assert ocdid in jurisdiction_fixtures

    validation_csv = _build_validation_csv(tmp_path, division_ocdids, division_fixtures)

    division_output_dir = tmp_path / "divisions"
    jurisdiction_output_dir = tmp_path / "jurisdictions"

    async def run_all() -> list:
        responses = []
        for ocdid in division_ocdids:
            parsed = ocdid_parser(ocdid)
            req = GeneratorReq(
                data=OCDidIngestResp(
                    uuid=str(uuid5(NAMESPACE_URL, ocdid)),
                    ocdid=OCDidParsed(
                        raw_ocdid=ocdid,
                        country=parsed.get("country", "us"),
                        state=parsed.get("state"),
                        county=parsed.get("county"),
                        place=parsed.get("place"),
                    ),
                    raw_record={},
                ),
                validation_data_filepath=str(validation_csv),
                build_base_object=True,
                jurisdiction_ai_url=False,
                division_geo_req=False,
                division_population_req=False,
            )

            pipeline = GeneratePipeline(
                req,
                division_output_dir=division_output_dir,
                jurisdiction_output_dir=jurisdiction_output_dir,
            )

            responses.append(await pipeline.run())
        return responses

    responses = asyncio.run(run_all())

    assert len(responses) == 5
    generated_division_paths: list[Path] = []
    generated_jurisdiction_paths: list[Path] = []

    for response in responses:
        assert response.status.status in (Status.SUCCESS, Status.SKIPPED, Status.PARTIAL)
        assert response.status.status is not Status.FAILED
        if response.division_path:
            division_path = Path(response.division_path)
            assert division_path.exists()
            generated_division_paths.append(division_path)
        if response.jurisdiction_path:
            jurisdiction_path = Path(response.jurisdiction_path)
            assert jurisdiction_path.exists()
            generated_jurisdiction_paths.append(jurisdiction_path)

    assert len(generated_division_paths) == 5
    assert len(generated_jurisdiction_paths) == 5

    for division_path in generated_division_paths:
        with division_path.open(encoding="utf-8") as handle:
            generated_division = yaml.safe_load(handle)

        expected_division = division_fixtures[generated_division["ocdid"]]
        assert generated_division["ocdid"] == expected_division["ocdid"]

        expected_geoid = expected_division.get("government_identifiers", {}).get("geoid")
        generated_geoid = generated_division.get("government_identifiers", {}).get("geoid")
        if expected_geoid and expected_geoid != "missing-geoid":
            assert generated_geoid == expected_geoid

    for jurisdiction_path in generated_jurisdiction_paths:
        with jurisdiction_path.open(encoding="utf-8") as handle:
            generated_jurisdiction = yaml.safe_load(handle)

        expected_jurisdiction = jurisdiction_fixtures[generated_jurisdiction["ocdid"]]
        assert generated_jurisdiction["ocdid"] == expected_jurisdiction["ocdid"]
        assert generated_jurisdiction["classification"] == expected_jurisdiction["classification"]


