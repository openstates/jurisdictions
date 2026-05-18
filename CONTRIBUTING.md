# Contributing to OpenStates Jurisdictions

Thanks for contributing.

This repository stores and generates Division and Jurisdiction YAML data for US
local governments.

## Why Your Contribution Matters

When you contribute to this project, your work directly improves the civic data infrastructure that powers transparency, research, and public engagement across the United States.

**Here's what happens:**
- Your corrections and updates to jurisdiction and division data become the authoritative source used by OpenStates.org and its API
- Researchers, journalists, and civic tech developers rely on this data to track legislation, analyze government accountability, find local representatives and build tools that serve the public
- Your knowledge of your local government (boundaries, officials, contact information) fills critical gaps that automated systems can't solve
- The improvements you make help ensure that civic technology actually works for the communities it serves

Think of it like this: just as Open States volunteers understood that better data on their website meant better tools for their state's civic engagement, your contributions here create the foundation that makes all downstream civic tech work correctly.

## Ways to Contribute

### Update YAML data directly - No coding required.
If you know that a division or jurisdiction file contains incorrect or outdated information — wrong district boundaries, a renamed office, a bad URL — you can edit the relevant file directly under `divisions/` or `jurisdictions/` and open a pull request with your correction.

**Your impact:** Your local knowledge flows directly into OpenStates.org and its API. When you fix a contact URL, update district boundaries, or correct an official's name, journalists and civic technologists immediately get better data. This type of contribution is especially valuable because you know things about your local government that no automated system can discover.

1. Fork this repo
2. On your forked repo, update a file under the `data` folder
3. Update the file, then `Commit changes` via `Commit directly to the main branch`.
4. Go back to your forked repo,  "Contribute" -> "Open pull request"
5. Follow the [Pull Request Guidelines](#pull-request-guidelines)
6. Click "Create pull request"

### Pick up an existing issue - Coding required. (Python)
Browse the [issues tracker](https://github.com/openstates/jurisdictions/issues) and pick up an issue. Labels marked as 'good first issue' are a good place to start.

**Your impact:** These issues often involve building tools or fixing processes that affect how hundreds or thousands of jurisdiction records are generated and validated. Your code changes improve the pipeline that feeds OpenStates' data infrastructure, making it faster, more reliable, and more comprehensive.

## Before You Start
1. Check for an existing issue related to your change.
2. If no issue exists, open one describing the problem and proposed approach.
3. Create a feature branch for your work.

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
2. Update this file (`CONTRIBUTING.md`) if contributor process changed.
3. Update `AGENTS.md` and `ai_tools/` assets if agent workflow changed.
4. Record breaking changes in `CHANGELOG.md`.

## Pull Request Guidelines
Include the following in your PR:
1. Linked issue.
2. Summary of what changed and why.
3. Tests and validation commands run.
4. Notes on data/output impact (for example `divisions/`, `jurisdictions/`).

## Where to Put Docs
- Human-facing documentation belongs in `docs/`.
- Agent-facing instructions belong in `AGENTS.md` and `ai_tools/`.

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
