"""Turns api/kb/*.md into kb_documents + kb_chunks rows with embeddings.

Called by the lifespan in app/main.py when INGEST_KB_ON_STARTUP is true and the
table is empty, and by `python -m app.rag.ingest --force` to re-ingest. Depends
on: app.llm.client.embed for vectors and Postgres to_tsvector for the keyword
half of the hybrid search.
"""

import argparse
import asyncio
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models
from app.db.engine import SessionLocal, engine
from app.llm.client import embed

log = logging.getLogger(__name__)

KB_DIR = Path(__file__).resolve().parents[2] / "kb"

# A different fixed key from the migration lock (4815162342 in app/db/migrations.py),
# so a replica applying migrations and a replica ingesting the KB do not block
# each other for no reason.
INGEST_LOCK_KEY = 4815162343

# Windows for prose sections. FAQ answers are already the right size, so only
# ## Overview / ## How it works bodies get split.
WINDOW_CHARS = 1200
OVERLAP_CHARS = 150


@dataclass
class Chunk:
    """One retrievable passage plus the heading it came from."""

    heading: str
    body: str

    def stored_text(self, title: str) -> str:
        """Retrieval returns text without its document, so carry context inline."""
        return f"{title} — {self.heading}\n{self.body}"


def parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    """Split `--- key: value --- body`. Hand-rolled: pyyaml is not a dependency.

    The KB files only ever use flat `key: value` pairs, so a full YAML parser
    would buy nothing.
    """
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, raw
    meta: dict[str, str] = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return meta, "\n".join(lines[i + 1 :])
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta, ""  # unterminated frontmatter: treat the whole file as metadata


def _window(paragraphs: list[str]) -> list[str]:
    """Pack paragraphs into ~WINDOW_CHARS windows with ~OVERLAP_CHARS of overlap.

    Breaking only on paragraph boundaries keeps sentences intact; the overlap is
    whole trailing paragraphs so a fact spanning a boundary appears in both.
    """
    windows: list[str] = []
    current: list[str] = []
    size = 0
    for para in paragraphs:
        if current and size + len(para) > WINDOW_CHARS:
            windows.append("\n\n".join(current))
            # Carry back whole trailing paragraphs that fit inside the overlap.
            tail: list[str] = []
            tail_size = 0
            for prev in reversed(current):
                if tail_size + len(prev) > OVERLAP_CHARS:
                    break
                tail.insert(0, prev)
                tail_size += len(prev)
            current, size = tail, tail_size
        current.append(para)
        size += len(para)
    if current:
        windows.append("\n\n".join(current))
    return windows


def _paragraphs(body: str) -> list[str]:
    return [p.strip() for p in body.split("\n\n") if p.strip()]


def split_markdown(body: str) -> list[Chunk]:
    """One chunk per `### Q:` block; `##` prose bodies windowed (PLAN.md §7)."""
    chunks: list[Chunk] = []
    section = "Overview"
    heading = section
    buffer: list[str] = []
    is_faq = False

    def flush() -> None:
        """Emit the buffered section: a whole FAQ answer, or windowed paragraphs."""
        joined = "\n".join(buffer).strip()
        if not joined:
            return
        if is_faq:
            chunks.append(Chunk(heading, joined))
        else:
            for window in _window(_paragraphs(joined)):
                chunks.append(Chunk(heading, window))

    for line in body.splitlines():
        if line.startswith("### "):
            flush()
            buffer = []
            heading = line[4:].strip()
            is_faq = True
        elif line.startswith("## "):
            flush()
            buffer = []
            section = line[3:].strip()
            heading = section
            is_faq = False
        else:
            buffer.append(line)
    flush()
    return chunks


def content_hash(raw: str) -> str:
    """sha256 of a KB file's bytes: the identity of one version of one document."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DocState:
    """What the database already holds for one kb/*.md file."""

    doc_id: int
    content_hash: str | None
    chunks: int


def needs_ingest(digest: str, existing: DocState | None) -> bool:
    """Should this file be (re-)ingested? The whole of A20's decision, in one place.

    Pure so it can be unit-tested without Postgres. A document is re-ingested when
    it is new, when the file changed, or when its row survived but its chunks did
    not — which is what "crashed half way through an ingest" looks like now that
    each document commits on its own.

    A row from before M19 has no `content_hash`. If it still has chunks we adopt
    it as the current version rather than re-embedding: those rows were produced
    by the very files being hashed, and re-ingesting would renumber chunk ids that
    existing traces point at. From the next edit onwards the hash governs.
    """
    if existing is None or existing.chunks == 0:
        return True
    if existing.content_hash is None:
        return False
    return existing.content_hash != digest


async def _existing_docs(session: AsyncSession) -> dict[str, DocState]:
    """filename -> what is on file, with the chunk count, for every KB document.

    Keyed on filename. Rows written before M19 have none, so they are keyed on
    `topic`, which this loader has always set to the file's stem — that is what
    lets the existing 120 chunks be recognised instead of re-embedded.
    """
    rows = (
        await session.execute(
            select(
                models.KbDocument.id,
                models.KbDocument.filename,
                models.KbDocument.topic,
                models.KbDocument.content_hash,
                func.count(models.KbChunk.id),
            )
            .outerjoin(models.KbChunk, models.KbChunk.document_id == models.KbDocument.id)
            .group_by(models.KbDocument.id)
        )
    ).all()
    return {
        (filename or f"{topic}.md"): DocState(doc_id, digest, int(count))
        for doc_id, filename, topic, digest, count in rows
    }


async def ingest_kb(*, force: bool = False) -> dict[str, int]:
    """Ingest the knowledge base under a cluster-wide lock. See `_ingest_locked`.

    `docker compose up --scale api=2` starts two processes that both read an
    empty-looking `kb_documents`, both decide every file needs ingesting, and
    both write it: duplicate chunks, duplicated citations, double embedding
    spend. Migrations were already serialised this way (app/db/migrations.py);
    ingest was the one startup step that was not.

    A dedicated connection holds the lock, exactly as run_migrations does: an
    advisory lock belongs to a Postgres *session*, and an ORM session hands its
    connection back to the pool on every commit — the lock would be stranded on
    a pooled connection while the work carried on somewhere else.
    """
    async with engine.connect() as lock_conn:
        await lock_conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": INGEST_LOCK_KEY})
        try:
            return await _ingest_locked(force=force)
        finally:
            await lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": INGEST_LOCK_KEY})


async def _ingest_locked(*, force: bool = False) -> dict[str, int]:
    """Ingest every kb/*.md that is new, changed or half-written. Idempotent per file.

    Before M19 this skipped the whole run whenever a single chunk existed, so a
    knowledge base left half-ingested by a crash stayed half-ingested for ever and
    `/health` reported 60 of 120 chunks with nothing to fix it (probe A20). Now
    each file is matched by name and content hash, re-ingested only when it has to
    be, and committed on its own — so an interrupted run is resumed by the next
    one instead of being rolled back or duplicated.
    """
    async with SessionLocal() as session:
        if force:
            # CASCADE clears kb_chunks; RESTART IDENTITY keeps ids readable.
            await session.execute(text("TRUNCATE TABLE kb_documents RESTART IDENTITY CASCADE"))
            await session.commit()
        existing = {} if force else await _existing_docs(session)

        result: dict[str, int] = {}
        # Pre-M19 rows whose hash this run wrote; reported so an operator can see it.
        adopted: list[str] = []
        for path in sorted(KB_DIR.glob("*.md")):
            raw = path.read_text()
            digest = content_hash(raw)
            state = existing.get(path.name)
            if not needs_ingest(digest, state):
                if state is not None and state.content_hash is None:
                    # Adoption (see needs_ingest): a pre-M19 row keeps its chunks,
                    # but it has to learn what version those chunks are, or every
                    # later run re-adopts it and a genuine edit is never noticed.
                    # That is exactly what happened to the shared database in M23:
                    # four edited KB files were silently ignored until the hashes
                    # were backfilled by hand. Written before the `continue`, and
                    # committed with it, so the adoption is never half-done.
                    await session.execute(
                        update(models.KbDocument)
                        .where(models.KbDocument.id == state.doc_id)
                        .values(content_hash=digest)
                    )
                    await session.commit()
                    log.info("ingest: %s adopted, content hash recorded", path.name)
                    adopted.append(path.name)
                    continue
                log.info("ingest: %s unchanged, skipping", path.name)
                continue
            if state is not None:
                # Replace rather than append: two copies of a chunk would both
                # come back from retrieval and the model would cite them twice.
                await session.execute(delete(models.KbDocument).where(models.KbDocument.id == state.doc_id))

            meta, body = parse_frontmatter(raw)
            doc_id = (
                await session.execute(
                    insert(models.KbDocument)
                    .values(
                        title=meta.get("title", path.stem),
                        topic=meta.get("topic", path.stem),
                        source_url=meta.get("source_url"),
                        filename=path.name,
                        content_hash=digest,
                    )
                    .returning(models.KbDocument.id)
                )
            ).scalar_one()

            chunks = split_markdown(body)
            texts = [c.stored_text(meta.get("title", path.stem)) for c in chunks]
            vectors = await embed(texts)  # client batches at 32
            for index, (chunk_text, vector) in enumerate(zip(texts, vectors, strict=True)):
                await session.execute(
                    insert(models.KbChunk).values(
                        document_id=doc_id,
                        chunk_index=index,
                        text=chunk_text,
                        embedding=vector,
                        # tsv is computed in Postgres so the analyzer matches the query side.
                        tsv=func.to_tsvector("english", chunk_text),
                    )
                )
            # One commit per document: the unit of resumability is a whole file.
            await session.commit()
            result[path.name] = len(chunks)
            log.info("ingest: %s -> %d chunks", path.name, len(chunks))

        if adopted:
            log.info("ingest: adopted %d pre-hash document(s): %s", len(adopted), ", ".join(adopted))
        return result


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Ingest api/kb/*.md into kb_chunks")
    parser.add_argument("--force", action="store_true", help="re-ingest even if chunks exist")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    counts = await ingest_kb(force=args.force)
    print(f"ingested {sum(counts.values())} chunks from {len(counts)} files: {counts}")


if __name__ == "__main__":
    asyncio.run(_main())
