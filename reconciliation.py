#!/usr/bin/env python3
"""
Inter-company reconciliation — monthly matrix + bidirectional matching.

For each transfer FROM entity A TO entity B, there should be a matching
entry IN entity B FROM entity A (same date, same amount).

This script:
1. Builds monthly transfer matrix (who sent how much to whom)
2. Matches outflows with inflows bidirectionally
3. Flags unmatched transfers
4. Produces a reconciliation report
"""

import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def load_transfers(path='output/transfers_all.csv'):
    with open(path, 'r') as f:
        return list(csv.DictReader(f))


def load_transactions(path='output/master_transactions.csv'):
    with open(path, 'r') as f:
        return list(csv.DictReader(f))


# Entities that are actual business accounts (NOT personal)
BUSINESS_ENTITIES = {'Siam House', 'Vine Room', 'Lotus Kitchen', 'Siam Holdings Inc', 'Garden Bistro'}
PERSONAL_ENTITIES = {'Owner_A (Personnel)', 'Holding Owner_A+Siam'}


def build_monthly_matrix(transfers):
    """Build monthly transfer matrix: month → source → dest → total.

    CRITICAL: Only count OUTFLOWS (description contains '/ à' or '/à')
    to avoid double-counting. Each inter-co transfer appears twice in the data:
    once as outflow (à) from sender, once as inflow (de) at receiver.

    Exception: owner_a_reimbursement type is already single-sided.
    """
    matrix = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))

    for t in transfers:
        if t['transfer_type'] == 'owner_a_reimbursement':
            # Owner_A reimbursements are single-sided, always count
            month = t['date'][:7] if t['date'] else 'unknown'
            src = t['source_entity']
            dst = t['destination_entity']
            if src != dst:
                matrix[month][src][dst] += float(t['amount'])
            continue

        if t['transfer_type'] == 'interac_out':
            # RBC "Virement envoyé" to known entities (Garden Bistro → Siam kitchen etc.)
            dst = t.get('destination_entity', '')
            # Map interac_out destinations to entities
            if 'Siam kitchen' in dst or 'Siam Kitchen' in dst:
                month = t['date'][:7] if t['date'] else 'unknown'
                matrix[month][t['source_entity']]['Siam Holdings Inc'] += float(t['amount'])
            continue

        if t['transfer_type'] != 'intercompany':
            continue

        # For inter-company: only count OUTFLOWS to avoid double-counting
        desc = t.get('description', '')
        is_outflow = ('/ à' in desc or '/à' in desc or
                      'Virement envoyé' in desc or 'Virement par Banque' in desc)

        if not is_outflow:
            continue

        month = t['date'][:7] if t['date'] else 'unknown'
        src = t['source_entity']
        dst = t['destination_entity']
        if src == dst:
            continue
        amt = float(t['amount'])
        matrix[month][src][dst] += amt

    return matrix


def reconcile_intercompany(transfers):
    """
    Match outflows with inflows bidirectionally.

    A transfer "Siam House → Siam Holdings Inc, $5,000 on 2024-03-15" should have
    a matching "Siam Holdings Inc received from Siam House, $5,000 on 2024-03-15".

    Returns (matched_pairs, unmatched_outflows, unmatched_inflows).
    """
    # Separate outflows (debit side) and inflows (credit side)
    outflows = []  # From entity A perspective: money going OUT to B
    inflows = []   # From entity B perspective: money coming IN from A

    for t in transfers:
        if t['transfer_type'] != 'intercompany':
            continue
        src = t['source_entity']
        dst = t['destination_entity']

        # Only reconcile business-to-business transfers (no self-transfers)
        if src not in BUSINESS_ENTITIES or dst not in BUSINESS_ENTITIES:
            continue
        if src == dst:
            continue

        amt = float(t['amount'])
        date = t['date']

        # Determine if this is an outflow or inflow based on the description
        desc = t.get('description', '')
        if '/ à' in desc.lower() or '/à' in desc.lower():
            # Outflow: entity sent money TO another account
            outflows.append({'date': date, 'amount': amt, 'from': src, 'to': dst, 'desc': desc, 'file': t.get('file', '')})
        elif '/ de' in desc.lower() or '/de' in desc.lower():
            # Inflow: entity received money FROM another account
            inflows.append({'date': date, 'amount': amt, 'from': src, 'to': dst, 'desc': desc, 'file': t.get('file', '')})

    # Match outflows with inflows
    matched = []
    used_inflows = set()

    # Helper: check if two dates are within N days
    from datetime import datetime as dt, timedelta
    def dates_close(d1, d2, max_days=3):
        try:
            t1 = dt.strptime(d1, '%Y-%m-%d')
            t2 = dt.strptime(d2, '%Y-%m-%d')
            return abs((t1 - t2).days) <= max_days
        except ValueError:
            return d1 == d2

    # Pass 1: exact date match
    for i, out in enumerate(outflows):
        for j, inf in enumerate(inflows):
            if j in used_inflows:
                continue
            if (abs(out['amount'] - inf['amount']) < 0.02 and
                out['date'] == inf['date'] and
                out['from'] == inf['from'] and
                out['to'] == inf['to']):
                matched.append((out, inf))
                used_inflows.add(j)
                break

    # Pass 2: fuzzy date (±3 days) for remaining unmatched
    matched_out_idx = set(i for i, (out, _) in enumerate(matched) if out in outflows)
    for i, out in enumerate(outflows):
        if any(out is m[0] for m in matched):
            continue
        for j, inf in enumerate(inflows):
            if j in used_inflows:
                continue
            if (abs(out['amount'] - inf['amount']) < 0.02 and
                dates_close(out['date'], inf['date']) and
                out['from'] == inf['from'] and
                out['to'] == inf['to']):
                matched.append((out, inf))
                used_inflows.add(j)
                break

    unmatched_out = [out for i, out in enumerate(outflows)
                     if not any(out is m[0] for m in matched)]
    unmatched_in = [inf for j, inf in enumerate(inflows)
                    if j not in used_inflows]

    return matched, unmatched_out, unmatched_in


def generate_report(transfers, transactions, output_path='output/INTERCO_RECONCILIATION.md'):
    """Generate the full reconciliation report."""
    lines = []
    lines.append('# RÉCONCILIATION INTER-COMPAGNIES')
    lines.append(f'**Généré:** {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    lines.append('')

    # === Section 1: Monthly matrix ===
    matrix = build_monthly_matrix(transfers)

    lines.append('## 1. MATRICE MENSUELLE DES TRANSFERTS')
    lines.append('')

    all_entities = sorted(BUSINESS_ENTITIES | PERSONAL_ENTITIES)
    months = sorted(matrix.keys())

    for month in months:
        month_data = matrix[month]
        # Check if there's any inter-entity flow this month
        has_flow = any(
            month_data[src][dst] > 0
            for src in month_data
            for dst in month_data[src]
            if src != dst
        )
        if not has_flow:
            continue

        month_total = sum(
            month_data[src][dst]
            for src in month_data
            for dst in month_data[src]
        )

        lines.append(f'### {month} (total: ${month_total:,.0f})')

        # Build compact table — only entities that appear
        active_src = sorted(set(src for src in month_data if any(month_data[src][d] > 0 for d in month_data[src])))
        active_dst = sorted(set(dst for src in month_data for dst in month_data[src] if month_data[src][dst] > 0))

        if not active_src:
            continue

        header = '| De \\ À | ' + ' | '.join(active_dst) + ' |'
        sep = '|--------|' + '|'.join(['--------'] * len(active_dst)) + '|'
        lines.append(header)
        lines.append(sep)

        for src in active_src:
            cells = []
            for dst in active_dst:
                val = month_data[src][dst]
                cells.append(f'${val:,.0f}' if val > 0 else '—')
            lines.append(f'| **{src}** | ' + ' | '.join(cells) + ' |')

        lines.append('')

    # === Section 2: Bidirectional reconciliation ===
    lines.append('## 2. RÉCONCILIATION BIDIRECTIONNELLE')
    lines.append('')

    matched, unmatched_out, unmatched_in = reconcile_intercompany(transfers)

    lines.append(f'**Paires matchées:** {len(matched)} (sortie = entrée confirmée)')
    lines.append(f'**Sorties non-matchées:** {len(unmatched_out)} (argent envoyé mais pas vu reçu)')
    lines.append(f'**Entrées non-matchées:** {len(unmatched_in)} (argent reçu mais pas vu envoyé)')
    lines.append('')

    if unmatched_out:
        lines.append('### Sorties non-matchées (top 30 par montant)')
        lines.append('| Date | Montant | De | À | Description |')
        lines.append('|------|---------|----|----|-------------|')
        for t in sorted(unmatched_out, key=lambda x: -x['amount'])[:30]:
            lines.append(f'| {t["date"]} | ${t["amount"]:,.2f} | {t["from"]} | {t["to"]} | {t["desc"][:50]} |')
        lines.append('')

    if unmatched_in:
        lines.append('### Entrées non-matchées (top 30 par montant)')
        lines.append('| Date | Montant | De | À | Description |')
        lines.append('|------|---------|----|----|-------------|')
        for t in sorted(unmatched_in, key=lambda x: -x['amount'])[:30]:
            lines.append(f'| {t["date"]} | ${t["amount"]:,.2f} | {t["from"]} | {t["to"]} | {t["desc"][:50]} |')
        lines.append('')

    # === Section 3: Owner_A & Owner_B complete ===
    lines.append('## 3. OWNER_A — PORTRAIT COMPLET 2024+2025')
    lines.append('')

    with open('output/owner_a_transfers.csv', 'r') as f:
        owner_a = list(csv.DictReader(f))

    reimb = [r for r in owner_a if r['type'] == 'remboursement']
    adv = [r for r in owner_a if r['type'] == 'avance_actionnaire']
    reimb_total = sum(float(r['amount']) for r in reimb)
    adv_total = sum(float(r['amount']) for r in adv)

    lines.append(f'| Type | Montant | Transferts |')
    lines.append(f'|------|---------|-----------|')
    lines.append(f'| Remboursements | **${reimb_total:,.2f}** | {len(reimb)} |')
    lines.append(f'| Avances holding | **${adv_total:,.2f}** | {len(adv)} |')
    lines.append(f'| **TOTAL** | **${reimb_total+adv_total:,.2f}** | {len(owner_a)} |')
    lines.append('')

    # Monthly breakdown
    lines.append('### Mensuel Owner_A')
    lines.append('| Mois | Remboursement | Avance | Total |')
    lines.append('|------|--------------|--------|-------|')

    by_month = defaultdict(lambda: {'reimb': 0, 'adv': 0})
    for r in owner_a:
        m = r['date'][:7]
        if r['type'] == 'remboursement':
            by_month[m]['reimb'] += float(r['amount'])
        else:
            by_month[m]['adv'] += float(r['amount'])

    for m in sorted(by_month.keys()):
        d = by_month[m]
        lines.append(f'| {m} | ${d["reimb"]:,.0f} | ${d["adv"]:,.0f} | ${d["reimb"]+d["adv"]:,.0f} |')
    lines.append('')

    # By entity
    lines.append('### Par entité Owner_A')
    lines.append('| Entité | Remboursement | Avance | Total |')
    lines.append('|--------|--------------|--------|-------|')

    by_entity = defaultdict(lambda: {'reimb': 0, 'adv': 0})
    for r in owner_a:
        entity = r['from']
        if r['type'] == 'remboursement':
            by_entity[entity]['reimb'] += float(r['amount'])
        else:
            by_entity[entity]['adv'] += float(r['amount'])

    for e in sorted(by_entity.keys(), key=lambda x: -(by_entity[x]['reimb'] + by_entity[x]['adv'])):
        d = by_entity[e]
        lines.append(f'| {e} | ${d["reimb"]:,.0f} | ${d["adv"]:,.0f} | ${d["reimb"]+d["adv"]:,.0f} |')
    lines.append('')

    # === Section 4: Owner_B ===
    lines.append('## 4. ALI — PORTRAIT COMPLET')
    lines.append('')

    with open('output/ali_transfers.csv', 'r') as f:
        owner_b = list(csv.DictReader(f))

    ali_r = sum(float(r['amount']) for r in owner_b if r.get('type') == 'remboursement')
    ali_a = sum(float(r['amount']) for r in owner_b if r.get('type') == 'avance')

    lines.append(f'| Type | Montant | Transferts |')
    lines.append(f'|------|---------|-----------|')
    lines.append(f'| Remboursements | **${ali_r:,.2f}** | {sum(1 for r in owner_b if r.get("type")=="remboursement")} |')
    lines.append(f'| Avances | **${ali_a:,.2f}** | {sum(1 for r in owner_b if r.get("type")=="avance")} |')
    lines.append(f'| **TOTAL** | **${ali_r+ali_a:,.2f}** | {len(owner_b)} |')
    lines.append('')

    # === Section 5: Comparison ===
    lines.append('## 5. COMPARAISON OWNER_A vs ALI (2024+2025)')
    lines.append('')
    lines.append('| | Owner_A | Owner_B | Ratio |')
    lines.append('|---|--------|-----|-------|')
    lines.append(f'| Remboursements | ${reimb_total:,.0f} | ${ali_r:,.0f} | {reimb_total/max(ali_r,1):.1f}x |')
    lines.append(f'| Avances | ${adv_total:,.0f} | ${ali_a:,.0f} | {adv_total/max(ali_a,1):.1f}x |')
    owner_a_total = reimb_total + adv_total
    ali_total = ali_r + ali_a
    lines.append(f'| **TOTAL** | **${owner_a_total:,.0f}** | **${ali_total:,.0f}** | **{owner_a_total/max(ali_total,1):.1f}x** |')
    lines.append('')

    report = '\n'.join(lines)
    Path(output_path).write_text(report, encoding='utf-8')
    print(f'Report: {output_path}')

    # Also write monthly matrix as CSV
    csv_path = 'output/interco_monthly_matrix.csv'
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['month', 'from', 'to', 'amount'])
        for month in sorted(matrix.keys()):
            for src in matrix[month]:
                for dst in matrix[month][src]:
                    amt = matrix[month][src][dst]
                    if amt > 0:
                        writer.writerow([month, src, dst, round(amt, 2)])
    print(f'Monthly matrix CSV: {csv_path}')

    return report


if __name__ == '__main__':
    transfers = load_transfers()
    transactions = load_transactions()
    generate_report(transfers, transactions)
