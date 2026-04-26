#!/usr/bin/env python3
"""
Personal Credit Card Classification — Business vs Personal vs À Vérifier.

Classifies Owner_A's personal CC transactions into:
- BUSINESS: restaurant supplier expenses (reimbursable)
- PERSONAL: not business-related (not reimbursable)
- TEAM_BUILDING: partner trips/events (50% company, 50% personal — confirm with comptable)
- VERIFY: ambiguous, needs manual review
- CARD_FEE: credit card fees/insurance (excluded from both sides)

Rules:
- Known restaurant suppliers = BUSINESS (SUPPLIER_A, SUPPLIER_B, SUPPLIER_C, Costco, SAQ >$300, etc.)
- SAQ < $300 = VERIFY (could be personal)
- Recurring subscriptions used by restos = BUSINESS (Videotron, Lightspeed, etc.)
- Travel with partners = TEAM_BUILDING at 50%
- Fitness, personal shopping = PERSONAL
- Card fees/insurance = CARD_FEE (excluded)
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
    # Food suppliers (handle "SUPPLIER_A SERVICE", "DAMENSERVICEALIMENTAIRE", "SUPPLIER_A ALIMENTAIRE")
    (r'SUPPLIER_A\s*SERVICE|DAMENSERVICE|SUPPLIER_A\s*ALIMENTAIRE', 'supplier_food', 'SUPPLIER_A Alimentaire'),
    (r'SUPPLIER_B\s*POISSON|FERROPOISSON', 'supplier_food', 'SUPPLIER_B Poisson & Fruits'),
    (r'SUPPLIER_D', 'supplier_food', 'SUPPLIER_D'),
    (r'SUPPLIER_C|MARCH[ÉE]\s*SUPPLIER_C', 'supplier_food', 'Marché SUPPLIER_C'),
    (r'HOUR\s*HONG|EPICERIE\s*HOUR|EPICERIESUPPLIER_E', 'supplier_food', 'SUPPLIER_E Épicerie'),
    (r'ALIMENTS\s*JORK', 'supplier_food', 'SUPPLIER_G'),
    (r'THAI\s*FOOD\s*MART', 'supplier_food', 'Thai Food Mart'),
    (r'COSTCO\s*DELIVERY|COSTCO\s*ENTREPRISE|COSTCOENTREPRISE', 'supplier_food', 'Costco (Business)'),
    (r'DISTRIBUTION\s*MA', 'supplier_food', 'Distribution MA'),
    (r'CAN-AM|CANAM', 'supplier_food', 'Can-Am (Supplier)'),
    (r'SUPPLIER_W', 'supplier_food', 'SUPPLIER_W Enterprises'),
    (r'DELIVERECT', 'supplier_food', 'Deliverect'),
    (r'LA POMME ROUGE', 'supplier_food', 'La Pomme Rouge'),
    (r'SUPPLIER_M', 'supplier_food', 'SUPPLIER_M (Épicerie asiatique)'),
    (r'SUPPLIER_N', 'supplier_beverage', 'SUPPLIER_N (Vin)'),
    (r'SUPPLIER_O', 'supplier_service', 'SUPPLIER_O (Inventaire bar)'),
    (r'LES MARCHANDS DIST', 'supplier_food', 'Les Marchands Distributeurs'),
    (r'SUPPLIER_P FOOD', 'supplier_equipment', 'SUPPLIER_P (Équipement cuisine)'),
    (r'SUPPLIER_Q', 'software_pos', 'SUPPLIER_Q (POS)'),
    (r'SUPPLIER_R', 'supplier_food', 'Choco (Food ordering)'),

    # Beverage/alcohol (SAQ >$300 only — handled in classify function)
    (r'MOLSON|LABATT|BRASSEUR', 'supplier_beverage', 'Brasseur'),

    # Cleaning/linen
    (r'CINTAS', 'supplier_cleaning', 'Cintas'),
    (r'ECOLAB', 'supplier_cleaning', 'Ecolab'),
    (r'LOC.*LINGE.*OLYMPI|LINGES\s*OLYMPI|LOCATION\s*OLYMPI|OLYMPICMONTREAL|PANNETON.*OLY', 'supplier_cleaning', 'Location Olympique'),
    (r'BUANDERIE|NETTOYEUR', 'supplier_cleaning', 'Buanderie/Nettoyeur'),

    # Fish/seafood
    (r'PECHERIES\s*SUPPLIER_F|LESPECHERIESSUPPLIER_F|SUPPLIER_F', 'supplier_food', 'Pêcheries SUPPLIER_F'),

    # Equipment/maintenance
    (r'HOTTE\s*BLANCHE|SUPPLIER_H', 'supplier_equipment', 'SUPPLIER_H'),
    (r'INTEGRAL\s*XT', 'supplier_service', 'SUPPLIER_I (Exterminateur)'),
    (r'SUPPLIER_J', 'supplier_service', 'SUPPLIER_J'),
    (r'CHEZ\s*POTIER|SPSUPPLIER_K', 'supplier_equipment', 'SUPPLIER_K'),
    (r'PROJET\s*HUITRES|SUPPLIER_L', 'supplier_food', 'Projet Huîtres'),

    # Telecom/tech for restaurants
    (r'VIDEOTRON', 'telecom', 'Vidéotron'),
    (r'ROGERS', 'telecom', 'Rogers'),
    (r'SUPPLIER_S|SUPPLIER_S', 'telecom', 'SUPPLIER_S'),
    (r'LIGHTSPEED', 'software_pos', 'Lightspeed (POS)'),
    (r'OPENTABLE', 'software_reservation', 'OpenTable'),
    (r'AGENDRIX', 'software_hr', 'Agendrix'),
    (r'SUPPLIER_T', 'software_payroll', 'SUPPLIER_T'),
    (r'NUAGE\s*SIGHT|SUPPLIER_U', 'supplier_service', 'SUPPLIER_U (Alarme)'),
    (r'SKOOL\.COM|SKOOL', 'software', 'Skool (Logiciel)'),
    (r'JASPER\.AI|JASPERAI', 'software', 'Jasper AI (Logiciel)'),

    # Utilities
    (r'ENERGIR', 'utility', 'Énergir'),
    (r'HYDRO.QUEBEC', 'utility', 'Hydro-Québec'),

    # Software subscriptions (business)
    (r'GOOGLE.*SUITE|GOOGLE.*WORKSPACE|GSUITE|GSUITE_DEBTOR', 'software', 'Google Workspace'),
    (r'QUICKBOOKS', 'software', 'QuickBooks'),
    (r'DROPBOX', 'software', 'Dropbox'),
    (r'ZOOM', 'software', 'Zoom'),
    (r'LOOM', 'software', 'Loom'),
    (r'ADOBE', 'software', 'Adobe'),
    (r'INDEED', 'software_hr', 'Indeed (Recrutement)'),
    (r'FACEBOOK|FACEBK', 'marketing', 'Facebook Ads'),
    (r'GOOGLE ONE', 'software', 'Google One'),
    (r'SHEMIE\.CA|WWW\.SHEMIE', 'accounting', 'ACCOUNTANT_DOMAIN (Comptable)'),
    (r'SERVICELABINC|SUPPLIER_V\s*INC|SERVICE\s*LAB', 'software', 'SUPPLIER_V Inc'),
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
    (r'FITNESS_VENDORFITNESS|FITNESS|GYM', 'fitness', 'Fitness'),
    (r'NETFLIX|SPOTIFY|DISNEY|CRAVE', 'entertainment', 'Streaming'),
    (r'PHARMAPRIX|JEAN COUTU', 'pharmacy', 'Pharmacie'),
    (r'NESPRESSO', 'personal_shopping', 'Nespresso'),
    (r'HOSPITAL_BANGKOK\s*HOSPITAL', 'personal_medical', 'Hospital Bangkok (Personal)'),
    (r'ANNUAL\s*FEE', 'card_fee', 'Annual Fee'),
    (r'DOLLARAMA', 'personal_shopping', 'Dollarama (Perso)'),
    (r'LAW_FIRM\s*THIBAULT', 'personal_legal', 'LAW_FIRM Thibault Ryan (Perso)'),
    (r'GRAB\.COM|WWW\.GRAB', 'personal_travel', 'Grab Bangkok (Perso vacances)'),
    (r'LASH\s*LAB|SQ\*BEAUTY_STUDIO', 'personal', 'BEAUTY_STUDIO (Perso)'),
    (r'ON\s*SPORTSWEAR|ONSPORTSWEAR', 'personal', 'On Sportswear (Perso)'),
    (r'STEPH\s*GUIDA|PERSONAL_STUDIO', 'personal', 'PERSONAL_STUDIO Studio (Perso)'),
    (r'RESTAURANT_TOKYO', 'personal_travel', 'Restaurant Tokyo (Perso)'),
]

# FLAG: transactions that need specific attention (red flag or verify with comptable)
FLAG_PATTERNS = [
    (r'FLAGGED_VENDOR\s*ST.OUEN|FLAGGED_VENDORSTOUEN', 'FLAG_RED', 'FLAGGED_VENDOR St-Ouen — VÉRIFIER LÉGITIMITÉ'),
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
    (r'BANGKOK_HOTEL.*HOTEL', 'team_building', 'Partner Trip Hotel'),
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
    (r'VERIFY_VENDOR_A', 'VERIFY', 'VERIFY_VENDOR_A — à vérifier'),
    (r'VERIFY_VENDOR_B', 'VERIFY', 'VERIFY_VENDOR_B — à vérifier'),
    (r'CHOCO\s*CHOCO\.COM|SUPPLIER_R', 'VERIFY', 'SUPPLIER_R — à vérifier'),
    (r'SUPPLIER_X|NELA\s*SANTE', 'VERIFY', 'Nela Santé — à vérifier'),
    (r'WALMART', 'VERIFY', 'Walmart — peut être resto ou perso'),
    (r'ESSO|PETRO|SHELL|ULTRAMAR|COUCHE-TARD', 'VERIFY', 'Gas/Transport — mix business/perso, appliquer %'),
    (r'INTERET\s*DE\s*DETAIL|INTERETDEDETAIL', 'card_fee', 'Intérêt de détail'),
]
COMPILED_VERIFY = [(re.compile(p, re.IGNORECASE), cls, label) for p, cls, label in VERIFY_PATTERNS]


def classify_transaction(description: str, amount: float) -> dict:
    """Classify a personal CC transaction."""

    # Check RED FLAGS first
    for regex, cls, label in COMPILED_FLAG:
        if regex.search(description):
            return {'class': cls, 'category': 'flag', 'label': label, 'business_amount': 0,
                    'note': 'RED FLAG — vérifier légitimité'}

    # Check card fees
    for regex, cat, label in COMPILED_CARD_FEE:
        if regex.search(description):
            return {'class': 'CARD_FEE', 'category': cat, 'label': label, 'business_amount': 0}

    # Check specific VERIFY patterns (before business, to catch Apple/Uber)
    for regex, cls, label in COMPILED_VERIFY:
        if regex.search(description):
            if cls == 'card_fee':
                return {'class': 'CARD_FEE', 'category': 'card_fee', 'label': label, 'business_amount': 0}
            return {'class': 'VERIFY', 'category': 'verify_specific', 'label': label,
                    'business_amount': 0, 'note': label}

    # Check team building
    for regex, cat, label in COMPILED_TEAM:
        if regex.search(description):
            return {'class': 'TEAM_BUILDING', 'category': cat, 'label': label,
                    'business_amount': round(amount * 0.5, 2),
                    'note': '50% company — confirm with comptable'}

    # Check personal
    for regex, cat, label in COMPILED_PERSONAL:
        if regex.search(description):
            return {'class': 'PERSONAL', 'category': cat, 'label': label, 'business_amount': 0}

    # SAQ: >$300 = business, <$300 = personal (confirmed by Owner_A)
    if re.search(r'SAQ', description, re.IGNORECASE):
        if amount >= 300:
            return {'class': 'BUSINESS', 'category': 'supplier_alcohol', 'label': 'SAQ (>$300)',
                    'business_amount': amount}
        else:
            return {'class': 'PERSONAL', 'category': 'personal_alcohol',
                    'label': 'SAQ (<$300 — personnel)',
                    'business_amount': 0}

    # Check business
    for regex, cat, label in COMPILED_BUSINESS:
        if regex.search(description):
            return {'class': 'BUSINESS', 'category': cat, 'label': label, 'business_amount': amount}

    # Default: VERIFY
    return {'class': 'VERIFY', 'category': 'unknown', 'label': 'À VÉRIFIER',
            'business_amount': 0}


def process_all_cards(ralf_path: str) -> list:
    """Process all personal CC transactions and classify them."""
    with open(ralf_path, 'r', encoding='utf-8-sig') as f:
        BOOKKEEPER = list(csv.DictReader(f))

    results = []
    for r in BOOKKEEPER:
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
            'label', 'business_amount', 'note', 'month',
        ])
        writer.writeheader()
        writer.writerows(results)
    print(f'Classified CSV: {csv_path}')

    # Summary
    by_class = defaultdict(lambda: {'count': 0, 'total': 0, 'business': 0})
    for r in results:
        by_class[r['class']]['count'] += 1
        by_class[r['class']]['total'] += r['amount']
        by_class[r['class']]['business'] += r['business_amount']

    print(f'\nCLASSIFICATION SUMMARY:')
    grand_total = sum(d['total'] for d in by_class.values())
    for cls in ['BUSINESS', 'TEAM_BUILDING', 'PERSONAL', 'CARD_FEE', 'VERIFY']:
        d = by_class[cls]
        pct = d['total'] / grand_total * 100 if grand_total > 0 else 0
        print(f'  {cls:15} {d["count"]:>5} txns  ${d["total"]:>12,.2f} ({pct:>5.1f}%)  business: ${d["business"]:>10,.2f}')

    business_total = sum(d['business'] for d in by_class.values())
    print(f'  {"TOTAL BUSINESS":15} {"":>5}       ${business_total:>12,.2f}')

    # By card
    print(f'\nBY CARD:')
    by_card = defaultdict(lambda: defaultdict(lambda: {'count': 0, 'total': 0, 'business': 0}))
    for r in results:
        by_card[r['card']][r['class']]['count'] += 1
        by_card[r['card']][r['class']]['total'] += r['amount']
        by_card[r['card']][r['class']]['business'] += r['business_amount']

    for card in sorted(by_card.keys()):
        card_total = sum(d['total'] for d in by_card[card].values())
        card_biz = sum(d['business'] for d in by_card[card].values())
        print(f'  {card}: ${card_total:,.0f} total, ${card_biz:,.0f} business ({card_biz/card_total*100:.0f}%)')
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
