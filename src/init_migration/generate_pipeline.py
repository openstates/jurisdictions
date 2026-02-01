"""
Orchestrator pipeline that coordinates division and jurisdiction generation.

This module accepts an `OCDidIngestResp` (single record) and delegates
generation work to `generate_division` and `generate_jurisdiction` modules.
"""

import logging
from pathlib import Path

from src.init_migration.models import OCDidIngestResp, GeneratorReq, GeneratorResp
from src.init_migration.generate_division import DivGenerator
from src.utils.ocdid import ocdid_parser
from src.models.division import Division
from src.models.jurisdiction import Jurisdiction
import polars as pl
from pydantic import BaseModel

logger = logging.getLogger(__name__)



class NoMatch(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    validation_no_ocdid_div: pl.DataFrame = pl.DataFrame()
    ocdid_no_validation_div: list[Division] = [] # Could also be OCDids

class ValidationRecord(BaseModel):
    """
    TODO: Convert the fields in the spreadsheet into a model.
    """

class GeneratePipeline:
    """Orchestrator that coordinates Division and Jurisdiction generation."""

    def __init__(
        self, req: GeneratorReq,
    ) -> None:
        """Initialize the Pipeline with request data and configuration flags.

        Args:
            data: OCDidIngestResp object containing UUID, filepath, ocdid, and raw_record
            build_base_object: Whether to build base Division object
            ai_url: Whether to populate URL data with AI scraper
            geo_req: Whether to populate geometry data
            population_req: Whether to populate Census population data
            validation_data_filepath: Optional path to validation CSV
        """
        self.data = data
        self.build_base_object = build_base_object
        self.ai_url = ai_url
        self.geo_req = geo_req
        self.population_req = population_req
        self.validation_data_filepath = validation_data_filepath
        self.quarantine = NoMatch()
        self.validation_no_ocdid_fp = f"validation_no_ocdid_asof_{req.asof_datetime}.csv"
        self.ocdid_no_validation_fp = f"ocdid_no_validation_asof_{req.asof_datetime}.txt"

        # Parse the OCDid
        try:
            self.parsed_ocdid = ocdid_parser(self.data.ocdid)
        except Exception:
            logger.error(f"Failed to parse OCDid: {self.data.ocdid}")


        # Initialize the generated objects as None
        self.division: Division | None = None
        self.jurisdiction: Jurisdiction | None = None
        # Initialize the response object
        self.response: GeneratorResp = GeneratorResp(
            data=self.data, division=None, jurisdiction=None
            )

    async def run(self) -> GeneratorResp:
        """Run the pipeline: generate Division then Jurisdiction.

        Returns:
            Dictionary with keys `division` and `jurisdiction` containing the generated
            objects or None if generation failed/was skipped.
        """
        req = GeneratorReq(
            data=self.data,
            build_base_object=self.build_base_object,
            ai_url=self.ai_url,
            geo_req=self.geo_req,
            population_req=self.population_req,
            validation_data_filepath=self.validation_data_filepath,
        )

        logger.info("Starting pipeline for OCDid", extra={"ocdid": self.data.ocdid, "as_datetime": req.asof_datetime})
        # Generate Division
        self.response.division = self._generate_division(req)

        # Generate Jurisdiction (only if division exists)
        if self.response.division:
            self.response.jurisdiction = self._generate_jurisdiction(req)

        return self.response

    def _generate_division(self, req: GeneratorReq) -> Division | None:
        """Generate a Division object based on the PipelineReq.

        Args:
            req: PipelineReq with configuration

        Returns:
            Generated Division object or None if generation failed
        """
        try:
            div_gen = DivGenerator(
                req=req,
                validation_data_filepath=self.validation_data_filepath
            )

            # Try to load existing division file
            try:
                div_gen.load_division()
            except Exception:
                logger.debug("No division file to load or load failed; continuing.")

            # Load state validation data
            try:
                state_df = div_gen.load_state_validation_data()
            except Exception:
                logger.debug("Could not load state validation data.")
                state_df = None

            # Attempt to match division with validation data
            matched = None
            if state_df is not None:
                try:
                    matched = div_gen.match_division(state_df)
                except Exception:
                    logger.debug("Could not match division with validation data.")

            # Generate and save division if we have a match
            if matched is not None:
                try:
                    division = div_gen.generate_division(val_rec=matched)
                    try:
                        div_gen.save_division()
                        logger.info(f"Division generated and saved: {self.data.ocdid}")
                    except Exception:
                        logger.warning("Division generated but could not be saved.")
                    return division
                except Exception:
                    logger.exception("Division generation failed.")
            else:
                logger.info("No matched validation record")
                div_gen.quarantine.division = div_gen.division
                div_gen.save_quarantine_data()

        except Exception:
            logger.exception("Division generator failed to initialize")

        return None

    def _generate_jurisdiction(self, req: GeneratorReq) -> Jurisdiction | None:
        """Generate a Jurisdiction object using the JurGenerator.

        Args:
            req: DivGeneratorReq with configuration

        Returns:
            Generated Jurisdiction object or None if generation failed
        """
        try:
            jur_gen = generate_jurisdiction.JurGenerator(
                req=req,
                validation_data_filepath=self.validation_data_filepath
                or generate_division.DIVISIONS_SHEET_CSV_URL,
            )

            # Load state validation data
            try:
                state_df = jur_gen.load_validation_data()
            except Exception:
                logger.debug("Could not load validation data for jurisdiction.")
                return None

            # Generate and save jurisdiction
            try:
                # Note: jurisdiction generation logic depends on the generator's implementation
                jurisdiction = jur_gen.generate_jurisdiction(val_rec=None)  # TODO: pass proper matched record
                if jurisdiction:
                    try:
                        jur_gen.save_jurisdiction()
                        logger.info(f"Jurisdiction generated and saved: {self.data.ocdid}")
                    except Exception:
                        logger.warning("Jurisdiction generated but could not be saved.")
                    return jurisdiction
            except Exception:
                logger.exception("Jurisdiction generation failed.")

        except Exception:
            logger.exception("Jurisdiction generator failed to initialize")

        return None


if __name__ == "__main__":
    import uuid

    sample = OCDidIngestResp(
        uuid=uuid.UUID(int=0),
        filepath=Path("/tmp/fake-division.yaml"),
        ocdid="ocd-division/country:us/state:ca",
        raw_record={}
    )

    pipeline = GeneratePipeline(
        data=sample,
        build_base_object=True,
        geo_req=False,
        ai_url=False
    )

    result = pipeline.run()

    print("=" * 60)
    print("Pipeline Run Complete")
    print("=" * 60)
    print(f"OCDid: {sample.ocdid}")
    print(f"Parsed: {pipeline.parsed_ocdid}")
    print(f"Division: {pipeline.division}")
    print(f"Jurisdiction: {pipeline.jurisdiction}")
    print("=" * 60)

