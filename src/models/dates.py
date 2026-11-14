"""Date string types for records that often know only part of a date."""

from typing import Annotated

from pydantic import StringConstraints

#: An ISO 8601 date that may be partial: ``YYYY``, ``YYYY-MM``, or
#: ``YYYY-MM-DD``. Public records often give only a year.
PartialDate = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}(-[0-9]{2}){0,2}$")]

#: A partial date, or a full date with a time and offset (Open Civic Data
#: fuzzy datetime, OCDEP 101): ``2025``, ``2025-03-04``, ``2025-03-04T14:00Z``.
FuzzyDateTime = Annotated[
    str,
    StringConstraints(
        pattern=(
            r"^[0-9]{4}((-[0-9]{2}){0,2}|(-[0-9]{2}){2}T[0-9]{2}(:[0-9]{2}){0,2}"
            r"(Z|[+-][0-9]{2}(:[0-9]{2})?))$"
        )
    ),
]
