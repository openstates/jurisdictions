"""
This pipeline works on generating division objects and populating them with data
from validation data sets. If requested, it will also enrich the data with
external API requests.
"""

from src.init_migration.models import DivGeneratorReq
from src.models.ocdid import OCDidParsed
from src.models.division import Division, Geometry
from src.models.jurisdiction import Jurisdiction
from typing import Any
import polars as pl
from polars import DataFrame
from utils.state_lookup import load_state_code_lookup
from pydantic import BaseModel
from datetime import datetime, UTC
import logging

logging.basicConfig()
logger = logging.getLogger(__name__)

DIVISIONS_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/139NETp-iofSoHtl_-IdSSph6xf_ePFVtR8l6KWYadSI/export?format=csv&gid=1481694121"

TODAY = datetime.now(tz=UTC) # automatically generate current run date.

class NoMatch(BaseModel):
    validation_no_ocdid: DataFrame = pl.DataFrame()
    ocdid_no_validation: list[Division] = [] # Could also be OCDids

class ValidationRecord(BaseModel):
    """
    TODO: Convert the fields in the spreadsheet into a model.
    """

class JurGenerator:
    def __init__(
            self,
            req: DivGeneratorReq, validation_data_filepath=DIVISIONS_SHEET_CSV_URL,
            ):
        self.req = req
        self.data = req.data
        self.uuid = self.data.uuid
        self.division_filepath = self.data.filepath
        self.parsed_ocdid = OCDidParsed(raw_ocdid=self.data.ocdid)
        self.raw_record = self.data  # Fix circular reference
        self.validation_load_fp = validation_data_filepath
        self.validation_output_fp = f"validation_data_asof_{TODAY}.csv"
        self.state_lookup = load_state_code_lookup()
        self.quarantine = NoMatch()
        self.validation_no_ocdid_fp = f"validation_no_ocdid_asof_{TODAY}.csv"
        self.ocdid_no_validation_fp = f"ocdid_no_validation_asof_{TODAY}.txt"
        self.division: Division | None  = None
        self.jurisdiction: Jurisdiction | None  = None


    def load_division(self) -> Division:
        """
        Load the Division .yaml file from self.filepath and convert it into a Division object.
        """
        # load division from dir
        try:
            self.division = Division.load_division(self.division_filepath)
            if self.division:
                return self.division
            else:
                raise
        except Exception as error:
            logger.error("Failed to load division object", extras={"error":error}, exc_info=True)
            raise ValueError("Failed to load division. Check filepath") from error

    def load_jurisdiction(self):
        try:
            self.jurisdiction = Jurisdiction.load_jurisdiction(self.division_filepath)
            if self.jurisdiction:
                return self.jurisdiction
            else:
                raise
        except Exception as error:
            logger.error("Failed to load jurisdiction object", extras={"error":error}, exc_info=True)
            raise ValueError("Failed to load jurisdiction. Check filepath") from error

    def load_validation_data(self) -> pl.DataFrame:
        """
        Given the parsed OCDid, load the relevant state data from the validation
        data set.
        """
        validation_data = pl.read_csv(self.validation_load_fp)
        state = self.parsed_ocdid.state
        state_code = [item.get("statefps") for item in self.state_lookup if item.get("stateusps") == state]
        if not state_code:
            raise ValueError("Failed to lookup state code")

        self.validation_df = validation_data.filter(pl.col("STATEFP") == state_code[0])
        if self.validation_df.is_empty:
            raise ValueError("Unable to filter state validation data.")
        return self.validation_df

    def _map_basedata_to_div_obj(self, val_rec: pl.Series) -> Division:
        return Division()

    def _populate_geometry(self) -> Geometry:
        geometry = Geometry()
        return geometry

    def _populate_census_population_request(self) -> str:
        return "some_api_call"

    def _check_if_div_is_jurisdiction(self) ->bool:
        is_jurisdiction = False
        return is_jurisdiction

    def _map_basedata_to_juris_obj(self, val_rec: pl.Series) -> Jurisdiction:
        val_rec
        return Jurisdiction()

    def _populate_juris_urls(self) -> dict[str, Any]:
        # Calls AI with self.jurisdiction object and returns the urls in the
        # following format.
        if self.req.ai_url:
            return {
                "primary_url": "",
                "secondary_url": ["", "", ""]
                }
        else:
            return {}

    def generate_jurisdiction(self, val_rec: pl.Series) -> Jurisdiction | None:
        if not self.division:
            raise ValueError("Division object does not exist")
        # Not all divisions have a corresponding jurisdiction object.
        is_jurisdiction = self._check_if_div_is_jurisdiction()
        if is_jurisdiction:
            self.jurisdiction = self._map_basedata_to_juris_obj(self, val_rec=val_rec)
            self._populate_juris_urls()


    def save_jurisdiction(self):
        if not self.jurisdiction:
            raise ValueError("Division does not exist.")
        filepath = self.jurisdiction.dump_jurisdiction()
        logger.info("Jurisdiction object stored", extras={"filepath": filepath})

    async def run(self):
        # TODO:
        # - Implement method by method
        # - Build tests for each methoad as you go.
        # - Run code async where feasible
        return self.jurisdiction



if __name__  == "__main__":

    import asyncio

    dg = JurGenerator()

    jurisdiction = asyncio.run(dg.run())









