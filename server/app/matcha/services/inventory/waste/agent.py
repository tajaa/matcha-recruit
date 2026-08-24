"""Read-only grounded waste analyst.

The first response is deterministic by design: every displayed amount is
constructed from a rollup and ships its source id. A later model narrator may
rephrase these records, but cannot become the source of any number.
"""
from datetime import date
from typing import Optional
from uuid import UUID

from . import lots, rollup

async def answer_question(conn, *, company_id: UUID, location_id: Optional[UUID], start: date, end: date, question: str) -> dict:
    by_reason = await rollup.waste_rollup(conn, company_id=company_id, location_id=location_id, start=start, end=end, group_by='reason')
    by_item = await rollup.waste_rollup(conn, company_id=company_id, location_id=location_id, start=start, end=end, group_by='item')
    expiring = await lots.expiring_lots(conn, company_id=company_id, location_id=location_id, within_days=7)
    top = by_item['groups'][:3]
    value = by_reason['total_value']
    percent = by_reason['waste_pct_of_revenue']
    headline = f"Recorded waste from {start.isoformat()} to {end.isoformat()}: {by_reason['total_units']} units"
    if value is not None: headline += f", ${value:,.2f}"
    if percent is not None: headline += f" ({percent:.1%} of committed sales)"
    details = [headline + ' [waste:reason]']
    if top: details.append('Top items: ' + ', '.join(f"{row['label']} ({row['units']} units)" for row in top) + ' [waste:item]')
    if expiring: details.append(f"{len(expiring)} open lot(s) expire within seven days. [lots:expiring]")
    return {
        'answer': ' '.join(details), 'question': question[:1000],
        'citations': [
            {'id': 'waste:reason', 'kind': 'waste_rollup', 'data': by_reason},
            {'id': 'waste:item', 'kind': 'waste_rollup', 'data': by_item},
            {'id': 'lots:expiring', 'kind': 'expiring_lots', 'data': expiring},
        ],
    }
