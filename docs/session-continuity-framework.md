# Multi-Session Continuity for Forensic Accounting in Claude Code
**Research Date:** 2026-03-30
**Context:** Demo Restaurant Group forensic bookkeeping pipeline. 13,081 transactions, 223 files, 5 entities. CC reconciliation phase incoming (7 Excel files, Jan-Jul). Insolvency proceedings require defensible audit trail.

---

## 1. SESSION STATE MANAGEMENT

### The Problem You Already Hit
The the CC reconciliation project lost state between sessions. 1,347 transactions processed, $409K still unclassified, and the next session had no way to pick up where it left off. The forensic-bookkeeping project is better (SESSION_STATE.md exists), but it's manually maintained and drifts from reality.

### Recommended Format: Markdown + JSON Sidecar

**Markdown for humans (SESSION_STATE.md):**
- What was done, what's pending, key decisions
- Claude reads this at session start to orient
- You can scan it yourself in 30 seconds

**JSON for machines (session_checkpoint.json):**
- Exact counts, file hashes, processing status per file
- Claude can load this programmatically to verify state
- No ambiguity — numbers either match or they don't

**Why not YAML:** Extra dependency, no benefit over JSON for structured data. Claude parses both fine, but JSON has zero edge cases.

**Why not pure JSON:** You need to read this too. Markdown is scannable. JSON is verifiable. Use both.

### What Must Be Preserved

```
SESSION_STATE.md (human-readable)
├── Last updated timestamp
├── Pipeline version (V3.1, V4, etc.)
├── Phase: where we are in the overall workflow
├── Completed work summary (counts + totals)
├── Pending items (specific next steps, not vague)
├── Decisions made this session (with reasoning)
├── Rules established (classification rules, etc.)
├── Known issues / blockers
└── Verification checksums (total txns, total $, file count)

session_checkpoint.json (machine-readable)
├── version: schema version for the checkpoint itself
├── pipeline_version: "V3.1"
├── timestamp: ISO 8601
├── phase: "cc_reconciliation"
├── files_processed: { "filename.xlsx": { status, hash, txn_count, matched, unmatched } }
├── files_pending: [ list ]
├── rules: [ { pattern, classification, source_session, confirmed_by } ]
├── decisions: [ { question, answer, date, context } ]
├── running_totals: { matched, unmatched, verify, business, personal }
├── unmatched_queue: [ { txn_id, amount, date, description, suggested_match } ]
└── verification: { total_txns, total_amount, checksum }
```

### How to Avoid Re-Doing Work

Three mechanisms, layered:

**1. File-level tracking (coarse):** Each file gets a status in session_checkpoint.json: `pending`, `in_progress`, `completed`, `verified`. A new session checks this before touching any file.

**2. Transaction-level idempotency (fine):** Each transaction gets a deterministic ID: `hash(date + amount + description + source_file)`. If a txn_id already exists in the output, skip it. This is what your pipeline.py dedup logic already does for CSV vs PDF — extend it to CC reconciliation.

**3. Output fingerprinting (verification):** After each file is processed, compute a fingerprint of the output (row count + total amount). Store it. Next session compares. If the fingerprint matches, the file doesn't need reprocessing.

---

## 2. CHECKPOINT PATTERNS FOR THE CC RECONCILIATION PIPELINE

### Your Specific Case: 7 Excel Files (Jan-Jul)

Each month's Excel produces:
- Matched transactions (CC statement row linked to Excel row)
- Unmatched from CC (on statement, not in Excel — potential unreported expenses)
- Unmatched from Excel (in Excel, not on statement — potential fabrication)
- Rules learned (e.g., "<MERCHANT_STRING>" = "<Supplier_A>" in Excel)

### The Graduated Processing Model

```
For each file (Jan → Jul, in order):
  1. LOAD checkpoint — know what's done
  2. VERIFY inputs — file hash matches expected, row counts match
  3. PROCESS with current ruleset
  4. REPORT results — matched/unmatched counts
  5. LEARN rules — new patterns discovered this file
  6. ACCUMULATE unmatched — add to running "to review" list
  7. SAVE checkpoint — write state before moving to next file
  8. VERIFY checkpoint — re-read and confirm it wrote correctly
```

### Rule Propagation Across Files

This is the key insight: rules learned in January apply to February. The checkpoint must carry forward the evolving ruleset.

```json
{
  "rules": [
    {
      "id": "rule_001",
      "pattern": "<MERCHANT_STRING>",
      "maps_to": "Supplier Alpha",
      "classification": "BUSINESS",
      "subcategory": "supplier_food",
      "source": "January 2025 reconciliation",
      "learned_session": "2026-03-31T09:00:00",
      "confirmed_by": "owner_a",
      "confidence": "confirmed"
    },
    {
      "id": "rule_002",
      "pattern": "<EXAMPLE_SUPPLIER>",
      "maps_to": "<example_supplier> (Exterminateur)",
      "classification": "BUSINESS",
      "subcategory": "supplier_service",
      "source": "Owner_A verbal confirmation",
      "learned_session": "2026-03-31T10:30:00",
      "confirmed_by": "owner_a",
      "confidence": "confirmed"
    }
  ]
}
```

Rules have three confidence levels:
- **confirmed**: Owner_A said yes, this is correct. Never re-ask.
- **inferred**: Pattern matches an existing confirmed rule. Use it, but flag for review if the amount is unusual.
- **suggested**: First time seeing this pattern. Must ask Owner_A.

### Unmatched Accumulation Pattern

```json
{
  "unmatched_queue": [
    {
      "txn_id": "hash_abc123",
      "source": "cc_statement",
      "file": "January_2025.xlsx",
      "date": "2025-01-15",
      "amount": 347.50,
      "description": "UNKNOWN MERCHANT XYZ",
      "status": "unresolved",
      "suggested_match": null,
      "reviewed_by": null,
      "notes": ""
    }
  ],
  "unmatched_summary": {
    "total_count": 14,
    "total_amount": 3847.50,
    "by_month": { "2025-01": 3, "2025-02": 5, "2025-03": 6 },
    "by_status": { "unresolved": 10, "reviewed_personal": 2, "reviewed_business": 2 }
  }
}
```

Key: unmatched items from January might get resolved when February's data reveals a pattern. The queue is persistent and re-evaluated each month.

---

## 3. DECISION LOG

### The Problem
You told Claude that "<example_supplier> = exterminateur = business" in one session. Next session, Claude asks again. This wastes your time and erodes trust.

### Implementation: decisions.jsonl (Append-Only Log)

Use JSON Lines format (one JSON object per line, append-only). This is the format used by audit trail systems because:
- Append-only = no accidental overwrites
- One line per decision = easy to grep/search
- JSONL loads incrementally (no need to parse entire file)
- Git-friendly (each new decision is a clean diff line)

```jsonl
{"id":"d001","timestamp":"2026-03-31T09:15:00","question":"What is <example_supplier>?","answer":"Exterminateur — business expense, supplier_service","context":"CC classification session, Owner_A confirmed verbally","category":"classification_rule","reversible":true}
{"id":"d002","timestamp":"2026-03-31T09:20:00","question":"SAQ purchases under $300 — business or personal?","answer":"VERIFY — could be either. Flag for manual review.","context":"SAQ threshold discussion. Over $300 is definitely business (restaurant stock).","category":"classification_threshold","reversible":true}
{"id":"d003","timestamp":"2026-03-31T09:45:00","question":"How to handle Warehouse Club split between Lotus Kitchen and Siam House?","answer":"If single CC charge split across entities in the bookkeeper's Excel, match CC charge to the SUM of Excel rows. Track both entity assignments.","context":"Split transaction pattern found in January data","category":"reconciliation_method","reversible":true}
```

### Loading Decisions Into Session Context

At session start, the skill or SESSION_STATE.md should include:

```markdown
## Decisions Made (do not re-ask)
- <example_supplier> = exterminateur = BUSINESS (d001, 2026-03-31)
- SAQ < $300 = VERIFY, SAQ >= $300 = BUSINESS (d002, 2026-03-31)
- Warehouse Club splits: match CC to SUM of Excel rows (d003, 2026-03-31)
- [... max 20 most recent/relevant decisions ...]

Full log: ~/CEO/forensic-bookkeeping/decisions.jsonl (XX entries)
```

This gives Claude the top decisions in context without loading the entire log. If a question comes up that might be in the log, Claude checks the file first.

### Decision Categories

| Category | Example | Persistence |
|----------|---------|-------------|
| classification_rule | "X = business expense" | Permanent — goes into cc_classification.py rules |
| classification_threshold | "SAQ < $300 = verify" | Permanent — goes into rules with condition |
| reconciliation_method | "How to handle split txns" | Permanent — goes into RESEARCH doc |
| entity_assignment | "This account belongs to Lotus Kitchen" | Permanent — goes into account mapping |
| one_time_judgment | "Skip this file, it's a duplicate" | Session only — in decisions.jsonl but not in rules |
| correction | "Previous classification was wrong" | Permanent — updates the rule it corrects |

---

## 4. CLAUDE CODE ARCHITECTURE: WHERE STATE LIVES

### The Three-Layer Model

```
Layer 1: SKILL (reusable knowledge — permanent)
  ~/.claude/skills/forensic-bookkeeping/SKILL.md
  ~/.claude/skills/forensic-bookkeeping/context.json

  Contains: account mapping, transfer classification rules, entity list,
  pipeline file locations, critical bugs to not regress, legal context.

  Updated: when something is PROVEN and STABLE. Not every session.
  Think of this as the "constitution" — rarely amended.

Layer 2: MEMORY (project state — semi-permanent)
  ~/.claude/projects/-Users-Owner_A-CEO/memory/project_forensic_bookkeeping.md
  ~/.claude/projects/-Users-Owner_A-CEO/memory/feedback_reimbursement_vs_advance.md
  ~/.claude/projects/-Users-Owner_A-CEO/memory/feedback_file_verification.md
  ~/.claude/projects/-Users-Owner_A-CEO/memory/feedback_no_shortcuts_financial.md

  Contains: project overview, key learnings from past sessions,
  behavioral rules ("never trust filenames", "no shortcuts").

  Updated: when a session produces a reusable lesson. After each major
  milestone, add a memory entry.

Layer 3: SESSION STATE (work in progress — ephemeral)
  ~/CEO/forensic-bookkeeping/SESSION_STATE.md
  ~/CEO/forensic-bookkeeping/session_checkpoint.json
  ~/CEO/forensic-bookkeeping/decisions.jsonl

  Contains: exact current progress, pending items, running totals,
  unmatched queue, file processing status.

  Updated: every session, possibly multiple times per session.
  Think of this as the "working notebook."
```

### What Goes Where — Decision Matrix

| Information | Layer | Why |
|-------------|-------|-----|
| Account 0011001 = Lotus Kitchen | Skill | Permanent fact, used every run |
| "Never trust filenames" | Memory (feedback) | Behavioral rule, applies beyond this project |
| "Processed Jan-Mar, pending Apr-Jul" | Session State | Changes every session |
| "<example_supplier> = exterminateur" | Session State (decisions.jsonl) + Skill (once confirmed) | Starts as decision, graduates to rule |
| "13,081 total transactions" | Skill + Session State | Skill has the stable total, session state has current run's total |
| "RBC PDF parser bug: FORFAIT" | Skill (critical bugs section) | Must never regress — needs permanent visibility |
| Python venv path | Skill (context.json) | Infrastructure, rarely changes |
| "Next step: process April Excel" | Session State only | Ephemeral — will be outdated by next session |

### The Graduation Pattern

Information flows upward as it stabilizes:

```
Session observation → "<MERCHANT_STRING> matches <Supplier_A> in Excel"
    ↓ (confirmed by Owner_A)
Decision log entry → decisions.jsonl, d001
    ↓ (used successfully across 3+ files)
Classification rule → cc_classification.py BUSINESS_PATTERNS
    ↓ (stable across full pipeline run)
Skill knowledge → SKILL.md classification rules section
```

Never skip levels. A pattern observed once goes in the decision log, not the skill.

---

## 5. VERIFICATION CHECKPOINTS

### The "Trust But Verify" Protocol

Every new session must verify it's working with correct data before proceeding. This takes 30 seconds and prevents catastrophic errors (processing the wrong file, working from stale output, etc.).

### Session Start Verification Sequence

```python
# Pseudocode — what Claude should do at the start of every forensic session

def verify_session_state():
    # 1. Load checkpoint
    checkpoint = load_json("session_checkpoint.json")
    state = load_markdown("SESSION_STATE.md")

    # 2. Verify output files exist and match checkpoint
    for filename, expected in checkpoint["output_files"].items():
        actual_hash = hash_file(f"output/{filename}")
        actual_rows = count_rows(f"output/{filename}")
        assert actual_hash == expected["hash"], f"STALE: {filename} changed since last session"
        assert actual_rows == expected["row_count"], f"MISMATCH: {filename} has {actual_rows} rows, expected {expected['row_count']}"

    # 3. Verify source files haven't changed
    for filename, expected in checkpoint["source_files"].items():
        actual_hash = hash_file(filename)
        assert actual_hash == expected["hash"], f"SOURCE CHANGED: {filename} — reprocessing needed"

    # 4. Verify running totals
    master = load_csv("output/master_transactions.csv")
    assert len(master) == checkpoint["verification"]["total_txns"]
    assert sum_column(master, "debit") == checkpoint["verification"]["total_debits"]

    # 5. Report
    print(f"Session verified. Phase: {checkpoint['phase']}")
    print(f"Files processed: {checkpoint['files_completed']}/{checkpoint['files_total']}")
    print(f"Next step: {checkpoint['next_step']}")

    return checkpoint
```

### Verification Points in the Pipeline

| When | What to Verify | Action if Failed |
|------|---------------|-----------------|
| Session start | Output files match checkpoint | Re-run from last good checkpoint |
| Before processing a file | Source file hash matches expected | Flag — file may have been updated in Google Drive |
| After processing a file | Row count matches, debits/credits balance | Stop. Do not proceed to next file. |
| After all files | Grand totals match sum of per-file totals | Reconciliation error — investigate |
| Session end | Checkpoint written successfully | Re-write. If still fails, alert. |

### The "Canary" Check

Before doing any real work, process one already-completed file and verify the output matches what's stored. This catches:
- Environment changes (Python version, library update)
- Parser regressions (someone edited pipeline.py)
- Data corruption (Google Drive sync issues)

```bash
# Quick canary: re-parse one known file, compare output
python -c "
from pipeline import parse_file
r = parse_file('path/to/known_file.csv')
assert len(r.transactions) == 47  # expected from checkpoint
assert sum(t.debit or 0 for t in r.transactions) == 12345.67  # expected total
print('Canary passed')
"
```

---

## 6. PRACTICAL IMPLEMENTATION PLAN

### For the CC Reconciliation Phase (Next Work)

**Step 1: Create session_checkpoint.json** (before starting)
```json
{
  "schema_version": 1,
  "pipeline_version": "V4_cc_reconciliation",
  "phase": "cc_reconciliation",
  "timestamp": null,
  "source_files": {
    "cc_reconciliation_january.xlsx": { "status": "pending", "hash": null },
    "cc_reconciliation_february.xlsx": { "status": "pending", "hash": null },
    "cc_reconciliation_march.xlsx": { "status": "pending", "hash": null },
    "cc_reconciliation_april.xlsx": { "status": "pending", "hash": null },
    "cc_reconciliation_may.xlsx": { "status": "pending", "hash": null },
    "cc_reconciliation_june.xlsx": { "status": "pending", "hash": null },
    "cc_reconciliation_july.xlsx": { "status": "pending", "hash": null }
  },
  "rules": [],
  "decisions": [],
  "unmatched_queue": [],
  "running_totals": {
    "matched_exact": 0,
    "matched_fuzzy": 0,
    "unmatched_cc": 0,
    "unmatched_excel": 0,
    "classified_business": 0,
    "classified_personal": 0,
    "classified_verify": 0
  },
  "verification": {
    "total_txns_processed": 0,
    "total_amount_processed": 0
  },
  "next_step": "Process January 2025"
}
```

**Step 2: Process one file per session** (or batch if rules are stable)
- Load checkpoint
- Verify state
- Process next pending file
- Interactive: ask Owner_A about unknowns
- Save decisions
- Update checkpoint
- Update SESSION_STATE.md

**Step 3: After all 7 files, consolidation session**
- Re-run with full ruleset to catch patterns that span months
- Resolve remaining unmatched queue
- Generate final report
- Graduate stable rules to cc_classification.py and SKILL.md

### File Structure After Implementation

```
~/CEO/forensic-bookkeeping/
  SESSION_STATE.md              ← human-readable current state
  session_checkpoint.json       ← machine-readable checkpoint
  decisions.jsonl               ← append-only decision log
  cc_classification.py          ← confirmed classification rules (code)
  cc_reconciliation.py          ← new: CC statement vs Excel matcher
  pipeline.py                   ← existing bank statement pipeline
  reconciliation.py             ← existing inter-company reconciliation
  output/
    master_transactions.csv     ← existing
    cc_reconciliation_january.csv  ← new: per-month results
    cc_reconciliation_february.csv
    ...
    cc_unmatched_queue.csv      ← running unmatched list
    cc_reconciliation_summary.md ← final consolidated report
```

---

## 7. ANTI-PATTERNS TO AVOID

1. **Storing state only in CLAUDE.md or memory**: These are loaded into context but can't be programmatically verified. Use them for orientation, not as source of truth for numbers.

2. **Monolithic state file**: A single 500-line SESSION_STATE.md becomes unreadable. Split: human summary (SESSION_STATE.md) + machine state (session_checkpoint.json) + decisions (decisions.jsonl).

3. **Re-asking confirmed decisions**: If Owner_A said "<example_supplier> = exterminateur" once, that's a permanent rule. Load decisions.jsonl and check before asking anything.

4. **Processing files out of order**: Rules propagate January to July. If you process April before February, February can't benefit from April's rules. Always process sequentially for the first pass.

5. **Updating the skill mid-session**: The skill file should only be updated after a session produces verified, stable results. Never update it during exploratory work.

6. **Trusting filenames without verification**: Already a known feedback item. Extend to CC files: verify the file's internal dates match the expected month.

7. **No canary check**: Starting work without verifying the environment matches expectations. Always run one known-good file first.

---

## Sources

- [Claude Code Common Workflows](https://code.claude.com/docs/en/common-workflows)
- [Claude Code Memory Architecture](https://code.claude.com/docs/en/memory)
- [Claude Code Task Management: Native Multi-Session AI](https://claudefa.st/blog/guide/development/task-management)
- [Multi-Session Task Coordination — Claude Code Ultimate Guide](https://deepwiki.com/FlorianBruniaux/claude-code-ultimate-guide/8.4-history-commands)
- [Claude Code Session Management Guide](https://claudelab.net/en/articles/claude-code/claude-code-session-management-resume-guide)
- [Claude Code Best Practices: Creator's 100-Line Workflow](https://mindwiredai.com/2026/03/25/claude-code-creator-workflow-claudemd/)
- [Claude Code Context Management — Long-Running Sessions](https://www.sitepoint.com/claude-code-context-management/)
- [Checkpointing — Dagster Glossary](https://dagster.io/glossary/checkpointing)
- [Idempotency in Data Pipelines — Airbyte](https://airbyte.com/data-engineering-resources/idempotency-in-data-pipelines)
- [Idempotent Data Pipelines for Resilience — Prefect](https://www.prefect.io/blog/the-importance-of-idempotent-data-pipelines-for-resilience)
- [Checkpoint/Restore Systems: Applications in AI Agents — Eunomia](https://eunomia.dev/blog/2025/05/11/checkpointrestore-systems-evolution-techniques-and-applications-in-ai-agents/)
- [LangGraph Persistence with Checkpointer — Couchbase](https://developer.couchbase.com/tutorial-langgraph-persistence-checkpoint/)
- [Debugging LLM Agents with Checkpoint-Based State Replay](https://dev.to/sreeni5018/debugging-non-deterministic-llm-agents-implementing-checkpoint-based-state-replay-with-langgraph-5171)
- [Audit Trail — Wikipedia](https://en.wikipedia.org/wiki/Audit_trail)
- [Valid8 Financial — Forensic Accounting Software](https://www.valid8financial.com/solutions/accounting)
- [Claude Code Session Memory — Automatic Cross-Session Context](https://claudefa.st/blog/guide/mechanics/session-memory)
- [Claude Code Tasks vs Todos — 2026](https://claudearchitect.com/docs/claude-code/claude-code-tasks-vs-todos/)
