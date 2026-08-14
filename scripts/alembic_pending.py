#!/usr/bin/env python
"""Print the revisions that `alembic upgrade heads` WOULD apply, oldest first.

Offline: reads the migration scripts on disk and the revision ids the caller
says the database is currently at. Touches no database — the caller already got
`alembic current` over the tunnel and passes it in, so this stays cheap and
cannot itself hang.

  usage: alembic_pending.py <current_rev> [<current_rev> ...]

Prints one "<rev>  <docstring first line>" per pending revision. Prints nothing
and exits 0 when the database is already at every head — which the caller reads
as "nothing to do".

The database can be at a sibling head while another sibling branch is still
pending. Do not pass all database heads as the end of one ``iterate_revisions``
range: Alembic treats unrelated current revisions as a range error/empty walk.
Instead, compute the applied ancestor closure and filter the complete graph.
"""

import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

SERVER_ROOT = Path(__file__).resolve().parent.parent / "server"


def _revision_closure(script: ScriptDirectory, revisions: tuple[str, ...]) -> set[str]:
    """Return the revisions represented by the supplied database heads."""
    applied: set[str] = set()
    for revision in revisions:
        applied.update(
            rev.revision for rev in script.iterate_revisions(revision, "base")
        )
    return applied


def pending_revisions(script: ScriptDirectory, current: tuple[str, ...]):
    """Return missing revisions in the order Alembic will apply them."""
    applied = _revision_closure(script, current)
    all_revisions = list(script.iterate_revisions(script.get_heads(), "base"))
    all_revisions.reverse()
    return [rev for rev in all_revisions if rev.revision not in applied]


def main() -> int:
    current = tuple(a for a in sys.argv[1:] if a)

    cfg = Config(str(SERVER_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER_ROOT / "alembic"))
    script = ScriptDirectory.from_config(cfg)

    for rev in pending_revisions(script, current):
        doc = (rev.doc or "").strip().splitlines()
        summary = doc[0] if doc else ""
        print(f"{rev.revision}  {summary}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
