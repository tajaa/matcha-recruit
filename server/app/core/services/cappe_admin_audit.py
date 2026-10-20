"""The audit row for a Matcha admin acting on Cappe.

Matcha's admin (hey-matcha.com/admin/cappe) is not a Cappe identity, so its
writes to `cappe_admin_audit` carry `actor_account_id` NULL, an action under
`matcha:`, and the admin's email in the payload. One format, used by core's
Cappe admin (`routes/admin/cappe_creators.py`) and by Cappe's own routes for
the same admin (`cappe/routes/matcha_admin.py`; cappe → core is the allowed
import direction). Don't put a customer's email in `payload`: the dev refresh
strips only the `email` key.
"""
import json


async def record_matcha_admin_action(
    conn, admin_email: str, action: str, target: str, payload: dict,
) -> None:
    await conn.execute(
        "INSERT INTO cappe_admin_audit (actor_account_id, action, target, payload) "
        "VALUES (NULL, $1, $2, $3::jsonb)",
        f"matcha:{action}", target,
        json.dumps({**payload, "admin_email": admin_email}, default=str),
    )
