"""Read-only grounded waste analyst.

The first response is deterministic by design: every displayed amount is
constructed from a rollup and ships its source id. A later model narrator may
rephrase these records, but cannot become the source of any number.
"""
from datetime import date
from typing import Optional
from uuid import UUID

from . import lots, rollup


async def usage_variance_for_item(
    conn, *, company_id: UUID, location_id: Optional[UUID], start: date, end: date,
) -> list[dict]:
    """Most recent persisted recipe-usage variances in the requested window."""
    rows = await conn.fetch(
        """
        SELECT al.item_id, i.name, al.theoretical_usage, al.actual_usage, al.usage_variance
        FROM inventory_audit_lines al
        JOIN inventory_audit_runs ar ON ar.id=al.run_id
        JOIN inventory_items i ON i.id=al.item_id
        WHERE ar.company_id=$1 AND al.created_at::date BETWEEN $2 AND $3
          AND al.usage_variance IS NOT NULL
          AND ($4::uuid IS NULL OR i.location_id IS NULL OR i.location_id=$4)
        ORDER BY al.created_at DESC, ABS(al.usage_variance) DESC
        LIMIT 10
        """,
        company_id, start, end, location_id,
    )
    return [dict(row) for row in rows]


async def par_history_for_item(conn, *, company_id: UUID, location_id: Optional[UUID]) -> list[dict]:
    """Recent deterministic par changes, including their persisted basis."""
    rows = await conn.fetch(
        """
        SELECT ph.item_id, i.name, ph.previous_par, ph.new_par, ph.par_basis,
               ph.drift_pct, ph.source, ph.changed_at
        FROM inventory_par_history ph
        JOIN inventory_items i ON i.id=ph.item_id
        WHERE ph.company_id=$1
          AND ($2::uuid IS NULL OR i.location_id IS NULL OR i.location_id=$2)
        ORDER BY ph.changed_at DESC, ph.id DESC
        LIMIT 10
        """,
        company_id, location_id,
    )
    return [dict(row) for row in rows]


async def item_history(
    conn, *, company_id: UUID, location_id: Optional[UUID], start: date, end: date,
) -> list[dict]:
    """Recent first-party waste facts; keeps the analyst read-only and grounded."""
    rows = await conn.fetch(
        """
        SELECT m.item_id, i.name, m.waste_reason, m.quantity, m.created_at
        FROM inventory_movements m
        JOIN inventory_items i ON i.id=m.item_id
        WHERE m.company_id=$1 AND m.kind='waste'
          AND m.created_at::date BETWEEN $2 AND $3
          AND ($4::uuid IS NULL OR i.location_id IS NULL OR i.location_id=$4)
        ORDER BY m.created_at DESC
        LIMIT 10
        """,
        company_id, start, end, location_id,
    )
    return [dict(row) for row in rows]

async def answer_question(conn, *, company_id: UUID, location_id: Optional[UUID], start: date, end: date, question: str) -> dict:
    by_reason = await rollup.waste_rollup(conn, company_id=company_id, location_id=location_id, start=start, end=end, group_by='reason')
    by_item = await rollup.waste_rollup(conn, company_id=company_id, location_id=location_id, start=start, end=end, group_by='item')
    expiring = await lots.expiring_lots(conn, company_id=company_id, location_id=location_id, within_days=7)
    usage = await usage_variance_for_item(
        conn, company_id=company_id, location_id=location_id, start=start, end=end,
    )
    pars = await par_history_for_item(conn, company_id=company_id, location_id=location_id)
    history = await item_history(
        conn, company_id=company_id, location_id=location_id, start=start, end=end,
    )
    top = by_item['groups'][:3]
    value = by_reason['total_value']
    percent = by_reason['waste_pct_of_revenue']
    headline = f"Recorded waste from {start.isoformat()} to {end.isoformat()}: {by_reason['total_units']} units"
    if value is not None: headline += f", ${value:,.2f}"
    if percent is not None: headline += f" ({percent:.1%} of committed sales)"
    details = [headline + ' [waste:reason]']
    if top: details.append('Top items: ' + ', '.join(f"{row['label']} ({row['units']} units)" for row in top) + ' [waste:item]')
    if expiring: details.append(f"{len(expiring)} open lot(s) expire within seven days. [lots:expiring]")
    asked = question.lower()
    if usage and any(term in asked for term in ('usage', 'portion', 'actual', 'theoretical', 'variance')):
        rows = usage[:3]
        details.append('Usage variance: ' + ', '.join(
            f"{row['name']} ({row['usage_variance']:+g} units)" for row in rows
        ) + ' [usage:variance]')
    if pars and any(term in asked for term in ('par', 'reorder', 'forecast', 'shelf')):
        rows = pars[:3]
        details.append('Recent par changes: ' + ', '.join(
            f"{row['name']} → {row['new_par']:g} ({row['par_basis'] or 'unspecified'})" for row in rows
        ) + ' [par:history]')
    if history and any(term in asked for term in ('history', 'recent', 'what happened', 'why')):
        rows = history[:3]
        details.append('Recent waste facts: ' + ', '.join(
            f"{row['name']} ({row['waste_reason'] or 'unknown'})" for row in rows
        ) + ' [item:history]')
    return {
        'answer': ' '.join(details), 'question': question[:1000],
        'citations': [
            {'id': 'waste:reason', 'kind': 'waste_rollup', 'data': by_reason},
            {'id': 'waste:item', 'kind': 'waste_rollup', 'data': by_item},
            {'id': 'lots:expiring', 'kind': 'expiring_lots', 'data': expiring},
            {'id': 'usage:variance', 'kind': 'usage_variance_for_item', 'data': usage},
            {'id': 'par:history', 'kind': 'par_history_for_item', 'data': pars},
            {'id': 'item:history', 'kind': 'item_history', 'data': history},
        ],
    }
