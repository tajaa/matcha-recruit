# Benefits — feature spec(s)

Moved verbatim from root `CLAUDE.md`'s Feature Flags table. Root keeps a one-line summary + pointer here.

## `benefits_admin` (default ❌)

Employee-benefits tooling — source-agnostic roster ingest (Finch + CSV), eligibility-exception detection (new-hire gaps + termination premium leaks), renewal-risk radar. Gates company-facing `/benefits/*`. Daily Celery `benefit_eligibility_sync` (scheduler row, default off).
