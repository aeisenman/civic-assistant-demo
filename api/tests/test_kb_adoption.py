"""Adopting a pre-M19 kb_documents row has to write that row's content hash.

Run by `uv run pytest`. Depends on: app.rag.ingest only — the fake session below
records the statements the loader sends and hands back canned results, the same
shape tests/test_migrations.py uses, so there is no Postgres and no embedding
call. The end-to-end proof is `python -m app.rag.ingest` against the real
database, which is how the defect was found.

The defect (M23): rows written before M19 have a NULL content_hash. `needs_ingest`
adopts them rather than re-embedding, which is right — but nothing wrote the hash,
so every later run adopted them again and four edited KB files were silently
ignored until the hashes were backfilled by hand.
"""

import pytest

from app.rag import ingest
from app.rag.ingest import DocState, content_hash

V1 = "---\ntitle: Trash\ntopic: trash\n---\n\n## Collection\n\nCarts go out on your service day.\n"
V2 = V1.replace("Carts go out on your service day.", "Carts go out by 6 a.m. on your service day.")


class _Result:
    """The two accessors the loader uses on a Result."""

    def __init__(self, value=None):
        self._value = value

    def scalar_one(self):
        return self._value

    def all(self):
        return []


class _Session:
    """Records every statement; answers the document INSERT with a row id."""

    def __init__(self):
        self.sql: list[str] = []
        self.commits = 0

    async def execute(self, statement, *args, **kwargs):
        self.sql.append(str(statement))
        return _Result(7)

    async def commit(self):
        self.commits += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def kb(tmp_path, monkeypatch):
    """One KB file on disk, a fake session, and no embedding call.

    Returns a callable: given what the database already holds for trash.md, it
    runs the loader and hands back (session, result).
    """
    (tmp_path / "trash.md").write_text(V1)
    monkeypatch.setattr(ingest, "KB_DIR", tmp_path)

    async def _embed(texts):
        return [[0.0] * 3 for _ in texts]

    monkeypatch.setattr(ingest, "embed", _embed)

    async def _run(existing: dict[str, DocState]):
        session = _Session()
        monkeypatch.setattr(ingest, "SessionLocal", lambda: session)

        async def _existing(_session):
            return existing

        monkeypatch.setattr(ingest, "_existing_docs", _existing)
        return session, await ingest._ingest_locked()

    return tmp_path, _run


async def test_adoption_writes_the_hash_onto_the_row(kb):
    """A NULL-hash row with chunks keeps them, and learns which version they are."""
    _, run = kb
    session, result = await run({"trash.md": DocState(doc_id=7, content_hash=None, chunks=12)})

    # Nothing was re-embedded: the chunks on file are the right ones.
    assert result == {}
    assert not any("DELETE" in sql for sql in session.sql)
    assert not any("INSERT INTO kb_chunks" in sql for sql in session.sql)
    # But the hash was written, in the same run, and committed.
    updates = [sql for sql in session.sql if sql.startswith("UPDATE kb_documents")]
    assert len(updates) == 1
    assert "content_hash" in updates[0]
    assert session.commits == 1


async def test_a_second_run_on_an_adopted_row_does_nothing(kb):
    """Idempotence: the hash the first run wrote makes the second run a no-op."""
    _, run = kb
    session, result = await run({"trash.md": DocState(7, content_hash(V1), chunks=12)})

    assert result == {}
    assert session.sql == []
    assert session.commits == 0


async def test_an_edit_after_adoption_is_re_ingested(kb):
    """The whole point of writing the hash: the next edit is finally detected.

    Before this, an adopted row was adopted again on every run and a changed file
    never reached the database — which is exactly what happened in M23.
    """
    tmp_path, run = kb
    (tmp_path / "trash.md").write_text(V2)
    session, result = await run({"trash.md": DocState(7, content_hash(V1), chunks=12)})

    assert result == {"trash.md": 1}
    # Replaced, not appended: the old document row goes first.
    assert any("DELETE FROM kb_documents" in sql for sql in session.sql)
    assert any("INSERT INTO kb_documents" in sql for sql in session.sql)
    assert any("INSERT INTO kb_chunks" in sql for sql in session.sql)
    assert session.commits == 1
