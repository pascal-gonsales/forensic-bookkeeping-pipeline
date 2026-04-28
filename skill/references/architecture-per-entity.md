# Architecture: Per-Entity is Canonical, Master is Index

> Tempted to consolidate into one big master file? Read this first.

---

## The principle

**Each entity has its own folder, its own STATUS.md, its own canonical Excel/CSV reconciliation files. The master is a navigation index — never a data store.**

This skill assumes a multi-entity insolvency case (typically 3-7 entities) where each entity has its own legal personality, its own creditors, its own tax accounts, its own employees. The trustee files separate Form 78 statements per entity. The OSB assigns separate estate numbers per entity.

A master file that consolidates all entities into one spreadsheet is:
- A duplicate of data that lives elsewhere (drift risk)
- A bottleneck (every change touches the master)
- A consolidation surface where bugs amplify silently
- Not what the trustee files (they file per entity)

---

## Why per-entity wins

### 1. AI context window stays focused
A 2,000-line master spreadsheet eats AI context that should go to actual analysis. A 200-line per-entity STATUS.md keeps the working memory clean.

### 2. Trustee navigates the same structure
Per entity, the trustee can request "send me everything for entity X" and you forward one folder. Master files force them to filter.

### 3. Edits are localized
Update one entity's bank coverage? Touch one file. With a master, every edit risks corrupting another entity's data.

### 4. Versioning is per-entity
Entity A can be at v4 reconciliation while Entity B is at v3. With a master, you're stuck with one version that's always behind on something.

### 5. Bug containment
A categorization error in one entity doesn't propagate to the master totals. With consolidation, one bug × 5 entities = visible-everywhere disaster (e.g. the 2x inter-company double-counting bug from April 2026 in this codebase).

### 6. Trustee deliverables compose at output time
When you need a cross-entity total, you compute it AT THE TIME OF DELIVERABLE, sourcing each entity's CONFIRMED figures. The total is documented as "computed YYYY-MM-DD from <entity files>" — not stored statically (where it could go stale).

---

## What the master IS allowed to be

`MASTER_INDEX.md` — a thin navigation file with:
- List of entities (slug, full name, NEQ, BN, status, link to STATUS.md)
- Cross-entity items that genuinely cross (e.g. inter-company loans matrix, but only as a pointer to the analysis file)
- Personal-debtor section for the consumer proposal side (separate file: `01_master/MASTER_dettes.xlsx`)
- Status dashboard: count of entities at each milestone (e.g. "3/5 Form 78 ready, 2/5 BLOCKED on RP statement")

What `MASTER_INDEX.md` is NOT allowed to contain:
- Dollar amounts copied from entity files
- Computed totals that aren't recomputed each time
- Classification decisions that should live in entity-specific decisions.jsonl entries

---

## What about cross-entity work?

Real cross-entity work exists:
- Inter-company transfers (entity A → entity B)
- Personal director liability rolling up multiple entities' DAS exposure
- Consumer proposal that aggregates the debtor's personal liability across all guarantees

For each: create a dedicated `cross-entity/` subfolder with its own STATUS.md and decisions.jsonl entries tagged `entity: cross-entity` or `entity: global`. Keep the cross-entity analysis OUT of any single entity's STATUS.md.

---

## Anti-pattern catalog

| Anti-pattern | Why bad | Fix |
|---|---|---|
| Maintaining a master Excel with all entities' totals updated manually | Stale within 24h, every session | Compute on demand at deliverable time |
| Storing inter-company totals in master AND in each entity's STATUS.md | Two sources of truth, will diverge | One source: cross-entity file. Entities link to it. |
| AI consolidates 5 entities' data into a single response | Context overload, classification drift | Touch one entity at a time |
| Trustee briefing built by re-aggregating master | Compounds any master errors | Build trustee briefing by reading per-entity STATUS.md, source-citing each row |
| One STATUS.md for "all 5 entities" | Edits collide, change tracking impossible | One STATUS.md per entity, mandatory |

---

## Migration from existing master file

If a working directory already has a giant master spreadsheet (typical state at v3 of forensic work):

1. Don't delete it — keep it as `archive/<filename>_DEPRECATED_<date>.xlsx`
2. Create `entities/<slug>/STATUS.md` for each entity, populated from the master at one point in time
3. Update `MASTER_INDEX.md` with pointers to the new per-entity files
4. Mark the old master as `[DEPRECATED — see entities/]` in its filename
5. Future updates go ONLY to per-entity files

The old master becomes evidence of the old state, not a live document.

---

## Mental model

Think of it as: **the per-entity STATUS.md files are the database. The master is the SQL view that joins them at query time.**

You don't store query results in a database. You compute them when needed, from sources that are kept fresh independently.
