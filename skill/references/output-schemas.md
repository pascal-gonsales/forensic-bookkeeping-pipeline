# Output Schemas — Reference

> Strict schemas for every persistent file produced by this skill. Drift here breaks Dataview queries, breaks downstream tools, and breaks trustee deliverables.

---

## decisions.jsonl — append-only decision log

**Format:** one JSON object per line. Append only. Never edit past lines.

**Required fields for every decision touching a material amount:**

| Field | Meaning |
|---|---|
| `ts` | ISO 8601 timestamp, minute precision (e.g. `2026-04-27T08:15`) |
| `entity` | entity slug (matches `entities/<slug>/`), or `global`, or `cross-entity` |
| `field` | what is being decided (e.g. `vacation_pay_total`, `cc_classification`, `creditor_addition`) |
| `value` | the value or label (number or string) |
| `basis` | source-based, methodological, or user-instruction reason — never a legal interpretation |
| `source_id` | stable id from `source_registry.csv`/`.json`, OR `user_confirmation:<ts>:<context>`, OR `none` only when status is `BLOCKED` |
| `source` | filename of the cited document (matches the registry's path) |
| `source_locator` | `:row=N`, `:page=N`, `:sheet=Name,row=N-M`, `entry=<id>`, etc. |
| `confidence_status` | one of `CONFIRMED|INFERRED|NEEDS_REVIEW|BLOCKED` |
| `session` | session identifier |

**Optional fields:**
- `corrects` — original `ts` of the entry being corrected
- `resolution_status` — only when the decision closes/supersedes an exception (`OPEN|RESOLVED|SUPERSEDED`)
- `notes` — free text, kept short

**`basis` is not legal advice.** Acceptable forms:
- `"User confirmation in STANDUP on 2026-04-27"`
- `"Source document on file; value extracted from <file>:<locator>"`
- `"Methodological choice per Skill architecture-per-entity.md (per-entity reconciliation)"`
- `"Routed to trustee — value remains NEEDS_REVIEW until trustee responds"`

Unacceptable: any sentence that interprets a statute or chooses a tax/legal posture. Those go into the trustee briefing's `Questions for trustee/accountant/counsel` section, not into `basis`.

**Examples (anonymous):**

```json
{"ts":"2026-04-27T08:15","entity":"entity-slug-1","field":"vacation_pay_net_6month","value":12345.67,"basis":"Source document on file; value extracted from sheet Vacances","source_id":"SRC-PAYROLL-001","source":"payroll-reconciliation-vN.xlsx","source_locator":":sheet=Vacances,row=42-78","confidence_status":"CONFIRMED","session":"sample-session"}
{"ts":"2026-04-27T08:20","entity":"global","field":"director_status_check","value":"unverified","basis":"Source missing — entry from Quebec corporate registry not yet pulled","source_id":"none","source":"","source_locator":"","confidence_status":"BLOCKED","session":"sample-session","notes":"Add to FETCH NEXT in FORENSIC_STATUS.md"}
{"ts":"2026-04-27T09:00","entity":"entity-slug-1","field":"vacation_pay_net_6month","value":12545.67,"basis":"Correction following review of additional payroll export","source_id":"SRC-PAYROLL-002","source":"payroll-bank-balance-export.csv","source_locator":":row=89","confidence_status":"CONFIRMED","session":"sample-session","corrects":"2026-04-27T08:15"}
```

---

## source_registry.csv — canonical document/source registry

**Format:** CSV with header row. One row per source document.

**Required columns:**

| Column | Meaning |
|---|---|
| `source_id` | stable id, e.g. `SRC-BANK-001` (assigned once, never reused) |
| `path` | path relative to the package root |
| `sha256` | SHA256 hex digest of the file contents |
| `size_bytes` | file size in bytes |
| `first_seen` | ISO date the registry first saw this file |
| `last_verified` | ISO date the registry last computed and matched the SHA256 |
| `entity` | entity slug, or `global`, or `cross-entity` |
| `domain` | one of `bank|cc|payroll|tax|creditor|intercompany|other` |
| `document_type` | short label, e.g. `etat_compte_RP`, `nethris_solde_banque`, `bank_statement_pdf`, `cc_statement_pdf`, `supplier_invoice_pdf`, `xlsx_reconciliation` |
| `obtained_from` | portal/source the user pulled it from, e.g. `CRA My Business Account`, `Revenu Quebec ClicSEQUR`, `Desjardins AccesD`, `RBC online`, `internal_export` |
| `date_on_document` | ISO date printed on the document, if any (else blank) |
| `notes` | optional free text |

A pipeline-generated JSON form (`source_registry.json`) is allowed and uses the same fields keyed by `path`. The validator accepts either form.

**Hard rules:**
- Every `CONFIRMED` row in any deliverable must reference a `source_id` that exists in this registry (unless `source_id` is `user_confirmation:<ts>:<context>`).
- Strict-mode validation recomputes SHA256 and fails on mismatch.
- File renames require a new registry row that points to the new path; the old row is marked `notes=superseded by SRC-XXX`.

---

## STATUS.md (per entity)

**Format:** Markdown with YAML frontmatter.

**Required frontmatter fields:**
```yaml
---
type: source                     # NEVER set to "analysis" — this is a source file
entity: <slug>                   # matches folder name
entity_name: <full legal name>
neq: <Quebec Enterprise Number>
bn: <Federal Business Number>
status: active|closed|sold|insolvent
trustee_estate_no: <if filed>
last_updated: YYYY-MM-DD         # MUST update every session that touches this file
---
```

**Required sections (in this order):**
1. Identification
2. Tax accounts status (table with: Program, Account #, État de compte date, Last verified, `confidence_status`, `source_id`, `source`, `source_locator`)
3. Employee claims (table with: Item, Amount, `confidence_status`, `source_id`, `source`, `source_locator`, Notes)
4. Creditors (table with: Type, Count, Total, Last refresh, `source_id`, `source`)
5. Inter-company (table with: Direction, Counterparty, Amount, Documented?, `confidence_status`, `source_id`, `source`, `source_locator`)
6. Bank coverage (table with: Bank, Account, Period covered, Gaps, `source_id`, `source`)
7. Director liability exposure (if applicable; same source/status columns)
8. OPEN GAPS (bullet list)
9. NEXT ACTION (single sentence)
10. BLOCKED ON (bullet list)
11. DECISIONS log (link to filtered decisions.jsonl)
12. Last 3 sessions (auto-appended)

Any amount-bearing row that does not carry `confidence_status` and a source pair is invalid.

---

## FORENSIC_STATUS.md (global cold-start)

**Format:** Markdown with YAML frontmatter.

**Required frontmatter:**
```yaml
---
type: source
last_updated: YYYY-MM-DD
session_id: <currently active session>
---
```

**Required sections (in this order):**
0. Anti-drift reminders for AI
1. LAST VERIFIED (table: Item, Amount, `confidence_status`, `source_id`, `source`, `source_locator`, Verified date)
2. OPEN GAPS (bullet list — what is unknown)
3. NEXT ACTION (single concrete next thing)
4. BLOCKED ON (table: what we are waiting on, who, since when)
5. **FETCH NEXT** (table — see schema below)
6. DO NOT TOUCH UNTIL (bullet list of files/states to leave alone)
7. Active session metadata

### FETCH NEXT table schema

| Column | Meaning |
|---|---|
| `document` | What to download |
| `portal_or_source` | Where to download it from (CRA, Revenu Quebec, bank portal, payroll system, supplier email, etc.) |
| `entity` | Entity slug, or `global`/`cross-entity` |
| `why_blocking` | Which decision/schedule cannot proceed without it |
| `needed_for` | Schedule(s) that depend on it (e.g. `das-tax-schedule.csv`, `employee-claims.csv`, trustee briefing section X) |
| `requested_date` | ISO date the request/note was first added |
| `confidence_impact` | What changes when received (e.g. promotes line N from `BLOCKED` to `CONFIRMED`) |
| `next_owner` | Who is supposed to fetch it (`user`, `trustee`, `accountant`) |

The user reads this section first thing each morning. If a row sits >7 days, escalate.

---

## STANDUP.md (daily user dump)

**Format:** Markdown with YAML frontmatter.

**Required frontmatter:**
```yaml
---
type: source
date: YYYY-MM-DD
session: <session identifier>
---
```

**Required sections (always 3, always in this order):**
1. SINCE LAST SESSION (bullets)
2. TODAY I HAVE (bullets — hard constraints)
3. GOAL TODAY (single bullet — one entity OR one topic)

Overwrite this file every morning. Never archive (the SESSION_LOG.md captures history).

---

## SESSION_LOG.md (chronological append-only)

**Format:** Markdown, append-only.

**Append format per session:**
```markdown
## YYYY-MM-DD HH:MM — <session_id>

**What changed:**
- ...

**Decisions logged:** <count> new entries in decisions.jsonl

**Open at end of session:** <state>

**Next session priority:** <one thing>

**Files NOT touched this session:**
- ...
```

Never delete past entries. They are evidence of work performed.

---

## exception-log.csv

**Format:** CSV with header row. New exceptions are appended; resolution columns are updated in place.

**Required columns:**

| Column | Meaning |
|---|---|
| `id` | sequential integer |
| `priority` | `P0|P1|P2` |
| `entity` | slug or `global` or `cross-entity` |
| `domain` | `das|tax|payroll|creditors|intercompany|cc|bank|other` |
| `description` | one-line summary |
| `discovered_date` | ISO date |
| `amount` | the material amount, if any (else blank) |
| `confidence_status` | `CONFIRMED|INFERRED|NEEDS_REVIEW|BLOCKED` — about the value's epistemic state |
| `resolution_status` | `OPEN|RESOLVED|SUPERSEDED` — workflow lifecycle |
| `source_id` | registry id, or `user_confirmation:<ts>`, or blank if `BLOCKED` |
| `source` | filename of the cited document |
| `source_locator` | row/page/sheet/entry id |
| `resolution_date` | ISO date or blank |
| `resolution_notes` | free text |

The two status columns are **independent**. A `RESOLVED` exception still records the `confidence_status` of the resulting value; a `BLOCKED` exception is `OPEN` until the document arrives.

---

## trustee-briefing.md

**Format:** Markdown deliverable for the trustee. Generated at handoff time.

**Required sections (in this order):**
1. Header (date, debtor, trustee, entities covered)
2. Executive summary (3 bullets max)
3. Confirmed numbers — table with columns: Item, Entity, Amount, `confidence_status`, `source_id`, `source`, `source_locator`
4. Per-entity status snapshot — same source/status columns on every amount-bearing row
5. INFERRED items (flagged for review) — same source/status columns
6. What's blocked (and on whom) — links to FETCH NEXT rows
7. **Not included because blocked** — explicit list of items missing from the briefing because the underlying source is not yet on file
8. **Questions for trustee/accountant/counsel** — questions only; no answers, no recommendations, no statutory interpretation
9. Files attached — table with: `source_id`, Path, SHA256, Size
10. Confidence statement (which numbers are CONFIRMED vs INFERRED, what registry was used, what validation modes were run)

**Hard rules:**
- No amount in section 3 without source columns populated.
- No `INFERRED` rows in section 3.
- Section 8 questions must not contain proposed answers, recommendations, or "you could try X" framing. Phrase as `"Question: ... ?"` only.

---

## CSV templates (per domain)

See `assets/templates/` for:
- `employee-claims.csv` — per-entity employee amounts owed
- `das-tax-schedule.csv` — DAS RP/RS, TVQ, GST, T2, CO-17, CNESST by entity by period
- `creditor-schedule.csv` — Lists A/B/C/D format aligned to trustee schedules
- `personal-debt-schedule.csv` — debtor personal exposure (consumer proposal side)
- `source-registry.csv` — canonical document/source registry
- `exception-log.csv` — durable exception tracking with dual statuses
- `decision-entry.jsonl` — example decision log entries (anonymous)

Each CSV has its own column schema documented at the top of the template file. Every amount-bearing row carries `amount`, `confidence_status`, `source_id`, `source`, `source_locator`, `notes`.
