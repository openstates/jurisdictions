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

// DuckDB-Wasm init + registering Parquet views from the published manifest.
export const Dataset = {
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

  async registerViews(conn) {
    const manifestResp = await fetch(DATA_BASE + "manifest.json");
    if (!manifestResp.ok) {
      throw new Error(`Failed to load manifest.json (${manifestResp.status})`);
    }
    const manifest = await manifestResp.json();

    const tableNames = [];
    // Row counts are computed once at export time (export_data.py) and
    // published in the manifest — reuse them rather than re-counting live.
    const rowCounts = new Map();
    for (const entry of manifest.tables) {
      const safeName = `"${entry.name.replace(/"/g, '""')}"`;

      if (entry.file) {
        // Single unpartitioned file.
        const url = absUrl(DATA_BASE + entry.file);
        await conn.query(
          `CREATE VIEW ${safeName} AS SELECT * FROM read_parquet('${url}')`
        );
      } else if (entry.files && Object.keys(entry.files).length > 0) {
        // Hive-partitioned table written as separate per-partition files.
        // hive_partitioning=true lets DuckDB infer the partition column
        // (e.g. state) from each file's path and prune remote fetches on
        // filtered queries, without needing directory listing over HTTP.
        const urls = Object.values(entry.files).map((f) => absUrl(DATA_BASE + f));
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
    }
    return { tableNames, rowCounts };
  },
};
