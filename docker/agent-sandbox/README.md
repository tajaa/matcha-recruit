# Agent sandbox image

Isolated Linux dev image shared by Codex, Claude Code, and OpenCode — no host
home directory, browser profiles, Keychain, SSH agent, or Docker socket.

```bash
msandbox install
msandbox
```

The interactive wizard creates and resumes sessions without requiring command
memorization. Standard permissions are the default; Autonomous must be chosen
explicitly for each session. The CLI remains available for automation.

(`msandbox` — not `sandbox` — because `sandbox` is already taken by an
unrelated devcontainer launcher elsewhere on this machine.)

Parallel session, attachment, validation, PR-release, and host-only Xcode
reference: `docs/ops/MSANDBOX_SESSIONS.md`. The broader isolation/threat model
and legacy AutoPR control plane remain in `docs/ops/AGENT_SANDBOX.md`.

Set `INSTALL_PLAYWRIGHT_BROWSERS=true` (or `msandbox build --playwright`) to
include an isolated Chromium binary for Playwright.
