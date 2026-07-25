# Matching OCDids to Validation Records

How `GeneratePipeline.find_matches()` decides which row of the validation sheet
describes a given OCDid, why it used to get this wrong, and what you need to know
about the underlying Census data to change it safely.

## Background: the three vocabularies

Matching sits at the seam between three naming systems. Most of the bugs in this
area come from treating them as interchangeable.

**1. The OCDid.** A slash-separated path of `type:type_id` pairs, e.g.
`ocd-division/country:us/state:wa/place:oak_harbor/council_district:3`. Per the
[OCD spec](https://open-civic-data.readthedocs.io/en/latest/proposals/0002.html),
`type_id` is always lowercase and may contain underscores and hyphens. It is a
**slug**, not a name: `oak_harbor`, not `Oak Harbor`.

**2. Census `NAMELSAD`.** The validation sheet's name column. It is the place's
name *concatenated with its LSAD phrase*: `Oak Harbor city`, `Abbeville CCD`,
`Juneau city and borough`. The name alone is never stored separately, so every
consumer has to strip the affix.

**3. LSAD (Legal/Statistical Area Description).** A two-character Census code
describing what kind of entity the row is, and how its name is decorated. `25` is
`city` (suffix), `22` is `CCD` (suffix), `28` is `District` (**prefix**). The full
table lives in `src/data/lsad_map.json`, generated from the Census code list by
`src/data/lsad_mapper.py`.

## Background: the validation sheet has exactly two layers

This is the single most important fact about the data, and it is not obvious.

The sheet contains **68,308 rows across two Census layers**, distinguished by the
`layer` column and, equivalently, by which FIPS column is populated:

| layer | rows | `PLACEFP` | `COUSUBFP` | what it is |
|---|---|---|---|---|
| `place` | 31,958 | populated | blank | cities, towns, villages, CDPs |
| `cousub` | 36,349 | blank | populated | county subdivisions (CCDs, townships) |

Two consequences:

- **There are no county rows.** Not one. An OCDid of the form
  `.../county:king/council_district:2` has nothing it could ever match.
- **The two layers share names.** `Seattle city` (place) and `Seattle East CCD`
  (cousub) both exist in Washington. A `place:` OCDid must only ever be matched
  against `place` rows.

You cannot use the LSAD code to tell the layers apart. LSAD `25` ("city") appears
on 9,957 `place` rows *and* 2,658 `cousub` rows — New England towns are county
subdivisions that are also legally cities. Filter on `PLACEFP` instead.

## The algorithm

`find_matches()` returns 0, 1, or 2+ rows, and `run()` treats those three outcomes
differently: 1 row generates a full Division, 0 or 2+ generate a stub and file the
record to quarantine for a researcher.

1. Parse the OCDid; take `state` and `place`.
2. Un-slug the place: `oak_harbor` → `oak harbor`.
3. Resolve the state's FIPS code and filter the sheet to that state.
4. Filter to the place layer (`PLACEFP` non-blank).
5. **Exact match** on the normalized name. If any row matches exactly, those rows
   are the answer.
6. Only if nothing matched exactly, **fuzzy match** with `token_sort_ratio` at
   `FUZZY_MATCH_THRESHOLD` (0.85).

Normalized name means `NAMELSAD` with its LSAD affix removed (by table lookup on
the row's LSAD code) and lowercased. `Oak Harbor city` → `oak harbor`.

## What was broken

Four defects, which together meant a full-state run produced **zero** successful
records. In the last run before the fix: 924 records quarantined as "no match",
175 as "multiple matches", 21 hard failures, 0 successes.

### 1. `token_set_ratio` scored subset names at 1.0

`token_set_ratio` compares the *intersection* of the two token sets and discards
the tokens they do not share. So a one-word query scores a perfect 100 against any
longer name containing it:

```
token_set_ratio("spokane", "spokane valley")       = 100
token_set_ratio("spokane", "mount spokane ccd")    = 100
```

Querying `place:spokane` returned **6 matches** — the city, Spokane Valley, and
four unrelated CCDs — so the record was quarantined as ambiguous instead of
generating. This is why so few YAML files had real content.

`token_sort_ratio` sorts the tokens and compares the whole strings, which keeps
multi-word names comparable without collapsing distinct places.

### 2. OCDid slugs were compared verbatim

`place:oak_harbor` was matched against `oak harbor` with the underscore intact.
It scored 0 and produced no match. Worse, it failed *inconsistently*:
`des_moines` scored 0.90 and passed. The reason is that `token_set_ratio` sorts
the leftover tokens, so `des moines` survives the sort in alphabetical order while
`oak harbor` becomes `harbor oak`. Whether a two-word place matched depended on
whether its words happened to be alphabetical.

### 3. `place_name.py` corrupted names it did not recognize

`namelsad_to_display_name()` stripped the LSAD with a hardcoded regex listing a
dozen suffixes. `CCD` was not among them. It also had a fallback that retried the
regex against `s.title()` and **returned the title-cased string even when the
retry also failed to match**:

```
"Abbeville CCD"    -> "Abbeville Ccd"
"Seattle East CCD" -> "Seattle East Ccd"
```

Any name with an unlisted LSAD came back reformatted. This corrupted
`Division.display_name`, and it is what the integration test's
`assert div_data["display_name"] == "Sausalito"` was catching.

### 4. `created` is a reserved `LogRecord` attribute

```python
logger.info("Ancestor stub check complete", extra={..., "created": ...})
# KeyError: "Attempt to overwrite 'created' in LogRecord"
```

`logging` forbids `extra` keys that collide with `LogRecord`'s own fields, and
`created` is the record timestamp. The call sat at the end of the success path,
*after* the YAML had been written, so files landed on disk while the broad
`except Exception` flipped the record to `FAILED`. **Already fixed upstream** (the
key was renamed to `generated`); documented here because the symptom — YAML on
disk but zero successes in the tracking table — is baffling otherwise.

## What changed

| File | Change |
|---|---|
| `src/utils/place_name.py` | `namelsad_to_display_name(namelsad, lsad_code=None)` strips the affix by LSAD table lookup, falling back to the regex when the code is absent or unknown. Removed the `.title()` fallback. Added `CCD` to the regex and a `coerce_lsad_code()` helper. |
| `src/init_migration/generate_pipeline.py` | Un-slug the OCDid place segment; filter candidates to the place layer; exact match before fuzzy; `token_sort_ratio` replaces `token_set_ratio`. |
| `src/init_migration/generate_division.py` | Passes the row's LSAD code into `namelsad_to_display_name()`, so `display_name` is correct. Reuses `coerce_lsad_code()`. |
| `tests/integration/test_generate_pipeline_integration.py` | Fixed fixture, `rglob`, new regression tests. |

### Results

Every place row in a state, slugified as an OCDid would be, then matched back:

| state | before | after |
|---|---|---|
| WA | 375/639 (58.7%) | 631/639 (**98.7%**) |
| TX | 858/1862 (46.1%) | 1810/1863 (**97.2%**) |
| OH | 591/1161 (50.9%) | 1126/1161 (**97.0%**) |

Roughly 97% of names resolve on the exact path; fuzzy handles only the ~1% tail.
That ordering matters: `token_sort_ratio("alto", "alton")` is 0.89, which clears
the 0.85 threshold. Because Alto has an exact row, exact-first prevents the false
positive. **Do not remove the exact-match step and rely on the threshold alone.**

### The residual 2-3% is correct behavior

The names that still return 2+ matches are genuinely ambiguous: Ohio has two
villages named Bainbridge, Washington has two Clear Lakes. A `place:` OCDid
carries no county, so nothing in the input can disambiguate them. Quarantining
them for a researcher is the intended outcome, not a bug.

## Test fixture gotcha

The integration fixture originally wrote `NAMELSAD` as `"Sausalito city, California"`.
**No real row looks like that** — 0 of 68,308 `NAMELSAD` values end in a state
name. The fixture only passed because `token_set_ratio` ignored the extra tokens;
under `token_sort_ratio` it scores 0.51 and fails.

If you change the scorer, check the fixture first. When writing new fixture rows,
mirror the real shape: `"<Name> <LSAD suffix>"`, a populated `PLACEFP` for places,
a populated `COUSUBFP` and blank `PLACEFP` for county subdivisions.

## Open question: county OCDids

82% of the records fed to Phase 3 (3,662 of 4,446 in a WA run) are shaped
`.../county:<name>/council_district:<n>`. `find_matches()` does not parse the
`county` segment, and even if it did, **the validation sheet contains no county
rows**. These records will keep producing stubs and quarantine entries until
either:

- a county layer is added to the validation sheet, or
- county OCDids are filtered out before Phase 3 and handled by a separate path.

This is a scoping decision for whoever owns the validation sheet, not a code fix.
The warning was downgraded to `debug` so it no longer floods the log, but the
records still land in quarantine where a researcher can see them.

## Related

- `docs/ocdid_matching_criteria.md` — the OCDid spec itself.
- `src/data/lsad_mapper.py` — regenerates `lsad_map.json` from the Census page.
- Census LSAD code list: <https://www.census.gov/library/reference/code-lists/legal-status-codes.html>
