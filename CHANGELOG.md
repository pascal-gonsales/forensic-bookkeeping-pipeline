# Changelog

## [v1.2.0] — 2026-04-28 (Skill v1.2 published + anonymization fix + scripts hardening)

Two changes ship in this release:

### 1. Forensic-bookkeeping Skill v1.2 published into this repo (`/skill/`)

The skill is the meta-instructions for how Claude operates this pipeline. It was
previously local-only at `~/.claude/skills/forensic-bookkeeping/` (Claude Code
skills directory). It is now public alongside the pipeline so any reader can see
the operating contract: anti-drift rules, source-traceability requirements,
NEEDS_REVIEW default, routing boundaries, and the per-entity STATUS architecture.

- `skill/SKILL.md` — main skill definition (anti-drift, anonymity, hard rules)
- `skill/references/` — 6 deep-dive guides (architecture, confidence/sourcing,
  output schemas, pipeline-technical, routing-boundaries, workflow-checklists)
- `skill/assets/templates/` — 10 working templates (STATUS, FORENSIC_STATUS,
  STANDUP, creditor schedule, employee claims, DAS schedule, source registry,
  trustee briefing, decision-entry jsonl, etc.)

Legacy v3.2 reference files (`legacy/` in the local skill dir) are intentionally
NOT included — they retain real names from the original case and are not the
v1.2 entry point.

### 2. Anonymization fix — `pipeline.py` trustee name no longer hard-coded

`pipeline.py` previously had a hardcoded trustee name in `CATEGORY_RULES` (a
debtor-specific identifier from the original case). v1.2 replaces it with an
optional `TRUSTEE_NAME` env-var pattern:

- OSS distribution default: no trustee-name rule registered (still catches
  generic "trustee|syndic" mentions via the standing rule).
- Local working copy: set `TRUSTEE_NAME=<name>` in `~/.config/wwithai/credentials.env`
  or shell env to register a debtor-specific rule at runtime.

This aligns the pipeline with the skill v1.2 anonymity contract: "must not name
any specific person, firm, or restaurant" in shared distribution.

### 3. Scripts hardening (continuation of v1.1.0 anti-drift work)

- `scripts/source_registry.py` — incremental hardening (validation, error paths)
- `scripts/validate_package.py` — strict/handoff modes, broader template/package
  validation, integration with v1.2 confidence-status conventions
- `tests/synthetic/` — synthetic-data test cases for validation gate (no real
  bank statements, safe to run on any clone)

### Migration note for existing users

Set `TRUSTEE_NAME` in your local env if you were relying on the hardcoded rule.
Without it, generic "trustee" / "syndic" strings still match — only the named
fallback rule is gone.

---

## [v1.1.0] — 2026-04-26 (Anti-drift hardening + standardized statuses)

Response to external code audit. Aligns the pipeline with the v1.1 forensic-bookkeeping
skill (rules, statuses, source registry, validate gate).

### Behavior changes (anti-drift, may affect existing classifications)

- **`cc_classification.py` SAQ rule alignment**: docstring corrected to match
  code behavior. SAQ <$300 = PERSONAL (CONFIRMED, debtor decision logged
  2026-04-02), SAQ >=$300 = BUSINESS (same source). Both now carry an explicit
  `source` note in the result dict.
- **`cc_classification.py` team-building auto-50% removed**: the pipeline no
  longer auto-computes a 50% business split for partner-trip merchants. Auto-
  computed splits without source confirmation were producing unsupported
  amounts. Output now: `business_amount: None`, `status: NEEDS_REVIEW`,
  user must supply the actual split via `decisions.jsonl`.
- **Default fallback: NEEDS_REVIEW (was VERIFY)**: unrecognized merchants
  return status `NEEDS_REVIEW` instead of legacy `VERIFY`. Aligns to skill v1.1
  standardized statuses (CONFIRMED / INFERRED / NEEDS_REVIEW / BLOCKED).
- **`status` field added to every classification output** and to the
  `cc_personal_classified.csv` columns. Status is one of the 4 standard values.
- **Summary report distinguishes business vs pending_user_input**: amounts in
  NEEDS_REVIEW are no longer counted as 0 business; they appear under a separate
  `pending_user_input` line so reviewers see what's awaiting human classification.

### New scripts

- **`scripts/source_registry.py`** — scans a working directory for source
  documents (PDF, CSV, XLSX), computes SHA256 per file, writes
  `source_registry.json` with metadata (entity, domain, first_seen,
  last_verified). Re-runs detect hash changes and flag them as alerts. This
  anchors decisions.jsonl source citations to a verifiable file state.
- **`scripts/validate_package.py`** — pre-flight validator that runs before
  delivering a trustee package. Checks: (a) every CSV row has non-empty source,
  (b) no row uses forbidden status (legacy VERIFY/TBD/MAYBE), (c) cited source
  files exist on disk, (d) referenced entities have folders. Exits 0 if package
  is ready, 1 if validation fails.

### Reference

This release implements the P0/P1 fixes from the external Codex audit:
- P0 standardized statuses (CONFIRMED/INFERRED/NEEDS_REVIEW/BLOCKED) — done
- P0 source traceability via SHA256 registry — done (source_registry.py)
- P1 SAQ classification drift — done (docstring/code aligned + source note)
- P1 auto-50% team-building unsupported amount — done (removed)
- P1 durable validation gate — done (validate_package.py)

Out-of-scope for v1.1 (deferred to v2.0):
- Synthetic CI fixtures for messy cases (P2)
- ChatGPT Skill format (`agents/openai.yaml`)
- Claude Code SessionStart/Stop hooks integration

## [v1.0.0] — 2026-04-26 (Production release)
- Trustee-defensible forensic bookkeeping pipeline.
- 7 PDF formats supported: Desjardins (bank/business CC/personal Visa),
  RBC (bank/Visa), BDC Mastercard, TD Aeroplan Visa.
- Categorization rate increased to 92%+ (was 86.8%).
- Inter-company match rate: 98% (610/624 pairs).
- 100% source traceability via append-only `decisions.jsonl` and SHA256 checksums.
- Public repo is now self-contained — `pdf_parsers.py` (v1) dependency removed.
- CI: GitHub Actions workflow runs `python test_parsers.py` on push/PR.

## [v3.4-classification] — 2026-04-26
- 22 new regex rules added to pipeline `CATEGORY_RULES`:
  cash advances, bank fees variants, pre-authorized payments, Facebook ads,
  AccèsD bill payments, Eureka & Fi loan, accountant payments, AMEX,
  Supa Pho, Peacock, Epidemic Sound, Moneris, BNI, Dollarama, etc.
- New `no_description` category replaces silent uncategorization for blank
  descriptions (data quality flag, not estimation).
- Known data gaps explicitly acknowledged in `decisions.jsonl`.

## [v3.3-parsers] — 2026-04-26
- `detect_pdf_format` moved into `pdf_parsers_v2` (v1 dependency removed).
- Three additional formats wired into pipeline dispatch:
  `bdc_mc_pdf`, `td_visa_pdf`, `desj_visa_perso_pdf`.
- Test suite extended: smoke test for imports + 3 PDF tests with
  skip-if-fixture-missing semantics.
- GitHub Actions workflow added.

## [v3.2-sync] — 2026-04-26
- Initial production sync from working tree (V3.2).
- Full PII anonymization audit: 6 production files, 0 leaks.
- Fixed 5 pre-existing sanitization bugs from v3.1:
  ALIGN/VALIGN restored (ReportLab broke), ALIMENTAIRE/ALIMENTS regex restored,
  one stray entity-name leak in the report file fixed.
- `generate_pdf_report.py` removed from public repo
  (contained sensitive financial detail).
- Added `.gitignore` covering generated artifacts and local-only files.

## [v3.1] — 2026-04-09 (initial commit)
- 13,081 transactions, 5 entities, 2 years of forensic data.
- Inter-company reconciliation with bidirectional matching (98% match rate).
- CC personal classification: $640K business identified, $33K flagged.
- Coordinate-based PDF extraction at 99% accuracy.
