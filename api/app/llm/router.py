"""Intent classification and model-tier selection — the routing story.

Called by app/agents/chat.py at the top of every turn. Depends on:
app.llm.client.chat_json at the SMALL tier. Rules, not vibes: the only
non-model shortcut is a tracking-number regex, because the prefix *is* the
intent. No other keyword heuristics — the evals measure the classifier, and
keyword patches would hide what it actually does (PLAN.md §14).
"""

import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

from app.llm.client import Tier, chat_json

log = logging.getLogger(__name__)

INTENTS = (
    "permits",
    "business",
    "trash",
    "service_request",
    "events",
    "general",
    "smalltalk",
)

# PRM-2026-000101 / BTC-2026-000201 / SR-2026-000301 / STR-2026-000401: the
# prefix names the domain. STR (M24's short-term rental licence) maps to
# `general`, because housing questions have no intent of their own — `general`
# is the profile that answers them and it holds every tool.
# STR before SR in the alternation: `SR` would otherwise match the "SR" inside
# "STR-2026-000401" and route a licence question to service requests.
TRACKING_RE = re.compile(r"\b(PRM|BTC|STR|SR)-\d{4}-\d{6}\b", re.IGNORECASE)
PREFIX_INTENT = {"PRM": "permits", "BTC": "business", "SR": "service_request", "STR": "general"}

LOW_CONFIDENCE = 0.6


class Classification(BaseModel):
    """What the SMALL model returns for one resident message."""

    intent: Literal["permits", "business", "trash", "service_request", "events", "general", "smalltalk"]
    confidence: float = Field(ge=0.0, le=1.0)
    complexity: Literal["low", "medium", "high"]
    secondary_intents: list[str] = Field(default_factory=list)


SYSTEM_PROMPT = """You classify messages sent to the City of San Diego's resident assistant.
Reply with JSON only.

Intents:
- permits: building/construction permits, permit fees, permit status, inspections.
  e.g. "Do I need a permit to remodel my bathroom?" / "What's the status of PRM-2026-000102?"
- business: starting or running a business, business tax certificates, licences, short-term rentals.
  e.g. "How much is a business tax certificate for 5 employees?" / "Can I rent my house on Airbnb?"
- trash: collection days, recycling, organics, bins, bulky items, the trash fee.
  e.g. "What day is my trash picked up?" / "Can pizza boxes go in recycling?"
- service_request: reporting a problem the City should fix, or the status of such a report.
  e.g. "There's a pothole on my street." / "My trash wasn't collected today."
- events: City events, council meetings, farmers markets, library programs, event permits.
  e.g. "When is the next council meeting?" / "How much is a special event permit?"
- general: other City services and things another agency handles — parking (citations, meters,
  permits, RV/oversized vehicles, street sweeping), water and sewer utility bills, housing
  (short-term rentals, ADUs, tenant help), libraries, council districts.
  e.g. "How do I pay my water bill?" / "How do I register to vote?" /
  "Can I park my RV on the street overnight?" / "How do I contest a parking ticket?" /
  "What are the short-term rental rules?"
- smalltalk: greetings, thanks, or chat with no city question in it.
  e.g. "Hi there" / "Thanks, that's all I needed."

confidence: 0-1, how sure you are of the primary intent.
complexity: "low" for a single fact or lookup, "medium" for a multi-step explanation,
"high" when the resident asks several things at once or the answer needs judgement.
secondary_intents: other intents the message also touches; empty list if there is only one."""


def _override(message: str) -> Classification | None:
    """A tracking number in the message settles the intent without a model call."""
    match = TRACKING_RE.search(message)
    if not match:
        return None
    intent = PREFIX_INTENT[match.group(1).upper()]
    log.info("router: tracking-number override -> %s", intent)
    return Classification(intent=intent, confidence=1.0, complexity="low", secondary_intents=[])


async def classify(message: str, recent_user_messages: list[str] | None = None) -> Classification:
    """Classify one message at the SMALL tier, with recent turns for context."""
    override = _override(message)
    if override is not None:
        return override

    context = ""
    if recent_user_messages:
        joined = "\n".join(f"- {m}" for m in recent_user_messages[-3:])
        context = f"\n\nEarlier messages from this resident:\n{joined}"
    result = await chat_json(
        Tier.SMALL,
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Message: {message}{context}"},
        ],
        Classification,
        temperature=0.0,
        max_tokens=200,
    )
    return result  # type: ignore[return-value]


def select_tier(c: Classification) -> tuple[Tier, str]:
    """Pick the answering tier and say why in one line (it goes in the trace)."""
    if c.intent == "smalltalk":
        return Tier.SMART, "smalltalk: smart tier, no tools and no retrieval"
    if c.confidence < LOW_CONFIDENCE:
        return Tier.ESCALATE, f"escalated: confidence {c.confidence:.2f} < {LOW_CONFIDENCE}"
    if c.complexity == "high":
        return Tier.ESCALATE, "escalated: classifier rated the turn high complexity"
    if len(c.secondary_intents) >= 1:
        return Tier.ESCALATE, (f"escalated: multiple intents ({c.intent} + {', '.join(c.secondary_intents)})")
    return Tier.SMART, f"smart: single {c.intent} intent, confidence {c.confidence:.2f}"
