---
type: source
last_updated: YYYY-MM-DD
session_id: <currently active session>
---

# FORENSIC STATUS — Cold-start file

> READ ME FIRST at every session start, before any other action.
> Rewritten at every session end. History lives in SESSION_LOG.md.

## 0. Anti-drift reminders for AI

- Never state any number as fact unless you cite source file + row/page/sheet/entry id. If you cannot, say `unverified`.
- Default `confidence_status` is `NEEDS_REVIEW`. Only escalate to `CONFIRMED` with explicit user confirmation recorded in `decisions.jsonl`.
- Never auto-compute split percentages without a source.
- Never modify `type: source` notes. Only create `type: analysis` notes.
- If `last_updated` on an entity STATUS.md is >7 days, flag before acting.
- Legal/tax/strategy questions: route to trustee, qualified accountant, or qualified counsel. Do not answer.
- Use `confidence_status` for value epistemic state and `resolution_status` for workflow lifecycle. Never collapse them into one column.

## 1. LAST VERIFIED (sourced confirmed numbers)

| Item | Amount | confidence_status | source_id | source | source_locator | Verified date |
|---|---|---|---|---|---|---|
| | | CONFIRMED | | | | |

## 2. OPEN GAPS (what's unknown)

- [ ]

## 3. NEXT ACTION (concrete next thing)

-

## 4. BLOCKED ON (waiting on external)

| What | Who | Since |
|---|---|---|
| | | |

## 5. FETCH NEXT (documents the user must download next)

| document | portal_or_source | entity | why_blocking | needed_for | requested_date | confidence_impact | next_owner |
|---|---|---|---|---|---|---|---|
| | | | | | YYYY-MM-DD | | user |

> The user reads this section first thing each morning to know what to download today. If a row sits >7 days, escalate.

## 6. DO NOT TOUCH UNTIL

-

## 7. Active session

- Session id:
- Started:
- Files touched this session:
- Next checkpoint:
