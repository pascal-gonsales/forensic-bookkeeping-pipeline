#!/usr/bin/env python3
"""
Source Registry — SHA256 anchor for forensic source documents (v1.2).

Scans a working directory for source documents (PDFs, CSVs, XLSX) and writes
a JSON registry with SHA256 hashes plus the v1.2 metadata fields. Decisions in
`decisions.jsonl` cite source files by `source_id` AND by filename. The registry
lets a reviewer verify the file content has not changed since the decision was
made.

Output schema (one entry per file, keyed by relative path):

    {
      "<rel_path>": {
        "source_id":         "SRC-DOMAIN-NNN",   # stable; preserved across reruns
        "sha256":            "<hex>",
        "size_bytes":        <int>,
        "first_seen":        "<ISO date>",
        "last_verified":     "<ISO date>",
        "entity":            "<slug or 'global' or 'cross-entity'>",
        "domain":            "bank|cc|payroll|tax|creditor|intercompany|other",
        "document_type":     "<short label, e.g. bank_statement_pdf>",
        "obtained_from":     "<portal/source the user pulled it from>",
        "date_on_document":  "<ISO date or empty>",
        "notes":             "<free text>"
      }
    }

Re-running:
  - preserves first_seen and source_id
  - updates last_verified
  - flags hash changes as alerts (exit code 2)
  - flags removed files as alerts

Aligned with the v1.2 forensic-bookkeeping skill (`references/output-schemas.md`).

Usage:
    python scripts/source_registry.py <working_dir> [--output source_registry.json]
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

EXTENSIONS = {'.pdf', '.csv', '.xlsx', '.xlsm', '.tsv'}

DOMAIN_KEYWORDS = {
    'bank': ['bank-statement', 'bank_statement', 'releve', 'desjardins', 'rbc', 'amex', 'bank-statements'],
    'cc': ['credit-card', 'cc_perso', 'cc-perso', 'mastercard', 'visa', 'cc_'],
    'payroll': ['payroll', 'paie', 'nethris', 'cgi', 'agendrix', 'employee', 'tips'],
    'tax': ['tax-account', 'tax_account', 'rp-federal', 'rs-quebec', 'tvq',
            'co-17', 'co17', 't2', 'cnesst', 'rl-1', 'gst', 'hst'],
    'creditor': ['creditor', 'supplier-invoice', 'invoice'],
    'intercompany': ['intercompany', 'interco'],
}

DOCUMENT_TYPE_KEYWORDS = {
    'etat_compte_RP': ['rp_etat', 'rp-etat', 'etat_compte_rp'],
    'etat_compte_RS': ['rs_etat', 'rs-etat', 'etat_compte_rs'],
    'etat_compte_TVQ': ['tvq_etat', 'tvq-etat'],
    'etat_compte_GST': ['gst_etat', 'gst-etat', 'hst_etat'],
    'cnesst_cotisation': ['cnesst'],
    't2_assessment': ['t2_assessment', 't2-assessment'],
    'co17_assessment': ['co17_assessment', 'co-17'],
    'bank_statement_pdf': ['bank-statement', 'bank_statement'],
    'cc_statement_pdf': ['cc-statement', 'cc_statement', 'visa', 'mastercard', 'amex'],
    'xlsx_reconciliation': ['reconciliation'],
    'supplier_invoice_pdf': ['invoice', 'facture'],
}


def compute_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def infer_entity(file_path: Path, root: Path) -> str:
    try:
        rel = file_path.relative_to(root)
    except ValueError:
        return 'global'
    parts = rel.parts
    if len(parts) >= 2 and parts[0] == 'entities':
        return parts[1]
    return 'global'


def infer_domain(file_path: Path) -> str:
    p = str(file_path).lower()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(kw in p for kw in keywords):
            return domain
    return 'other'


def infer_document_type(file_path: Path) -> str:
    p = str(file_path).lower()
    for label, keywords in DOCUMENT_TYPE_KEYWORDS.items():
        if any(kw in p for kw in keywords):
            return label
    return ''


def infer_date_on_document(file_path: Path) -> str:
    """Pick an ISO date out of the filename when one is present (YYYY-MM-DD or YYYY-MM)."""
    name = file_path.name
    m = re.search(r'(\d{4}-\d{2}-\d{2})', name)
    if m:
        return m.group(1)
    m = re.search(r'(\d{4})[._-](\d{2})\b', name)
    if m:
        return f'{m.group(1)}-{m.group(2)}-01'
    return ''


def next_source_id(used_ids: set, domain: str) -> str:
    """Generate a stable source_id like SRC-BANK-007 by counting existing ids in that domain."""
    domain_label = (domain or 'other').upper()
    n = 1
    while True:
        candidate = f'SRC-{domain_label}-{n:03d}'
        if candidate not in used_ids:
            used_ids.add(candidate)
            return candidate
        n += 1


def scan_directory(root: Path) -> dict:
    registry = {}
    for path in sorted(root.rglob('*')):
        if not (path.is_file() and path.suffix.lower() in EXTENSIONS):
            continue
        s = str(path)
        if 'output/' in s or '__pycache__' in s or '/templates/' in s or '/legacy/' in s:
            continue
        try:
            stat = path.stat()
            sha = compute_sha256(path)
        except (OSError, PermissionError) as e:
            print(f'WARN: cannot read {path}: {e}', file=sys.stderr)
            continue
        rel = str(path.relative_to(root))
        registry[rel] = {
            'sha256': sha,
            'size_bytes': stat.st_size,
            'last_verified': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'entity': infer_entity(path, root),
            'domain': infer_domain(path),
            'document_type': infer_document_type(path),
            'obtained_from': '',
            'date_on_document': infer_date_on_document(path),
            'notes': '',
        }
    return registry


def merge_registry(existing: dict, new: dict) -> tuple[dict, list]:
    merged = {}
    alerts = []
    used_ids = {meta.get('source_id') for meta in existing.values() if meta.get('source_id')}

    for path, meta in new.items():
        if path in existing:
            old = existing[path]
            meta['first_seen'] = old.get('first_seen', meta['last_verified'])
            meta['source_id'] = old.get('source_id') or next_source_id(used_ids, meta.get('domain', ''))
            # Preserve any user-curated metadata that the scanner cannot infer
            for k in ('obtained_from', 'notes'):
                if old.get(k):
                    meta[k] = old[k]
            if not meta.get('document_type') and old.get('document_type'):
                meta['document_type'] = old['document_type']
            if not meta.get('date_on_document') and old.get('date_on_document'):
                meta['date_on_document'] = old['date_on_document']
            if old.get('sha256') and old['sha256'] != meta['sha256']:
                alerts.append({
                    'source_id': meta['source_id'],
                    'path': path,
                    'old_sha': old.get('sha256'),
                    'new_sha': meta['sha256'],
                    'first_seen': old.get('first_seen'),
                    'message': 'HASH CHANGED — source content modified since first scan. '
                               'Decisions citing this file should be re-verified.',
                })
        else:
            meta['first_seen'] = meta['last_verified']
            meta['source_id'] = next_source_id(used_ids, meta.get('domain', ''))
        merged[path] = meta

    for path, old in existing.items():
        if path not in new:
            alerts.append({
                'source_id': old.get('source_id', ''),
                'path': path,
                'message': 'FILE REMOVED — source no longer present. '
                           'Decisions citing this file are now unverifiable.',
            })

    return merged, alerts


def main() -> int:
    parser = argparse.ArgumentParser(description='Build/update source registry (v1.2).')
    parser.add_argument('working_dir', help='Root directory to scan')
    parser.add_argument('--output', default='source_registry.json',
                        help='Output JSON file (default: source_registry.json at the cwd)')
    args = parser.parse_args()

    root = Path(args.working_dir).resolve()
    if not root.is_dir():
        print(f'ERROR: {root} is not a directory', file=sys.stderr)
        return 1

    output_path = Path(args.output)
    existing = {}
    if output_path.exists():
        try:
            with open(output_path) as f:
                existing = json.load(f)
        except json.JSONDecodeError:
            print(f'WARN: existing {output_path} is invalid JSON, starting fresh',
                  file=sys.stderr)

    print(f'Scanning {root}...')
    new = scan_directory(root)
    print(f'Found {len(new)} source files.')

    merged, alerts = merge_registry(existing, new)

    with open(output_path, 'w') as f:
        json.dump(merged, f, indent=2, sort_keys=True)
    print(f'Registry written to {output_path}')

    if alerts:
        print(f'\n{len(alerts)} alerts:')
        for a in alerts:
            sid = a.get('source_id') or ''
            print(f'  - [{sid}] {a["path"]}: {a["message"]}')
        return 2

    return 0


if __name__ == '__main__':
    sys.exit(main())
