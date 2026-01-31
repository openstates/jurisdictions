#!/usr/bin/env python
# Copyright 2023 Unified for Progress. All Rights Reserved.

"""
====================
Generate OCDids
====================
"""

from typing import Any
import i18naddress
import logging
from src.errors import OCDIdParsingError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_OCDID = "ocd-division/country:us"

def ocdid_parser(ocdid_str):
    """
    Parses OCDid's and returns each part as a key, value pair in a dictionary.
    Used to retrieve just the division (i.e. the "state" or "place", etc.)
    from a given OCDid.

    params:
        ocdid_str (str): The OCDid string to be parsed.

    returns:
        parsed_ocdid (dict): The parsed OCDid with each division returned as a key, value pair.
    """
    try:
        parsed = ocdid_str.split("/")
        parsed_ocdid = {"base": parsed[0]}
        for part in parsed[1:]:
            parsed_ocdid[part.split(":")[0]] = part.split(":")[1]
    except Exception as error:
        message = f"Error parsing OCDid: {ocdid_str} Error: {error}"
        raise OCDIdParsingError(message) from error
    return parsed_ocdid

def generate_ocdids(base_ocdid=BASE_OCDID) -> list[dict[str, Any]]:
    """
    Generates state/province OCDids based on base country ocdid.
    Returns a dictionary in the form of:

        {"ocd-division/country:us": False,
            "ocd-division/country:us/state:nj": True,
            }

    params:
        base_ocdid (str): The ocdid from which to generate ids.

    returns:
        ocd_ids (dict):  A dictionary of ocd_ids and recursive flag.

    TODO: Handle internationalization.
    """
    logger.info("Generate OCDids. Base_ocdid: %s", base_ocdid)
    country = ocdid_parser(base_ocdid)["country"]

    ocd_ids = []
    if country == "us":
        ocd_ids.append(
            {"ocd_id": base_ocdid, "recursive": False},
        )  # Set recursive to false
        logger.debug("Fetch US validation rules.")
        us_address_validation_rules = i18naddress.get_validation_rules(
            {"country_code": "US"},
        )
        districts = {"DC"}
        # Do not include 'AA', 'AE', 'AP',  used for armed services mail, not applicable'
        # Do not include 'MH', 'FM', 'PW', returns 404
        # See: https://en.wikipedia.org/wiki/List_of_U.S._state_and_territory_abbreviations
        exclude = ["AA", "AE", "AP", "MH", "FM", "PW"]
        territories = {"AS", "GU", "MP", "FM", "PR", "PW", "VI", "UM"}
        states = [state_abbr for state_abbr, state_name in us_address_validation_rules.country_area_choices]
        states = [state for state in states if state not in exclude]
        logger.debug("Generate admin1 (state) level ids.")
        for state in states:
            if state in districts:
                state_type = "district"
            elif state in territories:
                state_type = "territory"
            else:
                state_type = "state"
            state_ocd = f"{base_ocdid}/{state_type}:{state.lower()}"
            ocd_ids.append(
                {"ocd_id": state_ocd, "recursive": True},
            )  # Set recursive to True
    # Run other countries recursively.
    # Note this will likely throw an API error for countries with a
    # large number of administrative areas
    else:
        logger.debug("Generate non-US OCDids. Base_ocdid: %s", base_ocdid)
        ocd_ids.append(
            {"ocd_id": base_ocdid, "recursive": True},
        )  # Run base_ocd recursively
    logger.info("Number of OCDids: %s", len(ocd_ids))
    logger.info("Completed generating OCDids. Base_ocdid: %s", base_ocdid)
    return ocd_ids
