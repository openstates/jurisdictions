from pydantic import BaseModel
from uuid import UUID
from pathlib import Path
from typing import Any


class OCDidIngestResp(BaseModel):
    uuid:UUID
    filepath: Path
    ocdid: str
    raw_record: dict[str, Any]


# This request object allows the caller to determine which parts of the data to
# focus on enable the pipeline to be run to fill different aspects of the .yaml
# file.
class DivGeneratorReq(BaseModel):
    data: OCDidIngestResp
    build_base_object: bool
    ai_url: bool # Wether or not to populate url data w/ai scraper
    geo_req: bool # Whether or not to populate geo request data
    population_req: bool # Wether or not to populate with Census population API call.