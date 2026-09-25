import polars as pl

from src.init_migration.generate_pipeline import GeneratePipeline


def _pipeline_with_rows(rows):
    pipeline = GeneratePipeline.__new__(GeneratePipeline)
    pipeline.validation_df = pl.DataFrame(rows)
    return pipeline


def test_place_exact_match_prefers_single_active_funcstat():
    pipeline = _pipeline_with_rows(
        [
            {
                "STATEFP": "48",
                "layer": "tl_2025_48_place",
                "normalized_place_name": "mesquite",
                "FUNCSTAT": "A",
                "GEOID": "4847892",
            },
            {
                "STATEFP": "48",
                "layer": "tl_2025_48_place",
                "normalized_place_name": "mesquite",
                "FUNCSTAT": "S",
                "GEOID": "4847898",
            },
        ]
    )

    matches = pipeline.find_matches(
        "ocd-division/country:us/state:tx/place:mesquite"
    )

    assert matches.height == 1
    assert matches["GEOID"].to_list() == ["4847892"]
    assert matches["FUNCSTAT"].to_list() == ["A"]


def test_place_exact_match_preserves_ambiguity_with_multiple_active_rows():
    pipeline = _pipeline_with_rows(
        [
            {
                "STATEFP": "48",
                "layer": "tl_2025_48_place",
                "normalized_place_name": "example",
                "FUNCSTAT": "A",
                "GEOID": "4800001",
            },
            {
                "STATEFP": "48",
                "layer": "tl_2025_48_place",
                "normalized_place_name": "example",
                "FUNCSTAT": "A",
                "GEOID": "4800002",
            },
            {
                "STATEFP": "48",
                "layer": "tl_2025_48_place",
                "normalized_place_name": "example",
                "FUNCSTAT": "S",
                "GEOID": "4800003",
            },
        ]
    )

    matches = pipeline.find_matches(
        "ocd-division/country:us/state:tx/place:example"
    )

    assert matches.height == 3
