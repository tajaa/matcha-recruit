"""Werk — the peer-to-peer chat product (channels, DMs, calls, broadcasts).

This is the backend for **werk-lite** (business chat) and the channel surfaces of
the **werk** macOS client. It is deliberately NOT matcha-work: matcha-work
(`/work/<project-id>`) is a platform-only LLM work product for working *on* the
Matcha platform, not a peer chat app, and its backend stays at
`matcha/routes/matcha_work/`.

Some legacy coupling between the two still exists and is tracked as follow-up
work — `matcha_work/collaboration.py` bootstraps a discussion channel for collab
projects, and `matcha/services/project_service.py` writes `channel_members`.
That entanglement is preserved here as-is; unwinding it is a separate change.
"""
