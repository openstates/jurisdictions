from pydantic import BaseModel, Field
from uuid import UUID
from typing import Any
from datetime import datetime, UTC
from enum import Enum


DIVISIONS_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/139NETp-iofSoHtl_-IdSSph6xf_ePFVtR8l6KWYadSI/export?format=csv&gid=1481694121"

class OCDidIngestResp(BaseModel):
    uuid:UUID
    ocdid: str
    raw_record: dict[str, Any]

class GeneratorReq(BaseModel):
    """
    Request object for the Division/Jurisdiction generation pipeline.
    Includes flags to determine which parts of the data to load/populate.
    """
    data: OCDidIngestResp
    validation_data_filepath: str = DIVISIONS_SHEET_CSV_URL
    build_base_object: bool = True # Whether or not to build the base Division object (rather than enrich an existing model)
    jurisdiction_ai_url: bool = False # Wether or not to populate url data w/ai scraper
    division_geo_req: bool = False # Whether or not to populate geo request data
    division_population_req: bool = False # Wether or not to populate with Census population API call.
    asof_datetime: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

class Status(Enum, str):
    SUCCESS = "success"
    SKIPPED = "skipped"
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