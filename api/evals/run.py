"""Runs api/evals/golden.json against a live API and reports, mechanically.

Run from the host: `cd api && uv run python -m evals.run --base-url http://localhost:8080`.
Depends on: httpx and a running stack. Scoring is deliberately dumb — intent
match, expected tools called, citations present, loose keyword overlap, a literal
phrase guardrail and (M19) a check that every figure in the reply came from a
tool. No LLM judge, and nothing here is a pass/fail gate:
PLAN.md §14 says report the number, never tune the prompts to it.
"""

import argparse
import asyncio
import json
import re
import statistics
from datetime import UTC, datetime
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden.json"
RESULTS = HERE / "results"

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "your",
    "you",
    "are",
    "from",
    "have",
    "has",
    "into",
    "than",
    "then",
    "they",
    "them",
    "their",
    "there",
    "will",
    "would",
    "can",
    "not",
    "but",
    "any",
    "all",
    "was",
    "were",
    "been",
    "its",
    "it's",
    "about",
    "also",
    "only",
    "each",
    "when",
    "what",
    "which",
    "who",
    "how",
    "why",
    "does",
    "did",
    "get",
    "got",
    "out",
    "per",
    "city",
    "san",
    "diego",
    "estimate",
    "typically",
    "generally",
    "before",
    "after",
    "over",
}
NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
MIN_KEYWORDS = 2

# M9: every item is filed under exactly one of these; the report breaks the
# metrics out per category so an adversarial regression cannot hide inside a
# healthy overall average.
# M23 adds `production`: the ten highest-volume resident questions research/08
# found the knowledge base did not answer. They are a benchmark of coverage, so
# they are kept in their own category rather than folded into `standard`.
CATEGORIES = ("standard", "adversarial", "multi_turn", "multi_intent", "hardening", "production")
DEFAULT_CATEGORY = "standard"

# M19 / probe set section 4: a reply may not quote a figure nothing produced.
# Candidates are dollar amounts and runs of four or more digits — small integers
# ("3 employees", "every 2 weeks", "Wednesday the 17th") are ordinary prose and
# flagging them would drown the signal.
MONEY_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d{1,2})?")
LONG_NUMBER_RE = re.compile(r"(?<![\d.\-/])\d{4,}(?![\d])")
# Stripped from the reply before the check: a date is not a claim about an amount,
# and the eval turns ask about dates constantly.
DATE_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b(?:19|20)\d{2}\b",
)
# A tracking number carries digits the resident typed; the guardrail that matters
# for those is "never invent a status", which must_not_contain covers.
TRACKING_RE = re.compile(r"\b[A-Z]{2,3}-\d{4}-\d{4,6}\b", re.IGNORECASE)
# The one figure the system prompt supplies rather than a tool: the City's general
# information line. Every referral and every "I don't have that" reply ends in it.
PROMPT_CONSTANTS = ("619-236-5555", "911")
# Categories where the check is scored. Elsewhere it is reported but not enforced,
# because the older items were written before the rule existed (PLAN.md §14).
NUMBERS_CHECKED_CATEGORIES = ("hardening",)


def keywords(text: str) -> list[str]:
    """Significant words: lowercase, longer than 3 chars, minus stopwords."""
    words = re.findall(r"[a-zA-Z][a-zA-Z\-']+", text.lower())
    return [w for w in words if len(w) > 3 and w not in STOPWORDS]


def keyword_match(expected: str, reply: str) -> tuple[bool, int]:
    """Loose overlap: >=2 significant words, or any multi-digit number, in common."""
    lowered = reply.lower()
    hits = sum(1 for w in set(keywords(expected)) if w in lowered)
    numbers = [n for n in NUMBER_RE.findall(expected) if len(n) > 1]
    number_hit = any(n in lowered or n.replace(",", "") in lowered for n in numbers)
    return (hits >= MIN_KEYWORDS or number_hit), hits


def parse_ids(raw: str | None) -> set[int] | None:
    """`--ids 56,57,58` as a set, or None when the flag was not given.

    Re-running three specific golden items after a fix is the common case and
    costs three turns instead of fifty-four; blanks and stray spaces are ignored
    so a copy-pasted list works.
    """
    if raw is None:
        return None
    ids = {int(part) for part in raw.replace(" ", "").split(",") if part}
    if not ids:
        raise ValueError("--ids was given but listed no item ids")
    return ids


def category_of(item: dict) -> str:
    """The item's category, defaulting to `standard` for items written before M9."""
    return item.get("category") or DEFAULT_CATEGORY


def turns_of(item: dict) -> list[str]:
    """The messages to send, in order. A single-turn item is just its question."""
    return list(item.get("turns") or [item["question"]])


def expected_tools(item: dict) -> list[str]:
    """Tools the item requires. `tools` (M9, many) wins over `tool` (one)."""
    if item.get("tools"):
        return list(item["tools"])
    if item.get("expect") == "tool" and item.get("tool"):
        return [item["tool"]]
    return []  # RAG and out-of-scope items neither require nor forbid a tool


def tool_match(item: dict, called: list[str]) -> bool:
    """Every expected tool must have been called at least once across the turns."""
    return all(name in called for name in expected_tools(item))


def guardrail_check(item: dict, reply: str) -> tuple[bool, list[str]]:
    """Literal phrase checks: banned phrases absent, and one required phrase present.

    Case-insensitive substring matching, because the point is to catch a model
    that speculates ("generally speaking...") or leaks a status it never looked
    up. Returns (ok, reasons) so a failure says which phrase decided it.
    """
    lowered = reply.lower()
    reasons: list[str] = []
    for phrase in item.get("must_not_contain") or []:
        if phrase.lower() in lowered:
            reasons.append(f"contains {phrase!r}")
    required = item.get("must_contain_any") or []
    if required and not any(phrase.lower() in lowered for phrase in required):
        reasons.append(f"none of {required!r}")
    return (not reasons), reasons


def evidence_text(item: dict, responses: list[dict]) -> str:
    """Everything the reply was entitled to get a number from, as one blob.

    That is: the tool calls of every turn (name, arguments and result summary, all
    the trace keeps), the cited sources, the resident's own words — a tracking
    number or a budget they typed is theirs, not an invention — and the two
    figures the system prompt itself supplies.
    """
    parts: list[str] = [*turns_of(item), *PROMPT_CONSTANTS]
    for response in responses:
        for call in (response.get("trace") or {}).get("tool_calls") or []:
            parts.append(json.dumps(call, default=str))
        for citation in response.get("citations") or []:
            parts.append(str(citation.get("text") or ""))
            parts.append(str(citation.get("doc_title") or ""))
    return " ".join(parts)


def _normalise(value: str) -> str:
    """A figure as bare digits: no `$`, no thousands separators, no trailing `.00`."""
    cleaned = value.replace("$", "").replace(",", "").replace(" ", "").strip()
    if cleaned.endswith(".00"):
        cleaned = cleaned[:-3]
    elif cleaned.endswith(".0"):
        cleaned = cleaned[:-2]
    return cleaned


def _supported(candidate: str, haystack: str) -> bool:
    """Is this figure present in the evidence, in any of the forms tools emit?

    A fee reaches the model as dollars in a summary (`$43.88`) but as cents in the
    JSON (`fee_cents: 4388`), so both spellings count as support.
    """
    forms = {candidate, f"{candidate}.00"}
    try:
        forms.add(str(int(round(float(candidate) * 100))))
    except ValueError:  # pragma: no cover - LONG_NUMBER_RE only matches digits
        pass
    return any(form in haystack for form in forms)


def numbers_from_tools(item: dict, responses: list[dict]) -> tuple[bool, list[str]]:
    """Flag money and 4+ digit figures in the reply that no tool or source produced.

    The failure this exists for is the model filling a gap with a plausible number —
    "the fee is about $1,200" when the estimator was never called. Dates and the
    tracking numbers the resident typed are stripped out first: they are not claims
    about an amount, and the guardrails that cover them are `must_not_contain`.
    """
    reply = (responses[-1] if responses else {}).get("reply") or ""
    stripped = DATE_RE.sub(" ", TRACKING_RE.sub(" ", reply))
    candidates = [_normalise(m) for m in MONEY_RE.findall(stripped)]
    candidates += [_normalise(m) for m in LONG_NUMBER_RE.findall(stripped)]
    haystack = evidence_text(item, responses).replace("$", "").replace(",", "")
    unsupported = sorted({c for c in candidates if c and not _supported(c, haystack)})
    return (not unsupported), unsupported


def numbers_checked(item: dict) -> bool:
    """Is the numbers check scored for this item? On by default for `hardening`."""
    default = category_of(item) in NUMBERS_CHECKED_CATEGORIES
    return bool(item.get("check_numbers", default))


def score_item(item: dict, responses: list[dict]) -> dict:
    """Mechanical checks against the turns of one item; the last reply is scored.

    Tool calls are unioned across every turn (a multi-turn item may call its
    tool on turn 1 and answer from history on turn 2); cost is summed over all
    turns so the run total is honest.
    """
    last = responses[-1] if responses else {}
    trace = last.get("trace") or {}
    reply = last.get("reply") or ""

    called: list[str] = []
    for response in responses:
        for call in (response.get("trace") or {}).get("tool_calls") or []:
            called.append(call.get("name"))

    intent_ok = trace.get("intent") == item["intent"]
    tool_ok = tool_match(item, called)
    citations_ok = bool(last.get("citations")) if item["expect"] == "rag" else True
    keyword_ok, hits = keyword_match(item["expected_answer"], reply)
    guardrail_ok, guardrail_reasons = guardrail_check(item, reply)
    # Always computed so the JSON shows the offenders, only scored where the
    # category asks for it — the pre-M19 items were not written against this rule.
    numbers_found, unsupported_numbers = numbers_from_tools(item, responses)
    numbers_ok = numbers_found or not numbers_checked(item)

    return {
        "id": item["id"],
        "split": item["split"],
        "category": category_of(item),
        "question": item["question"],
        "turns_sent": len(responses),
        "expected_intent": item["intent"],
        "actual_intent": trace.get("intent"),
        "expected_tool": item.get("tool"),
        "expected_tools": expected_tools(item),
        "actual_tools": called,
        "tier": trace.get("tier"),
        "model": trace.get("model"),
        "intent_ok": intent_ok,
        "tool_ok": tool_ok,
        "citations_ok": citations_ok,
        "keyword_ok": keyword_ok,
        "guardrail_ok": guardrail_ok,
        "guardrail_reasons": guardrail_reasons,
        "numbers_ok": numbers_ok,
        "numbers_checked": numbers_checked(item),
        "unsupported_numbers": unsupported_numbers,
        "keyword_hits": hits,
        "citations": len(last.get("citations") or []),
        "latency_ms": trace.get("latency_ms") or 0,
        "cost_usd": sum(((r.get("trace") or {}).get("cost_usd") or 0.0) for r in responses),
        "reply": reply,
        "error": trace.get("error"),
    }


def session_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    """One client, and therefore one cookie jar, for one eval item.

    M20 binds a session id to the browser that first used it, so the runner has
    to behave like a browser: the `resident_session` cookie minted on turn 1 has
    to come back on turn 2 or a multi-turn item's second message is a 403. A
    fresh client per item is also what keeps one item's cookie out of the next
    item's request, since each item invents a new session id.

    `transport` exists for the test, which must not open a socket.
    """
    return httpx.AsyncClient(timeout=180, cookies=httpx.Cookies(), transport=transport)


async def ask(base_url: str, item: dict) -> list[dict]:
    """Send every turn on one fresh session id, so history never leaks between items."""
    # No dot: POST /api/chat now requires ^[A-Za-z0-9_-]{8,64}$ (M14).
    session_id = f"eval-{item['id']}-{int(datetime.now().timestamp() * 1000)}"
    responses = []
    async with session_client() as client:
        for message in turns_of(item):
            response = await client.post(
                f"{base_url}/api/chat", json={"session_id": session_id, "message": message}
            )
            response.raise_for_status()
            responses.append(response.json())
    return responses


def summarise(rows: list[dict], label: str) -> str:
    """One printed line per split or category: the five rates, latency and cost."""
    if not rows:
        return f"{label:12s} n= 0"

    def pct(key: str) -> str:
        """That column's pass rate, right-aligned so the table lines up."""
        return f"{100 * sum(1 for r in rows if r[key]) / len(rows):5.1f}%"

    return (
        f"{label:12s} n={len(rows):2d}  intent={pct('intent_ok')}  tool={pct('tool_ok')}  "
        f"citations={pct('citations_ok')}  keywords={pct('keyword_ok')}  "
        f"guardrail={pct('guardrail_ok')}  numbers={pct('numbers_ok')}  "
        f"mean_latency={statistics.mean(r['latency_ms'] for r in rows):7.0f}ms  "
        f"cost=${sum(r['cost_usd'] for r in rows):.4f}"
    )


def flag(row: dict, key: str) -> str:
    """One column of the live table: Y for a pass, . for a fail."""
    return "Y" if row[key] else "."


def report(rows: list[dict]) -> list[str]:
    """The printed summary: per split, then per category, then overall."""
    lines = [summarise([r for r in rows if r["split"] == s], s) for s in ("dev", "holdout")]
    lines.append("")
    lines += [summarise([r for r in rows if r["category"] == c], c) for c in CATEGORIES]
    lines.append("")
    lines.append(summarise(rows, "all"))
    return lines


async def main() -> None:
    """Parse the flags, run the selected items, print the table and save the JSON."""
    parser = argparse.ArgumentParser(description="Run the golden eval set against a live API")
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--limit", type=int, default=None, help="only the first N items")
    parser.add_argument("--split", choices=["dev", "holdout"], default=None)
    parser.add_argument("--category", choices=list(CATEGORIES), default=None)
    parser.add_argument("--ids", default=None, help="comma-separated golden ids, e.g. 56,57,58")
    args = parser.parse_args()

    wanted = parse_ids(args.ids)
    items = json.loads(GOLDEN.read_text())
    if wanted is not None:
        items = [i for i in items if i["id"] in wanted]
        missing = sorted(wanted - {i["id"] for i in items})
        if missing:
            raise SystemExit(f"no golden item with id(s) {missing}")
    if args.split:
        items = [i for i in items if i["split"] == args.split]
    if args.category:
        items = [i for i in items if category_of(i) == args.category]
    if args.limit:
        items = items[: args.limit]

    rows: list[dict] = []
    header = (
        f"{'id':>3} {'category':12} {'split':7} {'intent':16} "
        f"{'in':2} {'tl':2} {'ct':2} {'kw':2} {'gr':2} {'nm':2} {'tier':8} {'ms':>6}"
    )
    print(header)
    print("-" * len(header))
    # No shared client: `ask` opens one per item so each session id gets its own
    # cookie jar (M20). The cost is one TCP connection per item, which is noise
    # next to a model call.
    for item in items:
        try:
            responses = await ask(args.base_url, item)
        except Exception as exc:  # noqa: BLE001 - a dead API is a result too
            responses = [{"reply": "", "citations": [], "trace": {"error": str(exc)}}]
        row = score_item(item, responses)
        rows.append(row)
        print(
            f"{row['id']:>3} {row['category']:12} {row['split']:7} "
            f"{str(row['actual_intent']):16} {flag(row, 'intent_ok'):2} "
            f"{flag(row, 'tool_ok'):2} {flag(row, 'citations_ok'):2} "
            f"{flag(row, 'keyword_ok'):2} {flag(row, 'guardrail_ok'):2} "
            f"{flag(row, 'numbers_ok'):2} {str(row['tier']):8} {row['latency_ms']:>6}"
        )

    print()
    for line in report(rows):
        print(line)

    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    path = RESULTS / f"{stamp}.json"
    path.write_text(
        json.dumps(
            {
                "run_at": stamp,
                "base_url": args.base_url,
                "n": len(rows),
                "summary": {
                    split: summarise([r for r in rows if r["split"] == split], split)
                    for split in ("dev", "holdout")
                },
                "by_category": {
                    category: summarise([r for r in rows if r["category"] == category], category)
                    for category in CATEGORIES
                },
                "overall": summarise(rows, "all"),
                "items": rows,
            },
            indent=2,
        )
    )
    print(f"\nwrote {path}")


if __name__ == "__main__":
    asyncio.run(main())
