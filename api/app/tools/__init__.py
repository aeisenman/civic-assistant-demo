"""Function-calling tools: one module per domain, assembled in registry.py.

Called by app/agents/chat.py, which asks registry.py for the schemas the model
sees and dispatches the calls it makes. Depends on: app.db.models for the seed
tables and app.live.* for the real City map services.
"""
