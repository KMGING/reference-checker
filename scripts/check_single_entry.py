#!/usr/bin/env python3
"""Check one or more pasted BibTeX, bibitem, or plain-text references."""

from __future__ import annotations

import argparse
import json
import sys

from ieee_reference_core import analyze_text, analysis_summary, apply_patches, report_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stdin", action="store_true", help="Read the pasted entry or entries from standard input")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.stdin and sys.stdin.isatty():
        print("Use --stdin and pipe/paste one or more references.", file=sys.stderr)
        return 2
    text = sys.stdin.read()
    if not text.strip():
        print("No reference input received.", file=sys.stderr)
        return 2
    try:
        analysis = analyze_text(text)
        fixed = apply_patches(text, analysis.patches)
    except Exception as exc:
        print(f"Single-entry check failed: {exc}", file=sys.stderr)
        return 1
    if args.json:
        payload = report_json(analysis)
        payload["fixed_text"] = fixed
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    summary = analysis_summary(analysis)
    total = summary["ERROR"] + summary["WARNING"] + summary["INFO"]
    if not total:
        print("该条目在当前可检查范围内符合 IEEE 参考文献规范，未发现需要修改的问题。")
        print("说明：格式正确不等于元数据已在线核验。")
        return 0
    print(
        f"检查结果：发现 {total} 个问题，其中 {summary['safe_fixes']} 个可安全修复，"
        f"{summary['suggested_fixes']} 个为建议项，{summary['manual_review']} 个必须人工确认。"
    )
    print("\n问题列表：")
    for issue in analysis.issues:
        print(f"- [{issue.severity}] {issue.rule_id} ({issue.field or '条目'}): {issue.message}")
        if issue.suggested is not None:
            print(f"  建议：{issue.suggested}")

    language = "bibtex" if analysis.input_type == "bibtex" else "latex" if analysis.input_type == "bibitem" else "text"
    print("\n修复后的内容：")
    print(f"```{language}")
    print(fixed.rstrip())
    print("```")
    print("\n修改说明：")
    safe_issues = [issue for issue in analysis.issues if issue.fix_type == "SAFE_FIX"]
    if safe_issues:
        for issue in safe_issues:
            print(f"- {issue.rule_id}: {issue.original!r} → {issue.suggested!r}")
    else:
        print("- 未自动应用修改；当前问题均需建议或人工确认。")
    print("\n仍需人工确认的信息：")
    pending = [issue for issue in analysis.issues if issue.fix_type != "SAFE_FIX"]
    if pending:
        for issue in pending:
            print(f"- {issue.rule_id}: {issue.message}")
    else:
        print("- 无格式层面的待确认项；元数据尚未在线核验。")
    return 0 if summary["ERROR"] == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
