---
id: source-snapshots
type: rework-guide
owner: rework
status: active
last_updated: 2026-09-18
tags: [rework, phase-4, sources, snapshots, provenance]
task: "Phase 4 — Tasks 4.1–4.4 (issue #135)"
scope: "How external source files are fetched once, verified, cached under data/raw/, described by a metadata sidecar, and turned into SourceObj provenance."
---

# Source Snapshots (Phase 4)

The pipeline reads bulk files from three providers: the Census Government
Units Survey, Census TIGER, and the Open Civic Data division-id repository.
Each file is downloaded once per provider release, verified, and cached
with a metadata sidecar. Everything after the download runs offline from
the cache, and the golden tests run from checked-in fixture snapshots that
use the same sidecar format. `src/sources/snapshot.py` is the shared base;
the per-provider adapters (`census_governments.py`, `census_tiger.py`,
`ocd_master.py`) build on it and own parsing.

This replaces the download half of `DownloadManager`, which fetched the OCD
CSVs into DuckDB tables on every run (`current_pipeline.md` §2, §4). The
DuckDB file is not part of this layer and nothing here reads or writes it.

## 1. Four concerns, kept apart

| Concern | Where | Notes |
| --- | --- | --- |
| Fetch | `AsyncDownloader` (`src/init_migration/downloader.py`) | Reused as-is: retries, backoff, HTML-body guard, GitHub decoding. `SnapshotStore.fetch` calls `fetch_bytes(url, force=True)` because a cache miss here means the bytes are needed whatever the server's validators say. |
| Verify | `verify_snapshot`, `SnapshotSpec.expected_sha256` | Size and SHA-256 must match the sidecar. A caller that already knows the checksum pins it on the spec; a mismatch raises before anything is written. |
| Cache | `SnapshotStore` | `<root>/<source>/<release>/<filename>` plus `<filename>.meta.json`. Default root `data/raw/`. Files are written to a `.tmp` name and renamed, so a partial download never sits at the final path. |
| Parse | adapters | `Snapshot.read_bytes()` / `read_text()`; the base never interprets content. |

Timestamps are always injected. `SnapshotStore.fetch` and `put` take
`retrieved_at` as a keyword argument, and both `SnapshotSpec` and
`SnapshotMetadata` reject naive datetimes. Nothing under `src/sources/`
calls `datetime.now()`, so identical inputs yield identical sidecars.

## 2. Layout

```text
data/
  raw/
    census_governments/
      2022/
        <file>               bulk download, ignored by git
        <file>.meta.json     sidecar, committed
    tiger/
      2025/
        ...
    ocd_master/
      <release>/
        country-us.csv
        country-us.csv.meta.json
  cache/                     derived intermediates (Parquet etc.), ignored
```

`<release>` is the provider's own label: a GUS survey year, a TIGER/Line
vintage, or for the OCD repository a git ref or commit. Different releases
are different directories and never overwrite one another.

Fixture snapshots under `tests/fixtures/<source>/` use the same pair, file
plus sidecar, without the release directory. `load_snapshot(path)` opens
either layout: it reads the sidecar next to the file and verifies the
checksum by default.

## 3. The metadata record

`SnapshotMetadata` is the sidecar, serialized as JSON with sorted keys and
ISO 8601 timestamps:

| Field | Meaning |
| --- | --- |
| `source` | Cache directory key: `census_governments`, `tiger`, `ocd_master`. |
| `source_name` | Provider name as it appears in `SourceObj.source_name`. |
| `dataset` | Product within the provider (`SourceObj.dataset`). |
| `release` | Provider release, vintage, or version (`SourceObj.release`). |
| `filename` | Bare file name; must equal the name of the file the sidecar sits beside. |
| `url` | Exact URL fetched. |
| `sha256` | Hex digest of the file as stored. |
| `size_bytes` | Byte length of the file as stored. |
| `retrieved_at` | When this pipeline fetched it. Injected. |
| `publication_date` | When the provider published the release, when known. Null otherwise. |

Example:

```json
{
  "dataset": "Government Units Survey",
  "filename": "gus_2022.csv",
  "publication_date": null,
  "release": "2022",
  "retrieved_at": "2026-09-18T12:00:00+00:00",
  "sha256": "…",
  "size_bytes": 12345,
  "source": "census_governments",
  "source_name": "U.S. Census Bureau",
  "url": "https://…"
}
```

## 4. From snapshot to `SourceObj`

`source_obj_from_snapshot(metadata, field=[...])` is the only place
provenance is assembled from a snapshot. It fills:

| `SourceObj` field | From |
| --- | --- |
| `source_name` | `metadata.source_name` |
| `source_url` | `metadata.url` |
| `dataset` | `metadata.dataset` |
| `release` | `metadata.release` |
| `publication_date` | `metadata.publication_date` |
| `retrieval_date` | `metadata.retrieved_at` |
| `field`, `source_type`, `source_description` | caller; `source_type` defaults to `programmatically_generated` |

`release`, `publication_date`, and `retrieval_date` describe the source and
the observation. They never describe real-world validity: a TIGER/Line 2025
boundary is `valid_from` 2025-01-01 because that is the series' as-of date,
and `valid_to` stays null while the boundary is active. Those two fields
live on `Geometry`, not on the source (design §21, instruction §20).

## 5. Fetch behaviour

`SnapshotStore.fetch(spec, downloader, retrieved_at=...)`:

1. If the file and sidecar exist and verify, return them without touching
   the network. The recorded `retrieved_at` is the original download's.
2. If the cached file fails verification, log a warning and download again.
3. `refresh=True` downloads regardless.
4. A download whose SHA-256 differs from `spec.expected_sha256` raises
   `SnapshotIntegrityError` and writes nothing.
5. An HTML body where data was expected raises from the downloader
   (`UnexpectedContentError`) and writes nothing.

Errors are `SnapshotIntegrityError` (bytes do not match) and
`SnapshotMetadataError` (sidecar missing or malformed), both under
`SnapshotError` in `src/errors.py`.

## 6. Git policy for `data/raw/` and `data/cache/`

Bulk source files are never committed (instruction §17). The sidecars are
small and are what make a run reproducible: they pin the URL, release, and
checksum that produced the output. `.gitignore` therefore ignores everything
under `data/raw/` except `*.meta.json`, and ignores `data/cache/` entirely:

```gitignore
data/raw/**
!data/raw/**/
!data/raw/**/*.meta.json
data/cache/
```

A fresh checkout with committed sidecars can re-fetch each file and verify
it against the recorded checksum; a changed upstream file fails
verification instead of silently changing output.

## 7. What this layer does not do

- It does not normalize, resolve, or classify anything. Adapters return
  plain records; later phases consume them.
- It does not touch `data/ocdid_pipeline.duckdb`, `.etag_cache.json`
  semantics, `DownloadManager`, or `OCDidMatcher`. Those stay until the
  cleanup phase.
- It is not wired into `GeneratePipeline` or the CLI. The golden harness's
  `run_pipeline` still runs the existing generate stage; integration of the
  adapters is a later phase.
