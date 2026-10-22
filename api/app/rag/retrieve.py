"""Hybrid retrieval: pgvector cosine + Postgres full-text, fused with RRF.

Called by app/agents/chat.py for every non-smalltalk turn. Depends on: the
kb_chunks rows written by app/rag/ingest.py and app.llm.client.embed for the
query vector. Dense search finds paraphrases; full-text pins exact terms like
"SB-1186"; RRF needs no score calibration between the two.
"""

import logging
from dataclasses import asdict, dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import embed

log = logging.getLogger(__name__)

CANDIDATES = 8  # per retriever, before fusion
RRF_K = 60  # standard reciprocal-rank-fusion constant
MIN_TOPIC_HITS = 2  # below this, the topic filter was too narrow


@dataclass
class Hit:
    """One retrieved passage, rendered into the prompt as a numbered source."""

    chunk_id: int
    doc_title: str
    source_url: str | None
    topic: str | None
    text: str
    score: float

    def as_dict(self) -> dict:
        """Plain dict for the citation payload the API returns."""
        return asdict(self)


def rrf_scores(rank_lists: list[list[int]], k: int = RRF_K) -> dict[int, float]:
    """Sum 1/(k + rank) for every id, over every list it appears in."""
    scores: dict[int, float] = {}
    for ranked in rank_lists:
        for rank, item in enumerate(ranked, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return scores


def rrf(rank_lists: list[list[int]], k: int = RRF_K) -> list[int]:
    """Reciprocal rank fusion -> ids best first.

    Pure so it can be tested without a database. Ties break on first appearance
    across the input lists, which makes the order deterministic.
    """
    scores = rrf_scores(rank_lists, k)
    first_seen: dict[int, int] = {}
    position = 0
    for ranked in rank_lists:
        for item in ranked:
            first_seen.setdefault(item, position)
            position += 1
    return sorted(scores, key=lambda i: (-scores[i], first_seen[i]))


_SELECT = """
SELECT c.id, c.text, d.title, d.source_url, d.topic
FROM kb_chunks c JOIN kb_documents d ON d.id = c.document_id
"""

# The topic filter is spliced in rather than bound, because a bound NULL check
# needs a cast that asyncpg's numbered parameters do not accept inside text().
_VECTOR_SQL = (
    _SELECT
    + """
WHERE TRUE {topic_filter}
ORDER BY c.embedding <=> CAST(:vec AS vector)
LIMIT :limit
"""
)

_TEXT_SQL = (
    _SELECT
    + """
WHERE c.tsv @@ plainto_tsquery('english', :q) {topic_filter}
ORDER BY ts_rank_cd(c.tsv, plainto_tsquery('english', :q)) DESC
LIMIT :limit
"""
)


# ~1,500 tokens: well inside every provider's embedding limit and longer than
# any real resident question.
MAX_QUERY_CHARS = 6000


async def _run(session: AsyncSession, query: str, vector: list[float], topic: str | None):
    """Both halves of the hybrid search under one topic filter."""
    topic_filter = "AND d.topic = :topic" if topic else ""
    params: dict = {"limit": CANDIDATES}
    if topic:
        params["topic"] = topic
    dense = (
        (
            await session.execute(
                text(_VECTOR_SQL.format(topic_filter=topic_filter)),
                {**params, "vec": "[" + ",".join(map(str, vector)) + "]"},
            )
        )
        .mappings()
        .all()
    )
    lexical = (
        (await session.execute(text(_TEXT_SQL.format(topic_filter=topic_filter)), {**params, "q": query}))
        .mappings()
        .all()
    )
    return dense, lexical


async def retrieve(session: AsyncSession, query: str, topic: str | None = None, k: int = 5) -> list[Hit]:
    """Top-k passages for `query`, optionally restricted to one KB topic.

    A topic filter that yields fewer than two hits is dropped and the search is
    rerun: a narrow filter is worse than a slightly off-topic source.
    """
    if not query.strip():
        return []
    # Titan (and every other embedding model) has an input ceiling — 8192 tokens
    # — and a resident who pastes a long notice into the chat used to get the
    # generic "something went wrong" apology because the whole turn died on the
    # embedding call. The first few thousand characters carry the question.
    query = query[:MAX_QUERY_CHARS]
    vector = (await embed([query]))[0]

    dense, lexical = await _run(session, query, vector, topic)
    if topic is not None and len({r["id"] for r in dense} | {r["id"] for r in lexical}) < MIN_TOPIC_HITS:
        log.info("retrieve: topic=%s too narrow, retrying unfiltered", topic)
        dense, lexical = await _run(session, query, vector, None)

    rows = {r["id"]: r for r in list(dense) + list(lexical)}
    rank_lists = [[r["id"] for r in dense], [r["id"] for r in lexical]]
    scores = rrf_scores(rank_lists)
    ordered = rrf(rank_lists)
    hits = []
    for chunk_id in ordered[:k]:
        row = rows[chunk_id]
        hits.append(
            Hit(
                chunk_id=chunk_id,
                doc_title=row["title"],
                source_url=row["source_url"],
                topic=row["topic"],
                text=row["text"],
                score=round(scores[chunk_id], 6),
            )
        )
    return hits
