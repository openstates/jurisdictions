from pydantic import BaseModel, ConfigDict
from typing import Optional
from src.utils.ocdid import ocdid_parser
from src.errors import OCDIdParsingError

class OCDidParsed(BaseModel):
    """
    Parsed OCDid used for string matching on import records.
    """

    model_config = ConfigDict(extra='allow')

    country: str = "us"
    state: Optional[str] = None
    county: Optional[str] = None
    place: Optional[str] = None
    subdivision: Optional[str] = None
    raw_ocdid: str

    @classmethod
    def parse_ocdid(cls):
        try:
            ocdid_dict = ocdid_parser(cls.raw_ocdid)
            cls(**ocdid_dict)
        except Exception as error:
            raise OCDIdParsingError(error) from error




