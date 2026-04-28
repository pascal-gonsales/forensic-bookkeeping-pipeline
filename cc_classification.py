#!/usr/bin/env python3
"""
Personal Credit Card Classification — Business vs Personal vs Needs Review.

Classifies the debtor's personal CC transactions into:
- BUSINESS: restaurant supplier expenses (reimbursable, status: CONFIRMED)
- PERSONAL: not business-related (not reimbursable, status: CONFIRMED)
- TEAM_BUILDING: partner trips/events (status: NEEDS_REVIEW — split requires source confirmation)
- VERIFY (legacy): ambiguous, manual triage required (status: NEEDS_REVIEW)
- CARD_FEE: credit card fees/insurance (excluded from both sides, status: CONFIRMED)

Each output dict now includes a `status` field aligned to skill v1.1:
CONFIRMED | INFERRED | NEEDS_REVIEW | BLOCKED.

Rules (v1.1):
- Known restaurant suppliers = BUSINESS (named restaurant suppliers, etc.)
- SAQ >= $300 = BUSINESS (CONFIRMED — debtor decision logged 2026-04-02)
- SAQ < $300 = PERSONAL (CONFIRMED — debtor decision logged 2026-04-02)
- Travel with partners = TEAM_BUILDING + status NEEDS_REVIEW (no auto-split per v1.1
  anti-drift rule; user must supply business_amount with source citation)
- Fitness, personal shopping = PERSONAL
- Card fees/insurance = CARD_FEE
- Default fallback = NEEDS_REVIEW (never auto-classified BUSINESS without rule match)
"""

import csv
import json
import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def _load_extra_rules(env_var: str) -> list:
    """Load debtor-specific classification rules from a JSON env var.

    Format: '[["regex", "category", "label"], ...]'
    OSS distribution leaves env vars unset; real rules live in private JSON
    pointed at by env vars in ~/.config/wwithai/credentials.env (or shell).
    """
    raw = os.environ.get(env_var, '').strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return [(p, c, l) for p, c, l in parsed]
    except (json.JSONDecodeError, ValueError, TypeError):
        return []

# ---------------------------------------------------------------------------
# Classification rules
# ---------------------------------------------------------------------------

# BUSINESS: restaurant supplier expenses. Generic Canadian/global brand
# patterns kept as portable examples; debtor-specific small-supplier rules
# load at runtime from CC_BUSINESS_RULES_JSON env var.
BUSINESS_PATTERNS = [
    # Generic well-known Canadian brands (portable across debtors)
    (r'CINTAS', 'supplier_cleaning', 'Cintas'),
    (r'ECOLAB', 'supplier_cleaning', 'Ecolab'),
    (r'COSTCO\s*DELIVERY|COSTCO\s*ENTREPRISE|COSTCOENTREPRISE', 'supplier_food', 'Costco (Business)'),
    (r'CANADIAN TIRE', 'supplier_misc', 'Canadian Tire'),
    (r'RONA|HOME DEPOT|BMR', 'construction', 'Hardware Store'),
    (r'VIDEOTRON', 'telecom', 'Vidéotron'),
    (r'ROGERS', 'telecom', 'Rogers'),
    (r'ENERGIR', 'utility', 'Énergir'),
    (r'HYDRO.QUEBEC', 'utility', 'Hydro-Québec'),
    # Restaurant SaaS — generic, not debtor-specific
    (r'LIGHTSPEED', 'software_pos', 'Lightspeed (POS)'),
    (r'OPENTABLE', 'software_reservation', 'OpenTable'),
    (r'AGENDRIX', 'software_hr', 'Agendrix'),
    (r'INDEED', 'software_hr', 'Indeed (Recrutement)'),
    (r'UEAT|UBER.*EAT', 'delivery_platform', 'UberEats'),
    # Generic SaaS
    (r'GOOGLE.*SUITE|GOOGLE.*WORKSPACE|GSUITE', 'software', 'Google Workspace'),
    (r'QUICKBOOKS', 'software', 'QuickBooks'),
    (r'DROPBOX', 'software', 'Dropbox'),
    (r'ZOOM', 'software', 'Zoom'),
    (r'ADOBE', 'software', 'Adobe'),
    (r'FACEBOOK|FACEBK', 'marketing', 'Facebook Ads'),
    # Fuel/transport (mixed-use; routed to VERIFY in many cases)
    (r'AGENCE DE MOBILIT|AGENCEDEMOBILIT', 'transport', 'Parking/Mobilité'),
    # Storage
    (r'UHC OF QUEBEC|UHAUL', 'storage', 'UHaul/Storage'),
    # Pest control, fire safety
    (r'EXTERMINATEUR|PEST', 'supplier_service', 'Pest Control'),
] + _load_extra_rules('CC_BUSINESS_RULES_JSON')

# PERSONAL: not business. Generic patterns; debtor-specific personal merchants
# (medical providers, named studios, named travel agencies) load via env var.
PERSONAL_PATTERNS = [
    (r'FITNESS|GYM', 'fitness', 'Fitness'),
    (r'NETFLIX|SPOTIFY|DISNEY|CRAVE', 'entertainment', 'Streaming'),
    (r'PHARMAPRIX|JEAN COUTU', 'pharmacy', 'Pharmacie'),
    (r'NESPRESSO', 'personal_shopping', 'Nespresso'),
    (r'ANNUAL\s*FEE', 'card_fee', 'Annual Fee'),
    (r'DOLLARAMA', 'personal_shopping', 'Dollarama (Perso)'),
] + _load_extra_rules('CC_PERSONAL_RULES_JSON')

# FLAG: transactions that need specific attention (red-flag or verify with accountant)
FLAG_PATTERNS = [] + _load_extra_rules('CC_FLAG_RULES_JSON')

# CARD_FEE: excluded from both business and personal totals (generic card-fee patterns)
CARD_FEE_PATTERNS = [
    (r'ASSURANCE PAIEMENT', 'card_fee', 'Card Insurance'),
    (r'FRAIS DE DEPASSEMENT', 'card_fee', 'Overlimit Fee'),
    (r'INTERETS SUR ACHATS', 'card_fee', 'Interest Charges'),
    (r'FRAIS DE CR[ÉE]DIT', 'card_fee', 'Credit Fee'),
    (r'FRAIS SOLUTIONS LIBRE', 'card_fee', 'Card Service Fee'),
    (r'MENSUALIT[ÉE]\s*FINANCEMENT', 'card_fee', 'Card Financing Fee'),
    (r'FRAIS\s*INTERET|FRAIS\s*INTÉRÊT', 'card_fee', 'Interest Charges'),
    (r'PAIEMENT\s*-?\s*MERCI|PAIEMENT\s*RECU\s*MERCI', 'card_fee', 'CC Payment Received (not expense)'),
]

# TEAM_BUILDING: partner trips — split percentage requires source confirmation
# per skill v1.1 anti-drift rule (no auto-split).
TEAM_BUILDING_PATTERNS = [
    (r'VRBO|AIRBNB', 'team_building', 'Partner Trip Accommodation'),
    (r'BOOKING\.COM', 'team_building', 'Partner Trip Booking'),
] + _load_extra_rules('CC_TEAM_BUILDING_RULES_JSON')

COMPILED_BUSINESS = [(re.compile(p, re.IGNORECASE), cat, label) for p, cat, label in BUSINESS_PATTERNS]
COMPILED_PERSONAL = [(re.compile(p, re.IGNORECASE), cat, label) for p, cat, label in PERSONAL_PATTERNS]
COMPILED_CARD_FEE = [(re.compile(p, re.IGNORECASE), cat, label) for p, cat, label in CARD_FEE_PATTERNS]
COMPILED_TEAM = [(re.compile(p, re.IGNORECASE), cat, label) for p, cat, label in TEAM_BUILDING_PATTERNS]
COMPILED_FLAG = [(re.compile(p, re.IGNORECASE), cls, label) for p, cls, label in FLAG_PATTERNS]

# VERIFY: mixed-use merchants requiring manual review. Generic patterns;
# debtor-specific names load via env var.
VERIFY_PATTERNS = [
    (r'APPLE\.COM|APPLE\.COM/BILL', 'VERIFY', 'Apple — mixed business/personal'),
    (r'UBER\s*CANADA.*TRIP|UBERCANADA.*TRIP', 'VERIFY', 'Uber Trips — mixed, manual review'),
    (r'UBER.*EATS|UBEREATS', 'VERIFY', 'UberEats — mixed, manual review'),
    (r'WALMART', 'VERIFY', 'Walmart — could be restaurant or personal'),
    (r'ESSO|PETRO|SHELL|ULTRAMAR|COUCHE-TARD', 'VERIFY', 'Gas/Transport — mixed, apply business %'),
    (r'INTERET\s*DE\s*DETAIL|INTERETDEDETAIL', 'card_fee', 'Intérêt de détail'),
] + _load_extra_rules('CC_VERIFY_RULES_JSON')
COMPILED_VERIFY = [(re.compile(p, re.IGNORECASE), cls, label) for p, cls, label in VERIFY_PATTERNS]


def classify_transaction(description: str, amount: float) -> dict:
    """Classify a personal CC transaction.

    Returns a dict with 5 fields:
      - class: BUSINESS | PERSONAL | TEAM_BUILDING | CARD_FEE | VERIFY | FLAG
      - category: subtype label
      - label: human-readable description
      - business_amount: portion deductible to the business (or None if NEEDS_REVIEW)
      - status: CONFIRMED | INFERRED | NEEDS_REVIEW | BLOCKED (skill v1.1 schema)

    Anti-drift rules (v1.1):
      - Never auto-compute split percentages without user confirmation
      - Default fallback = NEEDS_REVIEW, never silent BUSINESS
    """

    # Check RED FLAGS first
    for regex, cls, label in COMPILED_FLAG:
        if regex.search(description):
            return {'class': cls, 'category': 'flag', 'label': label,
                    'business_amount': None, 'status': 'NEEDS_REVIEW',
                    'note': 'RED FLAG — vérifier légitimité'}

    # Check card fees
    for regex, cat, label in COMPILED_CARD_FEE:
        if regex.search(description):
            return {'class': 'CARD_FEE', 'category': cat, 'label': label,
                    'business_amount': 0, 'status': 'CONFIRMED'}

    # Check specific VERIFY patterns (before business, to catch Apple/Uber/Walmart/gas)
    for regex, cls, label in COMPILED_VERIFY:
        if regex.search(description):
            if cls == 'card_fee':
                return {'class': 'CARD_FEE', 'category': 'card_fee', 'label': label,
                        'business_amount': 0, 'status': 'CONFIRMED'}
            return {'class': 'VERIFY', 'category': 'verify_specific', 'label': label,
                    'business_amount': None, 'status': 'NEEDS_REVIEW', 'note': label}

    # Check team building — v1.1: NO auto-split, user must supply business_amount
    for regex, cat, label in COMPILED_TEAM:
        if regex.search(description):
            return {'class': 'TEAM_BUILDING', 'category': cat, 'label': label,
                    'business_amount': None, 'status': 'NEEDS_REVIEW',
                    'note': 'Split percentage requires user confirmation with source. '
                            'Auto-50% disabled in v1.1 (anti-drift rule).'}

    # Check personal
    for regex, cat, label in COMPILED_PERSONAL:
        if regex.search(description):
            return {'class': 'PERSONAL', 'category': cat, 'label': label,
                    'business_amount': 0, 'status': 'CONFIRMED'}

    # SAQ rule: >=$300 = BUSINESS, <$300 = PERSONAL (CONFIRMED by debtor 2026-04-02)
    if re.search(r'SAQ', description, re.IGNORECASE):
        if amount >= 300:
            return {'class': 'BUSINESS', 'category': 'supplier_alcohol',
                    'label': 'SAQ (>=$300)',
                    'business_amount': amount, 'status': 'CONFIRMED',
                    'note': 'Debtor decision logged 2026-04-02: SAQ >=$300 = BUSINESS'}
        else:
            return {'class': 'PERSONAL', 'category': 'personal_alcohol',
                    'label': 'SAQ (<$300)',
                    'business_amount': 0, 'status': 'CONFIRMED',
                    'note': 'Debtor decision logged 2026-04-02: SAQ <$300 = PERSONAL'}

    # Check business (only matched merchants; never silent BUSINESS by default)
    for regex, cat, label in COMPILED_BUSINESS:
        if regex.search(description):
            return {'class': 'BUSINESS', 'category': cat, 'label': label,
                    'business_amount': amount, 'status': 'CONFIRMED'}

    # Default: NEEDS_REVIEW (never silent BUSINESS — v1.1 anti-drift rule)
    return {'class': 'VERIFY', 'category': 'unknown', 'label': 'NEEDS_REVIEW — no rule match',
            'business_amount': None, 'status': 'NEEDS_REVIEW'}


def process_all_cards(source_path: str) -> list:
    """Process all personal CC transactions and classify them."""
    with open(source_path, 'r', encoding='utf-8-sig') as f:
        source_rows = list(csv.DictReader(f))

    results = []
    for r in source_rows:
        desc = r.get('description', '')
        montant = r.get('montant', '0').replace(',', '.')
        try:
            amt = abs(float(montant))
        except:
            amt = 0

        classification = classify_transaction(desc, amt)

        results.append({
            'date': r.get('date', ''),
            'card': r.get('carte', ''),
            'description': desc,
            'amount': amt,
            'class': classification['class'],
            'category': classification['category'],
            'label': classification['label'],
            'business_amount': classification['business_amount'],
            'status': classification.get('status', 'NEEDS_REVIEW'),
            'note': classification.get('note', ''),
            'month': r.get('mois', r.get('date', '')[:7]),
        })

    return results


def generate_report(results: list, output_dir: str = 'output'):
    """Generate classification report."""
    out = Path(output_dir)

    # Write classified CSV
    csv_path = out / 'cc_personal_classified.csv'
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'date', 'card', 'description', 'amount', 'class', 'category',
            'label', 'business_amount', 'status', 'note', 'month',
        ])
        writer.writeheader()
        writer.writerows(results)
    print(f'Classified CSV: {csv_path}')

    # Summary — None business_amount counts as "pending user input", not 0
    by_class = defaultdict(lambda: {'count': 0, 'total': 0, 'business': 0, 'pending': 0})
    for r in results:
        by_class[r['class']]['count'] += 1
        by_class[r['class']]['total'] += r['amount']
        if r['business_amount'] is None:
            by_class[r['class']]['pending'] += r['amount']
        else:
            by_class[r['class']]['business'] += r['business_amount']

    print(f'\nCLASSIFICATION SUMMARY:')
    grand_total = sum(d['total'] for d in by_class.values())
    for cls in ['BUSINESS', 'TEAM_BUILDING', 'PERSONAL', 'CARD_FEE', 'VERIFY']:
        d = by_class[cls]
        pct = d['total'] / grand_total * 100 if grand_total > 0 else 0
        line = (f'  {cls:15} {d["count"]:>5} txns  ${d["total"]:>12,.2f} ({pct:>5.1f}%)'
                f'  business: ${d["business"]:>10,.2f}')
        if d['pending'] > 0:
            line += f'  pending_user_input: ${d["pending"]:>10,.2f}'
        print(line)

    business_total = sum(d['business'] for d in by_class.values())
    pending_total = sum(d['pending'] for d in by_class.values())
    print(f'  {"TOTAL BUSINESS (CONFIRMED)":<27} ${business_total:>12,.2f}')
    if pending_total > 0:
        print(f'  {"TOTAL PENDING USER INPUT":<27} ${pending_total:>12,.2f}  '
              f'(NEEDS_REVIEW — not counted in business until user confirms)')

    # By card
    print(f'\nBY CARD:')
    by_card = defaultdict(lambda: defaultdict(lambda: {'count': 0, 'total': 0, 'business': 0}))
    for r in results:
        by_card[r['card']][r['class']]['count'] += 1
        by_card[r['card']][r['class']]['total'] += r['amount']
        if r['business_amount'] is not None:
            by_card[r['card']][r['class']]['business'] += r['business_amount']

    for card in sorted(by_card.keys()):
        card_total = sum(d['total'] for d in by_card[card].values())
        card_biz = sum(d['business'] for d in by_card[card].values())
        pct = card_biz/card_total*100 if card_total > 0 else 0
        print(f'  {card}: ${card_total:,.0f} total, ${card_biz:,.0f} business ({pct:.0f}%)')
        for cls in ['BUSINESS', 'TEAM_BUILDING', 'PERSONAL', 'CARD_FEE', 'VERIFY']:
            d = by_card[card][cls]
            if d['count'] > 0:
                print(f'    {cls:15} {d["count"]:>4}x ${d["total"]:>10,.0f}')

    # VERIFY list
    verify = [r for r in results if r['class'] == 'VERIFY']
    if verify:
        print(f'\nÀ VÉRIFIER ({len(verify)} transactions):')
        for r in sorted(verify, key=lambda x: -x['amount']):
            print(f'  {r["date"]:>12} ${r["amount"]:>9,.2f} {r["card"]:25} {r["description"][:50]}')

    return by_class


if __name__ == '__main__':
    source_path = './data/cc_master/master_transactions.csv'
    results = process_all_cards(source_path)
    generate_report(results)
