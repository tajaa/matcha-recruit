Finch's write surface is narrow — essentially one product: Deductions & Contributions (Benefits).
Everything else is read-only.

What Finch can write

1. Create a benefit / deduction (company-level) — POST /employer/benefits

- type, description, frequency. Covers the standard deduction categories:
  - Retirement: 401(k), 401(k) Roth, 403(b), 457, Roth 457
  - Health: HSA (pre/post-tax), FSA medical, FSA dependent-care, S125 medical/dental/vision
  - Commuter, plus custom pre-tax / post-tax

2. Enroll / set per-person amounts — POST /employer/benefits/{benefit_id}/individuals

- per individual: employee_deduction, company_contribution (fixed or %), annual_maximum. Same call
  updates existing enrollments.

3. Unenroll — DELETE /employer/benefits/{benefit_id}/individuals

4. Read side — GET /employer/benefits, …/{id}, …/{id}/individuals, plus provider-supported benefit
   types.

5. Register an existing deduction — POST /deductions/register (link a deduction Finch didn't create).

How the writes behave

- Async / job-based: write calls return a job_id → poll GET /jobs/{job_id}
  (pending|in_progress|complete|error).
- Automated vs Assisted: some providers do it via API (fast); others are "Assisted" — Finch's ops team
  keys it into the provider manually (hours/days). Coverage varies by provider.

Separate: sandbox writes (test-only, NOT real)

/sandbox/directory, /sandbox/employment/{id}, /sandbox/individual/{id}, /sandbox/payment, /sandbox/jobs
— these mutate mock data to test your read/sync (what we used in #2). They don't write to any real
provider.

What Finch CANNOT write (all read-only)

- Employees — no create / no terminate / no rehire
- Employment, compensation/pay-rate, demographics, hours
- Payroll runs, pay statements, taxes

Net: Finch write = "push deductions/contributions into payroll," nothing else. It's a
benefits-administration tool, not an employee/payroll editor. (This is why the doc's
onboarding/termination/comp write-back ideas don't hold — those are employee writes Finch doesn't do.)

Sources: Write Deductions (https://developer.tryfinch.com/implementation-guide/API-Calls/Write-Data),
Create Deduction (https://developer.tryfinch.com/api-reference/deductions/create-deduction), Deductions
product (https://www.tryfinch.com/product/deductions)

## Here's the head-to-head. Key: Finch writes deductions only; Merge writes a different,

broader-but-shallow set (PTO + timesheets natively, everything else via passthrough).

Write surface compared

┌────────────────────────────┬────────────────────────────────┬────────────────────────────────────┐
│ Write target │ Finch │ Merge │
├────────────────────────────┼────────────────────────────────┼────────────────────────────────────┤
│ Deductions / contributions │ ✅ core product, │ ❌ Employer Benefits is read; │
│ (401k, FSA, HSA…) │ managed/Assisted, many │ deduction-write not a product │
│ │ providers │ │
├────────────────────────────┼────────────────────────────────┼────────────────────────────────────┤
│ Time-off / PTO request │ ❌ │ ✅ native (POST Time Off) │
├────────────────────────────┼────────────────────────────────┼────────────────────────────────────┤
│ Timesheet entry │ ❌ │ ✅ native (POST Timesheet Entries) │
├────────────────────────────┼────────────────────────────────┼────────────────────────────────────┤
│ │ │ ⚠️ passthrough only │
│ Create employee │ ❌ │ (provider-native API, │
│ │ │ per-provider) │
├────────────────────────────┼────────────────────────────────┼────────────────────────────────────┤
│ Termination / status │ ❌ │ ⚠️ passthrough only │
├────────────────────────────┼────────────────────────────────┼────────────────────────────────────┤
│ Comp / pay-rate change │ ❌ │ ⚠️ passthrough only │
├────────────────────────────┼────────────────────────────────┼────────────────────────────────────┤
│ Payroll runs / pay stubs │ ❌ read │ ❌ read │
└────────────────────────────┴────────────────────────────────┴────────────────────────────────────┘

Model difference

- Finch = narrow but deep + managed. One thing (deductions) done across providers, including no-API
  long-tail via Assisted (Finch ops keys it in manually), async job_id polling.
- Merge = broader native writes (PTO, timesheets) but provider-dependent, and everything else is
  Passthrough — you call the provider's raw API yourself, per-provider, losing the unified abstraction. No
  managed/assisted manual write. Plus the store-and-sync data-at-rest copy.

What this means for Matcha

- Employee / comp / termination write (what onboarding/offboarding want): neither gives it cleanly.
  Merge can via passthrough = a per-provider build; Finch can't at all.
- Finch's deduction-write → maps to no current Matcha feature (no benefits domain).
- Merge's Time-Off write → maps to a feature you DO have (PTO/leave tracking, /employees/pto, leave
  workflows). That's the one real write match — push an approved Matcha PTO request back into payroll.
  Finch can't do that.

Bottom line

- Write capability doesn't overturn the Finch decision for the current app — the deduction-write Finch
  offers has no home, and the employee writes you'd want, neither does cleanly.
- The one scenario that favors Merge: PTO/leave write-back to payroll. If pushing approved time-off into
  the provider becomes a priority, that's a Merge-native capability (provider-dependent) Finch lacks —
  weigh it against Merge's store-and-sync security negative that lost the original call.

So: keep Finch for read/import; the only write feature worth revisiting Merge for is PTO-writeback, and
only if it becomes a roadmap priority.

Sources: Merge Time Off (https://docs.merge.dev/hris/time-off/), Merge Timesheet Entries
(https://docs.merge.dev/hris/timesheet-entries/), Merge Employer Benefits (read)
(https://docs.merge.dev/hris/employer-benefits/), Finch Write Data
(https://developer.tryfinch.com/implementation-guide/API-Calls/Write-Data)
