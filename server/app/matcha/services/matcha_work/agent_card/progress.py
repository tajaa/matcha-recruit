"""The card's progress line, as the runtime's progress sink."""
from __future__ import annotations

from uuid import UUID

from . import board


class CardProgress:
    """Writes `mw_tasks.progress_note` and fans the card out to open boards."""

    def __init__(self, *, project_id: UUID, task_id: UUID) -> None:
        self.project_id = project_id
        self.task_id = task_id

    async def note(self, text: str, *, force: bool = False) -> None:
        # Looked up on the module at call time, so a patched board is the one used.
        row = await board.set_progress(self.task_id, text)
        if row:
            await board.publish_task_updated(self.project_id, row)

    async def step(self, seq: int, kind: str, label: str, status: str) -> None:
        return None
