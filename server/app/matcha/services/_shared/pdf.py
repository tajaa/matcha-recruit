"""Shared PDF chrome — escaping, date formatting, and the house CSS reused by
every deterministic PDF renderer (claims readiness, broker pilot, analysis
pilot, legal defense). Leaf module: imports nothing from services/, so it
cannot participate in an import cycle.
"""
import html


def _esc(v) -> str:
    return html.escape(str(v)) if v is not None else "—"


def _fmt_dt(v) -> str:
    if v is None:
        return "—"
    try:
        return v.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(v)


_PDF_CSS = """
  body { font-family: -apple-system, Helvetica, sans-serif; color:#1a1a2e; padding:30px; font-size:11px; }
  h1 { color:#1f3a8a; margin:0 0 2px; font-size:21px; }
  .sub { color:#666; margin:0 0 14px; }
  h2 { font-size:12px; border-bottom:2px solid #1f3a8a; padding-bottom:4px; margin:16px 0 6px; }
  .grid { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:6px; }
  .cell { border:1px solid #e5e7eb; border-radius:8px; padding:6px 10px; min-width:90px; }
  .cell .l { font-size:8px; text-transform:uppercase; letter-spacing:.5px; color:#888; }
  .cell .v { font-size:14px; font-weight:400; margin-top:2px; }
  table { width:100%; border-collapse:collapse; margin-top:4px; }
  th { text-align:left; font-size:8px; text-transform:uppercase; color:#888; border-bottom:1px solid #ddd; padding:3px 6px; }
  td { padding:3px 6px; border-bottom:1px solid #f0f0f0; vertical-align:top; }
  .narr { background:#f2f4fb; border-left:3px solid #1f3a8a; padding:8px 12px; border-radius:0 6px 6px 0; margin:6px 0; white-space:pre-wrap; }
  ul { margin:4px 0; padding-left:18px; } li { margin:2px 0; }
  .foot { margin-top:22px; color:#999; font-size:8px; border-top:1px solid #eee; padding-top:6px; }
"""
