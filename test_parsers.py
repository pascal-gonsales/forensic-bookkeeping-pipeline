#!/usr/bin/env python3
"""
Test parsers on exactly 1 file per format.
Validates before scaling to full dataset.

Integration tests are fixture-driven. Set the env var
PARSER_TEST_FIXTURE_BASE to point at a local directory containing the
expected fixture files (the file names in PDF_TESTS are placeholders;
override the full path via PARSER_TEST_FIXTURE_BASE_BDC etc. for full
control). Without env vars set, integration tests are skipped — only
the import smoke test runs (matches the OSS distribution / CI behavior).
"""

import json
import os
import sys
from pathlib import Path
from parsers import parse_file

BASE = os.environ.get('PARSER_TEST_FIXTURE_BASE', './data/bank_statements')

TEST_FILES = [
    {
        'path': f"{BASE}/Siam House 2025/SiamHouse_Desjardins_Statement_2025.01.csv",
        'expected_format': 'desjardins_csv',
        'expected_entity': 'Siam House',
        'expected_bank': 'Desjardins',
        'label': 'Desjardins CSV — Siam House Jan 2025',
    },
    {
        'path': f"{BASE}/Garden bistro 2025/GardenBistro_RBC_Statement_2025.12.csv",
        'expected_format': 'rbc_csv',
        'expected_entity': 'Garden Bistro',
        'expected_bank': 'RBC',
        'label': 'RBC CSV — Garden Bistro Dec 2025',
    },
    {
        'path': f"{BASE}/Lotus Kitchen 2025/Business credit card American express/LotusKitchen_Amex_CreditCard_2025.01.csv",
        'expected_format': 'amex_csv',
        'expected_entity': 'Lotus Kitchen',
        'expected_bank': 'Amex',
        'label': 'Amex CSV — Lotus Kitchen Jan 2025',
    },
    {
        'path': f"{BASE}/LotusKitchen_Bank_statement_2026.01.csv",
        'expected_format': 'desjardins_csv',
        'expected_entity': 'Lotus Kitchen',
        'expected_bank': 'Desjardins',
        'label': 'Desjardins CSV — Lotus Kitchen 2026.01 (format change test)',
    },
]


def print_section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def print_validation(result):
    """Print detailed validation results."""
    v = result.validation
    status = "PASS" if v.ok else "FAIL"
    print(f"\n  Validation: {status}")
    for name, check in v.checks.items():
        icon = "✓" if check['passed'] else ("✗" if check['passed'] is False else "—")
        print(f"    {icon} {name}: {check['detail']}")
        if 'mismatches' in check and check['mismatches']:
            for mm in check['mismatches'][:3]:
                print(f"      → Row {mm['row']}, {mm['date']}: expected {mm['expected']}, got {mm['actual']} (diff ${mm['diff']})")


def run_test(test_spec: dict):
    """Run a single parser test. Returns True/False/None (None = skipped, fixture missing)."""
    print_section(test_spec['label'])

    if not Path(test_spec['path']).exists():
        print(f"  SKIP: fixture not found at {test_spec['path']}")
        return None

    result = parse_file(test_spec['path'])
    passed = True

    # Check 1: Format detection
    fmt_ok = result.detected_format == test_spec['expected_format']
    print(f"\n  Format detected: {result.detected_format} {'✓' if fmt_ok else '✗ EXPECTED: ' + test_spec['expected_format']}")
    if not fmt_ok:
        passed = False

    # Check 2: Bank detection
    bank_ok = result.detected_bank == test_spec['expected_bank']
    print(f"  Bank detected: {result.detected_bank} {'✓' if bank_ok else '✗ EXPECTED: ' + test_spec['expected_bank']}")
    if not bank_ok:
        passed = False

    # Check 3: Entity hint
    entity_ok = result.entity_hint == test_spec['expected_entity']
    print(f"  Entity hint: {result.entity_hint} {'✓' if entity_ok else '✗ EXPECTED: ' + test_spec['expected_entity']}")

    # Check 4: Transaction count
    tx_count = len(result.transactions)
    print(f"  Transactions parsed: {tx_count}")
    if tx_count == 0:
        print("  ✗ ZERO TRANSACTIONS — parser failed")
        passed = False

    # Check 5: Account / metadata
    if result.account_number:
        print(f"  Account: {result.account_number}")
    if result.branch_name:
        print(f"  Branch: {result.branch_name}")
    print(f"  Period: {result.period_start} → {result.period_end}")
    print(f"  Raw lines in file: {result.raw_line_count}")

    # Check 6: Financial summary
    total_debits = sum(t.debit or 0 for t in result.transactions)
    total_credits = sum(t.credit or 0 for t in result.transactions)
    print(f"\n  Total debits:  ${total_debits:>12,.2f}")
    print(f"  Total credits: ${total_credits:>12,.2f}")
    print(f"  Net flow:      ${(total_credits - total_debits):>12,.2f}")

    # Check 7: Sample transactions (first 3 + last 1)
    print(f"\n  First 3 transactions:")
    for tx in result.transactions[:3]:
        amt = f"-${tx.debit:,.2f}" if tx.debit else f"+${tx.credit:,.2f}" if tx.credit else "$0.00"
        bal = f"  bal: ${tx.balance:,.2f}" if tx.balance is not None else ""
        print(f"    {tx.date}  {amt:>12}  {tx.description[:60]}{bal}")

    if len(result.transactions) > 3:
        tx = result.transactions[-1]
        amt = f"-${tx.debit:,.2f}" if tx.debit else f"+${tx.credit:,.2f}" if tx.credit else "$0.00"
        bal = f"  bal: ${tx.balance:,.2f}" if tx.balance is not None else ""
        print(f"  Last transaction:")
        print(f"    {tx.date}  {amt:>12}  {tx.description[:60]}{bal}")

    # Check 8: Validation details
    print_validation(result)
    if not result.validation.ok:
        passed = False

    # Check 9: Warnings
    if result.warnings:
        print(f"\n  Warnings ({len(result.warnings)}):")
        for w in result.warnings:
            print(f"    ⚠ {w}")

    return passed


def smoke_test_imports() -> bool:
    """Always-runnable: verify all parser modules import and detect_pdf_format works."""
    print_section("SMOKE: module imports + API surface")
    try:
        from parsers import parse_file, ParseResult, Transaction
        from pdf_parsers_v2 import (
            detect_pdf_format,
            parse_desjardins_pdf_v2,
            parse_rbc_pdf_v2,
            parse_desjardins_cc_pdf_v2,
            parse_rbc_visa_pdf_v2,
            parse_desjardins_visa_perso_pdf_v2,
            parse_bdc_mc_pdf_v2,
            parse_td_visa_pdf_v2,
        )
        from cc_classification import classify_transaction, process_all_cards
        from reconciliation import build_monthly_matrix, reconcile_intercompany
        print("  ✓ All parser modules importable")
        print("  ✓ detect_pdf_format + 7 PDF parser functions present")
        print("  ✓ classify_transaction + reconcile_intercompany present")
        return True
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        return False


def run_pdf_test(label: str, path: str, parser_name: str, expected_format: str):
    """Run a single PDF parser test. Returns True/False/None (None = skipped)."""
    print_section(label)
    if not Path(path).exists():
        print(f"  SKIP: fixture not found at {path}")
        return None
    from pdf_parsers_v2 import detect_pdf_format
    import pdf_parsers_v2 as v2

    fmt = detect_pdf_format(path)
    fmt_ok = fmt == expected_format
    print(f"  Format detected: {fmt} {'✓' if fmt_ok else '✗ EXPECTED: ' + expected_format}")

    parser = getattr(v2, parser_name)
    result = parser(path)
    print(f"  Transactions: {len(result.transactions)}")
    debits = sum(t.debit or 0 for t in result.transactions)
    credits = sum(t.credit or 0 for t in result.transactions)
    print(f"  Total debits:  ${debits:>12,.2f}")
    print(f"  Total credits: ${credits:>12,.2f}")

    passed = fmt_ok and len(result.transactions) > 0
    if not passed:
        if not fmt_ok:
            print("  ✗ Format mismatch")
        if len(result.transactions) == 0:
            print("  ✗ Zero transactions")
    return passed


# PDF integration tests. Fixture paths sourced from env vars to keep the
# OSS distribution free of debtor-specific paths and card identifiers.
# When env vars are unset, these tests skip cleanly.
PDF_TESTS = [
    {
        'label': 'BDC Mastercard PDF',
        'path': os.environ.get('PARSER_TEST_FIXTURE_BDC', ''),
        'parser': 'parse_bdc_mc_pdf_v2',
        'expected_format': 'bdc_mc_pdf',
    },
    {
        'label': 'TD Aeroplan Visa PDF',
        'path': os.environ.get('PARSER_TEST_FIXTURE_TD_VISA', ''),
        'parser': 'parse_td_visa_pdf_v2',
        'expected_format': 'td_visa_pdf',
    },
    {
        'label': 'TD Aeroplan Visa Infinite Privilege PDF',
        'path': os.environ.get('PARSER_TEST_FIXTURE_TD_VISA_PRIVILEGE', ''),
        'parser': 'parse_td_visa_pdf_v2',
        'expected_format': 'td_visa_pdf',
    },
]


def main():
    print("FORENSIC BOOKKEEPING — PARSER TEST SUITE")
    print(f"Date: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}")

    results = []
    results.append(('SMOKE: imports', smoke_test_imports()))

    for test_spec in TEST_FILES:
        results.append((test_spec['label'], run_test(test_spec)))

    for t in PDF_TESTS:
        results.append((t['label'], run_pdf_test(t['label'], t['path'], t['parser'], t['expected_format'])))

    # Summary
    print_section("TEST SUMMARY")
    failed = passed = skipped = 0
    for label, ok in results:
        if ok is None:
            icon = "  SKIP"
            skipped += 1
        elif ok:
            icon = "✓ PASS"
            passed += 1
        else:
            icon = "✗ FAIL"
            failed += 1
        print(f"  {icon}  {label}")

    print(f"\n  {passed} passed, {failed} failed, {skipped} skipped (fixture missing)")
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
