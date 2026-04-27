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
- Known restaurant suppliers = BUSINESS (Damen, Ferro, Newon, Costco, etc.)
- SAQ >= $300 = BUSINESS (CONFIRMED — debtor decision logged 2026-04-02)
- SAQ < $300 = PERSONAL (CONFIRMED — debtor decision logged 2026-04-02)
- Travel with partners = TEAM_BUILDING + status NEEDS_REVIEW (no auto-split per v1.1
  anti-drift rule; user must supply business_amount with source citation)
- Fitness, personal shopping = PERSONAL
- Card fees/insurance = CARD_FEE
- Default fallback = NEEDS_REVIEW (never auto-classified BUSINESS without rule match)
"""

import csv
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Classification rules
# ---------------------------------------------------------------------------

# BUSINESS: definitely restaurant supplier expenses
BUSINESS_PATTERNS = [
    # Food suppliers (handle "DAMEN SERVICE", "DAMENSERVICEALIMENTAIRE", "DAMEN ALIMENTAIRE")
    (r'DAMEN\s*SERVICE|DAMENSERVICE|DAMEN\s*ALIMENTAIRE', 'supplier_food', 'Damen Alimentaire'),
    (r'FERRO\s*POISSON|FERROPOISSON', 'supplier_food', 'Ferro Poisson & Fruits'),
    (r'FRANDON', 'supplier_food', 'Frandon'),
    (r'NEWON|MARCH[ÉE]\s*NEWON', 'supplier_food', 'Marché Newon'),
    (r'HOUR\s*HONG|EPICERIE\s*HOUR|EPICERIEHOURHONG', 'supplier_food', 'Hour Hong Épicerie'),
    (r'ALIMENTS\s*JORK', 'supplier_food', 'Aliments Jork'),
    (r'THAI\s*FOOD\s*MART', 'supplier_food', 'Thai Food Mart'),
    (r'COSTCO\s*DELIVERY|COSTCO\s*ENTREPRISE|COSTCOENTREPRISE', 'supplier_food', 'Costco (Business)'),
    (r'DISTRIBUTION\s*MA', 'supplier_food', 'Distribution MA'),
    (r'CAN-AM|CANAM', 'supplier_food', 'Can-Am (Supplier)'),
    (r'TZANET', 'supplier_food', 'Tzanet Enterprises'),
    (r'DELIVERECT', 'supplier_food', 'Deliverect'),
    (r'LA POMME ROUGE', 'supplier_food', 'La Pomme Rouge'),
    (r'KIM PHAT', 'supplier_food', 'Kim Phat (Épicerie asiatique)'),
    (r'PRIMAVIN', 'supplier_beverage', 'Primavin (Vin)'),
    (r'BEVINCO', 'supplier_service', 'Bevinco (Inventaire bar)'),
    (r'LES MARCHANDS DIST', 'supplier_food', 'Les Marchands Distributeurs'),
    (r'HOBART FOOD', 'supplier_equipment', 'Hobart (Équipement cuisine)'),
    (r'NEOPOS', 'software_pos', 'Neopos (POS)'),
    (r'CHOCO161', 'supplier_food', 'Choco (Food ordering)'),

    # Beverage/alcohol (SAQ >$300 only — handled in classify function)
    (r'MOLSON|LABATT|BRASSEUR', 'supplier_beverage', 'Brasseur'),

    # Cleaning/linen
    (r'CINTAS', 'supplier_cleaning', 'Cintas'),
    (r'ECOLAB', 'supplier_cleaning', 'Ecolab'),
    (r'LOC.*LINGE.*OLYMPI|LINGES\s*OLYMPI|LOCATION\s*OLYMPI|OLYMPICMONTREAL|PANNETON.*OLY', 'supplier_cleaning', 'Location Olympique'),
    (r'BUANDERIE|NETTOYEUR', 'supplier_cleaning', 'Buanderie/Nettoyeur'),

    # Fish/seafood
    (r'PECHERIES\s*NORREF|LESPECHERIESNORREF|NORREFF', 'supplier_food', 'Pêcheries Norref'),

    # Equipment/maintenance
    (r'HOTTE\s*BLANCHE|HOTTEBLANCHE', 'supplier_equipment', 'Hotte Blanche'),
    (r'INTEGRAL\s*XT', 'supplier_service', 'Integral XT (Exterminateur)'),
    (r'SECURPLUS', 'supplier_service', 'Securplus'),
    (r'CHEZ\s*POTIER|SPCHEZPOTIER', 'supplier_equipment', 'Chez Potier'),
    (r'PROJET\s*HUITRES|PROJETHUITRES', 'supplier_food', 'Projet Huîtres'),

    # Telecom/tech for restaurants
    (r'VIDEOTRON', 'telecom', 'Vidéotron'),
    (r'ROGERS', 'telecom', 'Rogers'),
    (r'EMAK\s*TELECOM|EMAKTELECOM', 'telecom', 'EMAK Telecom'),
    (r'LIGHTSPEED', 'software_pos', 'Lightspeed (POS)'),
    (r'OPENTABLE', 'software_reservation', 'OpenTable'),
    (r'AGENDRIX', 'software_hr', 'Agendrix'),
    (r'PERSONAFI', 'software_payroll', 'Personafi'),
    (r'NUAGE\s*SIGHT|NUAGESIGHT', 'supplier_service', 'Nuage Sight (Alarme)'),
    (r'SKOOL\.COM|SKOOL', 'software', 'Skool (Logiciel)'),
    (r'JASPER\.AI|JASPERAI', 'software', 'Jasper AI (Logiciel)'),

    # Utilities
    (r'ENERGIR', 'utility', 'Énergir'),
    (r'HYDRO.QUEBEC', 'utility', 'Hydro-Québec'),

    # Software subscriptions (business)
    (r'GOOGLE.*SUITE|GOOGLE.*WORKSPACE|GSUITE|GSUITE_SIAMH', 'software', 'Google Workspace'),
    (r'QUICKBOOKS', 'software', 'QuickBooks'),
    (r'DROPBOX', 'software', 'Dropbox'),
    (r'ZOOM', 'software', 'Zoom'),
    (r'LOOM', 'software', 'Loom'),
    (r'ADOBE', 'software', 'Adobe'),
    (r'INDEED', 'software_hr', 'Indeed (Recrutement)'),
    (r'FACEBOOK|FACEBK', 'marketing', 'Facebook Ads'),
    (r'GOOGLE ONE', 'software', 'Google One'),
    (r'SHEMIE\.CA|WWW\.SHEMIE', 'accounting', 'Shemie.ca (Comptable)'),
    (r'SERVICELABINC|SERVICELAB\s*INC|SERVICE\s*LAB', 'software', 'Service Lab Inc'),
    (r'COPIE\s*2000', 'office', 'Copie 2000 (Impression)'),
    (r'EQUIFAX', 'software', 'Equifax (Vérification crédit)'),
    (r'RESTOMONTREAL|RESTO\s*MONTREAL', 'delivery_platform', 'Resto-Montréal'),
    (r'JOLT\.COM|JOLT', 'software', 'Jolt (Gestion resto)'),
    (r'PLAYLIST GENERATI|4TE\*THE', 'software', 'Playlist Generator (Musique resto)'),
    (r'TOURISMEMTL|TOURISME MTL', 'marketing', 'Tourisme Montréal'),

    # Restaurant supplies
    (r'CANADIAN TIRE', 'supplier_misc', 'Canadian Tire'),
    (r'RICK CANNON', 'supplier_misc', 'Rick Cannon'),
    (r'LIBRO', 'supplier_misc', 'Libro'),

    # Delivery/POS
    (r'RESTO-MTL|RESTO MTL', 'delivery_platform', 'Resto-MTL'),
    (r'UEAT|UBER.*EAT', 'delivery_platform', 'UberEats'),

    # Construction/repairs
    (r'RONA|HOME DEPOT|BMR', 'construction', 'Hardware Store'),

    # Parking — business (between restaurants)
    (r'AGENCE DE MOBILIT|AGENCEDEMOBILIT', 'transport', 'Parking/Mobilité'),

    # Suppliers identified by Owner_A
    (r'MARCH[ÉE]\s*DU\s*VILLAGE|MARCHEDUVILLAGE', 'supplier_food', 'Marché du Village (no tax)'),
    (r'GROUPE?\s*HL33|GROUPEHL33', 'supplier_equipment', 'Groupe HL33 (Équipement resto)'),
    (r'SERVICE\s*GIBEAULT|SERVICEGIBEAULT', 'supplier_service', 'Service Gibeault (Maintenance)'),
    (r'WAVE.*CONSTRUCTION', 'construction', 'Wave Construction (Terrasse resto)'),
    (r'LA BAIE.*HUDSON|BAIE D.HUDSON', 'supplier_misc', 'La Baie Hudson (Assiettes resto)'),

    # Storage
    (r'UHC OF QUEBEC|UHAUL', 'storage', 'UHaul/Storage'),

    # Libro — service de réservation resto
    (r'LIBRO', 'software_reservation', 'Libro (Service réservation)'),

    # Pest control, fire safety, etc.
    (r'EXTERMINATEUR|PEST', 'supplier_service', 'Pest Control'),
]

# PERSONAL: definitely not business
PERSONAL_PATTERNS = [
    (r'FRANCISCOTORRESFITNESS|FITNESS|GYM', 'fitness', 'Fitness'),
    (r'NETFLIX|SPOTIFY|DISNEY|CRAVE', 'entertainment', 'Streaming'),
    (r'PHARMAPRIX|JEAN COUTU', 'pharmacy', 'Pharmacie'),
    (r'NESPRESSO', 'personal_shopping', 'Nespresso'),
    (r'BUMRUNGRAD\s*HOSPITAL', 'personal_medical', 'Hospital Bangkok (Personal)'),
    (r'ANNUAL\s*FEE', 'card_fee', 'Annual Fee'),
    (r'DOLLARAMA', 'personal_shopping', 'Dollarama (Perso)'),
    (r'JANSON\s*THIBAULT', 'personal_legal', 'Janson Thibault Ryan (Perso)'),
    (r'GRAB\.COM|WWW\.GRAB', 'personal_travel', 'Grab Bangkok (Perso vacances)'),
    (r'LASH\s*LAB|SQ\*LASHLAB', 'personal', 'Lash Lab (Perso)'),
    (r'ON\s*SPORTSWEAR|ONSPORTSWEAR', 'personal', 'On Sportswear (Perso)'),
    (r'STEPH\s*GUIDA|STEPHGUIDA', 'personal', 'Steph Guida Studio (Perso)'),
    (r'KAISENBUTSU', 'personal_travel', 'Restaurant Tokyo (Perso)'),
]

# FLAG: transactions that need specific attention (red flag or verify with comptable)
FLAG_PATTERNS = [
    (r'TRENDYS\s*ST.OUEN|TRENDYSSTOUEN', 'FLAG_RED', 'Trendys St-Ouen — VÉRIFIER LÉGITIMITÉ'),
]

# CARD_FEE: excluded from both business and personal totals
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

# TEAM_BUILDING: partner trips — 50% company (confirm with comptable)
TEAM_BUILDING_PATTERNS = [
    (r'VRBO|AIRBNB', 'team_building', 'Partner Trip Accommodation'),
    (r'ZIPAIR|FLIGHTSONBOOKING|BOOKING\.COM', 'team_building', 'Partner Trip Flight/Booking'),
    (r'SINDHORN.*HOTEL', 'team_building', 'Partner Trip Hotel'),
]

COMPILED_BUSINESS = [(re.compile(p, re.IGNORECASE), cat, label) for p, cat, label in BUSINESS_PATTERNS]
COMPILED_PERSONAL = [(re.compile(p, re.IGNORECASE), cat, label) for p, cat, label in PERSONAL_PATTERNS]
COMPILED_CARD_FEE = [(re.compile(p, re.IGNORECASE), cat, label) for p, cat, label in CARD_FEE_PATTERNS]
COMPILED_TEAM = [(re.compile(p, re.IGNORECASE), cat, label) for p, cat, label in TEAM_BUILDING_PATTERNS]
COMPILED_FLAG = [(re.compile(p, re.IGNORECASE), cls, label) for p, cls, label in FLAG_PATTERNS]

# VERIFY with specific notes
VERIFY_PATTERNS = [
    (r'APPLE\.COM|APPLE\.COM/BILL', 'VERIFY', 'Apple — certains business, certains perso'),
    (r'UBER\s*CANADA.*TRIP|UBERCANADA.*TRIP', 'VERIFY', 'Uber Trips — mix business/perso, vérification manuelle'),
    (r'UBER.*EATS|UBEREATS', 'VERIFY', 'UberEats — mix testing/team building/perso, vérification manuelle'),
    (r'WHOOP', 'VERIFY', 'Whoop — à vérifier'),
    (r'DOOLA', 'VERIFY', 'Doola — à vérifier'),
    (r'CHOCO\s*CHOCO\.COM|CHOCOCHOCO', 'VERIFY', 'ChocoChoco — à vérifier'),
    (r'NELASANTEINC|NELA\s*SANTE', 'VERIFY', 'Nela Santé — à vérifier'),
    (r'WALMART', 'VERIFY', 'Walmart — peut être resto ou perso'),
    (r'ESSO|PETRO|SHELL|ULTRAMAR|COUCHE-TARD', 'VERIFY', 'Gas/Transport — mix business/perso, appliquer %'),
    (r'INTERET\s*DE\s*DETAIL|INTERETDEDETAIL', 'card_fee', 'Intérêt de détail'),
]
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


def process_all_cards(ralf_path: str) -> list:
    """Process all personal CC transactions and classify them."""
    with open(ralf_path, 'r', encoding='utf-8-sig') as f:
        ralf = list(csv.DictReader(f))

    results = []
    for r in ralf:
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
    ralf_path = './data/cc_master/master_transactions.csv'
    results = process_all_cards(ralf_path)
    generate_report(results)
