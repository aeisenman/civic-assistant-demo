"""HTTP routers, one module per resource; app/main.py includes each of them.

Called by FastAPI; nothing in the app imports these modules except main.py.
Depends on: app.db.engine for a session, and the agents/workflows underneath.
"""
