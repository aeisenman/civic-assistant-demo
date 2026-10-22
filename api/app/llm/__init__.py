"""The one place a model is called: the traced client and the tier router.

Imported by app/agents/* and app/workflows/* — nothing calls an SDK directly, so
every request is costed and traced. Depends on: the openai client and app.config.
"""
