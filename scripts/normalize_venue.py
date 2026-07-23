#!/usr/bin/env python3
"""Normalize or suggest an IEEE-style journal/conference venue name."""

from __future__ import annotations

import argparse
import json

from ieee_reference_core import (
    RuleContext,
    normalize_conference,
    normalize_lookup,
    normalize_non_ieee_venue,
    protect_tokens,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("venue")
    parser.add_argument("--kind", choices=["journal", "conference"], required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    context = RuleContext()
    if args.kind == "journal":
        match = context.journal_aliases.get(normalize_lookup(args.venue))
        if match:
            record, method = match
            payload = {
                "original": args.venue,
                "suggested": protect_tokens(record["reference_abbreviation"], ["IEEE", "ACM"]),
                "fix_type": "SAFE_FIX",
                "source": {**record.get("source", {}), "match_method": method},
            }
        else:
            suggested, sources, unresolved = normalize_non_ieee_venue(args.venue, context)
            payload = {
                "original": args.venue,
                "suggested": suggested,
                "fix_type": "SUGGESTED_FIX",
                "source": {"word_rule_sources": sources},
                "unresolved_words": unresolved,
            }
    else:
        suggested, fix_type, source, notes = normalize_conference(args.venue, context)
        payload = {
            "original": args.venue,
            "suggested": suggested,
            "fix_type": fix_type,
            "source": source,
            "notes": notes,
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["suggested"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
