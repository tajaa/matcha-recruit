-- Po Coffee Co (matcha_ops product, company_id c4c256c3-60ef-4cf5-8d4c-55e963c58416)
-- A small, ACTIVE employee handbook so the HR cases triage has something to
-- check an incident against. Without handbook/policy content the triage check
-- returns "nothing on file" = clean, so no incident ever opens an HR case.
--
-- The attendance, cash-handling and conduct sections are deliberately concrete
-- ("three no-call/no-shows in 30 days...") so a matching incident clears the
-- default 0.60 flag threshold and opens a flagged case.
--
-- Data only. Additive: one handbook, one published version, five sections.
-- Every row is pinned under UUID prefix c0ffeeee-0b00- so undo is a one-liner.
--
--   ./scripts/seed-prod.sh scripts/seed/po_coffee_handbook.sql --dry-run
--   ./scripts/seed-prod.sh scripts/seed/po_coffee_handbook.sql
--   ./scripts/seed-prod.sh scripts/seed/po_coffee_handbook.sql --undo

INSERT INTO handbooks
  (id, company_id, title, status, mode, source_type, active_version,
   guided_answers, published_at)
VALUES
  ('c0ffeeee-0b00-4b00-8b00-000000000001', 'c4c256c3-60ef-4cf5-8d4c-55e963c58416',
   'Po Coffee Co Employee Handbook', 'active', 'single_state', 'template', 1,
   '{}'::jsonb, now())
ON CONFLICT (id) DO NOTHING;

INSERT INTO handbook_versions
  (id, handbook_id, version_number, summary, is_published)
VALUES
  ('c0ffeeee-0b00-4b00-8b00-000000000002', 'c0ffeeee-0b00-4b00-8b00-000000000001',
   1, 'Initial version', TRUE)
ON CONFLICT (id) DO NOTHING;

INSERT INTO handbook_sections
  (id, handbook_version_id, section_key, title, section_order, section_type, content)
VALUES
  ('c0ffeeee-0b00-4b00-8b00-000000000011', 'c0ffeeee-0b00-4b00-8b00-000000000002',
   'attendance', 'Attendance and Punctuality', 1, 'custom',
$$Reliable attendance keeps every shift covered and the line moving.

Reporting an absence. If you cannot work a scheduled shift you must notify your shift lead or store manager at least 2 hours before the shift starts, by phone call or text. A message left with a coworker, or posted in the team channel only, does not count as notice.

No-call/no-show. Missing a scheduled shift without giving notice under this policy is a no-call/no-show. Three (3) no-call/no-shows within any rolling 30-day period is grounds for termination of employment. Missing a full shift without notice for two consecutive scheduled days is treated as job abandonment.

Tardiness. Arriving more than 10 minutes after the scheduled start without notice is a tardy. Four (4) tardies within any rolling 30-day period results in a written warning. Further tardies after a written warning may result in additional discipline up to and including termination.

Early departures. Leaving a shift early without the approval of the shift lead or store manager is treated as an unexcused absence for the remainder of the shift.

Protected absences. Absences protected by law, such as sick leave, family and medical leave, or jury duty, are never counted under this policy.$$),

  ('c0ffeeee-0b00-4b00-8b00-000000000012', 'c0ffeeee-0b00-4b00-8b00-000000000002',
   'cash-handling', 'Cash Handling and Theft', 2, 'custom',
$$Every dollar that crosses the counter must be rung up.

Register rules. Each employee counts the starting drawer, signs for it, and is responsible for it during the shift. Every sale must be rung through the register at the time of the sale. Do not hold a sale to ring later, and do not take cash outside the register.

Tips. Customer tips belong to the team and go in the tip jar or the tip screen only. Taking cash or tips for personal use is theft.

Theft and fraud. Theft of cash, inventory, supplies or a coworker's belongings, falsifying a transaction, voiding a sale to keep the cash, or giving unauthorized free product or discounts to yourself, friends or family is gross misconduct and is grounds for immediate termination.

Drawer variances. A drawer that is over or short by more than $10 must be reported to the shift lead before the end of the shift. Repeated unexplained variances will be reviewed by the store manager.

Reporting. If you see or suspect theft, tell your store manager or HR. Retaliation against anyone who reports in good faith is prohibited.$$),

  ('c0ffeeee-0b00-4b00-8b00-000000000013', 'c0ffeeee-0b00-4b00-8b00-000000000002',
   'conduct', 'Workplace Conduct and Anti-Harassment', 3, 'custom',
$$Po Coffee Co is a respectful, safe workplace for every employee and every guest.

Prohibited conduct. Harassment, discrimination, threats, intimidation, physical violence, fighting, or verbal abuse of a coworker or a customer is prohibited. This includes unwelcome comments or conduct based on race, sex, gender identity, sexual orientation, religion, national origin, age, disability or any other protected characteristic, and unwelcome sexual advances, touching or jokes.

Violence and threats. Any physical altercation, or a threat to harm another person, is grounds for immediate termination.

Substances. Reporting to work, or working a shift, under the influence of alcohol or non-prescribed drugs is prohibited.

Insubordination. Refusing a reasonable instruction from a shift lead or manager, or being openly disrespectful to a supervisor in front of the team or customers, may result in discipline.

Reporting. Report any violation to your store manager or HR. We investigate every report promptly and prohibit retaliation.$$),

  ('c0ffeeee-0b00-4b00-8b00-000000000014', 'c0ffeeee-0b00-4b00-8b00-000000000002',
   'food-safety', 'Food Safety and Hygiene', 4, 'custom',
$$Food safety protects our guests and our license to operate.

Hand washing. Wash hands for at least 20 seconds when you arrive, after breaks, after handling money, after touching your face or phone, and before preparing any drink or food.

Illness. Do not work if you have vomiting, diarrhea, fever or a jaundiced complexion. Tell your shift lead and go home. You will not be disciplined for staying home for these symptoms.

Temperature and dating. Dairy and other perishable items must be stored at 41 degrees Fahrenheit or colder. Every prepared item is labeled with its prep date. Expired product is discarded and logged, never served.

Intentional violations. Knowingly serving expired or unsafe product, or falsifying a temperature or cleaning log, is serious misconduct and may result in discipline up to termination.$$),

  ('c0ffeeee-0b00-4b00-8b00-000000000015', 'c0ffeeee-0b00-4b00-8b00-000000000002',
   'progressive-discipline', 'Corrective Action', 5, 'custom',
$$Employment at Po Coffee Co is at-will. This section describes the steps we usually follow, but the company may skip steps depending on the seriousness of the conduct.

Usual steps. Verbal coaching, then a written warning, then a final written warning, then termination.

Serious misconduct. Theft, fraud, violence, threats, harassment, working under the influence, and three no-call/no-shows in 30 days may result in immediate termination without prior steps.

Process. A manager prepares a written write-up that names the employee, gives the date and a description of what happened, states the expectation going forward and the consequence of further violations, and includes a signature line. HR reviews the write-up before it is delivered. The employee is asked to sign to acknowledge receipt, may add comments, and receives a copy. A signature acknowledges receipt, not agreement.

Protected leave. We do not discipline an employee for absences protected by law.$$)
ON CONFLICT (id) DO NOTHING;
