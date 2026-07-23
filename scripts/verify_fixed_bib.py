#!/usr/bin/env python3
"""Verify that a fixed bibliography parses and has no remaining SAFE_FIX."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ieee_reference_core import analyze_text, apply_patches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file")
    args = parser.parse_args()
    path = Path(args.file).resolve()
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 2
    try:
        text = path.read_text(encoding="utf-8-sig")
        analysis = analyze_text(text)
        if analysis.global_errors:
            raise RuntimeError("; ".join(analysis.global_errors))
        syntax_errors = [
            issue for issue in analysis.issues
            if issue.severity == "ERROR" and issue.rule_id.startswith("IEEE-SYNTAX")
        ]
        if syntax_errors:
            raise RuntimeError("; ".join(issue.message for issue in syntax_errors))
        second = apply_patches(text, analysis.patches)
        if second != text:
            raise RuntimeError(f"Idempotency failed: {len(analysis.patches)} SAFE_FIX patch(es) remain")
    except Exception as exc:
        print(f"Verification failed: {exc}", file=sys.stderr)
        return 1
    print(f"Verification passed: parseable and idempotent ({path.name}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
