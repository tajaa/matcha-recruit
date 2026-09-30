"""`ask_user`: the one way a run can stop and ask.

Calling it ends the run. The question is posted as a card in the chat; the
person's reply is simply the next message, and starts the next run with the
whole conversation replayed. There is no suspended run waiting anywhere.
"""
from __future__ import annotations

from .registry import AgentTool

ASK_USER = AgentTool(
    name="ask_user",
    effect="ask",
    description=(
        "Ask the person ONE question when you cannot go on without their answer "
        "(a missing date, which of two people they meant). This ends your turn; you "
        "continue when they reply. Do not ask for anything you can find out yourself, "
        "and do not ask for permission: acting is already allowed."
    ),
    parameters={
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "One short, specific question"},
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Up to 4 short answers to offer as buttons. Optional.",
            },
        },
        "required": ["question"],
    },
    step_kind="ask",
)
