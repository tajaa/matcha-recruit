"""Cappe social growth — connected accounts, scheduled posts, the reply inbox.

Layout:
  providers/   one module per network API (`meta.py` serves Instagram and
               Facebook Pages); `base.py` is the shape every provider returns
  oauth.py     the signed state a Connect round-trip carries
  connections  the stored accounts (tokens encrypted at rest)
  posts        posts + per-connection targets; the publisher's claim/roll-up
  captions     Claude Haiku caption options for the composer
  autoreply    the inbox policy + the grounded Claude Haiku draft
  inbox        stored comments/messages, replies, per-site settings
  metrics      follower counts and per-post reach
"""
