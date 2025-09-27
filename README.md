This repository contains YAML files with official information on state, county and
municipal jurisdictions, such as county government, city councils and school
boards.

# Setup Instructions (using uv)

## Requirements

- Python 3.12 or higher
- [uv](https://github.com/astral-sh/uv) (for dependency and environment management)

## Installation

1. **Install uv** (if not already installed):
	```sh
	brew install uv
	# or
	curl -LsSf https://astral.sh/uv/install.sh | sh
	```

2. **Create and activate a virtual environment:**
	```sh
	uv venv .venv
	source .venv/bin/activate
	```

3. **Install dependencies:**
	```sh
	uv sync --all-extras
	```

## Running

To run the main script:

```sh
uv run python main.py
```

## Development

To install development dependencies (for testing, linting, etc):

```sh
uv sync --all-extras
```

Run tests with:

```sh
uv run pytest
```

Run linter with:

```sh
uv run ruff .
```

## Project Dependencies

- Runtime: `pydantic>=2.11.9`
- Development: `polars>=1.33.1`, `pytest>=8.4.2`, `ruff>=0.13.2`

For more details on using uv, see [docs/setup_uv.md](docs/setup_uv.md).

# ENVIRONMENT