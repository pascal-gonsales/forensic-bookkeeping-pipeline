# Forensic Bookkeeping Pipeline

A production-grade forensic accounting system that processes 13,000+ bank transactions across 5 interlinked business entities, reconciles inter-company transfers, and classifies personal credit card expenses.

Built to handle real-world complexity: multi-format bank statements (CSV + PDF), French/English bilingual documents, Quebec tax law (GST 5% + QST 9.975%), and corporate group structures with shareholder advances.

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
```

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
- **August-December 2025 entity assignment** for centralized expenses requires invoice data from suppliers (Damen, Ferro, Frandon) that has not yet been received. The pipeline ingests the transactions but flags the entity column as `unassigned`.
- **199 mixed-use CC transactions** ($7K) sit in the `VERIFY` queue by design. These are merchants where business vs. personal cannot be determined from the description alone (Apple, UberEats, Walmart, gas stations). Manual review is the intended path.
- **331 transactions have no description** in the source (~$775K). They are quarantined under the `no_description` category — visible to the reviewer, never silently rolled into other buckets.
- **CI fixture absence**: the integration tests for CSV/PDF parsers depend on private bank-statement fixtures and skip cleanly on a fresh clone. Only the import smoke test runs in CI. Local validation is the canonical signal.

## Note on anonymization

All entity names, account numbers, supplier names, and personal identifiers have been anonymized. The code structure, algorithms, and methodology are preserved exactly as used in production. The anonymization mapping is consistent across all files (e.g. `Owner_A`, `Restaurant_A` style placeholders).

## License

All rights reserved. This repository is published as a methodology and code reference. Not licensed for derivative use.
