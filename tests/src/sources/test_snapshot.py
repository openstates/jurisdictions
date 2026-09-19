"""Tests for the source snapshot layer: fetch, verify, cache, provenance."""

import json
from datetime import datetime, timezone

import httpx
import pytest

from src.errors import SnapshotIntegrityError, SnapshotMetadataError
from src.init_migration.downloader import AsyncDownloader
from src.models.source import SourceType
from src.sources.snapshot import (
    Snapshot,
    SnapshotMetadata,
    SnapshotSpec,
    SnapshotStore,
    load_snapshot,
    read_metadata,
    sha256_of_bytes,
    sha256_of_file,
    sidecar_path,
    source_obj_from_snapshot,
    verify_snapshot,
    write_metadata,
)

URL = "https://example.com/data/units.csv"
CONTENT = b"id,name\n1,alpha\n2,beta\n"
RETRIEVED_AT = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
PUBLISHED_AT = datetime(2025, 3, 1, tzinfo=timezone.utc)


def make_spec(**overrides) -> SnapshotSpec:
    fields = dict(
        source="example",
        source_name="Example Provider",
        dataset="Example Units",
        release="2025",
        filename="units.csv",
        url=URL,
        publication_date=PUBLISHED_AT,
    )
    fields.update(overrides)
    return SnapshotSpec(**fields)


def make_metadata(**overrides) -> SnapshotMetadata:
    fields = dict(
        source="example",
        source_name="Example Provider",
        dataset="Example Units",
        release="2025",
        filename="units.csv",
        url=URL,
        sha256=sha256_of_bytes(CONTENT),
        size_bytes=len(CONTENT),
        retrieved_at=RETRIEVED_AT,
        publication_date=PUBLISHED_AT,
    )
    fields.update(overrides)
    return SnapshotMetadata(**fields)


class TestChecksums:
    def test_sha256_of_bytes_matches_file(self, tmp_path):
        path = tmp_path / "f.bin"
        path.write_bytes(CONTENT)
        assert sha256_of_file(path) == sha256_of_bytes(CONTENT)

    def test_sidecar_sits_next_to_file(self, tmp_path):
        assert sidecar_path(tmp_path / "units.csv") == tmp_path / "units.csv.meta.json"


class TestMetadata:
    def test_json_round_trip(self):
        metadata = make_metadata()
        assert SnapshotMetadata.from_json(metadata.to_json()) == metadata

    def test_json_is_sorted_and_iso(self):
        text = make_metadata().to_json()
        record = json.loads(text)
        assert list(record) == sorted(record)
        assert record["retrieved_at"] == "2026-09-18T12:00:00+00:00"
        assert record["publication_date"] == "2025-03-01T00:00:00+00:00"
        assert text.endswith("\n")

    def test_publication_date_optional(self):
        metadata = make_metadata(publication_date=None)
        record = json.loads(metadata.to_json())
        assert record["publication_date"] is None
        assert SnapshotMetadata.from_json(metadata.to_json()) == metadata

    def test_naive_retrieved_at_rejected(self):
        with pytest.raises(ValueError, match="retrieved_at"):
            make_metadata(retrieved_at=datetime(2026, 9, 18))

    def test_naive_publication_date_rejected(self):
        with pytest.raises(ValueError, match="publication_date"):
            make_spec(publication_date=datetime(2025, 3, 1))

    def test_missing_key_is_metadata_error(self):
        record = json.loads(make_metadata().to_json())
        del record["sha256"]
        with pytest.raises(SnapshotMetadataError):
            SnapshotMetadata.from_json(json.dumps(record))

    def test_invalid_json_is_metadata_error(self):
        with pytest.raises(SnapshotMetadataError):
            SnapshotMetadata.from_json("{not json")

    def test_spec_rejects_paths_as_filename(self):
        with pytest.raises(ValueError, match="bare file name"):
            make_spec(filename="sub/units.csv")

    def test_spec_rejects_empty_release(self):
        with pytest.raises(ValueError, match="release"):
            make_spec(release="")


class TestLoadAndVerify:
    def test_load_reads_sidecar_and_verifies(self, tmp_path):
        path = tmp_path / "units.csv"
        path.write_bytes(CONTENT)
        write_metadata(path, make_metadata())

        snapshot = load_snapshot(path)

        assert snapshot.path == path
        assert snapshot.metadata == make_metadata()
        assert snapshot.read_bytes() == CONTENT
        assert snapshot.read_text().startswith("id,name")

    def test_missing_sidecar(self, tmp_path):
        path = tmp_path / "units.csv"
        path.write_bytes(CONTENT)
        with pytest.raises(SnapshotMetadataError):
            load_snapshot(path)

    def test_sidecar_for_other_file(self, tmp_path):
        path = tmp_path / "other.csv"
        path.write_bytes(CONTENT)
        write_metadata(path, make_metadata(filename="units.csv"))
        with pytest.raises(SnapshotMetadataError, match="different file"):
            read_metadata(path)

    def test_tampered_content_fails_checksum(self, tmp_path):
        path = tmp_path / "units.csv"
        path.write_bytes(b"id,name\n1,ALPHA\n2,beta\n")
        write_metadata(path, make_metadata())
        with pytest.raises(SnapshotIntegrityError, match="checksum") as info:
            load_snapshot(path)
        assert info.value.expected == sha256_of_bytes(CONTENT)
        assert info.value.actual == sha256_of_file(path)

    def test_size_mismatch_reported_before_checksum(self, tmp_path):
        path = tmp_path / "units.csv"
        path.write_bytes(CONTENT + b"extra\n")
        write_metadata(path, make_metadata())
        with pytest.raises(SnapshotIntegrityError, match="size"):
            verify_snapshot(Snapshot(path=path, metadata=make_metadata()))

    def test_load_without_verify_skips_checksum(self, tmp_path):
        path = tmp_path / "units.csv"
        path.write_bytes(b"changed")
        write_metadata(path, make_metadata())
        snapshot = load_snapshot(path, verify=False)
        assert snapshot.metadata.sha256 == sha256_of_bytes(CONTENT)

    def test_missing_file(self, tmp_path):
        with pytest.raises(SnapshotIntegrityError, match="not found"):
            verify_snapshot(
                Snapshot(path=tmp_path / "absent.csv", metadata=make_metadata())
            )


class TestSourceObj:
    def test_fields_map_onto_source_obj(self):
        source = source_obj_from_snapshot(
            make_metadata(), field=["government_identifiers"]
        )
        assert source.field == ["government_identifiers"]
        assert source.source_name == "Example Provider"
        assert source.source_type == SourceType.SCRAPED
        assert str(source.source_url) == URL
        assert source.source_description is None
        assert source.dataset == "Example Units"
        assert source.release == "2025"
        assert source.publication_date == PUBLISHED_AT
        assert source.retrieval_date == RETRIEVED_AT

    def test_unknown_publication_date_stays_none(self):
        source = source_obj_from_snapshot(
            make_metadata(publication_date=None),
            field=["geometries"],
            source_type=SourceType.HUMAN,
            source_description="curated",
        )
        assert source.publication_date is None
        assert source.source_type == SourceType.HUMAN
        assert source.source_description == "curated"


class TestStore:
    def test_layout_is_source_release_filename(self, tmp_path):
        store = SnapshotStore(tmp_path / "raw")
        assert (
            store.path_for("census_governments", "2022", "units.csv")
            == tmp_path / "raw" / "census_governments" / "2022" / "units.csv"
        )

    def test_get_returns_none_when_absent(self, tmp_path):
        store = SnapshotStore(tmp_path)
        assert store.get("example", "2025", "units.csv") is None

    def test_get_requires_sidecar(self, tmp_path):
        store = SnapshotStore(tmp_path)
        path = store.path_for("example", "2025", "units.csv")
        path.parent.mkdir(parents=True)
        path.write_bytes(CONTENT)
        assert store.get("example", "2025", "units.csv") is None

    def test_put_writes_file_and_sidecar(self, tmp_path):
        store = SnapshotStore(tmp_path)
        snapshot = store.put(make_spec(), CONTENT, retrieved_at=RETRIEVED_AT)

        assert snapshot.path == tmp_path / "example" / "2025" / "units.csv"
        assert snapshot.path.read_bytes() == CONTENT
        assert snapshot.metadata == make_metadata()
        assert read_metadata(snapshot.path) == make_metadata()
        assert not snapshot.path.with_name("units.csv.tmp").exists()
        assert store.get("example", "2025", "units.csv") == snapshot

    def test_put_rejects_pinned_checksum_mismatch(self, tmp_path):
        store = SnapshotStore(tmp_path)
        spec = make_spec(expected_sha256=sha256_of_bytes(b"something else"))
        with pytest.raises(SnapshotIntegrityError, match="expected checksum"):
            store.put(spec, CONTENT, retrieved_at=RETRIEVED_AT)
        assert store.get("example", "2025", "units.csv") is None

    def test_put_accepts_matching_pinned_checksum(self, tmp_path):
        store = SnapshotStore(tmp_path)
        spec = make_spec(expected_sha256=sha256_of_bytes(CONTENT))
        snapshot = store.put(spec, CONTENT, retrieved_at=RETRIEVED_AT)
        assert snapshot.metadata.sha256 == sha256_of_bytes(CONTENT)


class TestFetch:
    @pytest.mark.asyncio
    async def test_fetch_downloads_and_records_metadata(self, respx_mock, tmp_path):
        route = respx_mock.get(URL).mock(
            return_value=httpx.Response(200, content=CONTENT)
        )
        store = SnapshotStore(tmp_path)
        async with AsyncDownloader() as downloader:
            snapshot = await store.fetch(
                make_spec(), downloader, retrieved_at=RETRIEVED_AT
            )

        assert route.call_count == 1
        assert snapshot.path.read_bytes() == CONTENT
        assert snapshot.metadata == make_metadata()
        assert sidecar_path(snapshot.path).is_file()

    @pytest.mark.asyncio
    async def test_second_fetch_uses_cache(self, respx_mock, tmp_path):
        route = respx_mock.get(URL).mock(
            return_value=httpx.Response(200, content=CONTENT)
        )
        store = SnapshotStore(tmp_path)
        later = datetime(2026, 9, 19, tzinfo=timezone.utc)
        async with AsyncDownloader() as downloader:
            first = await store.fetch(
                make_spec(), downloader, retrieved_at=RETRIEVED_AT
            )
            second = await store.fetch(make_spec(), downloader, retrieved_at=later)

        assert route.call_count == 1
        assert second == first
        assert second.metadata.retrieved_at == RETRIEVED_AT

    @pytest.mark.asyncio
    async def test_refresh_downloads_again(self, respx_mock, tmp_path):
        route = respx_mock.get(URL).mock(
            return_value=httpx.Response(200, content=CONTENT)
        )
        store = SnapshotStore(tmp_path)
        later = datetime(2026, 9, 19, tzinfo=timezone.utc)
        async with AsyncDownloader() as downloader:
            await store.fetch(make_spec(), downloader, retrieved_at=RETRIEVED_AT)
            refreshed = await store.fetch(
                make_spec(), downloader, retrieved_at=later, refresh=True
            )

        assert route.call_count == 2
        assert refreshed.metadata.retrieved_at == later

    @pytest.mark.asyncio
    async def test_corrupt_cache_is_replaced(self, respx_mock, tmp_path):
        route = respx_mock.get(URL).mock(
            return_value=httpx.Response(200, content=CONTENT)
        )
        store = SnapshotStore(tmp_path)
        cached = store.put(make_spec(), CONTENT, retrieved_at=RETRIEVED_AT)
        cached.path.write_bytes(b"corrupted")
        later = datetime(2026, 9, 19, tzinfo=timezone.utc)

        async with AsyncDownloader() as downloader:
            snapshot = await store.fetch(make_spec(), downloader, retrieved_at=later)

        assert route.call_count == 1
        assert snapshot.path.read_bytes() == CONTENT
        assert snapshot.metadata.retrieved_at == later

    @pytest.mark.asyncio
    async def test_pinned_checksum_mismatch_writes_nothing(self, respx_mock, tmp_path):
        respx_mock.get(URL).mock(return_value=httpx.Response(200, content=CONTENT))
        store = SnapshotStore(tmp_path)
        spec = make_spec(expected_sha256="0" * 64)
        async with AsyncDownloader() as downloader:
            with pytest.raises(SnapshotIntegrityError):
                await store.fetch(spec, downloader, retrieved_at=RETRIEVED_AT)
        assert store.get("example", "2025", "units.csv") is None

    @pytest.mark.asyncio
    async def test_html_body_is_rejected(self, respx_mock, tmp_path):
        respx_mock.get(URL).mock(
            return_value=httpx.Response(
                200,
                content=b"<!doctype html><html>",
                headers={"content-type": "text/html"},
            )
        )
        store = SnapshotStore(tmp_path)
        async with AsyncDownloader() as downloader:
            with pytest.raises(Exception, match="HTML"):
                await store.fetch(make_spec(), downloader, retrieved_at=RETRIEVED_AT)
        assert store.get("example", "2025", "units.csv") is None

    @pytest.mark.asyncio
    async def test_naive_retrieved_at_rejected_before_network(
        self, respx_mock, tmp_path
    ):
        route = respx_mock.get(URL).mock(
            return_value=httpx.Response(200, content=CONTENT)
        )
        store = SnapshotStore(tmp_path)
        async with AsyncDownloader() as downloader:
            with pytest.raises(ValueError, match="retrieved_at"):
                await store.fetch(
                    make_spec(), downloader, retrieved_at=datetime(2026, 9, 18)
                )
        assert route.call_count == 0
