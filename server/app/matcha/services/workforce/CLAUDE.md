# Workforce compliance trackers — feature spec(s)

Moved verbatim from root `CLAUDE.md`'s Feature Flags table. Root keeps a one-line summary + `→ full spec:` pointer here. Default column below matches `DEFAULT_COMPANY_FEATURES` in `server/app/core/feature_flags.py`.

## `workforce_compliance` (default ❌)

Business-first employment-practices risk trackers — per-state **pay-transparency** posting compliance, **AI hiring-tool bias-audit** register (cadence/overdue), **biometric/BIPA** consent inventory, and a **pay-equity study** register (cadence/overdue). Gates `/workforce-compliance/*` + the `/app/workforce-compliance` page. Each is a legal obligation the tenant tracks for itself; together they flip the broker EPL factors (`pay_transparency`/`ai_hiring_audit`/`biometrics_bipa`/`pay_equity`) from attested → derived in `epl_readiness.compute_epl_readiness`. The pay-equity register computes a **real protected-class gap** when HRIS demographics are present (`employee_demographics`, from the Finch/Gusto sync) and otherwise reports the dispersion screen under its own `dispersion_pct` — the two are separate columns on `pay_equity_reviews`, never conflated. Default off; admin-toggle; **in the `matcha_x` overlay** (the tier that already carries the roster + HRIS these trackers read).
