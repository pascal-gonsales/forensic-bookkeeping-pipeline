#!/usr/bin/env python3
"""
Source Registry — SHA256 anchor for forensic source documents.

Scans a working directory for source documents (PDFs, CSVs, XLSX) and writes
a JSON registry with SHA256 hashes. Decisions in decisions.jsonl cite source
files by name; this registry lets a reviewer verify the file content has not
changed since the decision was made.

Usage:
    python scripts/source_registry.py <working_dir> [--output source_registry.json]

Output schema (JSON):
    {
      "<file_path>": {
        "sha256": "<hash>",
        "size_bytes": <int>,
        "first_seen": "<ISO date>",
        "last_verified": "<ISO date>",
        "entity": "<slug or 'global'>",
        "domain": "bank|cc|payroll|tax|creditor|other"
      }
    }

Re-running updates last_verified (preserves first_seen). If a file's hash
changes between runs, an alert is printed and the new hash is recorded
(append-only via decisions.jsonl when integrated with the skill workflow).

Aligned with skill v1.1 confidence-and-sourcing.md reference.
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

EXTENSIONS = {'.pdf', '.csv', '.xlsx', '.xlsm', '.tsv'}

# Heuristic to infer entity slug + domain from path components
DOMAIN_KEYWORDS = {
    'bank': ['bank-statement', 'bank_statement', 'releve', 'desjardins', 'rbc', 'amex'],
    'cc': ['credit-card', 'cc_perso', 'cc-perso', 'mastercard', 'visa', 'cc_'],
    'payroll': ['payroll', 'paie', 'nethris', 'cgi', 'agendrix', 'employee', 'tips'],
    'tax': ['tax-account', 'tax_account', 'rp-federal', 'rs-quebec', 'tvq', 'co-17',
            't2', 'cnesst', 'rl-1'],
    'creditor': ['creditor', 'supplier-invoice', 'damen', 'ferro'],
}


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of a file. Reads in chunks to avoid loading large files."""
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def infer_entity(file_path: Path, root: Path) -> str:
    """Extract entity slug from path if file lives under entities/<slug>/."""
    try:
        rel = file_path.relative_to(root)
    except ValueError:
        return 'global'
    parts = rel.parts
    if len(parts) >= 2 and parts[0] == 'entities':
        return parts[1]
    return 'global'


def infer_domain(file_path: Path) -> str:
    """Heuristically classify a source file's domain from its path."""
    p = str(file_path).lower()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(kw in p for kw in keywords):
            return domain
    return 'other'


def scan_directory(root: Path) -> dict:
    """Walk root and collect SHA256 + metadata for every source file."""
    registry = {}
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.suffix.lower() in EXTENSIONS:
            # Skip generated outputs
            if 'output/' in str(path) or '__pycache__' in str(path):
                continue
            try:
                stat = path.stat()
                sha = compute_sha256(path)
            except (OSError, PermissionError) as e:
                print(f'WARN: cannot read {path}: {e}', file=sys.stderr)
                continue
            registry[str(path.relative_to(root))] = {
                'sha256': sha,
                'size_bytes': stat.st_size,
                'last_verified': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                'entity': infer_entity(path, root),
                'domain': infer_domain(path),
            }
    return registry


def merge_registry(existing: dict, new: dict) -> tuple[dict, list]:
    """Merge new scan into existing registry. Preserve first_seen. Detect hash changes."""
    merged = {}
    alerts = []
    for path, meta in new.items():
        if path in existing:
            old = existing[path]
            meta['first_seen'] = old.get('first_seen', meta['last_verified'])
            if old.get('sha256') != meta['sha256']:
                alerts.append({
                    'path': path,
                    'old_sha': old.get('sha256'),
                    'new_sha': meta['sha256'],
                    'first_seen': old.get('first_seen'),
                    'message': 'HASH CHANGED — source content modified since first scan. '
                               'Decisions citing this file should be re-verified.',
                })
        else:
            meta['first_seen'] = meta['last_verified']
        merged[path] = meta

    for path in existing:
        if path not in new:
            alerts.append({
                'path': path,
                'message': 'FILE REMOVED — source no longer present. '
                           'Decisions citing this file are now unverifiable.',
            })

    return merged, alerts


def main():
    parser = argparse.ArgumentParser(description='Build/update source registry.')
    parser.add_argument('working_dir', help='Root directory to scan')
    parser.add_argument('--output', default='source_registry.json',
                        help='Output JSON file (default: source_registry.json)')
    args = parser.parse_args()

    root = Path(args.working_dir).resolve()
    if not root.is_dir():
        print(f'ERROR: {root} is not a directory', file=sys.stderr)
        sys.exit(1)

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
            print(f'  - {a["path"]}: {a["message"]}')
        sys.exit(2)  # exit code 2 = alerts (not failure, but caller should review)

    sys.exit(0)


if __name__ == '__main__':
    main()
