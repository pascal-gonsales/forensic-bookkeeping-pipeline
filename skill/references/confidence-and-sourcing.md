# Confidence & Sourcing — Reference

> The single most important reference in this skill. Every number you produce will eventually be reviewed by a trustee, possibly by a court.

---

## The 4 confidence statuses (use these, only these)

| Status | When |
|---|---|
| `CONFIRMED` | Source document on file AND user has explicitly confirmed the value/classification, recorded in `decisions.jsonl`. |
| `INFERRED` | Probable from a data pattern (e.g. recurring monthly $X to the same payee). Must be flagged for human review before trustee deposit. Never escalate to CONFIRMED without user. |
| `NEEDS_REVIEW` | Default for any new item. Ambiguous classification, missing context, or split-decision required. |
| `BLOCKED` | A required source document is missing. Cannot complete until external action (bank pull, portal download, trustee answer). |

**Forbidden:** `VERIFY`, `MAYBE`, `LOOK INTO`, `TBD`, blank. Always one of the four above.

**Lifecycle vs confidence — do not mix.** When tracking exceptions, the workflow state is `OPEN | RESOLVED | SUPERSEDED` and lives in a separate `resolution_status` column. `confidence_status` is about the value's epistemic state, not the ticket's lifecycle.

---

## Required source-traceability columns on every material amount

Every row that carries a material amount (employee claim, tax balance, creditor, personal debt, intercompany, exception with money attached, briefing line) must carry these columns at minimum:

| Column | Meaning |
|---|---|
| `amount` | The number itself |
| `confidence_status` | CONFIRMED / INFERRED / NEEDS_REVIEW / BLOCKED |
| `source_id` | Stable id from `source_registry.csv` (or `source_registry.json`); or `user_confirmation:<ts>:<context>`; or `none` only if `BLOCKED` |
| `source` | Filename of the cited document (matches the registry path) |
| `source_locator` | `:row=N`, `:page=N`, `:sheet=Tips,row=42-78`, `entry=<id>`, etc. |
| `notes` | Free text context, kept short |

If any of these is missing for a material amount, the row is invalid and must not appear in a `CONFIRMED` section of any deliverable.

---

## Source citation format (inside narrative text)

When citing a source in prose or in a `source_locator` field, use:

```
<filename>:<row_or_page_or_sheet>
```

Examples (anonymous):
- `payroll-reconciliation-vN.xlsx:Sheet=Tips,Rows=42-78`
- `RP_Federal_etat-compte_YYYY-MM-DD.pdf:Page=2`
- `master_transactions.csv:Row=1247`
- `decisions.jsonl:Entry=2026-04-22T09:14`

If the source is a verbal/written user confirmation:
- `user_confirmation:2026-04-27T08:30:STANDUP`

If you cannot cite, the answer is `unverified`. Stop and ask, or mark `BLOCKED` and add a FETCH NEXT row to `FORENSIC_STATUS.md`.

---

## SHA256 anchoring (for evidence)

For any source file that grounds a `CONFIRMED` number, the file must be in the `source_registry` (CSV or JSON) with its SHA256 hash. This anchors the file content to a specific moment — if the file changes later, the hash check fails and dependent decisions are flagged for re-verification.

Compute by hand: `shasum -a 256 <file>` on macOS.
Build/refresh registry: `python3 scripts/source_registry.py <insolvency-root>` from the public pipeline repo.
Verify before handoff: `python3 scripts/validate_package.py <insolvency-root> --mode package --strict --handoff`.

---

## The "cite or unverified" rule

When asked for a number you do not have an explicit source for:

DO NOT write:
- "I think it is around $X"
- "Based on similar entities, probably $X"
- "Let me estimate: $X"

DO write:
- "Unverified — no source on file. FETCH NEXT: <document name> from <portal>"
- "Inferred from <pattern>; value approximately $X — `confidence_status: INFERRED`, flagged for review"
- "$X per `<filename>:<locator>`, `confidence_status: CONFIRMED`, `source_id: SRC-XXX`"

---

## Why this matters

Quebec courts have already sanctioned parties for relying on AI-generated content that was unsourced. For a debtor without legal counsel collaborating with a trustee, every number on a Form 78 attachment is sworn evidence. An AI-fabricated number that gets sworn becomes legal exposure for the debtor.

The right pattern: AI is the extraction and organization layer. The user is the verification and attestation layer. The Skill enforces that wall.

---

## Anti-pattern catalog

| Anti-pattern | Why it kills you | Correct behavior |
|---|---|---|
| Estimating a missing number "to keep the report flowing" | Estimate becomes sworn fact | `BLOCKED` + FETCH NEXT row |
| Auto-classifying a mixed-use merchant (Apple, Uber, Walmart, gas, etc.) | Splits without source = unsupported deduction | `NEEDS_REVIEW` until user provides the split with a source |
| Reading an analysis note from last session and treating its conclusions as source | AI-on-AI citation loop, error compounds | Re-verify against `type: source` notes only |
| Saying "based on the spreadsheet" without naming the file | No traceability, fails trustee challenge | Always cite filename + `source_locator` |
| Auto-computing a 50% (or any %) split for partner trips, mixed-use, team-building | Invented split = invented amount | Mark `NEEDS_REVIEW`, ask user for the actual split with source |
| Updating a STATUS.md without changing `last_updated` | Skill will not flag as fresh; future drift risk | Always touch `last_updated` when modifying |
| Using a `status` column for both confidence (CONFIRMED) and lifecycle (RESOLVED) | One column, two meanings = drift | Use `confidence_status` and `resolution_status` separately |
| Putting a statutory interpretation into `basis` | Becomes legal advice from the Skill | Move it to `Questions for trustee/accountant/counsel` in the briefing |
