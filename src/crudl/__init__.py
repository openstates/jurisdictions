# https://github.com/openstates/jurisdictions/issues/26

"""
CRUDL module for managing YAML files.

Provides YamlManager for Create, Read, Update, Delete, List operations
on Division and Jurisdiction YAML files with Pydantic validation.
"""

from .yaml_manager import YamlManager

__all__ = ["YamlManager"]
