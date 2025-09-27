from enum import Enum
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from .source import SourceObj

class ClassificationEnum(str, Enum):
    """These are the allowed defined types for jurisdictions"""
    GOVERNMENT = "government"  # i.e. city council
    LEGISLATURE = "legislature"
    SCHOOL_SYSTEM = "school_system"
    EXECUTIVE = "executive"  # i.e. mayor
    TRANSIT_AUTHORITY = "transit_authority"

class SessionDetail(BaseModel):
    """Appears in the 'legislative_sessions' as a value for each session key."""
    name: str = Field(..., description="Name of session, typically a year span like 2011-2012. **(required)**")
    identifiers: str = Field(..., description="Identifier of session. **(required)**")
    classification: str = Field(..., description="Type of session: primary or special")
    start_date: datetime = Field(..., description="Start date of session.")
    end_date: datetime = Field(..., description="End date of session.")

class TermDetail(BaseModel):
    duration: int = Field(..., description = "This is typically defined in years.")
    term_description: str = Field(..., description = "The legal language defining how the terms is proscribed in the source document. i.e Shall commence the second tuesday following the last general election and any other useful information.")
    term_limits: Optional[str] = Field(default=None, description = "Typically defined as the number of terms an office holder can hold. Can be a string description of the term limits if any.")
    source_url: str = Field(..., description = "The source url that defines the terms for the jurisdiction. Must be a .gov source. Can often be found in the incorporation charter or state constitution." )
    last_known_start_date: Optional[datetime] = Field(default=None, description="The last known start of the most recent term. This date allows future term start and end dates to be computed programmatically." )

class Jurisdiction(BaseModel):
    """
    Class for defining a Jurisdiction object.
    Reference: https://github.com/opencivicdata/docs.opencivicdata.org/blob/master/data/datatypes.rst#id3
    """
    id: str = Field(..., description="Jurisdictions IDs take the form ocd-jurisdiction/<jurisdiction_id>/<jurisdiction_type> where jurisdiction_id is the ID for the related division without the ocd-division/ prefix and jurisdiction_type is council, legislature, etc.")
    name: str = Field(..., description="Name of jurisdiction (e.g. North Carolina General Assembly). Should be sourced from official gov source data (i.e. Census) **(required)**")
    url: str = Field(..., description="URL pointing to jurisdiction's website. **(required)**")
    classification: ClassificationEnum = Field(..., description="A jurisdiction category. **(required)** See ClassificationEnum.")
    legislative_sessions: Dict[str, SessionDetail]  = Field(default_factory=dict, description="Dictionary describing sessions, each key is a session slug that must also appear in one ``sessions`` list in ``terms``.  Values consist of several fields giving more detail about the session. **(required)**")
    feature_flags: List[str] = Field(default_factory=list, description= "A way to mark certain features as available on a per-jurisdiction basis. Each element in feature_flags is of type (string) **(required, minItems: 0)** ")
    term: Optional[TermDetail] = Field(default=None, description="The details of the terms for elected officials representing this jurisdiction. ")
    accurate_asof: Optional[datetime] = Field(default=None, description="The datetime ('2025-05-01:00:00:00' ISO 8601 standard format when the data for the record is known to be accurate by the researcher. This may or may not be the same data as the 'last_updated' date below. **REQUIRED**")
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="The datetime that the data in the record was last updated by the researcher (or it's agent).")
    sourcing: List[SourceObj] = Field(default_factory=list, description="Describe how the data was sourced. Used to identify AI generated data.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Any other useful information that a research feels should be included.")

    # @field_validator("id")
    def validate_jurisdiction_id(self):
        """Jurisdictions IDs take the form ocd-jurisdiction/<jurisdiction_id>/<jurisdiction_type> where jurisdiction_id is the ID for the related division without the ocd-division/ prefix and jurisdiction_type is council, legislature, etc."""
        # TODO:
        #  - Check prefix = ocd-jurisdiction
        #  - Check "jurisdiction type" is an allowed type
        #  - Check that a matching Division object exists. If not... we need one!
        pass

    @classmethod
    def division_id_to_jurisdiction_id(cls, classification_type: str):
        """Given an ocd-id, convert it to a jurisdiction id"""
        # TODO:
        # - write this code
        pass

    def jurisdiction_id_to_division_id(self):
        # TODO convert the division id back to a jurisdiction id.
        pass

    def flatten(self) -> dict:
        """A method for converting a nested Jurisdiction object, to a flat record(s) in LongTidy format for export to csv."""
        raise NotImplementedError

    def to_csv(self) -> str:
        """ A method to export the flattend record(s) to .csv"""
        raise NotImplementedError


if __name__ == "__main__":

    sample = Jurisdiction(
        id="ocd-jurisdiction/country:us/state:wa/place:Seattle"
        name="Seattle City Council",
        url = "some url",
        classifaction = ClassificationEnum.GOVERNMENT,
    )
