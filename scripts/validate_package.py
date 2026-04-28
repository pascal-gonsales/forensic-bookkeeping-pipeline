#!/usr/bin/env python3
"""
Validate Package — pre-flight check for a forensic-bookkeeping v1.2 trustee package.

Modes
-----
  --mode template    Schema-only: placeholders allowed. Use to lint the Skill itself.
  --mode package     (default) Required schedules/logs/registry must exist; no placeholders
                     in non-BLOCKED rows; entity folders must exist; statuses must be valid.
  --strict           Every CONFIRMED row references a registered source; SHA256 verified;
                     forbidden statuses fail; decisions.jsonl required-fields validated.
  --handoff          Implies --strict, plus requires trustee-briefing.md and forbids
                     INFERRED rows in confirmed sections.

Required outputs in package mode:
  employee-claims.csv, das-tax-schedule.csv, creditor-schedule.csv,
  personal-debt-schedule.csv, exception-log.csv, decisions.jsonl,
  source_registry.csv OR source_registry.json

In handoff mode, additionally:
  trustee-briefing.md

Exit codes:
  0  package is ready to deliver (under the chosen mode)
  1  validation failed
  2  source registry SHA256 mismatch (rerun source_registry.py and review)

Usage:
    python scripts/validate_package.py <working_dir> --mode package --strict --handoff
"""

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

VALID_CONFIDENCE = {'CONFIRMED', 'INFERRED', 'NEEDS_REVIEW', 'BLOCKED'}
FORBIDDEN_CONFIDENCE = {'VERIFY', 'TBD', 'MAYBE', 'LOOK INTO', ''}
VALID_RESOLUTION = {'OPEN', 'RESOLVED', 'SUPERSEDED', ''}

REQUIRED_CSVS = [
    'employee-claims.csv',
    'das-tax-schedule.csv',
    'creditor-schedule.csv',
    'personal-debt-schedule.csv',
    'exception-log.csv',
]

REQUIRED_DECISION_FIELDS = {
    'ts', 'entity', 'field', 'value', 'basis',
    'source_id', 'source', 'source_locator',
    'confidence_status', 'session',
}

PLACEHOLDER_PATTERNS = [
    re.compile(r'^<[^>]+>$'),                     # <entity-slug>, <filename>
    re.compile(r'YYYY-MM-DD'),
    re.compile(r'YYYY-MM'),
    re.compile(r'^\s*$'),                         # blank
]

ZERO_HASH = '0' * 64

# Domains where a row carries a material amount and must have full source columns.
# The "amount" column varies by template — DAS uses balance_owed.
AMOUNT_REQUIRED_CSVS = {
    'employee-claims.csv': 'amount',
    'das-tax-schedule.csv': 'balance_owed',
    'creditor-schedule.csv': 'amount',
    'personal-debt-schedule.csv': 'amount',
}

# Columns required on every material-amount row, in addition to the per-CSV amount column.
AMOUNT_ROW_COLUMNS = {
    'confidence_status', 'source_id', 'source', 'source_locator',
}

# Exception log uses dual-status columns plus optional amount.
EXCEPTION_REQUIRED_COLUMNS = {
    'id', 'priority', 'entity', 'domain', 'description', 'discovered_date',
    'amount', 'confidence_status', 'resolution_status',
    'source_id', 'source', 'source_locator',
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def is_placeholder(value: str) -> bool:
    if value is None:
        return True
    s = value.strip()
    if not s:
        return True
    return any(p.search(s) for p in PLACEHOLDER_PATTERNS)


def find_required_csvs(root: Path, names: list) -> dict:
    """Locate required CSVs anywhere under root. Skip files under templates/ unless
    the package itself IS a templates/ directory (template mode)."""
    is_templates_root = root.name == 'templates' or root.parent.name == 'templates'
    found = {}
    for name in names:
        matches = list(root.rglob(name))
        if not matches:
            continue
        if is_templates_root:
            found[name] = matches[0]
        else:
            non_template = [m for m in matches if 'templates' not in m.parts and 'legacy' not in m.parts]
            found[name] = non_template[0] if non_template else None
    return found


def load_registry(root: Path, registry_arg: str | None) -> tuple[dict, Path | None]:
    """Load source registry. Returns (entries_by_source_id, path_or_None).

    Accepts either CSV (rows with source_id, path, sha256, ...) or JSON (path-keyed).
    Resolves paths relative to root.
    """
    candidates = []
    if registry_arg:
        candidates.append(Path(registry_arg))
    candidates.extend([
        root / 'source_registry.csv',
        root / 'source_registry.json',
    ])
    # Search recursively as a fallback (skipping templates/ and legacy/)
    for name in ('source_registry.csv', 'source_registry.json'):
        for hit in root.rglob(name):
            if 'templates' in hit.parts or 'legacy' in hit.parts:
                continue
            candidates.append(hit)

    for c in candidates:
        if c and c.exists() and c.is_file():
            return _parse_registry(c, root), c
    return {}, None


def _parse_registry(path: Path, root: Path) -> dict:
    entries = {}
    if path.suffix.lower() == '.json':
        try:
            with open(path) as f:
                data = json.load(f)
        except json.JSONDecodeError:
            return {}
        # JSON form is keyed by relative path; synthesize source_id if absent.
        for rel_path, meta in data.items():
            sid = meta.get('source_id') or f'PATH:{rel_path}'
            entries[sid] = {
                'source_id': sid,
                'path': rel_path,
                'sha256': meta.get('sha256', ''),
                'size_bytes': meta.get('size_bytes', 0),
                'first_seen': meta.get('first_seen', ''),
                'last_verified': meta.get('last_verified', ''),
                'entity': meta.get('entity', ''),
                'domain': meta.get('domain', ''),
                'document_type': meta.get('document_type', ''),
                'obtained_from': meta.get('obtained_from', ''),
                'date_on_document': meta.get('date_on_document', ''),
            }
        return entries
    # CSV form
    with open(path, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = (row.get('source_id') or '').strip()
            if not sid:
                continue
            entries[sid] = {k: (v or '').strip() for k, v in row.items()}
    return entries


def compute_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def validate_amount_csv(csv_path: Path, root: Path, registry: dict, mode: str,
                        strict: bool, handoff: bool) -> list:
    errors = []
    name = csv_path.name
    amount_col = AMOUNT_REQUIRED_CSVS.get(name, 'amount')
    with open(csv_path, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        cols = set(reader.fieldnames or [])
        required_cols = AMOUNT_ROW_COLUMNS | {amount_col}
        missing_cols = required_cols - cols
        if missing_cols:
            errors.append(f'{name}: missing required columns: {sorted(missing_cols)}')
            return errors

        for i, row in enumerate(reader, start=2):
            row_id = f'{name}:row={i}'
            entity = (row.get('entity') or '').strip()
            confidence = (row.get('confidence_status') or '').strip().upper()
            source_id = (row.get('source_id') or '').strip()
            source = (row.get('source') or '').strip()
            source_locator = (row.get('source_locator') or '').strip()

            # Skip whole-template rows (placeholder entity) only in template mode
            row_is_placeholder = (
                is_placeholder(entity) or is_placeholder(source) or is_placeholder(source_id)
            )
            if mode == 'template':
                # Schema-shape check is enough; statuses still must be in valid set
                if confidence and confidence not in VALID_CONFIDENCE | FORBIDDEN_CONFIDENCE:
                    errors.append(f'{row_id}: unknown confidence_status {confidence!r}')
                if confidence in FORBIDDEN_CONFIDENCE - {''}:
                    errors.append(f'{row_id}: forbidden confidence_status {confidence!r}')
                continue

            # Package mode and beyond
            if confidence in FORBIDDEN_CONFIDENCE - {''}:
                errors.append(f'{row_id}: forbidden confidence_status {confidence!r} '
                              f'(use one of {sorted(VALID_CONFIDENCE)})')
            elif confidence and confidence not in VALID_CONFIDENCE:
                errors.append(f'{row_id}: unknown confidence_status {confidence!r}')
            elif not confidence:
                errors.append(f'{row_id}: empty confidence_status')

            if row_is_placeholder:
                errors.append(f'{row_id}: placeholder values present in package mode '
                              f'(entity={entity!r}, source_id={source_id!r}, source={source!r})')
                continue

            # Entity folder must exist (unless entity is global/cross-entity)
            if entity and entity not in ('global', 'cross-entity'):
                entity_dir = root / 'entities' / entity
                if not entity_dir.is_dir():
                    errors.append(f'{row_id}: entity {entity!r} has no folder at entities/{entity}/')

            # BLOCKED rows allowed to have source_id == 'none' and empty source/locator
            if confidence == 'BLOCKED':
                continue

            # Non-BLOCKED material rows must carry source_id, source, source_locator
            if not source_id or source_id.lower() == 'none':
                errors.append(f'{row_id}: missing source_id (required when '
                              f'confidence_status != BLOCKED)')
            if not source:
                errors.append(f'{row_id}: missing source filename')
            if not source_locator:
                errors.append(f'{row_id}: missing source_locator (row/page/sheet/entry id)')

            # Strict checks
            if strict and confidence == 'CONFIRMED':
                # Allow user_confirmation:* as source_id without registry lookup
                if source_id and not source_id.startswith('user_confirmation'):
                    if source_id not in registry:
                        errors.append(
                            f'{row_id}: CONFIRMED row references source_id '
                            f'{source_id!r} which is not in the source registry')
                    else:
                        entry = registry[source_id]
                        rel = entry.get('path', '')
                        abs_path = (root / rel) if rel else None
                        if abs_path and abs_path.exists():
                            actual = compute_sha256(abs_path)
                            expected = entry.get('sha256', '')
                            if expected and actual != expected:
                                errors.append(
                                    f'{row_id}: SHA256 mismatch for source_id '
                                    f'{source_id!r} (expected {expected[:16]}…, '
                                    f'got {actual[:16]}…)')
                        else:
                            errors.append(
                                f'{row_id}: registry entry for {source_id!r} points '
                                f'to missing file {rel!r}')

            # Handoff mode forbids INFERRED in confirmed-section deliverables
            if handoff and confidence == 'INFERRED' and name in {
                'employee-claims.csv', 'das-tax-schedule.csv',
                'creditor-schedule.csv', 'personal-debt-schedule.csv',
            }:
                errors.append(f'{row_id}: INFERRED row not allowed in handoff mode '
                              f'(confidence-section deliverable)')

    return errors


def validate_exception_log(csv_path: Path, mode: str) -> list:
    errors = []
    name = csv_path.name
    with open(csv_path, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        cols = set(reader.fieldnames or [])
        missing = EXCEPTION_REQUIRED_COLUMNS - cols
        if missing:
            errors.append(f'{name}: missing required columns: {sorted(missing)}')
            return errors
        for i, row in enumerate(reader, start=2):
            row_id = f'{name}:row={i}'
            confidence = (row.get('confidence_status') or '').strip().upper()
            resolution = (row.get('resolution_status') or '').strip().upper()
            if confidence in FORBIDDEN_CONFIDENCE - {''}:
                errors.append(f'{row_id}: forbidden confidence_status {confidence!r}')
            elif confidence and confidence not in VALID_CONFIDENCE:
                errors.append(f'{row_id}: unknown confidence_status {confidence!r}')
            if resolution and resolution not in VALID_RESOLUTION - {''}:
                errors.append(f'{row_id}: unknown resolution_status {resolution!r}')
            # Cross-status sanity: never mix lifecycle with confidence in either field
            if confidence in {'OPEN', 'RESOLVED', 'SUPERSEDED'}:
                errors.append(f'{row_id}: lifecycle value {confidence!r} found in '
                              f'confidence_status column')
            if resolution in {'CONFIRMED', 'INFERRED', 'NEEDS_REVIEW', 'BLOCKED'}:
                errors.append(f'{row_id}: confidence value {resolution!r} found in '
                              f'resolution_status column')
    return errors


def validate_decisions_jsonl(path: Path, mode: str, strict: bool) -> list:
    errors = []
    if not path.exists():
        return [f'{path.name}: file missing']
    with open(path, encoding='utf-8') as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f'decisions.jsonl:line={i}: invalid JSON ({e})')
                continue
            missing = REQUIRED_DECISION_FIELDS - set(obj.keys())
            if missing:
                errors.append(
                    f'decisions.jsonl:line={i}: missing required fields '
                    f'{sorted(missing)}')
            confidence = str(obj.get('confidence_status', '')).upper()
            if confidence in FORBIDDEN_CONFIDENCE - {''}:
                errors.append(f'decisions.jsonl:line={i}: forbidden confidence_status '
                              f'{confidence!r}')
            elif confidence and confidence not in VALID_CONFIDENCE:
                errors.append(f'decisions.jsonl:line={i}: unknown confidence_status '
                              f'{confidence!r}')
            # `basis` must not look like statutory interpretation in strict mode
            if strict:
                basis = str(obj.get('basis', '')).lower()
                legal_terms = (
                    ' s.', ' bia ', ' loi ', ' itc', ' ita ', 'art.', 'paragraph',
                    'subparagraph', 'statutory interpretation', 'jurisprudence',
                )
                if any(t in f' {basis} ' for t in legal_terms):
                    errors.append(
                        f'decisions.jsonl:line={i}: `basis` looks like a legal '
                        f'interpretation; route to trustee/counsel instead')
    return errors


def validate_trustee_briefing(path: Path) -> list:
    errors = []
    if not path.exists():
        return [f'trustee-briefing.md: missing (required in handoff mode)']
    text = path.read_text(encoding='utf-8')
    # Must mention the canonical sections
    must_have = [
        'Confirmed numbers',
        'Per-entity status snapshot',
        'INFERRED items',
        'What\'s blocked',
        'Not included because blocked',
        'Questions for trustee',
        'Files attached',
        'Confidence statement',
    ]
    for needle in must_have:
        if needle not in text:
            errors.append(f'trustee-briefing.md: missing required section header '
                          f'"{needle}"')
    return errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(description='Validate trustee package readiness (v1.2).')
    p.add_argument('working_dir', help='Root directory of the package (or skill folder)')
    p.add_argument('--mode', choices=['template', 'package'], default='package')
    p.add_argument('--strict', action='store_true',
                   help='Verify CONFIRMED rows reference registered sources and SHA256 matches.')
    p.add_argument('--handoff', action='store_true',
                   help='Implies --strict, requires trustee-briefing.md, forbids INFERRED in confirmed sections.')
    p.add_argument('--registry', default=None,
                   help='Explicit source registry file (CSV or JSON).')
    args = p.parse_args()

    if args.handoff:
        args.strict = True

    root = Path(args.working_dir).resolve()
    if not root.is_dir():
        print(f'ERROR: {root} is not a directory', file=sys.stderr)
        return 1

    print(f'Validating: {root}')
    print(f'Mode: {args.mode}  strict={args.strict}  handoff={args.handoff}')

    errors: list[str] = []
    registry_mismatch = False

    # 1. Find required CSVs
    csvs = find_required_csvs(root, REQUIRED_CSVS)
    missing_csvs = [n for n in REQUIRED_CSVS if not csvs.get(n)]
    if args.mode == 'package' and missing_csvs:
        errors.append(f'package mode: missing required schedules/logs: {missing_csvs}')

    # 2. Load source registry (required in package mode and beyond)
    registry, registry_path = load_registry(root, args.registry)
    if args.mode == 'package' and registry_path is None:
        errors.append('package mode: source_registry.csv (or .json) not found')
    if registry_path:
        print(f'Source registry: {registry_path.relative_to(root) if registry_path.is_relative_to(root) else registry_path}')
        print(f'  entries: {len(registry)}')

    # 3. Validate decisions.jsonl
    decisions_path = next(iter([p for p in root.rglob('decisions.jsonl')
                                if 'templates' not in p.parts
                                and 'legacy' not in p.parts]), None)
    if args.mode == 'package' and decisions_path is None:
        errors.append('package mode: decisions.jsonl not found')
    if decisions_path:
        errors.extend(validate_decisions_jsonl(decisions_path, args.mode, args.strict))

    # 4. Validate per-CSV
    cross_cutting_errors = list(errors)  # snapshot of pre-CSV errors to print later
    for name, path in csvs.items():
        if path is None:
            continue
        if name == 'exception-log.csv':
            errs = validate_exception_log(path, args.mode)
        elif name in AMOUNT_REQUIRED_CSVS:
            errs = validate_amount_csv(path, root, registry, args.mode,
                                       args.strict, args.handoff)
        else:
            errs = []
        if errs:
            print(f'\n{name}: {len(errs)} validation errors')
            for e in errs:
                print(f'  - {e}')
            # Detect SHA256 mismatch specifically
            if any('SHA256 mismatch' in e for e in errs):
                registry_mismatch = True
            errors.extend(errs)
        else:
            print(f'{name}: OK')

    # Print cross-cutting errors (missing files, decisions.jsonl issues)
    if cross_cutting_errors:
        print(f'\n[cross-cutting] {len(cross_cutting_errors)} errors')
        for e in cross_cutting_errors:
            print(f'  - {e}')

    # 5. Trustee briefing required in handoff mode
    if args.handoff:
        briefing = next(iter([p for p in root.rglob('trustee-briefing.md')
                              if 'templates' not in p.parts
                              and 'legacy' not in p.parts]), None)
        target = briefing if briefing else root / 'trustee-briefing.md'
        b_errs = validate_trustee_briefing(target)
        if b_errs:
            print(f'\ntrustee-briefing.md: {len(b_errs)} validation errors')
            for e in b_errs:
                print(f'  - {e}')
            errors.extend(b_errs)
        else:
            print(f'trustee-briefing.md: OK')

    # Final verdict
    print(f'\n{"=" * 60}')
    if registry_mismatch:
        print('VALIDATION FAILED (SHA256 mismatch). Re-run source_registry.py and '
              're-verify dependent decisions before delivering.')
        return 2
    if errors:
        print(f'VALIDATION FAILED: {len(errors)} errors. Fix before delivering.')
        return 1
    print('VALIDATION PASSED: package is ready under the chosen mode.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
