#!/usr/bin/env python3
"""Generate PDF presentation of forensic bookkeeping tables."""

from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak,
    KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

def fmt(n):
    if n == 0 or n is None:
        return '—'
    return f'${n:,.0f}'

def build_pdf():
    doc = SimpleDocTemplate(
        'output/PRESENTATION_FORENSIC.pdf',
        pagesize=landscape(letter),
        topMargin=0.5*inch,
        bottomMargin=0.5*inch,
        leftMargin=0.5*inch,
        rightMargin=0.5*inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('CustomTitle', parent=styles['Title'], fontSize=18, spaceAfter=6)
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontSize=10, textColor=colors.grey, spaceAfter=12)
    heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=13, spaceAfter=6, spaceBefore=12)
    note_style = ParagraphStyle('Note', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#444444'), spaceBefore=4, spaceAfter=2)
    context_style = ParagraphStyle('Context', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#333333'), spaceBefore=6, spaceAfter=2, leftIndent=10, borderColor=colors.HexColor('#cccccc'), borderWidth=0.5, borderPadding=4)

    story = []

    header_bg = colors.HexColor('#1a1a2e')
    header_fg = colors.white
    row_alt = colors.HexColor('#f0f0f5')
    total_bg = colors.HexColor('#e8e8f0')

    def make_table(data, col_widths=None, has_total_row=True):
        t = Table(data, colWidths=col_widths, repeatRows=1)
        style = [
            ('BACKGROUND', (0, 0), (-1, 0), header_bg),
            ('TEXTCOLOR', (0, 0), (-1, 0), header_fg),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('OWNER_BGN', (1, 0), (-1, -1), 'RIGHT'),
            ('OWNER_BGN', (0, 0), (0, -1), 'LEFT'),
            ('VOWNER_BGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]
        for i in range(1, len(data)):
            if i % 2 == 0:
                style.append(('BACKGROUND', (0, i), (-1, i), row_alt))
        if has_total_row:
            style.append(('BACKGROUND', (0, -1), (-1, -1), total_bg))
            style.append(('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'))
        t.setStyle(TableStyle(style))
        return t

    # ==================== PAGE 1: TITLE + SUMMARY ====================
    story.append(Paragraph('Portrait Financier — Demo Restaurant Group', title_style))
    story.append(Paragraph('2024-2025 | Préparé le 2 avril 2026 | Source: 13,081 transactions bancaires + factures Quickbooks', subtitle_style))

    story.append(Paragraph('Résumé', heading_style))
    summary_data = [
        ['', '2024', '2025', 'Total'],
        ['Remboursements Owner_A', fmt(778681), fmt(584103), fmt(1362784)],
        ['Avances holding Owner_A', fmt(291527), fmt(258800), fmt(550327)],
        ['Owner_B remboursements', fmt(30530), fmt(49985), fmt(80515)],
        ['Owner_B avances holding', fmt(56712), fmt(51065), fmt(107777)],
        ['CC perso Owner_A (business + perso)', fmt(1157486), fmt(691553), fmt(1849039)],
        ['Refacturation alimentaire (QB)', fmt(327076), fmt(631547), fmt(958623)],
        ['Paiements non-rapprochés (Siam S)', '', '', fmt(565567)],
        ['A/R Aging Siam S (au 2 avr 2026)', '', '', fmt(383797)],
    ]
    story.append(make_table(summary_data, col_widths=[2.8*inch, 1.3*inch, 1.3*inch, 1.3*inch], has_total_row=False))

    # ==================== PAGE 2: INTERCO 2024 ====================
    story.append(PageBreak())
    story.append(Paragraph('Tableau 1 — Mouvements inter-compagnies 2024', heading_style))

    ic2024 = [
        ['De \\ À', 'Lotus Kitchen', 'Siam House', 'Siam S', 'Vine RM', 'Owner_A remb.', 'Holding', 'Owner_B remb.', 'Owner_B Hold.', 'TOTAL'],
        ['Lotus Kitchen', '—', fmt(20189), fmt(208859), fmt(44000), fmt(212680), fmt(110027), fmt(3123), fmt(12427), fmt(595755)],
        ['Siam House', fmt(54500), '—', fmt(208299), fmt(156100), fmt(187393), fmt(107000), fmt(4916), fmt(16285), fmt(713292)],
        ['Siam Holdings Inc', fmt(9300), fmt(6302), '—', fmt(6851), fmt(194002), fmt(74500), fmt(5317), fmt(28000), fmt(290955)],
        ['Vine Room', fmt(42000), fmt(38801), fmt(58343), '—', fmt(104008), '—', fmt(6146), '—', fmt(243152)],
        ['Garden Bistro', '—', '—', fmt(103463), '—', fmt(138688), '—', fmt(11029), '—', fmt(242151)],
        ['TOTAL REÇU', fmt(105800), fmt(65293), fmt(578964), fmt(206951), fmt(836771), fmt(291527), fmt(30530), fmt(56712), ''],
    ]
    story.append(make_table(ic2024, col_widths=[1.0*inch]+[0.85*inch]*9))
    story.append(Paragraph('<b>Notes:</b> Les mouvements de fonds des restaurants vers Siam S comprennent: (1) la refacturation alimentaire documentée dans Quickbooks, (2) les frais de licence de 5% du chiffre d\'affaires (voir contrat rédigé par Jamil), et (3) les frais de gestion pour les salaires d\'employés de gestion. Les montants vers le Holding Owner_B représentent des avances actionnaires. Estimation initiale des profits: $150-200K sur Siam House et Lotus Kitchen — profits non réalisés.', context_style))

    # ==================== PAGE 3: INTERCO 2025 ====================
    story.append(PageBreak())
    story.append(Paragraph('Tableau 1b — Mouvements inter-compagnies 2025', heading_style))

    ic2025 = [
        ['De \\ À', 'Lotus Kitchen', 'Siam House', 'Siam S', 'Vine RM', 'Owner_A remb.', 'Holding', 'Owner_B remb.', 'Owner_B Hold.', 'TOTAL'],
        ['Lotus Kitchen', '—', fmt(54577), fmt(300193), fmt(72350), fmt(80714), fmt(73225), fmt(3254), fmt(18435), fmt(581059)],
        ['Siam House', fmt(36977), '—', fmt(283859), fmt(64550), fmt(81291), fmt(12275), fmt(18661), fmt(5530), fmt(478952)],
        ['Siam Holdings Inc', fmt(10700), fmt(30500), '—', fmt(39600), fmt(488913), fmt(48300), fmt(8386), fmt(25600), fmt(618013)],
        ['Vine Room', fmt(15600), fmt(26600), fmt(44803), '—', fmt(40862), fmt(125000), fmt(9701), fmt(1500), fmt(252865)],
        ['Garden Bistro', '—', '—', fmt(298534), '—', fmt(67707), '—', fmt(9982), '—', fmt(366241)],
        ['TOTAL REÇU', fmt(63277), fmt(111677), fmt(927389), fmt(176500), fmt(759488), fmt(258800), fmt(49985), fmt(51065), ''],
    ]
    story.append(make_table(ic2025, col_widths=[1.0*inch]+[0.85*inch]*9))
    story.append(Paragraph('<b>Notes:</b> Vine Room $125,000 vers le Holding en mars 2025: prêt garanti personnel fait sur le Wineroom pour du cash flow. Montant prêté au Holding pour finaliser l\'achat du condo par Owner_A, devant être remboursé au Wineroom à la vente du condo. Terme du prêt: sans paiement de capital ou d\'intérêt avant fin 2026.', context_style))

    # ==================== PAGE 4: REMBOURSEMENTS OWNER_A 2024 ====================
    story.append(PageBreak())
    story.append(Paragraph('Tableau 2 — Remboursements Owner_A mensuel 2024', heading_style))
    story.append(Paragraph('Interac + virements au compte personnel 089511 combinés', note_style))

    reimb2024 = [
        ['Mois', 'Lotus Kitchen', 'Siam House', 'Siam S', 'Vine RM', 'Garden Bistro', 'TOTAL'],
        ['Jan', fmt(10000), fmt(9500), fmt(2550), fmt(6800), fmt(3305), fmt(32155)],
        ['Fév', fmt(24542), fmt(17020), fmt(6822), fmt(8695), fmt(10914), fmt(67993)],
        ['Mar', fmt(19012), fmt(12442), fmt(30049), fmt(2822), fmt(9891), fmt(74216)],
        ['Avr', fmt(12895), fmt(18090), fmt(14900), fmt(14552), fmt(9015), fmt(69452)],
        ['Mai', fmt(18081), fmt(12363), fmt(28692), fmt(7429), fmt(15105), fmt(81670)],
        ['Jun', fmt(12143), fmt(11652), fmt(5700), fmt(4967), '—', fmt(34463)],
        ['Jul', fmt(18111), fmt(23988), fmt(12614), fmt(2751), fmt(18338), fmt(75801)],
        ['Aoû', fmt(25489), fmt(21888), fmt(20208), fmt(8377), fmt(19424), fmt(95386)],
        ['Sep', fmt(17256), fmt(11961), fmt(3000), fmt(4829), fmt(14984), fmt(52030)],
        ['Oct', fmt(19676), fmt(14633), fmt(7251), fmt(7443), fmt(18574), fmt(67577)],
        ['Nov', fmt(13764), fmt(15492), fmt(23698), fmt(7697), fmt(11241), fmt(71892)],
        ['Déc', fmt(16550), fmt(11123), fmt(9421), fmt(11054), fmt(7898), fmt(56045)],
        ['TOTAL', fmt(207520), fmt(180152), fmt(164905), fmt(87415), fmt(138688), fmt(778681)],
    ]
    story.append(make_table(reimb2024, col_widths=[0.6*inch]+[1.2*inch]*6))
    story.append(Paragraph('<b>Notes:</b> Owner_A avançait les paiements fournisseurs sur ses cartes de crédit personnelles (4 cartes, total $1,157,486 en 2024). Les remboursements couvrent une partie de ces avances. Les données 2024 sont déjà triées mais doivent simplement être traitées dans le tableau de ventilation par entité.', context_style))

    # ==================== PAGE 5: REMBOURSEMENTS OWNER_A 2025 ====================
    story.append(PageBreak())
    story.append(Paragraph('Tableau 2b — Remboursements Owner_A mensuel 2025', heading_style))

    reimb2025 = [
        ['Mois', 'Lotus Kitchen', 'Siam House', 'Siam S', 'Vine RM', 'Garden Bistro', 'TOTAL'],
        ['Jan', fmt(9658), fmt(6835), fmt(11815), fmt(7716), fmt(18931), fmt(54955)],
        ['Fév', fmt(4409), fmt(1533), fmt(5700), fmt(1102), fmt(2924), fmt(15667)],
        ['Mar', fmt(14928), fmt(4891), fmt(2540), fmt(1657), fmt(12414), fmt(36430)],
        ['Avr', fmt(13422), fmt(9602), fmt(8484), fmt(6554), fmt(16828), fmt(54889)],
        ['Mai', fmt(10927), fmt(13318), fmt(17786), fmt(7318), fmt(10037), fmt(59387)],
        ['Jun', fmt(3235), fmt(3133), fmt(29331), fmt(5021), '—', fmt(40719)],
        ['Jul', fmt(1568), fmt(2963), fmt(59927), fmt(612), fmt(5073), fmt(70143)],
        ['Aoû', '—', fmt(2400), fmt(56901), '—', '—', fmt(59301)],
        ['Sep', '—', '—', fmt(62345), '—', '—', fmt(62345)],
        ['Oct', '—', fmt(1900), fmt(50887), '—', fmt(1501), fmt(54288)],
        ['Nov', fmt(870), '—', fmt(56410), '—', '—', fmt(57280)],
        ['Déc', '—', '—', fmt(18700), '—', '—', fmt(18700)],
        ['TOTAL', fmt(59015), fmt(46574), fmt(380826), fmt(29980), fmt(67707), fmt(584103)],
    ]
    story.append(make_table(reimb2025, col_widths=[0.6*inch]+[1.2*inch]*6))
    story.append(Paragraph('<b>Notes:</b> Décision prise à l\'été 2025 de centraliser les dépenses sur Siam S — organisation qui n\'a pas tenu sur la durée.', context_style))

    # ==================== PAGE 6: AVANCES HOLDING ====================
    story.append(PageBreak())
    story.append(Paragraph('Tableau 3 — Avances actionnaire (Holding 092483)', heading_style))

    holding = [
        ['Mois', 'Lotus Kitchen', 'Siam House', 'Siam S', 'Vine RM', 'TOTAL'],
        ['2024-01', fmt(5000), '—', fmt(1500), '—', fmt(6500)],
        ['2024-02', '—', '—', fmt(1000), '—', fmt(1000)],
        ['2024-03', '—', '—', fmt(11000), '—', fmt(11000)],
        ['2024-04', fmt(7500), '—', fmt(2000), '—', fmt(9500)],
        ['2024-05', fmt(30000), fmt(18000), '—', '—', fmt(48000)],
        ['2024-06', fmt(2000), fmt(2000), fmt(2000), '—', fmt(6000)],
        ['2024-07', fmt(5888), fmt(1000), fmt(2000), '—', fmt(8888)],
        ['2024-08', fmt(35258), '—', fmt(9000), '—', fmt(44258)],
        ['2024-09', fmt(4200), '—', fmt(4000), '—', fmt(8200)],
        ['2024-10', fmt(12181), fmt(30000), fmt(11000), '—', fmt(53181)],
        ['2024-11', fmt(8000), fmt(56000), fmt(7000), '—', fmt(71000)],
        ['2024-12', '—', '—', fmt(24000), '—', fmt(24000)],
        ['2024 Total', fmt(110027), fmt(107000), fmt(74500), '—', fmt(291527)],
        ['2025-01', fmt(3500), '—', fmt(3000), '—', fmt(6500)],
        ['2025-02', fmt(9500), '—', fmt(9500), '—', fmt(19000)],
        ['2025-03', fmt(7500), '—', fmt(6500), fmt(125000), fmt(139000)],
        ['2025-04', fmt(10000), fmt(1500), fmt(10200), '—', fmt(21700)],
        ['2025-05', fmt(13000), fmt(1000), fmt(1100), '—', fmt(15100)],
        ['2025-06', fmt(13000), '—', fmt(11000), '—', fmt(24000)],
        ['2025-07', fmt(4900), fmt(3000), fmt(7000), '—', fmt(14900)],
        ['2025-08', fmt(3375), fmt(3375), '—', '—', fmt(6750)],
        ['2025-09', fmt(5050), fmt(2550), '—', '—', fmt(7600)],
        ['2025-10', fmt(3400), fmt(850), '—', '—', fmt(4250)],
        ['2025 Total', fmt(73225), fmt(12275), fmt(48300), fmt(125000), fmt(258800)],
        ['GRAND TOTAL', fmt(183252), fmt(119275), fmt(122800), fmt(125000), fmt(550327)],
    ]
    story.append(make_table(holding, col_widths=[0.8*inch]+[1.2*inch]*5))
    story.append(Paragraph('Garden Bistro: $0 (RBC, pas de transferts vers le holding Desjardins)', note_style))
    story.append(Paragraph('<b>Contexte:</b> La stratégie pour des avances actionnaires aussi élevées était l\'estimation des profits ($150-200K sur Siam House et Lotus Kitchen). Quand les profits ne se sont pas réalisés, Owner_A a décidé de vendre son condo. Le nouveau condo qui devait représenter une revente rapide pour un profit de $100K a coûté plus cher avec des frais multiples. Nous espérions obtenir une marge de crédit hypothécaire pour rembourser le prêt au Wineroom. La vente du condo en dessous du prix d\'achat aurait été catastrophique. Deux courtiers consultés estimaient une vente autour de $1.5M.', context_style))

    # ==================== PAGE 7: CC PERSO ====================
    story.append(PageBreak())
    story.append(Paragraph('Tableau 4 — Cartes de crédit personnelles Owner_A', heading_style))

    cc_data = [
        ['Carte', '2024', '2025', 'Total'],
        ['TD Visa *YYYY', fmt(645608), fmt(306848), fmt(952456)],
        ['TD Visa *XXXX', fmt(256175), fmt(292593), fmt(548768)],
        ['Desjardins Visa *7006', fmt(242558), fmt(50599), fmt(293157)],
        ['BDC Mastercard *ZZZZ', fmt(13146), fmt(41512), fmt(54658)],
        ['TOTAL', fmt(1157486), fmt(691553), fmt(1849039)],
    ]
    story.append(make_table(cc_data, col_widths=[2.5*inch, 1.5*inch, 1.5*inch, 1.5*inch]))

    story.append(Spacer(1, 12))
    story.append(Paragraph('Classification des dépenses CC', heading_style))

    classif = [
        ['Catégorie', '2024', '2025', 'Total', '%'],
        ['Business confirmé', fmt(900022), fmt(641090), fmt(1541112), '83.7%'],
        ['Team building (50%)', fmt(5892), fmt(9511), fmt(15403), '0.8%'],
        ['Personnel', fmt(3765), fmt(6993), fmt(10758), '0.6%'],
        ['Frais de carte', fmt(20008), fmt(2245), fmt(22253), '1.2%'],
        ['À vérifier', fmt(219529), fmt(31714), fmt(251243), '13.6%'],
        ['TOTAL', fmt(1149216), fmt(691553), fmt(1840769), '100%'],
    ]
    story.append(make_table(classif, col_widths=[2*inch, 1.3*inch, 1.3*inch, 1.3*inch, 0.8*inch]))

    # ==================== PAGE 8: REFACTURATION ====================
    story.append(PageBreak())
    story.append(Paragraph('Tableau 6 — Refacturation alimentaire Siam Holdings Inc', heading_style))
    story.append(Paragraph('Source: Quickbooks — Siam S Invoices and Received Payments', note_style))

    refact = [
        ['Client', '2024 Facturé', '2024 Payé', '2025 Facturé', '2025 Payé', 'Total Facturé', 'Solde'],
        ['Siam House', fmt(112004), fmt(112004), fmt(172376), fmt(171559), fmt(284380), fmt(818)],
        ['Lotus Kitchen', fmt(99500), fmt(99500), fmt(232037), fmt(229714), fmt(331537), fmt(2323)],
        ['Garden Bistro', fmt(87816), fmt(87816), fmt(197965), fmt(195619), fmt(285781), fmt(2346)],
        ['Vine Room', fmt(27756), fmt(27756), fmt(29168), fmt(27370), fmt(56924), fmt(1799)],
        ['TOTAL', fmt(327076), fmt(327076), fmt(631547), fmt(624261), fmt(958623), fmt(7285)],
    ]
    story.append(make_table(refact, col_widths=[1.2*inch]+[1.1*inch]*6))
    story.append(Paragraph('<b>Notes:</b> Les montants facturés représentent la refacturation alimentaire. Dans les montants non-rapprochés (Tableau 7), il y a aussi des frais de gestion pour de la refacturation de salaire, en plus du contrat de licence rédigé par Jamil.', context_style))

    story.append(Spacer(1, 18))
    story.append(Paragraph('Tableau 7 — Transferts inter-co vs paiements Quickbooks: montants non-rapprochés', heading_style))

    mgmt = [
        ['Entité', 'Inter-co Desjardins', '+ Garden Bistro RBC', '= Total vers Siam S', 'QB Facturé', 'Écart'],
        ['Lotus Kitchen', fmt(509052), '—', fmt(509052), fmt(329214), fmt(179838)],
        ['Siam House', fmt(502710), '—', fmt(502710), fmt(283562), fmt(219147)],
        ['Vine Room', fmt(103146), '—', fmt(103146), fmt(55125), fmt(48021)],
        ['Garden Bistro', fmt(0), fmt(401997), fmt(401997), fmt(283435), fmt(118561)],
        ['TOTAL', fmt(1114908), fmt(401997), fmt(1516904), fmt(951337), fmt(565567)],
    ]
    story.append(make_table(mgmt, col_widths=[1.1*inch]+[1.25*inch]*5))
    story.append(Paragraph("<b>Notes:</b> L'écart de $565,567 représente les montants transférés par les restaurants vers Siam Holdings Inc qui ne sont pas rapprochés avec des factures dans Quickbooks. Ces montants incluent les frais de licence (5% du CA — contrat rédigé par Jamil, factures à produire) et les frais de gestion (refacturation de salaires des gestionnaires).", context_style))

    # ==================== PAGE 9: AGING ====================
    story.append(PageBreak())
    story.append(Paragraph('Tableau 8 — A/R Aging Summary (au 2 avril 2026)', heading_style))

    aging = [
        ['Client', 'Current', '1-30', '91+', 'TOTAL'],
        ['BNI Ville Marie', '—', '—', fmt(2805), fmt(2805)],
        ['Vine Room', '—', '—', fmt(74659), fmt(74659)],
        ['Le Garden Bistro', fmt(1374), fmt(254), fmt(143650), fmt(145278)],
        ['Lotus Kitchen Milton', fmt(576), fmt(123), fmt(155397), fmt(156096)],
        ['Siam House', fmt(695), fmt(559), fmt(3705), fmt(4959)],
        ['TOTAL', fmt(2645), fmt(936), fmt(380216), fmt(383797)],
    ]
    story.append(make_table(aging, col_widths=[1.5*inch]+[1.3*inch]*4))
    story.append(Paragraph('$380K en 91+ jours = principalement factures 2023 non-payées.', note_style))

    story.append(Spacer(1, 24))
    story.append(Paragraph('Ce qui reste à travailler', heading_style))

    todo = [
        ['#', 'Item', 'Montant', 'Priorité'],
        ['1', 'Ventilation CC par entité Août-Déc 2025', fmt(325000), 'Haute'],
        ['2', 'Ventilation CC par entité 2024', fmt(1157000), 'Haute'],
        ['3', 'Factures SUPPLIER_A (split par resto)', fmt(370000), 'Haute'],
        ['4', 'Factures SUPPLIER_B/SUPPLIER_D/Supplier Delta', fmt(76000), 'Moyenne'],
        ['5', 'Frais de licence 5% (factures à produire)', 'À calculer', 'Moyenne'],
        ['6', 'Frais de gestion (refacturation salaires)', 'À documenter', 'Moyenne'],
        ['7', 'Triage CC transactions à vérifier', fmt(251000), 'Moyenne'],
        ['8', 'Ventilation 2024 non-assigné', fmt(339000), 'Moyenne'],
    ]
    story.append(make_table(todo, col_widths=[0.4*inch, 3.5*inch, 1.2*inch, 0.8*inch], has_total_row=False))

    story.append(Spacer(1, 18))
    story.append(Paragraph('Source: Pipeline forensic bookkeeping V3.2 — Relevés bancaires (CSV+PDF), Relevés CC personnels (PDF+BOOKKEEPER-CC), Factures Quickbooks, A/R Aging Summary.', note_style))

    doc.build(story)
    print('PDF generated: output/PRESENTATION_FORENSIC.pdf')

if __name__ == '__main__':
    build_pdf()
