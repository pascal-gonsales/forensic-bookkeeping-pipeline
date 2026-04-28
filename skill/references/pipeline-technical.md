# Pipeline Technical Reference

> Read this only if the working directory has the Python forensic-bookkeeping pipeline (parsers, reconciliation, CC classification engine). If not, this file is not relevant.

---

## Overview

The pipeline is a Python codebase that:
1. Discovers bank statement files (CSV + PDF) across a `BASE_PATH`
2. Routes each file to the right parser by content (never by filename)
3. Extracts transactions into a normalized `Transaction` dataclass
4. Detects inter-company transfers from descriptions (single-side counted)
5. Categorizes via 100+ regex rules
6. Classifies personal credit card transactions (business / personal / team / verify)
7. Outputs CSVs + Markdown reports + an inter-company matrix

Public reference implementation: `pascal-gonsales/forensic-bookkeeping-pipeline` (v1.0.0 release on GitHub).

---

## CRITICAL BUGS that must NOT regress

### 1. Account normalization (5/6 → 7 digits)
PDF account-Folio extraction returns 5-6 digits ("93023" or "091889"). The `ACCOUNT_ENTITY_MAP` uses 7-digit padded keys ("0093023"). Without normalization, entity assignment falls back to filename, which is WRONG when files are mislabeled.

**Fix location:** `pipeline.py` ~line 572. Pad with leading zeros before the map lookup.

**If this regresses:** Two entities with similar account numbers will swap their data silently.

---

### 2. PDF transfer description spaces
CSV format: `/à 092483 EOP` (no space after slash)
PDF format: `/ à 092483 EOP` (space after slash)

**Fix:** `TRANSFER_TO_PATTERN` and `TRANSFER_FROM_PATTERN` use `/\s*[àa]` and `/\s*de` to handle both.

**If this regresses:** Zero inter-company transfers detected from PDFs. Holding advance totals collapse.

---

### 3. Owner-style detection for RBC PDFs
Some RBC patterns use "Virement envoyé <name>" (no Interac keyword). A specific pattern is checked BEFORE the generic `RBC_VIREMENT_ENVOYE`.

**If this regresses:** Reimbursement detection on RBC accounts disappears. Some entities lose tracked reimbursements.

---

### 4. Mislabeled files
Some files have wrong entity names in their filename (e.g. `<EntityX>_2024_06.pdf` actually contains `EntityY` data based on the account number inside). The parser detects by ACCOUNT CONTENT, not filename. This is correct behavior. Do NOT "fix" the entity assignment to match filenames.

---

### 5. Self-transfer filtering
Mislabeled files create apparent "EntityX → EntityX" transfers when content + filename disagree. These are filtered in `reconciliation.py`.

---

### 6. EOP section tracking + FORFAIT lines
"FORFAIT DE FRAIS DE FINANCEMENT" is a VALID transaction line, NOT a section exit marker. Only "SOMMAIRE DES FRAIS" exits the EOP section.

---

### 7. Inter-company double-counting (avoided)
Each transfer appears twice in raw data (outflow from sender, inflow at receiver). Reconciliation counts only ONE side to avoid 2x inflation. If you ever see inter-company totals jump 2x, this filter has regressed.

---

## Standardized statuses (must align with skill)

The CC classification engine and the pipeline categorization MUST use the four skill statuses:
- `CONFIRMED`
- `INFERRED`
- `NEEDS_REVIEW`
- `BLOCKED`

`VERIFY`, `TBD`, `MAYBE`, `LOOK INTO`, blank are forbidden in any new output. Existing legacy outputs that contain `VERIFY` are not v1.2-compliant and must be regenerated before they enter a trustee package.

The pipeline's CC classifier already enforces these v1.2 rules:
- SAQ rule resolved per debtor decision logged in `decisions.jsonl` (CONFIRMED) — no silent default.
- Team-building merchants return `business_amount=None`, `confidence_status=NEEDS_REVIEW`. No auto-split. The user supplies the actual split with a source.
- Default fallback for unmatched merchants: `NEEDS_REVIEW` with `business_amount=None`.

---

## Source registry (v1.2)

`scripts/source_registry.py` — scans the working tree for source documents (PDFs, CSVs, XLSX), computes SHA256, writes `source_registry.json` (the canonical CSV form is `source_registry.csv` in the Skill templates). Run after every batch of new documents added.

Required fields per entry (see `references/output-schemas.md`):

```
source_id, path, sha256, size_bytes, first_seen, last_verified,
entity, domain, document_type, obtained_from, date_on_document, notes
```

Decisions in `decisions.jsonl` cite `source_id` AND `source` (filename) AND `source_locator`. The registry lets a reviewer verify the file content has not changed since the decision was made; the validator recomputes SHA256 in `--strict` mode.

---

## Validation gate (v1.2)

`scripts/validate_package.py` — pre-flight check before producing a trustee deliverable.

Modes:
- `--mode template` — schema validation only; placeholder rows allowed (used to lint the Skill itself).
- `--mode package` (default) — required schedules/logs/registry must exist; placeholder source/status fail.
- `--strict` — `CONFIRMED` rows must reference a registered source; SHA256 must match; forbidden statuses fail.
- `--handoff` — implies `--strict`, plus requires the trustee briefing and forbids `INFERRED` rows in confirmed sections.

Required outputs in package mode:
- `employee-claims.csv`
- `das-tax-schedule.csv`
- `creditor-schedule.csv`
- `personal-debt-schedule.csv`
- `exception-log.csv`
- `decisions.jsonl`
- `source_registry.csv` (or `source_registry.json`)

In `--handoff` mode, additionally:
- `trustee-briefing.md`

Exit codes:
- 0 — package is ready to deliver
- 1 — validation failed (one or more rules violated)
- 2 — registry mismatch (run `source_registry.py` and review changed sources before deliver)

---

## Output files

| File | Contents |
|---|---|
| `output/master_transactions.csv` | All bank/CC transactions with classification |
| `output/transfers_all.csv` | All detected inter-company / personal transfers |
| `output/cc_personal_classified.csv` | Personal CC with status (CONFIRMED / INFERRED / NEEDS_REVIEW) |
| `output/INTERCO_RECONCILIATION.md` | Per-month inter-company matrix + report |
| `output/exception_log.csv` | Durable exception log (replaces in-memory anomalies) |

---

## Tests

`test_parsers.py` runs:
- Smoke test: imports + API surface (always runs)
- CSV parser tests (skip if fixtures absent)
- PDF parser tests (skip if fixtures absent)

CI runs only the smoke test (no private fixtures). Local runs with fixtures = full validation.

**Synthetic v1.2 safety tests** live at `tests/synthetic/test_validator_safety.py`. They cover:
- empty package fails in `--mode package`
- skill templates pass in `--mode template`
- placeholder source/source_id fails in package mode
- forbidden status (`VERIFY`) fails in package mode
- `CONFIRMED` row without registry entry fails in `--strict`
- SHA256 mismatch in `--strict` exits 2
- `INFERRED` row in confirmed-section deliverable fails in `--handoff`
- `decisions.jsonl` row missing `confidence_status` fails
- exception-log mixing lifecycle (`OPEN/RESOLVED`) and confidence (`CONFIRMED`) into the same column fails
- classifier returns `business_amount=None`/`status=NEEDS_REVIEW` for split/ambiguous and unmatched merchants

Run: `python3 tests/synthetic/test_validator_safety.py` (no private fixtures required).

Future fixtures to consider (P2):
- Missing month statements
- Duplicate transactions
- Interac ambiguity
- Employee advances over-paid
- Tax-balance gaps marked `BLOCKED` in `das-tax-schedule.csv`

---

## Pipeline + skill integration

The skill is the PROCESS layer. The pipeline is one TOOL the process uses. The skill works without the pipeline (e.g. for entities where you only have Excel reconciliations). The pipeline accelerates entities where you have raw bank/CC files.

When user requests a pipeline action ("re-run categorization", "re-discover files"), apply skill rules:
- Cite source for every output
- NEEDS_REVIEW default for any new classification
- Log decisions in `decisions.jsonl`
- Update `entities/<slug>/STATUS.md` with new evidence

Never run the pipeline silently. Every run produces a SESSION_LOG entry.
