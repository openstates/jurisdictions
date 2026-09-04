const QUERY_EXAMPLES = [
  {
    label: "Filter by state",
    description: "All matched lookup records for a single state.",
    sql: "SELECT *\nFROM ocdid_uuid_lookup\nWHERE state = 'wa'\nLIMIT 20;",
  },
  {
    label: "Aggregate: count per state",
    description: "How many matched records exist per state, most first.",
    sql: "SELECT state, COUNT(*) AS total\nFROM ocdid_uuid_lookup\nGROUP BY state\nORDER BY total DESC;",
  },
  {
    label: "Join: local records with their matched UUID",
    description: "Join the raw local staging table to the matched lookup table on OCD-ID.",
    sql: "SELECT l.name, l.state, u.uuid\nFROM local_ocdids l\nJOIN ocdid_uuid_lookup u ON l.id = u.ocdid\nLIMIT 20;",
  },
  {
    label: "Anti-join: master records with no local match",
    description: "LEFT JOIN + IS NULL to find master OCD-IDs missing from the local files — the same logic that produces master_orphans.",
    sql: "SELECT m.id, m.name\nFROM master_ocdids m\nLEFT JOIN local_ocdids l ON m.id = l.id\nWHERE l.id IS NULL\nLIMIT 20;",
  },
  {
    label: "Search by name",
    description: "Case-insensitive substring search across matched records.",
    sql: "SELECT ocdid, state, name\nFROM ocdid_uuid_lookup\nWHERE name ILIKE '%springfield%'\nLIMIT 20;",
  },
];

// Static, hand-written example queries shown in a collapsible <details> panel.
// No DB access needed — unlike SchemaPanel, this list doesn't depend on what
// tables happen to exist at runtime.
export const Examples = {
  el: document.getElementById("examples-list"),

  render(onSelectExample) {
    this.el.innerHTML = QUERY_EXAMPLES.map(
      (ex, i) => `
        <div class="example-item">
          <button type="button" class="example-name" data-index="${i}">${ex.label}</button>
          <div class="example-desc">${ex.description}</div>
          <pre class="example-sql">${ex.sql}</pre>
        </div>
      `
    ).join("");

    this.el.querySelectorAll(".example-name").forEach((btn) => {
      btn.addEventListener("click", () => {
        onSelectExample(QUERY_EXAMPLES[Number(btn.dataset.index)].sql);
      });
    });
  },
};
