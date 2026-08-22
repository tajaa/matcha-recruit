# Silent Error Autofix

`.github/workflows/silent-error-autofix.yml` runs every 15 minutes on this Mac's self-hosted GitHub Actions runner. It:

1. Reads only recent backend, worker, and nginx error/5xx signals from production over SSH.
2. Redacts auth headers, cookies, URL queries, common credential formats, emails, IPs, UUIDs, and long numeric identifiers before model access.
3. Checks configured public health endpoints.
4. Derives a stable incident signature and skips an already-open bot PR for it.
5. Runs local `opencode` with `openai/gpt-5.6-luna` to make a small, tested fix.
6. Opens a draft PR only when a code diff exists. It never deploys or auto-merges.

## One-time setup

1. Register GitHub Actions self-hosted runner on this Mac with labels `self-hosted`, `macOS`, and `opencode`. Run it as Finch's logged-in user so its OpenCode/OpenAI authentication is available.
2. Ensure `opencode models openai` lists `openai/gpt-5.6-luna` for that runner user.
3. Add repository variables `PROD_HEALTH_URL` and `PROD_API_HEALTH_URL`, such as public `/health` URLs. Empty variables skip those probes.
4. Keep repository secret `EC2_SSH_KEY` configured. Workflow uses it only for read-only log collection.
5. Enable workflow under Actions. Use `workflow_dispatch` once after runner setup to verify connectivity.

## Guardrails

- Agent receives only redacted evidence; the collector removes all URL query strings rather than relying on a secret-name allowlist.
- Agent cannot change workflows, deploy code, scripts, dependencies, migrations, or env files.
- Workflow stages first, then validates the complete staged diff with rename detection disabled so protected source and destination paths cannot bypass the guard.
- Failures without enough evidence produce no PR; inspect the workflow run and production logs manually.
