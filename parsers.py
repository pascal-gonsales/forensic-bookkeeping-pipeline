"""
Forensic Bookkeeping — Multi-format bank statement parsers.

Supported formats:
  1. Desjardins CSV (14-col, no header, quoted fields)
  2. RBC CSV (5-col with header: Date,Description,Debit,Credit,Balance)
  3. Amex CSV (French headers, comma decimals, multi-line addresses)

CRITICAL DESIGN RULE: Format is detected by CONTENT INSPECTION, never by filename.
A file named "Desjardins" could contain RBC data. Trust content, not names.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Transaction:
    date: str                   # ISO YYYY-MM-DD
    description: str
    debit: Optional[float]      # Money out (positive value or None)
    credit: Optional[float]     # Money in (positive value or None)
    balance: Optional[float]    # Running balance if available
    raw_row: dict = field(default_factory=dict, repr=False)  # Original data for audit


@dataclass
class ValidationResult:
    ok: bool
    checks: dict               # name -> {passed, detail}


@dataclass
class ParseResult:
    entity_hint: str            # Suggested entity from filename (NOT authoritative)
    detected_format: str        # 'desjardins_csv' | 'rbc_csv' | 'amex_csv' | 'unknown'
    detected_bank: str          # 'Desjardins' | 'RBC' | 'Amex' | 'Unknown'
    account_number: Optional[str]
    branch_name: Optional[str]
    period_start: Optional[str]
    period_end: Optional[str]
    transactions: list          # List[Transaction]
    validation: ValidationResult
    file_path: str
    warnings: list              # List[str] — anomalies, format mismatches, etc.
    raw_line_count: int         # Total lines in file for audit


# ---------------------------------------------------------------------------
# Safe float parsing
# ---------------------------------------------------------------------------

def _parse_float(val: str) -> Optional[float]:
    """Parse float from string. Returns None if empty/unparseable."""
    if not val or not val.strip():
        return None
    cleaned = val.strip().replace('\xa0', '').replace(' ', '')
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_french_float(val: str) -> Optional[float]:
    """Parse French-format float where comma = decimal ('3,06' -> 3.06).
    Also handles negative with quotes: '-3833,27' -> -3833.27"""
    if not val or not val.strip():
        return None
    cleaned = val.strip().replace('"', '').replace('\xa0', '').replace(' ', '')
    # French: comma is decimal separator, no thousands separator in Amex exports
    cleaned = cleaned.replace(',', '.')
    try:
        return float(cleaned)
    except ValueError:
        return None


def _normalize_date(date_str: str) -> str:
    """Normalize various date formats to YYYY-MM-DD."""
    date_str = date_str.strip()

    # Already ISO: 2025-01-15
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return date_str

    # Desjardins: 2025/01/15
    if re.match(r'^\d{4}/\d{2}/\d{2}$', date_str):
        return date_str.replace('/', '-')

    # Amex French: "21 Jan 2025", "15 Fév 2025", etc.
    MONTHS_FR = {
        'jan': '01', 'fév': '02', 'fev': '02', 'mar': '03', 'avr': '04',
        'mai': '05', 'jun': '06', 'jui': '07', 'jul': '07', 'aoû': '08',
        'aou': '08', 'sep': '09', 'oct': '10', 'nov': '11', 'déc': '12',
        'dec': '12',
    }
    MONTHS_EN = {
        'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05',
        'jun': '06', 'jul': '07', 'aug': '08', 'sep': '09', 'oct': '10',
        'nov': '11', 'dec': '12',
    }
    m = re.match(r'^(\d{1,2})\s+(\w{3,4})\s+(\d{4})$', date_str, re.IGNORECASE)
    if m:
        day, month_str, year = m.groups()
        month_key = month_str.lower()[:3]
        month_num = MONTHS_FR.get(month_key) or MONTHS_EN.get(month_key)
        if month_num:
            return f"{year}-{month_num}-{int(day):02d}"

    # Fallback: return as-is with warning
    return date_str


# ---------------------------------------------------------------------------
# Format detection (by CONTENT, not filename)
# ---------------------------------------------------------------------------

def detect_format(raw: str, file_path: str = '') -> tuple:
    """
    Detect bank statement format by inspecting file content.
    Returns (format_name, confidence, warnings).

    Confidence levels: 'high', 'medium', 'low'
    """
    lines = raw.strip().split('\n')
    if not lines:
        return ('unknown', 'low', ['File is empty'])

    warnings = []
    first_line = lines[0].strip()

    # --- Check for Amex CSV (French headers) ---
    # Header: "Date,Date de traitement,Description,Montant,..."
    if 'Date de traitement' in first_line or 'Montant des dépenses' in first_line:
        return ('amex_csv', 'high', warnings)

    # Also check English Amex header variant
    if 'Processing Date' in first_line and 'Amount' in first_line:
        warnings.append('Amex format appears to be English variant — verify parsing')
        return ('amex_csv', 'medium', warnings)

    # --- Check for RBC CSV (header row) ---
    # Header: "Date,Description,Debit,Credit,Balance" (or slight variations)
    if first_line.startswith('Date') and 'Description' in first_line and 'Balance' in first_line:
        return ('rbc_csv', 'high', warnings)

    # --- Check for Desjardins CSV (no header, 14+ columns, quoted) ---
    # Inspect first non-empty data lines
    desjardins_score = 0
    for line in lines[:10]:
        line = line.strip()
        if not line:
            continue
        # Try CSV parse
        try:
            reader = csv.reader(io.StringIO(line))
            cols = next(reader)
        except Exception:
            continue

        if len(cols) >= 14:
            desjardins_score += 2
        # Column 3 should be record type (EOP, VIS, MCA, etc.)
        if len(cols) >= 4 and cols[2].strip() in ('EOP', 'VIS', 'MCA', 'MCR'):
            desjardins_score += 3
        # Column 4 should be a date YYYY/MM/DD
        if len(cols) >= 4 and re.match(r'\d{4}/\d{2}/\d{2}', cols[3].strip()):
            desjardins_score += 2

    if desjardins_score >= 5:
        return ('desjardins_csv', 'high', warnings)
    elif desjardins_score >= 3:
        warnings.append(f'Desjardins detection score {desjardins_score}/7 — verify format manually')
        return ('desjardins_csv', 'medium', warnings)

    return ('unknown', 'low', [f'Could not detect format. First line: {first_line[:100]}'])


# ---------------------------------------------------------------------------
# Filename cross-check
# ---------------------------------------------------------------------------

def _cross_check_filename(file_path: str, detected_format: str) -> list:
    """Warn if detected format contradicts filename expectations."""
    warnings = []
    fname = Path(file_path).name.lower()

    expected_bank_from_name = None
    if 'desjardins' in fname:
        expected_bank_from_name = 'desjardins'
    elif 'rbc' in fname:
        expected_bank_from_name = 'rbc'
    elif 'amex' in fname:
        expected_bank_from_name = 'amex'

    detected_bank = detected_format.split('_')[0]

    if expected_bank_from_name and expected_bank_from_name != detected_bank:
        warnings.append(
            f'FORMAT MISMATCH: filename suggests {expected_bank_from_name} '
            f'but content detected as {detected_bank}. '
            f'CONTENT DETECTION TAKES PRIORITY — verify manually.'
        )

    return warnings


# ---------------------------------------------------------------------------
# Desjardins parser
# ---------------------------------------------------------------------------

def _parse_desjardins(raw: str, file_path: str) -> ParseResult:
    """Parse Desjardins CSV: 14+ cols, no header, quoted fields."""
    lines = raw.strip().split('\n')
    raw_line_count = len(lines)
    warnings = []

    reader = csv.reader(io.StringIO(raw))
    transactions = []
    account_number = None
    branch_name = None
    record_types_seen = set()

    for row_num, row in enumerate(reader, 1):
        if len(row) < 14:
            if any(c.strip() for c in row):  # Non-empty short row
                warnings.append(f'Row {row_num}: only {len(row)} columns (expected 14+), skipped')
            continue

        succursale, compte, type_rec, date_str, seq, description, extra, \
            debit_str, credit_str, col10, col11, col12, col13, balance_str = row[:14]

        type_rec = type_rec.strip()
        record_types_seen.add(type_rec)

        # Capture account metadata from first valid row
        if not branch_name and succursale.strip():
            branch_name = succursale.strip()
        if not account_number and compte.strip():
            account_number = compte.strip()

        # Only process EOP (checking account) records
        if type_rec != 'EOP':
            continue

        date = _normalize_date(date_str)
        debit = _parse_float(debit_str)
        credit = _parse_float(credit_str)
        balance = _parse_float(balance_str)

        transactions.append(Transaction(
            date=date,
            description=description.strip(),
            debit=debit,
            credit=credit,
            balance=balance,
            raw_row={'row_num': row_num, 'succursale': succursale.strip(),
                     'compte': compte.strip(), 'type_rec': type_rec,
                     'seq': seq.strip(), 'extra': extra.strip()},
        ))

    # Log non-EOP record types
    non_eop = record_types_seen - {'EOP', ''}
    if non_eop:
        warnings.append(f'Non-EOP record types found and excluded: {sorted(non_eop)}')

    # Validation
    validation = _validate_desjardins(transactions, warnings)

    # Period
    dates = sorted([t.date for t in transactions if t.date])
    period_start = dates[0] if dates else None
    period_end = dates[-1] if dates else None

    # Cross-check filename vs content
    warnings.extend(_cross_check_filename(file_path, 'desjardins_csv'))

    return ParseResult(
        entity_hint=_guess_entity_from_path(file_path),
        detected_format='desjardins_csv',
        detected_bank='Desjardins',
        account_number=account_number,
        branch_name=branch_name,
        period_start=period_start,
        period_end=period_end,
        transactions=transactions,
        validation=validation,
        file_path=file_path,
        warnings=warnings,
        raw_line_count=raw_line_count,
    )


def _validate_desjardins(transactions: list, warnings: list) -> ValidationResult:
    """Validate Desjardins parsed data with balance reconciliation."""
    checks = {}

    if not transactions:
        checks['has_transactions'] = {'passed': False, 'detail': 'No transactions parsed'}
        return ValidationResult(ok=False, checks=checks)

    checks['has_transactions'] = {'passed': True, 'detail': f'{len(transactions)} transactions'}

    # Balance reconciliation: compute running balance and compare
    txs_with_balance = [t for t in transactions if t.balance is not None]
    if len(txs_with_balance) >= 2:
        first = transactions[0]
        if first.balance is not None:
            # Compute opening balance
            opening = first.balance - (first.credit or 0) + (first.debit or 0)
            running = opening
            mismatches = []

            for i, tx in enumerate(transactions):
                running = running - (tx.debit or 0) + (tx.credit or 0)
                if tx.balance is not None:
                    diff = abs(running - tx.balance)
                    if diff > 0.02:
                        mismatches.append({
                            'row': i + 1,
                            'date': tx.date,
                            'expected': round(running, 2),
                            'actual': tx.balance,
                            'diff': round(diff, 2),
                        })
                    running = tx.balance  # Reset to actual for next segment

            if mismatches:
                checks['balance_reconciliation'] = {
                    'passed': False,
                    'detail': f'{len(mismatches)} balance mismatches found',
                    'mismatches': mismatches[:10],  # Cap at 10 for readability
                }
                warnings.append(f'BALANCE MISMATCH: {len(mismatches)} rows have computed vs actual balance discrepancy')
            else:
                checks['balance_reconciliation'] = {
                    'passed': True,
                    'detail': f'All {len(txs_with_balance)} balances reconcile within $0.02',
                }
    else:
        checks['balance_reconciliation'] = {
            'passed': None,
            'detail': 'Not enough balance data to reconcile',
        }

    # Check for duplicate sequential numbers
    seqs = [t.raw_row.get('seq') for t in transactions if t.raw_row.get('seq')]
    if seqs:
        unique_seqs = set(seqs)
        if len(unique_seqs) < len(seqs):
            dups = len(seqs) - len(unique_seqs)
            checks['unique_sequences'] = {'passed': False, 'detail': f'{dups} duplicate sequence numbers'}
            warnings.append(f'DUPLICATE SEQUENCES: {dups} rows share sequence numbers')
        else:
            checks['unique_sequences'] = {'passed': True, 'detail': f'{len(seqs)} unique sequences'}

    all_ok = all(c.get('passed', True) is not False for c in checks.values())
    return ValidationResult(ok=all_ok, checks=checks)


# ---------------------------------------------------------------------------
# RBC parser
# ---------------------------------------------------------------------------

def _parse_rbc(raw: str, file_path: str) -> ParseResult:
    """Parse RBC CSV: Date,Description,Debit,Credit,Balance"""
    lines = raw.strip().split('\n')
    raw_line_count = len(lines)
    warnings = []

    reader = csv.DictReader(io.StringIO(raw))
    transactions = []

    # Verify expected columns
    if reader.fieldnames:
        expected = {'Date', 'Description', 'Debit', 'Credit', 'Balance'}
        actual = set(reader.fieldnames)
        missing = expected - actual
        if missing:
            warnings.append(f'Missing expected columns: {missing}. Found: {reader.fieldnames}')

    for row_num, row in enumerate(reader, 2):  # Row 1 is header
        date = _normalize_date(row.get('Date', ''))
        description = row.get('Description', '').strip()
        debit = _parse_float(row.get('Debit', ''))
        credit = _parse_float(row.get('Credit', ''))
        balance = _parse_float(row.get('Balance', ''))

        transactions.append(Transaction(
            date=date,
            description=description,
            debit=debit,
            credit=credit,
            balance=balance,
            raw_row={'row_num': row_num},
        ))

    # Validation
    validation = _validate_rbc(transactions, warnings)

    dates = sorted([t.date for t in transactions if t.date])
    period_start = dates[0] if dates else None
    period_end = dates[-1] if dates else None

    warnings.extend(_cross_check_filename(file_path, 'rbc_csv'))

    return ParseResult(
        entity_hint=_guess_entity_from_path(file_path),
        detected_format='rbc_csv',
        detected_bank='RBC',
        account_number=None,  # RBC CSV doesn't include account number
        branch_name=None,
        period_start=period_start,
        period_end=period_end,
        transactions=transactions,
        validation=validation,
        file_path=file_path,
        warnings=warnings,
        raw_line_count=raw_line_count,
    )


def _validate_rbc(transactions: list, warnings: list) -> ValidationResult:
    """Validate RBC parsed data."""
    checks = {}

    if not transactions:
        checks['has_transactions'] = {'passed': False, 'detail': 'No transactions parsed'}
        return ValidationResult(ok=False, checks=checks)

    checks['has_transactions'] = {'passed': True, 'detail': f'{len(transactions)} transactions'}

    # RBC: balance reconciliation
    # RBC sometimes has gaps in balance column
    txs_with_balance = [t for t in transactions if t.balance is not None]

    if len(txs_with_balance) >= 2:
        # Find opening balance from first transaction with balance
        first_bal_idx = next(i for i, t in enumerate(transactions) if t.balance is not None)
        running = transactions[first_bal_idx].balance
        mismatches = []

        for i in range(first_bal_idx + 1, len(transactions)):
            tx = transactions[i]
            running = running - (tx.debit or 0) + (tx.credit or 0)
            if tx.balance is not None:
                diff = abs(running - tx.balance)
                if diff > 0.02:
                    mismatches.append({
                        'row': i + 1,
                        'date': tx.date,
                        'expected': round(running, 2),
                        'actual': tx.balance,
                        'diff': round(diff, 2),
                    })
                running = tx.balance

        if mismatches:
            total_hidden = sum(abs(m['diff']) for m in mismatches)
            checks['balance_reconciliation'] = {
                'passed': True,  # Soft pass — RBC hidden txns are expected
                'detail': f'{len(mismatches)} hidden transaction gaps totaling ${total_hidden:,.2f} (RBC interday)',
                'mismatches': mismatches[:10],
            }
            checks['hidden_transactions'] = {
                'passed': False,  # Flag for attention — money is moving off-statement
                'detail': f'${total_hidden:,.2f} in hidden transactions NOT in this CSV — verify via online banking',
            }
            warnings.append(f'HIDDEN TRANSACTIONS: {len(mismatches)} gaps, ${total_hidden:,.2f} total — RBC interday movements not in CSV export')
        else:
            checks['balance_reconciliation'] = {
                'passed': True,
                'detail': f'Balance reconciles across {len(txs_with_balance)} checkpoints',
            }
    else:
        checks['balance_reconciliation'] = {
            'passed': None,
            'detail': 'Insufficient balance data for reconciliation',
        }

    all_ok = all(c.get('passed', True) is not False for c in checks.values())
    return ValidationResult(ok=all_ok, checks=checks)


# ---------------------------------------------------------------------------
# Amex parser
# ---------------------------------------------------------------------------

def _parse_amex(raw: str, file_path: str) -> ParseResult:
    """Parse Amex CSV: French headers, comma decimals, multi-line addresses.

    Header: Date,Date de traitement,Description,Montant,Montant des dépenses en
    devises étrangères,Commission,Taux de change,Renseignements supplémentaires,
    Marchand,Adresse,Ville/Province,Code postal,Pays,Référence
    """
    raw_line_count = raw.count('\n') + 1
    warnings = []

    # Amex CSVs can have multi-line fields (addresses with newlines).
    # csv.reader handles this correctly with quoting.
    reader = csv.reader(io.StringIO(raw))

    # Read header
    try:
        header = next(reader)
    except StopIteration:
        return ParseResult(
            entity_hint=_guess_entity_from_path(file_path),
            detected_format='amex_csv', detected_bank='Amex',
            account_number=None, branch_name=None,
            period_start=None, period_end=None,
            transactions=[], file_path=file_path,
            validation=ValidationResult(ok=False, checks={'has_header': {'passed': False, 'detail': 'Empty file'}}),
            warnings=['File is empty'], raw_line_count=raw_line_count,
        )

    # Map header columns (handle slight variations)
    col_map = {}
    for i, h in enumerate(header):
        h_lower = h.strip().lower()
        if h_lower == 'date' and 'date' not in col_map:
            col_map['date'] = i
        elif 'traitement' in h_lower or 'processing' in h_lower:
            col_map['processing_date'] = i
        elif h_lower == 'description':
            col_map['description'] = i
        elif h_lower == 'montant' or (h_lower == 'amount' and 'amount' not in col_map):
            col_map['amount'] = i
        elif 'marchand' in h_lower or 'merchant' in h_lower:
            col_map['merchant'] = i
        elif h_lower.startswith('référence') or h_lower.startswith('reference'):
            col_map['reference'] = i
        elif 'renseignements' in h_lower or 'additional' in h_lower:
            col_map['additional_info'] = i

    if 'date' not in col_map or 'amount' not in col_map:
        warnings.append(f'Could not find required columns (date, amount) in header: {header}')

    transactions = []
    for row_num, row in enumerate(reader, 2):
        if not row or all(not c.strip() for c in row):
            continue

        date_str = row[col_map['date']].strip() if 'date' in col_map and col_map['date'] < len(row) else ''
        date = _normalize_date(date_str)

        description = row[col_map['description']].strip() if 'description' in col_map and col_map['description'] < len(row) else ''

        amount_str = row[col_map['amount']].strip() if 'amount' in col_map and col_map['amount'] < len(row) else ''
        amount = _parse_french_float(amount_str)

        if amount is None and not description:
            continue  # Skip truly empty rows

        # Amex: positive = charge (debit), negative = payment/credit
        debit = amount if amount is not None and amount > 0 else None
        credit = abs(amount) if amount is not None and amount < 0 else None

        merchant = row[col_map['merchant']].strip() if 'merchant' in col_map and col_map['merchant'] < len(row) else ''
        reference = row[col_map['reference']].strip() if 'reference' in col_map and col_map['reference'] < len(row) else ''

        transactions.append(Transaction(
            date=date,
            description=description,
            debit=debit,
            credit=credit,
            balance=None,  # Amex doesn't provide running balance
            raw_row={'row_num': row_num, 'merchant': merchant, 'reference': reference,
                     'raw_amount': amount_str},
        ))

    # Validation
    validation = _validate_amex(transactions, warnings)

    dates = sorted([t.date for t in transactions if t.date and re.match(r'\d{4}-\d{2}-\d{2}', t.date)])
    period_start = dates[0] if dates else None
    period_end = dates[-1] if dates else None

    warnings.extend(_cross_check_filename(file_path, 'amex_csv'))

    return ParseResult(
        entity_hint=_guess_entity_from_path(file_path),
        detected_format='amex_csv',
        detected_bank='Amex',
        account_number=None,
        branch_name=None,
        period_start=period_start,
        period_end=period_end,
        transactions=transactions,
        validation=validation,
        file_path=file_path,
        warnings=warnings,
        raw_line_count=raw_line_count,
    )


def _validate_amex(transactions: list, warnings: list) -> ValidationResult:
    """Validate Amex parsed data."""
    checks = {}

    if not transactions:
        checks['has_transactions'] = {'passed': False, 'detail': 'No transactions parsed'}
        return ValidationResult(ok=False, checks=checks)

    checks['has_transactions'] = {'passed': True, 'detail': f'{len(transactions)} transactions'}

    # Check for unparseable dates
    bad_dates = [t for t in transactions if t.date and not re.match(r'\d{4}-\d{2}-\d{2}', t.date)]
    if bad_dates:
        checks['date_parsing'] = {
            'passed': False,
            'detail': f'{len(bad_dates)} dates could not be normalized',
            'examples': [{'raw': t.date, 'desc': t.description[:50]} for t in bad_dates[:5]],
        }
        warnings.append(f'DATE PARSE ISSUE: {len(bad_dates)} transactions have non-standard dates')
    else:
        checks['date_parsing'] = {'passed': True, 'detail': 'All dates normalized to YYYY-MM-DD'}

    # Check for None amounts
    no_amount = [t for t in transactions if t.debit is None and t.credit is None]
    if no_amount:
        checks['amount_parsing'] = {
            'passed': False,
            'detail': f'{len(no_amount)} transactions have no parseable amount',
            'examples': [{'desc': t.description[:50], 'raw': t.raw_row.get('raw_amount')} for t in no_amount[:5]],
        }
        warnings.append(f'AMOUNT PARSE ISSUE: {len(no_amount)} transactions have no amount')
    else:
        checks['amount_parsing'] = {'passed': True, 'detail': 'All amounts parsed successfully'}

    # No balance reconciliation possible for Amex (no running balance)
    checks['balance_reconciliation'] = {
        'passed': None,
        'detail': 'Amex does not provide running balance — reconciliation not possible',
    }

    all_ok = all(c.get('passed', True) is not False for c in checks.values())
    return ValidationResult(ok=all_ok, checks=checks)


# ---------------------------------------------------------------------------
# Entity guess from path (advisory only — NOT authoritative)
# ---------------------------------------------------------------------------

ENTITY_PATTERNS = [
    (r'mae\s*sri', 'Lotus Kitchen'),
    (r'siam\s*thai', 'Siam House'),
    (r'siam\s*s\b', 'Siam Holdings Inc'),
    (r'garden\s*room', 'Garden Bistro'),
    (r'vine_room|wine\s*room', 'Vine Room'),
]


def _guess_entity_from_path(file_path: str) -> str:
    """Guess entity from file path. This is a HINT only — not authoritative.
    Only checks the last 3 path components to avoid false matches from
    Google Drive paths (e.g., owner@example.com in the drive URL)."""
    parts = Path(file_path).parts
    # Only check last 3 components (folder/subfolder/filename)
    relevant = '/'.join(parts[-3:]).lower() if len(parts) >= 3 else file_path.lower()
    for pattern, entity in ENTITY_PATTERNS:
        if re.search(pattern, relevant):
            return entity
    return 'Unknown'


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_file(file_path: str) -> ParseResult:
    """
    Parse a single bank statement file.
    Auto-detects format by content inspection.
    Returns ParseResult with full validation.
    """
    path = Path(file_path)

    if not path.exists():
        return ParseResult(
            entity_hint=_guess_entity_from_path(file_path),
            detected_format='error', detected_bank='Unknown',
            account_number=None, branch_name=None,
            period_start=None, period_end=None,
            transactions=[], file_path=file_path,
            validation=ValidationResult(ok=False, checks={'file_exists': {'passed': False, 'detail': f'File not found: {file_path}'}}),
            warnings=[f'File not found: {file_path}'], raw_line_count=0,
        )

    # Try multiple encodings
    raw = None
    used_encoding = None
    for encoding in ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']:
        try:
            raw = path.read_text(encoding=encoding)
            used_encoding = encoding
            break
        except UnicodeDecodeError:
            continue

    if raw is None:
        return ParseResult(
            entity_hint=_guess_entity_from_path(file_path),
            detected_format='error', detected_bank='Unknown',
            account_number=None, branch_name=None,
            period_start=None, period_end=None,
            transactions=[], file_path=file_path,
            validation=ValidationResult(ok=False, checks={'encoding': {'passed': False, 'detail': 'Could not decode file'}}),
            warnings=['Could not decode file with any supported encoding'], raw_line_count=0,
        )

    # Detect format
    fmt, confidence, detect_warnings = detect_format(raw, file_path)
    all_warnings = list(detect_warnings)

    if used_encoding != 'utf-8':
        all_warnings.append(f'File decoded with {used_encoding} (not UTF-8)')

    if confidence == 'low':
        all_warnings.append(f'Low confidence format detection — manual verification required')

    # Parse by detected format
    if fmt == 'desjardins_csv':
        result = _parse_desjardins(raw, file_path)
    elif fmt == 'rbc_csv':
        result = _parse_rbc(raw, file_path)
    elif fmt == 'amex_csv':
        result = _parse_amex(raw, file_path)
    else:
        result = ParseResult(
            entity_hint=_guess_entity_from_path(file_path),
            detected_format='unknown', detected_bank='Unknown',
            account_number=None, branch_name=None,
            period_start=None, period_end=None,
            transactions=[], file_path=file_path,
            validation=ValidationResult(ok=False, checks={'format': {'passed': False, 'detail': f'Unknown format'}}),
            warnings=all_warnings, raw_line_count=raw.count('\n') + 1,
        )

    # Merge detection warnings into result
    result.warnings = all_warnings + result.warnings

    return result
