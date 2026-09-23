"""
Minimal reader for dBASE III/IV attribute tables (the ``.dbf`` in a shapefile).

TIGER/Line attribute tables use only character and numeric fields, which
this reader returns as stripped strings so leading zeros in identifiers
survive. Deleted records are skipped. No geometry is read.
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass

FIELD_TERMINATOR = 0x0D
DELETED_FLAG = b"*"


@dataclass(frozen=True, slots=True)
class DbfField:
    name: str
    type: str
    length: int


def dbf_fields(data: bytes) -> list[DbfField]:
    """Field descriptors from the table header."""
    fields: list[DbfField] = []
    pos = 32
    while pos < len(data) and data[pos] != FIELD_TERMINATOR:
        descriptor = data[pos : pos + 32]
        if len(descriptor) < 32:
            raise ValueError("truncated dbf field descriptor")
        name = descriptor[:11].split(b"\x00", 1)[0].decode("ascii")
        fields.append(
            DbfField(name=name, type=chr(descriptor[11]), length=descriptor[16])
        )
        pos += 32
    return fields


def read_dbf(data: bytes, encoding: str = "latin-1") -> Iterator[dict[str, str]]:
    """Yield each live record as ``{field: stripped text}`` in file order."""
    if len(data) < 32:
        raise ValueError("dbf header too short")
    record_count = struct.unpack("<I", data[4:8])[0]
    header_length = struct.unpack("<H", data[8:10])[0]
    record_length = struct.unpack("<H", data[10:12])[0]
    fields = dbf_fields(data)
    if 1 + sum(field.length for field in fields) != record_length:
        raise ValueError("dbf field lengths do not add up to the record length")
    pos = header_length
    for _ in range(record_count):
        record = data[pos : pos + record_length]
        pos += record_length
        if len(record) < record_length:
            raise ValueError("dbf record truncated")
        if record[:1] == DELETED_FLAG:
            continue
        row: dict[str, str] = {}
        offset = 1
        for field in fields:
            raw = record[offset : offset + field.length]
            offset += field.length
            row[field.name] = raw.decode(encoding).strip()
        yield row
