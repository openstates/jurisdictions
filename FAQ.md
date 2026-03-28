# Jurisdictions FAQ

## Why Jurisdictions?

Civic data is difficult to use because governance is not modeled consistently.

Across the United States, the same types of governing entities are described in different ways. Names overlap, structures vary, and datasets often blur the line between a place and the entity that governs it.

This project exists to fix that.

A **jurisdiction** is a governing entity with authority — such as a state, county, or municipal government.

A **division** is a geographic area — the land itself.

These are related, but not the same:

* Division = where something is
* Jurisdiction = who governs it

This distinction is foundational.

Without it:

* governance data becomes inconsistent
* relationships between entities break down
* systems cannot scale

With it:

* governance can be modeled clearly
* entities connect correctly to geography
* a stable foundation exists for civic data systems

This project focuses on building a clean, consistent jurisdiction layer that can support broader civic infrastructure.

---

## Frequently Asked Questions

### What is a jurisdiction?

A jurisdiction is a governing entity with authority over a defined scope.

Examples include:

* a state government
* a county government
* a municipal government

It represents governance, not geography.

---

### What is a division?

A division is a geographic area.

Examples include:

* a state boundary
* a county boundary
* a city boundary

It represents land, not authority.

---

### What is the difference between a jurisdiction and a division?

* Division = where something is
* Jurisdiction = who governs it

They are related, but not interchangeable.

---

### Why not just use geographic data?

Geography alone does not describe governance.

A map can show where something is, but it cannot tell you:

* who governs it
* how authority is structured

Jurisdictions provide that missing layer.

---

### Why not just use names?

Names are ambiguous.

The same name can refer to:

* a geographic area (division)
* a governing entity (jurisdiction)

The system must distinguish between them explicitly.

---

### Do jurisdictions always match geographic boundaries?

Often, but not always.

Examples:

* cities spanning multiple counties
* overlapping governance structures

A jurisdiction may relate to multiple divisions.

---

### What types of jurisdictions are included?

This project focuses on core governing entities:

* states
* counties
* municipalities

---

### What is not a jurisdiction?

A jurisdiction is not:

* a geographic area alone
* an office
* an election
* a dataset label

It must represent a governing entity.

---

### How are jurisdictions identified?

Jurisdictions use standardized identifiers where available (such as OCDIDs for divisions).

If missing:

* do not invent identifiers
* flag the gap

---

### Can I create a new identifier?

No.

Inventing identifiers breaks consistency and interoperability.

---

### What if I am unsure something is a jurisdiction?

Ask:

* Does it govern?
* Does it have authority?
* Is it a recognized public body?

If unclear, open an issue.

---

### How precise does this need to be?

Very.

Small inconsistencies create large downstream issues.

---

### What sources should I use?

Prefer:

* official government sources
* authoritative documentation

Do not guess.

---

### Can I include offices, elections, or candidates?

No.

This project is jurisdiction-focused only.

---

### How should I structure my contribution?

* keep it small
* match existing patterns exactly
* ensure verifiability

---

### What is the most common mistake?

Confusing jurisdictions with divisions.

---

### What should I check before submitting?

* Is this a governing entity?
* Are identifiers valid?
* Does it match existing structure?
* Is it verified?

---

## OCDID vs Jurisdiction Model

### OCDID (Geography)

```
ocd-division/country:us/state:tx/county:travis
```

Represents a geographic area.

---

### Jurisdiction (Governance)

```
name: Travis County government
type: county
division_ref: ocd-division/country:us/state:tx/county:travis
```

Represents the governing entity.

---

### Key Difference

| Concept    | OCD Model | This Project |
| ---------- | --------- | ------------ |
| Geography  | OCDID     | Division     |
| Governance | Implicit  | Jurisdiction |
| Separation | Combined  | Explicit     |

---

### Rule

Do not replace OCDIDs.

Use them for divisions and link jurisdictions to them.

---

## Python Development FAQ

### What language is used?

Python.

---

### Do I need Python to contribute?

No.

* Data contributors: no code required
* Engineering contributors: Python

---

### Where should I start?

* Review data models
* Understand jurisdiction vs division
* Pick an issue

---

### What is the key concept?

Separation of:

* geography (division)
* governance (jurisdiction)

---

### What work is needed?

* validation
* pipelines
* relationship modeling
* testing

---

### Should I change the data model?

No.

Open an issue first.

---

### How important are tests?

Critical.

They enforce consistency and prevent regressions.

---

### Common dev mistake?

Confusing division and jurisdiction in logic.

---

### What if unclear?

Ask before implementing.

---

## Good vs Bad Pull Requests

### Example 1: Division vs Jurisdiction

❌ Bad:
Treats a place as a governing entity

✅ Good:
Models the governing body and links to geography

---

### Example 2: Identifiers

❌ Bad:
Invents IDs

✅ Good:
Uses standards or flags gaps

---

### Example 3: Consistency

❌ Bad:
Introduces new patterns

✅ Good:
Matches existing records exactly

---

### Example 4: Scope

❌ Bad:
Adds elections or offices

✅ Good:
Keeps jurisdiction layer clean

---

### Example 5: Verification

❌ Bad:
Assumes structure

✅ Good:
Uses real sources

---

## What a Strong PR Looks Like

A strong PR:

* models a real governing entity
* follows existing patterns
* uses valid identifiers
* stays within schema
* is small and reviewable
* is verifiable
