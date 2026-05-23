# OpenStates Jurisdictions

This repository stores and generates Division and Jurisdiction YAML data for US
local governments in the OpenStates ecosystem.

## What This Package Does

Civic data is inconsistent because governance is modeled differently across jurisdictions. This package provides standardized, machine-readable data for:

- **Divisions** — Geographic boundaries (counties, cities, districts)
- **Jurisdictions** — Governing entities (city councils, legislatures, school boards)
- **OCD IDs** — Open Civic Data identifiers for reliable data linking

The data powers [OpenStates.org](https://openstates.org) and downstream civic technology applications.

## Installation

### From PyPI (User)
```bash
pip install openstates-jurisdictions
```

### For Development
```bash
# Clone the repository
git clone https://github.com/openstates/jurisdictions.git
cd jurisdictions

# Install uv (if needed)
brew install uv
# or
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install in dev mode
uv venv .venv
source .venv/bin/activate
uv sync --all-extras

# Verify setup
uv run ruff check .
uv run pytest -m "not integration and not slow"
```

## What This Repo Contains
- Source models and pipeline code under `src/`
- Output YAML under:
  - `divisions/<state>/local/`
  - `jurisdictions/<state>/local/`
- Tests under `tests/`
- Human-facing docs under `docs/`

## Requirements
- Python `3.12+`
- [uv](https://github.com/astral-sh/uv) (for development)
- macOS/Linux shell examples below (adapt for Windows as needed)

## Quickstart (New Contributor)
1. Fork this repo on GitHub -> Owner (you) -> Create fork

2. Clone and enter repo.
```sh
git clone <your-repo-url>
cd jurisdictions
```

3. Install `uv` (if needed).
```sh
brew install uv
# or
curl -LsSf https://astral.sh/uv/install.sh | sh
```

4. Create virtual environment and install dependencies.
```sh
uv venv .venv
source .venv/bin/activate
uv sync --all-extras
```

5. Verify local setup.
```sh
uv run ruff check .
uv run pytest -m "not integration and not slow"
```

6. Make changes and push
```sh
git checkout -b <your-new-branch>
<make changes>
git add .
git commit -m "Information about your changes."
git push origin <your-new-branch>
```

7. Create pull request by going to https://github.com/<your-username>/jurisdictions/tree/<your-new-branch> -> Contribute -> Open Pull Request

## Common Commands
## Usage

### Python API

```python
from openstates_jurisdictions import Division, Jurisdiction

# Import and work with models
division = Division(
    ocdid="ocd-division/country:us/state:ca",
    country="us",
    display_name="California",
)
```

### CLI

```bash
# Generate jurisdictions for specific states
jurisdictions --state wa,tx,oh

# Run full pipeline
jurisdictions
```

## Common Development Commands

- Full test suite:
```sh
uv run pytest
```

- Fast local test pass (skip integration tests):
```sh
uv run pytest -m "not integration and not slow"
```

- Lint and format:
```sh
uv run ruff check .
uv run ruff format .
```

- Type checking:
```sh
uv run mypy src
```

- Run specific pipeline stage:
```sh
uv run jurisdictions
```

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- How to set up your development environment
- Our contributor workflow and expectations
- Code style and testing requirements

Quick checklist for PRs:
1. Create a branch for your change
2. Keep changes focused and add/update tests
3. Run validation before opening PR:
   ```bash
   uv run ruff check . && uv run pytest -m "not integration and not slow"
   ```
4. Update documentation if needed

## Project Structure

```
.
├── src/
│   ├── models/           # Pydantic models (Division, Jurisdiction)
│   ├── utils/            # Utilities (YamlManager, OCD parsing)
│   └── init_migration/   # Data generation pipeline
├── tests/                # Unit and integration tests
├── docs/                 # Human-facing documentation
├── divisions/            # Generated division YAML files
├── jurisdictions/        # Generated jurisdiction YAML files
└── pyproject.toml        # Project configuration
```

## Resources

- [OpenStates Documentation](https://docs.openstates.org)
- [Open Civic Data (OCD) Specification](https://github.com/opencivicdata/ocd-division-ids)
- [Contributing Guidelines](CONTRIBUTING.md)
- [FAQ](FAQ.md)

## Maintainers

Open States Contributors

## License

CC0 1.0 Universal (Public Domain)

See [LICENSE](LICENSE) for details.

## Notes

- Use `src` package-root imports in code and tests
- Do not modify core model contracts in `src/models/` without maintainer approval
- See [AGENTS.md](AGENTS.md) for semi-autonomous workflow rules

