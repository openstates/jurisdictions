// Pinned above 1.30.0: @duckdb/duckdb-wasm@1.29.2 was briefly compromised
// with crypto-stealing malware in Sep 2025 (CVE-2025-59037) before npm
// pulled it. Do not float this to "latest" without checking advisories.
import * as duckdb from "https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.30.0/+esm";

const DATA_BASE = "data/";

// DuckDB-Wasm's internal HTTP filesystem (used by read_parquet) does not
// resolve relative paths against the page URL the way fetch()/<img src>
// do — it needs an absolute http(s) URL, so every path handed to
// read_parquet() is resolved through this first.
function absUrl(relativePath) {
  return new URL(relativePath, document.baseURI).href;
}

// Every parquet URL carries the manifest's own timestamp. A run that changed nothing reuses
// the cached bytes; a new run changes every URL at once, so the file list and the files can
// never disagree.
function versionedUrl(manifest, path) {
  const version = encodeURIComponent(manifest.generated_at ?? "");
  return `${absUrl(DATA_BASE + path)}?v=${version}`;
}

// DuckDB-Wasm init + registering Parquet views from the published manifest.
export const Dataset = {
  // Call this immediately at page load, in parallel with initDb() — it's a
  // plain HTTP fetch with no dependency on DuckDB being ready, so there's no
  // reason to wait for WASM init before starting it. Pass the returned
  // promise into registerViews() once the connection is ready.
  async fetchManifest() {
    // `no-cache` forces revalidation, not a bypass: GitHub Pages serves with its own cache
    // TTL, and every deploy can rewrite the dataset. Without it a returning reader can query
    // the previous manifest against the new files. The ETag makes the revalidation cheap — an
    // unchanged manifest comes back 304 with no body.
    const resp = await fetch(DATA_BASE + "manifest.json", { cache: "no-cache" });
    if (!resp.ok) throw new Error(`Failed to load manifest.json (${resp.status})`);
    return resp.json();
  },

  async initDb() {
    const bundles = duckdb.getJsDelivrBundles();
    const bundle = await duckdb.selectBundle(bundles);

    const workerUrl = URL.createObjectURL(
      new Blob([`importScripts("${bundle.mainWorker}");`], { type: "text/javascript" })
    );

    const worker = new Worker(workerUrl);
    const logger = new duckdb.ConsoleLogger(duckdb.LogLevel.WARNING);
    const db = new duckdb.AsyncDuckDB(logger, worker);
    await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
    URL.revokeObjectURL(workerUrl);

    return db;
  },

  // Call right after fetchManifest(), before initDb(): starts every single-file table's
  // download at once, while WASM is still starting. DuckDB-Wasm's own HTTP reads go one
  // request at a time from its worker, so the browser fetching them in parallel and handing
  // DuckDB the bytes is much faster on a cold visit. Returns file path -> bytes promise.
  async prefetchFiles(manifestPromise) {
    const manifest = await manifestPromise;
    const files = new Map();
    for (const entry of manifest.tables) {
      if (!entry.file) continue;
      const bytes = fetch(versionedUrl(manifest, entry.file)).then(async (resp) => {
        if (!resp.ok) throw new Error(`Failed to load ${entry.file} (${resp.status})`);
        return new Uint8Array(await resp.arrayBuffer());
      });
      bytes.catch(() => {}); // surfaced when registerViews awaits it
      files.set(entry.file, bytes);
    }
    return files;
  },

  async registerViews(db, conn, manifestPromise, filesPromise) {
    const manifest = await manifestPromise;
    const files = await filesPromise;
    const versioned = (path) => versionedUrl(manifest, path);

    const tableNames = [];
    // Row counts and column schema are both computed once at export time
    // (src/utils/parquet.py) and published in the manifest — reuse them
    // rather than re-deriving live in the browser.
    const rowCounts = new Map();
    const manifestTables = [];
    for (const entry of manifest.tables) {
      const safeName = `"${entry.name.replace(/"/g, '""')}"`;

      if (entry.file) {
        // Single file, already downloaded by prefetchFiles(): DuckDB reads it from memory.
        await db.registerFileBuffer(entry.file, await files.get(entry.file));
        await conn.query(
          `CREATE VIEW ${safeName} AS SELECT * FROM read_parquet('${entry.file.replace(/'/g, "''")}')`
        );
      } else if (entry.files && Object.keys(entry.files).length > 0) {
        // Hive-partitioned table written as separate per-partition files.
        // hive_partitioning=true lets DuckDB infer the partition column
        // (e.g. state) from each file's path and prune remote fetches on
        // filtered queries, without needing directory listing over HTTP.
        const urls = Object.values(entry.files).map(versioned);
        const urlList = urls.map((u) => `'${u}'`).join(", ");
        await conn.query(
          `CREATE VIEW ${safeName} AS SELECT * FROM read_parquet([${urlList}], hive_partitioning=true)`
        );
      } else {
        // No partition files (e.g. a table with zero rows this run) — nothing to query.
        continue;
      }
      tableNames.push(entry.name);
      rowCounts.set(entry.name, entry.rows);
      manifestTables.push(entry);
    }
    return { tableNames, rowCounts, manifestTables };
  },
};
