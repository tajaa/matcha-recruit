"""A guarded browser: Chromium behind an egress proxy, driven by one loop.

Every server-side browser in matcha-work goes through here. See `egress.py`
for what it may reach and `session.py` for where it may navigate.
"""
