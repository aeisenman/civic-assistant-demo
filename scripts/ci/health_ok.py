#!/usr/bin/env python3
"""Reads a /health body on stdin; exits 0 when db and s3 are ok.

Called in a poll loop by .github/workflows/compose-smoke.yml. llm and embed are
printed but never required: compose-smoke answers "does the stack boot", and the
model endpoint there is a stub. Standard library only, no install step.
"""

import json
import sys


def main() -> int:
    try:
        health = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 1

    print(
        "db=%s s3=%s llm=%s embed=%s kb_chunks=%s"
        % (
            health.get("db"),
            health.get("s3"),
            health.get("llm"),
            health.get("embed"),
            health.get("kb_chunks"),
        )
    )
    return 0 if health.get("db") == "ok" and health.get("s3") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
