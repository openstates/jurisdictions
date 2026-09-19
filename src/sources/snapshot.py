"""
Cached bulk snapshots of external source files.

A snapshot is one downloaded file plus a JSON sidecar describing where it
came from and what was received. The four concerns are kept apart:

- fetch: bytes come from ``AsyncDownloader``; nothing else in this module
  touches the network.
- verify: the bytes on disk must match the SHA-256 and size recorded in the
  sidecar (and, when the caller knows it in advance, an expected SHA-256).
- cache: files live under ``<root>/<source>/<release>/<filename>`` with the
  sidecar at ``<filename>.meta.json`` beside them. A verified cached file is
  never re-fetched unless the caller asks for a refresh.
- parse: adapters open the snapshot's bytes; this module knows nothing about
  file formats.

Every timestamp is supplied by the caller. This module never reads the
clock, so identical inputs produce identical sidecars.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from logging import getLogger
from pathlib import Path

from src.errors import SnapshotIntegrityError, SnapshotMetadataError
from src.init_migration.downloader import AsyncDownloader
from src.models.source import SourceObj, SourceType

logger = getLogger(__name__)

DEFAULT_ROOT = Path("data/raw")
SIDECAR_SUFFIX = ".meta.json"


def sha256_of_bytes(content: bytes) -> str:
    """Hex SHA-256 of ``content``."""
    return hashlib.sha256(content).hexdigest()


def sha256_of_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """Hex SHA-256 of the file at ``path``, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sidecar_path(path: Path) -> Path:
    """Path of the metadata sidecar that sits next to ``path``."""
    return path.with_name(path.name + SIDECAR_SUFFIX)


def _require_aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value


@dataclass(frozen=True, slots=True)
class SnapshotSpec:
    """What to fetch and where it belongs in the cache.

    ``source`` is the cache directory key (``census_governments``, ``tiger``,
    ``ocd_master``). ``source_name`` and ``dataset`` are the provider and
    product names carried into ``SourceObj``. ``release`` is the provider's
    own release, vintage, or version label. ``expected_sha256`` pins the
    content when the caller already knows what it should receive.
    """

    source: str
    source_name: str
    dataset: str
    release: str
    filename: str
    url: str
    publication_date: datetime | None = None
    expected_sha256: str | None = None

    def __post_init__(self) -> None:
        for name in ("source", "source_name", "dataset", "release", "filename"):
            if not getattr(self, name):
                raise ValueError(f"{name} must not be empty")
        if Path(self.filename).name != self.filename:
            raise ValueError("filename must be a bare file name")
        if self.publication_date is not None:
            _require_aware(self.publication_date, "publication_date")


@dataclass(frozen=True, slots=True)
class SnapshotMetadata:
    """The sidecar record: provenance and integrity facts for one file."""

    source: str
    source_name: str
    dataset: str
    release: str
    filename: str
    url: str
    sha256: str
    size_bytes: int
    retrieved_at: datetime
    publication_date: datetime | None = None

    def __post_init__(self) -> None:
        _require_aware(self.retrieved_at, "retrieved_at")
        if self.publication_date is not None:
            _require_aware(self.publication_date, "publication_date")

    def to_json(self) -> str:
        """Serialize deterministically: sorted keys, ISO 8601 timestamps."""
        record = asdict(self)
        record["retrieved_at"] = self.retrieved_at.isoformat()
        record["publication_date"] = (
            self.publication_date.isoformat() if self.publication_date else None
        )
        return json.dumps(record, indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_json(cls, text: str) -> SnapshotMetadata:
        try:
            record = json.loads(text)
        except json.JSONDecodeError as error:
            raise SnapshotMetadataError(
                f"snapshot metadata is not valid JSON: {error}"
            ) from error
        if not isinstance(record, dict):
            raise SnapshotMetadataError("snapshot metadata must be a JSON object")
        try:
            retrieved_at = datetime.fromisoformat(record["retrieved_at"])
            publication_raw = record.get("publication_date")
            publication_date = (
                datetime.fromisoformat(publication_raw) if publication_raw else None
            )
            return cls(
                source=record["source"],
                source_name=record["source_name"],
                dataset=record["dataset"],
                release=record["release"],
                filename=record["filename"],
                url=record["url"],
                sha256=record["sha256"],
                size_bytes=int(record["size_bytes"]),
                retrieved_at=retrieved_at,
                publication_date=publication_date,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise SnapshotMetadataError(
                f"snapshot metadata is missing or malformed: {error}"
            ) from error


@dataclass(frozen=True, slots=True)
class Snapshot:
    """A cached file together with its metadata."""

    path: Path
    metadata: SnapshotMetadata

    def read_bytes(self) -> bytes:
        return self.path.read_bytes()

    def read_text(self, encoding: str = "utf-8") -> str:
        return self.path.read_text(encoding=encoding)


def read_metadata(path: Path) -> SnapshotMetadata:
    """Read the sidecar for the file at ``path``."""
    sidecar = sidecar_path(path)
    if not sidecar.is_file():
        raise SnapshotMetadataError(
            "snapshot metadata sidecar not found", path=str(sidecar)
        )
    metadata = SnapshotMetadata.from_json(sidecar.read_text(encoding="utf-8"))
    if metadata.filename != path.name:
        raise SnapshotMetadataError(
            "snapshot metadata describes a different file", path=str(sidecar)
        )
    return metadata


def write_metadata(path: Path, metadata: SnapshotMetadata) -> Path:
    """Write the sidecar for the file at ``path`` and return its location."""
    sidecar = sidecar_path(path)
    sidecar.write_text(metadata.to_json(), encoding="utf-8")
    return sidecar


def verify_snapshot(snapshot: Snapshot) -> None:
    """Raise unless the file's size and SHA-256 match its metadata."""
    if not snapshot.path.is_file():
        raise SnapshotIntegrityError("snapshot file not found", path=str(snapshot.path))
    actual_size = snapshot.path.stat().st_size
    if actual_size != snapshot.metadata.size_bytes:
        raise SnapshotIntegrityError(
            "snapshot size does not match metadata",
            path=str(snapshot.path),
            expected=str(snapshot.metadata.size_bytes),
            actual=str(actual_size),
        )
    actual_sha = sha256_of_file(snapshot.path)
    if actual_sha != snapshot.metadata.sha256:
        raise SnapshotIntegrityError(
            "snapshot checksum does not match metadata",
            path=str(snapshot.path),
            expected=snapshot.metadata.sha256,
            actual=actual_sha,
        )


def load_snapshot(path: Path, *, verify: bool = True) -> Snapshot:
    """Open an existing file with its sidecar, verifying integrity by default.

    This is how fixtures and previously cached files are used offline.
    """
    path = Path(path)
    snapshot = Snapshot(path=path, metadata=read_metadata(path))
    if verify:
        verify_snapshot(snapshot)
    return snapshot


def source_obj_from_snapshot(
    metadata: SnapshotMetadata,
    *,
    field: list[str],
    source_type: SourceType = SourceType.SCRAPED,
    source_description: str | None = None,
) -> SourceObj:
    """Build the provenance record for data taken from a snapshot.

    ``release`` is the provider's release label, ``publication_date`` is
    when the provider published it, and ``retrieval_date`` is when this
    pipeline fetched it. None of these describes real-world validity.
    """
    return SourceObj(
        field=list(field),
        source_name=metadata.source_name,
        source_type=source_type,
        source_url=metadata.url,
        source_description=source_description,
        dataset=metadata.dataset,
        release=metadata.release,
        publication_date=metadata.publication_date,
        retrieval_date=metadata.retrieved_at,
    )


class SnapshotStore:
    """The on-disk cache: ``<root>/<source>/<release>/<filename>``."""

    def __init__(self, root: Path = DEFAULT_ROOT) -> None:
        self.root = Path(root)

    def path_for(self, source: str, release: str, filename: str) -> Path:
        return self.root / source / release / filename

    def get(self, source: str, release: str, filename: str) -> Snapshot | None:
        """Return the cached snapshot if both file and sidecar exist."""
        path = self.path_for(source, release, filename)
        if not path.is_file() or not sidecar_path(path).is_file():
            return None
        return Snapshot(path=path, metadata=read_metadata(path))

    def put(
        self,
        spec: SnapshotSpec,
        content: bytes,
        *,
        retrieved_at: datetime,
    ) -> Snapshot:
        """Write ``content`` and its sidecar for ``spec``; verify first if pinned."""
        digest = sha256_of_bytes(content)
        if spec.expected_sha256 and digest != spec.expected_sha256:
            raise SnapshotIntegrityError(
                "downloaded content does not match expected checksum",
                path=spec.url,
                expected=spec.expected_sha256,
                actual=digest,
            )
        metadata = SnapshotMetadata(
            source=spec.source,
            source_name=spec.source_name,
            dataset=spec.dataset,
            release=spec.release,
            filename=spec.filename,
            url=spec.url,
            sha256=digest,
            size_bytes=len(content),
            retrieved_at=retrieved_at,
            publication_date=spec.publication_date,
        )
        path = self.path_for(spec.source, spec.release, spec.filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(path.name + ".tmp")
        tmp_path.write_bytes(content)
        os.replace(tmp_path, path)
        write_metadata(path, metadata)
        logger.info(
            "snapshot stored",
            extra={
                "source": spec.source,
                "release": spec.release,
                "snapshot_file": spec.filename,
                "size_bytes": len(content),
                "sha256": digest,
            },
        )
        return Snapshot(path=path, metadata=metadata)

    async def fetch(
        self,
        spec: SnapshotSpec,
        downloader: AsyncDownloader,
        *,
        retrieved_at: datetime,
        refresh: bool = False,
    ) -> Snapshot:
        """Return the verified cached snapshot, downloading only when needed.

        A cached file that fails verification is replaced. ``refresh``
        forces a download even when the cache is intact. The download
        bypasses the downloader's conditional-request cache because a cache
        miss here means the bytes are needed regardless of server validators.
        """
        _require_aware(retrieved_at, "retrieved_at")
        cached = self.get(spec.source, spec.release, spec.filename)
        if cached is not None and not refresh:
            try:
                verify_snapshot(cached)
            except SnapshotIntegrityError as error:
                logger.warning(
                    "cached snapshot failed verification; refetching",
                    extra={
                        "path": error.path,
                        "expected": error.expected,
                        "actual": error.actual,
                    },
                )
            else:
                logger.info(
                    "snapshot cache hit",
                    extra={
                        "source": spec.source,
                        "release": spec.release,
                        "snapshot_file": spec.filename,
                    },
                )
                return cached

        content = await downloader.fetch_bytes(spec.url, force=True)
        if content is None:
            raise SnapshotIntegrityError("download returned no content", path=spec.url)
        return self.put(spec, content, retrieved_at=retrieved_at)
