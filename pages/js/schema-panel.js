import { escapeHtml } from "./utils.js";

// Buckets a DuckDB column type (e.g. "DECIMAL(18,3)", "TIMESTAMP WITH TIME ZONE")
// into one of a few badge categories for at-a-glance readability.
function typeCategory(type) {
  const t = type.toUpperCase();
  if (/^(BOOLEAN|BOOL)/.test(t)) return "boolean";
  if (/^(DATE|TIME|TIMESTAMP|INTERVAL)/.test(t)) return "date";
  if (/^(TINYINT|SMALLINT|INTEGER|BIGINT|HUGEINT|UTINYINT|USMALLINT|UINTEGER|UBIGINT|UHUGEINT|DOUBLE|FLOAT|DECIMAL|NUMERIC|REAL)/.test(t)) {
    return "number";
  }
  if (/^(VARCHAR|TEXT|CHAR|STRING|UUID|BLOB)/.test(t)) return "text";
  return "other";
}

function groupByTable(schemaRows) {
  const byTable = new Map();
  for (const { table, column, type } of schemaRows) {
    if (!byTable.has(table)) byTable.set(table, []);
    byTable.get(table).push({ column, type });
  }
  return byTable;
}

// Lists registered tables + columns, queried live via information_schema
// against the in-browser DuckDB instance (not a static/hardcoded list).
// Rendered in two places: a compact, clickable name list near the top of
// the page (renderNames), and the full column/type reference at the bottom
// (renderDefinitions) — same underlying data, different level of detail.
export const SchemaPanel = {
  namesEl: document.getElementById("table-names-wrap"),
  definitionsEl: document.getElementById("table-definitions-wrap"),

  async load(conn, tableNames) {
    if (!tableNames.length) return [];
    const nameList = tableNames.map((t) => `'${t.replace(/'/g, "''")}'`).join(", ");
    const result = await conn.query(`
      SELECT table_name, column_name, data_type
      FROM information_schema.columns
      WHERE table_name IN (${nameList})
      ORDER BY table_name, ordinal_position
    `);
    return result.toArray().map((row) => ({
      table: row.table_name,
      column: row.column_name,
      type: row.data_type,
    }));
  },

  renderNames(schemaRows, rowCounts, onSelectTable) {
    if (!schemaRows.length) {
      this.namesEl.innerHTML = "";
      return;
    }

    const byTable = groupByTable(schemaRows);
    const pillsHtml = [...byTable.keys()]
      .map((table) => {
        const rows = rowCounts.get(table);
        const rowsLabel = rows === undefined ? "" : ` (${rows.toLocaleString()})`;
        return `<button type="button" class="table-pill" data-table="${escapeHtml(table)}">${escapeHtml(table)}${escapeHtml(rowsLabel)}</button>`;
      })
      .join("");

    this.namesEl.innerHTML = `<h2>Tables</h2><div class="table-pills">${pillsHtml}</div>`;

    this.namesEl.querySelectorAll(".table-pill").forEach((btn) => {
      btn.addEventListener("click", () => onSelectTable(btn.dataset.table));
    });
  },

  renderDefinitions(schemaRows, rowCounts) {
    if (!schemaRows.length) {
      this.definitionsEl.innerHTML = "";
      return;
    }

    const byTable = groupByTable(schemaRows);
    const tablesHtml = [...byTable.entries()]
      .map(([table, cols]) => {
        const colsHtml = cols
          .map((c) => {
            const category = typeCategory(c.type);
            return `${escapeHtml(c.column)} <span class="type-badge type-badge--${category}">${escapeHtml(c.type)}</span>`;
          })
          .join(", ");
        const rows = rowCounts.get(table);
        const rowCountHtml = rows === undefined
          ? ""
          : `<div class="schema-row-count">${rows.toLocaleString()} row${rows === 1 ? "" : "s"}</div>`;
        return `
          <div class="schema-table">
            <div class="def-table-name">${escapeHtml(table)}</div>
            ${rowCountHtml}
            <div class="schema-columns">${colsHtml}</div>
          </div>
        `;
      })
      .join("");

    this.definitionsEl.innerHTML = tablesHtml;
  },
};
