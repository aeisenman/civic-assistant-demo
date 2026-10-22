"""Hybrid retrieval over api/kb/*.md: ingest.py fills the tables, retrieve.py reads them.

Ingest is called by app/main.py at startup; retrieve by app/agents/chat.py on
every non-smalltalk turn. Depends on: pgvector for the embeddings and Postgres
full-text search for the lexical half of the RRF blend.
"""
