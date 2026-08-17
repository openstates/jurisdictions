from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl

from src.models.source import SourceObj, SourceType

class OrganizationClassificationEnum(str, Enum):
    """Popolo-compliant organization classification types.
    
    Reference: https://www.popoloproject.com/specs/organization.html
    """
    
    # Government entities
    GOVERNMENT = "government"
    LEGISLATURE = "legislature"
    EXECUTIVE = "executive"
    JUDICIARY = "judiciary"
    
    # Bodies and subdivisions
    LEGISLATIVE_BODY = "legislative_body"
    DEPARTMENT = "department"
    AGENCY = "agency"
    AUTHORITY = "authority"
    
    # Committees and boards
    COMMITTEE = "committee"
    BOARD = "board"
    COMMISSION = "commission"
    ADVISORY_BOARD = "advisory_board"

class Organization(BaseModel):
    """
    Example organizations: City Council, Mayor's Office, Parks Department,
    Planning Commission, County Board of Supervisors, etc.
    """
    
    name: str
    common_names: Optional[List[str]] = Field(
        default=None,
        description="Commonly used names for the organization, if different from the official name. Provide as a list of strings to support search functionality and matching."
    )
    url: Optional[HttpUrl] = Field(None, description="URL pointing to organization's official website. Internal links within government websites to a specific page permitted.")
    sourcing: List[SourceObj] = Field(
        default_factory=lambda: [
            SourceObj(
                field=["organization"],
                source_name="Popolo Schema",
                source_type=SourceType.HUMAN,
                source_url={"popolo": "https://www.popoloproject.com"},
                source_description="Organization structure and metadata sourced from Popolo standard for representing government entities"
            )
        ],
    )