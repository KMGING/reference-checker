#!/usr/bin/env python3
"""Check a BibTeX, bib.tex, or LaTeX thebibliography file."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from ieee_reference_core import (
    analyze_text,
    analysis_summary,
    apply_patches,
    report_json,
    report_markdown,
    select_analysis,
    verify_dois_online,
)


def read_text_preserving_bom(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        return raw.decode("utf-8-sig"), bom
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"Input is not valid UTF-8/UTF-8 BOM: {path}: {exc}") from exc


def write_text_preserving_bom(path: Path, text: str, bom: bool) -> None:
    encoding = "utf-8-sig" if bom else "utf-8"
    path.write_text(text, encoding=encoding, newline="")


def output_paths(source: Path) -> tuple[Path, Path, Path]:
    stem = source.stem
    report_md = source.with_name(f"{stem}.ieee-report.md")
    report_json_path = source.with_name(f"{stem}.ieee-report.json")
    suffix = source.suffix if source.suffix.casefold() in {".bib", ".tex"} else ".bib"
    fixed = source.with_name(f"{stem}.ieee-fixed{suffix}")
    return report_md, report_json_path, fixed


def inspect_project_context(source: Path) -> dict[str, object]:
    tex_files: list[str] = []
    ieeeabrv_mentions: list[str] = []
    for candidate in source.parent.glob("*.tex"):
        try:
            content = candidate.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        tex_files.append(candidate.name)
        if "IEEEabrv" in content and ("\\bibliography" in content or "\\addbibresource" in content):
            ieeeabrv_mentions.append(candidate.name)
    return {
        "tex_files_scanned": sorted(tex_files),
        "ieeeabrv_configured_in": sorted(ieeeabrv_mentions),
        "ieeeabrv_bib_present": (source.parent / "IEEEabrv.bib").exists(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", help=".bib, bib.tex, or LaTeX file containing \\bibitem")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check-only", action="store_true", help="Write reports only; do not create a fixed copy")
    mode.add_argument("--fix", action="store_true", help="Generate a minimally patched fixed copy")
    parser.add_argument("--in-place", action="store_true", help="With --fix, modify the source after creating FILE.bak")
    parser.add_argument("--key", help="Check/fix only one citation key")
    parser.add_argument(
        "--only",
        choices=["venue", "missing", "fields", "syntax", "author", "title", "doi", "pages", "date", "url", "arxiv", "duplicate"],
        help="Limit diagnostics and fixes to one category",
    )
    parser.add_argument("--verify-online", action="store_true", help="Opt in to Crossref DOI verification")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = Path(args.file).resolve()
    if not source.exists():
        print(f"Input file not found: {source}", file=sys.stderr)
        return 2
    if args.in_place and not args.fix:
        print("--in-place requires explicit --fix.", file=sys.stderr)
        return 2
    try:
        text, had_bom = read_text_preserving_bom(source)
        analysis = analyze_text(text)
        analysis.metadata["project_context"] = inspect_project_context(source)
        analysis = select_analysis(analysis, key=args.key, only=args.only)
        if args.verify_online:
            verify_dois_online(analysis)

        report_md_path, report_json_path, fixed_path = output_paths(source)
        # Default is a safe dry-run artifact: reports plus a separate fixed copy.
        create_fixed = not args.check_only
        fixed_text = text
        if create_fixed:
            fixed_text = apply_patches(text, analysis.patches)
            fixed_analysis = select_analysis(analyze_text(fixed_text), key=args.key, only=args.only)
            remaining_safe = len(fixed_analysis.patches)
            parse_ok = not fixed_analysis.global_errors and not any(
                issue.rule_id == "IEEE-SYNTAX-001" and issue.severity == "ERROR"
                for issue in fixed_analysis.issues
            )
            analysis.metadata["verification"] = {
                "fixed_parse_ok": parse_ok,
                "remaining_safe_fixes_after_second_pass": remaining_safe,
                "idempotent": parse_ok and remaining_safe == 0,
            }
            if not parse_ok or remaining_safe:
                raise RuntimeError(
                    "Fixed output failed parse/idempotency verification; no source file was modified."
                )
            if args.in_place:
                backup = Path(str(source) + ".bak")
                if backup.exists():
                    raise RuntimeError(f"Backup already exists; refusing to overwrite it: {backup}")
                shutil.copy2(source, backup)
                write_text_preserving_bom(source, fixed_text, had_bom)
                analysis.metadata["output"] = {"in_place": str(source), "backup": str(backup)}
            else:
                write_text_preserving_bom(fixed_path, fixed_text, had_bom)
                analysis.metadata["output"] = {"fixed_copy": str(fixed_path), "original_unchanged": True}

        report_md_path.write_text(report_markdown(analysis, source.name), encoding="utf-8")
        report_json_path.write_text(
            json.dumps(report_json(analysis, source.name), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"Bibliography check failed: {exc}", file=sys.stderr)
        return 1

    summary = analysis_summary(analysis)
    print(
        f"Checked {summary['total_entries']} entries: "
        f"ERROR={summary['ERROR']}, WARNING={summary['WARNING']}, INFO={summary['INFO']}, "
        f"SAFE_FIX={summary['safe_fixes']}."
    )
    print(f"Markdown report: {report_md_path}")
    print(f"JSON report: {report_json_path}")
    if create_fixed and not args.in_place:
        print(f"Fixed copy: {fixed_path}")
    if args.in_place:
        print(f"Modified in place with backup: {source}.bak")
    return 0 if summary["ERROR"] == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
