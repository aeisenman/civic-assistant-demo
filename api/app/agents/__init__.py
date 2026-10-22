"""Agent profiles (prompt + tools + KB topic) and the chat orchestrator.

Called by app/api/chat.py for both the buffered and the streaming turn.
Depends on: app.llm for the model calls, app.rag for sources, app.tools for
the function-calling catalogue.
"""
