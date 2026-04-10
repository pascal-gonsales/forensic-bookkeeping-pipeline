# PDF Bank Statement Extraction — Research Report
**Date:** 2026-03-30
**Context:** Forensic bookkeeping for Demo Restaurant Group
**Banks:** Desjardins + RBC Royal Bank (Canadian, French-language PDFs)
**Current approach:** pdfplumber `extract_text()` + regex → ~85% accuracy
**Target:** 99%+ accuracy on amounts and debit/credit classification

---

## 1. Python Library Comparison

### pdfplumber (CURRENT — best choice for this use case)
- **Strengths:** Character-level access (`.chars`), word-level access (`.extract_words()` with x/y coordinates), table extraction (`.extract_tables()`), page cropping, visual debugging (`.to_image()`). Works directly on machine-generated PDFs. Best for complex borderless tables.
- **Weaknesses:** Cannot auto-detect tables like Camelot/Tabula. Requires manual tuning of tolerance parameters. No OCR built-in (needs Tesseract for scanned docs).
- **Verdict:** KEEP. It is the right library. The problem is we're using the wrong extraction method (`extract_text()` instead of `extract_words()`).

### Camelot
- **Strengths:** Best for tables with clear ruled lines (Lattice mode). Better than Tabula for line-bordered tables. Good auto-detection.
- **Weaknesses:** Requires Ghostscript dependency. Lattice mode needs visible grid lines (bank statements rarely have these). Stream mode is less accurate than pdfplumber's word-level approach.
- **Verdict:** NOT recommended. Bank statements have borderless tables — Camelot's strength is ruled tables.

### tabula-py
- **Strengths:** Easy to use, good auto-detection in Stream mode.
- **Weaknesses:** Requires Java runtime. Less accurate than Camelot for structured tables. Struggles with multi-page tables, merged cells, sub-totals. Cannot handle French accented characters as well.
- **Verdict:** NOT recommended for this use case.

### PyMuPDF (fitz)
- **Strengths:** Fastest library. Good `get_text("dict")` mode returns structured data with fonts, coordinates, and layout. New PyMuPDF4LLM extension for structured extraction.
- **Weaknesses:** Teams "typically migrate away from PyMuPDF when encountering accuracy requirements for financial or legal documents." Struggles with random character artifacts, misaligned columns, and lost table structures.
- **Verdict:** NOT recommended for forensic accuracy.

### pdfminer
- **Strengths:** Low-level access to PDF internals. Already installed (pdfplumber uses it under the hood).
- **Weaknesses:** More complex API. No table extraction. Essentially what pdfplumber wraps with a nicer interface.
- **Verdict:** No advantage over pdfplumber.

---

## 2. The extract_words() Approach — RECOMMENDED UPGRADE

### Current Problem
`extract_text()` concatenates all characters into lines with heuristic spacing. For RBC PDFs, this produces compressed text like "Paiementdivers5250,0023847,93" where description, amount, and balance merge together. Regex then fights to separate them.

### Solution: extract_words() with coordinate-based column detection
```python
words = page.extract_words(
    x_tolerance=3,        # Max gap between chars to form a word
    y_tolerance=3,        # Max vertical gap for same line
    keep_blank_chars=False,
    use_text_flow=False,
    extra_attrs=["fontname", "size"]  # Include font info for section detection
)
```

Each word comes with: `{'text': '5250,00', 'x0': 420.5, 'x1': 465.2, 'top': 312.1, 'bottom': 322.1}`

### How to reconstruct columns:
1. **Sample first page** to find column boundaries (date, description, debit, credit, balance) by looking at header word positions
2. **Group words by row** using y-coordinate proximity (same `top` value within tolerance)
3. **Assign words to columns** based on x-coordinate ranges
4. **This eliminates the compression problem entirely** — "Paiementdivers" and "5250,00" become separate words in separate columns

### Why this is better:
- No more regex guessing where description ends and amounts begin
- Debit vs Credit column is determined by x-position, not heuristics
- Balance column is always rightmost — positional, not last-regex-match
- Works even when RBC compresses spaces between characters

### pdfplumber table_settings for borderless tables:
```python
table_settings = {
    "vertical_strategy": "text",     # Use word alignment, not lines
    "horizontal_strategy": "text",   # Use word tops, not lines
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "edge_min_length": 10,
    "text_x_tolerance": 3,
    "text_y_tolerance": 3,
}
tables = page.extract_tables(table_settings)
```

For maximum control, use `"vertical_strategy": "explicit"` with `"explicit_vertical_lines"` set to the column boundaries you detect from the header row.

---

## 3. Character-Level Extraction (Nuclear Option)

If `extract_words()` still fails on RBC's compressed text, go one level deeper:

```python
chars = page.chars  # Every single character with position
# Each char: {'text': '5', 'x0': 420.5, 'fontname': 'ArialMT', 'size': 8.0, ...}
```

This gives absolute control. You can:
- Detect column boundaries from header characters
- Group characters by y-position into rows
- Group characters by x-position into columns
- Reconstruct words manually with proper spacing

This is the most reliable approach for PDFs with garbled/compressed text extraction.

---

## 4. Dedicated Bank Statement Parsing Tools

### Open Source (GitHub)

| Tool | Banks | Method | Status | URL |
|------|-------|--------|--------|-----|
| **Teller** | RBC, TD, BMO, Manulife, AMEX | pdfplumber + regex | Inactive (last commit Oct 2021, 66 stars) | github.com/Bizzaro/Teller |
| **rbc-statement-parser** | RBC (Visa + chequing/savings) | Python, active | Active (v1.0.2, Mar 2026) | github.com/andrewscwei/rbc-statement-parser |
| **pdf-statement-reader** | Generic (config-based) | YAML config + regex | Moderate | pypi.org/project/pdf-statement-reader/ |
| **bank-statement-parser** | European banks (hledger) | Custom parsers | Active | github.com/felgru/bank-statement-parser |

**No Desjardins-specific parser exists on GitHub.**

The **Teller** project validates the same approach we're using (pdfplumber + regex) and confirms the fundamental limitation: "we can never have 100% correct bank statement regex since the bank changes its formats slightly between statements." This is exactly why the word-level approach is superior.

### Commercial SaaS

| Tool | Accuracy Claim | Price | Best For |
|------|---------------|-------|----------|
| **DocuClipper** | 99.5% OCR | $39-159/mo | General accounting, bulk conversion |
| **Valid8 Financial** | Not published | ~$5,000+/mo enterprise | Purpose-built forensic accounting |
| **Veryfi API** | 99.8% | Pay-per-use | API integration, high volume |
| **BankRead** | Not published | Not published | Canadian bank support claimed |
| **MoneyThumb (PDF2CSV)** | Not published | $25-100/mo | Desktop conversion tool |
| **Parseur** | Not published | Varies | Template-based extraction |
| **CounselPro** | Not published | Not published | Forensic accounting, 10K+ institutions |

**For 150 PDFs, commercial tools are overkill.** The monthly cost exceeds the one-time effort of fixing the parser.

---

## 5. Commercial Cloud APIs

### AWS Textract
- **AnalyzeLending:** Auto-classifies bank statements, tax forms. $7/1,000 pages.
- **Tables:** $15/1,000 pages for table extraction.
- **For 150 PDFs (~600 pages):** ~$4-9 total cost.
- **Accuracy:** 94.2% overall, 82% for line-item detection.
- **Limitation:** US-focused. No specific Canadian bank template. No French-language bank statement model.

### Google Document AI
- **Bank Statement Parser:** Pre-trained model, extracts 17+ entity types.
- **Price:** $0.75/document (classified), $30/1,000 pages for form parsing.
- **For 150 PDFs:** ~$112 at document level, or ~$18 at page level.
- **Accuracy:** 95.8% overall.
- **Limitation:** Pre-trained model may not handle French Canadian bank formats. Fine-tuning possible with 10+ labeled documents.

### Azure Document Intelligence
- **Bank Statement Model:** `prebuilt-bankStatement.us` — extracts account number, bank details, transaction details, fees.
- **Price:** ~$10/1,000 pages. Free tier available (F0).
- **For 150 PDFs (~600 pages):** ~$6 total.
- **CRITICAL LIMITATION:** Model ID is `prebuilt-bankStatement.us` — **US bank statements only.** Canadian French-language PDFs are not supported by the pre-built model.

### Verdict on Cloud APIs
- **Cost is minimal** (~$5-20 for 150 PDFs) but **accuracy for Canadian French-language bank statements is unproven**.
- Would require testing with sample PDFs before committing.
- **Not recommended as primary approach** — better to fix the pdfplumber parser which already handles the French format.
- **Could be useful as validation layer** — run both custom parser and API, compare results.

---

## 6. OCR-Based Approaches

### When OCR is needed:
- Scanned PDFs (image-only, no selectable text)
- Your Desjardins/RBC PDFs are **machine-generated with embedded text** — OCR is NOT needed

### For RBC's compressed text problem:
The issue isn't OCR — the text IS extractable. The problem is that `extract_text()` doesn't preserve column positions. Using `extract_words()` or `chars` solves this without OCR overhead.

### If OCR were needed:
- **Tesseract + pytesseract:** Convert PDF page to 300 DPI image, preprocess (grayscale, contrast), OCR. Accuracy depends heavily on image quality.
- **pdfplumber has Tesseract integration** for scanned pages.
- Not recommended for your PDFs since they already have embedded text.

---

## 7. LLM-Based Approaches (Emerging)

### How it works:
1. Extract raw text from PDF (PyPDF2 or pdfplumber)
2. Send text to LLM (Gemini, GPT-4) with structured JSON schema
3. LLM returns parsed transactions

### Performance:
- 95% success rate across 8 different banks (one study)
- Cost: ~$0.01/statement
- Development: 30 minutes vs 20+ hours for regex parsers

### For forensic accounting: NOT ACCEPTABLE
- 95% is 5% error rate — completely unacceptable for forensic work
- No audit trail
- No deterministic reproducibility (same input can give different output)
- Cannot be defended in court or to creditors
- Hallucination risk on amounts is catastrophic

### Potential use: VOWNER_BDATION ONLY
- Run LLM as second-pass validator to flag discrepancies
- Human reviews only the flagged items
- Never use LLM output as primary data source

---

## 8. RECOMMENDATION: Implementation Plan

### Priority 1: Upgrade RBC parser to extract_words() approach

The RBC parser currently fights compressed text. The fix:

```python
def parse_rbc_pdf_v2(file_path: str) -> ParseResult:
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=3, y_tolerance=3)

            # Step 1: Find column boundaries from header row
            # Look for words like "Date", "Description", "Retrait", "Dépôt", "Solde"
            header_words = [w for w in words if w['top'] < 100]  # adjust

            # Step 2: Define column ranges
            # date_col: x0 < 100
            # desc_col: 100 < x0 < 350
            # debit_col: 350 < x0 < 430
            # credit_col: 430 < x0 < 510
            # balance_col: x0 > 510

            # Step 3: Group words by row (same y-position)
            rows = group_by_y(words, tolerance=3)

            # Step 4: For each row, assign words to columns by x-position
            for row in rows:
                date = get_column_text(row, date_range)
                desc = get_column_text(row, desc_range)
                debit = get_column_text(row, debit_range)
                credit = get_column_text(row, credit_range)
                balance = get_column_text(row, balance_range)
```

**Expected improvement:** 85% → 98%+ accuracy. Debit/credit classification becomes deterministic (column position) instead of heuristic (keyword matching).

### Priority 2: Add balance reconciliation validation

After parsing, verify every transaction:
```
expected_balance = previous_balance - debit + credit
if abs(expected_balance - actual_balance) > 0.01:
    FLAG for manual review
```

This catches the remaining 1-2% errors.

### Priority 3: Visual debugging with pdfplumber

```python
im = page.to_image(resolution=150)
im.draw_rects(page.extract_words())  # See exactly what pdfplumber extracts
im.save("debug_page_1.png")
```

This lets you see exactly where column boundaries are and verify extraction.

### Priority 4 (Optional): Cloud API validation pass

Run 10 sample PDFs through Google Document AI ($0.75 each = $7.50) to compare results with your parser. Use discrepancies to find remaining parser bugs.

---

## Sources

### Library Comparisons
- [Best Python Libraries to Extract Tables From PDF (Unstract)](https://unstract.com/blog/extract-tables-from-pdf-python/)
- [Camelot vs Other Libraries (GitHub Wiki)](https://github.com/camelot-dev/camelot/wiki/Comparison-with-other-PDF-Table-Extraction-libraries-and-tools)
- [How to Extract Data from Bank Statements: 3 Methods (CapyParse)](https://capyparse.com/blog/extract-data-from-bank-statements)

### pdfplumber Deep Dives
- [pdfplumber GitHub Repository](https://github.com/jsvine/pdfplumber)
- [Fine-tuning tables with pdfplumber (Medium)](https://medium.com/@heinburgmans/fine-tuning-tables-before-extracting-with-python-pdfplumber-4bfedc264bfc)
- [pdfplumber Guide (Unstract)](https://unstract.com/blog/guide-to-pdfplumber-text-and-table-extraction-capabilities/)
- [pdfplumber table extraction settings (GitHub Discussion #1071)](https://github.com/jsvine/pdfplumber/discussions/1071)
- [x_tolerance fractional arguments (GitHub Issue #987)](https://github.com/jsvine/pdfplumber/issues/987)

### Canadian Bank Parsers
- [Teller — Canadian Bank PDF Parser (GitHub)](https://github.com/Bizzaro/Teller)
- [RBC Statement Parser (GitHub)](https://github.com/andrewscwei/rbc-statement-parser)
- [bank-statement-parser topic (GitHub)](https://github.com/topics/bank-statement-parser)

### Commercial APIs
- [AWS Textract Pricing](https://aws.amazon.com/textract/pricing/)
- [Azure Document Intelligence — Bank Statement US Model](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/bank-statement?view=doc-intel-4.0.0)
- [Google Document AI](https://cloud.google.com/document-ai)
- [Google Document AI Pricing](https://cloud.google.com/document-ai/pricing)

### Commercial SaaS Tools
- [10 Best Bank Statement Extraction Software (DocuClipper)](https://www.docuclipper.com/blog/best-bank-statement-extraction-software/)
- [Valid8 Financial — Forensic Accounting Software](https://www.valid8financial.com/)
- [Veryfi Bank Statements OCR API](https://www.veryfi.com/bank-statements-ocr-api/)

### LLM Approaches
- [Stop Writing Bank Statement Parsers — Use LLMs Instead (Medium)](https://medium.com/@mahmudulhoque/stop-writing-bank-statement-parsers-use-llms-instead-50902360a604)
- [Automated Bank Statement Analysis Using GPT + Langchain](https://www.reveation.io/blog/automated-bank-statement-analysis)

### OCR
- [PDF Text Extraction While Preserving Whitespaces (Towards Data Science)](https://towardsdatascience.com/pdf-text-extraction-while-preserving-whitespaces-using-python-and-pytesseract-ec142743e805/)
- [Extracting Data from Bank Statements using TrOcr & Detectron 2](https://www.indium.tech/blog/extracting-data-from-digital-and-scanned-bank-statements-using-trocr-detectron-2-part-1/)
