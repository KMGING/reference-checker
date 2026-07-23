---
name: ieee-reference-checker
description: Check, diagnose, and safely repair IEEE Transactions references using the bundled local IEEE Reference Style Guide and IEEE journal-title XLSX. Use for complete .bib files, bib.tex files, LaTeX thebibliography/\\bibitem files, or pasted BibTeX, bibitem, and plain-text references; trigger on requests to check or fix BibTeX/IEEE formatting, journal or ACM/USENIX/NDSS venue abbreviations, required fields, DOI/pages/article numbers, title casing, authors, duplicates, or arXiv-versus-formal versions. Support check-only, suggestions, separate fixed copies, one citation key, venue-only/missing-field-only checks, and explicit in-place edits with backup.
---

# IEEE Reference Checker

Use deterministic scripts and bundled local reference data. Never infer an official IEEE journal abbreviation when the XLSX has no match, and never invent DOI, author, pages, volume, issue, year, article number, publisher, or conference ordinal.

## Required local references

Require these files under `references/`:

- `IEEE_Reference_Style_Guide_for_Authors.docx` or a text-layer `IEEE_Reference_Style_Guide_for_Authors.pdf`
- `List_of_IEEE_Journal_Magazine_Titles_Internal_Acronym_and_Reference_Abbreviation.xlsx`

Use `data/ieee_journal_abbreviations.json`, `data/ieee_word_abbreviations.json`, and `data/rule_sources.json` at runtime. Rebuild them when missing or older than either local reference. Read `README.md` when installation, update, CLI, or limitation details are needed.

## Source priority

Resolve conflicts in this order:

1. User-specified target IEEE Transactions requirements.
2. Bundled latest IEEE Reference Style Guide.
3. Bundled IEEE journal-title XLSX for exact IEEE reference abbreviations.
4. Actual project use of IEEEtran, IEEEabrv, and local bibliography conventions.
5. Publisher/proceedings metadata used only for fact verification.
6. Existing consistent project formatting.
7. Model knowledge used only to request manual review.

## Workflow

1. Detect BibTeX, `thebibliography`/`\bibitem`, or plain text from content rather than extension.
2. Check rule-database existence and freshness; rebuild with `scripts/build_rule_database.py` if necessary.
3. Parse for diagnostics without reserializing the entire file.
4. Check syntax, entry type, required/recommended fields, authors, title protection, DOI, pages/article numbers, dates, URLs, arXiv status, and duplicates.
5. Match IEEE journals against XLSX full titles, inverted workbook titles, internal acronyms, official abbreviations, and supported IEEEabrv macro names.
6. Normalize non-IEEE venues only with extracted word rules and verified `data/venue_exceptions.yml`; retain uncovered words and request review.
7. Classify every finding as `SAFE_FIX`, `SUGGESTED_FIX`, or `MANUAL_REVIEW`, with `ERROR`, `WARNING`, or `INFO` severity and a stable rule ID.
8. Generate Markdown and JSON reports. Apply only `SAFE_FIX` patches when producing a fixed copy.
9. Preserve citation keys, entry/field order, comments, custom fields, indentation, LaTeX commands, encoding, and original file.
10. Reparse the fixed result and rerun the selected checks. Require zero remaining `SAFE_FIX` changes before delivery.
11. Query Crossref only when the user opts into `--verify-online`; record the URL/provider and never auto-apply returned metadata.

## Commands

Run from the skill directory:

```bash
python scripts/build_rule_database.py \
  --guide references/IEEE_Reference_Style_Guide_for_Authors.docx \
  --journals references/List_of_IEEE_Journal_Magazine_Titles_Internal_Acronym_and_Reference_Abbreviation.xlsx

python scripts/check_bibliography.py ref.bib --check-only
python scripts/check_bibliography.py ref.bib --fix
python scripts/check_bibliography.py ref.bib --fix --in-place
python scripts/check_bibliography.py ref.bib --key carlini2021extracting
python scripts/check_bibliography.py ref.bib --only venue
python scripts/check_single_entry.py --stdin
python scripts/verify_fixed_bib.py ref.ieee-fixed.bib
```

Default file mode is non-destructive: write reports and a separate fixed copy. `--check-only` suppresses the fixed copy. Permit `--in-place` only with explicit `--fix`; create `FILE.bak` first and refuse to overwrite an existing backup.

## Input handling

- Treat `.tex` dominated by `@article`, `@inproceedings`, and similar entries as BibTeX.
- Treat `\begin{thebibliography}` or `\bibitem{key}` as LaTeX bibliography text.
- For plain text, prioritize diagnostics and suggestions. Convert to BibTeX only when structure is unambiguous and the user requests conversion.
- Keep legitimate `@conference`; suggest `@inproceedings` without forcing it.
- Accept `@article`, `@inproceedings`, `@conference`, `@book`, `@inbook`, `@incollection`, `@techreport`, `@phdthesis`, `@mastersthesis`, `@misc`, `@online`, `@manual`, `@standard`, and `@patent`.

## Safe edit policy

Automatically patch only mechanically certain issues: pure DOI normalization, numeric page-range `-` to `--`, removal of `pp.` inside BibTeX `pages`, exact XLSX IEEE journal replacement, confirmed acronym bracing, known field-name lowercase normalization, and exception entries explicitly marked `SAFE_FIX`.

Do not automatically change ambiguous author strings, missing facts, venue ordinals/year labels, article-number representation, entry types, arXiv/formal-version selection, duplicate entries, or uncovered non-IEEE venue words. Never delete duplicates unless explicitly requested.

## Output contract

For `ref.bib`, write:

- `ref.ieee-report.md`
- `ref.ieee-report.json`
- `ref.ieee-fixed.bib` unless `--check-only`

Preserve `.tex` for LaTeX inputs. Include summary counts, per-entry issues, original/suggested values, fix class, and source location. For a pasted entry, answer in this order: conclusion, issue list, fixed content, change explanation, and remaining manual checks. If no issue is found, state that the entry is format-correct within checked scope and that metadata was not necessarily verified online.

## Verification policy

Run `scripts/verify_fixed_bib.py` after file fixes. Treat a parse failure, overlapping patch, second-pass `SAFE_FIX`, unreadable guide/XLSX, or missing rule database as a hard failure. Report PDF text-layer failure explicitly; do not silently OCR. Keep online verification disabled by default and never use Google Scholar as the sole metadata source.

## Examples

```bash
# Only one key
python scripts/check_bibliography.py ref.bib --key paper2024 --check-only

# Only venue findings and safe venue patches
python scripts/check_bibliography.py ref.bib --only venue --fix

# Pasted BibTeX
printf '@article{...}' | python scripts/check_single_entry.py --stdin
```
