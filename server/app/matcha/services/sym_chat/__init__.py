"""Sym-chat — intent-shaped micro group chats on the matcha-work /work surface.

Participants type in private tunnels; `extract` turns each transcript into a
structured stance (one OpenAI Luna call), `aggregate` deterministically rolls
stances up into the shared shape, `narrate` writes the shared feed lines, and
`service` persists it all and sends invites on consensus. See
docs/plans/SYM_CHAT_PLAN.md.
"""
