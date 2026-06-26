# OpenStates Jurisdictions

This repository stores and generates Division and Jurisdiction YAML data for U.S.local governments. 

It includes YAML files with metadata for every government entity in the United States, each referencing the geopolitical boundaries co-extensive with that jurisdiction.  

Open States is a long-standing open source project that provides legislative data for all U.S. state legislatures. We are working to extend that to counties, county sub-divisions, municipalities, territories, school districts, and special districts. 

Our data is derived from Census Data and mapped to Open Civic Data Division identifiers (another long-standing open source project).  

The OpenStates/Jurisdictions YAML files are intended to be used by application builders. 

By providing a complete, accurate, stable and human-verified set of Jurisdictions, we are helping civic engagement application builders more easily collect representative information, ballot information, public notices, public meetings, and more.

## Quick Navigation

| Purpose | Start Here |
|---------|-----------|
| 🚀 **Getting Started** | [Quickstart](#quickstart-new-contributor) • [Requirements](#requirements) • [Installation](#installation) |
| 📚 **Understanding the Project** | [Core Concepts](#core-concepts) • [FAQ](FAQ.md) • [Data Models](MODELS.md) • [Model Relationships](docs/data_model_relationships.md) |
| 🤝 **Contributing** | [CONTRIBUTING.md](CONTRIBUTING.md) • [Ways to Contribute](#ways-to-contribute) • [Making Code Changes](#making-code-changes) |
| 🔧 **Advanced Topics** | [Using DuckDB](#using-duckdb) • [Running Tests](#running-tests) • [Common Commands](#common-commands) • [Reviewing PRs](#pulling--reviewing-external-prs) |

## Core Concepts

**New to this project?** This repository works with two core concepts:
- **Divisions** = Geographic boundaries (the land areas)
- **Jurisdictions** = Governing entities (the organizations that have authority)

For complete conceptual explanations and FAQ, see **[FAQ.md](FAQ.md)**.

For technical details on data models and fields, see **[MODELS.md](MODELS.md)** and **[docs/data_model_relationships.md](docs/data_model_relationships.md)** for a visual overview.

## What This Repo Contains
- Source models and pipeline code under `src/`
- Output YAML under:
  - `divisions/<state>/local/`
  - `jurisdictions/<state>/local/`
- Tests under `tests/`
- Human-facing docs under `docs/`

## Requirements

### System Requirements

| Component | Minimum | Recommended | Notes |
|-----------|---------|-------------|-------|
| **Python** | 3.12+ | 3.12+ | Required for all workflows |
| **uv** | Latest | Latest | Python package manager ([install](https://github.com/astral-sh/uv)) |

### Optional Dependencies

- **DuckDB** - Automatically instantiated in pipeline; can be used manually for data exploration
- **macOS** - `brew` for system package management

## Installation

### Prerequisites: Install `uv`

`uv` is a fast Python package manager. Install it first:

**macOS:**
```sh
brew install uv
```

**Linux:**
```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (WSL2):**
```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Or visit [uv installation guide](https://github.com/astral-sh/uv).**

### Platform-Specific Setup

#### macOS

```sh
# 1. Clone the repository
git clone https://github.com/openstates/jurisdictions.git
cd jurisdictions

# 2. Create virtual environment
uv venv .venv

# 3. Activate virtual environment
source .venv/bin/activate

# 4. Install dependencies
uv sync --all-extras

# 5. Verify installation
uv run ruff check .
uv run pytest -m "not integration and not slow"
```

#### Linux (Ubuntu/Debian)

```sh
# 1. Install system dependencies (if needed)
sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv python3.12-dev

# 2. Clone and setup
git clone https://github.com/openstates/jurisdictions.git
cd jurisdictions

# 3. Create virtual environment
uv venv .venv

# 4. Activate virtual environment
source .venv/bin/activate

# 5. Install dependencies
uv sync --all-extras

# 6. Verify installation
uv run ruff check .
uv run pytest -m "not integration and not slow"
```

#### Windows (WSL2 Recommended)

```sh
# In WSL2 terminal, follow Linux instructions above

# Or on native Windows (cmd/PowerShell):
# 1. Clone repository
git clone https://github.com/openstates/jurisdictions.git
cd jurisdictions

# 2. Create virtual environment
uv venv .venv

# 3. Activate virtual environment (PowerShell)
.\.venv\Scripts\Activate.ps1

# 4. Install dependencies
uv sync --all-extras

# 5. Verify
uv run ruff check .
uv run pytest -m "not integration and not slow"
```

## Quickstart (New Contributor)
1. Fork this repo on GitHub -> Owner (you) -> Create fork

2. Clone and enter repo.
```sh
git clone <your-repo-url>
cd jurisdictions
```

3. Create virtual environment and install dependencies.
```sh
uv venv .venv
source .venv/bin/activate
uv sync --all-extras
```

4. Verify local setup.
```sh
uv run ruff check .
uv run pytest -m "not integration and not slow"
```

5. Make changes and push
```sh
git checkout -b <your-new-branch>
<make changes>
git add .
git commit -m "Information about your changes."
git push origin <your-new-branch>
```

6. Create pull request by going to https://github.com/<your-username>/jurisdictions/tree/<your-new-branch> -> Contribute -> Open Pull Request

## Running Tests

### Test Organization

Tests are organized by scope and execution time:

| Test Type | Command | Purpose | When to Use |
|-----------|---------|---------|-----------|
| **Fast Unit Tests** | `uv run pytest -m "not integration and not slow"` | Quick validation of code | Before commits, local development |
| **All Unit Tests** | `uv run pytest -m "not integration"` | Complete unit test coverage | Before PR, CI validation |
| **Integration Tests** | `uv run pytest -m "integration"` | End-to-end pipeline testing | After model changes, before merging |
| **Full Suite** | `uv run pytest` | Everything (includes slow tests) | Final validation, CI/CD |
| **Specific Test** | `uv run pytest tests/path/to/test_file.py::test_name` | Single test function | Debugging specific issues |

### Common Test Commands

```sh
# Fast local check (recommended before commits)
uv run pytest -m "not integration and not slow"

# All tests except slow ones
uv run pytest -m "not integration"

# Full test suite (takes longer)
uv run pytest

# Run tests with verbose output
uv run pytest -v

# Run tests and show output/print statements
uv run pytest -s

# Run only integration tests
uv run pytest -m "integration"

# Run tests matching a pattern
uv run pytest -k "test_division" -v

# Run with coverage report
uv run pytest --cov=src --cov-report=html
```

## Using DuckDB

DuckDB is used in the pipeline for data exploration and validation. It's automatically instantiated when the pipeline runs, but you can also use it manually.

### Automatic Instantiation

When you run the Stage 1 pipeline, DuckDB database is automatically created:

```sh
uv run python src/init_migration/main.py
```

This creates `data/ocdid_pipeline.duckdb` with OCD ID data.

### Manual Usage

**Explore the database:**

```python
import duckdb

# Connect to existing database
conn = duckdb.connect('data/ocdid_pipeline.duckdb')

# List all tables
print(conn.execute("SELECT * FROM information_schema.tables").fetchall())

# Query OCD ID data
result = conn.execute("""
    SELECT * FROM ocdid_data 
    WHERE state = 'ca' 
    LIMIT 5
""").fetchall()

for row in result:
    print(row)

conn.close()
```

**Create a new database for analysis:**

```python
import duckdb

# Create in-memory database for testing
conn = duckdb.connect(':memory:')

# Create a table
conn.execute("""
    CREATE TABLE jurisdictions AS
    SELECT 'ca' as state, 'Los Angeles' as name
    UNION ALL
    SELECT 'wa' as state, 'Seattle' as name
""")

# Query it
result = conn.execute("SELECT * FROM jurisdictions").fetchall()
print(result)

conn.close()
```

### DuckDB Resources

- [DuckDB Documentation](https://duckdb.org/docs/)
- [Python API Reference](https://duckdb.org/docs/api/python/overview)
- See `data/` directory for available databases

## Common Commands

### Development Workflow

```sh
# Create a new branch for your changes
git checkout -b feature/my-feature

# Install/update dependencies after pulling changes
uv sync --all-extras

# Run code quality checks
uv run ruff check .
uv run ruff format .

# Run tests before committing
uv run pytest -m "not integration and not slow"
```

### Data Pipeline

```sh
# Run full Stage 1 pipeline
uv run python src/init_migration/main.py

# Run pipeline for specific states
uv run python src/init_migration/main.py --state ca,wa,tx

# Force re-run (bypass cache)
uv run python src/init_migration/main.py --force

# Run with verbose output
uv run python src/init_migration/main.py --state ca --verbose
```

### Maintenance & Troubleshooting

```sh
# Clean up Python cache files
find . -type d -name __pycache__ -exec rm -r {} +
find . -type f -name "*.pyc" -delete

# Update all dependencies
uv sync --all-extras --upgrade

# Verify environment setup
python --version
uv --version
```

## Ways to Contribute

### Update YAML data directly - No coding required
See [CONTRIBUTING.md](CONTRIBUTING.md#update-yaml-data-directly---no-coding-required) for step-by-step instructions.

### Pick up an existing issue - Coding required
See [CONTRIBUTING.md](CONTRIBUTING.md#pick-up-an-existing-issue---coding-required-python) for how to find and work on issues.

## Contributing Guidance
- **Getting started:** See [`CONTRIBUTING.md`](CONTRIBUTING.md) for how to contribute code, data, and improvements
- **Conceptual Q&A:** [`FAQ.md`](FAQ.md) - Understanding [divisions](FAQ.md#what-is-a-division), [jurisdictions](FAQ.md#what-is-a-jurisdiction), [places](FAQ.md#what-is-a-place), and governance
- **Model definitions:** [`MODELS.md`](MODELS.md) - Technical details on [Division](MODELS.md#division-model), [Jurisdiction](MODELS.md#jurisdiction-model), [OCDID](MODELS.md#ocdidparsed-model), and data structures
- **Model relationships:** [`docs/data_model_relationships.md`](docs/data_model_relationships.md) - Visual map and detailed connections
- Agent and semi-autonomous workflow rules: `AGENTS.md`
- Pre-commit checklist: `ai_tools/system/pre-commit-checks.instruction.md`
- UV setup details and migration notes: `docs/setup_uv.md`

## Questions?

- **"How do I...?"** Check the [FAQ](FAQ.md) for common questions
- **"What's the data model?"** See [MODELS.md](MODELS.md) for technical details
- **"How do I contribute?"** Read [CONTRIBUTING.md](CONTRIBUTING.md)
- **"Something's broken"** Check `docs/setup_uv.md` for troubleshooting, or open an [issue](https://github.com/openstates/jurisdictions/issues)

## 🚀 YAML-Only Changes & Auto-Merge

For pull requests containing **only YAML file changes** in `divisions/` or `jurisdictions/`:

- ✅ PR automatically merges after approval
- ✅ Branch automatically deletes
- ✅ No manual merge step needed

**How it works:**
1. Create PR with YAML-only changes
2. Workflow verifies files are in safe paths
3. Request reviewer approval
4. Auto-merge triggers automatically

**Learn more:**
- [YAML Auto-Merge Quick Reference](docs/YAML_AUTO_MERGE_QUICK_REFERENCE.md) — 2-minute overview
- [YAML Auto-Merge Workflow](docs/YAML_AUTO_MERGE_WORKFLOW.md) — Technical details & configuration

---

## Notes
- Use `src` package-root imports in code and tests (e.g., `from src.models.division import Division`)
- Do not modify core model contracts in `src/models/` without maintainer approval
- See [CONTRIBUTING.md](CONTRIBUTING.md#documentation-expectations) for documentation expectations when making changes

## Pulling & Reviewing External PRs

If you need to review changes from a pull request created on a forked repository, you can pull them locally:

### Fetch a PR for Local Review

```sh
# Fetch the PR and create a local branch
git fetch origin pull/<PR_NUMBER>/head:<local-branch-name>

# Switch to that branch
git checkout <local-branch-name>

# Review the changes locally
# Run tests, lint, and other validations
uv run pytest -m "not integration and not slow"
uv run ruff check .

# Switch back when done
git checkout main
```

### Example

```sh
# Fetch PR #42 for local review
git fetch origin pull/42/head:review-pr-42
git checkout review-pr-42

# Test the changes
uv run pytest -m "not integration and not slow"

# Return to main
git checkout main
```
