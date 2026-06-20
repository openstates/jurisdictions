"""Generate a JSON lookup table for Census LSAD codes.

Source: U.S. Census Bureau, Legal/Statistical Area Description Codes and Definitions
https://www.census.gov/library/reference/code-lists/legal-status-codes.html

Run:
    python lsad_mapper.py

Output:
    lsad_map.json
"""

from __future__ import annotations

import json
import html
import re
from pathlib import Path
from typing import Optional
import httpx
from pydantic import BaseModel, Field

from logging import getLogger

logger = getLogger(__name__)


OUTPUT_FILENAME = "lsad_map.json"
OUTPUT_FILE_PATH = Path(__file__).parent / OUTPUT_FILENAME
LSAD_SOURCE_URL = (
    "https://www.census.gov/library/reference/code-lists/legal-status-codes.html"
)
LSAD_CODE_PATTERN = re.compile(r"^[0-9A-Z]{2}$")


class LSADCode(BaseModel):
    lsad_description: str = Field(description="Official LSAD description")
    lsad_prefix: Optional[str] = Field(
        default=None, description="Prefix text, if LSAD is prefix-based"
    )
    lsad_suffix: Optional[str] = Field(
        default=None, description="Suffix text, if LSAD is suffix-based"
    )
    associated_geographic_entity: str


def _normalize_column_name(column_name: str) -> str:
    return re.sub(r"\s+", " ", str(column_name)).strip().lower()


def _extract_cell_text(raw_html: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw_html, flags=re.DOTALL))
    return re.sub(r"\s+", " ", text).strip()


def fetch_lsad_rows() -> list[tuple[str, str, str]]:
    """Fetch and parse LSAD rows from the Census source page."""
    response = httpx.get(LSAD_SOURCE_URL, timeout=60.0, follow_redirects=True)
    response.raise_for_status()

    html_text = response.text
    table_match = re.search(
        r"<table[^>]*>(.*?)</table>", html_text, flags=re.IGNORECASE | re.DOTALL
    )
    if not table_match:
        raise ValueError("Could not locate LSAD table on source page")

    table_html = table_match.group(1)
    row_matches = re.findall(
        r"<tr[^>]*>(.*?)</tr>", table_html, flags=re.IGNORECASE | re.DOTALL
    )
    rows: list[tuple[str, str, str]] = []

    for row_html in row_matches:
        cell_matches = re.findall(
            r"<(td|th)[^>]*>(.*?)</\1>",
            row_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if len(cell_matches) < 3:
            continue

        cells = [_extract_cell_text(content) for _, content in cell_matches]

        if (
            _normalize_column_name(cells[0]) == "code"
            and _normalize_column_name(cells[1]) == "description"
        ):
            continue

        code = cells[0].upper()
        description = cells[1]
        entity = cells[2]
        if not code or not LSAD_CODE_PATTERN.fullmatch(code):
            continue
        rows.append((code, description, entity))

    if rows:
        return rows

    raise ValueError("Could not locate LSAD table on source page")


def split_prefix_suffix(description: str) -> tuple[str | None, str | None]:
    if description.endswith(" (prefix)"):
        return description.removesuffix(" (prefix)").lower(), None
    if description.endswith(" (suffix)"):
        return None, description.removesuffix(" (suffix)")
    return None, None


def build_lsad_map() -> dict[str, LSADCode]:
    records: dict[str, LSADCode] = {}
    duplicate_entities: dict[str, list[str]] = {}

    for code, description, entity in fetch_lsad_rows():
        prefix, suffix = split_prefix_suffix(description)
        item = LSADCode(
            lsad_description=description,
            lsad_prefix=prefix,
            lsad_suffix=suffix,
            associated_geographic_entity=entity,
        )

        if code in records:
            # The Census table has repeated code 06 with different descriptions/entities.
            # Preserve both meanings by merging the entity list and keeping the latter
            # general LSAD description as the canonical code-level description.
            old = records[code]
            merged_entities = sorted(
                set(map(str.strip, old.associated_geographic_entity.split(",")))
                | set(map(str.strip, entity.split(",")))
            )
            duplicate_entities.setdefault(code, []).append(old.lsad_description)
            duplicate_entities[code].append(description)
            item.associated_geographic_entity = ", ".join(merged_entities)
        records[code] = item

    if len(records) != 135:
        raise ValueError(f"Expected 135 unique LSAD codes, got {len(records)}")
    return records


def model_dump(model: LSADCode) -> dict[str, str | None]:
    return model.model_dump()


def main() -> dict[str, LSADCode]:
    records = build_lsad_map()
    payload = {code: model_dump(record) for code, record in sorted(records.items())}
    Path(OUTPUT_FILE_PATH).write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    logger.info(f"Wrote {len(payload)} LSAD codes to lsad_map.json")


def get_lsad_map() -> dict[str, LSADCode]:
    if not OUTPUT_FILE_PATH.exists():
        main()
    raw = OUTPUT_FILE_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)
    return {code: LSADCode(**details) for code, details in data.items()}


if __name__ == "__main__":
    main()
