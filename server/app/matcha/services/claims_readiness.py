"""Claims-readiness / litigation-defense packet — re-export shim.

The implementation split by domain in refactor round 2 stage 6:
`services/ir/ir_claims_packet.py` (incident packet) and
`services/er/er_claims_packet.py` (ER-case packet). This module stays so the
three existing importers are unchanged — `routes/broker/submission.py` imports
it as `cr`, and `routes/ir_incidents/claims_readiness.py` /
`routes/er_copilot/case_views.py` import it by module and call through it.


The PDF chrome (_esc / _fmt_dt / _PDF_CSS) is re-exported too: it lives in
services/_shared/pdf.py, but it was reachable through this module before the
split and the claims-readiness tests exercise it here.
"""
from app.matcha.services._shared.pdf import _PDF_CSS, _esc, _fmt_dt  # noqa: F401
from app.matcha.services.er.er_claims_packet import (  # noqa: F401
    _er_html,
    build_er_packet,
    render_er_packet_pdf,
)
from app.matcha.services.ir.ir_claims_packet import (  # noqa: F401
    _incident_html,
    _loads,
    build_incident_packet,
    render_incident_packet_pdf,
)
