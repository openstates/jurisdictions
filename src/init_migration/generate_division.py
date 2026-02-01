"""
This module handles Division object generation and serialization.

Responsibilities:
- Generate full Division objects from validation records
- Generate stub Division objects when no validation match exists
- Map validation record fields to Division model fields
- Check Division idempotency/deduplication
- Serialize Division objects to YAML files
"""

from src.init_migration.models import GeneratorReq
from src.utils.ocdid import ocdid_parser
from src.models.division import Division
from src.models.source import SourceType
from src.utils.state_lookup import load_state_code_lookup
from src.utils.place_name import namelsad_to_display_name
from pathlib import Path
from uuid import UUID
from datetime import datetime, timezone
import logging
import yaml

logging.basicConfig()
logger = logging.getLogger(__name__)


class DivGenerator:
    """Factory for generating Division objects with full/stub logic and persistence."""

    def __init__(self, req: GeneratorReq):
        """Initialize DivGenerator with request data.

        Args:
            req: GeneratorReq object with OCDid, UUID, and configuration
        """
        self.req = req
        self.data = req.data
        self.uuid = self.data.uuid
        self.parsed_ocdid = ocdid_parser(self.data.ocdid)
        self.state_lookup = load_state_code_lookup()
        self.division: Division | None = None

    def generate_division(self, val_rec: dict, uuid: UUID) -> Division:
        """Generate a full Division object from a matched validation record.

        Maps validation record fields to Division model fields. Checks for idempotency
        (does not regenerate if Division already exists).

        Args:
            val_rec: Validation record (dict) with fields like NAMELSAD, GEOID_Census, STATEFP, etc.
            uuid: UUID for this Division (from GeneratorReq)

        Returns:
            Division object

        Raises:
            ValueError: If required fields are missing from validation record
        """
        try:
            # Extract required fields from validation record
            namelsad = val_rec.get("NAMELSAD", "")
            geoid = val_rec.get("GEOID_Census", "")
            statefp = str(val_rec.get("STATEFP", "")).zfill(2)

            if not namelsad or not geoid:
                raise ValueError(f"Missing required fields in validation record: NAMELSAD={namelsad}, GEOID_Census={geoid}")

            # Derive display name from NAMELSAD (strip LSAD)
            display_name = namelsad_to_display_name(namelsad)

            # Check if Division already exists
            if self._division_exists(self.data.ocdid):
                logger.info(f"Division already exists for {self.data.ocdid}, returning existing")
                return self._load_existing_division(self.data.ocdid)

            # Map validation fields to Division model
            self.division = Division(
                id=uuid,
                ocdid=self.data.ocdid,
                country="us",
                display_name=display_name,
                geometries=[],
                also_known_as=[],
                jurisdiction_id=self._derive_jurisdiction_id(self.data.ocdid),
                government_identifiers={
                    "namelsad": namelsad,
                    "statefp": statefp,
                    "sldust": [str(v) for v in (val_rec.get("SLDUST_list", "").split("|") if val_rec.get("SLDUST_list") else [])],
                    "sldlst": [str(v) for v in (val_rec.get("SLDLST_list", "").split("|") if val_rec.get("SLDLST_list") else [])],
                    "countyfp": [str(v) for v in (val_rec.get("COUNTYFP_list", "").split("|") if val_rec.get("COUNTYFP_list") else [])],
                    "county_names": [str(v) for v in (val_rec.get("COUNTY_NAMES", "").split("|") if val_rec.get("COUNTY_NAMES") else [])],
                    "lsad": val_rec.get("LSAD", ""),
                    "geoid": geoid,
                },
                sourcing=[{
                    "field": ["government_identifiers"],
                    "source_name": "civicdata.tech",
                    "source_url": {"civicdata": "https://docs.google.com/spreadsheets/d/139NETp-iofSoHtl_-IdSSph6xf_ePFVtR8l6KWYadSI/"},
                    "source_type": SourceType.HUMAN,
                    "source_description": "Human-researched validation data from civicdata.tech"
                }],
                last_updated=datetime.now(timezone.utc)
            )

            logger.info(f"Division generated for {self.data.ocdid}")
            return self.division

        except Exception:
            logger.error(f"Failed to generate Division for {self.data.ocdid}", exc_info=True)
            raise

    def generate_division_stub(self, uuid: UUID) -> Division:
        """Generate a minimal stub Division when no validation match exists.

        Creates Division with only required fields populated from the OCDid,
        letting other fields use model defaults.

        Args:
            uuid: UUID for this Division (from GeneratorReq)

        Returns:
            Stub Division object

        Raises:
            ValueError: If OCDid cannot be parsed
        """
        try:
            # Extract state and place from OCDid
            parsed = ocdid_parser(self.data.ocdid)  # Returns dict

            # Derive display name from place (titlecase)
            place = parsed.get("place", "")
            display_name = place.title() if place else "Unknown"

            # Check if Division already exists
            if self._division_exists(self.data.ocdid):
                logger.info(f"Stub Division already exists for {self.data.ocdid}, returning existing")
                return self._load_existing_division(self.data.ocdid)

            # Create minimal stub Division with placeholder government identifiers
            # Extract state FIPS from state code
            state_code = parsed.get("state", "")
            state_fips = ""
            if state_code:
                state_lookup = load_state_code_lookup()
                fips_list = [item.get("statefps") for item in state_lookup if item.get("stateusps", "").upper() == state_code.upper()]
                state_fips = str(fips_list[0]).zfill(2) if fips_list else ""

            self.division = Division(
                id=uuid,
                ocdid=self.data.ocdid,
                country="us",
                display_name=display_name,
                geometries=[],
                also_known_as=[],
                jurisdiction_id=self._derive_jurisdiction_id(self.data.ocdid),
                government_identifiers={
                    "namelsad": display_name,
                    "statefp": state_fips,
                    "sldust": [],
                    "sldlst": [],
                    "countyfp": [],
                    "county_names": [],
                    "lsad": "",
                    "geoid": f"{state_fips}{place.zfill(5)}" if state_fips and place else "0000000",  # Placeholder geoid
                },
                sourcing=[{
                    "field": ["ocdid"],
                    "source_name": "ocdid_ingest",
                    "source_url": {"ocd_repo": "https://raw.githubusercontent.com/opencivicdata/ocd-division-ids/master/identifiers/country-us.csv"},
                    "source_type": SourceType.HUMAN,
                    "source_description": "Open Civic Data Master repo"
                }],
                last_updated=datetime.now(timezone.utc)
            )

            logger.info(f"Stub Division generated for {self.data.ocdid}")
            return self.division

        except Exception:
            logger.error(f"Failed to generate stub Division for {self.data.ocdid}", exc_info=True)
            raise

    def _derive_jurisdiction_id(self, division_ocdid: str) -> str:
        """Derive jurisdiction_id from division OCD ID.

        Args:
            division_ocdid: Division OCD ID

        Returns:
            Jurisdiction OCD ID
        """
        # Remove 'ocd-division/' prefix
        division_part = division_ocdid.replace("ocd-division/", "")
        # TODO: Implement proper jurisdiction type determination
        jurisdiction_type = "government"  # Placeholder
        return f"ocd-jurisdiction/{division_part}/{jurisdiction_type}"

    def _division_exists(self, ocdid: str) -> bool:
        """Check if a Division YAML file already exists for this OCD ID.

        Args:
            ocdid: The OCD division ID

        Returns:
            True if Division file exists, False otherwise
        """
        try:
            # Extract state from ocdid (e.g., 'ca' from 'ocd-division/country:us/state:ca/place:sausalito')
            parsed = ocdid_parser(ocdid)  # Returns dict
            state = parsed.get("state", "").lower() if parsed.get("state") else ""

            # Look for files in divisions/<state>/local/
            div_dir = Path(f"divisions/{state}/local")
            if not div_dir.exists():
                return False

            # Check if any file with this ocdid exists (would need to parse all files)
            # For now, return False (full implementation would parse each YAML)
            return False

        except Exception as e:
            logger.debug(f"Error checking if Division exists: {e}")
            return False

    def _load_existing_division(self, ocdid: str) -> Division:
        """Load an existing Division YAML file.

        Args:
            ocdid: The OCD division ID

        Returns:
            Division object

        Raises:
            ValueError: If file cannot be loaded
        """
        try:
            # TODO: Implement actual file loading
            raise NotImplementedError("_load_existing_division not yet implemented")
        except Exception:
            logger.error(f"Failed to load existing Division for {ocdid}", exc_info=True)
            raise

    def dump_division(self, output_dir: Path | None = None) -> Path:
        """Serialize and save Division object to YAML file.

        Args:
            output_dir: Base output directory (default: current directory)

        Returns:
            Path to saved YAML file

        Raises:
            ValueError: If Division object doesn't exist or required fields are missing
        """
        if not self.division:
            raise ValueError("Division object does not exist")

        if not self.division.government_identifiers:
            raise ValueError("government_identifiers required to save Division")

        geoid = self.division.government_identifiers.geoid
        if not geoid:
            raise ValueError("geoid required to generate filename")

        try:
            # Import filename helper from generate_pipeline
            from src.init_migration.generate_pipeline import get_division_filename

            # Generate filename
            filename = get_division_filename(
                self.division.display_name,
                geoid,
                self.division.id
            )

            # Determine state from ocdid
            parsed = ocdid_parser(self.division.ocdid)  # Returns dict
            state = parsed.get("state", "").lower() if parsed.get("state") else ""

            # Create directory if needed
            if output_dir is None:
                output_dir = Path(".")

            div_dir = output_dir / "divisions" / state / "local"
            div_dir.mkdir(parents=True, exist_ok=True)

            # Save to YAML
            filepath = div_dir / filename
            with open(filepath, 'w') as f:
                yaml.dump(
                    self.division.model_dump(exclude_none=False),
                    f,
                    default_flow_style=False,
                    sort_keys=False
                )

            logger.info(f"Division saved to {filepath}")
            return filepath

        except Exception:
            logger.error("Failed to save Division to YAML", exc_info=True)
            raise



if __name__ == "__main__":
    # Test division generation
    pass









