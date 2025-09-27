from pydantic import Field, BaseModel
from typing import Optional

class OCDidParsed(BaseModel):
    """
    Parsed OCDid used for string matching on import records.
    """
    country:str = "us"
    state :Optional[str] = None
    county:Optional[str] = None
    place:Optional[str] = None
    subdivision: Optional[str] = None

