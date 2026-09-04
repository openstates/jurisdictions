# Census Government Units fixtures

`mini_release_2025.json` contains one synthetic row for each of the five tabs
in the 2025 Government Units workbook. Tests construct a minimal XLSX and outer
ZIP from this JSON at runtime, preserving the official sheet names, headers,
and six-character Census identifiers without checking binary office files into
the repository.

The fixture is synthetic. It is intended to exercise source acquisition,
archive verification, cache integrity, raw-row provenance, and structured
errors. It must not be interpreted as factual government data or refreshed
from a live Census endpoint during normal tests.
