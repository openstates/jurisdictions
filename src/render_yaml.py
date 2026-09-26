"""Deterministic YAML rendering for canonical Division and Jurisdiction models.

Rendering is intentionally a terminal stage. It accepts already-constructed
models, performs no resolution or canonicalization, and writes byte-stable YAML
for unchanged model inputs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml
from pydantic import BaseModel

from src.models.division import Division
from src.models.jurisdiction import Jurisdiction
from src.models.ocdid import OCDIdParsed

CanonicalRecord = Division | Jurisdiction


def slugify(name: str) -> str:
    """Return the stable human-readable filename slug."""
    return "_".join(name.strip().lower().split())


def state_segment(ocdid: str) -> str:
    """Return the state/district directory segment for a canonical OCD ID."""
    parsed = OCDIdParsed.parse_ocdid(ocdid)
    state = parsed.state or getattr(parsed, "district", None)
    if not state:
        raise ValueError(f"no state or district segment in {ocdid}")
    return state.lower()


def record_relative_path(
    record: CanonicalRecord,
    *,
    namespace: str | None = None,
) -> Path:
    """Return the deterministic repository-relative path for one record.

    Production:
        divisions/<state>/local/<slug>_<uuid>.yaml
        jurisdictions/<state>/local/<slug>_<uuid>.yaml

    Controlled golden fixtures insert a namespace after the collection:
        divisions/test/<state>/local/<slug>_<uuid>.yaml

    GEOIDs are deliberately absent from filenames because they are external
    identifiers, may be unavailable, and must not participate in stable
    repository identity.
    """
    if isinstance(record, Division):
        kind = "divisions"
        name = record.display_name
    elif isinstance(record, Jurisdiction):
        kind = "jurisdictions"
        name = record.name
    else:
        raise TypeError(f"unsupported canonical record: {type(record).__name__}")

    parts = [kind]
    if namespace is not None:
        if (
            not namespace
            or "/" in namespace
            or "\\" in namespace
            or namespace in {".", ".."}
        ):
            raise ValueError(f"invalid path namespace: {namespace!r}")
        parts.append(namespace)

    parts.extend(
        [
            state_segment(record.ocdid),
            "local",
            f"{slugify(name)}_{record.id}.yaml",
        ]
    )
    return Path(*parts)


def render_yaml(value: BaseModel | Mapping[str, Any]) -> str:
    """Serialize one already-resolved value deterministically."""
    if isinstance(value, BaseModel):
        data = value.model_dump(mode="json", exclude_none=False)
    else:
        data = dict(value)

    return yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )


def write_yaml(path: Path, value: BaseModel | Mapping[str, Any]) -> Path:
    """Write deterministic YAML to an explicit path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_yaml(value), encoding="utf-8")
    return path


def write_yaml_record(
    record: CanonicalRecord,
    root: Path,
    *,
    namespace: str | None = None,
) -> Path:
    """Write one canonical record under ``root`` using the stable path policy."""
    return write_yaml(
        root / record_relative_path(record, namespace=namespace),
        record,
    )
