"""Pure containment helpers for the Huume code agent."""
from __future__ import annotations

import re

from app.matcha.services.matcha_work.github_service import EXCLUDED_DIRS

MAX_FILES = 25
MAX_FILE_BYTES = 80_000
MAX_TOTAL_BYTES = 400_000


def is_denied_path(path: str) -> bool:
    path = (path or "").strip().lstrip("/")
    if not path or ".." in path.split("/"):
        return True
    lowered = path.lower()
    parts = path.split("/")
    return (
        parts[0] in {".github", "secrets", "deploy"}
        or any(part in EXCLUDED_DIRS for part in parts[:-1])
        or lowered.startswith(".env")
        or lowered.endswith(".pem")
    )


def branch_name(task_id: str, title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "work").lower()).strip("-")[:48] or "work"
    return f"huume/{str(task_id)[:8]}-{slug}"


class WorkingSet:
    """In-memory read-your-writes staging area with hard server-side caps."""
    def __init__(self) -> None:
        self.files: dict[str, str] = {}
        self.deletes: set[str] = set()

    def _check(self, path: str, content: str | None = None) -> str:
        path = (path or "").strip().lstrip("/")
        if is_denied_path(path):
            raise ValueError(f"Refusing protected path: {path}")
        if content is not None and len(content.encode("utf-8")) > MAX_FILE_BYTES:
            raise ValueError("A staged file may not exceed 80 KB.")
        prospective = dict(self.files)
        if content is not None:
            prospective[path] = content
        elif path not in prospective:
            prospective[path] = ""
        touched = set(prospective) | self.deletes | {path}
        if len(touched) > MAX_FILES:
            raise ValueError("A run may touch at most 25 files.")
        if sum(len(value.encode("utf-8")) for value in prospective.values()) > MAX_TOTAL_BYTES:
            raise ValueError("A run may stage at most 400 KB.")
        return path

    def write(self, path: str, content: str) -> None:
        path = self._check(path, content)
        self.files[path] = content
        self.deletes.discard(path)

    def delete(self, path: str) -> None:
        path = self._check(path)
        self.files.pop(path, None)
        self.deletes.add(path)

    def read(self, path: str, fallback: str | None) -> str | None:
        path = (path or "").strip().lstrip("/")
        if path in self.deletes:
            return None
        return self.files.get(path, fallback)
