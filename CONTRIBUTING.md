# Contributing to OpenStates Jurisdictions

Thanks for contributing.

This repository stores and generates **[Division and Jurisdiction](MODELS.md)** YAML data for US local governments.

**Don't know the difference between Divisions and Jurisdictions?** Start with [FAQ.md](FAQ.md#what-is-the-difference-between-a-jurisdiction-and-a-division) for conceptual explanation, then [MODELS.md](MODELS.md#quick-reference) for technical details.

## Why Your Contribution Matters

When you contribute to this project, your work directly improves the civic data infrastructure that powers transparency, research, and public engagement across the United States.

**Here's what happens and why it matters:**
- Your corrections and updates to this repo and division data become the authoritative source used by OpenStates.org and its API.
- Researchers, journalists, and civic tech developers rely on this data to track legislation, analyze government accountability, find local representatives and build tools that serve the public
- Your knowledge of your local government (boundaries, officials, contact information) fills critical gaps that automated systems can't solve
- The improvements you make help ensure that civic technology actually works for the communities it serves

Think of it like this: just as Open States volunteers understood that better data on their website meant better tools for their state's civic engagement, your contributions here create the foundation that makes all downstream civic tech work correctly.

## Ways to Contribute

### Update YAML data directly - No coding required.
If you know that a division or jurisdiction file contains incorrect or outdated information — wrong district boundaries, a renamed office, a bad URL — you can edit the relevant file directly under `divisions/` or `jurisdictions/` and open a pull request with your correction.

**Your impact:** Your local knowledge flows directly into OpenStates.org and its API. When you fix a contact URL, update district boundaries, or correct an official's name, journalists and civic technologists immediately get better data.

1. Fork this repo
2. On your forked repo, update a file under the `data` folder
3. Update the file, then `Commit changes` via `Commit directly to the main branch`.
4. Go back to your forked repo,  "Contribute" -> "Open pull request"
5. Follow the [Pull Request Guidelines](#pull-request-guidelines)
6. Click "Create pull request"

**Need to understand the file structure?** See [MODELS.md](MODELS.md) for field definitions and examples.

**Working with places?** See [FAQ: What is a place?](FAQ.md#what-is-a-place).

### Pick up an existing issue - Coding required. (Python)
Browse the [issues tracker](https://github.com/openstates/jurisdictions/issues) and pick up an issue. Labels marked as 'good first issue' are a good place to start.

**Your impact:** These issues often involve building tools or fixing processes that affect how hundreds or thousands of jurisdiction records are generated and validated. Your code changes improve the pipeline that feeds OpenStates' data infrastructure, making it faster, more reliable, and more comprehensive.

## Before You Start
1. Check for an existing issue related to your change.
2. If no issue exists, open one describing the problem and proposed approach.
3. Create a feature branch for your work.
4. **Understand the basics:** Start with [FAQ.md](FAQ.md) for conceptual questions about divisions and jurisdictions, then [MODELS.md](MODELS.md) for technical details.

## Local Setup
See `README.md` for full setup instructions. Quick commands:

```sh
uv venv .venv
source .venv/bin/activate
uv sync --all-extras
```

## Making Changes
1. Keep changes focused and small.
2. Add or update tests for code changes.
3. Keep model contract changes in `src/models/` explicit and discussed with maintainers.
4. Use `src` package-root imports (for example `from src.models.division import Division`).
5. When modifying Division or Jurisdiction fields, ensure backward compatibility and update affected tests.
6. For OCD ID changes, test against the full validation pipeline.

## Validation Before PR
Run the checks below before opening or updating a PR:

```sh
uv run ruff check .
uv run pytest -m "not integration and not slow"
```

If your change affects cross-module behavior, pipeline orchestration, or output
artifacts, also run relevant integration tests.

For the full checklist, see `ai_tools/system/pre-commit-checks.instruction.md`.

## Documentation Expectations
When behavior or workflows change:
1. Update `README.md` if setup/run guidance changed.
2. Update `MODELS.md` if Division, Jurisdiction, or OCD ID structure changed.
3. Update `FAQ.md` if conceptual definitions or understanding changed.
4. Update this file (`CONTRIBUTING.md`) if contributor process changed.
5. Update `AGENTS.md` and `ai_tools/` assets if agent workflow changed.
6. Record breaking changes in `CHANGELOG.md`.

## Pull Request Guidelines
Include the following in your PR:
1. Linked issue.
2. Summary of what changed and why.
3. Tests and validation commands run.
4. Notes on data/output impact (for example `divisions/`, `jurisdictions/`).
5. For model changes: Clear explanation of how the structure changed and backward compatibility considerations (see [MODELS.md](MODELS.md) for current structure).

## YAML-Only Changes & Auto-Merge

For contributions that change **only YAML files** in safe paths:

**Safe paths for auto-merge:**
- `divisions/**/*.{yml,yaml}`
- `jurisdictions/**/*.{yml,yaml}`

**Process:**
1. Create PR with YAML-only changes in safe paths
2. Request reviewer approval
3. ✅ Workflow auto-merges after approval
4. ✅ Branch auto-deletes automatically

**Important:** If your PR includes any files outside these paths (code, config, docs), auto-merge is disabled and requires manual merge.

**Documentation:**
- [YAML Auto-Merge Quick Reference](../docs/YAML_AUTO_MERGE_QUICK_REFERENCE.md) — Quick overview for contributors
- [YAML Auto-Merge Workflow](../docs/YAML_AUTO_MERGE_WORKFLOW.md) — Technical details for maintainers

## Documentation Structure
- **[README.md](README.md)** - Project overview and quick start
- **[FAQ.md](FAQ.md)** - Conceptual questions (What's a division? What's a jurisdiction? Why both?)
- **[MODELS.md](MODELS.md)** - Technical data model definitions with field-level details
- **[docs/data_model_relationships.md](docs/data_model_relationships.md)** - Visual overview of how models connect
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - This file: how to contribute (code, data, improvements)
- **`docs/`** - Technical deep dives (OCD ID format, YAML structure, pipeline details)

## What Happens to Your Contribution

Once your PR is reviewed and merged:

1. **Data updates** (YAML files) are immediately available in this repository and automatically flow into OpenStates.org and its API on the next data update cycle
2. **Code improvements** help the team maintain, scale, and improve the pipeline that generates and validates all jurisdiction and division records
3. **Your contribution is credited** in the repository's git history and pull request records, creating a transparent record of who improved the civic data infrastructure
4. **Downstream users benefit** — researchers running studies, journalists investigating government, civic tech developers building tools, and citizens looking up their representatives all get more accurate and complete data

The improvements you make are permanent infrastructure improvements. They don't disappear after one election cycle or get overwritten—they become part of the foundation that civic technology builds on.

## Questions
Open an issue and tag maintainers if you are unsure about scope, data modeling,
or output conventions.

### Reference links: 
- [Census Fips
Codes](https://transition.fcc.gov/oet/info/maps/census/fips/fips.txt) - 
Census FIPS Codes — Federal Information Processing Standards (FIPS) codes are numeric identifiers assigned by the US Census Bureau to uniquely identify geographic and political entities. Every state has a 2-digit FIPS code, and every county has a 5-digit code (2-digit state + 3-digit county). 
- [Open Civic Data (OCD)](https://github.com/opencivicdata/ocd-division-ids) — standard identifiers and schemas for political divisions; the OCD-ID format is used throughout this repo
- [US Census Bureau TIGER/Line](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html) — authoritative geographic boundaries for counties, municipalities, districts, and more
ArcGIS Hub — aggregates open geospatial datasets from governments and agencies, often the source for local boundary files
  - [Tiger ArcGIS Rest API](https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/)
