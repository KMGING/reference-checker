#!/usr/bin/env python3
"""Core parser, diagnostics, minimal patches, and report rendering.

This module intentionally does not reserialize BibTeX.  It parses enough
structure for diagnostics and applies only non-overlapping text patches so
comments, entry order, field order, indentation, custom fields, and encoding
remain intact.
"""

from __future__ import annotations

import difflib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SUPPORTED_TYPES = {
    "article",
    "inproceedings",
    "conference",
    "book",
    "inbook",
    "incollection",
    "techreport",
    "phdthesis",
    "mastersthesis",
    "misc",
    "online",
    "manual",
    "standard",
    "patent",
}
META_TYPES = {"comment", "preamble", "string"}
KNOWN_FIELDS = {
    "address",
    "annote",
    "archiveprefix",
    "author",
    "booktitle",
    "chapter",
    "crossref",
    "doi",
    "edition",
    "editor",
    "eid",
    "eprint",
    "howpublished",
    "institution",
    "isbn",
    "issn",
    "journal",
    "key",
    "language",
    "month",
    "note",
    "number",
    "organization",
    "pages",
    "primaryclass",
    "publisher",
    "school",
    "series",
    "title",
    "type",
    "url",
    "urldate",
    "version",
    "volume",
    "year",
}
COMMON_FIELD_TYPOS = {
    "authors": "author",
    "journel": "journal",
    "journalname": "journal",
    "book_title": "booktitle",
    "accessed": "urldate",
}
REQUIRED_FIELDS = {
    "article": ({"author", "title", "journal", "year"}, {"volume", "number", "pages", "doi", "month"}),
    "inproceedings": ({"author", "title", "booktitle", "year"}, {"pages", "doi", "organization", "publisher", "address", "month"}),
    "conference": ({"author", "title", "booktitle", "year"}, {"pages", "doi"}),
    "book": ({"author", "title", "publisher", "year"}, {"address", "edition", "isbn"}),
    "inbook": ({"author", "title", "booktitle", "publisher", "year"}, {"chapter", "pages", "editor", "address"}),
    "incollection": ({"author", "title", "booktitle", "publisher", "year"}, {"editor", "pages", "address"}),
    "techreport": ({"author", "title", "institution", "year"}, {"number", "address"}),
    "phdthesis": ({"author", "title", "school", "year"}, {"type", "address"}),
    "mastersthesis": ({"author", "title", "school", "year"}, {"type", "address"}),
    "manual": ({"title", "year"}, {"author", "organization", "address", "edition", "url", "urldate"}),
    "standard": ({"title", "year"}, {"organization", "number", "url"}),
    "patent": ({"author", "title", "year"}, {"number", "month", "address", "url"}),
    "online": ({"title", "url"}, {"author", "organization", "year", "urldate", "version", "note"}),
    "misc": ({"title"}, {"author", "year", "doi", "url", "urldate", "howpublished", "note"}),
}


@dataclass
class BibField:
    name: str
    raw_name: str
    raw_value: str
    value: str
    name_start: int
    name_end: int
    value_start: int
    value_end: int
    inner_start: int
    inner_end: int
    wrapper: str


@dataclass
class BibEntry:
    entry_type: str
    raw_type: str
    citation_key: str
    start: int
    end: int
    fields: list[BibField]
    parse_errors: list[str] = field(default_factory=list)
    raw_text: str = ""

    @property
    def field_map(self) -> dict[str, BibField]:
        result: dict[str, BibField] = {}
        for item in self.fields:
            result.setdefault(item.name, item)
        return result


@dataclass
class Issue:
    citation_key: str
    entry_type: str
    severity: str
    rule_id: str
    field: str | None
    message: str
    original: str | None
    suggested: str | None
    fix_type: str
    source: dict[str, Any]
    category: str
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Patch:
    start: int
    end: int
    replacement: str
    citation_key: str
    field: str | None
    rule_id: str


@dataclass
class Analysis:
    input_type: str
    text: str
    entries: list[BibEntry]
    issues: list[Issue]
    patches: list[Patch]
    global_errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON rule database '{path}': {exc}") from exc


def load_exceptions(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or DATA_DIR / "venue_exceptions.yml"
    if not target.exists():
        return []
    raw = target.read_text(encoding="utf-8")
    try:
        # JSON is a YAML subset.  The bundled file intentionally uses this
        # representation so core checks still work in minimal environments.
        data = json.loads(raw)
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError(
                "PyYAML is required for non-JSON YAML venue exceptions. "
                "Install with: python -m pip install -r requirements.txt"
            ) from exc
        data = yaml.safe_load(raw) or []
    if not isinstance(data, list):
        raise RuntimeError(f"Venue exceptions must be a YAML list: {target}")
    return data


def detect_input_type(text: str) -> str:
    bibtex_count = len(re.findall(r"(?im)^\s*@(?:article|inproceedings|conference|book|inbook|incollection|techreport|phdthesis|mastersthesis|misc|online|manual|standard|patent|string|preamble|comment)\s*[{(]", text))
    bibitem_count = len(re.findall(r"\\bibitem(?:\[[^]]*\])?\s*{", text))
    if bibtex_count and bibtex_count >= bibitem_count:
        return "bibtex"
    if bibitem_count or "\\begin{thebibliography}" in text:
        return "bibitem"
    return "plain"


def _find_entry_close(text: str, opener_index: int, opener: str) -> int | None:
    if opener == "{":
        depth = 1
        escaped = False
        for index in range(opener_index + 1, len(text)):
            char = text[index]
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return index
        return None
    quote = False
    brace_depth = 0
    escaped = False
    for index in range(opener_index + 1, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
        elif char == '"' and brace_depth == 0:
            quote = not quote
        elif not quote and char == "{":
            brace_depth += 1
        elif not quote and char == "}" and brace_depth:
            brace_depth -= 1
        elif not quote and brace_depth == 0 and char == ")":
            return index
    return None


def _find_top_level_comma(text: str, start: int, end: int) -> int | None:
    brace_depth = 0
    quote = False
    escaped = False
    for index in range(start, end):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
        elif char == '"' and brace_depth == 0:
            quote = not quote
        elif not quote and char == "{":
            brace_depth += 1
        elif not quote and char == "}" and brace_depth:
            brace_depth -= 1
        elif not quote and brace_depth == 0 and char == ",":
            return index
    return None


def _parse_field_value(text: str, pos: int, end: int) -> tuple[int, int, int, int, str] | None:
    if pos >= end:
        return None
    start = pos
    if text[pos] == "{":
        depth = 1
        escaped = False
        pos += 1
        while pos < end:
            char = text[pos]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return start, pos + 1, start + 1, pos, "brace"
            pos += 1
        return None
    if text[pos] == '"':
        escaped = False
        pos += 1
        while pos < end:
            char = text[pos]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                return start, pos + 1, start + 1, pos, "quote"
            pos += 1
        return None
    comma = _find_top_level_comma(text, pos, end)
    value_end = comma if comma is not None else end
    while value_end > pos and text[value_end - 1].isspace():
        value_end -= 1
    return start, value_end, start, value_end, "bare"


def parse_bibtex(text: str) -> tuple[list[BibEntry], list[str]]:
    entries: list[BibEntry] = []
    errors: list[str] = []
    cursor = 0
    marker = re.compile(r"@\s*([A-Za-z][A-Za-z0-9_-]*)\s*([{(])")
    while True:
        match = marker.search(text, cursor)
        if not match:
            break
        raw_type = match.group(1)
        entry_type = raw_type.casefold()
        opener = match.group(2)
        opener_index = match.end() - 1
        close = _find_entry_close(text, opener_index, opener)
        if close is None:
            errors.append(f"Unclosed @{raw_type} entry starting at character {match.start()}")
            entries.append(
                BibEntry(entry_type, raw_type, "", match.start(), len(text), [], ["entry is not closed"], text[match.start():])
            )
            break
        if entry_type in META_TYPES:
            cursor = close + 1
            continue
        first_comma = _find_top_level_comma(text, opener_index + 1, close)
        if first_comma is None:
            key = text[opener_index + 1 : close].strip()
            entries.append(
                BibEntry(entry_type, raw_type, key, match.start(), close + 1, [], ["entry has no field separator"], text[match.start():close + 1])
            )
            cursor = close + 1
            continue
        key = text[opener_index + 1 : first_comma].strip()
        fields: list[BibField] = []
        entry_errors: list[str] = []
        pos = first_comma + 1
        while pos < close:
            while pos < close and (text[pos].isspace() or text[pos] == ","):
                pos += 1
            if pos >= close:
                break
            name_match = re.match(r"[A-Za-z][A-Za-z0-9_:-]*", text[pos:close])
            if not name_match:
                snippet = text[pos : min(pos + 30, close)].replace("\n", " ")
                entry_errors.append(f"cannot parse field near '{snippet}'")
                next_comma = _find_top_level_comma(text, pos, close)
                pos = close if next_comma is None else next_comma + 1
                continue
            name_start = pos
            name_end = pos + name_match.end()
            raw_name = text[name_start:name_end]
            pos = name_end
            while pos < close and text[pos].isspace():
                pos += 1
            if pos >= close or text[pos] != "=":
                entry_errors.append(f"field '{raw_name}' is missing '='")
                next_comma = _find_top_level_comma(text, pos, close)
                pos = close if next_comma is None else next_comma + 1
                continue
            pos += 1
            while pos < close and text[pos].isspace():
                pos += 1
            parsed = _parse_field_value(text, pos, close)
            if parsed is None:
                entry_errors.append(f"field '{raw_name}' has an unclosed value")
                break
            value_start, value_end, inner_start, inner_end, wrapper = parsed
            fields.append(
                BibField(
                    name=raw_name.casefold(),
                    raw_name=raw_name,
                    raw_value=text[value_start:value_end],
                    value=text[inner_start:inner_end],
                    name_start=name_start,
                    name_end=name_end,
                    value_start=value_start,
                    value_end=value_end,
                    inner_start=inner_start,
                    inner_end=inner_end,
                    wrapper=wrapper,
                )
            )
            pos = value_end
        entries.append(
            BibEntry(entry_type, raw_type, key, match.start(), close + 1, fields, entry_errors, text[match.start():close + 1])
        )
        cursor = close + 1
    return entries, errors


def parse_bibitems(text: str) -> list[BibEntry]:
    markers = list(re.finditer(r"\\bibitem(?:\[[^]]*\])?\s*{([^}]*)}", text))
    entries: list[BibEntry] = []
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        raw = text[marker.start():end]
        entries.append(BibEntry("bibitem", "bibitem", marker.group(1).strip(), marker.start(), end, [], [], raw))
    return entries


def strip_outer_braces(value: str) -> str:
    value = value.strip()
    while value.startswith("{") and value.endswith("}"):
        depth = 0
        balanced = True
        for index, char in enumerate(value):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0 and index != len(value) - 1:
                    balanced = False
                    break
        if balanced and depth == 0:
            value = value[1:-1].strip()
        else:
            break
    return value


def plain_value(value: str) -> str:
    value = re.sub(r"\\[A-Za-z]+\s*", "", value)
    value = value.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", value).strip()


def normalize_lookup(value: str) -> str:
    value = plain_value(value).casefold().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "", value)


def normalize_title(value: str) -> str:
    value = plain_value(value).casefold()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def protect_tokens(value: str, tokens: Iterable[str]) -> str:
    result = value
    for token in sorted(set(tokens), key=len, reverse=True):
        result = re.sub(
            rf"(?<![{{A-Za-z0-9])({re.escape(token)})(?![}}A-Za-z0-9])",
            r"{\1}",
            result,
        )
    return result


def source_for(rule_id: str, fallback_section: str = "") -> dict[str, Any]:
    payload = load_json(DATA_DIR / "rule_sources.json", {"rules": {}})
    result = dict(payload.get("rules", {}).get(rule_id, {}))
    if fallback_section and "section" not in result:
        result["section"] = fallback_section
    return result


class RuleContext:
    def __init__(self) -> None:
        journal_payload = load_json(DATA_DIR / "ieee_journal_abbreviations.json", {"records": []})
        word_payload = load_json(DATA_DIR / "ieee_word_abbreviations.json", {"abbreviations": {}})
        self.journals: list[dict[str, Any]] = journal_payload.get("records", [])
        self.words: dict[str, dict[str, Any]] = word_payload.get("abbreviations", {})
        self.exceptions = load_exceptions()
        self.journal_aliases: dict[str, tuple[dict[str, Any], str]] = {}
        self.ieee_macros: set[str] = set()
        for record in self.journals:
            candidates = [
                (record.get("full_title", ""), "Full Title exact match"),
                (record.get("workbook_title", ""), "Workbook Title exact match"),
                (record.get("internal_acronym", ""), "Internal Acronym match"),
                (record.get("reference_abbreviation", ""), "Reference Abbreviation match"),
            ]
            candidates.extend((alias, "Alias normalized match") for alias in record.get("aliases", []))
            for value, method in candidates:
                key = normalize_lookup(value)
                if key:
                    self.journal_aliases.setdefault(key, (record, method))
            acronym = re.sub(r"[^A-Za-z0-9]+", "_", record.get("internal_acronym", "")).strip("_")
            if acronym:
                self.ieee_macros.add(f"IEEE_J_{acronym.upper()}")


def normalize_non_ieee_venue(value: str, context: RuleContext) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Apply only sourced word-level abbreviations; return unresolved words."""
    clean = plain_value(value)
    clean = re.sub(r"\bProceedings\s+of\s+the\b", "Proc.", clean, flags=re.IGNORECASE)
    omitted = {"on", "of", "the", "and"}
    sources: list[dict[str, Any]] = []
    unresolved: list[str] = []
    output: list[str] = []
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9'/-]*|[():,.]", clean)
    for token in tokens:
        lower = token.casefold()
        if lower in omitted:
            continue
        if re.fullmatch(r"[A-Za-z][A-Za-z'-]*", token):
            rule = context.words.get(lower)
            if rule:
                output.append(rule["abbreviation"])
                sources.append(rule.get("source", {}))
            else:
                output.append(token)
                if len(token) > 4 and not token.isupper():
                    unresolved.append(token)
        else:
            output.append(token)
    result = " ".join(output)
    result = re.sub(r"\s+([,.:)])", r"\1", result)
    result = re.sub(r"([(])\s+", r"\1", result)
    result = re.sub(r"\s+", " ", result).strip()
    result = protect_tokens(result, ["ACM", "IEEE", "SIGSAC", "USENIX", "NDSS", "CCS"])
    return result, sources, sorted(set(unresolved), key=str.casefold)


def normalize_conference(value: str, context: RuleContext) -> tuple[str | None, str, dict[str, Any], list[str]]:
    plain = plain_value(value)
    lookup = normalize_lookup(plain)
    for exception in context.exceptions:
        aliases = [exception.get("canonical_name", ""), *exception.get("aliases", [])]
        if any(normalize_lookup(alias) == lookup for alias in aliases):
            return (
                exception.get("canonical_name"),
                exception.get("fix_type", "SUGGESTED_FIX"),
                exception.get("source", {}),
                list(exception.get("notes", [])),
            )

    usenix = re.fullmatch(
        r"(?:(?P<ordinal>\d+(?:st|nd|rd|th))\s+)?USENIX\s+Security(?:\s+(?:Symposium|\d{4}))?",
        plain,
        flags=re.IGNORECASE,
    )
    if usenix:
        ordinal = f"{usenix.group('ordinal')} " if usenix.group("ordinal") else ""
        suggestion = f"Proc. {ordinal}{{USENIX}} Secur. Symp."
        notes = ["The official short year form cannot be inferred safely from this field."]
        if not ordinal:
            notes.append("Add the official ordinal only after checking proceedings metadata.")
        return suggestion, "SUGGESTED_FIX", source_for("IEEE-CONF-001"), notes

    suggestion, sources, unresolved = normalize_non_ieee_venue(plain, context)
    if suggestion and not suggestion.casefold().startswith(("proc.", "conf. rec.")):
        suggestion = f"Proc. {suggestion}"
    source: dict[str, Any] = source_for("IEEE-CONF-001")
    if sources:
        source["word_rule_sources"] = sources[:20]
    notes = []
    if unresolved:
        notes.append("Uncovered venue words retained unchanged: " + ", ".join(unresolved))
    return suggestion, "SUGGESTED_FIX", source, notes


def normalize_doi(value: str) -> str | None:
    doi = plain_value(value).strip()
    doi = re.sub(r"^\s*(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)", "", doi, flags=re.IGNORECASE)
    doi = doi.strip().rstrip(".,; ")
    doi = re.sub(r"\s+", "", doi)
    if not doi:
        return None
    return doi


def doi_looks_valid(doi: str) -> bool:
    return bool(re.fullmatch(r"10\.\d{4,9}/\S+", doi, flags=re.IGNORECASE))


def is_macro_field(field: BibField) -> bool:
    return field.wrapper == "bare" and bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_:.-]*", field.value.strip()))


class Analyzer:
    def __init__(self, text: str, input_type: str | None = None) -> None:
        self.text = text
        self.input_type = input_type or detect_input_type(text)
        self.context = RuleContext()
        self.issues: list[Issue] = []
        self.patches: list[Patch] = []
        self._patch_spans: set[tuple[int, int]] = set()

    def add_issue(
        self,
        entry: BibEntry,
        severity: str,
        rule_id: str,
        field_name: str | None,
        message: str,
        original: str | None,
        suggested: str | None,
        fix_type: str,
        category: str,
        source: dict[str, Any] | None = None,
        notes: list[str] | None = None,
        patch: tuple[int, int, str] | None = None,
    ) -> None:
        self.issues.append(
            Issue(
                citation_key=entry.citation_key or "<empty-key>",
                entry_type=entry.entry_type,
                severity=severity,
                rule_id=rule_id,
                field=field_name,
                message=message,
                original=original,
                suggested=suggested,
                fix_type=fix_type,
                source=source or source_for(rule_id),
                category=category,
                notes=notes or [],
            )
        )
        if fix_type == "SAFE_FIX" and patch is not None:
            start, end, replacement = patch
            span = (start, end)
            if span not in self._patch_spans and self.text[start:end] != replacement:
                self._patch_spans.add(span)
                self.patches.append(Patch(start, end, replacement, entry.citation_key, field_name, rule_id))

    def analyze(self) -> Analysis:
        if self.input_type == "bibtex":
            entries, global_errors = parse_bibtex(self.text)
            for entry in entries:
                self.check_bibtex_entry(entry)
            self.check_duplicate_keys(entries)
            self.check_duplicate_works(entries)
            self.check_global_venue_consistency(entries)
        elif self.input_type == "bibitem":
            entries = parse_bibitems(self.text)
            global_errors = []
            for entry in entries:
                self.check_unstructured_entry(entry, allow_patch=True)
        else:
            entries = [BibEntry("plain", "plain", "pasted-entry", 0, len(self.text), [], [], self.text)]
            global_errors = []
            self.check_unstructured_entry(entries[0], allow_patch=False)
        return Analysis(self.input_type, self.text, entries, self.issues, self.patches, global_errors)

    def check_bibtex_entry(self, entry: BibEntry) -> None:
        if not entry.citation_key:
            self.add_issue(entry, "ERROR", "IEEE-SYNTAX-002", None, "Citation key is empty.", "", None, "MANUAL_REVIEW", "syntax")
        for error in entry.parse_errors:
            self.add_issue(entry, "ERROR", "IEEE-SYNTAX-001", None, error, None, None, "MANUAL_REVIEW", "syntax")
        if entry.entry_type not in SUPPORTED_TYPES:
            self.add_issue(
                entry,
                "WARNING",
                "IEEE-FIELD-000",
                None,
                f"Non-standard or unsupported entry type '@{entry.raw_type}'.",
                entry.raw_type,
                "inproceedings" if entry.entry_type == "conference" else None,
                "SUGGESTED_FIX",
                "fields",
                notes=["Do not change a legal project-specific type unless the target toolchain requires it."],
            )
        elif entry.entry_type == "conference":
            self.add_issue(
                entry,
                "INFO",
                "IEEE-FIELD-010",
                None,
                "@conference is commonly normalized to @inproceedings, but is not changed automatically.",
                "conference",
                "inproceedings",
                "SUGGESTED_FIX",
                "fields",
            )

        counts: dict[str, list[BibField]] = {}
        for field_item in entry.fields:
            counts.setdefault(field_item.name, []).append(field_item)
            if field_item.raw_name != field_item.name and field_item.name in KNOWN_FIELDS:
                self.add_issue(
                    entry,
                    "INFO",
                    "IEEE-SYNTAX-004",
                    field_item.name,
                    "Field-name capitalization is inconsistent.",
                    field_item.raw_name,
                    field_item.name,
                    "SAFE_FIX",
                    "syntax",
                    patch=(field_item.name_start, field_item.name_end, field_item.name),
                )
            if field_item.name not in KNOWN_FIELDS:
                suggested = COMMON_FIELD_TYPOS.get(field_item.name)
                self.add_issue(
                    entry,
                    "WARNING",
                    "IEEE-SYNTAX-005",
                    field_item.name,
                    "Unknown or project-specific BibTeX field name.",
                    field_item.raw_name,
                    suggested,
                    "SUGGESTED_FIX" if suggested else "MANUAL_REVIEW",
                    "syntax",
                    notes=["Custom fields are preserved."] if not suggested else [],
                )
            if field_item.value.endswith("\\") and not field_item.value.endswith("\\\\"):
                self.add_issue(
                    entry,
                    "WARNING",
                    "IEEE-SYNTAX-006",
                    field_item.name,
                    "Field ends with a possibly incomplete LaTeX escape.",
                    field_item.value,
                    None,
                    "MANUAL_REVIEW",
                    "syntax",
                )
        for name, duplicates in counts.items():
            if len(duplicates) > 1:
                self.add_issue(
                    entry,
                    "ERROR",
                    "IEEE-SYNTAX-003",
                    name,
                    "Duplicate field in one BibTeX entry.",
                    " | ".join(item.value for item in duplicates),
                    None,
                    "MANUAL_REVIEW",
                    "syntax",
                )

        fields = entry.field_map
        self.check_required_fields(entry, fields)
        self.check_author(entry, fields.get("author"))
        self.check_title(entry, fields.get("title"))
        self.check_journal(entry, fields.get("journal"))
        self.check_conference(entry, fields.get("booktitle"))
        self.check_doi(entry, fields.get("doi"), fields.get("url"))
        self.check_pages(entry, fields.get("pages"), fields.get("eid"))
        self.check_date(entry, fields.get("year"), fields.get("month"))
        self.check_online_fields(entry, fields)
        self.check_arxiv(entry, fields)

    def check_required_fields(self, entry: BibEntry, fields: dict[str, BibField]) -> None:
        required, recommended = REQUIRED_FIELDS.get(entry.entry_type, (set(), set()))
        for name in sorted(required - fields.keys()):
            self.add_issue(
                entry,
                "ERROR",
                "IEEE-FIELD-001",
                name,
                f"Required field '{name}' is missing for @{entry.entry_type}.",
                None,
                None,
                "MANUAL_REVIEW",
                "missing",
                notes=["No metadata is invented."],
            )
        for name in sorted(recommended - fields.keys()):
            # Pages/article number are alternatives for articles.
            if entry.entry_type == "article" and name == "pages" and "eid" in fields:
                continue
            self.add_issue(
                entry,
                "INFO",
                "IEEE-FIELD-002",
                name,
                f"Recommended field '{name}' is absent; it may legitimately be unavailable.",
                None,
                None,
                "SUGGESTED_FIX",
                "missing",
            )

    def check_author(self, entry: BibEntry, author: BibField | None) -> None:
        if author is None:
            return
        value = author.value.strip()
        if re.search(r"\bet\s+al\.?", plain_value(value), flags=re.IGNORECASE):
            self.add_issue(
                entry,
                "ERROR",
                "IEEE-AUTHOR-002",
                "author",
                "BibTeX author data must not replace omitted authors with 'et al.'.",
                value,
                None,
                "MANUAL_REVIEW",
                "author",
                source=source_for("IEEE-AUTHOR-001"),
            )
        if " and " not in value.casefold() and "," in value and not (value.startswith("{") and value.endswith("}")):
            self.add_issue(
                entry,
                "WARNING",
                "IEEE-AUTHOR-001",
                "author",
                "Multiple authors may be separated with commas instead of BibTeX 'and'.",
                value,
                None,
                "MANUAL_REVIEW",
                "author",
                notes=["Names are not rewritten because comma usage inside a BibTeX name can be valid."],
            )

    def check_title(self, entry: BibEntry, title: BibField | None) -> None:
        if title is None:
            return
        value = title.value
        known_exact = ["VLMs", "LLaVA", "GPT", "IEEE", "ACM", "USENIX", "NDSS"]
        protected = protect_tokens(value, [token for token in known_exact if token in plain_value(value)])
        if protected != value:
            self.add_issue(
                entry,
                "WARNING",
                "IEEE-TITLE-001",
                "title",
                "A known acronym or system name is not protected from BibTeX case conversion.",
                value,
                protected,
                "SAFE_FIX",
                "title",
                patch=(title.inner_start, title.inner_end, protected),
                notes=["Only the identified token is braced; the whole title is not double-braced."],
            )
        replacements = {"vlms": "{VLMs}", "llava": "{LLaVA}", "gpt": "{GPT}"}
        suggested = value
        changed = False
        for lower, replacement in replacements.items():
            if re.search(rf"\b{re.escape(lower)}\b", plain_value(value), flags=re.IGNORECASE) and lower in plain_value(value).casefold():
                # Suggest only when the source spelling is entirely lowercase.
                if re.search(rf"\b{re.escape(lower)}\b", plain_value(value)):
                    suggested = re.sub(rf"\b{re.escape(lower)}\b", replacement, suggested)
                    changed = True
        if changed:
            self.add_issue(
                entry,
                "WARNING",
                "IEEE-TITLE-002",
                "title",
                "Possible model/acronym casing needs confirmation.",
                value,
                suggested,
                "SUGGESTED_FIX",
                "title",
                notes=["Casing is not changed automatically because bibliographic metadata was not verified."],
            )

    def check_journal(self, entry: BibEntry, journal: BibField | None) -> None:
        if journal is None:
            return
        raw = journal.value.strip()
        if is_macro_field(journal) and raw.upper().startswith("IEEE_"):
            if raw.upper() not in self.context.ieee_macros:
                self.add_issue(
                    entry,
                    "WARNING",
                    "IEEE-JOURNAL-003",
                    "journal",
                    "IEEE journal macro could not be resolved from the local XLSX acronym mapping.",
                    raw,
                    None,
                    "MANUAL_REVIEW",
                    "venue",
                    notes=["Keep the macro unchanged and check IEEEabrv.bib/project configuration."],
                )
            return
        match = self.context.journal_aliases.get(normalize_lookup(raw))
        if match:
            record, method = match
            official = protect_tokens(record["reference_abbreviation"], ["IEEE", "ACM"])
            if raw != official:
                source = dict(record.get("source", {}))
                source["match_method"] = method
                self.add_issue(
                    entry,
                    "WARNING",
                    "IEEE-JOURNAL-001",
                    "journal",
                    "IEEE journal title does not use the XLSX official reference abbreviation exactly.",
                    raw,
                    official,
                    "SAFE_FIX",
                    "venue",
                    source=source,
                    patch=(journal.inner_start, journal.inner_end, official),
                )
            return
        if plain_value(raw).casefold().startswith("ieee "):
            self.add_issue(
                entry,
                "WARNING",
                "IEEE-JOURNAL-002",
                "journal",
                "IEEE-looking journal was not found in the local XLSX mapping.",
                raw,
                None,
                "MANUAL_REVIEW",
                "venue",
                notes=["Do not guess an IEEE abbreviation."],
            )
            return
        suggested, sources, unresolved = normalize_non_ieee_venue(raw, self.context)
        if suggested and normalize_lookup(suggested) != normalize_lookup(raw):
            source = source_for("IEEE-VENUE-001")
            source["word_rule_sources"] = sources[:20]
            notes = []
            if unresolved:
                notes.append("Guide-uncovered words retained: " + ", ".join(unresolved))
            self.add_issue(
                entry,
                "WARNING",
                "IEEE-JOURNAL-010",
                "journal",
                "Non-IEEE periodical can be normalized with sourced word-level abbreviations.",
                raw,
                suggested,
                "SUGGESTED_FIX",
                "venue",
                source=source,
                notes=notes,
            )

    def check_conference(self, entry: BibEntry, booktitle: BibField | None) -> None:
        if booktitle is None:
            if entry.entry_type == "article" and "conference" in plain_value(entry.field_map.get("journal", BibField("", "", "", "", 0, 0, 0, 0, 0, 0, "")).value).casefold():
                self.add_issue(entry, "WARNING", "IEEE-CONF-004", "journal", "A conference name may have been placed in the journal field.", None, None, "MANUAL_REVIEW", "venue")
            return
        suggestion, fix_type, source, notes = normalize_conference(booktitle.value, self.context)
        if suggestion and booktitle.value.strip() != suggestion:
            self.add_issue(
                entry,
                "WARNING",
                "IEEE-CONF-003",
                "booktitle",
                "Conference name is not in the sourced IEEE abbreviated form.",
                booktitle.value,
                suggestion,
                fix_type,
                "venue",
                source=source,
                notes=notes,
                patch=(booktitle.inner_start, booktitle.inner_end, suggestion) if fix_type == "SAFE_FIX" else None,
            )

    def check_doi(self, entry: BibEntry, doi: BibField | None, url: BibField | None) -> None:
        if doi is None:
            return
        normalized = normalize_doi(doi.value)
        if not normalized:
            self.add_issue(entry, "ERROR", "IEEE-DOI-002", "doi", "DOI field is empty after normalization.", doi.value, None, "MANUAL_REVIEW", "doi")
            return
        if normalized != doi.value.strip():
            self.add_issue(
                entry,
                "WARNING",
                "IEEE-DOI-001",
                "doi",
                "DOI should be stored as a pure DOI without resolver prefix, spaces, or trailing punctuation.",
                doi.value,
                normalized,
                "SAFE_FIX",
                "doi",
                patch=(doi.inner_start, doi.inner_end, normalized),
            )
        if not doi_looks_valid(normalized):
            self.add_issue(entry, "ERROR", "IEEE-DOI-002", "doi", "DOI is malformed or obviously truncated.", normalized, None, "MANUAL_REVIEW", "doi")
        if url and normalize_doi(url.value) == normalized and "doi.org" in plain_value(url.value).casefold():
            self.add_issue(
                entry,
                "INFO",
                "IEEE-DOI-003",
                "url",
                "URL duplicates the DOI resolver and is usually redundant for a formal publication.",
                url.value,
                None,
                "SUGGESTED_FIX",
                "doi",
                notes=["The URL is not deleted automatically."],
            )

    def check_pages(self, entry: BibEntry, pages: BibField | None, eid: BibField | None) -> None:
        if pages is None:
            return
        value = pages.value.strip()
        if re.fullmatch(r"(?:e\d+|\d{6,})", value, flags=re.IGNORECASE):
            self.add_issue(
                entry,
                "INFO",
                "IEEE-PAGES-003",
                "pages",
                "Value looks like an electronic article number; it is not converted to a page range.",
                value,
                None,
                "SUGGESTED_FIX",
                "pages",
                notes=["Confirm whether the target BibTeX style expects pages or eid/article-number metadata."],
            )
            return
        fixed = re.sub(r"^\s*pp?\.\s*", "", value, flags=re.IGNORECASE)
        fixed = re.sub(r"(?<=[0-9A-Za-z])\s*[–—]\s*(?=[0-9A-Za-z])", "--", fixed)
        fixed = re.sub(r"(?<=[0-9])-(?=[0-9])", "--", fixed)
        fixed = re.sub(r"-{3,}", "--", fixed)
        if fixed != value:
            self.add_issue(
                entry,
                "WARNING",
                "IEEE-PAGES-001",
                "pages",
                "BibTeX page range should omit 'pp.' and use a double hyphen.",
                value,
                fixed,
                "SAFE_FIX",
                "pages",
                patch=(pages.inner_start, pages.inner_end, fixed),
            )
        match = re.fullmatch(r"(\d+)--(\d+)", fixed)
        if match and int(match.group(1)) > int(match.group(2)):
            self.add_issue(entry, "WARNING", "IEEE-PAGES-002", "pages", "Page-range order appears reversed.", fixed, None, "MANUAL_REVIEW", "pages")
        if eid and normalize_lookup(eid.value) == normalize_lookup(value):
            self.add_issue(entry, "WARNING", "IEEE-PAGES-004", "pages", "The same article identifier appears in both pages and eid.", value, None, "MANUAL_REVIEW", "pages")

    def check_date(self, entry: BibEntry, year: BibField | None, month: BibField | None) -> None:
        if year and not re.fullmatch(r"(?:19|20)\d{2}", plain_value(year.value)):
            self.add_issue(entry, "ERROR", "IEEE-DATE-001", "year", "Year should be a four-digit publication year.", year.value, None, "MANUAL_REVIEW", "date")
        if month:
            months = {
                "january": "jan", "jan.": "jan", "february": "feb", "feb.": "feb",
                "march": "mar", "mar.": "mar", "april": "apr", "apr.": "apr",
                "may": "may", "june": "jun", "jun.": "jun", "july": "jul", "jul.": "jul",
                "august": "aug", "aug.": "aug", "september": "sep", "sept.": "sep", "sep.": "sep",
                "october": "oct", "oct.": "oct", "november": "nov", "nov.": "nov", "december": "dec", "dec.": "dec",
            }
            clean = plain_value(month.value).casefold()
            if clean in months and not (month.wrapper == "bare" and month.value.casefold() == months[clean]):
                self.add_issue(
                    entry,
                    "INFO",
                    "IEEE-DATE-002",
                    "month",
                    "Month representation is inconsistent with traditional BibTeX month macros.",
                    month.raw_value,
                    months[clean],
                    "SUGGESTED_FIX",
                    "date",
                    notes=["Not changed automatically because projects may intentionally use literal months."],
                )

    def check_online_fields(self, entry: BibEntry, fields: dict[str, BibField]) -> None:
        if entry.entry_type in {"online", "misc"} and "url" in fields:
            if "urldate" not in fields:
                self.add_issue(entry, "INFO", "IEEE-URL-001", "urldate", "Online resource has no access date (urldate).", None, None, "SUGGESTED_FIX", "url")
            if "year" not in fields:
                self.add_issue(entry, "WARNING", "IEEE-URL-002", "year", "Online resource has no publication year; use access year only if the guide/project requires it.", None, None, "MANUAL_REVIEW", "url")

    def check_arxiv(self, entry: BibEntry, fields: dict[str, BibField]) -> None:
        journal = plain_value(fields.get("journal", BibField("", "", "", "", 0, 0, 0, 0, 0, 0, "")).value)
        is_arxiv = bool(fields.get("eprint")) or "arxiv" in journal.casefold() or "arxiv" in plain_value(fields.get("note", BibField("", "", "", "", 0, 0, 0, 0, 0, 0, "")).value).casefold()
        if is_arxiv and "doi" in fields and entry.entry_type == "misc":
            self.add_issue(
                entry,
                "WARNING",
                "IEEE-ARXIV-001",
                "doi",
                "An arXiv/@misc entry already has a DOI and may have a formal published version.",
                fields["doi"].value,
                None,
                "MANUAL_REVIEW",
                "arxiv",
                notes=["No publication facts are changed without local or online verification."],
            )

    def check_duplicate_keys(self, entries: list[BibEntry]) -> None:
        grouped: dict[str, list[BibEntry]] = {}
        for entry in entries:
            grouped.setdefault(entry.citation_key, []).append(entry)
        for key, group in grouped.items():
            if key and len(group) > 1:
                for entry in group:
                    self.add_issue(entry, "ERROR", "IEEE-DUP-001", None, "Duplicate citation key.", key, None, "MANUAL_REVIEW", "duplicate")

    def check_duplicate_works(self, entries: list[BibEntry]) -> None:
        for left_index, left in enumerate(entries):
            lf = left.field_map
            left_title = normalize_title(lf.get("title", BibField("", "", "", "", 0, 0, 0, 0, 0, 0, "")).value)
            left_doi = normalize_doi(lf["doi"].value) if "doi" in lf else None
            left_eprint = plain_value(lf.get("eprint", BibField("", "", "", "", 0, 0, 0, 0, 0, 0, "")).value).casefold()
            for right in entries[left_index + 1 :]:
                rf = right.field_map
                right_title = normalize_title(rf.get("title", BibField("", "", "", "", 0, 0, 0, 0, 0, 0, "")).value)
                right_doi = normalize_doi(rf["doi"].value) if "doi" in rf else None
                right_eprint = plain_value(rf.get("eprint", BibField("", "", "", "", 0, 0, 0, 0, 0, 0, "")).value).casefold()
                classification = None
                if left_doi and right_doi and left_doi.casefold() == right_doi.casefold():
                    classification = "exact duplicate DOI"
                elif left_eprint and right_eprint and left_eprint == right_eprint:
                    classification = "same arXiv identifier"
                elif left_title and right_title:
                    ratio = difflib.SequenceMatcher(None, left_title, right_title).ratio()
                    if left_title == right_title or ratio >= 0.96:
                        left_arxiv = left.entry_type == "misc" or "arxiv" in plain_value(lf.get("journal", BibField("", "", "", "", 0, 0, 0, 0, 0, 0, "")).value).casefold() or bool(left_eprint)
                        right_arxiv = right.entry_type == "misc" or "arxiv" in plain_value(rf.get("journal", BibField("", "", "", "", 0, 0, 0, 0, 0, 0, "")).value).casefold() or bool(right_eprint)
                        classification = "preprint and formal-version duplicate" if left_arxiv != right_arxiv else "same work under different citation keys"
                if classification:
                    message = f"Possible duplicate: {classification}; related key '{right.citation_key}'."
                    self.add_issue(left, "WARNING", "IEEE-DUP-002", "title", message, lf.get("title").value if lf.get("title") else None, None, "MANUAL_REVIEW", "duplicate", notes=["Entries are never deleted automatically."])
                    reverse = f"Possible duplicate: {classification}; related key '{left.citation_key}'."
                    self.add_issue(right, "WARNING", "IEEE-DUP-002", "title", reverse, rf.get("title").value if rf.get("title") else None, None, "MANUAL_REVIEW", "duplicate", notes=["Prefer the verified formal version when both versions are confirmed."])

    def check_global_venue_consistency(self, entries: list[BibEntry]) -> None:
        macro_entries: list[BibEntry] = []
        string_entries: list[BibEntry] = []
        for entry in entries:
            journal = entry.field_map.get("journal")
            if not journal:
                continue
            if is_macro_field(journal) and journal.value.upper().startswith("IEEE_"):
                macro_entries.append(entry)
            elif normalize_lookup(journal.value) in self.context.journal_aliases:
                string_entries.append(entry)
        if macro_entries and string_entries:
            for entry in [macro_entries[0], string_entries[0]]:
                self.add_issue(
                    entry,
                    "INFO",
                    "IEEE-JOURNAL-004",
                    "journal",
                    "The bibliography mixes IEEEabrv-style macros and literal IEEE journal strings.",
                    entry.field_map["journal"].value,
                    None,
                    "MANUAL_REVIEW",
                    "venue",
                    notes=["Keep the project's established convention; no representation is forced."],
                )

    def check_unstructured_entry(self, entry: BibEntry, allow_patch: bool) -> None:
        raw = entry.raw_text
        doi_pattern = re.compile(r"(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)(10\.\d{4,9}/[^\s,;}]+)", re.IGNORECASE)
        doi_matches = list(doi_pattern.finditer(raw))
        doi_spans = [(match.start(), match.end()) for match in doi_matches]
        for match in doi_matches:
            normalized = match.group(1).rstrip(".")
            absolute = entry.start + match.start()
            self.add_issue(
                entry,
                "WARNING",
                "IEEE-DOI-001",
                "text",
                "DOI resolver/prefix can be normalized to a pure DOI.",
                match.group(0),
                normalized,
                "SAFE_FIX" if allow_patch else "SUGGESTED_FIX",
                "doi",
                patch=(absolute, absolute + len(match.group(0)), normalized) if allow_patch else None,
            )
        page_pattern = re.compile(r"(?<!-)(\d+)-(\d+)(?!-)")
        for match in page_pattern.finditer(raw):
            if any(match.start() < end and match.end() > start for start, end in doi_spans):
                continue
            absolute = entry.start + match.start()
            replacement = f"{match.group(1)}--{match.group(2)}"
            self.add_issue(
                entry,
                "WARNING",
                "IEEE-PAGES-001",
                "text",
                "LaTeX page range should use a double hyphen.",
                match.group(0),
                replacement,
                "SAFE_FIX" if allow_patch else "SUGGESTED_FIX",
                "pages",
                patch=(absolute, absolute + len(match.group(0)), replacement) if allow_patch else None,
            )
        if not re.search(r"\b(?:19|20)\d{2}\b", raw):
            self.add_issue(entry, "WARNING", "IEEE-DATE-001", "text", "No four-digit year was detected.", None, None, "MANUAL_REVIEW", "date")


def analyze_text(text: str, input_type: str | None = None) -> Analysis:
    return Analyzer(text, input_type=input_type).analyze()


def select_analysis(analysis: Analysis, key: str | None = None, only: str | None = None) -> Analysis:
    issues = analysis.issues
    patches = analysis.patches
    entries = analysis.entries
    if key:
        entries = [entry for entry in entries if entry.citation_key == key]
        issues = [issue for issue in issues if issue.citation_key == key]
        patches = [patch for patch in patches if patch.citation_key == key]
        if not entries:
            analysis.global_errors.append(f"Citation key not found: {key}")
    if only:
        category = only.casefold()
        aliases = {"venue": "venue", "missing": "missing", "fields": "fields"}
        category = aliases.get(category, category)
        issues = [issue for issue in issues if issue.category == category]
        allowed_rule_ids = {issue.rule_id for issue in issues if issue.fix_type == "SAFE_FIX"}
        allowed_keys = {issue.citation_key for issue in issues if issue.fix_type == "SAFE_FIX"}
        patches = [
            patch
            for patch in patches
            if patch.rule_id in allowed_rule_ids and (not patch.citation_key or patch.citation_key in allowed_keys)
        ]
    return Analysis(
        analysis.input_type,
        analysis.text,
        entries,
        issues,
        patches,
        list(analysis.global_errors),
        dict(analysis.metadata),
    )


def apply_patches(text: str, patches: Iterable[Patch]) -> str:
    ordered = sorted(patches, key=lambda patch: (patch.start, patch.end))
    previous_end = -1
    for patch in ordered:
        if patch.start < previous_end:
            raise RuntimeError(
                f"Overlapping safe fixes near character {patch.start}; no output was written."
            )
        if not (0 <= patch.start <= patch.end <= len(text)):
            raise RuntimeError(f"Invalid patch span: {patch}")
        previous_end = patch.end
    result = text
    for patch in reversed(ordered):
        result = result[: patch.start] + patch.replacement + result[patch.end :]
    return result


def analysis_summary(analysis: Analysis) -> dict[str, Any]:
    severity_counts = {name: 0 for name in ("ERROR", "WARNING", "INFO")}
    for issue in analysis.issues:
        severity_counts[issue.severity] = severity_counts.get(issue.severity, 0) + 1
    severity_counts["ERROR"] += len(analysis.global_errors)
    patched_keys = {patch.citation_key for patch in analysis.patches if patch.citation_key}
    return {
        "input_type": analysis.input_type,
        "total_entries": len(analysis.entries),
        "ERROR": severity_counts["ERROR"],
        "WARNING": severity_counts["WARNING"],
        "INFO": severity_counts["INFO"],
        "safe_fixes": len(analysis.patches),
        "manual_review": sum(issue.fix_type == "MANUAL_REVIEW" for issue in analysis.issues),
        "suggested_fixes": sum(issue.fix_type == "SUGGESTED_FIX" for issue in analysis.issues),
        "unchanged_entries": max(0, len(analysis.entries) - len(patched_keys)),
    }


def report_json(analysis: Analysis, source_file: str | None = None) -> dict[str, Any]:
    return {
        "file": source_file,
        "summary": analysis_summary(analysis),
        "global_errors": analysis.global_errors,
        "metadata": analysis.metadata,
        "entries": [asdict(issue) for issue in analysis.issues],
        "safe_patches": [asdict(patch) for patch in analysis.patches],
    }


def _md_code(value: str | None) -> str:
    if value is None:
        return "（无）"
    return f"`{value.replace('`', '\\`')}`"


def report_markdown(analysis: Analysis, source_file: str | None = None) -> str:
    summary = analysis_summary(analysis)
    lines = [
        "# IEEE 参考文献检查报告",
        "",
        f"文件：{source_file or '对话输入'}",
        f"输入类型：{summary['input_type']}",
        f"条目总数：{summary['total_entries']}",
        f"ERROR：{summary['ERROR']}",
        f"WARNING：{summary['WARNING']}",
        f"INFO：{summary['INFO']}",
        f"可安全修复：{summary['safe_fixes']}",
        f"需要人工确认：{summary['manual_review']}",
        f"未修改条目：{summary['unchanged_entries']}",
        "",
    ]
    if analysis.global_errors:
        lines.extend(["## 全局解析问题", ""])
        lines.extend(f"- {error}" for error in analysis.global_errors)
        lines.append("")
    grouped: dict[str, list[Issue]] = {}
    for issue in analysis.issues:
        grouped.setdefault(issue.citation_key, []).append(issue)
    if not grouped and not analysis.global_errors:
        lines.extend(
            [
                "该条目在当前可检查范围内符合 IEEE 参考文献规范，未发现需要修改的问题。",
                "",
                "注意：格式检查通过不等于元数据已经在线核验。",
                "",
            ]
        )
    for key, issues in grouped.items():
        lines.extend([f"## {key}", ""])
        for issue in issues:
            lines.extend(
                [
                    f"- 类型：@{issue.entry_type}",
                    f"- 状态：{issue.severity}",
                    f"- 规则：{issue.rule_id}",
                    f"- 字段：{issue.field or '（条目级）'}",
                    f"- 问题：{issue.message}",
                    f"- 原始值：{_md_code(issue.original)}",
                    f"- 建议值：{_md_code(issue.suggested)}",
                    f"- 修复级别：{issue.fix_type}",
                ]
            )
            if issue.source:
                source_bits = []
                for label, field_name in (
                    ("文件", "source_file"),
                    ("章节", "section"),
                    ("工作表", "sheet"),
                    ("行", "row"),
                    ("页", "page"),
                    ("匹配方式", "match_method"),
                ):
                    if issue.source.get(field_name) is not None:
                        source_bits.append(f"{label}: {issue.source[field_name]}")
                if source_bits:
                    lines.append("- 依据：" + "；".join(source_bits))
            for note in issue.notes:
                lines.append(f"- 备注：{note}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def verify_dois_online(analysis: Analysis, timeout: float = 10.0) -> None:
    """Opt-in Crossref DOI existence/title check; never creates fixes."""
    if analysis.input_type != "bibtex":
        analysis.metadata["online_verification"] = "skipped: only BibTeX DOI fields are supported"
        return
    checked = 0
    failures: list[str] = []
    for entry in analysis.entries:
        fields = entry.field_map
        if "doi" not in fields:
            continue
        doi = normalize_doi(fields["doi"].value)
        if not doi or not doi_looks_valid(doi):
            continue
        url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
        request = urllib.request.Request(url, headers={"User-Agent": "ieee-reference-checker/1.0 (mailto:unknown@example.invalid)"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            checked += 1
            metadata = payload.get("message", {})
            crossref_titles = metadata.get("title") or []
            local_title = normalize_title(fields.get("title", BibField("", "", "", "", 0, 0, 0, 0, 0, 0, "")).value)
            remote_title = normalize_title(crossref_titles[0]) if crossref_titles else ""
            if local_title and remote_title and difflib.SequenceMatcher(None, local_title, remote_title).ratio() < 0.75:
                analysis.issues.append(
                    Issue(
                        entry.citation_key,
                        entry.entry_type,
                        "WARNING",
                        "IEEE-DOI-010",
                        "doi",
                        "Crossref DOI metadata title differs substantially from the local title.",
                        fields["title"].value if "title" in fields else None,
                        crossref_titles[0] if crossref_titles else None,
                        "MANUAL_REVIEW",
                        {"type": "Crossref API", "url": url, "doi": doi},
                        "doi",
                        ["Do not overwrite authors, pages, year, volume, issue, or DOI without manual confirmation."],
                    )
                )
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            failures.append(f"{entry.citation_key}: {exc}")
    analysis.metadata["online_verification"] = {
        "enabled": True,
        "provider": "Crossref API",
        "checked_dois": checked,
        "failures": failures,
        "policy": "verification only; no metadata auto-fixes",
    }
