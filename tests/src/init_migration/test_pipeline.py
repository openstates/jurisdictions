from __future__ import annotations

import asyncio
import csv
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest
import yaml

from src.init_migration.generate_pipeline import GeneratePipeline
from src.init_migration.models import GeneratorReq, OCDidIngestResp, Status
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
			req = GeneratorReq(
				data=OCDidIngestResp(
					uuid=uuid5(NAMESPACE_URL, ocdid),
					ocdid=ocdid,
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



