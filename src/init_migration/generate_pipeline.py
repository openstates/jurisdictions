"""
Orchestrator pipeline that coordinates division and jurisdiction generation.

This module accepts a `GeneratorReq` (single record) and delegates
generation work to `generate_division` and `generate_jurisdiction` modules.

Responsibilities:
- Load and cache validation CSV (singleton pattern)
- Implement fuzzy matching logic
- Orchestrate Division and Jurisdiction generation
- Handle three match outcomes (0, 1, 2+ matches)
- Track quarantine data and Jurisdiction deduplication
"""

import logging
from pathlib import Path
from src.init_migration.pipeline_models import GeneratorReq, GeneratorResp, GeneratorStatus, Status
from src.init_migration.generate_division import DivGenerator
from src.init_migration.generate_jurisdiction import JurGenerator
from src.utils.ocdid import ocdid_parser
from src.utils.place_name import namelsad_to_display_name
from src.models.division import Division
from src.models.jurisdiction import Jurisdiction
import polars as pl
from pydantic import BaseModel

# Try to import rapidfuzz, fall back to difflib if not available
try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    import difflib
    HAS_RAPIDFUZZ = False

logger = logging.getLogger(__name__)

# Fuzzy matching threshold (0-1 scale, 0.85 = 85% match required)
FUZZY_MATCH_THRESHOLD = 0.85

# Filename pattern constants
DIVISION_FILENAME_PATTERN = "{display_name}_{geoid}_{uuid}.yaml"
JURISDICTION_FILENAME_PATTERN = "{name}_{uuid}.yaml"

# Output directory constants
DIVISION_OUTPUT_DIR = "divisions"
JURISDICTION_OUTPUT_DIR = "jurisdictions"


def get_division_filename(display_name: str, geoid: str, uuid: str) -> str:
    """Generate Division YAML filename from components.

    Args:
        display_name: Human-readable name (e.g., 'Sausalito')
        geoid: Census GEOID (e.g., '0670364')
        uuid: UUID from GeneratorReq

    Returns:
        Filename string (e.g., 'sausalito_0670364_3fa85f64-5717-4562-b3fc-2c963f66afa6.yaml')
    """
    safe_display_name = display_name.lower().replace(" ", "_")
    return f"{safe_display_name}_{geoid}_{uuid}.yaml"


def get_jurisdiction_filename(name: str, uuid: str) -> str:
    """Generate Jurisdiction YAML filename from components.

    Args:
        name: Jurisdiction name (e.g., 'Sausalito City Government')
        uuid: UUID from GeneratorReq (same as corresponding Division)

    Returns:
        Filename string (e.g., 'sausalito_city_government_3fa85f64-5717-4562-b3fc-2c963f66afa6.yaml')
    """
    safe_name = name.lower().replace(" ", "_")
    return f"{safe_name}_{uuid}.yaml"



class NoMatch(BaseModel):
    """Tracks records that did not match during pipeline processing."""
    model_config = {"arbitrary_types_allowed": True}
    validation_no_ocdid_div: pl.DataFrame = pl.DataFrame()  # Validation records with no matching OCD ID
    ocdid_no_validation_div: list[dict] = []  # OCDids with no matching validation record or multiple matches


class GeneratePipeline:
    """Orchestrator that coordinates Division and Jurisdiction generation.

    Responsibilities:
    - Load and normalize validation CSV (singleton pattern per instance)
    - Implement fuzzy matching between OCDids and validation records
    - Orchestrate Division and Jurisdiction generation
    - Handle three match outcomes (0 matches, 1 match, 2+ matches)
    - Track quarantine data for researcher review
    - Deduplicate Jurisdictions across multiple Divisions
    """

    def __init__(
        self,
        req: GeneratorReq,
        division_output_dir: str | Path = DIVISION_OUTPUT_DIR,
        jurisdiction_output_dir: str | Path = JURISDICTION_OUTPUT_DIR,
    ) -> None:
        """Initialize the Pipeline with request data and load validation CSV.

        Args:
            req: GeneratorReq object containing OCDid, UUID, flags, and validation data filepath
        """
        self.req = req
        self.data = req.data
        self.uuid = self.data.uuid
        self.validation_data_filepath = req.validation_data_filepath
        self.asof_datetime = req.asof_datetime
        self.division_output_dir = Path(division_output_dir)
        self.jurisdiction_output_dir = Path(jurisdiction_output_dir)

        # OCDid is already parsed as OCDidParsed from Stage 1
        self.parsed_ocdid = self.data.ocdid

        # Initialize generated objects
        self.division: Division | None = None
        self.jurisdiction: Jurisdiction | None = None

        # Initialize quarantine and tracking
        self.quarantine = NoMatch()
        self.created_jurisdictions: set[str] = set()  # Track jurisdiction ocd_ids already created

        # Load and normalize validation CSV (synchronously, cached for all run() calls)
        self.validation_df: pl.DataFrame = self._load_validation_csv()
        self.validation_df = self._normalize_validation_data()

        logger.info(f"Pipeline initialized for OCDid: {self.data.ocdid.raw_ocdid}", extra={"uuid": str(self.uuid)})

    def _load_validation_csv(self) -> pl.DataFrame:
        """Load validation research CSV from URL or filepath.

        Returns:
            Polars DataFrame with all validation records

        Raises:
            ValueError: If CSV cannot be loaded
        """
        try:
            df = pl.read_csv(self.validation_data_filepath)
            logger.info(f"Loaded validation CSV: {df.shape[0]} rows, {df.shape[1]} columns")
            return df
        except Exception as e:
            logger.error(f"Failed to load validation CSV from {self.validation_data_filepath}", exc_info=True)
            raise ValueError(f"Cannot load validation CSV: {self.validation_data_filepath}") from e

    def _normalize_validation_data(self) -> pl.DataFrame:
        """Normalize validation data by adding normalized place names.

        Uses place_name.py to strip LSAD from NAMELSAD, adds lowercase normalized column
        for fuzzy matching.

        Returns:
            Updated Polars DataFrame with normalized place name column
        """
        try:
            # Add normalized place name column (lowercase, LSAD stripped)
            df = self.validation_df.with_columns(
                pl.col("NAMELSAD")
                .map_elements(lambda x: namelsad_to_display_name(x).lower() if x else "", return_dtype=pl.Utf8)
                .alias("normalized_place_name")
            )
            logger.info("Normalized validation data with place names")
            return df
        except Exception:
            logger.error("Failed to normalize validation data", exc_info=True)
            raise ValueError("Cannot normalize validation data")

    def find_matches(self, ocdid: str) -> pl.DataFrame:
        """Find matching validation records for a given OCDid using fuzzy matching.

        Args:
            ocdid: The OCD division ID to match (e.g., 'ocd-division/country:us/state:ca/place:sausalito')

        Returns:
            Polars DataFrame with 0, 1, or 2+ matching validation records
        """
        try:
            # Parse OCDid to extract state and place
            parsed = ocdid_parser(ocdid)  # Returns dict
            state = parsed.get("state")
            place = parsed.get("place")

            if not state or not place:
                logger.warning(f"Missing state or place in OCDid: {ocdid}")
                return pl.DataFrame()

            state_upper = state.upper()
            place_lower = place.lower()

            # Look up state FIPS code
            from src.utils.state_lookup import load_state_code_lookup
            state_lookup = load_state_code_lookup()
            state_fips_list = [item.get("statefps") for item in state_lookup if item.get("stateusps", "").upper() == state_upper]

            if not state_fips_list:
                logger.warning(f"State code not found: {state_upper}")
                return pl.DataFrame()

            state_fips = str(state_fips_list[0]).zfill(2)

            # Filter validation data by state
            state_df = self.validation_df.filter(pl.col("STATEFP").cast(pl.Utf8) == state_fips)

            if state_df.is_empty():
                logger.debug(f"No validation records found for state: {state_upper} (FIPS: {state_fips})")
                return pl.DataFrame()

            # Fuzzy match on normalized place names
            matches = []
            for row in state_df.iter_rows(named=True):
                normalized_name = row.get("normalized_place_name", "")
                if normalized_name:
                    # Use fuzzy matching (token_set_ratio if rapidfuzz available, else SequenceMatcher)
                    if HAS_RAPIDFUZZ:
                        score = fuzz.token_set_ratio(place_lower, normalized_name) / 100  # Normalize to 0-1
                    else:
                        score = difflib.SequenceMatcher(None, place_lower, normalized_name).ratio()
                    if score >= FUZZY_MATCH_THRESHOLD:
                        matches.append((row, score))

            if not matches:
                logger.debug(f"No fuzzy matches found for place: {place} in state {state}")
                return pl.DataFrame()

            # Convert matches to DataFrame, sorted by score descending
            match_dicts = [m[0] for m in sorted(matches, key=lambda x: x[1], reverse=True)]
            result_df = pl.DataFrame(match_dicts)
            logger.info(f"Found {len(match_dicts)} match(es) for {ocdid}")

            return result_df

        except Exception:
            logger.error(f"Error in find_matches for {ocdid}", exc_info=True)
            return pl.DataFrame()

    def should_create_jurisdiction(self, division: Division) -> bool:
        """Determine if a Jurisdiction should be created for this Division.

        TODO: Define jurisdiction creation rules based on Division classification/type.
        Currently: Create jurisdiction for most cases (placeholder logic).

        Args:
            division: The Division object to evaluate

        Returns:
            True if Jurisdiction should be created, False otherwise
        """
        # Placeholder: Create jurisdiction for all Divisions
        return True

    def jurisdiction_exists(self, jurisdiction_ocdid: str) -> bool:
        """Check if a Jurisdiction with this ocd_id has already been created.

        Args:
            jurisdiction_ocdid: The derived jurisdiction ocd_id

        Returns:
            True if Jurisdiction already exists, False otherwise
        """
        return jurisdiction_ocdid in self.created_jurisdictions

    async def run(self) -> GeneratorResp:
        """Run the pipeline: find matches, generate Division, then Jurisdiction.

        Returns:
            GeneratorResp with Division/Jurisdiction objects, status, and file paths
        """
        response = GeneratorResp(
            data=self.data,
            status=GeneratorStatus(status=Status.SUCCESS),
            division_path=None,
            jurisdiction_path=None
        )

        try:
            # Find matches in validation data
            matches_df = self.find_matches(self.data.ocdid.raw_ocdid)
            match_count = len(matches_df)

            logger.info(f"Matching result for {self.data.ocdid.raw_ocdid}: {match_count} match(es)")

            # Branch on match count
            if match_count == 1:
                # Single match: generate full Division
                logger.info(f"Single match found for {self.data.ocdid.raw_ocdid}")
                matched_row = matches_df.row(0, named=True)

                div_gen = DivGenerator(self.req)
                self.division = div_gen.generate_division(val_rec=matched_row, uuid=self.uuid)
                response.division_path = (
                    str(self.division.dump_division(base_dir=self.division_output_dir))
                    if self.division
                    else None
                )

                # Generate Jurisdiction if appropriate
                if self.division and self.should_create_jurisdiction(self.division):
                    # Derive jurisdiction ocdid
                    jurisdiction_ocdid = self._derive_jurisdiction_ocdid(self.division.ocdid)

                    if not self.jurisdiction_exists(jurisdiction_ocdid):
                        jur_gen = JurGenerator(self.req, division=self.division)
                        self.jurisdiction = jur_gen.generate_jurisdiction(division=self.division, uuid=self.uuid)
                        if self.jurisdiction:
                            response.jurisdiction_path = str(
                                self.jurisdiction.dump_jurisdiction(
                                    base_dir=self.jurisdiction_output_dir
                                )
                            )
                            self.created_jurisdictions.add(jurisdiction_ocdid)
                            logger.info(f"Jurisdiction created: {jurisdiction_ocdid}")
                    else:
                        logger.info(f"Jurisdiction already exists: {jurisdiction_ocdid}")

                response.status = GeneratorStatus(status=Status.SUCCESS)

            elif match_count == 0:
                # No match: generate stub Division and add to quarantine
                logger.info(f"No matches found for {self.data.ocdid.raw_ocdid}, creating stub Division")

                div_gen = DivGenerator(self.req)
                self.division = div_gen.generate_division_stub(uuid=self.uuid)
                response.division_path = (
                    str(self.division.dump_division(base_dir=self.division_output_dir))
                    if self.division
                    else None
                )

                # Add to quarantine
                self.quarantine.ocdid_no_validation_div.append({
                    "ocdid": self.data.ocdid.raw_ocdid,
                    "reason": "no_validation_match",
                    "matched_records": []
                })

                response.status = GeneratorStatus(status=Status.SUCCESS, error="No validation match found")

            else:
                # Multiple matches: add to quarantine, skip Division generation
                logger.warning(f"Multiple matches found for {self.data.ocdid.raw_ocdid}, flagging for review")

                # Convert matched rows to dicts for quarantine storage
                matched_records = [dict(row) for row in matches_df.iter_rows(named=True)]

                self.quarantine.ocdid_no_validation_div.append({
                    "ocdid": self.data.ocdid.raw_ocdid,
                    "reason": "multiple_matches",
                    "matched_records": matched_records,
                    "match_count": match_count
                })

                response.status = GeneratorStatus(status=Status.SKIPPED, error=f"Multiple matches ({match_count}) found, flagged for review")

            return response

        except Exception as e:
            logger.exception(f"Pipeline failed for {self.data.ocdid.raw_ocdid}")
            response.status = GeneratorStatus(status=Status.FAILED, error=str(e))
            return response

    def _derive_jurisdiction_ocdid(self, division_ocdid: str) -> str:
        """Derive jurisdiction ocd_id from division ocd_id.

        Schema: ocd-jurisdiction/<division_without_prefix>/<type>

        Args:
            division_ocdid: Division OCD ID

        Returns:
            Jurisdiction OCD ID
        """
        # Remove 'ocd-division/' prefix and add jurisdiction type
        division_part = division_ocdid.replace("ocd-division/", "")
        # TODO: Implement proper jurisdiction type determination
        jurisdiction_type = "government"  # Placeholder
        return f"ocd-jurisdiction/{division_part}/{jurisdiction_type}"

    def save_quarantine_data(self, output_dir: Path | None = None) -> None:
        """Save quarantine data to CSV files for researcher review.

        Args:
            output_dir: Directory to save quarantine files (default: current directory)
        """
        if output_dir is None:
            output_dir = Path(".")

        try:
            # Filename with timestamp
            timestamp = self.asof_datetime.isoformat()

            # Save validation records with no OCD ID match
            if not self.quarantine.validation_no_ocdid_div.is_empty():
                filepath = output_dir / f"validation_no_ocdid_asof_{timestamp}.csv"
                self.quarantine.validation_no_ocdid_div.write_csv(filepath)
                logger.info(f"Saved validation_no_ocdid records to {filepath}")

            # Save OCDids with no validation match or multiple matches
            if self.quarantine.ocdid_no_validation_div:
                # Denormalize to separate rows for researcher-friendly CSV
                ocdid_records = []
                for entry in self.quarantine.ocdid_no_validation_div:
                    ocdid = entry["ocdid"]
                    reason = entry["reason"]
                    matched_records = entry.get("matched_records", [])

                    if reason == "no_validation_match":
                        ocdid_records.append({
                            "ocdid": ocdid,
                            "reason": reason,
                            "matched_count": 0
                        })
                    else:  # multiple_matches
                        match_count = entry.get("match_count", len(matched_records))
                        if matched_records:
                            for i, record in enumerate(matched_records):
                                ocdid_records.append({
                                    "ocdid": ocdid,
                                    "reason": reason,
                                    "matched_count": match_count,
                                    "match_number": i + 1,
                                    "matched_ocdid": record.get("division_ocdid", ""),
                                    "matched_name": record.get("NAMELSAD", ""),
                                    "matched_geoid": record.get("GEOID_Census", "")
                                })
                        else:
                            ocdid_records.append({
                                "ocdid": ocdid,
                                "reason": reason,
                                "matched_count": match_count
                            })

                ocdid_df = pl.DataFrame(ocdid_records)
                filepath = output_dir / f"ocdid_no_validation_asof_{timestamp}.csv"
                ocdid_df.write_csv(filepath)
                logger.info(f"Saved ocdid_no_validation records to {filepath}")

        except Exception:
            logger.error("Failed to save quarantine data", exc_info=True)


