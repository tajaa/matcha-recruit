# Codex sandbox

This is an isolated CLI workflow for working on Matcha without giving Codex
access to the macOS home directory, browser profiles, Keychain, SSH agent, or
Docker socket. It bind-mounts only this repository and runs the workspace as a
dedicated non-root Linux user.

```bash
./scripts/codex-sandbox.sh build
./scripts/codex-sandbox.sh login
./scripts/codex-sandbox.sh git-login
./scripts/codex-sandbox.sh dev
```

In another terminal, start the unrestricted Codex CLI inside that boundary:

```bash
./scripts/codex-sandbox.sh codex
```

`start`, `shell`, `status`, and `stop` manage the same Compose project.
`stop` preserves the dedicated Codex, dependency, PostgreSQL, and Redis
volumes. `import-db` imports a `pg_dump` stream from the running local
`matcha-postgres` container into the *sandbox-only* database volume; it prompts
before replacing sandbox data. Set `SOURCE_DB_CONTAINER`, `SOURCE_DB_NAME`, or
`SOURCE_DB_USER` to use a different local development source.

The repository bind mount is deliberately writable, so repository-local files
such as `server/.env` and `secrets/` remain visible to Codex. Keep secrets out
of the repository or mask and inject only the required values if that boundary
is too broad for your use case.

The default stack intentionally has no chat model. Do not mount the host model
directory into this workspace. If chat is needed later, run a separately
controlled model server and explicitly expose only that endpoint to the
container, or build a Linux-compatible model service with its own named volume.

Set `INSTALL_PLAYWRIGHT_BROWSERS=true` before `build` to include Chromium for
isolated Playwright tests. All published application ports bind to `127.0.0.1`.
