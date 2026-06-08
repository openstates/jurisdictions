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

from typing import TYPE_CHECKING

from src.models.division import Division
from src.models.jurisdiction import Jurisdiction
from src.models.ocdid import OCDIdParsed
from src.utils.yaml_manager import YamlManager

__all__ = [
    "Division",
    "Jurisdiction",
    "OCDidParsed",
    "SourceObj",
    "SourceType",
    "YamlManager",
    "__version__",
    "__author__",
    "__email__",
]
