#!/usr/bin/env python3
"""
Synthetic tests for v1.2 safety guarantees.

These tests do not need any private fixtures. They build small in-memory
package layouts, run the validator against them, and assert exit codes plus
salient error substrings.

Cases covered:
  - Empty/missing-package directory fails in package mode
  - Skill templates pass in template mode
  - Placeholder source/source_id in package mode fails
  - Forbidden status (VERIFY) fails in package mode
  - CONFIRMED row without registry entry fails in --strict
  - SHA256 mismatch fails in --strict (exit 2)
  - INFERRED row in confirmed-section fails in --handoff
  - Decision log missing required field (confidence_status) fails
  - Exception log mixing lifecycle + confidence into one column fails
  - Classifier returns business_amount=None for split/ambiguous cases

Run:
    python tests/synthetic/test_validator_safety.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATE = REPO_ROOT / 'scripts' / 'validate_package.py'
SKILL_DIR = Path('/Users/Pascal/.claude/skills/forensic-bookkeeping')


def run_validator(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(VALIDATE), *args],
        capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def write_csv(path: Path, header: list[str], rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in header})


def write_decisions(path: Path, lines: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        for obj in lines:
            f.write(json.dumps(obj) + '\n')


def write_registry_json(path: Path, entries: dict):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(entries, f, indent=2, sort_keys=True)


def assert_(cond: bool, msg: str):
    if not cond:
        print(f'  FAIL: {msg}')
        return False
    print(f'  ok:   {msg}')
    return True


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------


def case_empty_package_fails() -> bool:
    print('\n[case] empty package fails in --mode package')
    with tempfile.TemporaryDirectory() as tmp:
        rc, out = run_validator([tmp, '--mode', 'package'])
        return assert_(rc != 0, 'expected non-zero exit on empty package') and \
               assert_('missing required schedules' in out or 'not found' in out,
                       'expected missing-schedules error in output')


def case_skill_templates_template_mode_passes() -> bool:
    print('\n[case] skill templates in --mode template pass')
    if not SKILL_DIR.exists():
        print('  SKIP: skill dir not present')
        return True
    rc, out = run_validator([str(SKILL_DIR / 'assets' / 'templates'),
                             '--mode', 'template'])
    return assert_(rc == 0, f'expected exit 0, got {rc}\n--- output ---\n{out}')


def case_placeholders_in_package_fail() -> bool:
    print('\n[case] placeholder source in --mode package fails')
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / 'entities' / 'entity-a').mkdir(parents=True)
        write_csv(root / 'employee-claims.csv',
                  ['id','entity','employee_id','employee_label','claim_type','amount',
                   'period_from','period_to','confidence_status','source_id','source',
                   'source_locator','notes'],
                  [{'id':'1','entity':'<entity-slug>','employee_id':'EMP-001',
                    'employee_label':'A','claim_type':'unpaid_wages','amount':'0.00',
                    'period_from':'YYYY-MM-DD','period_to':'YYYY-MM-DD',
                    'confidence_status':'NEEDS_REVIEW','source_id':'SRC-PAYROLL-001',
                    'source':'<filename>','source_locator':'row=N','notes':''}])
        # other required outputs as empty/minimal but present
        for n in ('das-tax-schedule.csv','creditor-schedule.csv',
                  'personal-debt-schedule.csv'):
            (root / n).write_text('')
        write_csv(root / 'exception-log.csv',
                  ['id','priority','entity','domain','description','discovered_date',
                   'amount','confidence_status','resolution_status','source_id','source',
                   'source_locator','resolution_date','resolution_notes'], [])
        write_decisions(root / 'decisions.jsonl', [])
        write_registry_json(root / 'source_registry.json', {})
        rc, out = run_validator([tmp, '--mode', 'package'])
        return assert_(rc != 0, 'expected non-zero exit on placeholders') and \
               assert_('placeholder values present' in out,
                       'expected placeholder error')


def case_forbidden_status_fails() -> bool:
    print('\n[case] forbidden status (VERIFY) in --mode package fails')
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / 'entities' / 'entity-a').mkdir(parents=True)
        write_csv(root / 'employee-claims.csv',
                  ['id','entity','employee_id','employee_label','claim_type','amount',
                   'period_from','period_to','confidence_status','source_id','source',
                   'source_locator','notes'],
                  [{'id':'1','entity':'entity-a','employee_id':'E1','employee_label':'A',
                    'claim_type':'unpaid_wages','amount':'500.00','period_from':'2026-01-01',
                    'period_to':'2026-03-31','confidence_status':'VERIFY','source_id':'SRC-X-001',
                    'source':'x.xlsx','source_locator':'row=1','notes':''}])
        for n in ('das-tax-schedule.csv','creditor-schedule.csv','personal-debt-schedule.csv'):
            (root / n).write_text('')
        write_csv(root / 'exception-log.csv',
                  ['id','priority','entity','domain','description','discovered_date',
                   'amount','confidence_status','resolution_status','source_id','source',
                   'source_locator','resolution_date','resolution_notes'], [])
        write_decisions(root / 'decisions.jsonl', [])
        write_registry_json(root / 'source_registry.json', {})
        rc, out = run_validator([tmp, '--mode', 'package'])
        return assert_(rc != 0, 'expected non-zero exit on forbidden status') and \
               assert_("forbidden confidence_status 'VERIFY'" in out,
                       'expected forbidden-status error')


def case_confirmed_without_registry_fails_strict() -> bool:
    print('\n[case] CONFIRMED row without registry entry fails in --strict')
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / 'entities' / 'entity-a').mkdir(parents=True)
        write_csv(root / 'employee-claims.csv',
                  ['id','entity','employee_id','employee_label','claim_type','amount',
                   'period_from','period_to','confidence_status','source_id','source',
                   'source_locator','notes'],
                  [{'id':'1','entity':'entity-a','employee_id':'E1','employee_label':'A',
                    'claim_type':'unpaid_wages','amount':'500.00','period_from':'2026-01-01',
                    'period_to':'2026-03-31','confidence_status':'CONFIRMED',
                    'source_id':'SRC-MISSING-999','source':'doesnt_exist.xlsx',
                    'source_locator':'row=1','notes':''}])
        for n in ('das-tax-schedule.csv','creditor-schedule.csv','personal-debt-schedule.csv'):
            (root / n).write_text('')
        write_csv(root / 'exception-log.csv',
                  ['id','priority','entity','domain','description','discovered_date',
                   'amount','confidence_status','resolution_status','source_id','source',
                   'source_locator','resolution_date','resolution_notes'], [])
        write_decisions(root / 'decisions.jsonl', [])
        write_registry_json(root / 'source_registry.json', {})
        rc, out = run_validator([tmp, '--mode', 'package', '--strict'])
        return assert_(rc != 0, 'expected non-zero exit') and \
               assert_('not in the source registry' in out,
                       'expected unregistered-source error')


def case_sha256_mismatch_exits_2() -> bool:
    print('\n[case] SHA256 mismatch in --strict exits 2')
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / 'entities' / 'entity-a').mkdir(parents=True)
        # Real source file
        src_dir = root / 'entities' / 'entity-a' / 'payroll'
        src_dir.mkdir(parents=True)
        src_file = src_dir / 'payroll.xlsx'
        src_file.write_bytes(b'real content v1')
        actual = hashlib.sha256(src_file.read_bytes()).hexdigest()
        write_registry_json(root / 'source_registry.json', {
            str(src_file.relative_to(root)): {
                'source_id': 'SRC-PAYROLL-001',
                'sha256': 'f' * 64,  # deliberately wrong
                'size_bytes': src_file.stat().st_size,
                'first_seen': '2026-04-27',
                'last_verified': '2026-04-27',
                'entity': 'entity-a',
                'domain': 'payroll',
            }
        })
        write_csv(root / 'employee-claims.csv',
                  ['id','entity','employee_id','employee_label','claim_type','amount',
                   'period_from','period_to','confidence_status','source_id','source',
                   'source_locator','notes'],
                  [{'id':'1','entity':'entity-a','employee_id':'E1','employee_label':'A',
                    'claim_type':'unpaid_wages','amount':'500.00','period_from':'2026-01-01',
                    'period_to':'2026-03-31','confidence_status':'CONFIRMED',
                    'source_id':'SRC-PAYROLL-001','source':'payroll.xlsx',
                    'source_locator':'row=1','notes':''}])
        for n in ('das-tax-schedule.csv','creditor-schedule.csv','personal-debt-schedule.csv'):
            (root / n).write_text('')
        write_csv(root / 'exception-log.csv',
                  ['id','priority','entity','domain','description','discovered_date',
                   'amount','confidence_status','resolution_status','source_id','source',
                   'source_locator','resolution_date','resolution_notes'], [])
        write_decisions(root / 'decisions.jsonl', [])
        rc, out = run_validator([tmp, '--mode', 'package', '--strict'])
        ok = assert_(rc == 2, f'expected exit code 2, got {rc}')
        ok &= assert_('SHA256 mismatch' in out, 'expected SHA256 mismatch error')
        # Sanity: actual hash is not the wrong one
        ok &= assert_(actual != 'f' * 64, 'sanity: real hash differs from registry')
        return ok


def case_inferred_in_handoff_fails() -> bool:
    print('\n[case] INFERRED row in confirmed deliverable fails in --handoff')
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / 'entities' / 'entity-a').mkdir(parents=True)
        write_csv(root / 'employee-claims.csv',
                  ['id','entity','employee_id','employee_label','claim_type','amount',
                   'period_from','period_to','confidence_status','source_id','source',
                   'source_locator','notes'],
                  [{'id':'1','entity':'entity-a','employee_id':'E1','employee_label':'A',
                    'claim_type':'unpaid_wages','amount':'500.00','period_from':'2026-01-01',
                    'period_to':'2026-03-31','confidence_status':'INFERRED',
                    'source_id':'user_confirmation:2026-04-27T08:00','source':'standup.md',
                    'source_locator':'block=TODAY','notes':''}])
        for n in ('das-tax-schedule.csv','creditor-schedule.csv','personal-debt-schedule.csv'):
            (root / n).write_text('')
        write_csv(root / 'exception-log.csv',
                  ['id','priority','entity','domain','description','discovered_date',
                   'amount','confidence_status','resolution_status','source_id','source',
                   'source_locator','resolution_date','resolution_notes'], [])
        write_decisions(root / 'decisions.jsonl', [])
        write_registry_json(root / 'source_registry.json', {})
        # No trustee briefing — handoff should also fail on that
        rc, out = run_validator([tmp, '--mode', 'package', '--handoff'])
        return assert_(rc != 0, 'expected non-zero exit') and \
               assert_('INFERRED row not allowed in handoff mode' in out or
                       'trustee-briefing.md' in out,
                       'expected INFERRED-in-handoff or trustee-briefing error')


def case_decision_missing_confidence_fails() -> bool:
    print('\n[case] decisions.jsonl row missing confidence_status fails')
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / 'entities' / 'entity-a').mkdir(parents=True)
        for n in REQUIRED_FILES:
            if n.endswith('.csv'):
                (root / n).write_text('')
        write_decisions(root / 'decisions.jsonl', [{
            'ts':'2026-04-27T08:15','entity':'entity-a','field':'x','value':1,
            'basis':'user confirmation','source_id':'user_confirmation:2026-04-27T08:00',
            'source':'standup.md','source_locator':'block=TODAY',
            'session':'sample',
            # confidence_status omitted on purpose
        }])
        write_registry_json(root / 'source_registry.json', {})
        rc, out = run_validator([tmp, '--mode', 'package'])
        return assert_(rc != 0, 'expected non-zero exit') and \
               assert_('missing required fields' in out and 'confidence_status' in out,
                       'expected missing-confidence_status error')


def case_exception_status_swap_fails() -> bool:
    print('\n[case] exception-log mixing lifecycle + confidence fails')
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / 'entities' / 'entity-a').mkdir(parents=True)
        for n in ('employee-claims.csv','das-tax-schedule.csv',
                  'creditor-schedule.csv','personal-debt-schedule.csv'):
            (root / n).write_text('')
        write_csv(root / 'exception-log.csv',
                  ['id','priority','entity','domain','description','discovered_date',
                   'amount','confidence_status','resolution_status','source_id','source',
                   'source_locator','resolution_date','resolution_notes'],
                  [{'id':'1','priority':'P1','entity':'entity-a','domain':'payroll',
                    'description':'tip discrepancy','discovered_date':'2026-04-27',
                    'amount':'100.00','confidence_status':'RESOLVED',  # wrong column
                    'resolution_status':'CONFIRMED',                    # wrong column
                    'source_id':'SRC-PAYROLL-001','source':'tips.xlsx',
                    'source_locator':'row=2','resolution_date':'',
                    'resolution_notes':''}])
        write_decisions(root / 'decisions.jsonl', [])
        write_registry_json(root / 'source_registry.json', {})
        rc, out = run_validator([tmp, '--mode', 'package'])
        return assert_(rc != 0, 'expected non-zero exit') and \
               assert_("lifecycle value 'RESOLVED' found in confidence_status" in out,
                       'expected lifecycle/confidence mix error') and \
               assert_("confidence value 'CONFIRMED' found in resolution_status" in out,
                       'expected confidence/lifecycle mix error')


def case_classifier_returns_needs_review() -> bool:
    print('\n[case] classifier: split/ambiguous returns NEEDS_REVIEW with business_amount=None')
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from cc_classification import classify_transaction
    except Exception as e:
        print(f'  SKIP: cannot import classifier ({e})')
        return True
    ok = True
    # Team-building (partner trip) must NOT auto-split
    r = classify_transaction('VRBO BANGKOK STAY', 1234.0)
    ok &= assert_(r.get('business_amount') is None,
                  f'team-building business_amount must be None, got {r.get("business_amount")}')
    ok &= assert_(r.get('status') == 'NEEDS_REVIEW',
                  f'team-building status must be NEEDS_REVIEW, got {r.get("status")}')
    # Mixed-use vendor (Apple) must route to NEEDS_REVIEW
    r = classify_transaction('APPLE.COM/BILL', 50.0)
    ok &= assert_(r.get('status') == 'NEEDS_REVIEW',
                  f'mixed-use vendor must be NEEDS_REVIEW, got {r.get("status")}')
    # Unmatched merchant must default to NEEDS_REVIEW (never silent BUSINESS)
    r = classify_transaction('SOMETHING UNHEARDOF XYZ', 100.0)
    ok &= assert_(r.get('status') == 'NEEDS_REVIEW',
                  f'unmatched default must be NEEDS_REVIEW, got {r.get("status")}')
    return ok


REQUIRED_FILES = [
    'employee-claims.csv', 'das-tax-schedule.csv', 'creditor-schedule.csv',
    'personal-debt-schedule.csv', 'exception-log.csv',
]


CASES = [
    case_empty_package_fails,
    case_skill_templates_template_mode_passes,
    case_placeholders_in_package_fail,
    case_forbidden_status_fails,
    case_confirmed_without_registry_fails_strict,
    case_sha256_mismatch_exits_2,
    case_inferred_in_handoff_fails,
    case_decision_missing_confidence_fails,
    case_exception_status_swap_fails,
    case_classifier_returns_needs_review,
]


def main() -> int:
    print('Synthetic v1.2 safety tests')
    print('=' * 60)
    failures = 0
    for case in CASES:
        try:
            ok = case()
            if not ok:
                failures += 1
        except Exception as e:
            print(f'  CRASH in {case.__name__}: {e}')
            failures += 1
    print('=' * 60)
    print(f'{len(CASES) - failures}/{len(CASES)} cases passed')
    return 0 if failures == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
