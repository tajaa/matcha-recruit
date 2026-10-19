"""A model phase's `finish` tool, and reading what the model sent to it.

Job search and research tasks end each model phase with one `finish` call.
The answer's fields are the tool's own parameters. Wrapped in one `result`
object, Claude Haiku now and then sent that object as JSON text: in 4 of 12
job search plan and approach runs on prod (2026-10-15..18) it did, and each
was refused twice and failed. `answer` still reads a `result` object (how the
tools were shaped before, and how a model may still send one), and any list
or object sent as JSON text.
"""
from __future__ import annotations

import json
from typing import Any

from .registry import AgentTool


def tool(label: str, description: str, schema: dict) -> AgentTool:
    """The phase's `finish` tool: `schema` is the answer itself."""
    return AgentTool(
        name="finish", effect="finish", description=description, parameters=schema,
        step_kind="finish", describe=lambda _args: label,
    )


def answer(args: Any) -> dict:
    """The finish call's own fields, or its `result` object, with each list or
    object sent as JSON text read as itself. A ValueError (which gets the
    model one repair) when there is no object to read."""
    if not isinstance(args, dict):
        raise ValueError("`result` must be an object")
    result = args.get("result", args)
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except ValueError:
            raise ValueError("The answer was text, and not valid JSON: send its fields directly, "
                             "as an object, not as a string") from None
    if not isinstance(result, dict):
        raise ValueError("`result` must be an object")
    return {key: unquoted(value) for key, value in result.items()}


def unquoted(value: Any) -> Any:
    """A list or object a model sent as JSON text ("[{...}]"), as itself; any
    other text as it is (no contract field's text starts that way)."""
    if isinstance(value, str) and value.lstrip()[:1] in ("[", "{"):
        try:
            parsed = json.loads(value)
        except ValueError:
            return value
        if isinstance(parsed, (list, dict)):
            return parsed
    return value


def items(result: dict, key: str) -> list:
    """A list field of the answer, [] when it is missing, each element sent as
    JSON text read as itself. A ValueError (the model's one repair) when the
    field is text or not a list: text here is a list sent as JSON that isn't
    valid (a cover letter's quotes left unescaped, say). Read letter by letter,
    it came back as "give an approach for each job shown, by its short id",
    which points the model at its ids, not its JSON."""
    value = result.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        raise ValueError(f"`{key}` came as text, not a list: send it as a list of objects, "
                         "not as a string of JSON")
    if not isinstance(value, list):
        raise ValueError(f"`{key}` must be a list")
    return [unquoted(item) for item in value]
