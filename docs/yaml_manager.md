# CRUDL Module

A **C**reate, **R**ead, **U**pdate, **D**elete, **L**ist module for managing YAML files with Pydantic model validation.

## Overview

The `YamlManager` class provides file I/O operations for Division and Jurisdiction YAML files, with built-in serialization (YAML ↔ JSON/dict) and Pydantic model validation.

**Note:** Default values for some methods have changed. See below for details.

## Installation

The module is part of the `jurisdictions` package. No additional installation required.

## Quick Start

```python
from src.utils import YamlManager

# Initialize the manager (base_path is now required and must exist as a directory)
manager = YamlManager(base_path="data/divisions")
```

## Core CRUDL Operations

### Create

```python
# Create a new YAML file
data = {
    "ocdid": "ocd-division/country:us/state:oh/place:columbus",
    "name": "Columbus",
    "url": "https://www.columbus.gov"
}
filepath = manager.create("columbus.yaml", data)
```

### Read

```python
# Read a YAML file as a dictionary
data = manager.read("columbus.yaml")
print(data["name"])  # "Columbus"
```

### Update

```python
# Update with merge (set merge=True) - preserves existing fields
manager.update("columbus.yaml", {"url": "https://new-url.gov"}, merge=True)

# Update with replace (default: merge=False) - overwrites entire file
manager.update("columbus.yaml", new_data)
```

### Delete

```python
# Delete with optional confirmation prompt
manager.delete("columbus.yaml", confirm=True)  # Prompts user for confirmation

# Delete without confirmation (default)
manager.delete("columbus.yaml")
```

### List

```python
# List all YAML files in a directory (non-recursive by default)
files = manager.list_files("data/divisions")

# With custom pattern
files = manager.list_files("data/", pattern="*.yml")

# Recursive search
files = manager.list_files("data/", recursive=True)
```

## Pydantic Model Operations

Load and validate YAML files against Pydantic models:

```python
# Load as Division model (validates against schema)
division = manager.load_division("divisions/columbus.yaml")
print(division.ocdid)

# Load as Jurisdiction model
jurisdiction = manager.load_jurisdiction("jurisdictions/city_council.yaml")
print(jurisdiction.classification)

# Dump models to YAML
manager.dump_division("output/division.yaml", division)
manager.dump_jurisdiction("output/jurisdiction.yaml", jurisdiction, overwrite=True)
```

## Batch Operations

```python
# Read multiple files at once
filepaths = manager.list_files("data/")
all_data = manager.read_all(filepaths)  # Returns list of dicts with '_source_file' key

# List and load in one call
all_data = manager.list_and_load("data/divisions/")

# Iterate over files (memory efficient)
for filepath, data in manager.iter_files("data/"):
    print(f"{filepath}: {data['name']}")
```

## JSON Conversion

```python
# Convert dict to JSON string
json_str = manager.to_json(data)

# Read YAML file as JSON
json_str = manager.read_as_json("file.yaml")

# List, load, and convert to JSON
json_str = manager.list_and_load_as_json("data/")
```

## Filesystem Helpers

```python
# Check if file exists
if manager.exists("file.yaml"):
    data = manager.read("file.yaml")

# Count files in directory
count = manager.count("data/divisions/")
print(f"Found {count} YAML files")
```

