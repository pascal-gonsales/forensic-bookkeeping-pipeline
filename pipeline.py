#!/usr/bin/env python3
"""
Forensic Bookkeeping Pipeline — Full entity analysis.

Processes all CSV bank statements + Amex credit cards across 5 entities.
Detects inter-company transfers, categorizes, builds financial portrait.

GUARD RAILS:
  - Every file validated individually before aggregation
  - Inter-company transfers matched bidirectionally (source + destination)
  - Unmatched transfers flagged
  - Duplicate detection across files
  - Summary totals cross-checked
"""

import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from parsers import parse_file, ParseResult, Transaction

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_PATH = "./data/bank_statements"

# Known Desjardins account → entity mapping (verified from actual data)
ACCOUNT_ENTITY_MAP = {
    '0011002': 'Siam House',
    '0011001': 'Lotus Kitchen',
    '0011003': 'Siam Holdings Inc',
    '0011004': 'Vine Room',
    '0011005': 'Owner_A (Personnel)',       # Owner_A's personal Desjardins account
    '0011006': 'Holding Owner_A+Siam',    # Owner_A + Siam wife holding (Owner_B 15%)
    # Garden Bistro is RBC (no Desjardins account number)
}

# Transfer classification: reimbursement vs shareholder advance
# Reimbursement = Owner_A paid suppliers with personal CC, company reimburses
# Shareholder advance = compensation/salary via holding company
REIMBURSEMENT_DESTINATIONS = {'Owner_A (Personnel)', 'Owner_A (Personal)'}
SHAREHOLDER_ADVANCE_DESTINATIONS = {'Holding Owner_A+Siam'}
ALI_REIMBURSEMENT_PATTERN = re.compile(r'Owner_B|Owner_B\s*Zare[ia]', re.IGNORECASE)
ALI_ADVANCE_PATTERN = re.compile(r'Owner_B\s*Holding', re.IGNORECASE)

# Reverse: entity → account for transfer matching
ENTITY_ACCOUNT_MAP = {v: k for k, v in ACCOUNT_ENTITY_MAP.items()}

# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def discover_csv_files(base_path: str = BASE_PATH) -> list:
    """Find all CSV files in the bank statements directory tree."""
    base = Path(base_path)
    files = []
    for f in sorted(base.rglob('*.csv')):
        files.append({
            'path': str(f),
            'name': f.name,
            'parent': f.parent.name,
            'size': f.stat().st_size,
            'source_type': 'csv',
        })
    return files


def discover_pdf_files(base_path: str = BASE_PATH) -> list:
    """Find ALL PDF files (bank statements + credit cards).
    Uses content-based detection to classify format."""
    try:
        from pdf_parsers import detect_pdf_format
    except ImportError:
        return []

    base = Path(base_path)
    files = []
    for f in sorted(base.rglob('*.pdf')):
        fmt = detect_pdf_format(str(f))
        if fmt in ('desjardins_pdf', 'rbc_pdf', 'desjardins_cc_pdf', 'rbc_visa_pdf'):
            files.append({
                'path': str(f),
                'name': f.name,
                'parent': f.parent.name,
                'size': f.stat().st_size,
                'source_type': 'pdf',
                'pdf_format': fmt,
            })
    return files


# ---------------------------------------------------------------------------
# Inter-company transfer detection
# ---------------------------------------------------------------------------

# Desjardins transfer patterns: "Virement - AccèsD Internet /à XXXXXX EOP" or "/de XXXXXX EOP"
# PDF descriptions have spaces: "/ à 092483" vs CSV "/à 092483"
TRANSFER_TO_PATTERN = re.compile(r'Virement.*Acc[èe]sD.*?/\s*[àa]\s*(\d{6,7})\s*EOP', re.IGNORECASE)
TRANSFER_FROM_PATTERN = re.compile(r'Virement.*Acc[èe]sD.*?/\s*de\s*(\d{6,7})\s*EOP', re.IGNORECASE)

# Interac transfers to Owner_A
# Owner_A detection: handles both CSV "/Owner_A" and PDF "/ Owner_A" (space after slash)
# Also handles RBC "Virement envoyé Owner_A"
OWNER_A_INTERAC_PATTERN = re.compile(r'Virement\s+Interac\s+[àa]\s*/\s*Owner_A', re.IGNORECASE)
OWNER_A_RBC_PATTERN = re.compile(r'Virement\s+envoy[ée]\s+Owner_A', re.IGNORECASE)
OWNER_A_INTERAC_FROM = re.compile(r'Virement\s+Interac.*de\s*/Owner_A', re.IGNORECASE)

# General Interac transfers
INTERAC_TO_PATTERN = re.compile(r'Virement\s+Interac\s+[àa]\s*/(.*?)/', re.IGNORECASE)
INTERAC_FROM_PATTERN = re.compile(r'Virement\s+Interac.*de\s*/(.*?)/', re.IGNORECASE)

# RBC transfers
RBC_VIREMENT_ENVOYE = re.compile(r'Virement envoy[ée]\s+(.*)', re.IGNORECASE)
RBC_VIREMENT_RECU = re.compile(r'Virement re[çc]u\s+(.*)', re.IGNORECASE)


@dataclass
class TransferRecord:
    date: str
    amount: float
    source_entity: str
    source_account: Optional[str]
    destination_entity: Optional[str]
    destination_account: Optional[str]
    description: str
    transfer_type: str  # 'intercompany', 'owner_a_personal', 'interac_out', 'interac_in'
    matched: bool = False  # True if bidirectional match found
    file_path: str = ''


def _resolve_account(acct: str) -> tuple:
    """Resolve account number to entity, trying with/without leading zeros.
    Returns (entity_name, normalized_account)."""
    # Try as-is
    if acct in ACCOUNT_ENTITY_MAP:
        return ACCOUNT_ENTITY_MAP[acct], acct
    # Try with leading zero (descriptions often drop leading 0)
    padded = '0' + acct
    if padded in ACCOUNT_ENTITY_MAP:
        return ACCOUNT_ENTITY_MAP[padded], padded
    # Try stripping leading zero
    if acct.startswith('0') and acct[1:] in ACCOUNT_ENTITY_MAP:
        return ACCOUNT_ENTITY_MAP[acct[1:]], acct[1:]
    return f'Unknown ({acct})', acct


def detect_transfers(tx: Transaction, entity: str, account: Optional[str]) -> Optional[TransferRecord]:
    """Detect if a transaction is an inter-company or personal transfer."""
    desc = tx.description

    # Desjardins: transfer TO another account
    m = TRANSFER_TO_PATTERN.search(desc)
    if m and tx.debit:
        dest_acct = m.group(1)
        dest_entity, dest_acct = _resolve_account(dest_acct)
        return TransferRecord(
            date=tx.date, amount=tx.debit, source_entity=entity,
            source_account=account, destination_entity=dest_entity,
            destination_account=dest_acct, description=desc,
            transfer_type='intercompany',
        )

    # Desjardins: transfer FROM another account
    m = TRANSFER_FROM_PATTERN.search(desc)
    if m and tx.credit:
        src_acct = m.group(1)
        src_entity, src_acct = _resolve_account(src_acct)
        return TransferRecord(
            date=tx.date, amount=tx.credit, source_entity=src_entity,
            source_account=src_acct, destination_entity=entity,
            destination_account=account, description=desc,
            transfer_type='intercompany',
        )

    # Interac TO Owner_A (= reimbursement for supplier payments)
    if OWNER_A_INTERAC_PATTERN.search(desc) and tx.debit:
        return TransferRecord(
            date=tx.date, amount=tx.debit, source_entity=entity,
            source_account=account, destination_entity='Owner_A (Personnel)',
            destination_account=None, description=desc,
            transfer_type='owner_a_reimbursement',
        )

    # Interac FROM Owner_A (= Owner_A injecting money back)
    if OWNER_A_INTERAC_FROM.search(desc) and tx.credit:
        return TransferRecord(
            date=tx.date, amount=tx.credit, source_entity='Owner_A (Personnel)',
            source_account=None, destination_entity=entity,
            destination_account=account, description=desc,
            transfer_type='owner_a_reimbursement',
        )

    # RBC: Virement envoyé Owner_A (BEFORE generic RBC pattern)
    if OWNER_A_RBC_PATTERN.search(desc) and tx.debit:
        return TransferRecord(
            date=tx.date, amount=tx.debit, source_entity=entity,
            source_account=account, destination_entity='Owner_A (Personnel)',
            destination_account=None, description=desc,
            transfer_type='owner_a_reimbursement',
        )

    # General Interac OUT
    m = INTERAC_TO_PATTERN.search(desc)
    if m and tx.debit:
        recipient = m.group(1).strip()
        return TransferRecord(
            date=tx.date, amount=tx.debit, source_entity=entity,
            source_account=account, destination_entity=f'Interac: {recipient}',
            destination_account=None, description=desc,
            transfer_type='interac_out',
        )

    # RBC: Virement envoyé (generic — after Owner_A-specific check)
    m = RBC_VIREMENT_ENVOYE.search(desc)
    if m and tx.debit:
        recipient = m.group(1).strip()
        return TransferRecord(
            date=tx.date, amount=tx.debit, source_entity=entity,
            source_account=account, destination_entity=f'Transfer: {recipient}',
            destination_account=None, description=desc,
            transfer_type='interac_out',
        )

    # RBC: Virement reçu
    m = RBC_VIREMENT_RECU.search(desc)
    if m and tx.credit:
        sender = m.group(1).strip()
        return TransferRecord(
            date=tx.date, amount=tx.credit, source_entity=f'Transfer: {sender}',
            source_account=None, destination_entity=entity,
            destination_account=account, description=desc,
            transfer_type='interac_in',
        )

    return None


def match_intercompany_transfers(transfers: list) -> tuple:
    """
    Match inter-company transfers bidirectionally.
    A transfer from A→B should have a matching entry in B (credit from A).
    Returns (matched_pairs, unmatched).
    """
    # Group by (date, amount) for matching
    by_key = defaultdict(list)
    for t in transfers:
        if t.transfer_type == 'intercompany':
            key = (t.date, t.amount)
            by_key[key].append(t)

    matched_pairs = []
    unmatched = []

    for key, group in by_key.items():
        # Look for source/dest pairs
        sources = [t for t in group if t.source_entity != t.destination_entity and t.source_account]
        dests = [t for t in group if t.destination_entity and t.destination_account]

        # Try to pair them
        used = set()
        for s in sources:
            for i, d in enumerate(dests):
                if i in used:
                    continue
                # Match: s sends to d's account, d receives from s's account
                if s.destination_account == d.destination_account and s.source_account == d.source_account:
                    if s is not d:  # Not the same record
                        s.matched = True
                        d.matched = True
                        matched_pairs.append((s, d))
                        used.add(i)
                        break

    # Collect unmatched
    for t in transfers:
        if t.transfer_type == 'intercompany' and not t.matched:
            unmatched.append(t)

    return matched_pairs, unmatched


# ---------------------------------------------------------------------------
# Transaction categorization (reusing existing rules + extensions)
# ---------------------------------------------------------------------------

CATEGORY_RULES = [
    # Revenue
    (r'PAYFACTO CAD PAYFACTO', 'revenue_pos', 'Revenue POS (Payfacto)'),
    (r'Lightspeed Commerce.*LS', 'revenue_pos', 'Revenue POS (Lightspeed)'),
    (r'AMEX 2992156570', 'revenue_amex', 'Revenue AMEX'),
    (r'Uber Holdings C', 'revenue_delivery', 'Revenue Uber Eats'),
    (r'DoorDash', 'revenue_delivery', 'Revenue DoorDash'),
    (r'UEAT AR', 'revenue_delivery', 'Revenue UberEats AR'),
    (r'D[ée]p[oô]t GAB', 'revenue_cash', 'Revenue Cash (GAB)'),
    (r'D[ée]p[oô]t direct', 'revenue_deposit', 'Revenue Direct Deposit'),

    # Labor
    (r'NETHRIS', 'labor', 'Labor (Nethris)'),
    (r'CGI PAYROLL', 'labor', 'Labor (CGI Payroll)'),

    # Rent
    (r'LOYER|BAUX', 'rent', 'Rent'),

    # Utilities
    (r'HYDRO-QUEBEC', 'utilities', 'Utilities (Hydro-Quebec)'),
    (r'ENERGIR', 'utilities', 'Utilities (Energir)'),
    (r'BELL CAN|BELL MOBIL', 'utilities', 'Utilities (Bell)'),
    (r'VIDEOTRON', 'utilities', 'Utilities (Videotron)'),

    # Insurance
    (r'Intact Assur|Economical', 'insurance', 'Insurance'),

    # Tax
    (r'REV QC|REVENU QUEBEC', 'tax_rq', 'Tax (Revenue Quebec)'),
    (r'PME MTL|VILLE DE|MUNICIPAL', 'tax_municipal', 'Tax (Municipal)'),

    # Lightspeed capital (cash advance repayment)
    (r'Paiement /LSPD CAPITAL|LSPD CAPITAL', 'loan_lightspeed', 'Lightspeed Cash Advance Repayment'),

    # Government tax remittances (GST/QST)
    (r'Remise gouvernementale.*TPS|Remise gouvernementale.*TVQ', 'tax_gst_qst', 'Tax Remittance (TPS-TVQ)'),

    # Landlord payments (rent or partial taxes — needs confirmation if not explicit)
    (r'Paiement internet.*Landlord.*rent|Paiement internet.*Landlord.*loyer', 'rent', 'Rent (Landlord)'),
    (r'Paiement internet.*Landlord.*Tax', 'tax_property', 'Property Tax (Landlord)'),
    (r'Paiement internet.*Landlord', 'rent_unconfirmed', 'Landlord Payment (rent or tax — à confirmer)'),

    # Owner_B Holding (shareholder advance)
    (r'Owner_B\s*Holding', 'ali_advance', 'Owner_B Holding (Shareholder Advance)'),

    # Aliments Jork (food supplier)
    (r'Aliments Jork', 'supplier_food', 'Supplier (Aliments Jork)'),

    # Loans & leases
    (r'VERSEMENT PRET|Versement sur pr[êe]t', 'loan', 'Loan Payment'),
    (r'Int[ée]r[êe]ts sur pr[êe]t', 'loan_interest', 'Loan Interest'),
    (r'CREDIT PRET', 'loan_credit', 'Loan Credit'),
    (r'ECONOLEASE|VLFC', 'lease', 'Equipment Lease'),
    (r'BANQUE DEVELOPPEMENT|BDC', 'loan_bdc', 'BDC Payment'),
    (r'CWB National Leasing', 'lease', 'Equipment Lease (CWB)'),
    (r'D[ÉE]P[ÔO]T DE LA MARGE', 'credit_line', 'Credit Line Draw'),
    (r'Frais fixes financement', 'loan_fees', 'Financing Fees'),

    # Bank Fees
    (r'Frais mensuels|Frais bancaires|Frais fixes d.utilisation', 'bank_fees', 'Bank Fees'),
    (r'MERCH PAD|FIRST DATA|CLOVER', 'pos_fees', 'POS/Card Processing Fees'),
    (r'Frais virement INTERAC', 'bank_fees', 'Interac Fee'),

    # Suppliers (restaurant-specific)
    (r'Brasseurs|Molson|Labatt', 'supplier_beverage', 'Supplier (Beverage)'),
    (r'Damen|Ferro|Newon|march[ée]', 'supplier_food', 'Supplier (Food)'),
    (r'ECOLAB|Cintas', 'supplier_cleaning', 'Supplier (Cleaning/Linen)'),
    (r'Sysco|GFS|Gordon Food', 'supplier_food', 'Supplier (Food Distributor)'),
    (r'SAQ\d', 'supplier_alcohol', 'Supplier (SAQ)'),

    # Internal transfers (handled separately by transfer detection)
    (r'Virement.*Acc[èe]sD.*EOP', 'transfer_internal', 'Internal Transfer'),
    (r'Virement Interac', 'transfer_interac', 'Interac Transfer'),
    (r'Virement envoy[ée]', 'transfer_out', 'Transfer Out'),
    (r'Virement re[çc]u', 'transfer_in', 'Transfer In'),
    (r'VISA DESJARDINS|Paiement.*American Express', 'cc_payment', 'CC Payment'),

    # Trustee / Legal
    (r'trustee|syndic', 'trustee', 'Trustee Payment'),
    (r'Nagi Haddad', 'trustee', 'Trustee (Nagi Haddad)'),

    # Amex CC payment received (credit on Amex statement)
    (r'PAIEMENT RE[ÇC]U.*MERCI', 'cc_payment_received', 'Amex Payment Received'),

    # Credit line repayments
    (r'Virement-remboursement.*PR\s*\d', 'credit_line_repayment', 'Credit Line Repayment'),

    # Journey Capital / OnDeck (cash advance loan)
    (r'JOURNEY CAPITAL|ONDECK', 'loan_journey', 'Loan (Journey Capital/OnDeck)'),

    # Insurance (broader pattern)
    (r'Assurance.*Compagnie|assurance', 'insurance', 'Insurance'),

    # AGENDRIX (scheduling/HR software)
    (r'AGENDRIX', 'software_hr', 'Software (Agendrix HR/Scheduling)'),

    # SAQ (alcohol — broader pattern)
    (r'SAQ\s', 'supplier_alcohol', 'Supplier (SAQ Alcohol)'),

    # Milton rent
    (r'Milton rent|Milton Rent', 'rent_milton', 'Rent (Milton)'),

    # Cash deposits/withdrawals at counter
    (r'D[ée]p[oô]t au comptoir', 'cash_deposit', 'Cash Deposit (Counter)'),
    (r'Retrait au comptoir', 'cash_withdrawal_counter', 'Cash Withdrawal (Counter)'),

    # Payfacto payment (POS fees — broader)
    (r'Paiement.*PAYFACTO', 'pos_fees', 'POS Fees (Payfacto)'),

    # Virement par Banque en direct (external bank transfer)
    (r'Virement par Banque en direct', 'transfer_bank_direct', 'Direct Bank Transfer'),

    # PERSONAFI (payroll/HR related)
    (r'PERSONAFI', 'software_payroll', 'Software (Personafi Payroll)'),

    # Other
    (r'Retrait GAB', 'cash_withdrawal', 'Cash Withdrawal (ATM)'),
    (r'Ch[èe]que', 'cheque', 'Cheque'),
    (r'Achat Interac|D[ée]bit', 'purchase', 'Purchase'),
    (r'Remboursement automatique', 'auto_repayment', 'Auto Repayment'),
]

COMPILED_RULES = [(re.compile(p, re.IGNORECASE), cat, label) for p, cat, label in CATEGORY_RULES]


def categorize(description: str) -> dict:
    """Categorize a transaction by description."""
    for regex, category, label in COMPILED_RULES:
        if regex.search(description):
            return {'category': category, 'label': label}
    return {'category': 'uncategorized', 'label': 'UNCATEGORIZED'}


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------

@dataclass
class EntitySummary:
    entity: str
    account_number: Optional[str]
    bank: str
    files_processed: int
    total_transactions: int
    period_start: str
    period_end: str
    total_debits: float
    total_credits: float
    net_flow: float
    opening_balance: Optional[float]
    closing_balance: Optional[float]
    categories: dict  # category -> {debit_total, credit_total, count}
    validation_issues: list
    warnings: list


def run_pipeline(base_path: str = BASE_PATH) -> dict:
    """
    Run the full forensic bookkeeping pipeline.

    Returns:
        {
            'entities': {name: EntitySummary},
            'all_transactions': [...],
            'transfers': [...],
            'matched_transfers': [...],
            'unmatched_transfers': [...],
            'owner_a_transfers': [...],
            'file_reports': [...],
            'anomalies': [...],
            'run_timestamp': str,
        }
    """
    print(f"\n{'='*70}")
    print(f"  FORENSIC BOOKKEEPING PIPELINE")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*70}\n")

    # Step 1: Discover files
    print("Step 1: Discovering files...")
    csv_files = discover_csv_files(base_path)
    pdf_files = discover_pdf_files(base_path)
    print(f"  Found {len(csv_files)} CSV files + {len(pdf_files)} PDF bank statements\n")

    # Deduplicate: when CSV and PDF exist for same entity/period, prefer CSV
    # Track which entity+account+months are covered by CSV
    csv_coverage = set()  # (account_number, year_month) pairs

    # First pass: parse CSVs to build coverage set
    for finfo in csv_files:
        result = parse_file(finfo['path'])
        acct = result.account_number
        if acct and result.transactions:
            months_covered = set()
            for tx in result.transactions:
                if tx.date and len(tx.date) >= 7:
                    months_covered.add(tx.date[:7])
            for ym in months_covered:
                csv_coverage.add((acct, ym))

    # Filter PDF files: only include months NOT covered by CSV
    filtered_pdf_files = []
    skipped_pdf = 0
    for finfo in pdf_files:
        try:
            from pdf_parsers_v2 import parse_desjardins_pdf_v2, parse_rbc_pdf_v2
            pdf_fmt = finfo.get('pdf_format', '')
            if pdf_fmt == 'desjardins_pdf':
                result = parse_desjardins_pdf_v2(finfo['path'])
            elif pdf_fmt == 'rbc_pdf':
                result = parse_rbc_pdf_v2(finfo['path'])
            elif pdf_fmt == 'desjardins_cc_pdf':
                from pdf_parsers_v2 import parse_desjardins_cc_pdf_v2
                result = parse_desjardins_cc_pdf_v2(finfo['path'])
            elif pdf_fmt == 'rbc_visa_pdf':
                from pdf_parsers_v2 import parse_rbc_visa_pdf_v2
                result = parse_rbc_visa_pdf_v2(finfo['path'])
            else:
                continue  # Unknown format — skip
            acct = result.account_number
            if acct:
                # Normalize account (add leading zero if needed)
                if len(acct) == 5:
                    acct = '00' + acct
                elif len(acct) == 6:
                    acct = '0' + acct
                pdf_months = set()
                for tx in result.transactions:
                    if tx.date and len(tx.date) >= 7:
                        pdf_months.add(tx.date[:7])
                # Check if ALL months in this PDF are already covered by CSV
                covered = all((acct, ym) in csv_coverage for ym in pdf_months)
                if covered and pdf_months:
                    skipped_pdf += 1
                    continue
        except Exception:
            pass  # Include PDFs we can't pre-check
        filtered_pdf_files.append(finfo)

    print(f"  Skipped {skipped_pdf} PDF files (already covered by CSV)")
    print(f"  Using {len(filtered_pdf_files)} PDF files for new data\n")

    all_files = csv_files + filtered_pdf_files

    # Step 2: Parse each file
    print("Step 2: Parsing files...")
    file_reports = []
    all_transactions = []
    all_transfers = []
    anomalies = []

    for finfo in all_files:
        if finfo['source_type'] == 'csv':
            result = parse_file(finfo['path'])
        else:
            try:
                pdf_fmt = finfo.get('pdf_format', '')
                if pdf_fmt == 'desjardins_pdf':
                    from pdf_parsers_v2 import parse_desjardins_pdf_v2
                    result = parse_desjardins_pdf_v2(finfo['path'])
                elif pdf_fmt == 'rbc_pdf':
                    from pdf_parsers_v2 import parse_rbc_pdf_v2
                    result = parse_rbc_pdf_v2(finfo['path'])
                elif pdf_fmt == 'desjardins_cc_pdf':
                    from pdf_parsers_v2 import parse_desjardins_cc_pdf_v2
                    result = parse_desjardins_cc_pdf_v2(finfo['path'])
                elif pdf_fmt == 'rbc_visa_pdf':
                    from pdf_parsers_v2 import parse_rbc_visa_pdf_v2
                    result = parse_rbc_visa_pdf_v2(finfo['path'])
                else:
                    from pdf_parsers import parse_pdf_file
                    result = parse_pdf_file(finfo['path'])
            except Exception as e:
                anomalies.append({'type': 'pdf_parse_error', 'file': finfo['name'], 'detail': str(e)})
                continue
        file_reports.append(result)

        entity = result.entity_hint
        account = result.account_number

        # Validate account→entity consistency
        # CRITICAL: normalize account number (PDF returns 5-6 digits, map uses 7)
        normalized_account = account
        if account:
            if len(account.strip()) == 5:
                normalized_account = '00' + account.strip()
            elif len(account.strip()) == 6:
                normalized_account = '0' + account.strip()
            else:
                normalized_account = account.strip()

        if normalized_account and normalized_account in ACCOUNT_ENTITY_MAP:
            expected_entity = ACCOUNT_ENTITY_MAP[normalized_account]
            if entity != expected_entity:
                anomalies.append({
                    'type': 'entity_mismatch',
                    'file': finfo['name'],
                    'detail': f'Path suggests "{entity}" but account {normalized_account} maps to "{expected_entity}". Using account mapping.',
                })
                entity = expected_entity

        status = "✓" if result.validation.ok else "⚠"
        tx_count = len(result.transactions)
        print(f"  {status} {finfo['name']}: {tx_count} txns, {result.detected_format}, entity={entity}")

        if result.warnings:
            for w in result.warnings:
                if 'HIDDEN' in w or 'MISMATCH' in w or 'FORMAT MISMATCH' in w:
                    print(f"    ⚠ {w}")

        # Tag transactions with entity and collect
        for tx in result.transactions:
            tx.raw_row['entity'] = entity
            tx.raw_row['account'] = account
            tx.raw_row['file'] = finfo['name']
            tx.raw_row['source_type'] = finfo.get('source_type', 'csv')
            tx.raw_row['categorization'] = categorize(tx.description)
            all_transactions.append(tx)

            # Detect transfers
            transfer = detect_transfers(tx, entity, account)
            if transfer:
                transfer.file_path = finfo['name']
                all_transfers.append(transfer)

    print(f"\n  Total: {len(all_transactions)} transactions from {len(file_reports)} files")

    # Step 3: Match inter-company transfers
    print("\nStep 3: Matching inter-company transfers...")
    matched_pairs, unmatched = match_intercompany_transfers(all_transfers)
    # Classify personal transfers
    owner_a_reimbursements = [t for t in all_transfers if t.transfer_type == 'owner_a_reimbursement']
    owner_a_holding = [t for t in all_transfers
                      if t.transfer_type == 'intercompany' and t.destination_entity == 'Holding Owner_A+Siam']
    ali_reimbursements = [t for t in all_transfers
                          if t.transfer_type in ('interac_out',) and ALI_REIMBURSEMENT_PATTERN.search(t.destination_entity or t.description or '')]
    # Owner_B Holding payments are regular debits, not transfer-detected — search all transactions
    ali_advances = []
    for tx in all_transactions:
        if ALI_ADVANCE_PATTERN.search(tx.description):
            ali_advances.append(TransferRecord(
                date=tx.date, amount=tx.debit or 0,
                source_entity=tx.raw_row.get('entity', ''),
                source_account=tx.raw_row.get('account'),
                destination_entity='Owner_B Holding',
                destination_account=None,
                description=tx.description,
                transfer_type='ali_advance',
                file_path=tx.raw_row.get('file', ''),
            ))

    print(f"  Inter-company matched pairs: {len(matched_pairs)}")
    print(f"  Unmatched transfers: {len(unmatched)}")
    print(f"  Owner_A reimbursements: {len(owner_a_reimbursements)}")
    print(f"  Owner_A holding advances: {len(owner_a_holding)}")
    print(f"  Owner_B reimbursements: {len(ali_reimbursements)}")
    print(f"  Owner_B advances (Owner_B Holding): {len(ali_advances)}")

    # Step 4: Aggregate per entity
    print("\nStep 4: Building entity summaries...")
    entities = {}
    tx_by_entity = defaultdict(list)
    for tx in all_transactions:
        tx_by_entity[tx.raw_row['entity']].append(tx)

    for entity_name, txs in sorted(tx_by_entity.items()):
        total_debits = sum(tx.debit or 0 for tx in txs)
        total_credits = sum(tx.credit or 0 for tx in txs)
        dates = sorted([tx.date for tx in txs if tx.date])

        # Category breakdown
        categories = defaultdict(lambda: {'debit_total': 0, 'credit_total': 0, 'count': 0})
        for tx in txs:
            cat = tx.raw_row.get('categorization', {}).get('category', 'uncategorized')
            categories[cat]['count'] += 1
            categories[cat]['debit_total'] += tx.debit or 0
            categories[cat]['credit_total'] += tx.credit or 0

        # Opening/closing from first/last balance
        balances = [(tx.date, tx.balance) for tx in txs if tx.balance is not None]
        balances.sort()
        opening = balances[0][1] if balances else None
        closing = balances[-1][1] if balances else None

        # Collect warnings from files for this entity
        entity_warnings = []
        entity_validation_issues = []
        for fr in file_reports:
            if fr.entity_hint == entity_name:
                entity_warnings.extend(fr.warnings)
                if not fr.validation.ok:
                    entity_validation_issues.append(fr.file_path)

        # Accounts for this entity
        accounts = set(tx.raw_row.get('account') for tx in txs if tx.raw_row.get('account'))

        summary = EntitySummary(
            entity=entity_name,
            account_number=', '.join(sorted(filter(None, accounts))) or None,
            bank=txs[0].raw_row.get('file', '').split('_')[0] if txs else 'Unknown',
            files_processed=len(set(tx.raw_row.get('file') for tx in txs)),
            total_transactions=len(txs),
            period_start=dates[0] if dates else '',
            period_end=dates[-1] if dates else '',
            total_debits=round(total_debits, 2),
            total_credits=round(total_credits, 2),
            net_flow=round(total_credits - total_debits, 2),
            opening_balance=opening,
            closing_balance=closing,
            categories=dict(categories),
            validation_issues=entity_validation_issues,
            warnings=entity_warnings,
        )
        entities[entity_name] = summary
        print(f"  {entity_name}: {len(txs)} txns, debits ${total_debits:,.2f}, credits ${total_credits:,.2f}, net ${total_credits - total_debits:,.2f}")

    # Step 5: Duplicate detection
    print("\nStep 5: Checking for duplicates...")
    seen = defaultdict(list)
    for tx in all_transactions:
        key = (tx.date, tx.description, tx.debit, tx.credit, tx.raw_row.get('entity'))
        seen[key].append(tx)

    duplicates = {k: v for k, v in seen.items() if len(v) > 1}
    if duplicates:
        print(f"  ⚠ {len(duplicates)} potential duplicate transaction groups found")
        anomalies.append({
            'type': 'duplicates',
            'detail': f'{len(duplicates)} potential duplicate groups across files',
            'count': len(duplicates),
        })
    else:
        print(f"  ✓ No duplicates detected")

    print(f"\nPipeline complete.")

    return {
        'entities': entities,
        'all_transactions': all_transactions,
        'transfers': all_transfers,
        'matched_transfers': matched_pairs,
        'unmatched_transfers': unmatched,
        'owner_a_reimbursements': owner_a_reimbursements,
        'owner_a_holding': owner_a_holding,
        'ali_reimbursements': ali_reimbursements,
        'ali_advances': ali_advances,
        'file_reports': file_reports,
        'anomalies': anomalies,
        'run_timestamp': datetime.now().isoformat(),
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(pipeline_result: dict, output_dir: str = 'output') -> str:
    """Generate comprehensive financial portrait as Markdown report."""
    out = Path(output_dir)
    out.mkdir(exist_ok=True)

    entities = pipeline_result['entities']
    transfers = pipeline_result['transfers']
    matched = pipeline_result['matched_transfers']
    unmatched = pipeline_result['unmatched_transfers']
    owner_a_reimb = pipeline_result['owner_a_reimbursements']
    owner_a_hold = pipeline_result['owner_a_holding']
    ali_reimb = pipeline_result['ali_reimbursements']
    ali_adv = pipeline_result['ali_advances']
    anomalies = pipeline_result['anomalies']
    all_txns = pipeline_result['all_transactions']

    lines = []
    lines.append("# PORTRAIT FINANCIER — FORENSIC BOOKKEEPING")
    lines.append(f"**Généré:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Fichiers traités:** {len(pipeline_result['file_reports'])}")
    lines.append(f"**Transactions totales:** {len(all_txns)}")
    lines.append("")

    # --- Entity summaries ---
    lines.append("## 1. RÉSUMÉ PAR ENTITÉ")
    lines.append("")
    lines.append("| Entité | Compte | Fichiers | Transactions | Débits | Crédits | Net | Période |")
    lines.append("|--------|--------|----------|-------------|--------|---------|-----|---------|")
    grand_debits = 0
    grand_credits = 0
    for name, s in sorted(entities.items()):
        grand_debits += s.total_debits
        grand_credits += s.total_credits
        lines.append(
            f"| {name} | {s.account_number or 'N/A'} | {s.files_processed} | {s.total_transactions} | "
            f"${s.total_debits:,.0f} | ${s.total_credits:,.0f} | ${s.net_flow:,.0f} | "
            f"{s.period_start} → {s.period_end} |"
        )
    lines.append(
        f"| **TOTAL** | | | **{len(all_txns)}** | "
        f"**${grand_debits:,.0f}** | **${grand_credits:,.0f}** | **${grand_credits - grand_debits:,.0f}** | |"
    )
    lines.append("")

    # --- Inter-company transfer matrix ---
    lines.append("## 2. MATRICE DE TRANSFERTS INTER-COMPAGNIES")
    lines.append("")
    lines.append("Argent envoyé de Source → Destination:")
    lines.append("")

    # Build matrix
    transfer_matrix = defaultdict(lambda: defaultdict(float))
    for t in transfers:
        if t.transfer_type == 'intercompany':
            transfer_matrix[t.source_entity][t.destination_entity] += t.amount

    all_entities = sorted(set(list(transfer_matrix.keys()) + [d for s in transfer_matrix.values() for d in s]))
    if all_entities:
        header = "| De \\ À | " + " | ".join(all_entities) + " | Total envoyé |"
        separator = "|--------|" + "|".join(["--------"] * len(all_entities)) + "|-------------|"
        lines.append(header)
        lines.append(separator)
        for src in all_entities:
            row_total = sum(transfer_matrix[src].values())
            cells = []
            for dst in all_entities:
                val = transfer_matrix[src][dst]
                cells.append(f"${val:,.0f}" if val > 0 else "—")
            lines.append(f"| **{src}** | " + " | ".join(cells) + f" | **${row_total:,.0f}** |")
    lines.append("")

    # --- Owner_A & Owner_B: Reimbursement vs Shareholder Advance ---
    lines.append("## 3. OWNER_A — REMBOURSEMENTS vs AVANCES ACTIONNAIRE")
    lines.append("")

    reimb_total = sum(t.amount for t in owner_a_reimb)
    hold_total = sum(t.amount for t in owner_a_hold)
    lines.append("### Résumé Owner_A")
    lines.append("")
    lines.append("| Type | Montant | # Transferts | Description |")
    lines.append("|------|---------|-------------|-------------|")
    lines.append(f"| **Remboursement** (Interac + compte 089511) | **${reimb_total:,.2f}** | {len(owner_a_reimb)} | Owner_A a payé fournisseurs avec CC perso, compagnies le remboursent |")
    lines.append(f"| **Avance actionnaire** (Holding 092483) | **${hold_total:,.2f}** | {len(owner_a_hold)} | Rémunération via holding (Owner_A+Siam, Owner_B 15%) |")
    lines.append(f"| **TOTAL sorties vers Owner_A** | **${reimb_total + hold_total:,.2f}** | {len(owner_a_reimb) + len(owner_a_hold)} | |")
    lines.append("")

    # Reimbursements by entity
    from collections import defaultdict as dd
    reimb_by_entity = dd(float)
    for t in owner_a_reimb:
        reimb_by_entity[t.source_entity] += t.amount
    lines.append("#### Remboursements par entité:")
    lines.append("| Entité | Montant |")
    lines.append("|--------|---------|")
    for e, total in sorted(reimb_by_entity.items(), key=lambda x: -x[1]):
        lines.append(f"| {e} | ${total:,.2f} |")
    lines.append("")

    # Holding by entity
    hold_by_entity = dd(float)
    for t in owner_a_hold:
        hold_by_entity[t.source_entity] += t.amount
    lines.append("#### Avances actionnaire par entité:")
    lines.append("| Entité | Montant |")
    lines.append("|--------|---------|")
    for e, total in sorted(hold_by_entity.items(), key=lambda x: -x[1]):
        lines.append(f"| {e} | ${total:,.2f} |")
    lines.append("")

    # Monthly breakdown
    reimb_by_month = dd(float)
    hold_by_month = dd(float)
    for t in owner_a_reimb:
        reimb_by_month[t.date[:7]] += t.amount
    for t in owner_a_hold:
        hold_by_month[t.date[:7]] += t.amount
    all_months = sorted(set(list(reimb_by_month.keys()) + list(hold_by_month.keys())))
    lines.append("#### Évolution mensuelle:")
    lines.append("| Mois | Remboursement | Avance Holding | Total |")
    lines.append("|------|--------------|----------------|-------|")
    for m in all_months:
        r = reimb_by_month.get(m, 0)
        h = hold_by_month.get(m, 0)
        lines.append(f"| {m} | ${r:,.0f} | ${h:,.0f} | ${r+h:,.0f} |")
    lines.append("")

    # --- Owner_B ---
    lines.append("## 3b. ALI — REMBOURSEMENTS vs AVANCES")
    lines.append("")
    ali_reimb_total = sum(t.amount for t in ali_reimb)
    ali_adv_total = sum(t.amount for t in ali_adv)
    lines.append("| Type | Montant | # Transferts |")
    lines.append("|------|---------|-------------|")
    lines.append(f"| **Remboursement** (Interac à Owner_B) | **${ali_reimb_total:,.2f}** | {len(ali_reimb)} |")
    lines.append(f"| **Avance** (Owner_B Holding) | **${ali_adv_total:,.2f}** | {len(ali_adv)} |")
    lines.append(f"| **TOTAL Owner_B** | **${ali_reimb_total + ali_adv_total:,.2f}** | {len(ali_reimb) + len(ali_adv)} |")
    lines.append("")

    # --- Comparison ---
    lines.append("## 3c. COMPARAISON OWNER_A vs ALI")
    lines.append("")
    lines.append("| | Owner_A | Owner_B | Ratio |")
    lines.append("|---|--------|-----|-------|")
    owner_a_total = reimb_total + hold_total
    ali_total = ali_reimb_total + ali_adv_total
    ratio = f"{owner_a_total/ali_total:.1f}x" if ali_total > 0 else "N/A"
    lines.append(f"| Remboursement | ${reimb_total:,.0f} | ${ali_reimb_total:,.0f} | |")
    lines.append(f"| Avance/Rémunération | ${hold_total:,.0f} | ${ali_adv_total:,.0f} | |")
    lines.append(f"| **TOTAL** | **${owner_a_total:,.0f}** | **${ali_total:,.0f}** | **{ratio}** |")
    lines.append("")

    # --- All Interac/external transfers ---
    lines.append("## 4. TOUS LES TRANSFERTS SORTANTS (NON INTER-COMPAGNIES)")
    lines.append("")
    external_out = [t for t in transfers if t.transfer_type in ('interac_out', 'transfer_out')]
    if external_out:
        # Group by recipient
        by_recipient = defaultdict(lambda: {'total': 0, 'count': 0, 'dates': []})
        for t in external_out:
            dest = t.destination_entity
            by_recipient[dest]['total'] += t.amount
            by_recipient[dest]['count'] += 1
            by_recipient[dest]['dates'].append(t.date)

        lines.append("| Destinataire | Total | # Transferts | Première | Dernière |")
        lines.append("|-------------|-------|-------------|----------|----------|")
        for dest, info in sorted(by_recipient.items(), key=lambda x: -x[1]['total']):
            dates_sorted = sorted(info['dates'])
            lines.append(f"| {dest} | ${info['total']:,.2f} | {info['count']} | {dates_sorted[0]} | {dates_sorted[-1]} |")
    lines.append("")

    # --- Category breakdown per entity ---
    lines.append("## 5. VENTILATION PAR CATÉGORIE")
    lines.append("")
    for name, s in sorted(entities.items()):
        lines.append(f"### {name}")
        lines.append("")
        lines.append("| Catégorie | Débits | Crédits | # Transactions |")
        lines.append("|-----------|--------|---------|---------------|")
        for cat, data in sorted(s.categories.items(), key=lambda x: -x[1]['debit_total']):
            lines.append(
                f"| {cat} | ${data['debit_total']:,.0f} | ${data['credit_total']:,.0f} | {data['count']} |"
            )
        lines.append("")

    # --- Unmatched transfers ---
    if unmatched:
        lines.append("## 6. TRANSFERTS NON-MATCHÉS (À VÉRIFIER)")
        lines.append("")
        lines.append(f"**{len(unmatched)} transferts inter-compagnies sans contrepartie trouvée.**")
        lines.append("Ces transferts apparaissent d'un côté mais pas de l'autre.")
        lines.append("")
        lines.append("| Date | Montant | Source | Destination | Description |")
        lines.append("|------|---------|--------|-------------|-------------|")
        for t in sorted(unmatched, key=lambda x: (-x.amount, x.date)):
            lines.append(f"| {t.date} | ${t.amount:,.2f} | {t.source_entity} | {t.destination_entity} | {t.description[:60]} |")
        lines.append("")

    # --- Anomalies ---
    if anomalies:
        lines.append("## 7. ANOMALIES DÉTECTÉES")
        lines.append("")
        for a in anomalies:
            lines.append(f"- **{a['type']}**: {a['detail']}")
        lines.append("")

    # --- Uncategorized transactions ---
    uncategorized = [tx for tx in all_txns if tx.raw_row.get('categorization', {}).get('category') == 'uncategorized']
    if uncategorized:
        lines.append("## 8. TRANSACTIONS NON-CATÉGORISÉES")
        lines.append(f"\n**{len(uncategorized)} transactions** n'ont pas pu être classifiées automatiquement.\n")
        # Group by description pattern
        uncat_patterns = defaultdict(lambda: {'count': 0, 'total_debit': 0, 'total_credit': 0})
        for tx in uncategorized:
            # Truncate description to first 40 chars as pattern
            pattern = tx.description[:40]
            uncat_patterns[pattern]['count'] += 1
            uncat_patterns[pattern]['total_debit'] += tx.debit or 0
            uncat_patterns[pattern]['total_credit'] += tx.credit or 0

        lines.append("| Pattern | # | Total Débit | Total Crédit |")
        lines.append("|---------|---|------------|-------------|")
        for pattern, data in sorted(uncat_patterns.items(), key=lambda x: -(x[1]['total_debit'] + x[1]['total_credit']))[:30]:
            lines.append(f"| {pattern} | {data['count']} | ${data['total_debit']:,.0f} | ${data['total_credit']:,.0f} |")
        lines.append("")

    report_text = '\n'.join(lines)

    # Write report
    report_path = out / 'PORTRAIT_FINANCIER.md'
    report_path.write_text(report_text, encoding='utf-8')
    print(f"\n  Report written to: {report_path}")

    # Write transfers CSV for detailed analysis
    transfers_path = out / 'transfers_all.csv'
    with open(transfers_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['date', 'amount', 'source_entity', 'source_account',
                        'destination_entity', 'destination_account',
                        'transfer_type', 'matched', 'description', 'file'])
        for t in sorted(transfers, key=lambda x: x.date):
            writer.writerow([t.date, t.amount, t.source_entity, t.source_account,
                           t.destination_entity, t.destination_account,
                           t.transfer_type, t.matched, t.description, t.file_path])
    print(f"  Transfers CSV: {transfers_path}")

    # Write Owner_A transfers specifically (reimbursement + holding combined)
    all_owner_a = owner_a_reimb + owner_a_hold
    if all_owner_a:
        owner_a_path = out / 'owner_a_transfers.csv'
        with open(owner_a_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['date', 'amount', 'from', 'to', 'type', 'description', 'file'])
            for t in sorted(all_owner_a, key=lambda x: x.date):
                xfer_type = 'remboursement' if t.transfer_type == 'owner_a_reimbursement' else 'avance_actionnaire'
                writer.writerow([t.date, t.amount, t.source_entity, t.destination_entity,
                               xfer_type, t.description, t.file_path])
        print(f"  Owner_A transfers CSV: {owner_a_path}")

    # Write Owner_B transfers
    all_owner_b = ali_reimb + ali_adv
    if all_owner_b:
        ali_path = out / 'ali_transfers.csv'
        with open(ali_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['date', 'amount', 'from', 'to', 'type', 'description', 'file'])
            for t in sorted(all_owner_b, key=lambda x: x.date):
                xfer_type = 'remboursement' if ALI_REIMBURSEMENT_PATTERN.search(t.destination_entity or '') else 'avance'
                writer.writerow([t.date, t.amount, t.source_entity, t.destination_entity,
                               xfer_type, t.description, t.file_path])
        print(f"  Owner_B transfers CSV: {ali_path}")

    # Write master transactions CSV
    master_path = out / 'master_transactions.csv'
    with open(master_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['date', 'entity', 'account', 'description', 'debit', 'credit',
                        'balance', 'category', 'category_label', 'source_type', 'file'])
        for tx in sorted(all_txns, key=lambda x: (x.raw_row.get('entity', ''), x.date)):
            cat = tx.raw_row.get('categorization', {})
            writer.writerow([
                tx.date, tx.raw_row.get('entity'), tx.raw_row.get('account'),
                tx.description, tx.debit or '', tx.credit or '',
                tx.balance if tx.balance is not None else '',
                cat.get('category', ''), cat.get('label', ''),
                tx.raw_row.get('source_type', 'csv'),
                tx.raw_row.get('file', ''),
            ])
    print(f"  Master transactions CSV: {master_path}")

    return str(report_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    result = run_pipeline()
    report_path = generate_report(result)
    print(f"\n✓ Done. Open report: {report_path}")
