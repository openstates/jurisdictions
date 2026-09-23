"""Tests for merging the Census of Governments benchmark with an annual listing."""

import csv
import io
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.sources import census_governments, census_gus
from src.sources.government_units import (
    CensusGovernmentRecord,
    GovernmentKind,
    ParseResult,
)
from src.sources.government_units_merge import (
    CHANGE_COLUMNS,
    COMPARED_FIELDS,
    MERGED_COLUMNS,
    ONE_SIDED_FIELDS,
    FieldChange,
    MergeStatus,
    diff_records,
    export_merge,
    merge,
    merge_records,
)
from src.sources.snapshot import SnapshotMetadata, load_snapshot, read_metadata

BENCHMARK = Path("tests/fixtures/census_governments")
ANNUAL = Path("tests/fixtures/census_gus")
SHEETS = [
    ("general_purpose", GovernmentKind.GENERAL_PURPOSE),
    ("special_district", GovernmentKind.SPECIAL_DISTRICT),
    ("school_district", GovernmentKind.SCHOOL_DISTRICT),
    ("dependent_school_system", GovernmentKind.DEPENDENT_SCHOOL_SYSTEM),
]


def load_benchmark() -> ParseResult:
    result = ParseResult()
    for sheet, kind in SHEETS:
        part = census_governments.parse_sheet_snapshot(
            load_snapshot(BENCHMARK / f"govt_units_2022_{sheet}.csv"), kind
        )
        result.extend(part)
        result.metadata = part.metadata
    return result


def load_annual(include_pensions: bool = True) -> ParseResult:
    result = ParseResult()
    sheets = SHEETS + (
        [("public_pension_system", GovernmentKind.PUBLIC_PENSION_SYSTEM)]
        if include_pensions
        else []
    )
    for sheet, kind in sheets:
        part = census_gus.parse_sheet_snapshot(
            load_snapshot(ANNUAL / f"gov_units_2026_{sheet}.csv"), kind
        )
        result.extend(part)
        result.metadata = part.metadata
    return result


def make_record(census_id: str = "161205", **overrides) -> CensusGovernmentRecord:
    values = dict(
        census_id=census_id,
        name="CITY OF SAUSALITO",
        kind=GovernmentKind.GENERAL_PURPOSE,
        state="CA",
        fips_state="06",
        is_active=True,
        unit_type="2 - MUNICIPAL",
        fips_county="041",
        fips_place="70364",
        county_area_name="MARIN",
        web_address="http://www.ci.sausalito.ca.us",
        population=7199,
        population_year=2021,
    )
    values.update(overrides)
    return CensusGovernmentRecord(**values)


def metadata(source: str, release: str, day: int) -> SnapshotMetadata:
    return SnapshotMetadata(
        source=source,
        source_name="U.S. Census Bureau",
        dataset=f"{source} listing",
        release=release,
        filename=f"{source}_{release}.zip",
        url=f"https://example.com/{source}/{release}.zip",
        sha256="a" * 64,
        size_bytes=1,
        retrieved_at=datetime(2026, 9, day, tzinfo=timezone.utc),
        publication_date=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )


def result_of(records, source: str, release: str, day: int) -> ParseResult:
    return ParseResult(records=list(records), metadata=metadata(source, release, day))


class TestFieldComparison:
    def test_compared_fields_exclude_one_sided_and_id(self):
        assert "census_id" not in COMPARED_FIELDS
        assert not ONE_SIDED_FIELDS & set(COMPARED_FIELDS)
        assert ONE_SIDED_FIELDS == {
            "legacy_id",
            "political_code",
            "parent_census_id",
            "parent_name",
        }
        assert "population" in COMPARED_FIELDS and "unit_type" in COMPARED_FIELDS

    def test_identical_records_have_no_changes(self):
        assert diff_records(make_record(), make_record()) == ()

    def test_value_change_and_fill_are_distinguished(self):
        old = make_record(unit_type=None)
        new = make_record(population=7075, unit_type="2 - MUNICIPAL")
        changes = diff_records(old, new)
        assert changes == (
            FieldChange("161205", "unit_type", "", "2 - MUNICIPAL", filled=True),
            FieldChange("161205", "population", "7199", "7075", filled=False),
        )

    def test_one_sided_fields_are_not_compared(self):
        old = make_record(legacy_id="05202100900000")
        new = make_record(political_code="CITY", parent_census_id="100630")
        assert diff_records(old, new) == ()

    def test_boolean_and_kind_render_as_text(self):
        changes = diff_records(make_record(), make_record(is_active=False))
        assert changes[0].benchmark_value == "Y" and changes[0].annual_value == "N"

    def test_merge_records_carries_benchmark_legacy_id(self):
        old = make_record(legacy_id="05202100900000")
        new = make_record(population=7075, political_code="CITY")
        merged = merge_records(old, new)
        assert merged.population == 7075
        assert merged.political_code == "CITY"
        assert merged.legacy_id == "05202100900000"
        assert merge_records(make_record(), new) is new


class TestSyntheticMerge:
    def test_statuses(self):
        benchmark = result_of(
            [
                make_record("100001"),
                make_record("100002", legacy_id="x", unit_type=None),
                make_record("100003", population=1),
                make_record("100004"),
            ],
            "census_governments",
            "2022",
            1,
        )
        annual = result_of(
            [
                make_record("100001"),
                make_record("100002", unit_type="2 - MUNICIPAL"),
                make_record("100003", population=2),
                make_record("100005"),
                make_record(
                    "900001",
                    kind=GovernmentKind.PUBLIC_PENSION_SYSTEM,
                    name="PENSION",
                    parent_census_id="100001",
                ),
            ],
            "census_gus",
            "2026",
            2,
        )
        result = merge(benchmark, annual)

        statuses = {m.record.census_id: m.status for m in result.records}
        assert statuses == {
            "100001": MergeStatus.UNCHANGED,
            "100002": MergeStatus.FILLED,
            "100003": MergeStatus.CHANGED,
            "100004": MergeStatus.REMOVED,
            "100005": MergeStatus.ADDED,
        }
        assert [m.record.census_id for m in result.records] == sorted(statuses)
        assert result.counts() == {
            "unchanged": 1,
            "filled": 1,
            "changed": 1,
            "added": 1,
            "removed": 1,
        }
        assert "900001" not in statuses

    def test_removed_record_is_kept_with_benchmark_values(self):
        benchmark = result_of([make_record("100004", population=42)], "b", "2022", 1)
        annual = result_of([], "a", "2026", 2)
        [removed] = merge(benchmark, annual).records
        assert removed.status is MergeStatus.REMOVED
        assert removed.record.population == 42
        assert removed.changes == ()

    def test_merged_record_takes_annual_values_and_keeps_legacy_id(self):
        benchmark = result_of([make_record(legacy_id="L")], "b", "2022", 1)
        annual = result_of([make_record(population=7075)], "a", "2026", 2)
        [merged] = merge(benchmark, annual).records
        assert merged.record.population == 7075
        assert merged.record.legacy_id == "L"
        assert [c.field for c in merged.changes] == ["population"]

    def test_metadata_required(self):
        with pytest.raises(ValueError, match="metadata"):
            merge(ParseResult(), result_of([], "a", "2026", 2))


class TestFixtureMerge:
    @pytest.fixture(scope="class")
    def result(self):
        return merge(load_benchmark(), load_annual())

    def test_same_universe_no_additions_or_removals(self, result):
        assert len(result.records) == 17
        assert result.counts()["added"] == 0
        assert result.counts()["removed"] == 0
        assert result.counts()["unchanged"] == 0
        assert all(
            m.record.kind is not GovernmentKind.PUBLIC_PENSION_SYSTEM
            for m in result.records
        )

    def test_general_purpose_populations_changed(self, result):
        by_id = {m.record.census_id: m for m in result.records}
        sausalito = by_id["161205"]
        assert sausalito.status is MergeStatus.CHANGED
        assert sausalito.record.population == 7075
        assert sausalito.record.population_year == 2024
        assert sausalito.record.legacy_id == "05202100900000"
        assert sausalito.record.political_code == "CITY"
        assert {
            (c.field, c.benchmark_value, c.annual_value) for c in sausalito.changes
        } == {
            ("population", "7199", "7075"),
            ("population_year", "2021", "2024"),
        }

    def test_special_district_only_filled(self, result):
        by_id = {m.record.census_id: m for m in result.records}
        marin_city = by_id["205945"]
        assert marin_city.status is MergeStatus.FILLED
        assert [(c.field, c.annual_value) for c in marin_city.changes] == [
            ("unit_type", "4 - SPECIAL DISTRICT")
        ]

    def test_dependent_school_gets_parent_and_enrollment_change(self, result):
        by_id = {m.record.census_id: m for m in result.records}
        dcps = by_id["101868"]
        assert dcps.status is MergeStatus.CHANGED
        assert dcps.record.parent_census_id == "124214"
        fields = {c.field for c in dcps.changes}
        assert {"school_enrollment", "enrollment_year"} <= fields
        assert "parent_census_id" not in fields

    def test_every_change_names_a_compared_field(self, result):
        assert result.changes()
        assert all(c.field in COMPARED_FIELDS for c in result.changes())


class TestExport:
    def test_export_writes_both_files_with_sidecars(self, tmp_path):
        result = merge(load_benchmark(), load_annual())
        merged, changes = export_merge(result, cache_root=tmp_path)

        directory = tmp_path / "government_units" / "2022-2026"
        assert merged.path == directory / "merged_governments.csv"
        assert changes.path == directory / "government_changes.csv"

        rows = list(csv.DictReader(io.StringIO(merged.path.read_text())))
        assert list(rows[0]) == list(MERGED_COLUMNS)
        assert len(rows) == 17
        assert [r["census_id"] for r in rows] == sorted(r["census_id"] for r in rows)
        sausalito = next(r for r in rows if r["census_id"] == "161205")
        assert sausalito["merge_status"] == "changed"
        assert sausalito["population"] == "7075"
        assert sausalito["legacy_id"] == "05202100900000"
        assert (sausalito["benchmark_release"], sausalito["annual_release"]) == (
            "2022",
            "2026",
        )

        change_rows = list(csv.DictReader(io.StringIO(changes.path.read_text())))
        assert list(change_rows[0]) == list(CHANGE_COLUMNS)
        assert {"161205", "205945"} <= {r["census_id"] for r in change_rows}
        marin = next(r for r in change_rows if r["census_id"] == "205945")
        assert marin == {
            "census_id": "205945",
            "field": "unit_type",
            "benchmark_value": "",
            "annual_value": "4 - SPECIAL DISTRICT",
            "filled": "Y",
        }

        for snapshot in (merged, changes):
            metadata = read_metadata(snapshot.path)
            assert metadata == snapshot.metadata
            assert metadata.source == "government_units"
            assert metadata.release == "2022-2026"
            assert metadata.url == result.annual.url
            assert metadata.retrieved_at == max(
                result.benchmark.retrieved_at, result.annual.retrieved_at
            )
            assert result.benchmark.sha256 in metadata.dataset
            assert result.annual.sha256 in metadata.dataset
            assert metadata.size_bytes == snapshot.path.stat().st_size
            assert load_snapshot(snapshot.path) == snapshot

    def test_export_is_deterministic(self, tmp_path):
        first, _ = export_merge(
            merge(load_benchmark(), load_annual()), cache_root=tmp_path / "a"
        )
        second, _ = export_merge(
            merge(load_benchmark(), load_annual()), cache_root=tmp_path / "b"
        )
        assert first.path.read_bytes() == second.path.read_bytes()
        assert first.metadata.sha256 == second.metadata.sha256

    def test_removed_record_appears_in_merged_output(self, tmp_path):
        benchmark = result_of([make_record("100004")], "census_governments", "2022", 1)
        annual = result_of([], "census_gus", "2026", 2)
        merged, changes = export_merge(merge(benchmark, annual), cache_root=tmp_path)
        rows = list(csv.DictReader(io.StringIO(merged.path.read_text())))
        assert [(r["census_id"], r["merge_status"]) for r in rows] == [
            ("100004", "removed")
        ]
        assert changes.path.read_text().splitlines() == [",".join(CHANGE_COLUMNS)]
