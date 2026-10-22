"""Every tool must produce a schema, and dispatch must never raise at the caller."""

import pytest

from app.tools.registry import TOOLS, dispatch, openai_schemas


def test_every_tool_produces_an_openai_schema():
    schemas = openai_schemas(list(TOOLS))
    assert len(schemas) == len(TOOLS)
    for schema in schemas:
        assert schema["type"] == "function"
        function = schema["function"]
        assert function["name"] in TOOLS
        assert function["description"]
        assert function["parameters"]["type"] == "object"


def test_unknown_names_are_dropped_not_raised():
    assert openai_schemas(["get_referral", "nope"]) and len(openai_schemas(["nope"])) == 0


async def test_dispatch_rejects_an_unknown_tool():
    result = await dispatch("teleport", {}, None)
    assert "unknown tool" in result["error"]


async def test_dispatch_returns_an_error_dict_on_bad_arguments():
    # A missing required field must not raise: the model gets another turn.
    result = await dispatch("get_trash_schedule", {}, None)
    assert "invalid arguments" in result["error"]
    assert result["summary"] == result["error"]


async def test_dispatch_reports_a_tool_failure_as_an_error():
    # session=None blows up inside the tool; the loop still gets a dict.
    result = await dispatch("get_trash_schedule", {"address": "4521 Adams Ave"}, None)
    assert "error" in result


@pytest.mark.parametrize("name", sorted(TOOLS))
def test_tool_specs_are_well_formed(name):
    spec = TOOLS[name]
    assert spec.name == name
    assert callable(spec.fn)
    assert "summary" not in spec.model.model_fields  # summary is output, not input
