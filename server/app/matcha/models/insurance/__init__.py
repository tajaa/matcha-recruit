"""Insurance-side models: coverage lines, driver risk, limit adequacy,
loss development, and resident care.

Moved here from the flat models/ directory in refactor round 2 stage 7,
mirroring the services/ subdirectory names. No facade re-export:
models/__init__.py was 0 bytes, so there was never a package surface to
preserve — import the module you want directly.
"""
