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

		records.append(
			{
				"STATEFP": statefp,
				"NAMELSAD": str(identifiers.get("namelsad", fixture.get("display_name", ""))),
				"GEOID_Census": str(identifiers.get("geoid", "")),
				"SLDUST_list": " | ".join(identifiers.get("sldust", [])),
				"SLDLST_list": " | ".join(identifiers.get("sldlst", [])),
				"COUNTYFP_list": " | ".join(identifiers.get("countyfp", [])),
				"COUNTY_NAMES": " | ".join(identifiers.get("county_names", [])),
				"LSAD": str(identifiers.get("lsad", "")),
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
	"""Check if field path represents a timestamp field.

	Args:
		path: Dot-separated field path (e.g., 'accurate_asof', 'sourcing.0.accessed_at')

	Returns:
		True if field is a timestamp field, False otherwise
	"""
	timestamp_fields = {'accurate_asof', 'last_updated', 'accessed_at', 'valid_asof', 'valid_thru'}
	# Check if any component of the path is a timestamp field
	path_parts = path.split('.')
	return any(part in timestamp_fields for part in path_parts)


def _generate_field_diff_report(
	expected: dict | list | str | int | float | bool | None,
	generated: dict | list | str | int | float | bool | None,
	path: str = "",
) -> list[str]:
	"""Recursively compare fields and generate diff report.

	Args:
		expected: Expected value from fixture
		generated: Generated value from pipeline output
		path: Current field path (dot-separated)

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

	# One None, one not - mismatch
	if expected is None or generated is None:
		diffs.append(f"{path or 'root'}: expected={expected!r}, generated={generated!r}")
		return diffs

	# Different types - mismatch
	if type(expected) is not type(generated):
		diffs.append(f"{path or 'root'}: type mismatch - expected {type(expected).__name__}={expected!r}, generated {type(generated).__name__}={generated!r}")
		return diffs

	# Compare dicts recursively
	if isinstance(expected, dict):
		all_keys = set(expected.keys()) | set(generated.keys())
		for key in sorted(all_keys):
			new_path = f"{path}.{key}" if path else key
			if key not in expected:
				diffs.append(f"{new_path}: unexpected field in generated (value={generated[key]!r})")
			elif key not in generated:
				diffs.append(f"{new_path}: missing field in generated (expected={expected[key]!r})")
			else:
				diffs.extend(_generate_field_diff_report(expected[key], generated[key], new_path))
		return diffs

	# Compare lists recursively
	if isinstance(expected, list):
		if len(expected) != len(generated):
			diffs.append(f"{path or 'root'}: list length mismatch - expected {len(expected)}, generated {len(generated)}")
			# Still compare common elements
			for i in range(min(len(expected), len(generated))):
				new_path = f"{path}.{i}" if path else f"[{i}]"
				diffs.extend(_generate_field_diff_report(expected[i], generated[i], new_path))
		else:
			for i, (exp_item, gen_item) in enumerate(zip(expected, generated)):
				new_path = f"{path}.{i}" if path else f"[{i}]"
				diffs.extend(_generate_field_diff_report(exp_item, gen_item, new_path))
		return diffs

	# Compare primitives
	if expected != generated:
		diffs.append(f"{path or 'root'}: expected={expected!r}, generated={generated!r}")

	return diffs


def _compare_yaml_exact(
	expected: dict,
	generated: dict,
	label: str,
) -> None:
	"""Compare expected and generated YAML data with detailed diff reporting.

	Validates that timestamp fields are populated, then performs exact comparison
	of all non-timestamp fields. Fails test with detailed diff report if any
	mismatches found.

	Args:
		expected: Expected data from fixture
		generated: Generated data from pipeline
		label: Label for error messages (e.g., "Division ocd-division/...")

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

	# Generate diff report for all non-timestamp fields
	diffs = _generate_field_diff_report(expected, generated)

	# If there are differences, fail with detailed report
	if diffs:
		diff_report = "\n".join(f"  - {diff}" for diff in diffs)
		raise AssertionError(f"{label}: Field mismatches found:\n{diff_report}")


@pytest.mark.integration
def test_generate_pipeline_main_style_integration(tmp_path: Path) -> None:
	"""Run generate_pipeline main-style flow over five sample OCD IDs.

	Uses:
	- Input: tests/sample_data/testing_ocd_sample.csv
	- Expected output fixtures:
	  - tests/sample_output/divisions
	  - tests/sample_output/jurisdictions
	"""

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
		assert response.status.status in (Status.SUCCESS, Status.SKIPPED)
		assert response.status.status is not Status.FAILED
		assert response.division_path is not None
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


@pytest.mark.integration
def test_generate_pipeline_creyton_sample_comprehensive(tmp_path: Path) -> None:
	"""Comprehensive integration test for GeneratePipeline with exact field matching.

	Tests:
	1. Structure validation - YAML validity and Pydantic model compliance
	2. Field population - All required fields have values
	3. Exact value matching - All non-timestamp fields match expected fixtures exactly
	4. Timestamp validation - Timestamp fields are populated and parseable
	5. No placeholder values - Test fails if any placeholders like "missing-geoid" are generated

	Uses:
	- Input: tests/sample_data/testing_ocd_sample.csv (government classifications only)
	- Validation CSV: Built from expected fixtures
	- Expected output fixtures:
	  - tests/sample_output/divisions/test/**/\*.yaml
	  - tests/sample_output/jurisdictions/test/**/\*.yaml
	"""
	# Phase 1: Test Setup and Data Loading
	# Load only government classification jurisdictions (same pattern as existing test)
	target_rows = _load_target_rows()
	assert len(target_rows) >= 5

	division_ocdids = [row["division_ocdid"] for row in target_rows]
	jurisdiction_ocdids = [row["jurisdiction_ocdid"] for row in target_rows]

	# Load expected output fixtures
	division_fixtures = _load_fixture_index(SAMPLE_OUTPUT_DIVISIONS)
	jurisdiction_fixtures = _load_fixture_index(SAMPLE_OUTPUT_JURISDICTIONS)

	# Verify all test divisions have fixtures
	for ocdid in division_ocdids:
		assert ocdid in division_fixtures, f"Missing division fixture for {ocdid}"
	for ocdid in jurisdiction_ocdids:
		assert ocdid in jurisdiction_fixtures, f"Missing jurisdiction fixture for {ocdid}"

	# Build validation CSV from fixtures
	validation_csv = _build_validation_csv(tmp_path, division_ocdids, division_fixtures)

	# Set up temporary output directories
	division_output_dir = tmp_path / "divisions"
	jurisdiction_output_dir = tmp_path / "jurisdictions"

	# Phase 2: Pipeline Execution
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

	# Collect responses and file paths
	assert len(responses) == len(division_ocdids)
	generated_division_paths: list[Path] = []
	generated_jurisdiction_paths: list[Path] = []

	for response in responses:
		assert response.status.status in (Status.SUCCESS, Status.SKIPPED), \
			f"Pipeline failed: {response.status.error}"
		assert response.status.status is not Status.FAILED
		assert response.division_path is not None
		division_path = Path(response.division_path)
		assert division_path.exists(), f"Division file not found: {division_path}"
		generated_division_paths.append(division_path)

		if response.jurisdiction_path:
			jurisdiction_path = Path(response.jurisdiction_path)
			assert jurisdiction_path.exists(), f"Jurisdiction file not found: {jurisdiction_path}"
			generated_jurisdiction_paths.append(jurisdiction_path)

	# Phase 3: Structure Validation
	# Validate YAML parsability and load all generated files
	generated_divisions: list[dict] = []
	generated_jurisdictions: list[dict] = []
	validation_errors: list[str] = []

	for division_path in generated_division_paths:
		with division_path.open(encoding="utf-8") as handle:
			data = yaml.safe_load(handle)
			assert isinstance(data, dict), f"Division YAML is not a dict: {division_path}"
			generated_divisions.append(data)

			# Validate against Pydantic model (collect errors, don't fail immediately)
			try:
				Division(**data)
			except Exception as e:
				validation_errors.append(f"Division Pydantic validation failed for {data.get('ocdid', division_path)}: {e}")

	for jurisdiction_path in generated_jurisdiction_paths:
		with jurisdiction_path.open(encoding="utf-8") as handle:
			data = yaml.safe_load(handle)
			assert isinstance(data, dict), f"Jurisdiction YAML is not a dict: {jurisdiction_path}"
			generated_jurisdictions.append(data)

			# Validate against Pydantic model (collect errors, don't fail immediately)
			try:
				Jurisdiction(**data)
			except Exception as e:
				validation_errors.append(f"Jurisdiction Pydantic validation failed for {data.get('ocdid', jurisdiction_path)}: {e}")

	# Phase 4: Field Population Validation
	for gen_div in generated_divisions:
		ocdid = gen_div.get("ocdid")

		# Check required fields are populated (collect errors)
		if not gen_div.get("id"):
			validation_errors.append(f"Division {ocdid}: 'id' field is empty")
		if not gen_div.get("ocdid"):
			validation_errors.append(f"Division {ocdid}: 'ocdid' field is empty")
		if not gen_div.get("country"):
			validation_errors.append(f"Division {ocdid}: 'country' field is empty")
		if not gen_div.get("display_name"):
			validation_errors.append(f"Division {ocdid}: 'display_name' field is empty")
		if "geometries" not in gen_div:
			validation_errors.append(f"Division {ocdid}: 'geometries' field is missing")
		if "also_known_as" not in gen_div:
			validation_errors.append(f"Division {ocdid}: 'also_known_as' field is missing")
		if not gen_div.get("sourcing"):
			validation_errors.append(f"Division {ocdid}: 'sourcing' field is empty")
		if not gen_div.get("accurate_asof"):
			validation_errors.append(f"Division {ocdid}: 'accurate_asof' field is empty")
		if not gen_div.get("last_updated"):
			validation_errors.append(f"Division {ocdid}: 'last_updated' field is empty")
		if not gen_div.get("jurisdiction_id"):
			validation_errors.append(f"Division {ocdid}: 'jurisdiction_id' field is empty")

		# Check government_identifiers
		gov_ids = gen_div.get("government_identifiers")
		if not gov_ids:
			validation_errors.append(f"Division {ocdid}: 'government_identifiers' field is empty")
		else:
			if not gov_ids.get("namelsad"):
				validation_errors.append(f"Division {ocdid}: government_identifiers.namelsad is empty")
			if not gov_ids.get("statefp"):
				validation_errors.append(f"Division {ocdid}: government_identifiers.statefp is empty")
			if "sldust" not in gov_ids:
				validation_errors.append(f"Division {ocdid}: government_identifiers.sldust is missing")
			if "sldlst" not in gov_ids:
				validation_errors.append(f"Division {ocdid}: government_identifiers.sldlst is missing")
			if "countyfp" not in gov_ids:
				validation_errors.append(f"Division {ocdid}: government_identifiers.countyfp is missing")
			if "county_names" not in gov_ids:
				validation_errors.append(f"Division {ocdid}: government_identifiers.county_names is missing")
			if not gov_ids.get("lsad"):
				validation_errors.append(f"Division {ocdid}: government_identifiers.lsad is empty")
			if not gov_ids.get("geoid"):
				validation_errors.append(f"Division {ocdid}: government_identifiers.geoid is empty")

			# Check for placeholder values (should never be generated)
			geoid = gov_ids.get("geoid", "")
			if geoid.startswith("missing-"):
				validation_errors.append(f"Division {ocdid}: Placeholder value found in geoid: {geoid!r}. Pipeline must generate complete data.")

	for gen_jur in generated_jurisdictions:
		ocdid = gen_jur.get("ocdid")

		# Check required fields are populated (collect errors)
		if not gen_jur.get("id"):
			validation_errors.append(f"Jurisdiction {ocdid}: 'id' field is empty")
		if not gen_jur.get("ocdid"):
			validation_errors.append(f"Jurisdiction {ocdid}: 'ocdid' field is empty")
		if not gen_jur.get("name"):
			validation_errors.append(f"Jurisdiction {ocdid}: 'name' field is empty")
		if not gen_jur.get("url"):
			validation_errors.append(f"Jurisdiction {ocdid}: 'url' field is empty")
		if not gen_jur.get("classification"):
			validation_errors.append(f"Jurisdiction {ocdid}: 'classification' field is empty")
		if "legislative_sessions" not in gen_jur:
			validation_errors.append(f"Jurisdiction {ocdid}: 'legislative_sessions' field is missing")
		if "feature_flags" not in gen_jur:
			validation_errors.append(f"Jurisdiction {ocdid}: 'feature_flags' field is missing")
		if "term" not in gen_jur:
			validation_errors.append(f"Jurisdiction {ocdid}: 'term' field is missing")
		if not gen_jur.get("sourcing"):
			validation_errors.append(f"Jurisdiction {ocdid}: 'sourcing' field is empty")
		if not gen_jur.get("accurate_asof"):
			validation_errors.append(f"Jurisdiction {ocdid}: 'accurate_asof' field is empty")
		if not gen_jur.get("last_updated"):
			validation_errors.append(f"Jurisdiction {ocdid}: 'last_updated' field is empty")

	# Phase 5: Exact Value Matching
	for gen_div in generated_divisions:
		ocdid = gen_div["ocdid"]
		expected_div = division_fixtures[ocdid]

		# Use comprehensive diff comparison (collect errors, don't fail immediately)
		try:
			_compare_yaml_exact(expected_div, gen_div, f"Division {ocdid}")
		except AssertionError as e:
			validation_errors.append(str(e))

	for gen_jur in generated_jurisdictions:
		ocdid = gen_jur["ocdid"]
		expected_jur = jurisdiction_fixtures[ocdid]

		# Use comprehensive diff comparison (collect errors, don't fail immediately)
		try:
			_compare_yaml_exact(expected_jur, gen_jur, f"Jurisdiction {ocdid}")
		except AssertionError as e:
			validation_errors.append(str(e))

	# Report all validation errors at once
	if validation_errors:
		error_report = "\n\n" + "\n\n".join(f"{i+1}. {err}" for i, err in enumerate(validation_errors))
		raise AssertionError(f"Test identified {len(validation_errors)} issue(s) in pipeline output:{error_report}")

