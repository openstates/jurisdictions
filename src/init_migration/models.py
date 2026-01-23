from pydantic import BaseModel, Field
from uuid import UUID
from pathlib import Path
from typing import Any
from datetime import datetime, UTC


class OCDidIngestResp(BaseModel):
    uuid:UUID
    filepath: Path
    ocdid: str
    raw_record: dict[str, Any]


# This request object allows the caller to determine which parts of the data to
# focus on enable the pipeline to be run to fill different aspects of the .yaml
# file.
class PipelineReq(BaseModel):
    data: OCDidIngestResp
    validation_data_filepath: str
    build_base_object: bool # Whether or not to build the base Division object (rather than enrich an existing model)
    ai_url: bool # Wether or not to populate url data w/ai scraper
    geo_req: bool # Whether or not to populate geo request data
    population_req: bool # Wether or not to populate with Census population API call.
    asof_datetime: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

class GeneratorResp(BaseModel):
    data: OCDidIngestResp
    division: Any | None # Division object
    jurisdiction: Any | None  # Jurisdiction object, if applicable.

class JurGeneratorReq(PipelineReq):
    division_id: str  # OCDID of the division to generate jurisdiction for.