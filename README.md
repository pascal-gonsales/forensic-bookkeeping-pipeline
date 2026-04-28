# Forensic Bookkeeping Pipeline + Skill (v1.2)

A production-grade forensic accounting system that processes 13,000+ bank transactions across 5 interlinked business entities, reconciles inter-company transfers, and classifies personal credit card expenses.

Built to handle real-world complexity: multi-format bank statements (CSV + PDF), French/English bilingual documents, Quebec tax law (GST 5% + QST 9.975%), and corporate group structures with shareholder advances.

> **This repo ships two things:** (1) the **Python pipeline** (root) — production-tested forensic engine; (2) the **Claude Skill v1.2** at [`/skill/`](skill/) — anti-drift operating contract that turns the pipeline into a trustee-defensible workflow when used with Claude Code. Both anonymized, both reusable across debtors.

## What It Does

1. **Multi-format parsing** - Ingests Desjardins CSV (14-column), RBC CSV (5-column), and Amex CSV with comma decimals. Format detected by content inspection, never by filename.

2. **Coordinate-based PDF extraction** - Uses `pdfplumber` word coordinates to deterministically classify amounts as debit/credit based on column position. 99% accuracy validated against CSV ground truth (24/24 statements, $0 variance). Seven PDF formats supported: Desjardins (bank, business CC, personal Visa), RBC (bank, Visa), BDC Mastercard, TD Aeroplan Visa.

3. **Inter-company reconciliation** - Bidirectional matching of transfers between entities. 610/624 pairs matched (98%). Unmatched transfers flagged with date tolerance (+-3 days).

4. **Credit card classification** - 105+ regex rules classify 1,364 transactions ($691K) as business/personal/team-building. Ambiguous items ($7K) routed to a manual-review queue (`VERIFY`) rather than guessed — the system never invents a classification on mixed-use merchants.

5. **Audit trail** - Immutable decision log (JSONL), SHA256 checksums, session state management for multi-day analysis continuity.

## Architecture

```
pipeline.py           Main orchestrator - file discovery, transfer detection, reporting, categorization
parsers.py            Multi-format CSV parsers with content-based format detection
pdf_parsers_v2.py     Coordinate-based PDF extraction (debit/credit by x-position) + format detector
cc_classification.py  Business vs personal expense classification (105+ rules)
reconciliation.py     Bidirectional inter-company transfer matching
test_parsers.py       Test suite (smoke + per-format integration tests with skip-if-fixture-missing)
scripts/
  source_registry.py  Catalogue source documents with SHA256 + verification metadata
  validate_package.py Pre-flight validator before trustee handoff (template/package/strict/handoff modes)
tests/synthetic/      Synthetic-data tests (no real bank statements; safe on any clone)
skill/                Forensic-bookkeeping Skill v1.2 (Claude operating contract)
  SKILL.md              main definition: anti-drift rules, anonymity, hard rules, cold-start protocol
  references/           6 deep-dive guides: architecture, sourcing, output schemas, routing, workflows
  assets/templates/     10 working templates: STATUS, FORENSIC_STATUS, STANDUP, creditor schedule,
                        employee claims, DAS schedule, source registry, trustee briefing, decisions JSONL
```

## Forensic Skill v1.2 — operating contract

The pipeline alone is just code; the skill is what makes it **trustee-defensible**. When used with Claude Code, the skill enforces:

- **Source traceability** — every number must cite source file + row/page/sheet/entry id; if uncitable, status is `unverified` and Claude stops (no rounding, no interpolation, no "reasonable estimate")
- **`NEEDS_REVIEW` by default** — values escalate to `CONFIRMED` only with source document on file AND user confirmation
- **No invented insolvency facts** — amounts, creditors, employee balances, tax balances, dates, classifications. If missing, write `BLOCKED` and a fetch-next entry
- **Routing on legal/tax/strategic questions** — Claude routes to trustee, accountant, or qualified counsel; never freelances on BIA / ITA / LAF / CCQ / LACC / Loi sur les normes du travail
- **Cold-start + end-of-session protocols** — every session reads STANDUP → FORENSIC_STATUS → decisions.jsonl tail → entity STATUS, and ends by rewriting STATUS, FORENSIC_STATUS, appending SESSION_LOG and decisions.jsonl
- **Anonymity rule** — the skill itself contains zero real names; debtor-specific identifiers (e.g. trustee name) come from runtime env vars (`TRUSTEE_NAME`)

See [`skill/SKILL.md`](skill/SKILL.md) for the full v1.2 contract and [`skill/references/`](skill/references/) for the 6 detailed guides.

## Key Technical Decisions

- **Content over filenames**: A file named "Desjardins" could contain RBC data. Every file is classified by its actual content structure.
- **Coordinate geometry for PDFs**: Text-based parsing achieved ~85% accuracy. Switching to word x-coordinates for column detection pushed accuracy to 99%.
- **Bidirectional matching**: Each inter-company transfer appears twice (outflow from sender, inflow at receiver). Only outflows are counted to prevent double-counting.
- **No gap-filling**: When data is missing or ambiguous, the system flags it rather than estimating. Every number traces to a source file.
- **Manual-review queue is a feature**: Mixed-use merchants (Apple, Uber, Walmart, gas stations) are intentionally routed to `VERIFY` before any business-rule check fires. A reviewer must confirm. The pipeline never auto-classifies.

## Results

| Metric | Value |
|--------|-------|
| Bank transactions processed | 13,081 |
| Source files parsed | 223 (75 CSV + 148 PDF) |
| Inter-company match rate | 98% (610/624 pairs) |
| PDF extraction accuracy | 99% (validated vs CSV) |
| Categorization rate | 94.17% (was 86.8% pre-rule-tuning) |
| CC transactions classified | 1,364 ($691K total) |
| CC business expenses identified | $640K |
| CC routed to manual-review queue | $7K |
| Personal transfers tracked | 656 ($1.9M) |

## Documentation

- `docs/pdf-extraction-methodology.md` - Research on PDF parsing approaches and why coordinate-based extraction wins
- `docs/cc-reconciliation-methodology.md` - Credit card reconciliation algorithm (4-pass approach)
- `docs/session-continuity-framework.md` - How to maintain forensic accuracy across multi-day analysis sessions

## Tech Stack

Python 3.11+ | pdfplumber | csv | dataclasses | pathlib

## Known Limitations

Forensic transparency: the following gaps are documented rather than estimated.

- **June 2024 RBC statement permanently missing** for one entity (RBC archive limit exceeded). The pipeline's hidden-transaction detector catches the gap automatically; the value is left blank rather than interpolated.
- **August-December 2025 entity assignment** for centralized expenses requires invoice data from suppliers (SUPPLIER_A, SUPPLIER_B, SUPPLIER_D) that has not yet been received. The pipeline ingests the transactions but flags the entity column as `unassigned`.
- **199 mixed-use CC transactions** ($7K) sit in the `VERIFY` queue by design. These are merchants where business vs. personal cannot be determined from the description alone (Apple, UberEats, Walmart, gas stations). Manual review is the intended path.
- **331 transactions have no description** in the source (~$775K). They are quarantined under the `no_description` category — visible to the reviewer, never silently rolled into other buckets.
- **CI fixture absence**: the integration tests for CSV/PDF parsers depend on private bank-statement fixtures and skip cleanly on a fresh clone. Only the import smoke test runs in CI. Local validation is the canonical signal.

## Note on anonymization

All entity names, account numbers, supplier names, and personal identifiers have been anonymized. The code structure, algorithms, and methodology are preserved exactly as used in production. The anonymization mapping is consistent across all files (e.g. `Owner_A`, `Restaurant_A` style placeholders).

**Debtor-specific configuration via env vars** (v1.2): the trustee name is read from `TRUSTEE_NAME` env var at runtime. Public OSS distribution leaves it unset. Local working copies set it in `~/.config/wwithai/credentials.env` or shell env to register a debtor-specific categorization rule. The generic `trustee|syndic` regex still catches generic mentions in either configuration.

## License

All rights reserved. This repository is published as a methodology and code reference. Not licensed for derivative use.
