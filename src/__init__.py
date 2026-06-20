"""
OpenStates Jurisdictions

Standardized Division and Jurisdiction data for US local governments
in the OpenStates ecosystem.

This package provides:
- Pydantic models for Division, Jurisdiction, and related entities
- Data generation and serialization utilities
- YAML management for civic data files
- OCD ID parsing and validation
"""

__version__ = "0.1.0"
__author__ = "Open States Contributors"
__email__ = "hello@openstates.org"

# Public API exports

from src.models.division import Division
from src.models.jurisdiction import Jurisdiction
from src.models.ocdid import OCDIdParsed
from src.models.source import SourceObj, SourceType
__all__ = [
    "Division",
    "Jurisdiction",
    "OCDIdParsed",
    "SourceObj",
    "SourceType",
    "__version__",
    "__author__",
    "__email__",
]
