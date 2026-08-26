#!/usr/bin/env python3
"""Create the kanban-autopr service account: a `client`-role bot user plus a
`mw_project_collaborators` row on each of the four projects the loop is
scoped to (WerkWerk, Beetlejuse, Gummfit, MATCHA — spanning two different
company_ids, so per-project collaborator rows are used rather than a single
`clients` row; see docs/ops/KANBAN_AUTOPR.md).

Prints SQL to stdout (the seed-prod.sh .py convention). --undo prints the
reversing SQL.

    AUTOPR_BOT_PASSWORD=... ./scripts/seed-prod.sh scripts/seed/autopr_bot.py --dry-run
    AUTOPR_BOT_PASSWORD=... ./scripts/seed-prod.sh scripts/seed/autopr_bot.py
    ./scripts/seed-prod.sh scripts/seed/autopr_bot.py --undo

AUTOPR_BOT_PASSWORD is required except on --undo (the password never lands
in this file or in git — it's hashed here, at seed time, from the caller's
environment).
"""

import os
import sys

import bcrypt

BOT_USER_ID = "a0700000-0000-4000-8000-000000000001"
BOT_EMAIL = "autopr@matcha.invalid"  # RFC 2606 reserved domain — never a real mailbox.

# (project_id, project title — for the SQL comment only)
PROJECTS = [
    ("7f728636-3219-4d83-9df3-a4682e3242de", "WerkWerk"),
    ("fade10b4-36ff-4c60-af59-5cc6058285ab", "Beetlejuse"),
    ("84823d21-c752-4abd-9696-4c93c8b3c21e", "Gummfit"),
    ("8b924347-d6e4-4000-8e7d-ca8f46f76fba", "MATCHA"),
]


def upgrade_sql() -> str:
    password = os.environ.get("AUTOPR_BOT_PASSWORD")
    if not password:
        print("AUTOPR_BOT_PASSWORD must be set in the environment", file=sys.stderr)
        sys.exit(1)
    password_hash = bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt(rounds=10)).decode("ascii")

    lines = [
        "-- kanban-autopr bot account. Undo: scripts/seed-prod.sh scripts/seed/autopr_bot.py --undo",
        f"INSERT INTO users (id, email, password_hash, role, is_active, created_at)"
        f" VALUES ('{BOT_USER_ID}', '{BOT_EMAIL}', '{password_hash}', 'client', true, NOW())"
        f" ON CONFLICT (id) DO UPDATE SET password_hash = EXCLUDED.password_hash;",
    ]
    for project_id, title in PROJECTS:
        lines.append(
            f"-- {title}\n"
            f"INSERT INTO mw_project_collaborators (project_id, user_id, invited_by, role, status)"
            f" SELECT '{project_id}', '{BOT_USER_ID}', p.created_by, 'collaborator', 'active'"
            f" FROM mw_projects p WHERE p.id = '{project_id}'"
            f" ON CONFLICT (project_id, user_id) DO UPDATE SET status = 'active';"
        )
    return "\n".join(lines)


def undo_sql() -> str:
    lines = [f"DELETE FROM mw_project_collaborators WHERE user_id = '{BOT_USER_ID}';"]
    lines.append(f"DELETE FROM users WHERE id = '{BOT_USER_ID}';")
    return "\n".join(lines)


if __name__ == "__main__":
    print(undo_sql() if "--undo" in sys.argv else upgrade_sql())
