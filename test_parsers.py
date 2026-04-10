#!/usr/bin/env python3
"""
Test parsers on exactly 1 file per format.
Validates before scaling to full dataset.

Tests:
  1. Desjardins CSV — Lotus Kitchen Jan 2025
  2. RBC CSV — Garden Bistro Dec 2025
  3. Amex CSV — Siam House Jan 2025
  4. Desjardins CSV — Siam House 2026.01 (format change test)
"""

import json
import sys
from pathlib import Path
from parsers import parse_file

BASE = "./data/bank_statements"

TEST_FILES = [
    {
        'path': f"{BASE}/Lotus Kitchen 2025/RESTAURANT_B_Desjardins_Statement_2025.01.csv",
        'expected_format': 'desjardins_csv',
        'expected_entity': 'Lotus Kitchen',
        'expected_bank': 'Desjardins',
        'label': 'Desjardins CSV — Lotus Kitchen Jan 2025',
    },
    {
        'path': f"{BASE}/Garden Bistro 2025/GardenBistro_RBC_Statement_2025.12.csv",
        'expected_format': 'rbc_csv',
        'expected_entity': 'Garden Bistro',
        'expected_bank': 'RBC',
        'label': 'RBC CSV — Garden Bistro Dec 2025',
    },
    {
        'path': f"{BASE}/Siam House 2025/Business credit card American express/SiamHouse_Amex_CreditCard_2025.01.csv",
        'expected_format': 'amex_csv',
        'expected_entity': 'Siam House',
        'expected_bank': 'Amex',
        'label': 'Amex CSV — Siam House Jan 2025',
    },
    {
        'path': f"{BASE}/SiamHouse_Bank_statement_2026.01.csv",
        'expected_format': 'desjardins_csv',
        'expected_entity': 'Siam House',
        'expected_bank': 'Desjardins',
        'label': 'Desjardins CSV — Siam House 2026.01 (format change test)',
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


def run_test(test_spec: dict) -> bool:
    """Run a single parser test. Returns True if all checks pass."""
    print_section(test_spec['label'])

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


def main():
    print("FORENSIC BOOKKEEPING — PARSER TEST SUITE")
    print(f"Testing {len(TEST_FILES)} files, 1 per format")
    print(f"Date: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}")

    results = []
    for test_spec in TEST_FILES:
        ok = run_test(test_spec)
        results.append((test_spec['label'], ok))

    # Summary
    print_section("TEST SUMMARY")
    all_passed = True
    for label, ok in results:
        icon = "✓ PASS" if ok else "✗ FAIL"
        print(f"  {icon}  {label}")
        if not ok:
            all_passed = False

    print(f"\n  {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
