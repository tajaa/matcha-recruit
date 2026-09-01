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


def declarations() -> list[types.FunctionDeclaration]:
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
        _tool(
            "answer_question",
            "Finish with the grounded answer that will be posted to project chat.",
            {"answer": string("Concise Markdown with source path and line citations")},
            ["answer"],
        ),
    ]
