"""Responses function tools for the read-only project agent.

JSON Schema, sent to the OpenAI Responses API as-is — these used to be
google-genai `FunctionDeclaration`s translated at the client edge, which
silently dropped anything the translator did not know about.
"""
from __future__ import annotations

from typing import Any


def _tool(
    name: str,
    description: str,
    properties: dict | None = None,
    required: list[str] | None = None,
) -> dict[str, Any]:
    parameters: dict[str, Any] = {"type": "object"}
    # Empty is omitted rather than emitted, matching what the provider has
    # actually been receiving through the retired translator.
    if properties:
        parameters["properties"] = properties
    if required:
        parameters["required"] = list(required)
    return {
        "type": "function", "name": name,
        "description": description, "parameters": parameters,
    }


def _read_declarations() -> list[dict[str, Any]]:
    string = lambda description="": {"type": "string", **({"description": description} if description else {})}
    integer = lambda description="": {"type": "integer", **({"description": description} if description else {})}
    return [
        _tool(
            "list_files",
            "List repository file paths, optionally beneath a path prefix.",
            {"prefix": string("Optional repository-relative prefix")},
        ),
        _tool(
            "search_repo",
            "Search the project's synced repository snapshot and live file paths.",
            {"query": string("A focused identifier, route, label, or feature term")},
            ["query"],
        ),
        _tool(
            "read_file",
            "Read a bounded, line-numbered window from one repository file.",
            {
                "path": string("Repository-relative file path"),
                "start_line": integer("First line, 1-based"),
                "end_line": integer("Last line, inclusive; at most 400 lines are returned"),
            },
            ["path"],
        ),
    ]


def declarations() -> list[dict[str, Any]]:
    string = lambda description="": {"type": "string", **({"description": description} if description else {})}
    return [
        *_read_declarations(),
        _tool(
            "answer_question",
            "Finish with the grounded answer that will be posted to project chat.",
            {"answer": string("Concise Markdown with source path and line citations")},
            ["answer"],
        ),
    ]


def task_draft_declarations() -> list[dict[str, Any]]:
    string = lambda description="": {"type": "string", **({"description": description} if description else {})}
    strings = lambda description="": {
        "type": "array",
        **({"description": description} if description else {}),
        "items": {"type": "string"},
    }
    return [
        _tool(
            "draft_ticket",
            "Finish with one architecture-guide-grounded, reviewable kanban ticket draft.",
            {
                "title": string("Short imperative title, at most 80 characters"),
                "description": string("Concise Markdown that explains scope and acceptance criteria"),
                "priority": string("critical, high, medium, or low"),
                "category": string(
                    "engineering, bug, product, sales, general, research, manual, feat, or fix. "
                    "Use research when the ask is to look into, evaluate, compare, or find out "
                    "whether something, with a written report as the deliverable and no code change."
                ),
                "board_column": string("todo, in_progress, review, or done; normally todo"),
                "assignee_name": string("Exact collaborator name, or an empty string"),
                "element_name": string("Exact project element name, or an empty string"),
                "subtasks": strings("Three to six short, ordered, verifiable checklist steps"),
                "sources": strings("CLAUDE.md or AGENTS.md citations as path:line or path:start-end"),
            },
            [
                "title", "description", "priority", "category", "board_column",
                "subtasks", "sources",
            ],
        ),
    ]
