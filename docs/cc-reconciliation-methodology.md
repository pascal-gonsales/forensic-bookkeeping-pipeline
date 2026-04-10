# Credit Card Reconciliation Methodology — Research & Best Practices
**Context:** Demo Restaurant Group forensic bookkeeping. Personal CC transactions (from Ralf's Excel) vs. bank/CC statements (PDF/CSV). Insolvency/consumer proposal context requires defensible audit trail.

**Date:** 2026-03-30

---

## 1. METHODOLOGY: Matching CC Statement vs. Hand-Filled Excel

### The Core Problem
You have two data sources:
- **Source A (CC Statements):** CSV/PDF with date, description (merchant name), amount, card number. Machine-generated, authoritative.
- **Source B (Ralf's Excel):** Hand-filled tabs with date, supplier name, amount, company assignment (which restaurant the expense belongs to). Human-entered, potentially inaccurate.

The goal is to match every row in Source B to exactly one row in Source A, and flag anything that doesn't match in either direction.

### Recommended Matching Order

**Amount first, then date, then description.** Here's why:

1. **Amount is the most reliable field.** Even a sloppy bookkeeper writes down the dollar amount correctly because it comes from the receipt. Amounts are rarely transcribed wrong — they're numbers, not free text.

2. **Date is second.** Hand-entered dates can drift by 1-3 days from the actual transaction posting date. The CC statement shows the posting date; Ralf's Excel might show the purchase date, the receipt date, or the date he entered it. A tolerance of **+/- 3 calendar days** is standard in forensic reconciliation. For month-end transactions, extend to **+/- 5 days** (a Dec 30 purchase might post Jan 2).

3. **Description is least reliable for matching** but most useful for validation. CC statements say "SUPPLIER_ALPHASERVICEOWNER_BM" while Ralf's Excel says "Damen" or "Owner_Bmentaire". Use description for confirming matches, not finding them.

### Tolerance Recommendations

| Field | Exact Match | Fuzzy Match | Notes |
|-------|------------|-------------|-------|
| Amount | +/- $0.00 | +/- $0.05 | Rounding on FX, tips. If amounts differ by more than $0.05, it's a different transaction |
| Date | Same day | +/- 3 days | Extend to +/- 5 at month boundaries. CC posting vs. purchase date |
| Description | N/A | Levenshtein > 0.6 | Only for confirmation, not primary matching |

### The Graduated Matching Algorithm (4 passes)

This is the industry standard approach, and it's what your `reconciliation.py` already partially implements:

**Pass 1 — Perfect match:** Same amount (exact), same date (exact). Highest confidence. Mark as MATCHED_EXACT.

**Pass 2 — Date-fuzzy match:** Same amount (exact), date within +/- 3 days. Mark as MATCHED_DATE_FUZZY.

**Pass 3 — Amount-fuzzy match:** Amount within +/- $0.05, date within +/- 3 days. Mark as MATCHED_AMOUNT_FUZZY. (Rare — only catches FX rounding.)

**Pass 4 — Description-assisted match:** For remaining unmatched, use fuzzy string matching on description/supplier name to suggest possible matches. Mark as SUGGESTED — requires manual review.

After all passes, anything left unmatched in Source A = "on the statement but not in Ralf's Excel" (potentially unreported expense). Anything left unmatched in Source B = "in Ralf's Excel but not on the statement" (potentially fabricated or misattributed).

---

## 2. COMMON PITFALLS

### In Manual Reconciliation
1. **Date confusion:** CC statements show posting date, not purchase date. A Friday purchase posts Monday. A Dec 31 purchase posts Jan 2. Always use a date window, never exact-date-only.

2. **Duplicate matching:** One Excel row accidentally matched to multiple CC charges, or vice versa. Once a transaction is matched, it MUST be removed from the candidate pool. Your current code does this correctly with `used_inflows`.

3. **Amount sign confusion:** CC statements may show charges as positive or negative depending on the bank. Ralf's Excel may or may not use signs. Normalize everything to absolute value for matching, track debit/credit separately.

4. **FX transactions:** If any purchases were in USD or THB, the CC statement shows CAD equivalent, but the Excel might show the original currency amount. Flag any amount that's close but not exact — could be FX.

5. **Returns/credits:** A refund on the CC statement (-$500) may not appear in Ralf's Excel at all, or may appear as a separate line. Match refunds to the original charge if possible.

6. **Partial payments / installments:** A $3,000 Warehouse Club order paid in 3 installments of $1,000 on the CC but entered as one $3,000 line in Excel. This creates a one-to-many mismatch.

7. **Month-end cutoff errors:** Transaction in one month on CC statement, recorded in next month in Excel. This is the most common reconciliation discrepancy in restaurant operations.

8. **Commingled funds:** In your specific case, personal CCs used for business expenses. The CC statement has BOTH personal and business charges. Ralf's Excel should only have business charges. Any CC transaction not in Ralf's Excel could be personal — or it could be a business expense he forgot to record.

### Specific to Your Situation (Insolvency Context)
9. **Confirmation bias:** The person who filled the Excel has an incentive to classify as much as possible as "business" to justify reimbursements. Cross-check classifications against the `cc_classification.py` rules.

10. **Missing receipts:** In insolvency, you need to demonstrate that reimbursed expenses were legitimate. An Excel entry without a matching CC statement transaction is a red flag.

11. **Retroactive entries:** Watch for clusters of entries added to the Excel all at once (same handwriting, same ink, all from different months) — suggests after-the-fact reconstruction rather than real-time bookkeeping.

---

## 3. MATCHING STRATEGIES FOR EDGE CASES

### Split Transactions (One CC Charge, Multiple Excel Rows)

Example: One Warehouse Club charge of $1,500 on the CC, split across "Lotus Kitchen $800" and "Siam House $700" in Ralf's Excel.

**Strategy:**
1. After Pass 1-3 (direct matching), look at unmatched CC transactions.
2. For each unmatched CC transaction, search for combinations of 2-3 unmatched Excel rows on the same date (or +/- 1 day) whose amounts sum to the CC amount.
3. Use a subset-sum approach with tolerance: `abs(cc_amount - sum(excel_amounts)) < $0.05`.
4. Limit combinatorial explosion: only try combinations of 2-4 rows, and only rows from the same supplier or similar description.

```python
from itertools import combinations

def find_split_matches(cc_amount, cc_date, excel_rows, max_parts=3, date_tol=1, amt_tol=0.05):
    """Find combinations of Excel rows that sum to the CC amount."""
    candidates = [r for r in excel_rows
                  if abs((r['date'] - cc_date).days) <= date_tol]

    matches = []
    for n in range(2, max_parts + 1):
        for combo in combinations(candidates, n):
            total = sum(r['amount'] for r in combo)
            if abs(total - cc_amount) <= amt_tol:
                matches.append(combo)
    return matches
```

**Oracle's approach:** Only allow splitting into 2 parts at a time. Match one part, leave the remainder as a new unmatched transaction. This is simpler and more auditable.

### Multiple Same-Amount Transactions on Same Day

Example: 3 Damen deliveries of $500 each on the same day.

**Strategy:**
1. **Sequential consumption:** Match them in order (first CC row to first Excel row, etc.). This works when both sources are in the same order.
2. **Description differentiation:** Even if amounts are identical, descriptions might differ slightly ("SUPPLIER_ALPHA 001" vs "SUPPLIER_ALPHA 002") or time stamps might differ.
3. **Count-based matching:** If the CC has 3x $500 Damen charges and the Excel has 3x $500 Damen entries on the same day, match them as a group. The individual pairing doesn't matter — what matters is the count matches.
4. **Flag if counts differ:** If CC has 3x $500 but Excel has 2x $500, flag the entire group for review.

```python
def match_identical_groups(cc_rows, excel_rows, date_tol=1):
    """Group identical transactions and match by count."""
    from collections import Counter

    def make_key(row, date_tol=0):
        return (round(row['amount'], 2), row['date'])

    cc_groups = Counter(make_key(r) for r in cc_rows)
    excel_groups = Counter(make_key(r) for r in excel_rows)

    for key in cc_groups:
        cc_count = cc_groups[key]
        excel_count = excel_groups.get(key, 0)
        if cc_count != excel_count:
            print(f"MISMATCH: {key} — CC has {cc_count}, Excel has {excel_count}")
```

### Many-to-One (Multiple CC Charges = One Excel Row)

Less common but possible: Ralf enters one line "Damen $1,500" when there were actually 3 charges of $500.

**Strategy:** After direct matching fails for an Excel row, search for combinations of CC transactions from the same merchant within +/- 3 days that sum to the Excel amount. Same subset-sum logic as split transactions, but in reverse.

---

## 4. CARD-TO-TAB MAPPING

### The Problem
Ralf's Excel has tabs labeled "TD 2870" but the actual card ending is 8371. Tab names are unreliable.

### Resolution Strategy (Ranked by Reliability)

**Method 1 — Amount fingerprinting (most reliable):**
Take the first 5-10 transactions from a tab in Ralf's Excel and find which CC statement has those exact amounts on those approximate dates. Each card has a unique "fingerprint" of transaction amounts. Even 3-4 matching amounts in sequence is near-certain identification.

```python
def identify_card_by_fingerprint(excel_tab_rows, all_cc_statements, min_matches=5):
    """Match a tab to a card by finding which statement has the most matching amounts."""
    # Take first 20 rows from the tab
    sample = excel_tab_rows[:20]

    scores = {}
    for card_id, statement_rows in all_cc_statements.items():
        matches = 0
        for excel_row in sample:
            for stmt_row in statement_rows:
                if (abs(excel_row['amount'] - stmt_row['amount']) < 0.05 and
                    abs((excel_row['date'] - stmt_row['date']).days) <= 5):
                    matches += 1
                    break
        scores[card_id] = matches

    best = max(scores, key=scores.get)
    confidence = scores[best] / len(sample)
    return best, confidence, scores
```

**Method 2 — Monthly total comparison:**
Sum all transactions per month in each Excel tab and compare to monthly totals on each CC statement. Monthly totals should match within a few dollars.

**Method 3 — Unique amounts:**
Find transactions with unusual amounts (not round numbers like $500 or $1,000) in the Excel tab. Search for those exact amounts across all CC statements. A charge of $847.33 is virtually unique.

**Method 4 — Date range alignment:**
Check which CC statement covers the same date range as the Excel tab. If a tab has entries from Jan-Jun 2024 and only one card was active during that period, that's the match.

**Method 5 — Ask Ralf.**
Seriously. If the other methods are ambiguous, a 5-minute conversation may resolve it faster than hours of analysis.

### Documentation
Once identified, create a mapping table and include the evidence:

| Excel Tab | Actual Card | Confidence | Evidence |
|-----------|-------------|------------|----------|
| TD 2870 | TD *8371 | 98% | 18/20 sample amounts matched |
| Desj Perso | Desj *4002 | 95% | Monthly totals within $5 for 8 months |

---

## 5. AUDIT TRAIL FOR LEGAL/INSOLVENCY DEFENSIBILITY

In a Canadian insolvency context (BIA/CCAA), the trustee and creditors need to see that personal CC reimbursements were legitimate. CPA Canada's SPIFA (Standard Practices for Investigative and Forensic Accounting Engagements) governs this.

### Required Documentation

**A. Methodology Document** (you're building this now)
- Describe the matching algorithm, tolerances used, and why
- Document all data sources with file hashes and dates obtained
- Explain each classification rule and its rationale
- This document should be written BEFORE running the analysis, not after

**B. Complete Transaction Ledger**
- Every CC transaction with its match status and classification
- Fields: date, description, amount, card, match_status, matched_to (Excel row ref), classification, business_amount, notes
- Export as CSV with row IDs for traceability

**C. Match Evidence File**
For each matched pair:
- CC statement row (date, desc, amount, card, PDF page reference)
- Excel row (date, supplier, amount, company assignment, tab name)
- Match type (exact, date_fuzzy, split, group, manual)
- Match confidence score
- Reviewer initials and date reviewed

**D. Exception Report**
- All unmatched CC transactions (on statement but not in Excel)
- All unmatched Excel transactions (in Excel but not on statement)
- All split matches (one-to-many or many-to-one)
- All same-amount-same-day groups where counts don't match
- All description mismatches (Excel says "Damen" but CC says "Warehouse Club")

**E. Summary Statistics**
- Total CC charges vs. total Excel entries (by card, by month)
- Match rate (% of transactions matched)
- Business vs. personal vs. verify breakdown (from cc_classification.py)
- Total reimbursement claimed vs. total CC business expenses confirmed

**F. Data Integrity Checksums**
- SHA-256 hash of every input file (CC statements, Excel workbook)
- Date each file was obtained and from whom
- Chain of custody: who provided the Excel, when, in what format

### What Makes It "Defensible"

1. **Reproducibility:** Anyone can re-run the Python pipeline on the same inputs and get the same outputs.
2. **Conservatism:** When in doubt, classify as VERIFY, not BUSINESS. Let the trustee decide.
3. **Transparency:** Every match decision is logged with its reasoning.
4. **Completeness:** 100% of transactions accounted for (matched, unmatched, or excluded with reason).
5. **Independence:** The analysis was performed by someone other than the person claiming the reimbursements.

---

## 6. TOOLS & TECHNIQUES

### Python Libraries (Available in Your .venv)

| Library | Purpose | Status |
|---------|---------|--------|
| `pandas` | Data manipulation, merging, grouping | Install needed |
| `openpyxl` | Read Ralf's Excel tabs | Installed |
| `pdfplumber` | Parse CC statement PDFs | Installed |
| `difflib` | Built-in fuzzy string matching | Available (stdlib) |
| `recordlinkage` | Academic-grade record linkage with blocking, comparison, classification | Install needed |
| `fuzzywuzzy` / `thefuzz` | Levenshtein-based string matching | Install needed |
| `hashlib` | SHA-256 file checksums | Available (stdlib) |

### Recommended Stack for This Project

```
pandas          — dataframe operations, merge, groupby
openpyxl        — read Excel tabs
pdfplumber      — already used for CC statement PDFs
difflib         — SequenceMatcher for description matching (no install needed)
```

You do NOT need `recordlinkage` or `fuzzywuzzy` for this project. Your matching is primarily numeric (amount + date), and `difflib.SequenceMatcher` handles the description confirmation step fine. Keep dependencies minimal for reproducibility.

### Key Code Pattern: Graduated Matching

```python
import pandas as pd
from datetime import timedelta
from difflib import SequenceMatcher

def reconcile_cc_vs_excel(cc_df, excel_df, date_tol_days=3, amount_tol=0.05):
    """
    4-pass graduated matching: CC statement rows vs Excel rows.
    Returns: matched_pairs, unmatched_cc, unmatched_excel
    """
    cc_remaining = set(cc_df.index)
    excel_remaining = set(excel_df.index)
    matched = []

    # PASS 1: Exact amount + exact date
    for ci in list(cc_remaining):
        for ei in list(excel_remaining):
            if (abs(cc_df.loc[ci, 'amount'] - excel_df.loc[ei, 'amount']) < 0.01 and
                cc_df.loc[ci, 'date'] == excel_df.loc[ei, 'date']):
                matched.append((ci, ei, 'EXACT', 1.0))
                cc_remaining.discard(ci)
                excel_remaining.discard(ei)
                break

    # PASS 2: Exact amount + fuzzy date (+/- N days)
    for ci in list(cc_remaining):
        for ei in list(excel_remaining):
            date_diff = abs((cc_df.loc[ci, 'date'] - excel_df.loc[ei, 'date']).days)
            if (abs(cc_df.loc[ci, 'amount'] - excel_df.loc[ei, 'amount']) < 0.01 and
                date_diff <= date_tol_days):
                confidence = 1.0 - (date_diff * 0.1)  # Degrade by 0.1 per day off
                matched.append((ci, ei, 'DATE_FUZZY', confidence))
                cc_remaining.discard(ci)
                excel_remaining.discard(ei)
                break

    # PASS 3: Fuzzy amount + fuzzy date
    for ci in list(cc_remaining):
        for ei in list(excel_remaining):
            date_diff = abs((cc_df.loc[ci, 'date'] - excel_df.loc[ei, 'date']).days)
            amt_diff = abs(cc_df.loc[ci, 'amount'] - excel_df.loc[ei, 'amount'])
            if amt_diff <= amount_tol and date_diff <= date_tol_days:
                confidence = 0.8 - (date_diff * 0.1) - (amt_diff * 2)
                matched.append((ci, ei, 'AMOUNT_FUZZY', confidence))
                cc_remaining.discard(ci)
                excel_remaining.discard(ei)
                break

    # PASS 4: Description-assisted (for remaining)
    for ci in list(cc_remaining):
        best_score = 0
        best_ei = None
        for ei in list(excel_remaining):
            date_diff = abs((cc_df.loc[ci, 'date'] - excel_df.loc[ei, 'date']).days)
            if date_diff > 7:  # Wider window for description matching
                continue
            desc_sim = SequenceMatcher(None,
                cc_df.loc[ci, 'description'].upper(),
                excel_df.loc[ei, 'supplier'].upper()
            ).ratio()
            if desc_sim > 0.5:
                score = desc_sim * 0.6 + (1 - date_diff/7) * 0.4
                if score > best_score:
                    best_score = score
                    best_ei = ei

        if best_ei and best_score > 0.5:
            matched.append((ci, best_ei, 'DESCRIPTION_SUGGESTED', best_score))
            cc_remaining.discard(ci)
            excel_remaining.discard(best_ei)

    return matched, cc_remaining, excel_remaining
```

### File Integrity Helper

```python
import hashlib
from pathlib import Path
from datetime import datetime

def compute_file_hashes(directory, pattern='*.*'):
    """Compute SHA-256 hashes for all input files — chain of custody."""
    hashes = []
    for f in sorted(Path(directory).glob(pattern)):
        sha = hashlib.sha256(f.read_bytes()).hexdigest()
        hashes.append({
            'file': f.name,
            'sha256': sha,
            'size_bytes': f.stat().st_size,
            'modified': datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return hashes
```

---

## 7. IMPLEMENTATION PLAN FOR YOUR PIPELINE

Given the existing codebase (`cc_classification.py`, `reconciliation.py`, `pipeline.py`), here's the recommended next step:

### New Module: `cc_reconciliation.py`

**Inputs:**
1. Ralf's Excel workbook (tabs per card, hand-filled)
2. CC statement PDFs/CSVs (already parsed by `pdf_parsers_v2.py`)
3. Card-to-tab mapping (determined by fingerprinting)

**Outputs:**
1. `output/cc_reconciliation_matched.csv` — all matched pairs with confidence
2. `output/cc_reconciliation_unmatched.csv` — exceptions both directions
3. `output/cc_reconciliation_splits.csv` — split/group matches
4. `output/CC_RECONCILIATION_REPORT.md` — human-readable summary
5. `output/file_integrity_hashes.csv` — chain of custody

**Flow:**
1. Load & normalize both sources (dates to YYYY-MM-DD, amounts to absolute float)
2. Run card-to-tab fingerprinting
3. For each card: run 4-pass graduated matching
4. Run split-transaction detection on remainders
5. Run same-amount-same-day group matching
6. Merge with `cc_classification.py` results for business/personal classification
7. Generate all output files

This builds directly on what you have. No new architecture needed.

---

## Sources

- [Transaction Reconciliation: Best Practices — Numeric](https://www.numeric.io/blog/transaction-reconciliation-guide)
- [Credit Card Reconciliation — HighRadius](https://www.highradius.com/resources/Blog/credit-card-reconciliation/)
- [Credit Card Reconciliation — Ramp (2026)](https://ramp.com/blog/how-to-streamline-your-credit-card-reconciliation-process)
- [How to Automate Reconciliations in Python — Mito](https://www.trymito.io/blog/how-to-automate-reconciliations-in-python-a-complete-guide)
- [Python Record Linkage Toolkit Documentation](https://recordlinkage.readthedocs.io/en/latest/about.html)
- [Fuzzy Matching for Reconciliation — Pathway](https://pathway.com/developers/templates/etl/fuzzy_join_chapter1)
- [Forensic and Investigative Accounting — CPA Canada](https://www.cpacanada.ca/business-and-accounting-resources/forensic-and-investigative-accounting)
- [Forensic Accounting in Bankruptcy and Insolvency — AKGVG](https://www.akgvg.com/blog/forensic-accounting-in-bankruptcy-and-insolvency-analysis/)
- [Transaction Tracing in Insolvency Cases — Valid8](https://www.valid8financial.com/resource/how-transaction-tracing-enhances-forensic-analysis-in-insolvency-cases)
- [Commingling Funds — Indinero](https://www.indinero.com/blog/what-to-do-if-you-commingle-personal-and-business-funds/)
- [Oracle: Splitting Unmatched Transactions](https://docs.oracle.com/en/cloud/saas/account-reconcile-cloud/raarc/reconcile_trans_match_splitting_transactions_100x04daf31c.html)
- [Oracle: Reconciliation Matching Rules](https://docs.oracle.com/en/cloud/saas/financials/24c/fairp/reconciliation-matching-rules.html)
- [Reconciliation Rules — Modern Treasury](https://docs.moderntreasury.com/reconciliation/docs/defining-your-reconciliation-rules)
- [Building an Automatic Reconciliation Engine — Midday](https://midday.ai/updates/automatic-reconciliation-engine/)
- [Identifying Personal Expenses in Business — Morones Analytics](https://moronesanalytics.com/is-this-business-or-personal-identifying-personal-expenses-run-through-a-business/)
- [Solving Duplicate Transactions Issues — Daybook Group](https://www.daybookgroup.com/solving-duplicate-transactions-issues/)
