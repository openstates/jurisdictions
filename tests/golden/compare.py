from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Diff:
    file: str
    path: str
    kind: str
    expected: Any = None
    actual: Any = None


def _yaml_files(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*.yaml")}


def _child(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _compare_values(file: str, path: str, expected: Any, actual: Any) -> list[Diff]:
    if type(expected) is not type(actual):
        return [Diff(file, path, "TYPE_MISMATCH", expected, actual)]
    if isinstance(expected, dict):
        diffs: list[Diff] = []
        for key in expected:
            if key not in actual:
                diffs.append(Diff(file, _child(path, key), "MISSING_KEY", expected[key], None))
            else:
                diffs.extend(_compare_values(file, _child(path, key), expected[key], actual[key]))
        for key in actual:
            if key not in expected:
                diffs.append(Diff(file, _child(path, key), "EXTRA_KEY", None, actual[key]))
        return diffs
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return [Diff(file, path, "VALUE_MISMATCH", expected, actual)]
        diffs = []
        for i, (e, a) in enumerate(zip(expected, actual)):
            diffs.extend(_compare_values(file, f"{path}[{i}]", e, a))
        return diffs
    if expected != actual:
        return [Diff(file, path, "VALUE_MISMATCH", expected, actual)]
    return []


def compare_trees(expected_dir: Path, actual_dir: Path) -> list[Diff]:
    expected_dir, actual_dir = Path(expected_dir), Path(actual_dir)
    expected_files, actual_files = _yaml_files(expected_dir), _yaml_files(actual_dir)
    diffs: list[Diff] = []
    for rel in sorted(expected_files - actual_files):
        diffs.append(Diff(rel, "", "MISSING_FILE"))
    for rel in sorted(actual_files - expected_files):
        diffs.append(Diff(rel, "", "EXTRA_FILE"))
    for rel in sorted(expected_files & actual_files):
        expected_doc = yaml.safe_load((expected_dir / rel).read_text())
        actual_doc = yaml.safe_load((actual_dir / rel).read_text())
        diffs.extend(_compare_values(rel, "", expected_doc, actual_doc))
    return diffs
