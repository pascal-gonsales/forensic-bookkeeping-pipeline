# Workflow Checklists — Reference

> Concrete checklists for daily, end-of-session, weekly, and trustee-handoff cadence.

---

## Cold-start checklist (every session, in this order)

1. Read `STANDUP.md` — today's user dump (3 blocks: SINCE LAST / TODAY I HAVE / GOAL TODAY)
2. Read `FORENSIC_STATUS.md` — global state (LAST VERIFIED / OPEN GAPS / NEXT ACTION / BLOCKED ON / FETCH NEXT / DO NOT TOUCH UNTIL)
3. Run `tail -10 decisions.jsonl` — last 10 decisions
4. Read `entities/<slug>/STATUS.md` for the entity in scope today
5. Check `last_updated` on every file you read — if >7 days, flag

**Respond in exactly 3 lines:**
- Line 1: "Read [files], current state is [1-sentence summary]"
- Line 2: "Today's task: [one specific action]"
- Line 3: "I will NOT touch: [list of things explicitly out of scope today]"

Anything more is friction. Anything less is unsafe.

---

## During work (per-action discipline)

For every classification or number you produce:

```
[ ] Source registered — file is in source_registry with stable source_id
[ ] confidence_status assigned (CONFIRMED / INFERRED / NEEDS_REVIEW / BLOCKED)
[ ] source_id, source, source_locator filled (or `none` if BLOCKED)
[ ] Decision logged in decisions.jsonl with required fields including basis (no legal interpretation)
[ ] STATUS.md of touched entity updated
```

If any of the above is "no", stop. Do it before moving on.

---

## End-of-session checklist (5 min, hard requirement)

1. Rewrite `entities/<slug>/STATUS.md` for every entity touched this session
   - Update `last_updated` field
   - Update OPEN GAPS, NEXT ACTION, BLOCKED ON sections
2. Rewrite `FORENSIC_STATUS.md`
   - Move newly-CONFIRMED items to LAST VERIFIED (with `source_id`, `source`, `source_locator`)
   - Add new gaps to OPEN GAPS
   - Update NEXT ACTION to whatever the next session should do first
   - Update BLOCKED ON if new external dependencies appeared
   - Update FETCH NEXT with any new documents the user must download
3. Append to `SESSION_LOG.md` with format:

```markdown
## YYYY-MM-DD HH:MM — session_id

**What changed:**
- ...

**Decisions logged:** [count] new entries in decisions.jsonl

**Open at end of session:** [what's still in-flight]

**Next session priority:** [the ONE thing to start with]

**Files NOT touched this session:**
- ...
```

4. Confirm all new decisions are appended to `decisions.jsonl` with the required-fields schema (including `confidence_status` and `source_id`)
5. If new source documents arrived, refresh the source registry (`python3 scripts/source_registry.py <root>`)

If any of the 5 steps is incomplete, the session is NOT closed. The next session will start blind.

---

## Weekly review (Sunday, 15 min max)

1. Open `decisions.jsonl`, scroll to the week's entries
2. Pick 3 entries at random — verify against the cited source. If the source does not match the decision, flag and re-do.
3. Check each entity's `STATUS.md` `last_updated` — flag any >7 days
4. Update `MASTER_INDEX.md` with current entity status (CONFIRMED count, OPEN GAPS count, BLOCKED count) — no numbers
5. Decide the next week's focus entity. Write it in `FORENSIC_STATUS.md` NEXT ACTION
6. Re-run source registry (`source_registry.py`) to detect any modified files

---

## Trustee email cadence

**Recommended: 2 emails per week** (e.g. Tuesday + Friday)

**Tuesday email format:**
- Subject: `[Insolvency] Status update Week N — <date>`
- Section 1: What changed since last email (1-3 bullets)
- Section 2: Documents prepared and where they are (link/path)
- Section 3: What is being waited on from the trustee
- Section 4: Open questions for the next call (if any)

**Friday email format:**
- Subject: `[Insolvency] Documents delivered Week N — <date>`
- Attachment: the trustee-briefing.md (rendered to PDF if requested)
- Body: 1-paragraph summary of what is in the package + what is still open

**Never:**
- Verbal-only updates on amounts or commitments
- Forwarding a single document without context
- Letting more than 7 days pass with no contact

---

## "What to fetch next" — running list

Maintain this in the `FETCH NEXT` section of `FORENSIC_STATUS.md`. Schema:

| document | portal_or_source | entity | why_blocking | needed_for | requested_date | confidence_impact | next_owner |
|---|---|---|---|---|---|---|---|
| RP federal état de compte | CRA My Business Account | <entity-slug> | DAS reconciliation cannot complete | das-tax-schedule.csv row N | YYYY-MM-DD | promotes line N from BLOCKED to CONFIRMED | user |

The user reads this section first thing each morning to know what to download today. Items >7 days old should be escalated (re-request, escalate to trustee, or change scope).

---

## Onboarding a new entity (when one is added)

1. Create `entities/<new-slug>/` with the full subfolder set
2. Copy `assets/templates/STATUS.md` to `entities/<new-slug>/STATUS.md`
3. Update slug in YAML frontmatter
4. Append entity to `MASTER_INDEX.md` (1 line: name, slug, status: NEW)
5. Log a decision: `field=entity_added`, `basis=corporate registry record on file`, `source_id` = the registry record's id

---

## Recovery from drift

If the AI starts asserting things that do not match the source files, run this prompt:

> "Stop. Read decisions.jsonl entries for <entity>. List what you believe is true. Flag any claim that is not sourced in those entries."

The AI must self-correct or reveal the gap. This is the anchor.
