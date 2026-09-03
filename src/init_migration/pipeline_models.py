from pydantic import BaseModel, ConfigDict, Field
from typing import Any
from datetime import datetime, UTC
from enum import Enum
from uuid import UUID
from src.models.ocdid import OCDIdParsed

# Master Validation Set for initial load
DIVISIONS_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/139NETp-iofSoHtl_-IdSSph6xf_ePFVtR8l6KWYadSI/export?format=csv&gid=1481694121"
STATES_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT0q9msUiw5mGUu6PrZg3beDT38MpjOXrruhXqC8MwI9gPrD0vIQSbaKhuFfG_g8UnAJl5e860QTiyp/pub?gid=2024806624&single=true&output=csv"
COUNTIES_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT0q9msUiw5mGUu6PrZg3beDT38MpjOXrruhXqC8MwI9gPrD0vIQSbaKhuFfG_g8UnAJl5e860QTiyp/pub?gid=1652436767&single=true&output=csv"

# Used to source repo generated SourceObjs
REPO_URL = "https://github.com/openstates/jurisdictions"


class OCDidIngestResp(BaseModel):
    uuid: UUID  # UUID5 identifier
    ocdid: OCDIdParsed
    raw_record: dict[str, Any]


class GeneratorReq(BaseModel):
    """
    Request object for the Division/Jurisdiction generation pipeline.
    Includes flags to determine which parts of the data to load/populate.
    """

    # Unknown keys are rejected rather than ignored: a stale validation-filepath
    # kwarg would otherwise be dropped silently and the pipeline would fall back
    # to fetching the live sheets instead of the caller's file.
    model_config = ConfigDict(extra="forbid")

    data: OCDidIngestResp
    validation_data_division_filepath: str = DIVISIONS_SHEET_CSV_URL
    validation_data_states_filepath: str = STATES_SHEET_CSV_URL
    validation_data_counties_filepath: str = COUNTIES_SHEET_CSV_URL
    build_base_object: bool = True  # Whether or not to build the base Division object (rather than enrich an existing model)
    jurisdiction_ai_url: bool = False  # Wether or not to populate url data w/ai scraper
    division_geo_req: bool = False  # Whether or not to populate geo request data
    division_population_req: bool = (
        False  # Wether or not to populate with Census population API call.
    )
    asof_datetime: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class Status(str, Enum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    PARTIAL = "partial"
    FAILED = "failed"


class GeneratorStatus(BaseModel):
    status: Status
    error: str | None = None


class GeneratorResp(BaseModel):
    data: OCDidIngestResp
    status: GeneratorStatus
    division_path: str | None
    jurisdiction_path: str | None


class JurGeneratorReq(GeneratorReq):
    division_id: str  # OCDID of the division to generate jurisdiction for.
