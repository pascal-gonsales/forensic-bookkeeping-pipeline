# Changelog

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
