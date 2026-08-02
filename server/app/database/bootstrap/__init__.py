"""app.database.bootstrap — init_db() orchestrator (split of app/database.py).

Verbatim split: fast-path guard is app/database.py lines 661-673 (with
`_ensure_handbook_tables` now imported from app.database.handbook), the
CREATE EXTENSION vector call is hoisted from er_copilot.py (see below), the
15 `create_*` calls run in the ORIGINAL TABLE ORDER (load-bearing — later
domains ALTER/FK-reference earlier ones, notably jurisdictions.py's late FK
into compliance.py's tables and incidents.py's IR<->ER bridge ALTERs), and
the closing print is app/database.py line 6551.
"""
from app.database.pool import get_connection
from app.database.handbook import _ensure_handbook_tables

from app.database.bootstrap.identity import create_identity
from app.database.bootstrap.recruiting import create_recruiting
from app.database.bootstrap.er_copilot import create_er_copilot
from app.database.bootstrap.incidents import create_incidents
from app.database.bootstrap.leads_policies import create_leads_policies
from app.database.bootstrap.compliance import create_compliance
from app.database.bootstrap.jurisdictions import create_jurisdictions
from app.database.bootstrap.portal_chat import create_portal_chat
from app.database.bootstrap.data_sources import create_data_sources
from app.database.bootstrap.broker import create_broker
from app.database.bootstrap.provisioning import create_provisioning
from app.database.bootstrap.seeds_platform import create_seeds_platform
from app.database.bootstrap.matcha_work import create_matcha_work
from app.database.bootstrap.training import create_training
from app.database.bootstrap.misc_tail import create_misc_tail
from app.database.bootstrap.ems import create_ems
from app.database.bootstrap.inventory import create_inventory


async def init_db():
    """Create tables if they don't exist."""
    async with get_connection() as conn:
        # Fast path: skip the expensive setup when the DB is already initialized.
        # New schema changes should go through Alembic migrations, not this function.
        already_initialized = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='users')"
        )
        if already_initialized:
            await _ensure_handbook_tables(conn)
            return

        # Hoisted from the ER Copilot section (orig line 1646): pgvector must
        # exist before any module creating vector columns
        # (compliance_embeddings, payer_policy_embeddings, er_evidence_chunks).
        # The original statement stays verbatim in er_copilot.py too; both
        # are IF NOT EXISTS idempotent.
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

        await create_identity(conn)
        await create_recruiting(conn)
        await create_er_copilot(conn)
        await create_incidents(conn)
        await create_leads_policies(conn)
        await create_compliance(conn)
        await create_jurisdictions(conn)
        await create_portal_chat(conn)
        await create_data_sources(conn)
        await create_broker(conn)
        await create_provisioning(conn)
        await create_seeds_platform(conn)
        await create_matcha_work(conn)
        await create_training(conn)
        await create_misc_tail(conn)
        await create_ems(conn)
        await create_inventory(conn)

        print("[DB] Tables initialized")
