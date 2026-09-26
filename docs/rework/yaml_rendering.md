# Deterministic YAML rendering

Phase 10 makes YAML rendering a terminal, deterministic stage. Resolution,
OCDID generation/validation, and canonical model construction happen before the
renderer receives a record.

## Serialization contract

Canonical `Division` and `Jurisdiction` models are serialized with:

- `model_dump(mode="json", exclude_none=False)`;
- model field order preserved (`sort_keys=False`);
- UTF-8 / Unicode output;
- one deterministic YAML representation for unchanged model inputs.

The renderer does not call Census, TIGER, OCD services, resolvers, rule engines,
or canonical validators.

## Stable path policy

Production records use:

```text
divisions/<state>/local/<slug>_<uuid>.yaml
jurisdictions/<state>/local/<slug>_<uuid>.yaml
```

Controlled golden output inserts `test` after the collection:

```text
divisions/test/<state>/local/<slug>_<uuid>.yaml
jurisdictions/test/<state>/local/<slug>_<uuid>.yaml
```

`district:dc` maps to the `dc` directory.

The human-readable slug is derived from `Division.display_name` or
`Jurisdiction.name`. The UUID remains the stable identity anchor. Census GEOIDs
are intentionally excluded from filenames because they are external
identifiers, can be absent for valid records, and must not define repository
identity.

## Reproducible timestamps

Canonical construction derives `last_updated` from immutable snapshot
provenance (`retrieval_date`, falling back to `publication_date`) rather than
the wall clock. This keeps two unchanged runs byte-identical while retaining a
meaningful source-observation timestamp.
