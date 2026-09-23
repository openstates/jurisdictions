"""Fixtures shared by the source-layer tests."""

import struct

import pytest


def _build_dbf(fields: list[tuple[str, int]], rows: list[list[str]]) -> bytes:
    """A dBASE III table with character fields only, as TIGER/Line ships."""
    record_length = 1 + sum(length for _, length in fields)
    header_length = 32 + 32 * len(fields) + 1
    header = bytearray(32)
    header[0] = 0x03
    header[1:4] = bytes([124, 1, 1])
    header[4:8] = struct.pack("<I", len(rows))
    header[8:10] = struct.pack("<H", header_length)
    header[10:12] = struct.pack("<H", record_length)
    out = bytearray(header)
    for name, length in fields:
        descriptor = bytearray(32)
        descriptor[:11] = name.encode("ascii").ljust(11, b"\x00")
        descriptor[11] = ord("C")
        descriptor[16] = length
        out += descriptor
    out += b"\x0d"
    for row in rows:
        deleted = row[0] == "*deleted*"
        out += b"*" if deleted else b" "
        values = row[1:] if deleted else row
        for (_, length), value in zip(fields, values):
            out += value.encode("latin-1").ljust(length)[:length]
    out += b"\x1a"
    return bytes(out)


@pytest.fixture
def build_dbf():
    return _build_dbf
