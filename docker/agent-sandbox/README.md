# Agent sandbox image

Isolated Linux dev image shared by Codex, Claude Code, and OpenCode — no host
home directory, browser profiles, Keychain, SSH agent, or Docker socket.

```bash
msandbox build
msandbox login codex   # or claude / opencode / gh
msandbox dev
msandbox codex         # in another terminal — or `claude` / `opencode`
```

(`msandbox` — not `sandbox` — because `sandbox` is already taken by an
unrelated devcontainer launcher elsewhere on this machine.)

Full command reference, the isolation/threat model, and the host-only
build/deploy and Xcode lanes: `docs/ops/AGENT_SANDBOX.md`.

Set `INSTALL_PLAYWRIGHT_BROWSERS=true` (or `msandbox build --playwright`) to
include an isolated Chromium binary for Playwright.
