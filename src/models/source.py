from enum import Enum
from pydantic import BaseModel, Field
from pydantic import AnyHttpUrl, FtpUrl, FileUrl
from typing import Union


class SourceType(str, Enum):
    """These are the allowed defined types for SourceObjects"""
    AI = "ai_generated"
    HUMAN = "human_researched"  # Default
    SCRAPED = "programmatically_generated"  # For programmatic scapers. Do not use this if an AI agent is handling the scraping.

class SourceObj(BaseModel):
    """A source object. Used for determining the valid-thru and veracity of the
    data collected."""
    field: list[str] = Field(description = "An array of fields that this SourceObj refers to, can be more than one. Validated against the available fields in the model.")
    source_name: str = Field(..., description = "The name of the source. I.e. 'ArcGIS', 'Census Bureau', 'City of Seattle Open Data Portal', etc.")
    source_type: SourceType = Field(default=SourceType.HUMAN, description="The method used to collect the data.")
    source_url: dict[str, Union[AnyHttpUrl, FtpUrl, FileUrl]] = Field(description = "The source name and url. If AI generated, the source url identified by the AI agent.")
    source_description: str | None = Field(description="A brief description of how the data was sourced. I.e. ArcGIS library provided by arcgismapper.com")




