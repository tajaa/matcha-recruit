"""Matcha as a remote MCP connector for Claude and ChatGPT.

The person's own Claude / ChatGPT plan runs the model; Matcha exposes tools over
that person's data and never touches a Claude or OpenAI credential. See
`server.py` for the wire layout, `research.py` for the tools' access rules, and
`app/core/services/mcp_oauth.py` for the OAuth authorization server. Ops +
policy notes: docs/ops/MCP_CONNECTOR.md.
"""
