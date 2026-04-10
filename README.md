# Forensic Bookkeeping Pipeline

A production-grade forensic accounting system that processes 13,000+ bank transactions across 5 interlinked business entities, reconciles inter-company transfers, and classifies personal credit card expenses.

Built to handle real-world complexity: multi-format bank statements (CSV + PDF), French/English bilingual documents, Quebec tax law (GST 5% + QST 9.975%), and corporate group structures with shareholder advances.

## What It Does

1. **Multi-format parsing** - Ingests Desjardins CSV (14-column), RBC CSV (5-column), and Amex CSV with comma decimals. Format detected by content inspection, never by filename.

2. **Coordinate-based PDF extraction** - Uses `pdfplumber` word coordinates to deterministically classify amounts as debit/credit based on column position. 99% accuracy validated against CSV ground truth (24/24 statements, $0 variance).

3. **Inter-company reconciliation** - Bidirectional matching of transfers between entities. 610/624 pairs matched (98%). Unmatched transfers flagged with date tolerance (+-3 days).

4. **Credit card classification** - 105+ regex rules classify 1,364 transactions ($691K) as business/personal/team-building. Ambiguous items ($33K) flagged for manual review rather than guessed.

5. **Audit trail** - Immutable decision log (JSONL), SHA256 checksums, session state management for multi-day analysis continuity.

## Architecture

```
pipeline.py           Main orchestrator - file discovery, transfer detection, reporting
parsers.py            Multi-format CSV parsers with content-based format detection
pdf_parsers_v2.py     Coordinate-based PDF extraction (debit/credit by x-position)
cc_classification.py  Business vs personal expense classification (105+ rules)
reconciliation.py     Bidirectional inter-company transfer matching
generate_pdf_report.py  PDF report generation with monthly matrices
```

## Key Technical Decisions

- **Content over filenames**: A file named "Desjardins" could contain RBC data. Every file is classified by its actual content structure.
- **Coordinate geometry for PDFs**: Text-based parsing achieved ~85% accuracy. Switching to word x-coordinates for column detection pushed accuracy to 99%.
- **Bidirectional matching**: Each inter-company transfer appears twice (outflow from sender, inflow at receiver). Only outflows are counted to prevent double-counting.
- **No gap-filling**: When data is missing or ambiguous, the system flags it rather than estimating. Every number traces to a source file.

## Results

| Metric | Value |
|--------|-------|
| Bank transactions processed | 13,081 |
| Source files parsed | 223 (75 CSV + 148 PDF) |
| Inter-company match rate | 98% (610/624 pairs) |
| PDF extraction accuracy | 99% (validated vs CSV) |
| CC transactions classified | 1,364 ($691K total) |
| CC business expenses identified | $640K |
| CC flagged for manual review | $33K |
| Personal transfers tracked | 656 ($1.9M) |

## Documentation

- `docs/pdf-extraction-methodology.md` - Research on PDF parsing approaches and why coordinate-based extraction wins
- `docs/cc-reconciliation-methodology.md` - Credit card reconciliation algorithm (4-pass approach)
- `docs/session-continuity-framework.md` - How to maintain forensic accuracy across multi-day analysis sessions

## Tech Stack

Python 3.11+ | pdfplumber | csv | dataclasses | pathlib

## Note

All entity names, account numbers, supplier names, and personal identifiers have been anonymized. The code structure, algorithms, and methodology are preserved exactly as used in production.
