"""Gemini tool declarations for the read-only project agent."""
from __future__ import annotations

from google.genai import types


def _tool(
    name: str,
    description: str,
    properties: dict | None = None,
    required: list[str] | None = None,
) -> types.FunctionDeclaration:
    return types.FunctionDeclaration(
        name=name,
        description=description,
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties=properties or {},
            required=required or [],
        ),
    )


def _read_declarations() -> list[types.FunctionDeclaration]:
    string = lambda description="": types.Schema(type=types.Type.STRING, description=description)
    integer = lambda description="": types.Schema(type=types.Type.INTEGER, description=description)
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


def declarations() -> list[types.FunctionDeclaration]:
    string = lambda description="": types.Schema(type=types.Type.STRING, description=description)
    return [
        *_read_declarations(),
        _tool(
            "answer_question",
            "Finish with the grounded answer that will be posted to project chat.",
            {"answer": string("Concise Markdown with source path and line citations")},
            ["answer"],
        ),
    ]


def task_draft_declarations() -> list[types.FunctionDeclaration]:
    string = lambda description="": types.Schema(type=types.Type.STRING, description=description)
    strings = lambda description="": types.Schema(
        type=types.Type.ARRAY,
        description=description,
        items=types.Schema(type=types.Type.STRING),
    )
    return [
        _tool(
            "draft_ticket",
            "Finish with one architecture-guide-grounded, reviewable kanban ticket draft.",
            {
                "title": string("Short imperative title, at most 80 characters"),
                "description": string("Concise Markdown that explains scope and acceptance criteria"),
                "priority": string("critical, high, medium, or low"),
                "category": string("engineering, bug, product, sales, general, manual, feat, or fix"),
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
