"""One isolated media child, supervised by the queue worker's process deadline."""
import asyncio
import sys
from uuid import UUID

from app.config import load_recap_worker_settings
from .reconcile import cleanup_job, render_job


def main():
    load_recap_worker_settings()
    kind, raw_id = sys.argv[1:]
    operation = {"render": render_job, "cleanup": cleanup_job}[kind]
    asyncio.run(operation(UUID(raw_id)))


if __name__ == "__main__":
    main()
