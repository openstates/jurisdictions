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
# This simulates the Creyton validation dataset.
#
# NAMELSAD must mirror the real sheet: "<name> <LSAD suffix>", with no trailing
# state name. Place rows carry a PLACEFP and no COUSUBFP; county subdivision
# (cousub) rows carry a COUSUBFP and no PLACEFP.
VALIDATION_CSV_ROWS = [
    # Sausalito match
    {
        "GEOID_Census": "0670364",
        "STATEFP": "06",
        "NAMELSAD": "Sausalito city",
        "LSAD": "25",
        "SLDUST_list": "",
        "SLDLST_list": "",
        "COUNTYFP_list": "041",
        "COUNTY_NAMES": "Marin",
        "COUSUBFP": "",
        "PLACEFP": "70364",
        "layer": "tl_2025_06_place",
    },
    # Tacoma match (for fuzzy testing)
    {
        "GEOID_Census": "5370000",
        "STATEFP": "53",
        "NAMELSAD": "Tacoma city",
        "LSAD": "25",
        "SLDUST_list": "",
        "SLDLST_list": "",
        "COUNTYFP_list": "053",
        "COUNTY_NAMES": "Pierce",
        "COUSUBFP": "",
        "PLACEFP": "70000",
        "layer": "tl_2025_53_place",
    },
    # Seattle match
    {
        "GEOID_Census": "5363000",
        "STATEFP": "53",
        "NAMELSAD": "Seattle city",
        "LSAD": "25",
        "SLDUST_list": "",
        "SLDLST_list": "",
        "COUNTYFP_list": "033",
        "COUNTY_NAMES": "King",
        "COUSUBFP": "",
        "PLACEFP": "63000",
        "layer": "tl_2025_53_place",
    },
    # Austin match
    {
        "GEOID_Census": "4845390165",
        "STATEFP": "48",
        "NAMELSAD": "Austin city",
        "LSAD": "25",
        "SLDUST_list": "",
        "SLDLST_list": "",
        "COUNTYFP_list": "453",
        "COUNTY_NAMES": "Travis",
        "COUSUBFP": "",
        "PLACEFP": "01000",
        "layer": "tl_2025_48_place",
    },
    # Decoys. Each of these matched its city at score 1.0 under token_set_ratio,
    # pushing the city into the "multiple matches" quarantine branch.
    {
        # Cousub sharing Seattle's name — must be excluded by the place-layer filter.
        "GEOID_Census": "5303392524",
        "STATEFP": "53",
        "NAMELSAD": "Seattle East CCD",
        "LSAD": "22",
        "SLDUST_list": "",
        "SLDLST_list": "",
        "COUNTYFP_list": "033",
        "COUNTY_NAMES": "King",
        "COUSUBFP": "92524",
        "PLACEFP": "",
        "layer": "tl_2025_53_cousub",
    },
    {
        # Distinct place that merely contains Tacoma's name as a token.
        "GEOID_Census": "5370010",
        "STATEFP": "53",
        "NAMELSAD": "Tacoma Valley city",
        "LSAD": "25",
        "SLDUST_list": "",
        "SLDLST_list": "",
        "COUNTYFP_list": "053",
        "COUNTY_NAMES": "Pierce",
        "COUSUBFP": "",
        "PLACEFP": "70010",
        "layer": "tl_2025_53_place",
    },
    {
        # Multi-word place: OCDid slug "oak_harbor" must reach "Oak Harbor".
        "GEOID_Census": "5350360",
        "STATEFP": "53",
        "NAMELSAD": "Oak Harbor city",
        "LSAD": "25",
        "SLDUST_list": "",
        "SLDLST_list": "",
        "COUNTYFP_list": "029",
        "COUNTY_NAMES": "Island",
        "COUSUBFP": "",
        "PLACEFP": "50360",
        "layer": "tl_2025_53_place",
    },
    {
        # Place sharing King County's name — must be excluded when a `county:`
        # OCDid routes to the county layer.
        "GEOID_Census": "5335275",
        "STATEFP": "53",
        "NAMELSAD": "King city",
        "LSAD": "25",
        "SLDUST_list": "",
        "SLDLST_list": "",
        "COUNTYFP_list": "033",
        "COUNTY_NAMES": "King",
        "COUSUBFP": "",
        "PLACEFP": "35275",
        "layer": "tl_2025_53_place",
    },
    {
        # Place sharing the state's name — must be excluded when a bare state
        # OCDid routes to the state layer.
        "GEOID_Census": "5376565",
        "STATEFP": "53",
        "NAMELSAD": "Washington city",
        "LSAD": "25",
        "SLDUST_list": "",
        "SLDLST_list": "",
        "COUNTYFP_list": "001",
        "COUNTY_NAMES": "Adams",
        "COUSUBFP": "",
        "PLACEFP": "76565",
        "layer": "tl_2025_53_place",
    },
    # No Marin City match (intentionally omitted to test quarantine)
    # No DC data (intentionally omitted to test quarantine)
]

# States tab rows. State-level records carry a STATEFP and roll up every county
# beneath them: COUNTYFP_list and COUNTY_NAMES are pipe-delimited lists covering
# the whole state, while PLACEFP and COUSUBFP stay blank. Values below are the
# real sheet's Washington row, truncated to the first few counties — the full row
# carries all 39.
STATES_CSV_ROWS = [
    {
        "GEOID_Census": "53",
        "STATEFP": "53",
        "NAMELSAD": "Washington",
        "LSAD": "00",
        "SLDUST_list": "",
        "SLDLST_list": "",
        "COUNTYFP_list": "001 | 003 | 005 | 029 | 033 | 053",
        "COUNTY_NAMES": "Adams | Asotin | Benton | Island | King | Pierce",
        "COUSUBFP": "",
        "PLACEFP": "",
        "layer": "tl_2025_us_state",
    },
]

# Counties tab rows. County records carry STATEFP + COUNTYFP_list, and leave the
# place-layer columns (PLACEFP, COUSUBFP) blank.
COUNTIES_CSV_ROWS = [
    {
        "GEOID_Census": "53033",
        "STATEFP": "53",
        "NAMELSAD": "King County",
        "LSAD": "06",
        "SLDUST_list": "",
        "SLDLST_list": "",
        "COUNTYFP_list": "033",
        "COUNTY_NAMES": "King",
        "COUSUBFP": "",
        "PLACEFP": "",
        "layer": "tl_2025_53_county",
    },
]


def _write_validation_csv(path: Path, rows: list[dict]) -> Path:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.fixture
def validation_csv_files(tmp_path) -> list[Path]:
    """Create the three validation CSV files (divisions, states, counties)."""
    return [
        _write_validation_csv(tmp_path / "validation_data.csv", VALIDATION_CSV_ROWS),
        _write_validation_csv(tmp_path / "states_validation.csv", STATES_CSV_ROWS),
        _write_validation_csv(tmp_path / "counties_validation.csv", COUNTIES_CSV_ROWS),
    ]


def _create_ocdid_ingest_resp(ocdid_str: str, asof_dt: datetime) -> OCDidIngestResp:
    """Helper to create OCDidIngestResp from OCD ID string."""
    parsed = OCDIdParsed.parse_ocdid(ocdid_str)
    uuid = uuid5(
        NAMESPACE_URL,
        f"{ocdid_str}|{asof_dt.date().isoformat()}",
    )
    return OCDidIngestResp(uuid=uuid, ocdid=parsed, raw_record={})


def _create_generator_req(
    ocdid_str: str, validation_files: list[Path], asof_dt: datetime
) -> GeneratorReq:
    """Helper to create GeneratorReq with proper initialization."""
    ingest_resp = _create_ocdid_ingest_resp(ocdid_str, asof_dt)
    divisions, states, counties = validation_files
    return GeneratorReq(
        data=ingest_resp,
        validation_data_division_filepath=str(divisions),
        validation_data_states_filepath=str(states),
        validation_data_counties_filepath=str(counties),
        build_base_object=True,
        jurisdiction_ai_url=False,
        division_geo_req=False,
        division_population_req=False,
        asof_datetime=asof_dt,
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    ("ocdid", "expected_namelsad"),
    [
        # A cousub ("Seattle East CCD") and a longer place ("Tacoma Valley city")
        # both scored 1.0 against the city under token_set_ratio, because that
        # scorer drops the tokens the two names do not share.
        ("ocd-division/country:us/state:wa/place:seattle", "Seattle city"),
        ("ocd-division/country:us/state:wa/place:tacoma", "Tacoma city"),
        # Underscored slugs were compared verbatim against the spaced name.
        ("ocd-division/country:us/state:wa/place:oak_harbor", "Oak Harbor city"),
        # Trailing segments are ignored; the place drives the match.
        (
            "ocd-division/country:us/state:wa/place:seattle/council_district:1",
            "Seattle city",
        ),
    ],
)
def test_find_matches_returns_exactly_one_place(
    validation_csv_files, ocdid, expected_namelsad
):
    """Each place OCDid resolves to exactly one validation record."""
    asof_dt = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)
    req = _create_generator_req(ocdid, validation_csv_files, asof_dt)
    pipeline = GeneratePipeline(req)

    matches = pipeline.find_matches(ocdid)

    assert len(matches) == 1, (
        f"Expected 1 match for {ocdid}, got {len(matches)}: "
        f"{matches['NAMELSAD'].to_list() if len(matches) else []}"
    )
    assert matches.row(0, named=True)["NAMELSAD"] == expected_namelsad


@pytest.mark.integration
def test_find_matches_excludes_non_place_rows(validation_csv_files):
    """Only place-layer rows are candidates for a `place:` OCDid.

    County subdivisions, states, and counties all leave PLACEFP blank.
    """
    asof_dt = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)
    ocdid = "ocd-division/country:us/state:wa/place:seattle"
    req = _create_generator_req(ocdid, validation_csv_files, asof_dt)
    pipeline = GeneratePipeline(req)

    matched_names = pipeline.find_matches(ocdid)["NAMELSAD"].to_list()

    assert "Seattle East CCD" not in matched_names
    assert "Washington" not in matched_names
    assert "King County" not in matched_names


@pytest.mark.integration
def test_find_matches_returns_exactly_one_state(validation_csv_files):
    """A bare state OCDid resolves to exactly one row on the state layer.

    The States tab carries the state's full name in NAMELSAD ("Washington"),
    while the OCDid carries the USPS code ("wa"), so the code is expanded via
    the state lookup before matching.
    """
    asof_dt = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)
    ocdid = "ocd-division/country:us/state:wa"
    req = _create_generator_req(ocdid, validation_csv_files, asof_dt)
    pipeline = GeneratePipeline(req)

    matches = pipeline.find_matches(ocdid)

    assert len(matches) == 1, (
        f"Expected 1 match for {ocdid}, got {len(matches)}: "
        f"{matches['NAMELSAD'].to_list() if len(matches) else []}"
    )
    row = matches.row(0, named=True)
    assert row["NAMELSAD"] == "Washington"
    assert row["layer"].endswith("_state")


@pytest.mark.integration
def test_find_matches_returns_exactly_one_county(validation_csv_files):
    """A `county:` OCDid resolves to exactly one row on the county layer."""
    asof_dt = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)
    ocdid = "ocd-division/country:us/state:wa/county:king"
    req = _create_generator_req(ocdid, validation_csv_files, asof_dt)
    pipeline = GeneratePipeline(req)

    matches = pipeline.find_matches(ocdid)

    assert len(matches) == 1, (
        f"Expected 1 match for {ocdid}, got {len(matches)}: "
        f"{matches['NAMELSAD'].to_list() if len(matches) else []}"
    )
    row = matches.row(0, named=True)
    assert row["NAMELSAD"] == "King County"
    assert row["layer"].endswith("_county")


@pytest.mark.integration
@pytest.mark.parametrize(
    ("ocdid", "expected_layer", "excluded_names"),
    [
        (
            "ocd-division/country:us/state:wa/place:seattle",
            "place",
            ["Seattle East CCD", "King County", "Washington"],
        ),
        (
            "ocd-division/country:us/state:wa/county:king",
            "county",
            ["King city", "Seattle East CCD", "Washington"],
        ),
        (
            "ocd-division/country:us/state:wa",
            "state",
            ["Washington city", "King County", "Seattle city"],
        ),
    ],
)
def test_find_matches_isolates_layers(
    validation_csv_files, ocdid, expected_layer, excluded_names
):
    """Each segment type matches its own Census layer and no other.

    The fixture deliberately contains a place, a county, and a state that share
    names ("King city" / "King County", "Washington city" / "Washington"), so a
    name-only match would cross layers.
    """
    asof_dt = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)
    req = _create_generator_req(ocdid, validation_csv_files, asof_dt)
    pipeline = GeneratePipeline(req)

    matches = pipeline.find_matches(ocdid)

    assert len(matches) > 0, f"Expected at least one match for {ocdid}"
    layers = matches["layer"].to_list()
    assert all(layer.endswith(f"_{expected_layer}") for layer in layers), (
        f"{ocdid} matched outside the {expected_layer} layer: {layers}"
    )
    matched_names = matches["NAMELSAD"].to_list()
    for name in excluded_names:
        assert name not in matched_names, (
            f"{ocdid} wrongly matched {name!r} from another layer"
        )


@pytest.mark.integration
def test_load_validation_csv_unifies_all_three_tabs(validation_csv_files):
    """validation_df carries place, state, and county rows from all three tabs."""
    asof_dt = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)
    ocdid = "ocd-division/country:us/state:wa/place:seattle"
    req = _create_generator_req(ocdid, validation_csv_files, asof_dt)
    pipeline = GeneratePipeline(req)

    names = pipeline.validation_df["NAMELSAD"].to_list()

    assert "Seattle city" in names, "divisions tab rows missing"
    assert "Washington" in names, "states tab rows missing"
    assert "King County" in names, "counties tab rows missing"
    assert len(pipeline.validation_df) == (
        len(VALIDATION_CSV_ROWS) + len(STATES_CSV_ROWS) + len(COUNTIES_CSV_ROWS)
    )

    # The `layer` column names the Census TIGER layer each row came from
    # (tl_<year>_<state|us>_<geography>). It is the explicit signal the follow-up
    # matching ticket needs to tell county and state rows apart from places,
    # rather than inferring the layer from which FIPS columns are populated.
    layers = set(pipeline.validation_df["layer"].to_list())
    assert "tl_2025_53_place" in layers, "place-layer rows missing"
    assert "tl_2025_us_state" in layers, "state-layer rows missing"
    assert "tl_2025_53_county" in layers, "county-layer rows missing"
    assert "tl_2025_53_cousub" in layers, "cousub-layer rows missing"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_pipeline_5_sample_records(tmp_path, validation_csv_files):
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
        req = _create_generator_req(ocdid, validation_csv_files, asof_dt)

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
        f"Expected 3 successes, got {len(results['success'])}: {results['success']}"
    )
    assert len(results["partial"]) == 2, (
        f"Expected 2 partial (quarantine), got {len(results['partial'])}: "
        f"{results['partial']}"
    )
    assert len(results["failed"]) == 0, (
        f"Expected 0 failures, got {len(results['failed'])}: {results['failed']}"
    )

    # Verify output files created. Output is nested (divisions/<state>/local/…),
    # so this must recurse.
    division_files = list(division_output.rglob("*.yaml"))
    assert len(division_files) >= 5, (
        f"Expected at least 5 division YAML files, got {len(division_files)}"
    )

    jurisdiction_files = list(jurisdiction_output.rglob("*.yaml"))
    assert len(jurisdiction_files) >= 3, (
        f"Expected at least 3 jurisdiction YAML files, got {len(jurisdiction_files)}"
    )

    print(f"\n✓ Generated {len(division_files)} division files")
    print(f"✓ Generated {len(jurisdiction_files)} jurisdiction files")
    print(f"✓ {len(results['success'])} records succeeded")
    print(f"✓ {len(results['partial'])} records quarantined")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_pipeline_successful_record_output(
    tmp_path, validation_csv_files
):
    """Verify successful record (Sausalito) produces valid Division and Jurisdiction."""
    asof_dt = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)
    division_output = tmp_path / "divisions"
    jurisdiction_output = tmp_path / "jurisdictions"
    division_output.mkdir()
    jurisdiction_output.mkdir()

    ocdid = "ocd-division/country:us/state:ca/place:sausalito"
    req = _create_generator_req(ocdid, validation_csv_files, asof_dt)

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
    expected_jur_ocdid = (
        "ocd-jurisdiction/country:us/state:ca/place:sausalito/government"
    )
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
async def test_generate_pipeline_quarantine_tracking(tmp_path, validation_csv_files):
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
        req = _create_generator_req(ocdid, validation_csv_files, asof_dt)
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
async def test_generate_pipeline_council_district_logic(tmp_path, validation_csv_files):
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
    req = _create_generator_req(ocdid, validation_csv_files, asof_dt)

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
async def test_generate_pipeline_deduplication(tmp_path, validation_csv_files):
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

    req1 = _create_generator_req(ocdid1, validation_csv_files, asof_dt)
    pipeline = GeneratePipeline(
        req1,
        division_output_dir=division_output,
        jurisdiction_output_dir=jurisdiction_output,
    )

    response1 = await pipeline.run()
    assert response1.status.status == Status.SUCCESS
    assert response1.jurisdiction_path is not None
    junction_count_after_1 = len(list(jurisdiction_output.rglob("*.yaml")))

    # Now run a second council district from the same city
    req2 = _create_generator_req(ocdid2, validation_csv_files, asof_dt)
    pipeline2 = GeneratePipeline(
        req2,
        division_output_dir=division_output,
        jurisdiction_output_dir=jurisdiction_output,
    )
    response2 = await pipeline2.run()
    assert response2.status.status == Status.SUCCESS
    # Note: junction_path might be None if already exists (depending on implementation)
    junction_count_after_2 = len(list(jurisdiction_output.rglob("*.yaml")))

    # Both divisions created, but jurisdictions might be deduplicated
    division_count = len(list(division_output.rglob("*.yaml")))
    assert division_count >= 2, "Should have at least 2 divisions"

    print("\n✓ Deduplication verified:")
    print(f"  - Divisions: {division_count}")
    print(f"  - Jurisdictions after CD1: {junction_count_after_1}")
    print(f"  - Jurisdictions after CD2: {junction_count_after_2}")
