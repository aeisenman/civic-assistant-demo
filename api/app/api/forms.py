"""GET /api/forms/{type} — the field list the chat UI renders inline.

Called by the web app and by the start_application tool. The schema is derived
from the pydantic models in app/workflows/schemas.py, so extraction, validation
and rendering can never drift apart. Depends on: app.workflows.schemas only.
"""

from fastapi import APIRouter, HTTPException

from app.workflows.schemas import FIELD_MODELS, form_schema

router = APIRouter(tags=["forms"])

# Rendered once at import: the models are static, and start_application wants a
# plain dict it can hand straight back to the UI.
FORM_SCHEMAS: dict[str, dict] = {name: form_schema(name) for name in FIELD_MODELS}


@router.get("/api/forms/{form_type}")
async def get_form(form_type: str) -> dict:
    """The field schema the UI renders, straight from the pydantic model."""
    schema = FORM_SCHEMAS.get(form_type)
    if schema is None:
        raise HTTPException(status_code=404, detail=f"unknown form type '{form_type}'")
    return schema
