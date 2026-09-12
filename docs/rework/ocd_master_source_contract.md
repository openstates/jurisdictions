# OCD Division ID Master Source Contract

## Purpose

This document defines the source boundary for Issue #135, Task 4.3. The adapter
uses the Open Civic Data United States division ID master only to answer an
exact membership question:

> Does this complete `ocd-division/...` identifier exist in the pinned master?

Nearest-ID results are optional review aids. They are never accepted as matches
and never generate, repair, normalize, or quarantine an OCD ID.

## Pinned Source

| Field | Value |
|---|---|
| Repository | `opencivicdata/ocd-division-ids` |
| Repository revision | `a52719a15852fc8c8418194016c16657591930ad` |
| Source path | `identifiers/country-us.csv` |
| Git blob SHA-1 | `bca1de20902adabb89961d08e68e0400d41dde50` |
| Source format | UTF-8 CSV |

The raw download URL contains the full repository revision. Normal development
and tests use a controlled local fixture and perform no network requests.

## Exact Header Contract

The pinned CSV header is:

```text
id
name
sameAs
sameAsNote
validThrough
census_geoid
census_geoid_12
census_geoid_14
openstates_district
placeholder_id
sch_dist_stateid
state_id
validFrom
```

The adapter rejects missing, reordered, renamed, or additional columns. It
preserves the original CSV bytes unchanged in the cache. The source record API
emits only the exact identifier, display name, and source row needed for this
membership boundary; the unmodified cached snapshot remains authoritative for
all other source fields.

## Lifecycle Contract

### Fetch

- Use the repository's existing asynchronous downloader boundary.
- Fetch the revision-pinned raw URL.
- Treat a conditional `304 Not Modified` result as `None` and reuse only a
  complete, integrity-checked cache.

### Verify

Before caching or parsing, require:

- non-empty source bytes within the configured size limit;
- no NUL bytes and valid UTF-8;
- the pinned Git blob identity when configured;
- the exact header sequence above;
- at least one data row;
- the exact expected column count on every row;
- a non-empty identifier and display name;
- no surrounding whitespace on identifiers;
- every identifier to parse through `OCDIdParsed.parse_ocdid()`;
- `ocd-division` identifiers only; and
- no duplicate identifiers.

Verification is fail-closed. A malformed or partial source is not cached and
cannot produce an acceptance index.

### Cache

Cache the original source bytes unchanged beside an atomic JSON manifest that
records:

- repository, revision, source path, and revision-pinned URL;
- retrieval timestamp in UTC;
- SHA-256 and Git blob SHA-1 identities;
- byte size and data-row count;
- exact headers; and
- local source and manifest paths.

Loading a cache repeats source verification and compares all integrity fields.

### Parse

Parsing emits immutable source records with:

- exact OCD division ID;
- source display name; and
- one-based CSV source row number.

No normalization or inferred hierarchy is introduced.

## Membership and Suggestions

### Acceptance

`exact_lookup()` and `contains()` validate the candidate with
`OCDIdParsed.parse_ocdid()` and then perform literal full-ID membership. A
valid negative remains negative.

### Review-only suggestions

`suggest_for_review()`:

- runs only for valid, non-member division IDs;
- searches only siblings with the same segment type under the candidate's
  immediate parent;
- returns an explicit `review_only = True` marker; and
- never changes `contains()` or `exact_lookup()`.

No score threshold is an acceptance threshold.

## Scope Exclusions

This task does not:

- generate OCD IDs;
- implement the Phase 7 rule engine;
- implement Phase 8 validation or quarantine decisions;
- normalize Census Government Units records;
- resolve governments to TIGER geography;
- write DuckDB state, orphan tables, Division YAML, or Jurisdiction YAML;
- modify `src/models/`, `tests/sample_output/`, `tests/integration/`, workflows,
  dependencies, or package `__init__.py` files; or
- make network requests during normal tests.
