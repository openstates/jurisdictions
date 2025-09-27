

from pydantic import BaseModel, Field
from typing import Any, List, Dict, Optional
from datetime import datetime, timezone
from .source import SourceObj


class Centroid(BaseModel):
    geo_type: str = Field(default="Point")
    coordinates: List[float] = Field(..., description="A two-item array defining the centroid (center) of the geometry. Example: [-176.59989528409687, 51.88215100813731]")

class Extent(BaseModel):
    extent: List[float] = Field(..., description = "Object describing the extents. [left-most, lower-most, right-most, upper-most]")

class Boundary(BaseModel):
    centroid: Optional[Centroid] = None
    extent: Optional[Extent] = None


class GovernmentIdentifiers(BaseModel):
    """
    Census designated identifiers for the locale.
    TODO: Provide a reference(s) for census definitions of the codes below here
    and in the docs.
    """
    namelsad: str = Field(description="The Census designated legal name for the geo political entity associated with a given locale.")
    statefp: str
    sldust: list[str]
    sldlst: list[str]
    countyfp: list[str]
    county_names: list[str]
    cousubfp: Optional[str] = None
    placefp: Optional[str] = None
    lsad: str
    common_name: Optional[list[str]] = Field(default=None, description="The commonly used named for the place if different than the official NAMELSAD. Used for matching on alternative names for a locale.")


class Geometry(BaseModel):
    start: datetime = Field(..., description = "Best approximation of date boundary became effective.")
    end: datetime = Field(..., description = "Best approximation of date boundary was replaced or made obsolete (null for current boundaries).")
    boundary: Boundary = Field(..., description = "The centroid and extent of the geometry.")
    children: List[str] = Field(default_factory=list, description = "A list of child division ids.")
    arcGIS_address: str = Field(..., description = "A url or curl-like request string to the arcGIS server. Ideally this is granular to the layer defined by the division id.")
    government_identifiers: Optional[dict[str, Any]] = Field(default_factory=dict, description="A dictionary of the  code(s) (i.e. Census state_code, fips_code, geoid, etc.) official name in snake_case and the value. Can include more than one key.")

class Division(BaseModel):
    id: str = Field(..., description = "Description the canonical OpenCivicData id for the political geo division. Should be sourced from the Open Civic Data repo. Example: ADD TKTK See: docs.opencivicdata.org")
    country: str = Field(..., description = "Two-letter ISO-3166 alpha-2 country code. (e.g. 'us', 'ca')")
    display_name: str = Field(..., description = "Human-readable name for division. Should be sourced from the Open Civic Data repo.")
    geometries: Optional[List[Geometry]] = Field(default_factory=list, description = "A list of associated geometries, as defined by the Geometry model. Empty array if not set.")
    also_known_as: List[str] = Field(default_factory=list, description = "A list of alternate formatted OCDids that refer to the same geo political divisions.")
    valid_thru: Optional[datetime] = Field(default=None, description="If a division is set to be retired, use this date to indicate when the division is no longer valid.")
    valid_asof: Optional[datetime] = Field(default=None, description="If a new division is created use this date to indicate when the division will become active.")
    accurate_asof: Optional[datetime] = Field(default=None, description="The datetime ('2025-05-01:00:00:00' ISO 8601 standard format when the data for the record is known to be accurate by the researcher. This may or may not be the same data as the 'last_updated' date below.")
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="The datetime that the data in the record was last updated by the researcher (or it's agent).")
    sourcing: List[SourceObj] = Field(default_factory=list, description="Describe how the data was sourced. Used to identify AI generated data.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Any other useful information that a researcher feels should be included.")

    def flatten(self) -> dict:
        """A method for converting a nested Division object, to a flat record(s) in LongTidy format for export to csv."""
        raise NotImplementedError

    def to_csv(self, include_children: bool = True) -> str:
        """ A method to export the flattend record(s) to .csv"""
        raise NotImplementedError

