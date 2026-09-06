-- Codify meal-period TIMING (how early a meal break may start) in the
-- compliance catalog for CA / WA / OR.
--
-- Why: the schedule break-time suggester used to offer the shift's own start
-- time as a break, because nothing in the catalog or the curated threshold
-- table said anything about an EARLIEST. The existing per-state
-- `meal_breaks:meal_break` rows carry the DEADLINE (and, for WA/OR, the
-- earliest buried in prose only). These rows make the timing window a first-
-- class, citable requirement so the scheduler and the pilots can refer to it.
--
-- CA is deliberately included as an explicit negative: § 512(a) and Brinker
-- fix only the deadline, so a first-hour meal is lawful there. Recording
-- "no statutory earliest" is what stops the next reader inventing one.
--
-- Additive only: one new requirement_key per state, ON CONFLICT DO NOTHING,
-- and every scaffolding column is cloned from that state's existing
-- `meal_breaks:meal_break` row so category_id / jurisdiction_level /
-- jurisdiction_name stay consistent with its neighbours.
-- Undo: meal_break_timing.undo.sql.

-- California — no statutory earliest.
INSERT INTO jurisdiction_requirements
    (jurisdiction_id, requirement_key, category, category_id, jurisdiction_level,
     jurisdiction_name, title, description, current_value, numeric_value,
     statute_citation, source_name, source_url, status, last_verified_at)
SELECT
    base.jurisdiction_id,
    'meal_breaks:meal_break_timing',
    base.category,
    base.category_id,
    base.jurisdiction_level,
    base.jurisdiction_name,
    'Meal Period Timing — No Statutory Earliest',
    'California fixes only the deadline for the first meal period: it must begin before the end of the employee''s 5th hour of work (Cal. Lab. Code § 512(a)). No statute, wage order, or DLSE interpretation sets an EARLIEST — under Brinker Restaurant Corp. v. Superior Court (2012) 53 Cal.4th 1004 an employer may lawfully provide the meal period in the first hour of the shift. Scheduling tools that decline to suggest a break at the very start of a shift are applying operational policy, not California law.',
    'No statutory earliest; deadline only (before end of 5th hour)',
    NULL,
    'Cal. Lab. Code § 512(a); Brinker Restaurant Corp. v. Superior Court (2012) 53 Cal.4th 1004',
    base.source_name,
    'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=LAB&sectionNum=512',
    'active',
    NOW()
FROM jurisdiction_requirements base
JOIN jurisdictions j ON j.id = base.jurisdiction_id
WHERE base.requirement_key = 'meal_breaks:meal_break'
  AND j.level = 'state' AND j.state = 'CA'
ON CONFLICT (jurisdiction_id, requirement_key) DO NOTHING;

-- Washington — meal period must commence between the 2nd and 5th hour.
INSERT INTO jurisdiction_requirements
    (jurisdiction_id, requirement_key, category, category_id, jurisdiction_level,
     jurisdiction_name, title, description, current_value, numeric_value,
     statute_citation, source_name, source_url, status, last_verified_at)
SELECT
    base.jurisdiction_id,
    'meal_breaks:meal_break_timing',
    base.category,
    base.category_id,
    base.jurisdiction_level,
    base.jurisdiction_name,
    'Meal Period Timing Window',
    'Washington fixes both ends of the meal-period window: the meal period "commences no less than two hours nor more than five hours from the beginning of the shift" (WAC 296-126-092(1)). numeric_value is the EARLIEST, in hours from shift start; the five-hour end of the window is the deadline already carried by meal_breaks:meal_break. No employee may be required to work more than five consecutive hours without a meal period.',
    '2–5 hours from the beginning of the shift',
    2,
    'WAC 296-126-092(1)',
    base.source_name,
    'https://app.leg.wa.gov/wac/default.aspx?cite=296-126-092',
    'active',
    NOW()
FROM jurisdiction_requirements base
JOIN jurisdictions j ON j.id = base.jurisdiction_id
WHERE base.requirement_key = 'meal_breaks:meal_break'
  AND j.level = 'state' AND j.state = 'WA'
ON CONFLICT (jurisdiction_id, requirement_key) DO NOTHING;

-- Oregon — earliest depends on the length of the work period.
INSERT INTO jurisdiction_requirements
    (jurisdiction_id, requirement_key, category, category_id, jurisdiction_level,
     jurisdiction_name, title, description, current_value, numeric_value,
     statute_citation, source_name, source_url, status, last_verified_at)
SELECT
    base.jurisdiction_id,
    'meal_breaks:meal_break_timing',
    base.category,
    base.category_id,
    base.jurisdiction_level,
    base.jurisdiction_name,
    'Meal Period Timing Window',
    'Oregon''s meal-period window has two tiers (OAR 839-020-0050(2)(d)): for a work period of seven hours or less the meal period is taken after the conclusion of the 2nd hour worked and completed before the commencement of the 5th; for a work period over seven hours it is taken after the conclusion of the 3rd hour worked and completed before the commencement of the 6th. numeric_value records the STRICTER earliest (3 hours), because scheduling a break later than required is lawful while scheduling one earlier is not. Acute inpatient care facilities have their own variant in (2)(d)(C).',
    'After the 2nd hour (work period ≤7h); after the 3rd hour (>7h)',
    3,
    'OAR 839-020-0050(2)(d)(A)-(B)',
    base.source_name,
    'https://secure.sos.state.or.us/oard/viewSingleRule.action?ruleVrsnRsn=310125',
    'active',
    NOW()
FROM jurisdiction_requirements base
JOIN jurisdictions j ON j.id = base.jurisdiction_id
WHERE base.requirement_key = 'meal_breaks:meal_break'
  AND j.level = 'state' AND j.state = 'OR'
ON CONFLICT (jurisdiction_id, requirement_key) DO NOTHING;
