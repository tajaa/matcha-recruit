# Agent sandbox image

Isolated Linux dev image shared by Codex, Claude Code, and OpenCode — no host
home directory, browser profiles, Keychain, SSH agent, or Docker socket.

```bash
sandbox build
sandbox login codex   # or claude / opencode / gh
sandbox dev
sandbox codex         # in another terminal — or `claude` / `opencode`
```

Full command reference, the isolation/threat model, and the host-only
build/deploy and Xcode lanes: `docs/ops/AGENT_SANDBOX.md`.

Set `INSTALL_PLAYWRIGHT_BROWSERS=true` (or `sandbox build --playwright`) to
include an isolated Chromium binary for Playwright.
