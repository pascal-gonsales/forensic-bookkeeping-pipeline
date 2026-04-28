---
name: forensic-bookkeeping
description: Trustee-defensible forensic bookkeeping skill for restaurant insolvency dossier prep. Activates on requests touching: bank/CC reconciliation, inter-company transfers, employee claims (vacation/wages/tips), DAS source deductions (federal RP + Quebec RS), CNESST, T2/CO-17 tax, creditor schedules, consumer proposal debts, trustee handoff packages. Built around per-entity files as canonical truth + thin master index. Enforces source traceability, NEEDS_REVIEW default, no-invention rules, cold-start protocol.
---

# Forensic Bookkeeping Skill — v1.2 (Claude-first)

> **Purpose:** Help a debtor prepare a trustee-defensible insolvency dossier without a lawyer, working with a licensed insolvency trustee, in 30-45 min/day max.

> **Scope:** bank statements, credit card classification, inter-company transfers, payroll/employee claims, DAS, taxes, creditor schedules, supplier reconciliation, document handoff to trustee.

> **Out of scope:** legal advice, tax advice, strategy advice, negotiation. Always defer those to the trustee, a qualified accountant, or qualified counsel. Never advise.

> **Anonymity rule:** This Skill is reusable across debtors. It must not name any specific person, firm, or restaurant. Local working files outside this Skill may carry real identifiers.

---

## 1. Hard rules — anti-drift (read every session)

These rules are NON-NEGOTIABLE. Apply them on every action.

1. **Never state any number as fact unless you can cite source file + row/page/sheet/entry id.** If you cannot cite, the answer is `unverified` and you stop. Do not estimate, interpolate, or "round to a reasonable figure."

2. **Default confidence status is `NEEDS_REVIEW`.** Only escalate to `CONFIRMED` when (a) a source document is on file AND (b) the user has explicitly confirmed the value. `INFERRED` is allowed only when an obvious-but-unconfirmed pattern exists, and must be flagged for human review before any deposit to the trustee.

3. **Never auto-compute split percentages** (e.g. partner-trip 50% business, X% business-use of personal CC, mixed-use vendor splits). Mark `NEEDS_REVIEW`. Splits require explicit user input with a source.

4. **Never modify `type: source` notes.** Source notes record what the documents say. Only create or modify `type: analysis` notes for synthesis. Distinction lives in YAML frontmatter on every markdown file.

5. **Stale-note check:** if a STATUS.md you are about to act on has `last_updated` more than 7 days old, flag it before acting and ask the user if anything has changed.

6. **Legal, tax, or strategic questions = route, do not answer.** Use the generic phrasing in `references/routing-boundaries.md`. Route to the trustee, a qualified accountant, or qualified counsel as appropriate. Do not freelance interpretations of statutes (BIA, ITA, LAF, CCQ, LACC, Loi sur les normes du travail, etc.).

7. **Never invent insolvency facts.** Do not invent amounts, creditors, employee balances, tax balances, dates, or classifications. If a needed fact is missing, write `BLOCKED` and add a fetch-next entry.

8. **Cold-start protocol** (run at every session start, in this exact order):
   - Read `STANDUP.md` (today's user dump)
   - Read `FORENSIC_STATUS.md` (global cold-start state)
   - Read tail of `decisions.jsonl` (last 10 entries)
   - Read `STATUS.md` of the entity you are about to touch
   - Respond in exactly 3 lines: (a) what you read, (b) the one task you will do today, (c) what you will NOT touch today

9. **End-of-session protocol** (hard requirement, no shortcut):
   - Rewrite the touched entity `STATUS.md` (overwrite)
   - Rewrite `FORENSIC_STATUS.md` (overwrite)
   - Append a new block to `SESSION_LOG.md` (chronological, append-only)
   - Append any new decisions to `decisions.jsonl` using the required-fields schema (see `references/output-schemas.md`)

---

## 2. Architecture — per-entity is canonical, master is index

This skill assumes a working directory structured as:

```
<insolvency-root>/
├── FORENSIC_STATUS.md           ← cold-start file, overwrite each session
├── STANDUP.md                   ← daily user dump, overwrite each morning
├── SESSION_LOG.md               ← chronological, append-only
├── decisions.jsonl              ← append-only decision log (required-fields schema)
├── source_registry.csv          ← canonical document/source registry (per-row schema)
│                                  (or source_registry.json if the pipeline is in use)
├── MASTER_INDEX.md              ← thin master, navigation only — NO numbers
├── 01_master/                   ← personal debt master spreadsheet
├── entities/                    ← canonical truth per entity
│   ├── <entity-slug-1>/
│   │   ├── STATUS.md            ← entity state (rewrite per session)
│   │   ├── corporate-records/
│   │   ├── tax-accounts/{rp-federal, rs-quebec, co-17, t2, tvq, cnesst}/
│   │   ├── payroll/
│   │   ├── creditors/
│   │   ├── bank-statements/
│   │   └── supplier-invoices/
│   └── <entity-slug-N>/         ← same structure
└── 03_deliverables/             ← outputs to trustee (built from per-entity)
```

**Principle:** numbers live in entity files. The master is a navigation index, never a data store. Cross-entity totals are computed at deliverable time, not stored.

See `references/architecture-per-entity.md` for the full rationale.

---

## 3. Confidence statuses — standardized everywhere

| Status | Meaning | Allowed when |
|---|---|---|
| `CONFIRMED` | Source reviewed AND user confirmed | Document on file + explicit user "yes" recorded in `decisions.jsonl` |
| `INFERRED` | Probable from data, not yet confirmed | Pattern obvious; must be flagged for review before trustee deposit |
| `NEEDS_REVIEW` | Ambiguous, requires user decision | Default for any new item |
| `BLOCKED` | Source document missing — cannot complete | Wait on external (bank, portal, trustee answer) |

Forbidden ad-hoc values: `VERIFY`, `MAYBE`, `LOOK INTO`, `TBD`, blank. Always one of the four above.

**Important separation:** `confidence_status` is for the value's epistemic state. Workflow lifecycle (whether an exception is open or closed) is recorded separately as `resolution_status` (`OPEN | RESOLVED | SUPERSEDED`). Never mix the two in one column.

---

## 4. Source-traceability rule for every material amount

Every row that carries a material amount (employee claim, tax balance, creditor, personal debt, intercompany, exception with money attached, briefing line) must carry these columns at minimum:

| Column | Meaning |
|---|---|
| `amount` | The number itself |
| `confidence_status` | One of CONFIRMED / INFERRED / NEEDS_REVIEW / BLOCKED |
| `source_id` | Stable id from `source_registry.csv` (or `source_registry.json`); `user_confirmation:<ts>` when the source is a verbal/written user confirmation; `none` only if `BLOCKED` |
| `source` | Filename of the document (matches the registry path) |
| `source_locator` | Row, page, sheet, entry id, or `:row=N`, `:page=N`, `:sheet=Tips,row=42-78` |
| `notes` | Free text context, kept short |

If any of these is missing for a material amount, the row is invalid and must not appear in a `CONFIRMED` section.

See `references/confidence-and-sourcing.md` for the rule and `references/output-schemas.md` for the per-template column lists.

---

## 5. Decision log — required-fields schema

Append-only. Never edit past entries. Corrections = new entry with `"corrects": "<original_ts>"`.

**Required fields for every decision touching a material amount:**

```json
{
  "ts": "2026-04-27T08:15",
  "entity": "entity-slug-or-global-or-cross-entity",
  "field": "what is being decided",
  "value": "the value or label",
  "basis": "source-based, methodological, or user-instruction reason; never a legal interpretation",
  "source_id": "stable id from source_registry (or user_confirmation:<ts>)",
  "source": "filename matching the registry",
  "source_locator": "row, page, sheet, or entry id",
  "confidence_status": "CONFIRMED|INFERRED|NEEDS_REVIEW|BLOCKED",
  "session": "session identifier"
}
```

Optional fields: `corrects`, `notes`, `resolution_status` (only when the decision closes an exception).

**`basis` is not legal advice.** Acceptable forms:
- "User confirmation in STANDUP on <date>"
- "Source document on file, value extracted from `<file>:<locator>`"
- "Methodological choice: per-entity reconciliation per Skill `architecture-per-entity.md`"
- "Question routed to trustee — value stays NEEDS_REVIEW until trustee responds"

Unacceptable: any sentence that interprets a statute or chooses a tax/legal posture. Those go into `Questions for trustee/accountant/counsel` in the trustee briefing, never into `basis`.

See `references/output-schemas.md` for full schema details.

---

## 6. Daily collaboration loop

**Morning (15 min):**
1. User overwrites `STANDUP.md` with 3 blocks:
   - SINCE LAST SESSION (what changed offline)
   - TODAY I HAVE (hard constraints)
   - GOAL TODAY (one entity or one topic)
2. User starts session with: "Read STANDUP.md then FORENSIC_STATUS.md."
3. Skill responds in 3 lines: read state / one task / what NOT to touch

**Work (30-45 min max):**
- Touch one entity at a time. Read its `STATUS.md` first.
- For every classification: append `decisions.jsonl` with required fields including `confidence_status`, `source_id`, `source`, `source_locator`, `basis`.
- Cite source for every number. If you cannot, mark `BLOCKED` and add a fetch-next entry to `FORENSIC_STATUS.md`.

**End of session (5 min):**
- Rewrite touched entity `STATUS.md`
- Rewrite `FORENSIC_STATUS.md` (especially OPEN GAPS, NEXT ACTION, BLOCKED ON, FETCH NEXT)
- Append `SESSION_LOG.md` with: what changed, decisions logged, open at end, next priority, files NOT touched

See `references/workflow-checklists.md` for the full checklists.

---

## 7. Routing — what stays in scope, what defers

| Topic | Action |
|---|---|
| Bank/CC parsing, transfer detection, classification | In scope — see `references/pipeline-technical.md` if a pipeline is wired in |
| Per-entity reconciliation (payroll, taxes, employees) | In scope — work in `entities/<slug>/` |
| Building trustee deliverables from sourced data | In scope — use templates in `assets/templates/` |
| Insolvency procedure, statutory deadlines, BIA filings | **Defer to the trustee** |
| Legal interpretation, settlement strategy, negotiation tactics | **Defer to the trustee or qualified counsel** |
| Tax advice, voluntary disclosure, T2/CO-17 elections | **Defer to a qualified accountant or qualified counsel** |
| Director liability defense | **Out of scope — defer to qualified counsel** |

Use the generic phrases in `references/routing-boundaries.md`. Do not name a specific person.

---

## 8. Pipeline (technical, optional)

If the working directory has a Python pipeline (parsers, reconciliation, CC classification), the technical reference is in `references/pipeline-technical.md`. The Skill works without the pipeline — it accelerates entities where you have raw bank/CC files.

---

## 9. References (read on demand)

| File | When to consult |
|---|---|
| `references/confidence-and-sourcing.md` | Any time you classify or deposit a number |
| `references/output-schemas.md` | Building any deliverable (decisions.jsonl, STATUS.md, source-registry, trustee-briefing) |
| `references/workflow-checklists.md` | Daily start/end, weekly review, trustee email cadence |
| `references/routing-boundaries.md` | Anything touching legal/tax/strategy |
| `references/architecture-per-entity.md` | Tempted to consolidate into one master? Read this first. |
| `references/pipeline-technical.md` | Touching bank/CC parsers or classification engine |

---

## 10. Templates (read-only — copy when needed)

In `assets/templates/`:
- `STATUS.md` — per-entity status template
- `FORENSIC_STATUS.md` — global cold-start template (includes FETCH NEXT section)
- `STANDUP.md` — daily user dump template
- `decision-entry.jsonl` — decision log entry example (anonymous)
- `source-registry.csv` — canonical document/source registry template
- `exception-log.csv` — durable exception tracking (dual confidence + resolution status)
- `trustee-briefing.md` — handoff doc template (every amount sourced)
- `employee-claims.csv`, `das-tax-schedule.csv`, `creditor-schedule.csv`, `personal-debt-schedule.csv`

---

## 11. Validation

Before any trustee handoff, run the validator from the public pipeline repo:

```bash
python3 scripts/validate_package.py <insolvency-root> --mode package --strict
# add --handoff to require trustee briefing and forbid INFERRED in confirmed sections
```

Modes:
- `--mode template` — schema validation only; placeholders allowed (use against this Skill itself)
- `--mode package` (default) — required schedules/logs/registry/trustee briefing must exist; placeholders fail
- `--strict` — every `CONFIRMED` row must reference a registered source, SHA256 must match, no forbidden statuses
- `--handoff` — implies `--strict`, plus requires trustee-briefing and forbids INFERRED rows in confirmed sections

A non-zero exit means do not deliver.

---

## 12. Trigger keywords (for auto-activation)

This skill should activate on user mentions of: insolvency, bankruptcy, consumer proposal, syndic, trustee, restaurant insolvency, forensic bookkeeping, bank reconciliation, inter-company transfers, employee claims, vacation pay due, unpaid wages, tips reconciliation, DAS, source deductions, RP federal, RS Quebec, CNESST, T2, CO-17, TVQ, creditor schedule, supplier reconciliation, trustee package, dossier syndic.

---

## 13. What is NOT in this Skill

- ChatGPT / OpenAI Skill packaging (`agents/openai.yaml`) — deferred to v2
- Named-person routing — this Skill is anonymous and reusable
- Case-specific financial totals or account mappings — those live in local working files, never in the Skill
- Legacy v3.2 quick-start (see `legacy/`) — kept for historical reference only, not part of the active workflow

---

*v1.2 — 2026-04-27. Claude-first, anonymized, reusable across debtors. Local working files retain real names. Legacy v3.2 quick-start is archived under `legacy/` and is not the v1.2 entry point.*
