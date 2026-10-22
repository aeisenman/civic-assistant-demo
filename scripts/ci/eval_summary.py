#!/usr/bin/env python3
"""Turns the newest api/evals/results/*.json into markdown for a run summary.

Called by .github/workflows/eval-nightly.yml, which appends the output to
$GITHUB_STEP_SUMMARY. Depends on the standard library only, so it runs on the
runner's system Python without installing anything.
"""

import glob
import json
import sys


def main() -> int:
    pattern = sys.argv[1] if len(sys.argv) > 1 else "api/evals/results/*.json"
    # Filenames are UTC timestamps, so lexical order is chronological order.
    files = sorted(glob.glob(pattern))
    if not files:
        print("No results file was written — the run did not finish.")
        return 0

    latest = files[-1]
    data = json.loads(open(latest).read())
    print(f"Results file: `{latest}` — {data.get('n')} items, "
          f"base URL `{data.get('base_url')}`")
    print()
    print("| scope | scores |")
    print("|---|---|")

    def row(label: str, block: object) -> None:
        # summarise() returns a formatted one-line string; print it verbatim
        # rather than re-deriving numbers the eval runner already computed.
        print(f"| {label} | {block} |")

    row("overall", data.get("overall"))
    for key, block in (data.get("summary") or {}).items():
        row(f"split: {key}", block)
    for key, block in (data.get("by_category") or {}).items():
        row(f"category: {key}", block)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
