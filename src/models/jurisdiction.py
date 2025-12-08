from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from .source import SourceObj
import yaml
from pathlib import Path
# We can choose whichever UUID version is short but won't cause clashes.
from uuid import UUID, uuid4

import logging
logger = logging.getLogger(__name__)


PROJECT_PATH = "jurisdictions/"

class ClassificationEnum(str, Enum):
    """These are the allowed defined types for jurisdictions"""
    GOVERNMENT = "government" #i.e. city council
    LEGISLATURE = "legislature" # i.e. state legislature,
    SCHOOL_SYSTEM = "school_system" # i.e. county school district board, individualschool board, community college board
    EXECUTIVE = "executive"  # i.e. mayor
    TRANSIT_AUTHORITY = "transit_authority" #i.e. PORT Authority of New York and New Jersey
    JUDICIAL = "judicial" # NON-OCDid COMPLIANT; ADDED
    PROSECUTORIAL = "prosecutorial" # NON-OCDid COMPLIANT; ADDED, Examples: District Attorney Offices
    GOVERNING_BOARD = "governing_board" # NON-OCDid COMPLIANT; ADDED; Examples:  Cousubs that have elected governing bodies that advise but meet under the fiscal oversight of the county government. Utility districts with elected boards, etc.


class URLEnum(str, Enum):
    """These are the allowed defined types for jurisdiction urls"""
    PEOPLE = "people"
    MEETINGS = "meetings"

class URLObject(BaseModel):
    """A URL object for defining known url types for a jurisdiction."""
    url_type: URLEnum | str = Field(..., description="The type of url being defined.")
    url: str = Field(..., description="The url string associated with the url type.")

class URLS(BaseModel):
    urls: list[URLObject] = Field(..., description="The url string or enum value.")


class JurisdictionMetadata(BaseModel):
    """A metadata object for defining known metadata for a jurisdiction."""
    model_config = ConfigDict(extra='allow')
    urls: list[URLObject] = Field(
        ...,
        description=
            "List of URLs related to the jurisdiction; additional arbitrary key-value pairs allowed on this model.",
    )

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
    number_of_positions: int = Field(..., description = "The number of distinct positions that are elected to represent the jurisdiction inclusive of at-large positions. For a city council with 5 members and , this would be 7.")ig
    term_limits: Optional[str] = Field(default=None, description = "Typically defined as the number of terms an office holder can hold. Can be a string description of the term limits if any.")
    source_url: str = Field(..., description = "The source url that defines the terms for the jurisdiction. Must be a .gov source. Can often be found in the incorporation charter or state constitution." )
    last_known_term_end_date: Optional[datetime] = Field(default=None, description="The last known start of the most recent term. This date allows future term start and end dates to be computed programmatically." )

class Jurisdiction(BaseModel):
    """
    Class for defining a Jurisdiction object.
    Reference: https://github.com/opencivicdata/docs.opencivicdata.org/blob/master/data/datatypes.rst#id3
    """
    id: UUID = Field(default_factory=uuid4(), description = "The uuid associated with the object when it was generated for this project. This is a ddeterministic uuid based on the ocdid and version")
    ocdid: str = Field(..., description="Jurisdictions IDs take the form ocd-jurisdiction/<jurisdiction_id>/<jurisdiction_type> where jurisdiction_id is the ID for the related division without the ocd-division/ prefix and jurisdiction_type is council, legislature, etc.")
    name: str = Field(..., description="Name of jurisdiction (e.g. North Carolina General Assembly). Should be sourced from official gov source data (i.e. Census) **(required)**")
    url: str = Field(..., description="URL pointing to jurisdiction's website. **(required)**")
    classification: ClassificationEnum = Field(..., description="A jurisdiction category. **(required)** See ClassificationEnum.")
    legislative_sessions: Dict[str, SessionDetail]  = Field(default_factory=dict, description="Dictionary describing sessions, each key is a session slug that must also appear in one ``sessions`` list in ``terms``.  Values consist of several fields giving more detail about the session. **(required)**")
    feature_flags: List[str] = Field(default_factory=list, description= "A way to mark certain features as available on a per-jurisdiction basis. Each element in feature_flags is of type (string) **(required, minItems: 0)** ")
    term: Optional[TermDetail] = Field(default=None, description="The details of the terms for elected officials representing this jurisdiction. ")
    accurate_asof: Optional[datetime] = Field(default=None, description="The datetime ('2025-05-01:00:00:00' ISO 8601 standard format when the data for the record is known to be accurate by the researcher. This may or may not be the same data as the 'last_updated' date below. **REQUIRED**")
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="The datetime that the data in the record was last updated by the researcher (or it's agent).")
    sourcing: List[SourceObj] = Field(default_factory=list, description="Describe how the data was sourced. Used to identify AI generated data.")
    metadata: JurisdictionMetadata = Field(default_factory=dict, description="Any other useful information that a research feels should be included.")

    # @field_validator("id")
    def validate_jurisdiction_id(self):
        """Jurisdictions IDs take the form ocd-jurisdiction/<jurisdiction_id>/<jurisdiction_type> where jurisdiction_id is the ID for the related division without the ocd-division/ prefix and jurisdiction_type is council, legislature, etc."""
        # TODO:
        #  - Check prefix = ocd-jurisdiction
        #  - Check "jurisdiction type" is an allowed type
        #  - Check that a matching Division object exists. If not... we need one!
        pass

    # Untested
    @classmethod
    def load_jurisdiction(cls, filepath):
        try:
            data = yaml.safe_load(filepath)
            cls = cls(**data)
        except Exception as error:
            logger.error("Failed to load jurisdiction object", extras={"error":error}, exc_info=True)
            raise ValueError("Failed to load jurisdiction. Check filepath") from error
    # Untested
    def dump_jurisdiction(self):
        filepath = Path(f"{PROJECT_PATH}/{self.name}_{self.id}_{self._id}")
        yaml.safe_dump(filepath)
        return filepath

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

    sample = Jurisdiction (
        name="Seattle City Council",
        url="https://www.seattle.gov/council",
        classification=ClassificationEnum.GOVERNMENT,
        legislative_sessions = SessionDetail(
            name="119th Congress",
            identifiers = "",
            classification = "",
            start_date = datetime(day=10, month=10, year=2025),
        ),
        feature_flags = [{"legislative_sessions": -1, "term_detail": 1}], # Where "1" means expect this feature and "-1" means not applicable.
    )
