"""Database access: the async engine/session factory and the ORM models.

Imported by nearly every module that touches data, and by app/main.py at
startup. Depends on: SQLAlchemy 2 (asyncio), asyncpg and pgvector.
"""
