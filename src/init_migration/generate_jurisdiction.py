"""
This module handles Jurisdiction object generation and serialization.

Responsibilities:
- Generate Jurisdiction objects from Division objects
- Derive jurisdiction_id from division OCDid
- Resolve jurisdiction name and URL via AI lookup or deterministic fallback
- Serialize Jurisdiction objects to YAML files

Name and URL resolution order:
    1. AI lookup (when req.jurisdiction_ai_url is True — stub, not yet implemented)
    2. Deterministic fallback from Division data
"""

from src.init_migration.pipeline_models import GeneratorReq
from src.models.division import Division
from src.models.jurisdiction import Jurisdiction
from src.models.source import SourceType
from src.utils.ocdid import ocdid_parser
from pathlib import Path
from datetime import datetime, timezone
from uuid import UUID
import logging
import yaml
import re

logging.basicConfig()
logger = logging.getLogger(__name__)

def get_jurisdiction_filename(ocdid: str, uuid: UUID) -> str:
    """Generate Jurisdiction YAML filename from components.

    Derives the name segment from the second-to-last path component of the
    jurisdiction OCD ID (e.g. 'place:seattle' → 'place_seattle').

    Args:
        ocdid: Jurisdiction OCD ID (e.g., 'ocd-jurisdiction/country:us/state:wa/place:seattle/government')
        uuid: UUID from GeneratorReq (same as corresponding Division)

    Returns:
        Filename string (e.g., 'place_seattle_3fa85f64-5717-4562-b3fc-2c963f66afa6.yaml')
    """
    parts = ocdid.rstrip("/").split("/")
    segment = parts[-2] if len(parts) >= 2 else parts[-1]
    safe_segment = segment.replace(":", "_")
    return f"{safe_segment}_{uuid}.yaml"

class JurGenerator:
    """Factory for generating Jurisdiction objects from Division objects with persistence."""

    def __init__(
        self,
        req: GeneratorReq,
        division: Division | None = None,
    ):
        """Initialize JurGenerator with request data and optional Division.

        Args:
            req: GeneratorReq object with OCDid, UUID, and configuration.
            division: Optional Division object.
        """
        self.req = req
        self.data = req.data
        self.uuid = self.data.uuid
        self.division = division
        self.jurisdiction: Jurisdiction | None = None

    def _ai_lookup(self, division: Division) -> dict | None:
        """Look up official jurisdiction name and URL via AI agent.

        Returns a dict with at minimum 'name' and 'url' keys when the lookup
        succeeds, or None when AI lookup is disabled (req.jurisdiction_ai_url
        is False).

        This is a stub.  Full AI integration is tracked separately.  When
        enabled the implementation should:
          - Query the AI with division identifiers (ocdid, display_name,
            government_identifiers.namelsad, state/county/place context).
          - Parse the structured response for the official governing body name
            and its primary website URL.
          - Return {'name': <str>, 'url': <str>} on success.

        Args:
            division: Division object whose jurisdiction is being generated.

        Returns:
            dict with 'name'/'url' keys, or None if AI lookup is disabled.

        Raises:
            NotImplementedError: When jurisdiction_ai_url=True (not yet built).
        """
        if not self.req.jurisdiction_ai_url:
            return None
        raise NotImplementedError(
            "AI jurisdiction lookup is not yet implemented. "
            "Set jurisdiction_ai_url=False to use deterministic fallback values."
        )

    def generate_jurisdiction(self, division: Division, uuid: UUID, classification: str = "government") -> Jurisdiction:
        """Generate a Jurisdiction object from a Division object.

        Name and URL are resolved from AI lookup first, then deterministic
        fallback values derived from Division data.

        Args:
            division: Division object to generate Jurisdiction from.
            uuid: UUID for this Jurisdiction.
            classification: Jurisdiction classification (from JurisdictionSeed).

        Returns:
            Jurisdiction object.

        Raises:
            ValueError: If required Division fields are missing.
        """
        try:
            if not division or not division.ocdid:
                raise ValueError("Division object or ocdid is missing")

            jurisdiction_ocdid = self._derive_jurisdiction_ocdid(division.ocdid, classification)

            if self._jurisdiction_exists(jurisdiction_ocdid):
                logger.info(f"Jurisdiction already exists: {jurisdiction_ocdid}, returning existing")
                return self._load_existing_jurisdiction(jurisdiction_ocdid)

            ai = self._ai_lookup(division)

            if classification == "government":
                fallback_name = f"{division.display_name} Government"
            else:
                fallback_name = f"{division.display_name} {classification.replace('_', ' ').title()}"
            fallback_url = f"https://opencivicdata.org/division/{division.ocdid}"

            # --- Name / URL ---
            name = (ai or {}).get("name") or fallback_name
            url = (ai or {}).get("url") or fallback_url

            # --- Term / Metadata ---
            term = None
            metadata: dict = {"urls": []}

            now = datetime.now(timezone.utc)
            self.jurisdiction = Jurisdiction(
                ocdid=jurisdiction_ocdid,
                name=name,
                url=url,
                classification=classification,
                legislative_sessions={},
                feature_flags=[],
                term=term,
                metadata=metadata,
                sourcing=[{
                    "field": ["ocdid", "name", "classification"],
                    "source_name": "derived_from_division",
                    "source_url": {
                        "division": f"https://opencivicdata.org/division/{division.ocdid}"
                    },
                    "source_type": SourceType.HUMAN,
                    "source_description": "Jurisdiction derived from Division object",
                }],
                accurate_asof=self.req.asof_datetime,
                last_updated=now,
            )

            logger.info(f"Jurisdiction generated: {jurisdiction_ocdid}")
            return self.jurisdiction

        except Exception:
            logger.error(
                f"Failed to generate Jurisdiction from Division {division.ocdid if division else 'unknown'}",
                exc_info=True,
            )
            raise

    def _derive_jurisdiction_ocdid(self, division_ocdid: str, classification: str = "government") -> str:
        """Derive jurisdiction ocd_id from division ocd_id."""
        division_part = division_ocdid.replace("ocd-division/", "")
        division_part = re.sub(r"/council_district:[^/]+", "", division_part)
        return f"ocd-jurisdiction/{division_part}/{classification}"

    def _jurisdiction_exists(self, jurisdiction_ocdid: str) -> bool:
        try:
            parsed = ocdid_parser(jurisdiction_ocdid)
            state = parsed.get("state", "").lower() if parsed.get("state") else ""
            jur_dir = Path(f"jurisdictions/{state}/local")
            if not jur_dir.exists():
                return False
            return False
        except Exception as e:
            logger.debug(f"Error checking if Jurisdiction exists: {e}")
            return False

    def _load_existing_jurisdiction(self, jurisdiction_ocdid: str) -> Jurisdiction:
        try:
            raise NotImplementedError("_load_existing_jurisdiction not yet implemented")
        except Exception:
            logger.error(f"Failed to load existing Jurisdiction for {jurisdiction_ocdid}", exc_info=True)
            raise

    def dump_jurisdiction(self, output_dir: Path | None = None) -> Path:
        """Serialize and save Jurisdiction object to YAML file."""
        if not self.jurisdiction:
            raise ValueError("Jurisdiction object does not exist")

        try:
            filename = get_jurisdiction_filename(
                self.jurisdiction.ocdid,
                self.jurisdiction.id,
            )

            # Use the division OCD ID (from the request) to extract state —
            # jurisdiction OCD IDs end with an unkeyed "/government" segment
            # that ocdid_parser cannot handle.
            div_parsed = ocdid_parser(self.req.data.ocdid.raw_ocdid)
            state = (div_parsed.get("state") or div_parsed.get("district") or "").lower()

            if output_dir is None:
                output_dir = Path(".")

            jur_dir = output_dir / "jurisdictions" / state / "local"
            jur_dir.mkdir(parents=True, exist_ok=True)

            data = self.jurisdiction.model_dump(mode="json", exclude_none=False)

            filepath = jur_dir / filename
            with open(filepath, "w") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)

            logger.info(f"Jurisdiction saved to {filepath}")
            return filepath

        except Exception:
            logger.error("Failed to save Jurisdiction to YAML", exc_info=True)
            raise


if __name__ == "__main__":
    pass
