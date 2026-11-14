import re
from datetime import datetime
from enum import Enum
from types import NoneType, UnionType
from typing import Annotated, Any, Union, get_args, get_origin
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import (
    BaseModel,
    Field,
    FileUrl,
    FtpUrl,
    HttpUrl,
    RootModel,
    model_validator,
)


class SourceType(str, Enum):
    """How a Source's data was collected."""

    AI = "ai_generated"
    HUMAN = "human_researched"
    SCRAPED = "programmatically_generated"  # For programmatic scapers. Do not use this if an AI agent is handling the scraping.


class Source(BaseModel):
    """Provenance for a dataset or document cited by a record.

    A Source describes *observation time* — when the cited dataset was
    published and when this pipeline retrieved it. It never describes
    real-world validity time; that belongs to the owning record
    (``valid_from`` / ``valid_to`` on Geometry, Division and Jurisdiction).
    Everything here is mutable provenance and does not feed
    entity identity.

    ``node_id`` identifies the source globally, across records, from
    ``SOURCE_IDENTITY_FIELDS``. The observation dates, type, and description
    describe one citation of it, not the source itself.
    """

    source_name: str = Field(
        ...,
        description="The name of the source. I.e. 'ArcGIS', 'Census Bureau', 'City of Seattle Open Data Portal', etc.",
    )
    source_type: SourceType = Field(
        description="How the data was collected: ai_generated, human_researched, or programmatically_generated.",
    )
    source_url: HttpUrl | FtpUrl | FileUrl = Field(
        description="URL of the cited source — http(s), ftp, or file. If AI generated, the source url identified by the AI agent."
    )
    source_description: str | None = Field(
        default=None,
        description="A brief description of how the data was sourced. I.e. ArcGIS library provided by arcgismapper.com",
    )
    dataset: str | None = Field(
        default=None,
        description="The specific dataset or product within the source, e.g. 'TIGER/Line Shapefiles', 'Government Units Survey', 'ocd-division-ids/identifiers/country-us.csv'.",
    )
    release: str | None = Field(
        default=None,
        description="Release, vintage, or version of the dataset in the provider's own terms — a Census vintage ('2020'), a TIGER/Line release ('2024'), a git tag or SHA.",
    )
    publication_date: datetime | None = Field(
        default=None,
        description="When the provider published this release.",
    )
    retrieval_date: datetime | None = Field(
        default=None,
        description="When this pipeline retrieved the data from the source.",
    )

    @property
    def node_id(self) -> UUID:
        """UUID5 of the source's identity fields; stable across records and runs."""
        identity = "|".join(
            str(getattr(self, name) or "") for name in SOURCE_IDENTITY_FIELDS
        )
        return uuid5(NAMESPACE_URL, f"source:{identity}")


#: Fields that identify a Source globally. Observation dates and descriptions
#: vary per citation and are excluded.
SOURCE_IDENTITY_FIELDS = ("source_name", "dataset", "release", "source_url")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _unwrap(annotation: Any) -> Any:
    """Strip ``Annotated`` and ``None`` from an annotation.

    Of a union's remaining members, a model or container is preferred over a
    scalar, since only those can hold nested paths.
    """
    while get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    if get_origin(annotation) in (Union, UnionType):
        members = [_unwrap(arg) for arg in get_args(annotation) if arg is not NoneType]
        nested = [member for member in members if _holds_paths(member)]
        return (nested or members)[0]
    return annotation


def _is_model(annotation: Any) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def _is_container(annotation: Any) -> bool:
    if get_origin(annotation) in (list, dict, set, frozenset, tuple):
        return True
    return isinstance(annotation, type) and issubclass(annotation, RootModel)


def _holds_paths(annotation: Any) -> bool:
    return _is_container(annotation) or _is_model(annotation)


def _path_exists(model: type[BaseModel], path: str) -> bool:
    """Whether a dotted path names a field (or sub-field) of ``model``.

    Segments after a list, dict, or RootModel are item keys (e.g. an
    identifier's ``authority.id_type`` or a geometry's ``valid_from``) and are
    not checked. A model that allows extra fields accepts any segment.
    """
    annotation: Any = model
    for segment in path.split("."):
        annotation = _unwrap(annotation)
        if _is_container(annotation):
            return True
        if not _is_model(annotation):
            return False
        if segment not in annotation.model_fields:
            return annotation.model_config.get("extra") == "allow"
        annotation = annotation.model_fields[segment].annotation
    return True


class Sourcing(BaseModel):
    """A record's provenance, indexed by field path.

    ``sources`` stores each distinct Source once under a readable key.
    ``fields`` maps a dotted path on the owning record to the keys of the
    sources that support it. Items inside a list or dict are addressed by a
    stable key, not a position: ``identifiers.census.geoid``,
    ``geometries.2024-01-01``.
    """

    sources: dict[str, Source] = Field(
        default_factory=dict,
        description="Each distinct source cited by the record, keyed by a readable slug.",
    )
    fields: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Dotted field path on the owning record → keys into ``sources``.",
    )

    @model_validator(mode="after")
    def check_references(self) -> "Sourcing":
        cited: set[str] = set()
        for path, keys in self.fields.items():
            unknown = [key for key in keys if key not in self.sources]
            if unknown:
                raise ValueError(f"Field {path!r} cites unknown source(s) {unknown}")
            cited.update(keys)
        uncited = sorted(set(self.sources) - cited)
        if uncited:
            raise ValueError(f"Sources {uncited} are not cited by any field")
        return self

    def _key_for(self, source: Source) -> str:
        for key, existing in self.sources.items():
            if existing == source:
                return key
        base = (
            _slug(
                "_".join(
                    part
                    for part in (source.source_name, source.dataset, source.release)
                    if part
                )
            )
            or "source"
        )
        key, suffix = base, 2
        while key in self.sources:
            key, suffix = f"{base}_{suffix}", suffix + 1
        self.sources[key] = source
        return key

    def add(self, path: str, source: Source) -> str:
        """Cite ``source`` for ``path`` and return the source's key.

        An equal source already present is reused rather than stored again.
        """
        plain = Source.model_validate(source.model_dump())
        key = self._key_for(plain)
        cited = self.fields.setdefault(path, [])
        if key not in cited:
            cited.append(key)
        return key

    def sources_for(self, path: str) -> list[Source]:
        """Return the sources cited for exactly ``path``."""
        return [self.sources[key] for key in self.fields.get(path, [])]

    def check_paths(self, model: type[BaseModel]) -> None:
        """Raise ValueError naming every path that ``model`` does not have."""
        unknown = [path for path in self.fields if not _path_exists(model, path)]
        if unknown:
            raise ValueError(
                f"Sourcing paths not on {model.__name__}: {', '.join(unknown)}"
            )

    def merge(self, other: "Sourcing") -> None:
        """Add every citation in ``other`` to this index."""
        for path, keys in other.fields.items():
            for key in keys:
                self.add(path, other.sources[key])
