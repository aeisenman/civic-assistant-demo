"""Loads api/seed_data/*.json into the demo tables at startup.

Called by app/main.py when SEED_ON_STARTUP is true. Depends on: app.db.models
and the JSON files, whose shapes are fixed in PLAN.md section 13.
"""
