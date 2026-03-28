"""
YamlManager: CRUDL operations for YAML files.

Provides file I/O, serialization (YAML to JSON/dict), Pydantic model validation,
and filesystem operations for Division and Jurisdiction YAML files.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterator

import yaml

from src.models.division import Division
from src.models.jurisdiction import Jurisdiction

logger = logging.getLogger(__name__)


class YamlManager:
    """
    CRUDL manager for YAML files with Pydantic model support.

    Attributes:
        base_path: Optional base path prepended to relative file paths.
    """

    def __init__(self, base_path: str | Path | None = None):
        """
        Initialize the YamlManager.

        Args:
            base_path: Optional base path to prepend to relative file paths.

        Raises:
            ValueError: If base_path is None.
            FileNotFoundError: If base_path does not exist.
            NotADirectoryError: If base_path is not a directory.
        """
        self.base_path = Path(base_path) if base_path else None
        if not self.base_path:
            logger.exception("Initialized YamlManager with no base path.", extra={"base_path": base_path})
            raise ValueError("Base path must be provided for YamlManager.")

        if not self.base_path.exists():
            logger.error("Base path does not exist.", extra={"base_path": str(self.base_path)})
            raise FileNotFoundError(f"Base path does not exist: {self.base_path}")

        if not self.base_path.is_dir():
            logger.error("Base path is not a directory.", extra={"base_path": str(self.base_path)})
            raise NotADirectoryError(f"Base path is not a directory: {self.base_path}")

    def _resolve_path(self, path: str | Path) -> Path:
        """Resolve a path, prepending base_path if set."""
        p = Path(path)
        if self.base_path and not p.is_absolute():
            return self.base_path / p
        return p

    def create(self, filepath: str | Path, data: dict[str, Any]) -> Path:
        """
        Create a new YAML file.

        Args:
            filepath: Path where the file should be written.
            data: Dictionary to serialize as YAML.

        Returns:
            The Path to the written file.

        Raises:
            FileExistsError: If the file already exists.
            ValueError: If data is not a dict.
        """
        if not isinstance(data, dict):
            raise ValueError("Data must be a dictionary")

        path = self._resolve_path(filepath)

        if path.exists():
            raise FileExistsError(f"File already exists: {path}")

        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)

        logger.info(f"Created YAML file: {path}")
        return path

    def read(self, filepath: str | Path) -> dict[str, Any]:
        """
        Read a YAML file and return its contents as a dict.

        Args:
            filepath: Path to the YAML file.

        Returns:
            The parsed YAML as a dict. Returns empty dict for empty files.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If YAML is not a mapping (dict) at top level.
        """
        path = self._resolve_path(filepath)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if data is None:
            return {}

        if not isinstance(data, dict):
            raise ValueError(f"Expected YAML mapping at top level, got {type(data).__name__}")

        return data

    def update(
        self,
        filepath: str | Path,
        data: dict[str, Any],
        merge: bool = False
    ) -> dict[str, Any]:
        """
        Update an existing YAML file. If using "merge", be sure to create a deep
        copy of the original data if you want to preserve it, as this method will modify the original dict in place.

        Args:
            filepath: Path to the file to update.
            data: Dictionary with updates.
            merge: If True, merge with existing data. If False, replace entirely. Default False.

        Returns:
            The updated data.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        path = self._resolve_path(filepath)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if merge:
            existing = self.read(filepath)
            existing.update(data)
            result = existing
        else:
            result = data

        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(result, f, sort_keys=False, allow_unicode=True)

        logger.info(f"Updated YAML file: {path}")
        return result

    def delete(self, filepath: str | Path, confirm: bool = False) -> bool:
        """
        Delete a YAML file.

        Args:
            filepath: Path to the file to delete.
            confirm: If True, prompt for user confirmation before deleting.

        Returns:
            True if file was deleted, False if user declined deletion.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        path = self._resolve_path(filepath)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if confirm:
            response = input(f"Delete {path}? (y/n): ").strip().lower()
            if response not in ('y', 'yes'):
                logger.info("Deletion cancelled by user.", extra={"path": str(path)})
                return False

        path.unlink()
        logger.info(f"Deleted file: {path}")
        return True

    def list_files(
        self,
        directory: str | Path,
        pattern: str = "*.yaml",
        recursive: bool = False
    ) -> list[Path]:
        """
        List YAML files in a directory.

        Args:
            directory: Path to the directory to search.
            pattern: Glob pattern for matching files. Default "*.yaml".
            recursive: If True, search subdirectories. Default False.

        Returns:
            Sorted list of Path objects for matching files.

        Raises:
            FileNotFoundError: If the directory does not exist.
            NotADirectoryError: If the path is not a directory.
        """
        path = self._resolve_path(directory)

        if not path.exists():
            raise FileNotFoundError(f"Directory not found: {path}")

        if not path.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")

        if recursive:
            files = sorted(path.rglob(pattern))
        else:
            files = sorted(path.glob(pattern))

        return files

    # Helper Methods

    def exists(self, filepath: str | Path) -> bool:
        """
        Check if a file exists.

        Args:
            filepath: Path to check.

        Returns:
            True if file exists, False otherwise.
        """
        return self._resolve_path(filepath).exists()

    def count(
        self,
        directory: str | Path,
        pattern: str = "*.yaml",
        recursive: bool = False
    ) -> int:
        """
        Count YAML files in a directory.

        Args:
            directory: Path to the directory.
            pattern: Glob pattern for files.
            recursive: Search subdirectories if True.

        Returns:
            Number of matching files.
        """
        return len(self.list_files(directory, pattern=pattern, recursive=recursive))


    def load_division(self, filepath: str | Path) -> Division:
        """
        Load a YAML file and validate it as a Division model.

        Args:
            filepath: Path to the YAML file.

        Returns:
            Validated Division model instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            pydantic.ValidationError: If YAML does not match Division schema.
        """
        data = self.read(filepath)
        return Division.model_validate(data)

    def load_jurisdiction(self, filepath: str | Path) -> Jurisdiction:
        """
        Load a YAML file and validate it as a Jurisdiction model.

        Args:
            filepath: Path to the YAML file.

        Returns:
            Validated Jurisdiction model instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            pydantic.ValidationError: If YAML does not match Jurisdiction schema.
        """
        data = self.read(filepath)
        return Jurisdiction.model_validate(data)

    def dump_division(
        self,
        filepath: str | Path,
        division: Division,
        overwrite: bool = False
    ) -> Path:
        """
        Serialize a Division model to a YAML file.

        Args:
            filepath: Path where the file should be written.
            division: Division model to serialize.
            overwrite: If True, overwrite existing files.

        Returns:
            The Path to the written file.
        """
        data = division.model_dump(mode="json")
        if overwrite and self.exists(filepath):
            self.update(filepath, data, merge=False)
            return self._resolve_path(filepath)
        return self.create(filepath, data)

    def dump_jurisdiction(
        self,
        filepath: str | Path,
        jurisdiction: Jurisdiction,
        overwrite: bool = False
    ) -> Path:
        """
        Serialize a Jurisdiction model to a YAML file.

        Args:
            filepath: Path where the file should be written.
            jurisdiction: Jurisdiction model to serialize.
            overwrite: If True, overwrite existing files.

        Returns:
            The Path to the written file.
        """
        data = jurisdiction.model_dump(mode="json")
        if overwrite and self.exists(filepath):
            self.update(filepath, data, merge=False)
            return self._resolve_path(filepath)
        return self.create(filepath, data)

    # Batch Operations

    def read_all(self, filepaths: list[str | Path]) -> list[dict[str, Any]]:
        """
        Read multiple YAML files.

        Args:
            filepaths: List of paths to YAML files.

        Returns:
            List of dicts, each with '_source_file' key added.
        """
        results = []
        for fp in filepaths:
            data = self.read(fp)
            data["_source_file"] = str(fp)
            results.append(data)
        return results

    def list_and_load(
        self,
        directory: str | Path,
        pattern: str = "*.yaml",
        recursive: bool = False
    ) -> list[dict[str, Any]]:
        """
        List YAML files in a directory and load them all.

        Args:
            directory: Path to the directory.
            pattern: Glob pattern for files.
            recursive: Search subdirectories if True.

        Returns:
            List of dicts, each with '_source_file' key.
        """
        filepaths = self.list_files(directory, pattern=pattern, recursive=recursive)
        return self.read_all(filepaths)

    def iter_files(
        self,
        directory: str | Path,
        pattern: str = "*.yaml",
        recursive: bool = False
    ) -> Iterator[tuple[Path, dict[str, Any]]]:
        """
        Iterate over YAML files, yielding (path, data) tuples.

        Args:
            directory: Path to the directory.
            pattern: Glob pattern for files.
            recursive: Search subdirectories if True.

        Yields:
            Tuples of (Path, dict) for each file.
        """
        for filepath in self.list_files(directory, pattern=pattern, recursive=recursive):
            data = self.read(filepath)
            yield filepath, data

    def to_json(self, data: dict[str, Any] | list[dict[str, Any]], **kwargs) -> str:
        """
        Convert data to a JSON string.

        Args:
            data: Dictionary or list of dictionaries.
            **kwargs: Additional arguments for json.dumps()
                      (e.g., indent=2 for pretty printing).

        Returns:
            JSON string representation.
        """
        kwargs.setdefault("indent", 2)
        kwargs.setdefault("ensure_ascii", False)
        kwargs.setdefault("default", str)  # Handle datetime, UUID, etc.
        return json.dumps(data, **kwargs)

    def read_as_json(self, filepath: str | Path) -> str:
        """
        Read a YAML file and return it as a JSON string.

        Args:
            filepath: Path to the YAML file.

        Returns:
            JSON string representation of the YAML contents.
        """
        data = self.read(filepath)
        return self.to_json(data)

    def list_and_load_as_json(
        self,
        directory: str | Path,
        pattern: str = "*.yaml",
        recursive: bool = False
    ) -> str:
        """
        List YAML files, load them all, and return as JSON string.

        Args:
            directory: Path to the directory.
            pattern: Glob pattern for files.
            recursive: Search subdirectories if True.

        Returns:
            JSON string representation of all loaded files.
        """
        data = self.list_and_load(directory, pattern=pattern, recursive=recursive)
        return self.to_json(data)
