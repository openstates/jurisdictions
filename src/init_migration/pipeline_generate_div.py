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
from src.utils.state_lookup import load_state_code_lookup
from pydantic import BaseModel, ConfigDict
from datetime import datetime, UTC
import logging

logging.basicConfig()
logger = logging.getLogger(__name__)

DIVISIONS_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/139NETp-iofSoHtl_-IdSSph6xf_ePFVtR8l6KWYadSI/export?format=csv&gid=1481694121"

TODAY = datetime.now(tz=UTC) # automatically generate current run date.

class PolarsBaseModel(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
class NoMatch(PolarsBaseModel):
    validation_no_ocdid: DataFrame = pl.DataFrame()
    ocdid_no_validation: list[Division] = [] # Could also be OCDids
    


class ValidationRecord(BaseModel):
    """
    TODO: Convert the fields in the spreadsheet into a model.
    """

class DivGenerator:
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


    def load_state_lookup(self):
        pass  # This method is already called in __init__


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

    def match_division(self, state_val_df) -> pl.Series | None:
        """
        Given a parsed OCDid, match to the division object.
        """

        found = pl.Series()
        # code here to match on the parsed ocdid.
        match_candidates = pl.DataFrame()
        if match_candidates.is_empty():
            self.quarantine.ocdid_no_validation.append(self.division)
        if len(match_candidates) > 0:
            for match in match_candidates.iter_rows():
                pass
            # Need to determine how to manage these.
            # Potentially mark the pl and create a div object for each one...
            # Or just update the dataframe with Failed: More than one match...
        elif len(match_candidates) == 0:
            found = match_candidates[0]
            # Update validation set
            # Add ocd_id column if it doesn't exist
            if "ocd_id" not in self.validation_df.columns:
                self.validation_df = self.validation_df.with_columns(
                    pl.lit(None).alias("ocd_id"),
                    )

            # Update the validation DataFrame to mark this record with the
            # matching ocdid.
            self.validation_df = self.validation_df.with_columns(
                pl.when(pl.col("some_matching_column") == "matching_value")
                .then(pl.lit(self.parsed_ocdid.raw_ocdid))
                .otherwise(pl.col("ocd_id"))
                .alias("ocd_id")
            )
            return found.to_series()

    def _map_basedata_to_div_obj(self, val_rec: pl.Series) -> Division:
        return Division()

    def _populate_geometry(self) -> Geometry:
        geometry = Geometry()
        return geometry

    def _populate_census_population_request(self) -> str:
        return "some_api_call"

    def generate_division(self,val_rec: pl.Series) -> Division:
        if not self.division or not isinstance(self.division, Division):
            raise ValueError("No division object exists.")
        if self.req.build_base_object:
            self.division = self._map_basedata_to_div_obj(val_rec=val_rec)
        if self.req.geo_req:
            geometry: Geometry = self._populate_geometry()
            self.division.geometries = [geometry]
        return self.division

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

    def save_division(self):
        """
        Store the populated division object to the divisions filepath.
        """
        if not self.division:
            raise ValueError("Division does not exist.")
        filepath = self.division.dump_division()
        logger.info("Division object stored", extras={"filepath": filepath})

    def save_jurisdiction(self):
        if not self.jurisdiction:
            raise ValueError("Division does not exist.")
        filepath = self.jurisdiction.dump_jurisdiction()
        logger.info("Jurisdiction object stored", extras={"filepath": filepath})

    def save_quarantine_data(self):
        """
        Save the data for which there were no matches to
        .csv
        """
        ocdid_no_validation = self.quarantine.ocdid_no_validation
        validation_no_ocdid = self.quarantine.validation_no_ocdid

        validation_no_ocdid.write_csv(self.validation_no_ocdid_fp)
        logger.info("Stored validation data missing OCDids", extra={"filepath":self.validation_no_ocdid_fp})

        with open(self.ocdid_no_validation_fp, 'wb') as file:
            file.write(ocdid_no_validation)
        logger.info("Stored ocdids missing validation records", extra={"filepath":self.ocdid_no_validation_fp})

    def save_validation_data(self):
        """
        Save the updated validation DataFrame to a local CSV file.
        This can then be manually uploaded to update the shared Google Sheet.
        """
        self.validation_df.write_csv(self.validation_output_fp)
        print(f"Validation data saved to: {self.validation_output_fp}")


    def build_jurisdiction_record(self) -> Jurisdiction | None:
        """
        Build or update the Jurisdiction record for the current division.

        Behavior:
        - Uses the configured DivGeneratorReq on self.req.
        - If build_base_object is True:
            * Treat as if there is no existing YAML jurisdiction file.
            * Construct a new Jurisdiction object from validation data.
        - If build_base_object is False:
            * Attempt to load an existing jurisdiction from disk and update it.
        - If ai_url is True:
            * Make an AI/url-population call via _populate_juris_urls and attach
              any returned URLs to the jurisdiction object.
        """
        # Ensure we have a Division to work with
        if not self.division:
            try:
                self.load_division()
            except Exception as error:
                logger.error(
                    "Unable to build jurisdiction record without a division",
                    extra={"error": error},
                    exc_info=True,
                )
                raise

        # We need a validation record to map into a Jurisdiction
        if not hasattr(self, "validation_df") or getattr(self, "validation_df", None) is None:
            # Load the state-specific validation data
            self.load_validation_data()

        # Try to match this division to a single validation record
        state_val_df = self.validation_df
        match = self.match_division(state_val_df)
        if match is None:
            logger.info(
                "No matching validation record found for division; skipping jurisdiction build",
                extra={"ocdid": self.parsed_ocdid.raw_ocdid},
            )
            return None

        # Build or load the base jurisdiction object
        if self.req.build_base_object:
            # Act like there is no existing YAML; build from validation record
            self.jurisdiction = self._map_basedata_to_juris_obj(val_rec=match)
        else:
            # Try to load an existing jurisdiction file and then update it
            try:
                existing = self.load_jurisdiction()
                self.jurisdiction = existing
            except Exception:
                # If loading fails, fall back to building from scratch
                logger.warning(
                    "Failed to load existing jurisdiction; building a new one instead",
                    extra={"filepath": str(self.division_filepath)},
                    exc_info=True,
                )
                self.jurisdiction = self._map_basedata_to_juris_obj(val_rec=match)

        if not self.jurisdiction:
            raise ValueError("Jurisdiction object was not created successfully.")

        # Only divisions that are actually jurisdictions should proceed
        if not self._check_if_div_is_jurisdiction():
            logger.info(
                "Division is not a jurisdiction; skipping jurisdiction record build",
                extra={"ocdid": self.parsed_ocdid.raw_ocdid},
            )
            return None

        # Optionally enrich with AI-derived URLs
        if self.req.ai_url:
            try:
                url_data = self._populate_juris_urls()
                # Attach URLs to the jurisdiction object if there is a place for them.
                # This assumes the Jurisdiction model has attributes like `urls` or `extras`.
                if hasattr(self.jurisdiction, "urls") and isinstance(
                    getattr(self.jurisdiction, "urls"), dict | list | type(None)
                ):
                    # Simple strategy: store primary + secondary under a single field
                    setattr(self.jurisdiction, "urls", url_data)
                elif hasattr(self.jurisdiction, "extras") and isinstance(
                    getattr(self.jurisdiction, "extras"), dict | type(None)
                ):
                    extras = getattr(self.jurisdiction, "extras") or {}
                    extras["ai_urls"] = url_data
                    setattr(self.jurisdiction, "extras", extras)
            except Exception as error:
                logger.error(
                    "AI URL enrichment failed; continuing without URL data",
                    extra={"error": error},
                    exc_info=True,
                )

        # Persist the jurisdiction YAML
        self.save_jurisdiction()
        return self.jurisdiction


    async def run(self):
        # TODO:
        # - Implement method by method
        # - Build tests for each methoad as you go.
        # - Run code async where feasible
        return self.division, self.jurisdiction



if __name__  == "__main__":

    import asyncio
    from pathlib import Path
    from src.init_migration.models import OCDidIngestResp, DivGeneratorReq

    # TODO: customize these values for the division you want to process
    ingest = OCDidIngestResp(
        uuid="00000000-0000-0000-0000-000000000000",  # or an actual UUID
        filepath=Path("path/to/division.yaml"),
        ocdid="ocd-division/country:us/state:ca/place:san_francisco",
        raw_record={},
    )

    req = DivGeneratorReq(
        data=ingest,
        build_base_object=True,
        ai_url=False,
        geo_req=False,
        population_req=False,
    )

    dg = DivGenerator(req=req)
    division, jurisdiction = asyncio.run(dg.run())
    print("Division:", division)
    print("Jurisdiction:", jurisdiction)






