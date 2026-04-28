---
type: analysis
prepared_by: <debtor name>
prepared_for: <trustee name>
date: YYYY-MM-DD
covers_period: YYYY-MM-DD to YYYY-MM-DD
entities_covered: <list of entity slugs>
validation_modes_run: package, strict, handoff
---

# Trustee Briefing — <Date>

> **For:** <trustee name>, <trustee firm>
> **From:** <debtor name>
> **Re:** Insolvency dossier — <restaurant group descriptor>

## 1. Executive summary (3 bullets max)

-
-
-

## 2. Confirmed numbers (every row sourced)

| Item | Entity | Amount | confidence_status | source_id | source | source_locator |
|---|---|---|---|---|---|---|
| | | | CONFIRMED | | | |

> Only `CONFIRMED` rows appear here. `INFERRED` items appear in section 4. `BLOCKED` items appear in section 6 + 7.

## 3. Per-entity status snapshot

For each entity, report only sourced rows. Every amount carries `confidence_status` + source columns.

### <entity-slug-1>

| Item | Amount | confidence_status | source_id | source | source_locator |
|---|---|---|---|---|---|
| Tax accounts CONFIRMED count | | CONFIRMED | | | |
| Employee claims CONFIRMED net | | CONFIRMED | | | |
| Creditors total | | CONFIRMED | | | |

Open items: see `entities/<entity-slug-1>/STATUS.md`.

### <entity-slug-2>

(same structure)

## 4. INFERRED items (flagged for user/trustee review before any deposit)

| Item | Entity | Amount | confidence_status | source_id | source | source_locator | Why inferred | Action requested |
|---|---|---|---|---|---|---|---|---|
| | | | INFERRED | | | | | |

## 5. NEEDS_REVIEW items still open (will not be deposited until resolved)

| Item | Entity | Amount | confidence_status | source_id | source | source_locator | Open question |
|---|---|---|---|---|---|---|---|---|
| | | | NEEDS_REVIEW | | | | |

## 6. What's blocked (and on whom)

Pulled from `FORENSIC_STATUS.md` FETCH NEXT section.

| Item | Blocked on (portal/source) | Entity | Since | Action expected | Next owner |
|---|---|---|---|---|---|
| | | | | | |

## 7. Not included because blocked

The following amounts are deliberately excluded from sections 2 and 3 because the underlying source is not yet on file. They are not estimated.

| Item | Entity | Why excluded | Document needed | Where to fetch |
|---|---|---|---|---|
| | | | | |

## 8. Questions for trustee, qualified accountant, or qualified counsel

Questions only. No proposed answers. No recommendations. No statutory interpretation.

1. Question:
2. Question:
3. Question:

> Routing legend: trustee = insolvency procedure / BIA-related / filing decisions; qualified accountant = tax planning / T2/CO-17 elections / voluntary disclosure; qualified counsel = legal interpretation / director liability defense / litigation.

## 9. Files attached

| source_id | Path | SHA256 | Size |
|---|---|---|---|
| | | | |

## 10. Confidence statement

This briefing distinguishes:
- **CONFIRMED** numbers (section 2 + 3): backed by source documents reviewed and confirmed by the debtor
- **INFERRED** numbers (section 4): probable from data patterns, flagged for review before any deposit
- **NEEDS_REVIEW** items (section 5): open questions awaiting user/trustee response
- **BLOCKED** items (sections 6 + 7): awaiting external documents, never estimated

Validation modes run before this briefing was generated: `<list, e.g. package, strict, handoff>`. Source registry checksums verified `<date>`.

No invented or estimated figures appear in the CONFIRMED section. Every number traces to a `source_id` in `source_registry.csv`. The full decision log is available in `decisions.jsonl` for audit.

---

*Generated using the forensic-bookkeeping skill v1.2. Methodology references available on request.*
