"""IR-incident request/response models.

Split from the flat models/ir_incident.py (1,059 lines) in refactor round 2
stage 7, along the `# ====` banners it already carried — the groups map
near-1:1 onto routes/ir_incidents/'s submodules.

No facade re-export here on purpose: models/__init__.py was 0 bytes, so there
was never a package surface to preserve, and every importer names the module
it wants. Import from the submodule (`from app.matcha.models.ir.osha import
Osha300LogEntry`), not from this package.
"""
