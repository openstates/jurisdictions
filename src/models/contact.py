"""Contact details and links shared by people, offices, bodies, and governments.

Shapes follow the Popolo contact detail and link.
"""

import re

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter, model_validator

from src.models.dates import PartialDate

_HTTP_URL = TypeAdapter(HttpUrl)
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ContactDetail(BaseModel):
    """A way to contact a person, office, body, or government (Popolo contact detail)."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(
        description="Medium: 'address', 'email', 'url', or a telephone type such as 'voice', 'fax', 'cell', 'text'."
    )
    value: str = Field(description="The address, number, or URL.")
    label: str | None = Field(default=None, description="Human-readable label.")
    note: str | None = Field(
        default=None, description="e.g. 'City Hall', 'District Office', 'Clerk'."
    )
    valid_from: PartialDate | None = Field(
        default=None, description="Date from which the detail is valid."
    )
    valid_to: PartialDate | None = Field(
        default=None, description="Date after which the detail is no longer valid."
    )

    @model_validator(mode="after")
    def check_value(self) -> "ContactDetail":
        """A ``url`` must be an http(s) URL and an ``email`` an email address."""
        if self.type == "url":
            _HTTP_URL.validate_python(self.value)
        elif self.type == "email" and not _EMAIL.match(self.value):
            raise ValueError(f"{self.value!r} is not an email address")
        return self


class Link(BaseModel):
    """A URL about a record (Popolo link)."""

    model_config = ConfigDict(extra="forbid")

    url: HttpUrl
    note: str | None = Field(default=None, description="e.g. 'Wikipedia page'.")
