from __future__ import annotations

import asyncio
import csv
import json
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from src.init_migration.ocd_master_adapter import (
    OCD_MASTER_HEADERS,
    OCD_MASTER_RELEASE,
    OCDMasterAdapter,
    OCDMasterCacheMissError,
    OCDMasterIndex,
    OCDMasterReleaseSpec,
    OCDMasterSnapshotIntegrityError,
    OCDMasterSourceError,
    OCDMasterSourceRecord,
)

FIXTURE_PATH = (
    Path(__file__).parents[2]
    / "fixtures"
    / "ocd_master"
    / "mini_country_us.csv"
)
FIXED_RETRIEVED_AT = datetime(2026, 8, 16, 18, 30, tzinfo=timezone.utc)


class FakeFetcher:
    def __init__(self, payload: bytes | None) -> None:
        self.payload = payload
        self.calls: list[tuple[str, bool]] = []

    async def fetch_bytes(self, url: str, *, force: bool = False) -> bytes | None:
        self.calls.append((url, force))
        return self.payload


@pytest.fixture
def fixture_payload() -> bytes:
    return FIXTURE_PATH.read_bytes()


@pytest.fixture
def fixture_spec() -> OCDMasterReleaseSpec:
    return OCDMasterReleaseSpec(
        repository="example/ocd-division-ids",
        revision="fixture-revision",
        source_path="identifiers/country-us.csv",
        source_url="https://example.invalid/fixture-revision/country-us.csv",
        expected_git_blob_sha1=None,
    )


@pytest.fixture
def adapter(
    tmp_path: Path,
    fixture_spec: OCDMasterReleaseSpec,
) -> OCDMasterAdapter:
    return OCDMasterAdapter(tmp_path, release_spec=fixture_spec)


def _csv_payload(
    rows: list[list[str]],
    *,
    headers: tuple[str, ...] = OCD_MASTER_HEADERS,
) -> bytes:
    from io import StringIO

    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _source_row(ocdid: str, name: str) -> list[str]:
    return [ocdid, name, *([""] * (len(OCD_MASTER_HEADERS) - 2))]


def _verified_index(
    adapter: OCDMasterAdapter,
    payload: bytes,
) -> OCDMasterIndex:
    snapshot = adapter.verify(payload)
    return adapter.build_index(adapter.parse(snapshot))


def test_default_release_is_revision_pinned() -> None:
    assert OCD_MASTER_RELEASE.revision in OCD_MASTER_RELEASE.source_url
    assert "/master/" not in OCD_MASTER_RELEASE.source_url
    assert OCD_MASTER_RELEASE.expected_git_blob_sha1 == (
        "bca1de20902adabb89961d08e68e0400d41dde50"
    )


def test_fetch_delegates_to_existing_downloader_boundary(
    adapter: OCDMasterAdapter,
    fixture_payload: bytes,
) -> None:
    fetcher = FakeFetcher(fixture_payload)

    result = asyncio.run(adapter.fetch(fetcher, force=True))

    assert result == fixture_payload
    assert fetcher.calls == [(adapter.release_spec.source_url, True)]


def test_verify_accepts_controlled_offline_fixture(
    adapter: OCDMasterAdapter,
    fixture_payload: bytes,
) -> None:
    snapshot = adapter.verify(fixture_payload)

    assert snapshot.data_row_count == 8
    assert snapshot.source_size == len(fixture_payload)
    assert snapshot.source_sha256 == sha256(fixture_payload).hexdigest()
    assert len(snapshot.source_git_blob_sha1) == 40


def test_verify_enforces_pinned_git_blob(
    tmp_path: Path,
    fixture_spec: OCDMasterReleaseSpec,
    fixture_payload: bytes,
) -> None:
    pinned_spec = replace(fixture_spec, expected_git_blob_sha1="0" * 40)
    pinned_adapter = OCDMasterAdapter(tmp_path, release_spec=pinned_spec)

    with pytest.raises(OCDMasterSourceError, match="pinned Git blob"):
        pinned_adapter.verify(fixture_payload)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"", "empty"),
        (b"\xff\xfe", "valid UTF-8"),
        (b"id,name\x00\n", "NUL"),
    ],
)
def test_verify_rejects_invalid_source_bytes(
    adapter: OCDMasterAdapter,
    payload: bytes,
    message: str,
) -> None:
    with pytest.raises(OCDMasterSourceError, match=message):
        adapter.verify(payload)


def test_verify_rejects_oversized_source(
    tmp_path: Path,
    fixture_spec: OCDMasterReleaseSpec,
) -> None:
    tiny_adapter = OCDMasterAdapter(
        tmp_path,
        release_spec=fixture_spec,
        max_source_bytes=2,
    )

    with pytest.raises(OCDMasterSourceError, match="size limit"):
        tiny_adapter.verify(b"abc")


def test_verify_rejects_header_drift(adapter: OCDMasterAdapter) -> None:
    changed_headers = ("ocdid", *OCD_MASTER_HEADERS[1:])
    payload = _csv_payload(
        [_source_row("ocd-division/country:us", "United States")],
        headers=changed_headers,
    )

    with pytest.raises(OCDMasterSourceError, match="headers"):
        adapter.verify(payload)


def test_verify_rejects_source_without_data_rows(adapter: OCDMasterAdapter) -> None:
    payload = _csv_payload([])

    with pytest.raises(OCDMasterSourceError, match="no data rows"):
        adapter.verify(payload)


def test_verify_rejects_wrong_column_count(adapter: OCDMasterAdapter) -> None:
    payload = _csv_payload([["ocd-division/country:us", "United States"]])

    with pytest.raises(OCDMasterSourceError, match="2 columns"):
        adapter.verify(payload)


@pytest.mark.parametrize(
    ("ocdid", "name", "message"),
    [
        ("", "Missing ID", "empty ID"),
        ("ocd-division/country:us/state:co", "   ", "empty name"),
        (
            " ocd-division/country:us/state:co",
            "Colorado",
            "whitespace",
        ),
        ("not-an-ocdid", "Invalid", "invalid division ID"),
        (
            "ocd-jurisdiction/country:us/state:co/government",
            "Colorado government",
            "invalid division ID",
        ),
    ],
)
def test_verify_rejects_invalid_membership_rows(
    adapter: OCDMasterAdapter,
    ocdid: str,
    name: str,
    message: str,
) -> None:
    payload = _csv_payload([_source_row(ocdid, name)])

    with pytest.raises(OCDMasterSourceError, match=message):
        adapter.verify(payload)


def test_verify_rejects_duplicate_identifiers(adapter: OCDMasterAdapter) -> None:
    duplicate = "ocd-division/country:us/state:co"
    payload = _csv_payload(
        [
            _source_row(duplicate, "Colorado"),
            _source_row(duplicate, "Duplicate Colorado"),
        ]
    )

    with pytest.raises(OCDMasterSourceError, match="duplicates ID"):
        adapter.verify(payload)


def test_parse_preserves_exact_ids_names_and_source_rows(
    adapter: OCDMasterAdapter,
    fixture_payload: bytes,
) -> None:
    result = adapter.parse(adapter.verify(fixture_payload))

    assert result.record_count == 8
    assert result.records[0] == OCDMasterSourceRecord(
        ocdid="ocd-division/country:us",
        name="United States",
        source_row_number=2,
    )
    assert result.records[-1].source_row_number == 9
    assert result.source_sha256 == sha256(fixture_payload).hexdigest()


def test_exact_lookup_returns_source_record(
    adapter: OCDMasterAdapter,
    fixture_payload: bytes,
) -> None:
    index = _verified_index(adapter, fixture_payload)

    match = index.exact_lookup(
        "ocd-division/country:us/state:co/place:colorado_springs"
    )

    assert match is not None
    assert match.name == "Colorado Springs"
    assert index.contains(match.ocdid) is True


def test_exact_lookup_returns_none_for_valid_negative(
    adapter: OCDMasterAdapter,
    fixture_payload: bytes,
) -> None:
    index = _verified_index(adapter, fixture_payload)
    candidate = "ocd-division/country:us/state:co/place:missing"

    assert index.exact_lookup(candidate) is None
    assert index.contains(candidate) is False


@pytest.mark.parametrize(
    "candidate",
    [
        "not-an-ocdid",
        " ocd-division/country:us/state:co",
        "ocd-jurisdiction/country:us/state:co/government",
    ],
)
def test_exact_lookup_rejects_malformed_or_non_division_candidates(
    adapter: OCDMasterAdapter,
    fixture_payload: bytes,
    candidate: str,
) -> None:
    index = _verified_index(adapter, fixture_payload)

    with pytest.raises(Exception):
        index.exact_lookup(candidate)


def test_review_suggestions_are_same_parent_and_explicitly_non_accepting(
    adapter: OCDMasterAdapter,
    fixture_payload: bytes,
) -> None:
    index = _verified_index(adapter, fixture_payload)
    candidate = "ocd-division/country:us/state:co/place:colorado_spring"

    suggestions = index.suggest_for_review(candidate, score_cutoff=60)

    assert suggestions
    assert suggestions[0].suggested_ocdid == (
        "ocd-division/country:us/state:co/place:colorado_springs"
    )
    assert all(suggestion.review_only is True for suggestion in suggestions)
    assert all("/state:co/" in suggestion.suggested_ocdid for suggestion in suggestions)
    assert all("/place:" in suggestion.suggested_ocdid for suggestion in suggestions)
    assert all(
        "/state:tx/" not in suggestion.suggested_ocdid
        for suggestion in suggestions
    )
    assert index.contains(candidate) is False
    assert index.exact_lookup(candidate) is None


def test_review_suggestions_are_empty_for_exact_member(
    adapter: OCDMasterAdapter,
    fixture_payload: bytes,
) -> None:
    index = _verified_index(adapter, fixture_payload)
    exact = "ocd-division/country:us/state:tx/place:austin"

    assert index.suggest_for_review(exact) == ()


def test_review_suggestions_do_not_cross_missing_parent(
    adapter: OCDMasterAdapter,
    fixture_payload: bytes,
) -> None:
    index = _verified_index(adapter, fixture_payload)
    candidate = "ocd-division/country:us/state:zz/place:austin"

    assert index.suggest_for_review(candidate) == ()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"limit": 0}, "positive integer"),
        ({"limit": True}, "positive integer"),
        ({"score_cutoff": -1}, "between 0 and 100"),
        ({"score_cutoff": 101}, "between 0 and 100"),
    ],
)
def test_review_suggestion_controls_are_validated(
    adapter: OCDMasterAdapter,
    fixture_payload: bytes,
    kwargs: dict[str, object],
    message: str,
) -> None:
    index = _verified_index(adapter, fixture_payload)
    candidate = "ocd-division/country:us/state:co/place:colorado_spring"

    with pytest.raises(ValueError, match=message):
        index.suggest_for_review(candidate, **kwargs)  # type: ignore[arg-type]


def test_index_rejects_duplicate_records() -> None:
    record = OCDMasterSourceRecord(
        ocdid="ocd-division/country:us/state:co",
        name="Colorado",
        source_row_number=2,
    )

    with pytest.raises(ValueError, match="Duplicate OCD ID"):
        OCDMasterIndex([record, record])


def test_cache_writes_verbatim_source_and_complete_manifest(
    adapter: OCDMasterAdapter,
    fixture_payload: bytes,
) -> None:
    snapshot = adapter.verify(fixture_payload)

    metadata = adapter.cache(snapshot, retrieved_at=FIXED_RETRIEVED_AT)
    manifest = json.loads(metadata.manifest_path.read_text(encoding="utf-8"))

    assert metadata.cache_path.read_bytes() == fixture_payload
    assert metadata.retrieved_at == "2026-08-16T18:30:00Z"
    assert manifest["source_revision"] == adapter.release_spec.revision
    assert manifest["source_sha256"] == sha256(fixture_payload).hexdigest()
    assert manifest["data_row_count"] == 8
    assert tuple(manifest["headers"]) == OCD_MASTER_HEADERS


def test_load_cached_metadata_round_trips_integrity_checked_snapshot(
    adapter: OCDMasterAdapter,
    fixture_payload: bytes,
) -> None:
    cached = adapter.cache(
        adapter.verify(fixture_payload),
        retrieved_at=FIXED_RETRIEVED_AT,
    )

    loaded = adapter.load_cached_metadata()

    assert loaded == cached
    assert adapter.parse_cached().record_count == 8


def test_load_cached_metadata_detects_source_tampering(
    adapter: OCDMasterAdapter,
    fixture_payload: bytes,
) -> None:
    metadata = adapter.cache(adapter.verify(fixture_payload))
    metadata.cache_path.write_bytes(fixture_payload + b"\n")

    with pytest.raises(OCDMasterSnapshotIntegrityError, match="Checksum mismatch"):
        adapter.load_cached_metadata()


def test_load_cached_metadata_detects_manifest_contract_tampering(
    adapter: OCDMasterAdapter,
    fixture_payload: bytes,
) -> None:
    metadata = adapter.cache(adapter.verify(fixture_payload))
    manifest = json.loads(metadata.manifest_path.read_text(encoding="utf-8"))
    manifest["source_revision"] = "different-revision"
    metadata.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(
        OCDMasterSnapshotIntegrityError,
        match="source_revision",
    ):
        adapter.load_cached_metadata()


def test_cache_miss_is_explicit(adapter: OCDMasterAdapter) -> None:
    with pytest.raises(OCDMasterCacheMissError, match="No complete cached"):
        adapter.load_cached_metadata()


def test_refresh_fetches_verifies_and_caches_new_bytes(
    adapter: OCDMasterAdapter,
    fixture_payload: bytes,
) -> None:
    fetcher = FakeFetcher(fixture_payload)

    metadata = asyncio.run(
        adapter.refresh(
            fetcher,
            force=True,
            retrieved_at=FIXED_RETRIEVED_AT,
        )
    )

    assert metadata.cache_path.read_bytes() == fixture_payload
    assert metadata.data_row_count == 8
    assert fetcher.calls == [(adapter.release_spec.source_url, True)]


def test_refresh_reuses_only_a_valid_cache_after_not_modified(
    adapter: OCDMasterAdapter,
    fixture_payload: bytes,
) -> None:
    expected = adapter.cache(
        adapter.verify(fixture_payload),
        retrieved_at=FIXED_RETRIEVED_AT,
    )
    fetcher = FakeFetcher(None)

    loaded = asyncio.run(adapter.refresh(fetcher))

    assert loaded == expected


def test_refresh_not_modified_without_cache_fails_closed(
    adapter: OCDMasterAdapter,
) -> None:
    fetcher = FakeFetcher(None)

    with pytest.raises(OCDMasterCacheMissError):
        asyncio.run(adapter.refresh(fetcher))


def test_cache_rejects_snapshot_from_different_release(
    tmp_path: Path,
    adapter: OCDMasterAdapter,
    fixture_spec: OCDMasterReleaseSpec,
    fixture_payload: bytes,
) -> None:
    snapshot = adapter.verify(fixture_payload)
    other_adapter = OCDMasterAdapter(
        tmp_path / "other",
        release_spec=replace(fixture_spec, revision="different"),
    )

    with pytest.raises(ValueError, match="does not match adapter"):
        other_adapter.cache(snapshot)


def test_naive_retrieval_timestamp_is_rejected(
    adapter: OCDMasterAdapter,
    fixture_payload: bytes,
) -> None:
    snapshot = adapter.verify(fixture_payload)

    with pytest.raises(ValueError, match="timezone-aware"):
        adapter.cache(snapshot, retrieved_at=datetime(2026, 8, 16, 18, 30))
