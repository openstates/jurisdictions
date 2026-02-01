"""
This module handles Jurisdiction object generation and serialization.

Responsibilities:
- Generate Jurisdiction objects from Division objects
- Derive jurisdiction_id from division OCDid
- Map Division fields to Jurisdiction model fields
- Check Jurisdiction idempotency/deduplication
- Serialize Jurisdiction objects to YAML files
"""

from src.init_migration.models import GeneratorReq
from src.models.division import Division
from src.models.jurisdiction import Jurisdiction
from src.models.source import SourceType
from src.utils.ocdid import ocdid_parser
from pathlib import Path
from uuid import UUID
from datetime import datetime, timezone
import logging
import yaml

logging.basicConfig()
logger = logging.getLogger(__name__)




class JurGenerator:
    """Factory for generating Jurisdiction objects from Division objects with persistence."""

    def __init__(self, req: GeneratorReq, division: Division | None = None):
        """Initialize JurGenerator with request data and optional Division.

        Args:
            req: GeneratorReq object with OCDid, UUID, and configuration
            division: Optional Division object (can be passed later in generate_jurisdiction)
        """
        self.req = req
        self.data = req.data
        self.uuid = self.data.uuid
        self.division = division
        self.jurisdiction: Jurisdiction | None = None

    def generate_jurisdiction(self, division: Division, uuid: UUID) -> Jurisdiction:
        """Generate a Jurisdiction object from a Division object.

        Derives jurisdiction_id from division OCDid, maps Division fields to
        Jurisdiction model fields. Checks for idempotency.

        Args:
            division: Division object to generate Jurisdiction from
            uuid: UUID for this Jurisdiction (same as Division UUID)

        Returns:
            Jurisdiction object

        Raises:
            ValueError: If required Division fields are missing
        """
        try:
            # Validate Division
            if not division or not division.ocdid:
                raise ValueError("Division object or ocdid is missing")

            # Derive jurisdiction_id from division ocdid
            jurisdiction_ocdid = self._derive_jurisdiction_ocdid(division.ocdid)

            # Check if Jurisdiction already exists
            if self._jurisdiction_exists(jurisdiction_ocdid):
                logger.info(f"Jurisdiction already exists: {jurisdiction_ocdid}, returning existing")
                return self._load_existing_jurisdiction(jurisdiction_ocdid)

            # Determine jurisdiction type and name
            jurisdiction_type = self._determine_jurisdiction_type(division)
            jurisdiction_name = self._generate_jurisdiction_name(division, jurisdiction_type)

            # Create Jurisdiction object
            self.jurisdiction = Jurisdiction(
                id=uuid,
                ocdid=jurisdiction_ocdid,
                name=jurisdiction_name,
                url="missing-url-" + (division.display_name.lower().replace(" ", "-")) if division.display_name else "missing-url",
                classification=jurisdiction_type,
                legislative_sessions={},
                feature_flags=[],
                sourcing=[{
                    "field": ["ocdid", "name", "classification"],
                    "source_name": "derived_from_division",
                    "source_url": {"division": division.ocdid},
                    "source_type": SourceType.HUMAN,
                    "source_description": "Jurisdiction derived from Division object"
                }],
                last_updated=datetime.now(timezone.utc)
            )

            logger.info(f"Jurisdiction generated: {jurisdiction_ocdid}")
            return self.jurisdiction

        except Exception:
            logger.error(f"Failed to generate Jurisdiction from Division {division.ocdid if division else 'unknown'}", exc_info=True)
            raise

    def _derive_jurisdiction_ocdid(self, division_ocdid: str) -> str:
        """Derive jurisdiction ocd_id from division ocd_id.

        Schema: ocd-jurisdiction/<division_without_prefix>/<type>

        Args:
            division_ocdid: Division OCD ID

        Returns:
            Jurisdiction OCD ID
        """
        # Remove 'ocd-division/' prefix
        division_part = division_ocdid.replace("ocd-division/", "")

        # Determine jurisdiction type (placeholder)
        jurisdiction_type = "government"  # TODO: Implement proper type determination

        return f"ocd-jurisdiction/{division_part}/{jurisdiction_type}"

    def _determine_jurisdiction_type(self, division: Division) -> str:
        """Determine jurisdiction type/classification based on Division.

        TODO: Define jurisdiction type rules based on Division classification/type.
        Currently: Placeholder returning 'government'.

        Args:
            division: Division object

        Returns:
            Jurisdiction classification (e.g., 'government', 'legislature', 'school_system')
        """
        # Placeholder logic - rules to be defined separately
        return "government"

    def _generate_jurisdiction_name(self, division: Division, jurisdiction_type: str) -> str:
        """Generate jurisdiction name from Division.

        Args:
            division: Division object
            jurisdiction_type: Jurisdiction type/classification

        Returns:
            Jurisdiction name
        """
        base_name = division.display_name or "Unknown"

        # TODO: Implement proper name generation based on jurisdiction type
        if jurisdiction_type == "legislature":
            return f"{base_name} City Council"
        elif jurisdiction_type == "school_system":
            return f"{base_name} School District"
        else:
            return f"{base_name} {jurisdiction_type.title()}"

    def _jurisdiction_exists(self, jurisdiction_ocdid: str) -> bool:
        """Check if a Jurisdiction YAML file already exists for this OCD ID.

        Args:
            jurisdiction_ocdid: The OCD jurisdiction ID

        Returns:
            True if Jurisdiction file exists, False otherwise
        """
        try:
            # Extract state from jurisdiction_ocdid
            parsed = ocdid_parser(jurisdiction_ocdid)  # Returns dict
            state = parsed.get("state", "").lower() if parsed.get("state") else ""

            # Look for files in jurisdictions/<state>/local/
            jur_dir = Path(f"jurisdictions/{state}/local")
            if not jur_dir.exists():
                return False

            # Check if any file with this ocdid exists (would need to parse all files)
            # For now, return False (full implementation would parse each YAML)
            return False

        except Exception as e:
            logger.debug(f"Error checking if Jurisdiction exists: {e}")
            return False

    def _load_existing_jurisdiction(self, jurisdiction_ocdid: str) -> Jurisdiction:
        """Load an existing Jurisdiction YAML file.

        Args:
            jurisdiction_ocdid: The OCD jurisdiction ID

        Returns:
            Jurisdiction object

        Raises:
            ValueError: If file cannot be loaded
        """
        try:
            # TODO: Implement actual file loading
            raise NotImplementedError("_load_existing_jurisdiction not yet implemented")
        except Exception:
            logger.error(f"Failed to load existing Jurisdiction for {jurisdiction_ocdid}", exc_info=True)
            raise

    def dump_jurisdiction(self, output_dir: Path | None = None) -> Path:
        """Serialize and save Jurisdiction object to YAML file.

        Args:
            output_dir: Base output directory (default: current directory)

        Returns:
            Path to saved YAML file

        Raises:
            ValueError: If Jurisdiction object doesn't exist or required fields are missing
        """
        if not self.jurisdiction:
            raise ValueError("Jurisdiction object does not exist")

        try:
            # Import filename helper from generate_pipeline
            from src.init_migration.generate_pipeline import get_jurisdiction_filename

            # Generate filename
            filename = get_jurisdiction_filename(
                self.jurisdiction.name,
                self.jurisdiction.id
            )

            # Determine state from jurisdiction ocdid
            parsed = ocdid_parser(self.jurisdiction.ocdid)  # Returns dict
            state = parsed.get("state", "").lower() if parsed.get("state") else ""

            # Create directory if needed
            if output_dir is None:
                output_dir = Path(".")

            jur_dir = output_dir / "jurisdictions" / state / "local"
            jur_dir.mkdir(parents=True, exist_ok=True)

            # Save to YAML
            filepath = jur_dir / filename
            with open(filepath, 'w') as f:
                yaml.dump(
                    self.jurisdiction.model_dump(exclude_none=False),
                    f,
                    default_flow_style=False,
                    sort_keys=False
                )

            logger.info(f"Jurisdiction saved to {filepath}")
            return filepath

        except Exception:
            logger.error("Failed to save Jurisdiction to YAML", exc_info=True)
            raise



if __name__ == "__main__":
    # Test jurisdiction generation
    pass









