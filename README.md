# IEEE Reference Checker Skill

Language: English | [中文](README.zh-CN.md)

This is a local skill for **checking and conservatively fixing IEEE Transactions reference formats**.

The reference source is the IEEE Reference Guide in the [IEEE Editorial Style Manual](https://journals.ieeeauthorcenter.ieee.org/your-role-in-article-production/ieee-editorial-style-manual/).

It is designed for pre-submission bibliography cleanup. It supports `.bib` files, `.tex` files that mainly contain BibTeX entries, LaTeX `thebibliography` / `\bibitem` references, and BibTeX, bibitem, or plain-text references pasted into the conversation.

The default policy is: **check only, generate reports, and do not overwrite the original file**. A separate `.ieee-fixed.*` file is generated only when the user explicitly asks for safe fixes or a fixed copy.

## How to Use

You usually do not need to run Python commands yourself. In Codex, describe in natural language which bibliography file you want to check, whether you only want a report, and whether you want a fixed copy.

Before first use, install the dependencies. You can tell Codex:

```text
Install dependencies for ieee-reference-checker.
```

The corresponding Python commands are:

```bash
cd ~/.codex/skills/ieee-reference-checker
python -m pip install -r requirements.txt
```

If you simply say "check this bibliography file" without any extra requirement, the default behavior is: **generate Markdown/JSON reports only, do not modify the original file, and do not generate a fixed copy**.

The equivalent default command is:

```bash
python scripts/check_bibliography.py /path/to/ref.bib --check-only
```

The safest recommended request is:

```text
Use ieee-reference-checker to check /path/to/ref.bib, generate reports only, and do not modify the original file.
```

If the references are inside a LaTeX paper, you can say:

```text
Use ieee-reference-checker to check the references in /path/to/main.tex. Check only and do not modify the source file.
```

Codex will automatically detect whether the input is a `.bib` file, a BibTeX-style `.tex` file, a `thebibliography` / `\bibitem` bibliography, or a single pasted reference.

### Common Natural-Language Requests

Check only and generate reports:

```text
Use ieee-reference-checker to check /path/to/ref.bib and generate a report only.
```

Check inline `bibitem` references in a LaTeX file:

```text
Use ieee-reference-checker to check the references in /path/to/main.tex. Do not modify the original file.
```

Generate a separate fixed file while keeping the original file:

```text
Use ieee-reference-checker to check and safely fix /path/to/ref.bib. Generate a separate fixed file and do not overwrite the original file.
```

Check only one citation key:

```text
Use ieee-reference-checker to check only the carlini2021extracting reference in /path/to/ref.bib.
```

Check only journal or conference venue formatting:

```text
Use ieee-reference-checker to check only venue formatting in /path/to/ref.bib.
```

Check missing fields only:

```text
Use ieee-reference-checker to check which entries in /path/to/ref.bib are missing DOI, pages, volume, issue, or similar fields.
```

Check one pasted BibTeX entry:

```text
Use ieee-reference-checker to check the following BibTeX entry and tell me what does not follow IEEE style:

@article{key,
  title={...}
}
```

If DOI verification needs network access, say so explicitly:

```text
Use ieee-reference-checker to check /path/to/ref.bib and verify DOI existence online.
```

Online verification is disabled by default.

### Recommended Workflow

First, check only:

```text
Use ieee-reference-checker to check /path/to/ref.bib, generate reports only, and do not modify the original file.
```

After reviewing the report, generate a fixed copy:

```text
Use ieee-reference-checker to apply safe fixes to /path/to/ref.bib. Generate a separate fixed file and do not overwrite the original file.
```

Finally, verify the fixed copy:

```text
Use ieee-reference-checker to verify whether /path/to/ref.ieee-fixed.bib still has safely fixable issues.
```

## Outputs

For `ref.bib`, the usual outputs are:

- `ref.ieee-report.md`: a human-readable issue report.
- `ref.ieee-report.json`: structured check results.
- `ref.ieee-fixed.bib`: a separate fixed file, created only when a fixed copy is requested.

For `.tex` input, reports are still generated in the same directory. If a fixed copy is requested, the fixed file keeps the `.tex` suffix.

## Safety Principles

The default behavior is non-destructive:

- Do not overwrite the original `.bib` or `.tex` file.
- Do not change citation keys.
- Do not reorder entries or fields.
- Do not delete comments, custom fields, or duplicate entries.
- Do not invent DOI, pages, volume, issue, year, conference ordinal, author, publisher, or article number.

Codex uses in-place modification only when you explicitly ask to "modify the original file directly." In that mode, it first creates `FILE.bak`; if the backup already exists, it refuses to overwrite it.

## Corresponding Python Commands

Natural-language requests are mapped to local scripts. To run them manually, execute commands from the skill directory:

```bash
cd ~/.codex/skills/ieee-reference-checker
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Check only, without generating a fixed file:

```bash
python scripts/check_bibliography.py ref.bib --check-only
```

Generate a separate fixed file:

```bash
python scripts/check_bibliography.py ref.bib --fix
```

Verify the fixed result:

```bash
python scripts/verify_fixed_bib.py ref.ieee-fixed.bib
```

Check only one citation key:

```bash
python scripts/check_bibliography.py ref.bib --key carlini2021extracting
```

Check only venue formatting:

```bash
python scripts/check_bibliography.py ref.bib --only venue
```

Check only missing fields:

```bash
python scripts/check_bibliography.py ref.bib --only missing
```

Check a single entry:

```bash
python scripts/check_single_entry.py --stdin
```

Explicit in-place modification:

```bash
python scripts/check_bibliography.py ref.bib --fix --in-place
```

## What the Skill Can Fix Automatically

`SAFE_FIX` includes:

- Normalize DOI resolver URLs, `doi:` prefixes, spaces, and trailing punctuation into plain DOI values.
- Convert numeric page ranges from `-` to `--`, and remove `pp.` from BibTeX `pages` fields.
- Replace exactly matched IEEE journal names with the official `Reference Abbreviation` from the XLSX.
- Add local brace protection for confirmed acronyms or system names.
- Normalize known field names to lowercase.
- Apply conference forms explicitly marked as `SAFE_FIX` in `venue_exceptions.yml`.

## What Requires Manual Confirmation

`SUGGESTED_FIX` or `MANUAL_REVIEW` includes:

- Missing DOI, pages, volume, issue, month, access date, or similar metadata.
- Author comma structure, `et al.`, organizational authors, or incomplete author lists.
- USENIX Security ordinal or official year label.
- Venues such as CCS whose official names are year-sensitive.
- Non-IEEE venue words not covered by the guide.
- Choosing between article number and page fields.
- arXiv versus formal versions, and merging or deleting duplicate entries.
- DOI/title, year, or publisher conflicts.

The skill never invents DOI, pages, volume, issue, year, conference ordinal, author, publisher, or article number.

## IEEEabrv Project Handling

The checker scans `.tex` files in the same directory as the input file and records whether `\bibliography{IEEEabrv,...}` or related configuration appears, and whether `IEEEabrv.bib` exists.

`IEEE_J_*` macros that can be resolved from internal XLSX acronyms are preserved. Unresolved macros are reported only and are not forcibly expanded. If the same database mixes macros and literal strings, the checker suggests keeping the project's existing convention consistent.

## Online Verification

Online verification is completely disabled by default. Enable it explicitly when needed:

```bash
python scripts/check_bibliography.py ref.bib --verify-online
```

The current online implementation only uses the Crossref DOI API to verify DOI existence and title similarity, and records the provider and request URL. It does not automatically overwrite author, page, year, volume, issue, or DOI metadata. arXiv, publisher proceedings, DBLP, and similar factual checks still require manual review or future extension. Google Scholar is not used as the sole metadata source.

## Local Rule Sources

This skill includes:

- `references/IEEE_Reference_Style_Guide_for_Authors.docx`
- `references/List_of_IEEE_Journal_Magazine_Titles_Internal_Acronym_and_Reference_Abbreviation.xlsx`

The original workspace provides a DOCX guide, not a PDF. The builder reads text and tables directly from the DOCX. It also supports PDFs with an available text layer. If a PDF has no text layer, the builder fails explicitly and does not run OCR by default. The original source files are not modified.

The XLSX reader uses `openpyxl` and automatically finds semantic columns such as `Title` / `Full Title`, `Internal Acronym` / `Journal/Magazine`, and `Reference Abbreviation`; it does not depend on fixed column numbers. The DOCX guide is read with `python-docx` to identify common conference word lists and the `Common Abbreviations of Words in References` table. Each journal record preserves its worksheet and row number, and each word rule preserves its section, table, and row number.

## Rebuilding the Rule Database

After replacing the IEEE guide or journal-abbreviation workbook, rebuild the local rule database:

```bash
python scripts/build_rule_database.py \
  --guide references/IEEE_Reference_Style_Guide_for_Authors.docx \
  --journals references/List_of_IEEE_Journal_Magazine_Titles_Internal_Acronym_and_Reference_Abbreviation.xlsx
```

If the guide is replaced with a PDF:

```bash
python scripts/build_rule_database.py \
  --guide references/IEEE_Reference_Style_Guide_for_Authors.pdf \
  --journals references/List_of_IEEE_Journal_Magazine_Titles_Internal_Acronym_and_Reference_Abbreviation.xlsx
```

Output files:

- `data/ieee_journal_abbreviations.json`
- `data/ieee_word_abbreviations.json`
- `data/rule_sources.json`
- `data/unresolved_pdf_rules.txt`
- `data/unresolved_xlsx_rows.json`

The current local data contains 267 usable IEEE journal/magazine records and 314 general/conference word abbreviations. The XLSX includes blank rows caused by formatting; these counts refer to usable data records, not the maximum worksheet row number.

Recommended steps when updating IEEE files:

1. Keep backups of old files, but do not modify the original IEEE source files.
2. Replace the corresponding DOCX/PDF or XLSX in `references/`.
3. Run `build_rule_database.py` again.
4. Review `unresolved_pdf_rules.txt` and `unresolved_xlsx_rows.json`.
5. Run `--fix` on your own `.bib` sample, then run `verify_fixed_bib.py` to verify the fixed result.

## Known Limitations

- The bundled parser targets common BibTeX. Complex BibLaTeX value concatenation, cross-field macro expressions, or heavily damaged entries may require manual handling.
- Plain-text references can only be diagnosed conservatively and cannot reliably recover all fields.
- Non-IEEE venues use only word-level rules extracted from the local guide; uncovered words are not guessed.
- DOCX tables can be extracted reliably for the current guide. Tables in differently formatted PDFs may be written to unresolved files and require manual review.
- The journal workbook contains historical acronyms and abbreviations. At runtime, the first current reference abbreviation in each row is used as the primary value while preserving original aliases and source rows.
- Passing the format check does not mean author, title, year, volume, issue, pages, or DOI metadata has been verified against publisher records.

## License

MIT
