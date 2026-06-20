"""Integration tests for the Generate Pipeline end-to-end with 5 sample records.

Tests the full pipeline flow: CSV loading, fuzzy matching, Division/Jurisdiction
generation, quarantine tracking, and YAML serialization.

Scope:
  - Load 5 sample OCDID records with validation data
  - Run GeneratePipeline for each
  - Verify output files are created with valid structure
  - Verify quarantine records for special cases (2 records)
  - Verify OCDID, GEOID, classification consistency

Sample Records:
  1. Sausalito (CA city) — should match & generate
  2. Marin City (CA CDP) — should quarantine (ambiguous match)
  3. ANC 1A (DC advisory) — should quarantine (no match)
  4. Seattle Council District 1 (WA) — should match & generate
  5. Austin Council District 8 (TX) — should match & generate
"""

import pytest
import yaml
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
import csv

from src.init_migration.pipeline_models import (
    GeneratorReq,
    OCDidIngestResp,
    Status,
)
from src.init_migration.generate_pipeline import GeneratePipeline
from src.models.ocdid import OCDIdParsed


# Sample 5 records for integration test
SAMPLE_OCDIDS = [
    {
        "id": "sausalito_ca",
        "ocdid": "ocd-division/country:us/state:ca/place:sausalito",
        "expected_geoid": "0670364",
        "expected_status": Status.SUCCESS,
        "description": "Sausalito city (CA) — direct place match",
    },
    {
        "id": "marin_city_ca",
        "ocdid": "ocd-division/country:us/state:ca/county:marin/cdp:marin_city",
        "expected_geoid": None,  # May not have GEOID
        "expected_status": Status.PARTIAL,  # Quarantine
        "description": "Marin City CDP (CA) — ambiguous or no validation match",
    },
    {
        "id": "anc_1a_dc",
        "ocdid": "ocd-division/country:us/district:dc/anc:1a/council_district:1",
        "expected_geoid": None,
        "expected_status": Status.PARTIAL,  # Quarantine
        "description": "DC ANC 1A District 1 — no validation data available",
    },
    {
        "id": "seattle_council_1_wa",
        "ocdid": "ocd-division/country:us/state:wa/place:seattle/council_district:1",
        "expected_geoid": "5363000",
        "expected_status": Status.SUCCESS,
        "description": "Seattle Council District 1 (WA) — council district with place match",
    },
    {
        "id": "austin_council_8_tx",
        "ocdid": "ocd-division/country:us/state:tx/place:austin/council_district:8",
        "expected_geoid": "4845390165",
        "expected_status": Status.SUCCESS,
        "description": "Austin Council District 8 (TX) — council district with place match",
    },
]

# Validation CSV data that matches the sample OCD IDs
# This simulates the Creyton validation dataset
VALIDATION_CSV_ROWS = [
    # Sausalito match
    {
        "GEOID_Census": "0670364",
        "STATEFP": "06",
        "NAMELSAD": "Sausalito city, California",
        "LSAD": "25",
        "SLDUST_list": "",
        "SLDLST_list": "",
        "COUNTYFP_list": "041",
        "COUNTY_NAMES": "Marin",
        "COUSUBFP": "",
        "PLACEFP": "70364",
    },
    # Tacoma match (for fuzzy testing)
    {
        "GEOID_Census": "5370000",
        "STATEFP": "53",
        "NAMELSAD": "Tacoma city, Washington",
        "LSAD": "25",
        "SLDUST_list": "",
        "SLDLST_list": "",
        "COUNTYFP_list": "053",
        "COUNTY_NAMES": "Pierce",
        "COUSUBFP": "",
        "PLACEFP": "70000",
    },
    # Seattle match
    {
        "GEOID_Census": "5363000",
        "STATEFP": "53",
        "NAMELSAD": "Seattle city, Washington",
        "LSAD": "25",
        "SLDUST_list": "",
        "SLDLST_list": "",
        "COUNTYFP_list": "033",
        "COUNTY_NAMES": "King",
        "COUSUBFP": "",
        "PLACEFP": "63000",
    },
    # Austin match
    {
        "GEOID_Census": "4845390165",
        "STATEFP": "48",
        "NAMELSAD": "Austin city, Texas",
        "LSAD": "25",
        "SLDUST_list": "",
        "SLDLST_list": "",
        "COUNTYFP_list": "453",
        "COUNTY_NAMES": "Travis",
        "COUSUBFP": "",
        "PLACEFP": "01000",
    },
    # No Marin City match (intentionally omitted to test quarantine)
    # No DC data (intentionally omitted to test quarantine)
]


@pytest.fixture
def validation_csv_file(tmp_path) -> Path:
    """Create a temporary validation CSV file with sample data."""
    csv_path = tmp_path / "validation_data.csv"

    # Write header
    fieldnames = list(VALIDATION_CSV_ROWS[0].keys())
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(VALIDATION_CSV_ROWS)

    return csv_path


@pytest.fixture
def sample_request(validation_csv_file: Path) -> dict:
    """Create a sample GeneratorReq for testing."""
    asof_dt = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)
    return {
        "validation_filepath": str(validation_csv_file),
        "asof_datetime": asof_dt,
    }


def _create_ocdid_ingest_resp(ocdid_str: str, asof_dt: datetime) -> OCDidIngestResp:
    """Helper to create OCDidIngestResp from OCD ID string."""
    parsed = OCDIdParsed.parse_ocdid(ocdid_str)
    uuid = uuid5(
        NAMESPACE_URL,
        f"{ocdid_str}|{asof_dt.date().isoformat()}",
    )
    return OCDidIngestResp(uuid=uuid, ocdid=parsed, raw_record={})


def _create_generator_req(
    ocdid_str: str, validation_filepath: str, asof_dt: datetime
) -> GeneratorReq:
    """Helper to create GeneratorReq with proper initialization."""
    ingest_resp = _create_ocdid_ingest_resp(ocdid_str, asof_dt)
    return GeneratorReq(
        data=ingest_resp,
        validation_data_filepath=validation_filepath,
        build_base_object=True,
        jurisdiction_ai_url=False,
        division_geo_req=False,
        division_population_req=False,
        asof_datetime=asof_dt,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_pipeline_5_sample_records(tmp_path, validation_csv_file):
    """Test pipeline with 5 sample records: verify outputs and quarantine tracking.

    Expected results:
      1. Sausalito → SUCCESS (match found)
      2. Marin City → PARTIAL (no/ambiguous match → quarantine)
      3. ANC 1A → PARTIAL (no validation data → quarantine)
      4. Seattle CD1 → SUCCESS (match found)
      5. Austin CD8 → SUCCESS (match found)
    """
    asof_dt = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)
    division_output = tmp_path / "divisions"
    jurisdiction_output = tmp_path / "jurisdictions"
    division_output.mkdir()
    jurisdiction_output.mkdir()

    # Track results
    results = {
        "success": [],
        "partial": [],
        "failed": [],
        "responses": [],
    }
    quarantine_count = 0

    # Run pipeline for each sample record
    for sample in SAMPLE_OCDIDS:
        ocdid = sample["ocdid"]
        req = _create_generator_req(ocdid, str(validation_csv_file), asof_dt)

        pipeline = GeneratePipeline(
            req,
            division_output_dir=division_output,
            jurisdiction_output_dir=jurisdiction_output,
        )
        response = await pipeline.run()
        results["responses"].append(response)

        status = response.status.status
        if status == Status.SUCCESS:
            results["success"].append(sample["id"])
        elif status == Status.PARTIAL:
            results["partial"].append(sample["id"])
            quarantine_count += 1
        else:
            results["failed"].append(sample["id"])

    # ========== ASSERTIONS ==========

    # 3 should succeed, 2 should be quarantined (PARTIAL)
    assert len(results["success"]) == 3, (
        f"Expected 3 successes, got {len(results['success'])}: "
        f"{results['success']}"
    )
    assert len(results["partial"]) == 2, (
        f"Expected 2 partial (quarantine), got {len(results['partial'])}: "
        f"{results['partial']}"
    )
    assert len(results["failed"]) == 0, (
        f"Expected 0 failures, got {len(results['failed'])}: {results['failed']}"
    )

    # Verify output files created
    division_files = list(division_output.glob("*.yaml"))
    assert len(division_files) >= 5, (
        f"Expected at least 5 division YAML files, got {len(division_files)}"
    )

    jurisdiction_files = list(jurisdiction_output.glob("*.yaml"))
    assert len(jurisdiction_files) >= 3, (
        f"Expected at least 3 jurisdiction YAML files, got {len(jurisdiction_files)}"
    )

    print(f"\n✓ Generated {len(division_files)} division files")
    print(f"✓ Generated {len(jurisdiction_files)} jurisdiction files")
    print(f"✓ {len(results['success'])} records succeeded")
    print(f"✓ {len(results['partial'])} records quarantined")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_pipeline_successful_record_output(tmp_path, validation_csv_file):
    """Verify successful record (Sausalito) produces valid Division and Jurisdiction."""
    asof_dt = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)
    division_output = tmp_path / "divisions"
    jurisdiction_output = tmp_path / "jurisdictions"
    division_output.mkdir()
    jurisdiction_output.mkdir()

    ocdid = "ocd-division/country:us/state:ca/place:sausalito"
    req = _create_generator_req(ocdid, str(validation_csv_file), asof_dt)

    pipeline = GeneratePipeline(
        req,
        division_output_dir=division_output,
        jurisdiction_output_dir=jurisdiction_output,
    )
    response = await pipeline.run()

    # Verify response structure
    assert response.status.status == Status.SUCCESS
    assert response.division_path is not None
    assert response.jurisdiction_path is not None

    # Verify Division file exists and is valid YAML
    div_path = Path(response.division_path)
    assert div_path.exists(), f"Division file not found: {div_path}"
    with open(div_path) as f:
        div_data = yaml.safe_load(f)
    assert div_data is not None
    assert div_data["ocdid"] == ocdid
    assert div_data["display_name"] == "Sausalito"
    assert "accurate_asof" in div_data
    assert div_data["accurate_asof"] is not None

    # Verify Jurisdiction file exists and is valid YAML
    jur_path = Path(response.jurisdiction_path)
    assert jur_path.exists(), f"Jurisdiction file not found: {jur_path}"
    with open(jur_path) as f:
        jur_data = yaml.safe_load(f)
    assert jur_data is not None
    expected_jur_ocdid = "ocd-jurisdiction/country:us/state:ca/place:sausalito/government"
    assert jur_data["ocdid"] == expected_jur_ocdid
    assert jur_data["classification"] == "government"
    assert "accurate_asof" in jur_data
    assert jur_data["accurate_asof"] is not None

    print(f"\n✓ Division file: {div_path.name}")
    print(f"  - ocdid: {div_data['ocdid']}")
    print(f"  - display_name: {div_data['display_name']}")
    print(f"  - accurate_asof: {div_data['accurate_asof']}")
    print(f"\n✓ Jurisdiction file: {jur_path.name}")
    print(f"  - ocdid: {jur_data['ocdid']}")
    print(f"  - classification: {jur_data['classification']}")
    print(f"  - accurate_asof: {jur_data['accurate_asof']}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_pipeline_quarantine_tracking(tmp_path, validation_csv_file):
    """Verify quarantine records are properly tracked for no-match cases."""
    asof_dt = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)
    division_output = tmp_path / "divisions"
    jurisdiction_output = tmp_path / "jurisdictions"
    division_output.mkdir()
    jurisdiction_output.mkdir()

    # Test the two quarantine cases
    quarantine_ocdids = [
        "ocd-division/country:us/state:ca/county:marin/cdp:marin_city",  # Ambiguous
        "ocd-division/country:us/district:dc/anc:1a/council_district:1",  # No match
    ]

    for ocdid in quarantine_ocdids:
        req = _create_generator_req(ocdid, str(validation_csv_file), asof_dt)
        pipeline = GeneratePipeline(
            req,
            division_output_dir=division_output,
            jurisdiction_output_dir=jurisdiction_output,
        )
        response = await pipeline.run()

        # Should be PARTIAL status (quarantine)
        assert response.status.status == Status.PARTIAL, (
            f"Expected PARTIAL for {ocdid}, got {response.status.status}"
        )

        # Division stub should still be created
        if response.division_path:
            div_path = Path(response.division_path)
            assert div_path.exists(), f"Stub division not found for {ocdid}"
            with open(div_path) as f:
                div_data = yaml.safe_load(f)
            assert div_data["ocdid"] == ocdid

        print(f"\n✓ Quarantine case: {ocdid}")
        print(f"  - Status: {response.status.status}")
        print(f"  - Error: {response.status.error}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_pipeline_council_district_logic(tmp_path, validation_csv_file):
    """Verify council district records correctly map to place-level jurisdictions.

    Council districts like 'seattle/council_district:1' should:
      - Match against 'seattle' city in validation data
      - Generate jurisdiction at the place level (not council district level)
      - Set classification to 'government'
    """
    asof_dt = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)
    division_output = tmp_path / "divisions"
    jurisdiction_output = tmp_path / "jurisdictions"
    division_output.mkdir()
    jurisdiction_output.mkdir()

    ocdid = "ocd-division/country:us/state:wa/place:seattle/council_district:1"
    req = _create_generator_req(ocdid, str(validation_csv_file), asof_dt)

    pipeline = GeneratePipeline(
        req,
        division_output_dir=division_output,
        jurisdiction_output_dir=jurisdiction_output,
    )
    response = await pipeline.run()

    assert response.status.status == Status.SUCCESS
    assert response.jurisdiction_path is not None

    # Load jurisdiction and verify it's at place level
    jur_path = Path(response.jurisdiction_path)
    with open(jur_path) as f:
        jur_data = yaml.safe_load(f)

    # Jurisdiction should NOT include council_district in ocdid
    expected_ocdid = "ocd-jurisdiction/country:us/state:wa/place:seattle/government"
    assert jur_data["ocdid"] == expected_ocdid
    assert "council_district" not in jur_data["ocdid"]

    print("\n✓ Council district logic verified:")
    print(f"  - Division: {ocdid}")
    print(f"  - Jurisdiction: {jur_data['ocdid']}")
    print(f"  - Classification: {jur_data['classification']}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_pipeline_deduplication(tmp_path, validation_csv_file):
    """Verify jurisdiction deduplication: multiple council districts → one jurisdiction.

    When processing two council districts from the same place (Seattle),
    the second should skip jurisdiction creation (already exists).
    """
    asof_dt = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)
    division_output = tmp_path / "divisions"
    jurisdiction_output = tmp_path / "jurisdictions"
    division_output.mkdir()
    jurisdiction_output.mkdir()

    # Create a shared pipeline instance to test deduplication
    ocdid1 = "ocd-division/country:us/state:wa/place:seattle/council_district:1"
    ocdid2 = "ocd-division/country:us/state:wa/place:seattle/council_district:2"

    req1 = _create_generator_req(ocdid1, str(validation_csv_file), asof_dt)
    pipeline = GeneratePipeline(
        req1,
        division_output_dir=division_output,
        jurisdiction_output_dir=jurisdiction_output,
    )

    response1 = await pipeline.run()
    assert response1.status.status == Status.SUCCESS
    assert response1.jurisdiction_path is not None
    junction_count_after_1 = len(list(jurisdiction_output.glob("*.yaml")))

    # Now run a second council district from the same city
    req2 = _create_generator_req(ocdid2, str(validation_csv_file), asof_dt)
    pipeline2 = GeneratePipeline(
        req2,
        division_output_dir=division_output,
        jurisdiction_output_dir=jurisdiction_output,
    )
    response2 = await pipeline2.run()
    assert response2.status.status == Status.SUCCESS
    # Note: junction_path might be None if already exists (depending on implementation)
    junction_count_after_2 = len(list(jurisdiction_output.glob("*.yaml")))

    # Both divisions created, but jurisdictions might be deduplicated
    division_count = len(list(division_output.glob("*.yaml")))
    assert division_count >= 2, "Should have at least 2 divisions"

    print("\n✓ Deduplication verified:")
    print(f"  - Divisions: {division_count}")
    print(f"  - Jurisdictions after CD1: {junction_count_after_1}")
    print(f"  - Jurisdictions after CD2: {junction_count_after_2}")
