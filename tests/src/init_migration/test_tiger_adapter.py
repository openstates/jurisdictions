"""Unit tests for the offline-first TIGER source snapshot adapter."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from src.init_migration.tiger_adapter import (
    TIGER_LAYERS_2025,
    TigerAdapter,
    TigerCacheMissError,
    TigerGeography,
    TigerLayerSpec,
    TigerSnapshotIntegrityError,
    TigerSourceResponseError,
)

FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "tiger"
ALL_GEOGRAPHIES = tuple(TigerGeography)


class FakeFetcher:
    """Small ``AsyncDownloader`` stand-in for offline unit tests."""

    def __init__(self, *responses: bytes | None) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, bool]] = []

    async def fetch_bytes(
        self, url: str, *, force: bool = False
    ) -> bytes | None:
        self.calls.append((url, force))
        if not self.responses:
            raise AssertionError("FakeFetcher received an unexpected request")
        return self.responses.pop(0)


def fixture_bytes(geography_type: TigerGeography) -> bytes:
    path = FIXTURE_ROOT / f"{geography_type.value}.json"
    return path.read_bytes()


def fixture_document(geography_type: TigerGeography) -> dict:
    return json.loads(fixture_bytes(geography_type))


def layer_metadata_document(spec: TigerLayerSpec) -> dict:
    return {
        "id": spec.layer_id,
        "name": spec.layer_name,
        "type": "Feature Layer",
        "description": (
            f"{spec.layer_name}; January 1, {spec.vintage} vintage"
        ),
        "parentLayer": {
            "id": spec.parent_layer_id,
            "name": spec.parent_layer_name,
        },
        "capabilities": "Map,Query,Data",
        "maxRecordCount": 100_000,
        "fields": [
            {
                "name": name,
                "type": "esriFieldTypeString",
                "length": length,
            }
            for name, length in spec.expected_field_lengths.items()
        ],
    }


def layer_metadata_bytes(spec: TigerLayerSpec) -> bytes:
    return json.dumps(layer_metadata_document(spec)).encode()


def test_layer_catalog_covers_phase_4_scope() -> None:
    assert set(TIGER_LAYERS_2025) == set(ALL_GEOGRAPHIES)


def test_layer_catalog_uses_versioned_acs_2025_layers() -> None:
    assert TIGER_LAYERS_2025[TigerGeography.STATE].layer_id == 18
    assert TIGER_LAYERS_2025[TigerGeography.COUNTY].layer_id == 19
    assert TIGER_LAYERS_2025[TigerGeography.PLACE].layer_id == 11
    assert (
        TIGER_LAYERS_2025[TigerGeography.COUNTY_SUBDIVISION].layer_id
        == 8
    )
    assert (
        TIGER_LAYERS_2025[
            TigerGeography.UNIFIED_SCHOOL_DISTRICT
        ].layer_id
        == 5
    )
    assert TIGER_LAYERS_2025[TigerGeography.STATE].parent_layer_id == 17
    assert TIGER_LAYERS_2025[TigerGeography.PLACE].parent_layer_id == 6
    assert (
        TIGER_LAYERS_2025[
            TigerGeography.UNIFIED_SCHOOL_DISTRICT
        ].parent_layer_id
        == 4
    )


@pytest.mark.parametrize("geography_type", ALL_GEOGRAPHIES)
def test_layer_catalog_defines_widths_for_every_query_field(
    geography_type: TigerGeography,
) -> None:
    spec = TIGER_LAYERS_2025[geography_type]

    assert set(spec.expected_field_lengths) == set(spec.query_fields)


def test_query_requests_attributes_only_and_deterministic_order(
    tmp_path: Path,
) -> None:
    adapter = TigerAdapter(tmp_path)
    spec = adapter.get_spec(TigerGeography.PLACE)

    parsed = urlparse(adapter.build_query_url(spec))
    query = parse_qs(parsed.query)

    assert parsed.path.endswith("/MapServer/11/query")
    assert query["where"] == ["1=1"]
    assert query["returnGeometry"] == ["false"]
    assert query["orderByFields"] == ["GEOID"]
    assert query["resultRecordCount"] == ["100000"]
    assert "GEOID" in query["outFields"][0].split(",")
    assert "STGEOMETRY" not in query["outFields"][0].split(",")


@pytest.mark.parametrize("geography_type", ALL_GEOGRAPHIES)
def test_layer_metadata_preflight_accepts_catalog_contract(
    tmp_path: Path,
    geography_type: TigerGeography,
) -> None:
    adapter = TigerAdapter(tmp_path)
    spec = adapter.get_spec(geography_type)

    adapter.verify_layer_metadata(
        geography_type, layer_metadata_bytes(spec)
    )


@pytest.mark.asyncio
async def test_fetch_preflights_metadata_before_query(tmp_path: Path) -> None:
    adapter = TigerAdapter(tmp_path)
    geography_type = TigerGeography.STATE
    spec = adapter.get_spec(geography_type)
    payload = fixture_bytes(geography_type)
    fetcher = FakeFetcher(layer_metadata_bytes(spec), payload)

    result = await adapter.fetch(fetcher, geography_type)

    assert result == payload
    assert fetcher.calls == [
        (spec.metadata_url, True),
        (adapter.build_query_url(spec), False),
    ]


@pytest.mark.asyncio
async def test_fetch_rejects_missing_metadata_payload(tmp_path: Path) -> None:
    adapter = TigerAdapter(tmp_path)

    with pytest.raises(
        TigerSourceResponseError, match="metadata preflight returned no payload"
    ):
        await adapter.fetch(FakeFetcher(None), TigerGeography.STATE)


def test_layer_metadata_rejects_wrong_parent_vintage(
    tmp_path: Path,
) -> None:
    adapter = TigerAdapter(tmp_path)
    geography_type = TigerGeography.STATE
    spec = adapter.get_spec(geography_type)
    document = layer_metadata_document(spec)
    document["parentLayer"] = {"id": 35, "name": "ACS 2024"}

    with pytest.raises(
        TigerSourceResponseError, match="parent does not match"
    ):
        adapter.verify_layer_metadata(
            geography_type, json.dumps(document).encode()
        )


def test_layer_metadata_rejects_description_vintage_drift(
    tmp_path: Path,
) -> None:
    adapter = TigerAdapter(tmp_path)
    geography_type = TigerGeography.PLACE
    spec = adapter.get_spec(geography_type)
    document = layer_metadata_document(spec)
    document["description"] = "Incorporated Places; January 1, 2024 vintage"

    with pytest.raises(
        TigerSourceResponseError, match="does not confirm"
    ):
        adapter.verify_layer_metadata(
            geography_type, json.dumps(document).encode()
        )


def test_layer_metadata_rejects_name_drift(tmp_path: Path) -> None:
    adapter = TigerAdapter(tmp_path)
    geography_type = TigerGeography.COUNTY
    spec = adapter.get_spec(geography_type)
    document = layer_metadata_document(spec)
    document["name"] = "County Subdivisions"

    with pytest.raises(
        TigerSourceResponseError, match="name does not match"
    ):
        adapter.verify_layer_metadata(
            geography_type, json.dumps(document).encode()
        )


def test_layer_metadata_rejects_missing_query_capability(
    tmp_path: Path,
) -> None:
    adapter = TigerAdapter(tmp_path)
    geography_type = TigerGeography.STATE
    spec = adapter.get_spec(geography_type)
    document = layer_metadata_document(spec)
    document["capabilities"] = "Map,Data"

    with pytest.raises(
        TigerSourceResponseError, match="Query capability"
    ):
        adapter.verify_layer_metadata(
            geography_type, json.dumps(document).encode()
        )


def test_layer_metadata_rejects_small_record_limit(tmp_path: Path) -> None:
    adapter = TigerAdapter(tmp_path)
    geography_type = TigerGeography.STATE
    spec = adapter.get_spec(geography_type)
    document = layer_metadata_document(spec)
    document["maxRecordCount"] = 2_000

    with pytest.raises(
        TigerSourceResponseError, match="maxRecordCount"
    ):
        adapter.verify_layer_metadata(
            geography_type, json.dumps(document).encode()
        )


def test_layer_metadata_rejects_missing_field(tmp_path: Path) -> None:
    adapter = TigerAdapter(tmp_path)
    geography_type = TigerGeography.PLACE
    spec = adapter.get_spec(geography_type)
    document = layer_metadata_document(spec)
    document["fields"] = [
        field for field in document["fields"] if field["name"] != "PLACE"
    ]

    with pytest.raises(
        TigerSourceResponseError, match="missing required fields: PLACE"
    ):
        adapter.verify_layer_metadata(
            geography_type, json.dumps(document).encode()
        )


def test_layer_metadata_rejects_identifier_width_drift(
    tmp_path: Path,
) -> None:
    adapter = TigerAdapter(tmp_path)
    geography_type = TigerGeography.UNIFIED_SCHOOL_DISTRICT
    spec = adapter.get_spec(geography_type)
    document = layer_metadata_document(spec)
    geoid_field = next(
        field for field in document["fields"] if field["name"] == "GEOID"
    )
    geoid_field["length"] = 8

    with pytest.raises(
        TigerSourceResponseError, match="GEOID.*retain length 7"
    ):
        adapter.verify_layer_metadata(
            geography_type, json.dumps(document).encode()
        )


@pytest.mark.parametrize("geography_type", ALL_GEOGRAPHIES)
def test_fixture_round_trip_is_offline_and_lossless(
    tmp_path: Path,
    geography_type: TigerGeography,
) -> None:
    adapter = TigerAdapter(tmp_path)
    payload = fixture_bytes(geography_type)
    retrieved_at = datetime(2026, 8, 10, 16, 0, tzinfo=timezone.utc)

    verified = adapter.verify(geography_type, payload)
    metadata = adapter.cache(verified, retrieved_at=retrieved_at)
    parsed = adapter.parse(geography_type)

    assert metadata.record_count == 1
    assert metadata.retrieved_at == "2026-08-10T16:00:00Z"
    assert metadata.snapshot_path.read_bytes() == payload
    assert parsed.input_count == 1
    assert len(parsed.records) == 1
    assert parsed.errors == ()
    assert parsed.records[0].geography_type is geography_type


def test_parse_preserves_leading_zero_identifiers(tmp_path: Path) -> None:
    adapter = TigerAdapter(tmp_path)
    geography_type = TigerGeography.COUNTY_SUBDIVISION
    payload = fixture_bytes(geography_type)

    adapter.cache(adapter.verify(geography_type, payload))
    record = adapter.parse(geography_type).records[0]

    assert record.geoid == "0804100001"
    assert record.state_fips == "08"
    assert record.county_fips == "041"
    assert record.county_subdivision_fips == "00001"


def test_parse_accepts_blank_school_district_type(tmp_path: Path) -> None:
    adapter = TigerAdapter(tmp_path)
    geography_type = TigerGeography.UNIFIED_SCHOOL_DISTRICT
    payload = fixture_bytes(geography_type)

    adapter.cache(adapter.verify(geography_type, payload))
    record = adapter.parse(geography_type).records[0]

    assert record.school_district_type is None
    assert record.low_grade == "PK"
    assert record.high_grade == "12"


@pytest.mark.asyncio
async def test_refresh_reuses_integrity_checked_cache_after_304(
    tmp_path: Path,
) -> None:
    adapter = TigerAdapter(tmp_path)
    geography_type = TigerGeography.STATE
    spec = adapter.get_spec(geography_type)
    initial = adapter.cache(
        adapter.verify(geography_type, fixture_bytes(geography_type))
    )
    fetcher = FakeFetcher(layer_metadata_bytes(spec), None)

    refreshed = await adapter.refresh(fetcher, geography_type)

    assert refreshed.sha256 == initial.sha256
    assert refreshed.record_count == initial.record_count
    assert len(fetcher.calls) == 2


@pytest.mark.asyncio
async def test_refresh_304_without_cache_fails_closed(
    tmp_path: Path,
) -> None:
    adapter = TigerAdapter(tmp_path)
    geography_type = TigerGeography.STATE
    spec = adapter.get_spec(geography_type)

    with pytest.raises(TigerCacheMissError):
        await adapter.refresh(
            FakeFetcher(layer_metadata_bytes(spec), None), geography_type
        )


def test_verify_rejects_arcgis_error_response(tmp_path: Path) -> None:
    adapter = TigerAdapter(tmp_path)
    payload = json.dumps(
        {"error": {"code": 500, "message": "source failure"}}
    ).encode()

    with pytest.raises(TigerSourceResponseError, match="returned an error"):
        adapter.verify(TigerGeography.STATE, payload)


def test_verify_rejects_partial_transfer(tmp_path: Path) -> None:
    adapter = TigerAdapter(tmp_path)
    document = fixture_document(TigerGeography.STATE)
    document["exceededTransferLimit"] = True

    with pytest.raises(
        TigerSourceResponseError, match="partial snapshot"
    ):
        adapter.verify(
            TigerGeography.STATE, json.dumps(document).encode()
        )


def test_verify_rejects_empty_national_layer(tmp_path: Path) -> None:
    adapter = TigerAdapter(tmp_path)
    document = fixture_document(TigerGeography.STATE)
    document["features"] = []

    with pytest.raises(
        TigerSourceResponseError, match="contained no features"
    ):
        adapter.verify(
            TigerGeography.STATE, json.dumps(document).encode()
        )


def test_verify_rejects_missing_requested_field(tmp_path: Path) -> None:
    adapter = TigerAdapter(tmp_path)
    document = fixture_document(TigerGeography.PLACE)
    del document["features"][0]["attributes"]["PLACE"]

    with pytest.raises(
        TigerSourceResponseError, match="missing requested fields: PLACE"
    ):
        adapter.verify(
            TigerGeography.PLACE, json.dumps(document).encode()
        )


def test_parse_reports_bad_row_instead_of_dropping_it(
    tmp_path: Path,
) -> None:
    adapter = TigerAdapter(tmp_path)
    geography_type = TigerGeography.PLACE
    document = fixture_document(geography_type)
    malformed = dict(document["features"][0]["attributes"])
    malformed["GEOID"] = 800001
    document["features"].append({"attributes": malformed})
    payload = json.dumps(document).encode()

    adapter.cache(adapter.verify(geography_type, payload))
    result = adapter.parse(geography_type)

    assert result.input_count == 2
    assert len(result.records) == 1
    assert len(result.errors) == 1
    assert result.errors[0].feature_index == 1
    assert "GEOID must be a non-empty string" in result.errors[0].message


def test_parse_reports_duplicate_geoid(tmp_path: Path) -> None:
    adapter = TigerAdapter(tmp_path)
    geography_type = TigerGeography.COUNTY
    document = fixture_document(geography_type)
    duplicate = dict(document["features"][0]["attributes"])
    document["features"].append({"attributes": duplicate})
    payload = json.dumps(document).encode()

    adapter.cache(adapter.verify(geography_type, payload))
    result = adapter.parse(geography_type)

    assert result.input_count == 2
    assert len(result.records) == 1
    assert len(result.errors) == 1
    assert "duplicate GEOID" in result.errors[0].message


def test_parse_reports_component_geoid_mismatch(tmp_path: Path) -> None:
    adapter = TigerAdapter(tmp_path)
    geography_type = TigerGeography.COUNTY
    document = fixture_document(geography_type)
    document["features"][0]["attributes"]["COUNTY"] = "042"
    payload = json.dumps(document).encode()

    adapter.cache(adapter.verify(geography_type, payload))
    result = adapter.parse(geography_type)

    assert result.records == ()
    assert len(result.errors) == 1
    assert "does not match component fields" in result.errors[0].message


def test_cached_snapshot_checksum_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    adapter = TigerAdapter(tmp_path)
    geography_type = TigerGeography.STATE
    metadata = adapter.cache(
        adapter.verify(geography_type, fixture_bytes(geography_type))
    )
    metadata.snapshot_path.write_bytes(
        metadata.snapshot_path.read_bytes() + b"\n"
    )

    with pytest.raises(
        TigerSnapshotIntegrityError, match="Checksum mismatch"
    ):
        adapter.load_cached_metadata(geography_type)


def test_cache_requires_timezone_aware_retrieval_time(
    tmp_path: Path,
) -> None:
    adapter = TigerAdapter(tmp_path)
    verified = adapter.verify(
        TigerGeography.STATE, fixture_bytes(TigerGeography.STATE)
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        adapter.cache(verified, retrieved_at=datetime(2026, 8, 10))


def test_unsupported_vintage_is_explicit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported TIGER vintage"):
        TigerAdapter(tmp_path, vintage="2024")
