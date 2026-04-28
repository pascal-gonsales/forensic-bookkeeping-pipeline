---
type: source
entity: ENTITY_SLUG
entity_name: Full Legal Name Inc.
neq: 0000000000
bn: 000000000RC0001
status: active|closed|sold|insolvent
trustee_estate_no: 41-XXXXXXX
last_updated: YYYY-MM-DD
---

# ENTITY_NAME — STATUS

> **Type rule:** This is a `source` note. Do NOT modify with inferences. Create a separate `analysis` note for any synthesis.

> **Source rule:** Every amount-bearing row MUST carry `confidence_status` plus `source_id`, `source`, `source_locator`. If you cannot fill them, the row stays empty.

## 1. Identification
- Legal name:
- Operating name(s):
- NEQ (Quebec registry):
- BN (federal):
- Date of closure / sale:
- Director status on REQ (verified date, source_id):
- Bank account(s):

## 2. Tax accounts status

| Program | Account # | État de compte date | Last verified | confidence_status | source_id | source | source_locator |
|---|---|---|---|---|---|---|---|
| RP federal (paie) | | | | NEEDS_REVIEW | | | |
| RT federal (corp GST/HST) | | | | NEEDS_REVIEW | | | |
| RS Quebec (paie) | | | | NEEDS_REVIEW | | | |
| CO-17 (corp QC) | | | | NEEDS_REVIEW | | | |
| TVQ | | | | NEEDS_REVIEW | | | |
| CNESST | | | | NEEDS_REVIEW | | | |
| T2 latest filed (year:) | | | | NEEDS_REVIEW | | | |
| CO-17 latest filed (year:) | | | | NEEDS_REVIEW | | | |

## 3. Employee claims

| Item | Amount | confidence_status | source_id | source | source_locator | Notes |
|---|---|---|---|---|---|---|
| Vacation pay net (CCQ-protected window) | | NEEDS_REVIEW | | | | |
| Vacation pay >6 months | | NEEDS_REVIEW | | | | |
| Unpaid wages | | NEEDS_REVIEW | | | | |
| Final pay outstanding | | NEEDS_REVIEW | | | | |
| Tips reconciliation | | NEEDS_REVIEW | | | | |
| Employee advances (over-paid) | | NEEDS_REVIEW | | | | |

## 4. Creditors

| Type | Count | Total | Last refresh | source_id | source |
|---|---|---|---|---|---|
| Secured | | | | | |
| Preferred | | | | | |
| Unsecured | | | | | |
| Contingent (guarantees) | | | | | |

## 5. Inter-company

| Direction | Counterparty | Amount | Documented? | confidence_status | source_id | source | source_locator |
|---|---|---|---|---|---|---|---|
| Owed TO this entity from | | | | NEEDS_REVIEW | | | |
| Owed BY this entity to | | | | NEEDS_REVIEW | | | |

## 6. Bank coverage

| Bank | Account | Period covered | Gaps | source_id | source |
|---|---|---|---|---|---|
| | | | | | |

## 7. Director liability exposure (if applicable)

| Item | Amount | confidence_status | source_id | source | source_locator |
|---|---|---|---|---|---|
| DAS RP unremitted (federal) | | NEEDS_REVIEW | | | |
| DAS RS unremitted (Quebec) | | NEEDS_REVIEW | | | |
| 2-year clock starts (date) | | NEEDS_REVIEW | | | |

> Director-liability legal interpretation is out of scope for this Skill. Document the underlying facts here, then ask the trustee or qualified counsel.

## 8. OPEN GAPS
- [ ]

## 9. NEXT ACTION
-

## 10. BLOCKED ON
-

## 11. DECISIONS log (link)
- See `decisions.jsonl` filtered by `entity:ENTITY_SLUG`

## 12. Last 3 sessions (auto-appended)
-
