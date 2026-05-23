"""
Unit tests for generate_jurisdiction.py

Tests cover:
- JurGenerator initialization
- Jurisdiction OCD ID derivation
- Jurisdiction generation from Division
- Fallback name and URL generation
- YAML file serialization
- AI lookup stub behavior
"""

import pytest
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from src.init_migration.pipeline_models import GeneratorReq, OCDidIngestResp
from src.init_migration.generate_jurisdiction import JurGenerator, get_jurisdiction_filename
from src.models.division import Division
from src.models.jurisdiction import Jurisdiction
from src.models.ocdid import OCDidParsed
from src.models.source import SourceType
from src.utils.yaml_manager import YamlManager


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_req_jurisdiction(tmp_path) -> GeneratorReq:
	"""Create a GeneratorReq for jurisdiction generation."""
	parsed = OCDidParsed(
		raw_ocdid="ocd-division/country:us/state:ca/place:seattle",
		country="us",
		state="ca",
		place="seattle",
	)
	test_uuid = uuid5(
		NAMESPACE_URL,
		f"ocd-division/country:us/state:ca/place:seattle|{datetime.now(timezone.utc).date().isoformat()}",
	)
	resp = OCDidIngestResp(
		uuid=test_uuid,
		ocdid=parsed,
		raw_record={},
	)
	# Create a dummy validation CSV file
	validation_csv = tmp_path / "validation.csv"
	validation_csv.write_text("STATEFP,NAMELSAD,GEOID_Census\n06,Seattle,0600000\n")
	
	req = GeneratorReq(
		data=resp,
		build_base_object=False,
		jurisdiction_ai_url=False,  # AI lookup disabled for unit tests
		division_geo_req=False,
		division_population_req=False,
		validation_data_filepath=str(validation_csv),
	)
	return req


@pytest.fixture
def sample_division(sample_req_jurisdiction) -> Division:
	"""Create a sample Division object for testing."""
	return Division(
		ocdid="ocd-division/country:us/state:ca/place:seattle",
		country="us",
		display_name="Seattle",
		geometries=[],
		also_known_as=[],
		sourcing=[],
		jurisdiction_id="ocd-jurisdiction/country:us/state:ca/place:seattle/government",
		government_identifiers=None,
	)


@pytest.fixture
def jur_generator(sample_req_jurisdiction) -> JurGenerator:
	"""Create a JurGenerator instance for testing."""
	return JurGenerator(req=sample_req_jurisdiction)


# ============================================================================
# TEST: FILENAME GENERATION
# ============================================================================

class TestGetJurisdictionFilename:
	"""Tests for get_jurisdiction_filename function."""

	def test_filename_from_standard_ocdid(self):
		"""Filename should derive from second-to-last OCD ID segment."""
		ocdid = "ocd-jurisdiction/country:us/state:ca/place:seattle/government"
		test_uuid = uuid5(NAMESPACE_URL, "test")
		filename = get_jurisdiction_filename(ocdid, test_uuid)

		assert filename.endswith(f"_{test_uuid}.yaml")
		assert "place_seattle" in filename

	def test_filename_with_colons_replaced(self):
		"""Colons in OCD ID segments should be replaced with underscores."""
		ocdid = "ocd-jurisdiction/country:us/state:ca/county:06001/government"
		test_uuid = uuid5(NAMESPACE_URL, "test")
		filename = get_jurisdiction_filename(ocdid, test_uuid)

		assert "county_06001" in filename
		assert ":" not in filename  # No colons in filename

	def test_filename_handles_trailing_slash(self):
		"""Filename generation should handle trailing slashes."""
		ocdid = "ocd-jurisdiction/country:us/state:ca/place:seattle/government/"
		test_uuid = uuid5(NAMESPACE_URL, "test")
		filename = get_jurisdiction_filename(ocdid, test_uuid)

		assert "place_seattle" in filename
		assert filename.endswith(".yaml")


# ============================================================================
# TEST: JUR GENERATOR INITIALIZATION
# ============================================================================

class TestJurGeneratorInitialization:
	"""Tests for JurGenerator initialization."""

	def test_jur_generator_initializes(self, jur_generator, sample_req_jurisdiction):
		"""JurGenerator should initialize with request data."""
		assert jur_generator.req == sample_req_jurisdiction
		assert jur_generator.data == sample_req_jurisdiction.data
		assert jur_generator.uuid == sample_req_jurisdiction.data.uuid
		assert jur_generator.division is None
		assert jur_generator.jurisdiction is None

	def test_jur_generator_with_division(self, sample_req_jurisdiction, sample_division):
		"""JurGenerator should accept optional Division in constructor."""
		jur_gen = JurGenerator(req=sample_req_jurisdiction, division=sample_division)
		assert jur_gen.division == sample_division


# ============================================================================
# TEST: AI LOOKUP
# ============================================================================

class TestAILookup:
	"""Tests for AI lookup functionality."""

	def test_ai_lookup_disabled_returns_none(self, jur_generator, sample_division):
		"""AI lookup should return None when jurisdiction_ai_url is False."""
		jur_generator.req.jurisdiction_ai_url = False
		result = jur_generator._ai_lookup(sample_division)
		assert result is None

	def test_ai_lookup_enabled_raises_not_implemented(self, jur_generator, sample_division):
		"""AI lookup should raise NotImplementedError when jurisdiction_ai_url is True."""
		jur_generator.req.jurisdiction_ai_url = True
		with pytest.raises(NotImplementedError, match="AI jurisdiction lookup is not yet implemented"):
			jur_generator._ai_lookup(sample_division)


# ============================================================================
# TEST: JURISDICTION OCDID DERIVATION
# ============================================================================

class TestDeriveJurisdictionOCDId:
	"""Tests for _derive_jurisdiction_ocdid method."""

	def test_derive_from_standard_division_ocdid(self, jur_generator):
		"""Should derive jurisdiction OCD ID from division OCD ID."""
		division_ocdid = "ocd-division/country:us/state:ca/place:seattle"
		result = jur_generator._derive_jurisdiction_ocdid(division_ocdid, classification="government")

		assert result.startswith("ocd-jurisdiction/")
		assert "country:us" in result
		assert "state:ca" in result
		assert "place:seattle" in result
		assert result.endswith("/government")

	def test_derive_with_different_classification(self, jur_generator):
		"""Should use provided classification in OCD ID."""
		division_ocdid = "ocd-division/country:us/state:ca"
		result_gov = jur_generator._derive_jurisdiction_ocdid(division_ocdid, classification="government")
		result_leg = jur_generator._derive_jurisdiction_ocdid(division_ocdid, classification="legislature")

		assert result_gov.endswith("/government")
		assert result_leg.endswith("/legislature")

	def test_derive_removes_council_district(self, jur_generator):
		"""Should remove council_district segments from derived OCD ID."""
		division_ocdid = "ocd-division/country:us/state:ca/place:seattle/council_district:1"
		result = jur_generator._derive_jurisdiction_ocdid(division_ocdid, classification="government")

		assert "council_district" not in result
		assert "place:seattle" in result


# ============================================================================
# TEST: JURISDICTION GENERATION
# ============================================================================

class TestGenerateJurisdiction:
	"""Tests for generate_jurisdiction method."""

	def test_generate_jurisdiction_basic(self, jur_generator, sample_division):
		"""Should generate a Jurisdiction object from a Division."""
		jurisdiction = jur_generator.generate_jurisdiction(
			division=sample_division,
			uuid=jur_generator.uuid,
			classification="government"
		)

		assert isinstance(jurisdiction, Jurisdiction)
		assert jurisdiction.ocdid.startswith("ocd-jurisdiction/")
		assert jurisdiction.name is not None
		assert jurisdiction.url is not None
		assert jurisdiction.classification == "government"

	def test_generated_jurisdiction_has_required_fields(self, jur_generator, sample_division):
		"""Generated Jurisdiction should have all required fields."""
		jurisdiction = jur_generator.generate_jurisdiction(
			division=sample_division,
			uuid=jur_generator.uuid,
			classification="government"
		)

		# Required fields per Jurisdiction model
		assert jurisdiction.id is not None
		assert jurisdiction.ocdid is not None
		assert jurisdiction.name is not None
		assert jurisdiction.url is not None
		assert jurisdiction.classification is not None
		assert jurisdiction.legislative_sessions is not None
		assert jurisdiction.feature_flags is not None
		assert jurisdiction.sourcing is not None
		assert jurisdiction.accurate_asof is not None
		assert jurisdiction.last_updated is not None

	def test_generated_jurisdiction_fallback_name(self, jur_generator, sample_division):
		"""Generated Jurisdiction should use fallback name when AI lookup disabled."""
		jurisdiction = jur_generator.generate_jurisdiction(
			division=sample_division,
			uuid=jur_generator.uuid,
			classification="government"
		)

		# With AI disabled, should use deterministic fallback
		assert "Seattle" in jurisdiction.name
		assert "Government" in jurisdiction.name

	def test_generated_jurisdiction_fallback_url(self, jur_generator, sample_division):
		"""Generated Jurisdiction should use fallback URL when AI lookup disabled."""
		jurisdiction = jur_generator.generate_jurisdiction(
			division=sample_division,
			uuid=jur_generator.uuid,
			classification="government"
		)

		# With AI disabled, should use OpenCivicData fallback
		assert "opencivicdata.org" in jurisdiction.url
		assert sample_division.ocdid in jurisdiction.url

	def test_generate_with_different_classifications(self, jur_generator, sample_division):
		"""Should generate jurisdictions with different classifications."""
		for classification in ["government", "legislature", "school_system"]:
			jurisdiction = jur_generator.generate_jurisdiction(
				division=sample_division,
				uuid=jur_generator.uuid,
				classification=classification
			)
			assert jurisdiction.classification == classification

	def test_generate_requires_division(self, jur_generator):
		"""Should raise ValueError if Division is missing."""
		with pytest.raises(ValueError, match="Division object or ocdid is missing"):
			jur_generator.generate_jurisdiction(
				division=None,
				uuid=jur_generator.uuid
			)

	def test_generate_requires_division_ocdid(self, jur_generator):
		"""Should raise ValueError if Division OCD ID is missing."""
		bad_division = Division(
			ocdid="ocd-division/country:us/state:ca/place:seattle",  # Provide valid ocdid first
			country="us",
			display_name="Test",
			geometries=[],
			jurisdiction_id="test",
		)
		# Now set it to None to test the error condition
		bad_division.ocdid = None
		with pytest.raises(ValueError):
			jur_generator.generate_jurisdiction(
				division=bad_division,
				uuid=jur_generator.uuid
			)

	def test_generated_jurisdiction_sourcing(self, jur_generator, sample_division):
		"""Generated Jurisdiction should have sourcing information."""
		jurisdiction = jur_generator.generate_jurisdiction(
			division=sample_division,
			uuid=jur_generator.uuid
		)

		assert len(jurisdiction.sourcing) > 0
		source = jurisdiction.sourcing[0]
		assert "ocdid" in source.field
		assert "name" in source.field
		assert source.source_type == SourceType.HUMAN

	def test_generated_jurisdiction_timestamps(self, jur_generator, sample_division):
		"""Generated Jurisdiction should have valid timestamps."""
		jurisdiction = jur_generator.generate_jurisdiction(
			division=sample_division,
			uuid=jur_generator.uuid
		)

		assert jurisdiction.accurate_asof is not None
		assert jurisdiction.last_updated is not None
		assert isinstance(jurisdiction.accurate_asof, datetime)
		assert isinstance(jurisdiction.last_updated, datetime)

	def test_generated_jurisdiction_metadata_urls(self, jur_generator, sample_division):
		"""Generated Jurisdiction metadata should have urls field."""
		jurisdiction = jur_generator.generate_jurisdiction(
			division=sample_division,
			uuid=jur_generator.uuid
		)

		assert jurisdiction.metadata is not None
		assert hasattr(jurisdiction.metadata, "urls")
		assert isinstance(jurisdiction.metadata.urls, list)


# ============================================================================
# TEST: JURISDICTION EXISTENCE CHECKING
# ============================================================================

class TestJurisdictionExistence:
	"""Tests for _jurisdiction_exists and related methods."""

	def test_jurisdiction_exists_returns_bool(self, jur_generator):
		"""_jurisdiction_exists should return boolean."""
		result = jur_generator._jurisdiction_exists("ocd-jurisdiction/country:us/state:ca/place:seattle/government")
		assert isinstance(result, bool)

	def test_jurisdiction_exists_handles_invalid_ocdid(self, jur_generator):
		"""_jurisdiction_exists should handle invalid OCD IDs gracefully."""
		result = jur_generator._jurisdiction_exists("invalid-ocdid")
		assert isinstance(result, bool)


# ============================================================================
# TEST: YAML SERIALIZATION
# ============================================================================

class TestDumpJurisdiction:
	"""Tests for dump_jurisdiction method."""

	def test_dump_jurisdiction_creates_file(self, jur_generator, sample_division, tmp_path):
		"""dump_jurisdiction should create a YAML file."""
		jurisdiction = jur_generator.generate_jurisdiction(
			division=sample_division,
			uuid=jur_generator.uuid
		)
		jur_generator.jurisdiction = jurisdiction

		output_dir = tmp_path / "jurisdictions"
		output_path = jur_generator.dump_jurisdiction(output_dir=output_dir)

		assert output_path.exists()
		assert output_path.suffix == ".yaml"
		# The file should be created in a subdirectory structure (state/local/)
		assert "jurisdictions" in str(output_path)

	def test_dump_jurisdiction_file_contains_valid_yaml(self, jur_generator, sample_division, tmp_path):
		"""Dumped YAML file should contain valid YAML and Jurisdiction data."""
		jurisdiction = jur_generator.generate_jurisdiction(
			division=sample_division,
			uuid=jur_generator.uuid
		)
		jur_generator.jurisdiction = jurisdiction

		output_dir = tmp_path / "jurisdictions"
		output_path = jur_generator.dump_jurisdiction(output_dir=output_dir)

		# Use YamlManager to read and validate YAML
		yaml_mgr = YamlManager(base_path=output_dir)
		data = yaml_mgr.read(output_path)

		assert isinstance(data, dict)
		assert data.get("ocdid") == jurisdiction.ocdid
		assert data.get("name") == jurisdiction.name
		assert data.get("classification") == jurisdiction.classification

	def test_dump_jurisdiction_requires_generated_jurisdiction(self, jur_generator, tmp_path):
		"""dump_jurisdiction should raise error if jurisdiction not generated."""
		# JurGenerator without a generated jurisdiction
		with pytest.raises(ValueError, match="Jurisdiction object does not exist"):
			jur_generator.dump_jurisdiction(output_dir=tmp_path)


# ============================================================================
# TEST: INTEGRATION SCENARIOS
# ============================================================================

class TestJurisdictionGenerationIntegration:
	"""Integration tests for full jurisdiction generation workflow."""

	def test_full_workflow_division_to_jurisdiction(self, sample_req_jurisdiction, sample_division, tmp_path):
		"""Should complete full workflow: create generator, generate jurisdiction, dump file."""
		# Create generator
		jur_gen = JurGenerator(req=sample_req_jurisdiction, division=sample_division)

		# Generate jurisdiction
		jurisdiction = jur_gen.generate_jurisdiction(
			division=sample_division,
			uuid=jur_gen.uuid,
			classification="government"
		)

		# Dump to file
		output_dir = tmp_path / "jurisdictions"
		output_path = jur_gen.dump_jurisdiction(output_dir=output_dir)

		# Verify result
		assert output_path.exists()
		assert jurisdiction.ocdid is not None
		assert jurisdiction.name is not None

	def test_multiple_classifications_generate_distinct_jurisdictions(
		self, sample_req_jurisdiction, sample_division, tmp_path
	):
		"""Should generate distinct jurisdictions for different classifications."""
		classifications = ["government", "legislature", "school_system"]
		jurisdictions = []

		for classification in classifications:
			jur_gen = JurGenerator(req=sample_req_jurisdiction)
			jurisdiction = jur_gen.generate_jurisdiction(
				division=sample_division,
				uuid=jur_gen.uuid,
				classification=classification
			)
			jurisdictions.append(jurisdiction)

		# All should have different OCD IDs (due to different classifications)
		ocdids = [j.ocdid for j in jurisdictions]
		assert len(set(ocdids)) == len(ocdids)  # All unique

		# All should have the same base but different classification
		for jur in jurisdictions:
			assert "place:seattle" in jur.ocdid

