from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from typing import Optional
from src.utils.ocdid import ocdid_parser
from src.errors import OCDIdParsingError

import logging

logger = logging.getLogger(__name__)


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

    def build_ancestors(self) -> list[OCDidParsed]:
        """Return an OCDidParsed for each ancestor between the country root and this OCD ID.

        Excludes the country root (`ocd-division/country:us`) and the leaf
        (`self`) from the result.  Returns ancestors ordered from shallowest
        to deepest.

        Examples::

            OCDidParsed(raw_ocdid="ocd-division/country:us/state:wa/place:seattle",
                        state="wa", place="seattle").build_ancestors()
            # → [OCDidParsed(raw_ocdid="ocd-division/country:us/state:wa", state="wa")]

        Returns:
            Ordered list of OCDidParsed objects, one per ancestor level.
        """
        parts = self.raw_ocdid.split("/")
        # parts[0]="ocd-division", parts[1]="country:us"  ← skip as root
        # parts[2..N-1] are the ancestors we want; parts[N] is the leaf.
        known_fields = {"country", "state", "county", "place", "subdivision"}
        ancestors: list[OCDidParsed] = []

        for end in range(3, len(parts)):
            ancestor_ocdid = "/".join(parts[:end])
            try:
                parsed = ocdid_parser(ancestor_ocdid)
            except Exception:
                logger.debug("Could not parse ancestor OCD ID: %s", ancestor_ocdid)
                continue

            # Collect any non-standard segment keys (e.g. district, anc) as extras
            # so that extra='allow' stores them as attributes on the model.
            extras = {
                k: v
                for k, v in parsed.items()
                if k not in known_fields and k != "base"
            }

            ancestors.append(
                OCDidParsed(
                    raw_ocdid=ancestor_ocdid,
                    country=parsed.get("country", self.country),
                    state=parsed.get("state"),
                    county=parsed.get("county"),
                    place=parsed.get("place"),
                    subdivision=parsed.get("subdivision"),
                    **extras,
                )
            )

        return ancestors




