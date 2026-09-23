"""Tests for the dBASE attribute-table reader."""

import pytest

from src.sources.dbf import DbfField, dbf_fields, read_dbf

FIELDS = [("STATEFP", 2), ("GEOID", 7), ("NAME", 20)]


class TestReadDbf:
    def test_rows_are_stripped_strings_with_leading_zeros(self, build_dbf):
        data = build_dbf(
            FIELDS, [["06", "0670364", "Sausalito"], ["48", "4805000", "Austin"]]
        )
        assert list(read_dbf(data)) == [
            {"STATEFP": "06", "GEOID": "0670364", "NAME": "Sausalito"},
            {"STATEFP": "48", "GEOID": "4805000", "NAME": "Austin"},
        ]

    def test_fields(self, build_dbf):
        data = build_dbf(FIELDS, [])
        assert dbf_fields(data) == [
            DbfField("STATEFP", "C", 2),
            DbfField("GEOID", "C", 7),
            DbfField("NAME", "C", 20),
        ]
        assert list(read_dbf(data)) == []

    def test_deleted_records_are_skipped(self, build_dbf):
        data = build_dbf(
            FIELDS,
            [
                ["06", "0670364", "Sausalito"],
                ["*deleted*", "06", "0645820", "Marin City"],
            ],
        )
        assert [row["GEOID"] for row in read_dbf(data)] == ["0670364"]

    def test_latin1_names(self, build_dbf):
        data = build_dbf(FIELDS, [["72", "7200001", "Añasco"]])
        assert next(read_dbf(data))["NAME"] == "Añasco"

    def test_truncated_record_raises(self, build_dbf):
        data = build_dbf(FIELDS, [["06", "0670364", "Sausalito"]])
        with pytest.raises(ValueError, match="truncated"):
            list(read_dbf(data[:-10]))

    def test_short_header_raises(self):
        with pytest.raises(ValueError, match="header"):
            list(read_dbf(b"\x03"))
