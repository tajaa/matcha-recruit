"""Gemini tool declarations for the draft-PR agent."""
from __future__ import annotations

from google.genai import types


def _tool(name: str, description: str, properties: dict | None = None, required: list[str] | None = None) -> types.FunctionDeclaration:
    return types.FunctionDeclaration(name=name, description=description, parameters=types.Schema(
        type=types.Type.OBJECT, properties=properties or {}, required=required or [],
    ))


def declarations() -> list[types.FunctionDeclaration]:
    string = lambda description="": types.Schema(type=types.Type.STRING, description=description)
    return [
        _tool("list_tickets", "List open engineering tickets. Use before choosing work."),
        _tool("read_ticket", "Read one ticket, including its checklist and associated element.", {"task_id": string()}, ["task_id"]),
        _tool("list_files", "List repository files. Optional path prefix.", {"prefix": string()}),
        _tool("read_file", "Read a repository file; includes staged edits if present.", {"path": string()}, ["path"]),
        _tool("search_repo", "Search the synced repository snapshot and paths.", {"query": string()}, ["query"]),
        _tool("write_file", "Stage a UTF-8 file edit. Protected paths are refused server-side.", {"path": string(), "content": string()}, ["path", "content"]),
        _tool("delete_file", "Stage a deletion. Protected paths are refused server-side.", {"path": string()}, ["path"]),
        _tool("post_update", "Post one concise progress update to the collab chat.", {"message": string()}, ["message"]),
        _tool("open_pr", "Commit all staged edits to a Huume branch and open a DRAFT pull request. Use only after a ticket was read.", {"title": string(), "body": string()}, ["title", "body"]),
        _tool("finish", "End the run with a concise message.", {"message": string()}, ["message"]),
    ]
