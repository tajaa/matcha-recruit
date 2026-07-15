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
"""

import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

SERVER_ROOT = Path(__file__).resolve().parent.parent / "server"


def main() -> int:
    current = tuple(a for a in sys.argv[1:] if a)

    cfg = Config(str(SERVER_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER_ROOT / "alembic"))
    script = ScriptDirectory.from_config(cfg)

    heads = set(script.get_heads())
    if set(current) == heads:
        return 0

    # iterate_revisions walks heads -> current (newest first); reverse for the
    # order they will actually be applied in.
    pending = list(script.iterate_revisions(heads, current or ("base",)))
    pending.reverse()

    for rev in pending:
        if rev.revision in current:
            continue
        doc = (rev.doc or "").strip().splitlines()
        summary = doc[0] if doc else ""
        print(f"{rev.revision}  {summary}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
