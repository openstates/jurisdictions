from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, FileUrl, FtpUrl, HttpUrl, field_validator


class SourceType(str, Enum):
    """These are the allowed defined types for SourceObjects"""

    AI = "ai_generated"  # Default
    HUMAN = "human_researched"
    SCRAPED = "programmatically_generated"  # For programmatic scapers. Do not use this if an AI agent is handling the scraping.


class SourceObj(BaseModel):
    """Provenance for one or more fields of a record.

    A SourceObj describes *observation time* — when the cited dataset was
    published and when this pipeline retrieved it. It never describes
    real-world validity time; that belongs to the owning record
    (``Geometry.valid_from`` / ``valid_to``, ``Division.valid_asof`` /
    ``valid_thru``). Everything here is mutable provenance and does not feed
    entity identity.
    """

    field: list[str] = Field(
        description="Dotted field paths on the owning record that this source covers, e.g. ['term', 'term.term_limits'] or ['metadata', 'metadata.population']. Free-form; not validated against the owning model."
    )
    source_name: str = Field(
        ...,
        description="The name of the source. I.e. 'ArcGIS', 'Census Bureau', 'City of Seattle Open Data Portal', etc.",
    )
    source_type: SourceType = Field(
        default=SourceType.AI,
        description="The method used to collect the data. If AI generated, this should be set to 'AI'.",
    )
    source_url: HttpUrl | FtpUrl | FileUrl = Field(
        description="URL of the cited source — http(s), ftp, or file. If AI generated, the source url identified by the AI agent."
    )
    source_description: str | None = Field(
        description="A brief description of how the data was sourced. I.e. ArcGIS library provided by arcgismapper.com"
    )
    dataset: str | None = Field(
        default=None,
        description="The specific dataset or product within the source, e.g. 'TIGER/Line Shapefiles', 'Government Units Survey', 'ocd-division-ids/identifiers/country-us.csv'.",
    )
    release: str | None = Field(
        default=None,
        description="Release, vintage, or version of the dataset in the provider's own terms — a Census vintage ('2020'), a TIGER/Line release ('2024'), a git tag or SHA.",
    )
    publication_date: datetime | None = Field(
        default=None,
        description="When the provider published this release.",
    )
    retrieval_date: datetime | None = Field(
        default=None,
        description="When this pipeline retrieved the data from the source.",
    )

    @field_validator("source_url", mode="before")
    @classmethod
    def _unwrap_legacy_url_map(cls, value: Any) -> Any:
        """Accept a single-entry ``{label: url}`` map as the URL.

        Older records wrote ``source_url`` as a one-entry map. The label
        carried no meaning independent of ``source_name`` /
        ``source_description``, so it is dropped and the URL kept.
        """
        if isinstance(value, dict):
            if len(value) != 1:
                raise ValueError("legacy source_url map must contain exactly one URL")
            return next(iter(value.values()))
        return value
