"""Application records and the state machine that advances them.

Called by app/api/applications.py, the background worker in app/main.py and the
create_service_request tool. Depends on: app.db.models for the rows,
app.storage for certificates and app.llm for PDF field extraction.
"""
