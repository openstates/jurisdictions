"""
This module handles Division object generation and serialization.

Responsibilities:
- Generate full Division objects from validation records
- Generate stub Division objects when no validation match exists
- Map validation record fields to Division model fields
- Check Division idempotency/deduplication
- Serialize Division objects to YAML files
"""

from src.init_migration.pipeline_models import GeneratorReq
from src.init_migration.jurisdiction_seed import derive_jurisdiction_ocdid
from src.utils.ocdid import ocdid_parser
from src.models.division import Division
from src.models.source import SourceType
from src.utils.state_lookup import load_state_code_lookup
from src.utils.place_name import coerce_lsad_code, namelsad_to_display_name
from pathlib import Path
from datetime import datetime, timezone
from uuid import UUID
import logging
import yaml

logging.basicConfig()
logger = logging.getLogger(__name__)


def get_division_filename(display_name: str, geoid: str, uuid: UUID) -> str:
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


def _leaf_segment_display_name(parsed_ocdid: dict[str, str]) -> str | None:
    """Return the display name for a council_district or ward division, or None if not applicable.

    For ``place/council_district`` OCD IDs:   "{Place} Council District {N}"
    For ``place/ward`` OCD IDs:   "{Place} Ward {N}"
    For ``anc/council_district`` OCD IDs:     "ANC {ANC_ID} District {N}"

    """

    council_district_value = parsed_ocdid.get("council_district")
    if council_district_value:
        label = "Council District"
        value = council_district_value

    ward_value = parsed_ocdid.get("ward")
    if ward_value:
        label = "Ward"
        value = ward_value

    if not (council_district_value or ward_value):
        return None

    # ref: https://en.wikipedia.org/wiki/Advisory_Neighborhood_Commission
    # ref: https://github.com/opencivicdata/ocd-division-ids/blob/master/identifiers/country-us/state-dc-local_gov.csv
    anc_value = parsed_ocdid.get("anc")
    if anc_value:
        label = "District"
        return f"ANC {anc_value.upper()} {label} {value}"

    place = parsed_ocdid.get("place")
    if place:
        city_name = place.replace("_", " ").title()
        return f"{city_name} {label} {value}"

    return None


class DivGenerator:
    """Factory for generating Division objects with full/stub logic and persistence."""

    def __init__(self, req: GeneratorReq):
        self.req = req
        self.data = req.data
        self.uuid = self.data.uuid
        self.parsed_ocdid = ocdid_parser(self.data.ocdid.raw_ocdid)
        self.state_lookup = load_state_code_lookup()
        self.division: Division | None = None

    def generate_division(self, val_rec: dict, uuid: UUID) -> Division:
        """Generate a full Division object from a matched validation record."""
        try:
            namelsad = val_rec.get("NAMELSAD", "")
            geoid_raw = val_rec.get("GEOID_Census", "") or ""
            geoid = "" if geoid_raw in ("None", "null") else geoid_raw
            statefp = str(val_rec.get("STATEFP", "")).zfill(2)

            if not namelsad:
                raise ValueError(
                    f"Missing required NAMELSAD in validation record: {val_rec}"
                )

            # Normalise lsad — handle "None" strings and Python list reprs from CSV
            lsad = coerce_lsad_code(val_rec.get("LSAD", ""))

            # leaf segment override takes precedence over NAMELSAD-derived name
            leaf_name = _leaf_segment_display_name(self.parsed_ocdid)
            display_name = (
                leaf_name if leaf_name else namelsad_to_display_name(namelsad, lsad)
            )

            raw_ocdid = self.data.ocdid.raw_ocdid
            if self._division_exists(raw_ocdid):
                logger.info(
                    f"Division already exists for {raw_ocdid}, returning existing"
                )
                return self._load_existing_division(raw_ocdid)

            now = datetime.now(timezone.utc)
            self.division = Division(
                ocdid=raw_ocdid,
                country="us",
                display_name=display_name,
                geometries=[],
                also_known_as=[],
                jurisdiction_id=derive_jurisdiction_ocdid(raw_ocdid),
                government_identifiers={
                    "namelsad": namelsad,
                    "statefp": statefp,
                    "sldust": [
                        v.strip()
                        for v in (val_rec.get("SLDUST_list", "") or "").split("|")
                        if v.strip()
                    ],
                    "sldlst": [
                        v.strip()
                        for v in (val_rec.get("SLDLST_list", "") or "").split("|")
                        if v.strip()
                    ],
                    "countyfp": [
                        v.strip()
                        for v in (val_rec.get("COUNTYFP_list", "") or "").split("|")
                        if v.strip()
                    ],
                    "county_names": [
                        v.strip()
                        for v in (val_rec.get("COUNTY_NAMES", "") or "").split("|")
                        if v.strip()
                    ],
                    "lsad": lsad,
                    "geoid": geoid,
                },
                sourcing=[
                    {
                        "field": ["government_identifiers"],
                        "source_name": "civicdata.tech",
                        "source_url": {
                            "civicdata": "https://docs.google.com/spreadsheets/d/139NETp-iofSoHtl_-IdSSph6xf_ePFVtR8l6KWYadSI/"
                        },
                        "source_type": SourceType.HUMAN,
                        "source_description": "Human-researched validation data from civicdata.tech",
                    }
                ],
                accurate_asof=self.req.asof_datetime,
                last_updated=now,
            )

            logger.info(f"Division generated for {raw_ocdid}")
            return self.division

        except Exception:
            logger.error(
                f"Failed to generate Division for {self.data.ocdid.raw_ocdid}",
                exc_info=True,
            )
            raise

    def generate_division_stub(self, uuid: UUID) -> Division:
        """Generate a minimal stub Division when no validation match exists."""
        try:
            raw_ocdid = self.data.ocdid.raw_ocdid
            parsed = ocdid_parser(raw_ocdid)

            leaf_name = _leaf_segment_display_name(parsed)
            if leaf_name:
                display_name = leaf_name
            else:
                place = parsed.get("place", "")
                display_name = place.replace("_", " ").title() if place else "Unknown"

            if self._division_exists(raw_ocdid):
                logger.info(
                    f"Stub Division already exists for {raw_ocdid}, returning existing"
                )
                return self._load_existing_division(raw_ocdid)

            state_code = parsed.get("state", "")
            state_fips = ""
            if state_code:
                fips_list = [
                    item.get("statefps")
                    for item in self.state_lookup
                    if item.get("stateusps", "").upper() == state_code.upper()
                ]
                state_fips = str(fips_list[0]).zfill(2) if fips_list else ""

            place = parsed.get("place", "")

            now = datetime.now(timezone.utc)
            self.division = Division(
                ocdid=raw_ocdid,
                country="us",
                display_name=display_name,
                geometries=[],
                also_known_as=[],
                jurisdiction_id=derive_jurisdiction_ocdid(raw_ocdid),
                government_identifiers={
                    "namelsad": display_name,
                    "statefp": state_fips,
                    "sldust": [],
                    "sldlst": [],
                    "countyfp": [],
                    "county_names": [],
                    "lsad": "",
                    "geoid": (
                        f"{state_fips}{place.zfill(5)}" if state_fips and place else ""
                    ),
                },
                sourcing=[
                    {
                        "field": ["ocdid"],
                        "source_name": "ocdid_ingest",
                        "source_url": {
                            "ocd_repo": "https://raw.githubusercontent.com/opencivicdata/ocd-division-ids/master/identifiers/country-us.csv"
                        },
                        "source_type": SourceType.HUMAN,
                        "source_description": "Open Civic Data Master repo",
                    }
                ],
                accurate_asof=self.req.asof_datetime,
                last_updated=now,
            )

            logger.info(f"Stub Division generated for {raw_ocdid}")
            return self.division

        except Exception:
            logger.error(
                f"Failed to generate stub Division for {self.data.ocdid.raw_ocdid}",
                exc_info=True,
            )
            raise

    def _division_exists(self, ocdid: str) -> bool:
        try:
            parsed = ocdid_parser(ocdid)
            state = parsed.get("state", "").lower() if parsed.get("state") else ""
            div_dir = Path(f"divisions/{state}/local")
            if not div_dir.exists():
                return False
            return False
        except Exception as e:
            logger.debug(f"Error checking if Division exists: {e}")
            return False

    def _load_existing_division(self, ocdid: str) -> Division:
        try:
            raise NotImplementedError("_load_existing_division not yet implemented")
        except Exception:
            logger.error(f"Failed to load existing Division for {ocdid}", exc_info=True)
            raise

    def dump_division(self, output_dir: Path | None = None) -> Path:
        """Serialize and save Division object to YAML file.

        Excludes null optional GovernmentIdentifiers fields.
        Excludes ``metadata`` when None.
        """
        if not self.division:
            raise ValueError("Division object does not exist")

        if not self.division.government_identifiers:
            raise ValueError("government_identifiers required to save Division")

        geoid = self.division.government_identifiers.geoid
        # if not geoid:
        #     raise ValueError(
        #         "geoid required to generate filename — record should have been quarantined"
        #     )

        try:
            filename = get_division_filename(
                self.division.display_name,
                geoid,
                self.division.id,
            )

            parsed = ocdid_parser(self.division.ocdid)
            state = parsed.get("state", "").lower() if parsed.get("state") else ""

            if output_dir is None:
                output_dir = Path(".")

            div_dir = output_dir / "divisions" / state / "local"
            div_dir.mkdir(parents=True, exist_ok=True)

            data = self.division.model_dump(mode="json", exclude_none=False)

            # Remove null optional GovernmentIdentifiers fields
            gov_ids = data.get("government_identifiers") or {}
            for field in ("cousubfp", "placefp", "geoid_12", "geoid_14", "common_name"):
                if field in gov_ids and gov_ids[field] is None:
                    del gov_ids[field]
            data["government_identifiers"] = gov_ids

            # Exclude metadata when None
            if data.get("metadata") is None:
                data.pop("metadata", None)

            filepath = div_dir / filename
            with open(filepath, "w") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)

            logger.info(f"Division saved to {filepath}")
            return filepath

        except Exception:
            logger.error("Failed to save Division to YAML", exc_info=True)
            raise


if __name__ == "__main__":
    pass
