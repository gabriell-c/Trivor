# Debug: PDF Order & Markdown Artifacts

## Session ID
`pdf-order-markdown-artifacts`

## Bug Description
After the column-order fix (commit 8cb4803), two new issues appeared:
1. `##` symbols appearing inside bullet points (e.g. `## Atuação em telemarketing de cobrança ativa e receptiva`)
2. Items being placed in wrong sections by the markdown converter
3. Capitalization artifacts — OCR/text extraction causing false "errors"

## Root Cause Hypothesis
The `_text_to_markdown()` function has overly broad section header patterns.
Patterns like `r'^ATUAÇÃO'` and `r'^ATUACAO'` match **any line starting with those words**,
including bullet-point content like "Atuação em telemarketing..." which should NOT be a header.

## Evidence
- User confirmed: raw PDF→MD conversion (without the custom `_text_to_markdown`) works fine
- The LLM prompt itself has rules about OCR tolerance (section 2)
- The `##` artifact only appears when `_text_to_markdown` runs, not in raw extraction

## Hypotheses
1. **PRIMARY**: `_text_to_markdown()` section patterns are too broad — they match descriptive text lines, not just section headers
2. **SECONDARY**: PyMuPDF `get_text("blocks")` preserves original PDF capitalization which may differ from visual rendering (OCR artifact)
3. The column-interleaving in `_extract_pdf_text_pymupdf()` may produce lines that look like headers but aren't

## Fix Applied
- Changed all SECTION_PATTERNS to use `$` (exact match) instead of prefix match
- Added `len(stripped) <= 40` gate before header detection
- This prevents bullets like "Atuação em telemarketing de cobrança ativa e receptiva" from being treated as headers
- Tested on all 9 PDFs in `docs/`: zero false positives, all real headers correctly detected

## Verification
- `_test_markdown_fix.py`: 24/24 cases passed (8 bullet lines + 16 real headers)
- `_test_order_fix.py`: order preservation confirmed ✅
- `_test_real_pdfs.py`: all 9 real PDFs processed, zero `##` artifacts on long lines ✅

## Commits
- `72342c8` fix: strict section header detection to prevent false positives in _text_to_markdown
- `8cb4803` fix: preserve PDF text order in column layouts and markdown conversion (previous session)


## Files to Modify
- `backend/main.py` — `_text_to_markdown()` function only
