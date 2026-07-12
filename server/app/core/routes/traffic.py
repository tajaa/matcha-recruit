"""Admin traffic report — serves the goaccess HTML generated on the host.

A host systemd timer (`goaccess-report.timer`, every 15 min) parses the nginx
access logs for ALL vhosts (hey-matcha.com, gummfit.com, tenant subdomains)
into `/home/ec2-user/matcha/analytics/report.html`; the deploy script mounts
that dir read-only at /app/analytics. Local dev has no mount → 404 with hint.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from ..dependencies import require_admin

router = APIRouter()

_REPORT_PATH = os.environ.get("TRAFFIC_REPORT_PATH", "/app/analytics/report.html")


@router.get("/admin/traffic-report", dependencies=[Depends(require_admin)])
async def traffic_report() -> HTMLResponse:
    try:
        with open(_REPORT_PATH, encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=(
                "Traffic report not available — goaccess-report.timer writes it "
                "on the prod host; not generated in this environment."
            ),
        )
    return HTMLResponse(content=html)
