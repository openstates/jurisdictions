from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from src.models.division import Division
from src.models.jurisdiction import Jurisdiction


@dataclass
class RunResult:
    division_paths: list[Path] = field(default_factory=list)
    jurisdiction_paths: list[Path] = field(default_factory=list)

    @property
    def division_count(self) -> int:
        return len(self.division_paths)

    @property
    def jurisdiction_count(self) -> int:
        return len(self.jurisdiction_paths)


class GoldenRunner(Protocol):
    def run(self, output_dir: Path) -> RunResult: ...


class FixtureRunner:
    """Initial GoldenRunner: dumps injected model records into a temp dir."""

    def __init__(
        self, divisions: list[Division], jurisdictions: list[Jurisdiction]
    ) -> None:
        self._divisions = divisions
        self._jurisdictions = jurisdictions

    def run(self, output_dir: Path) -> RunResult:
        output_dir = Path(output_dir)
        div_dir = output_dir / "divisions"
        jur_dir = output_dir / "jurisdictions"
        result = RunResult()
        for division in self._divisions:
            result.division_paths.append(division.dump_division(base_dir=div_dir))
        for jurisdiction in self._jurisdictions:
            result.jurisdiction_paths.append(
                jurisdiction.dump_jurisdiction(base_dir=jur_dir)
            )
        return result
