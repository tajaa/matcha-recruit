-- Seed employee_schedule demo data for "720 Behavioral" (dev DB only).
-- Uses the existing employee roster; 2-week window starting this week's Monday.
-- Weekday mask matches services/schedule_rules.py:sunday_indexed_weekday (Sun=0..Sat=6),
-- which is the same convention as Postgres EXTRACT(DOW). Times stored as literal UTC
-- wall-clock, matching template_windows()'s "what the admin typed is what the
-- employee sees" behavior — no timezone conversion needed.

BEGIN;

\set company_id '1a1123e5-4c24-4735-8501-9a64a1dd7691'
\set hq_location '7538c28b-0a5e-4168-8e84-a694e905e913'
\set created_by '55c8b446-b174-4042-ba1e-4d2f437bd609'

SELECT date_trunc('week', CURRENT_DATE)::date AS week_start \gset

-- ── Templates ─────────────────────────────────────────────────────────

INSERT INTO schedule_shift_templates
    (company_id, name, department, location_id, start_time, end_time,
     break_minutes, required_staff, days_of_week, color, notes, created_by)
VALUES (:'company_id', 'Outpatient Clinic — Weekday', 'Outpatient Services', :'hq_location',
        '08:00', '17:00', 60, 21, '[1,2,3,4,5]'::jsonb, '#38bdf8',
        'Standard weekday outpatient clinic coverage', :'created_by')
RETURNING id AS outpatient_tpl \gset

INSERT INTO schedule_shift_templates
    (company_id, name, department, location_id, start_time, end_time,
     break_minutes, required_staff, days_of_week, color, notes, created_by)
VALUES (:'company_id', 'Psychiatry Clinic — Weekday', 'Psychiatry', :'hq_location',
        '08:00', '17:00', 60, 9, '[1,2,3,4,5]'::jsonb, '#a78bfa',
        'Standard weekday psychiatry clinic coverage', :'created_by')
RETURNING id AS psychiatry_tpl \gset

INSERT INTO schedule_shift_templates
    (company_id, name, department, location_id, start_time, end_time,
     break_minutes, required_staff, days_of_week, color, notes, created_by)
VALUES (:'company_id', 'Substance Use — Day Program', 'Substance Use Programs', :'hq_location',
        '08:00', '16:00', 30, 7, '[1,2,3,4,5]'::jsonb, '#f59e0b',
        'Weekday day-program groups + individual sessions', :'created_by')
RETURNING id AS sud_day_tpl \gset

INSERT INTO schedule_shift_templates
    (company_id, name, department, location_id, start_time, end_time,
     break_minutes, required_staff, days_of_week, color, notes, created_by)
VALUES (:'company_id', 'Substance Use — Evening Group', 'Substance Use Programs', :'hq_location',
        '16:00', '20:00', 0, 3, '[1,3,5]'::jsonb, '#fb923c',
        'Mon/Wed/Fri evening group facilitation (rotating subset)', :'created_by')
RETURNING id AS sud_evening_tpl \gset

INSERT INTO schedule_shift_templates
    (company_id, name, department, location_id, start_time, end_time,
     break_minutes, required_staff, days_of_week, color, notes, created_by)
VALUES (:'company_id', 'Residential — Day', 'Residential Services', :'hq_location',
        '07:00', '15:00', 30, 2, '[0,1,2,3,4,5,6]'::jsonb, '#34d399',
        '24/7 residential unit — day shift', :'created_by')
RETURNING id AS res_day_tpl \gset

INSERT INTO schedule_shift_templates
    (company_id, name, department, location_id, start_time, end_time,
     break_minutes, required_staff, days_of_week, color, notes, created_by)
VALUES (:'company_id', 'Residential — Evening', 'Residential Services', :'hq_location',
        '15:00', '23:00', 30, 2, '[0,1,2,3,4,5,6]'::jsonb, '#22c55e',
        '24/7 residential unit — evening shift', :'created_by')
RETURNING id AS res_evening_tpl \gset

INSERT INTO schedule_shift_templates
    (company_id, name, department, location_id, start_time, end_time,
     break_minutes, required_staff, days_of_week, color, notes, created_by)
VALUES (:'company_id', 'Residential — Overnight', 'Residential Services', :'hq_location',
        '23:00', '07:00', 30, 2, '[0,1,2,3,4,5,6]'::jsonb, '#16a34a',
        '24/7 residential unit — overnight shift', :'created_by')
RETURNING id AS res_night_tpl \gset

INSERT INTO schedule_shift_templates
    (company_id, name, department, location_id, start_time, end_time,
     break_minutes, required_staff, days_of_week, color, notes, created_by)
VALUES (:'company_id', 'Community Programs — Weekday', 'Community Programs', :'hq_location',
        '09:00', '17:00', 60, 5, '[1,2,3,4,5]'::jsonb, '#f472b6',
        'Peer support / community programs weekday coverage', :'created_by')
RETURNING id AS community_tpl \gset

INSERT INTO schedule_shift_templates
    (company_id, name, department, location_id, start_time, end_time,
     break_minutes, required_staff, days_of_week, color, notes, created_by)
VALUES (:'company_id', 'Child & Adolescent — Afternoon', 'Child & Adolescent', :'hq_location',
        '12:00', '20:00', 30, 5, '[1,2,3,4,5]'::jsonb, '#818cf8',
        'After-school hours coverage for child & adolescent services', :'created_by')
RETURNING id AS child_tpl \gset

INSERT INTO schedule_shift_templates
    (company_id, name, department, location_id, start_time, end_time,
     break_minutes, required_staff, days_of_week, color, notes, created_by)
VALUES (:'company_id', 'Administration — Business Hours', 'Administration', NULL,
        '09:00', '17:00', 60, 8, '[1,2,3,4,5]'::jsonb, '#94a3b8',
        'Standard business hours; several staff are fully remote', :'created_by')
RETURNING id AS admin_tpl \gset

-- ── Concrete shifts (2-week window, published) ───────────────────────

INSERT INTO schedule_shifts
    (company_id, location_id, template_id, series_id, department,
     starts_at, ends_at, break_minutes, required_staff, color, notes,
     status, published_at, created_by)
SELECT :'company_id', :'hq_location', :'outpatient_tpl', gen_random_uuid(), 'Outpatient Services',
       (d::timestamp + time '08:00') AT TIME ZONE 'UTC',
       (d::timestamp + time '17:00') AT TIME ZONE 'UTC',
       60, 21, '#38bdf8', 'Standard weekday outpatient clinic coverage',
       'published', now(), :'created_by'
FROM generate_series(:'week_start'::date, :'week_start'::date + 13, interval '1 day') AS d
WHERE extract(dow from d) IN (1,2,3,4,5);

INSERT INTO schedule_shifts
    (company_id, location_id, template_id, series_id, department,
     starts_at, ends_at, break_minutes, required_staff, color, notes,
     status, published_at, created_by)
SELECT :'company_id', :'hq_location', :'psychiatry_tpl', gen_random_uuid(), 'Psychiatry',
       (d::timestamp + time '08:00') AT TIME ZONE 'UTC',
       (d::timestamp + time '17:00') AT TIME ZONE 'UTC',
       60, 9, '#a78bfa', 'Standard weekday psychiatry clinic coverage',
       'published', now(), :'created_by'
FROM generate_series(:'week_start'::date, :'week_start'::date + 13, interval '1 day') AS d
WHERE extract(dow from d) IN (1,2,3,4,5);

INSERT INTO schedule_shifts
    (company_id, location_id, template_id, series_id, department,
     starts_at, ends_at, break_minutes, required_staff, color, notes,
     status, published_at, created_by)
SELECT :'company_id', :'hq_location', :'sud_day_tpl', gen_random_uuid(), 'Substance Use Programs',
       (d::timestamp + time '08:00') AT TIME ZONE 'UTC',
       (d::timestamp + time '16:00') AT TIME ZONE 'UTC',
       30, 7, '#f59e0b', 'Weekday day-program groups + individual sessions',
       'published', now(), :'created_by'
FROM generate_series(:'week_start'::date, :'week_start'::date + 13, interval '1 day') AS d
WHERE extract(dow from d) IN (1,2,3,4,5);

INSERT INTO schedule_shifts
    (company_id, location_id, template_id, series_id, department,
     starts_at, ends_at, break_minutes, required_staff, color, notes,
     status, published_at, created_by)
SELECT :'company_id', :'hq_location', :'sud_evening_tpl', gen_random_uuid(), 'Substance Use Programs',
       (d::timestamp + time '16:00') AT TIME ZONE 'UTC',
       (d::timestamp + time '20:00') AT TIME ZONE 'UTC',
       0, 3, '#fb923c', 'Mon/Wed/Fri evening group facilitation (rotating subset)',
       'published', now(), :'created_by'
FROM generate_series(:'week_start'::date, :'week_start'::date + 13, interval '1 day') AS d
WHERE extract(dow from d) IN (1,3,5);

INSERT INTO schedule_shifts
    (company_id, location_id, template_id, series_id, department,
     starts_at, ends_at, break_minutes, required_staff, color, notes,
     status, published_at, created_by)
SELECT :'company_id', :'hq_location', :'res_day_tpl', gen_random_uuid(), 'Residential Services',
       (d::timestamp + time '07:00') AT TIME ZONE 'UTC',
       (d::timestamp + time '15:00') AT TIME ZONE 'UTC',
       30, 2, '#34d399', '24/7 residential unit — day shift',
       'published', now(), :'created_by'
FROM generate_series(:'week_start'::date, :'week_start'::date + 13, interval '1 day') AS d;

INSERT INTO schedule_shifts
    (company_id, location_id, template_id, series_id, department,
     starts_at, ends_at, break_minutes, required_staff, color, notes,
     status, published_at, created_by)
SELECT :'company_id', :'hq_location', :'res_evening_tpl', gen_random_uuid(), 'Residential Services',
       (d::timestamp + time '15:00') AT TIME ZONE 'UTC',
       (d::timestamp + time '23:00') AT TIME ZONE 'UTC',
       30, 2, '#22c55e', '24/7 residential unit — evening shift',
       'published', now(), :'created_by'
FROM generate_series(:'week_start'::date, :'week_start'::date + 13, interval '1 day') AS d;

INSERT INTO schedule_shifts
    (company_id, location_id, template_id, series_id, department,
     starts_at, ends_at, break_minutes, required_staff, color, notes,
     status, published_at, created_by)
SELECT :'company_id', :'hq_location', :'res_night_tpl', gen_random_uuid(), 'Residential Services',
       (d::timestamp + time '23:00') AT TIME ZONE 'UTC',
       ((d::date + 1)::timestamp + time '07:00') AT TIME ZONE 'UTC',
       30, 2, '#16a34a', '24/7 residential unit — overnight shift',
       'published', now(), :'created_by'
FROM generate_series(:'week_start'::date, :'week_start'::date + 13, interval '1 day') AS d;

INSERT INTO schedule_shifts
    (company_id, location_id, template_id, series_id, department,
     starts_at, ends_at, break_minutes, required_staff, color, notes,
     status, published_at, created_by)
SELECT :'company_id', :'hq_location', :'community_tpl', gen_random_uuid(), 'Community Programs',
       (d::timestamp + time '09:00') AT TIME ZONE 'UTC',
       (d::timestamp + time '17:00') AT TIME ZONE 'UTC',
       60, 5, '#f472b6', 'Peer support / community programs weekday coverage',
       'published', now(), :'created_by'
FROM generate_series(:'week_start'::date, :'week_start'::date + 13, interval '1 day') AS d
WHERE extract(dow from d) IN (1,2,3,4,5);

INSERT INTO schedule_shifts
    (company_id, location_id, template_id, series_id, department,
     starts_at, ends_at, break_minutes, required_staff, color, notes,
     status, published_at, created_by)
SELECT :'company_id', :'hq_location', :'child_tpl', gen_random_uuid(), 'Child & Adolescent',
       (d::timestamp + time '12:00') AT TIME ZONE 'UTC',
       (d::timestamp + time '20:00') AT TIME ZONE 'UTC',
       30, 5, '#818cf8', 'After-school hours coverage for child & adolescent services',
       'published', now(), :'created_by'
FROM generate_series(:'week_start'::date, :'week_start'::date + 13, interval '1 day') AS d
WHERE extract(dow from d) IN (1,2,3,4,5);

INSERT INTO schedule_shifts
    (company_id, location_id, template_id, series_id, department,
     starts_at, ends_at, break_minutes, required_staff, color, notes,
     status, published_at, created_by)
SELECT :'company_id', NULL, :'admin_tpl', gen_random_uuid(), 'Administration',
       (d::timestamp + time '09:00') AT TIME ZONE 'UTC',
       (d::timestamp + time '17:00') AT TIME ZONE 'UTC',
       60, 8, '#94a3b8', 'Standard business hours; several staff are fully remote',
       'published', now(), :'created_by'
FROM generate_series(:'week_start'::date, :'week_start'::date + 13, interval '1 day') AS d
WHERE extract(dow from d) IN (1,2,3,4,5);

-- ── Assignments: whole-department templates get every active employee ──

INSERT INTO schedule_shift_assignments (company_id, shift_id, employee_id, status, assigned_by, assigned_at)
SELECT :'company_id', s.id, e.id, 'assigned', :'created_by', s.created_at
FROM schedule_shifts s
JOIN employees e ON e.org_id = :'company_id' AND e.department = 'Outpatient Services' AND e.employment_status = 'active'
WHERE s.template_id = :'outpatient_tpl';

INSERT INTO schedule_shift_assignments (company_id, shift_id, employee_id, status, assigned_by, assigned_at)
SELECT :'company_id', s.id, e.id, 'assigned', :'created_by', s.created_at
FROM schedule_shifts s
JOIN employees e ON e.org_id = :'company_id' AND e.department = 'Psychiatry' AND e.employment_status = 'active'
WHERE s.template_id = :'psychiatry_tpl';

INSERT INTO schedule_shift_assignments (company_id, shift_id, employee_id, status, assigned_by, assigned_at)
SELECT :'company_id', s.id, e.id, 'assigned', :'created_by', s.created_at
FROM schedule_shifts s
JOIN employees e ON e.org_id = :'company_id' AND e.department = 'Substance Use Programs' AND e.employment_status = 'active'
WHERE s.template_id = :'sud_day_tpl';

INSERT INTO schedule_shift_assignments (company_id, shift_id, employee_id, status, assigned_by, assigned_at)
SELECT :'company_id', s.id, e.id, 'assigned', :'created_by', s.created_at
FROM schedule_shifts s
JOIN LATERAL (
    SELECT id FROM employees
    WHERE org_id = :'company_id' AND department = 'Substance Use Programs' AND employment_status = 'active'
    ORDER BY id LIMIT 3
) e ON true
WHERE s.template_id = :'sud_evening_tpl';

INSERT INTO schedule_shift_assignments (company_id, shift_id, employee_id, status, assigned_by, assigned_at)
SELECT :'company_id', s.id, e.id, 'assigned', :'created_by', s.created_at
FROM schedule_shifts s
JOIN employees e ON e.org_id = :'company_id' AND e.department = 'Community Programs' AND e.employment_status = 'active'
WHERE s.template_id = :'community_tpl';

INSERT INTO schedule_shift_assignments (company_id, shift_id, employee_id, status, assigned_by, assigned_at)
SELECT :'company_id', s.id, e.id, 'assigned', :'created_by', s.created_at
FROM schedule_shifts s
JOIN employees e ON e.org_id = :'company_id' AND e.department = 'Child & Adolescent' AND e.employment_status = 'active'
WHERE s.template_id = :'child_tpl';

INSERT INTO schedule_shift_assignments (company_id, shift_id, employee_id, status, assigned_by, assigned_at)
SELECT :'company_id', s.id, e.id, 'assigned', :'created_by', s.created_at
FROM schedule_shifts s
JOIN employees e ON e.org_id = :'company_id' AND e.department = 'Administration' AND e.employment_status = 'active'
WHERE s.template_id = :'admin_tpl';

-- ── Residential rotation: 6 staff → 3 pairs, pair covers a different
-- shift each day on a 3-day cycle so nobody double-books. ──

WITH re AS (
    SELECT id, ntile(3) OVER (ORDER BY id) AS pair_num
    FROM employees
    WHERE org_id = :'company_id' AND department = 'Residential Services' AND employment_status = 'active'
)
INSERT INTO schedule_shift_assignments (company_id, shift_id, employee_id, status, assigned_by, assigned_at)
SELECT :'company_id', s.id, re.id, 'assigned', :'created_by', s.created_at
FROM schedule_shifts s
JOIN re ON re.pair_num = (((s.starts_at::date - :'week_start'::date) + 0) % 3) + 1
WHERE s.template_id = :'res_day_tpl';

WITH re AS (
    SELECT id, ntile(3) OVER (ORDER BY id) AS pair_num
    FROM employees
    WHERE org_id = :'company_id' AND department = 'Residential Services' AND employment_status = 'active'
)
INSERT INTO schedule_shift_assignments (company_id, shift_id, employee_id, status, assigned_by, assigned_at)
SELECT :'company_id', s.id, re.id, 'assigned', :'created_by', s.created_at
FROM schedule_shifts s
JOIN re ON re.pair_num = (((s.starts_at::date - :'week_start'::date) + 1) % 3) + 1
WHERE s.template_id = :'res_evening_tpl';

WITH re AS (
    SELECT id, ntile(3) OVER (ORDER BY id) AS pair_num
    FROM employees
    WHERE org_id = :'company_id' AND department = 'Residential Services' AND employment_status = 'active'
)
INSERT INTO schedule_shift_assignments (company_id, shift_id, employee_id, status, assigned_by, assigned_at)
SELECT :'company_id', s.id, re.id, 'assigned', :'created_by', s.created_at
FROM schedule_shifts s
JOIN re ON re.pair_num = (((s.starts_at::date - :'week_start'::date) + 2) % 3) + 1
WHERE s.template_id = :'res_night_tpl';

-- A little status variety so it doesn't read as machine-generated.
UPDATE schedule_shift_assignments SET status = 'confirmed'
WHERE company_id = :'company_id' AND id IN (
    SELECT id FROM schedule_shift_assignments WHERE company_id = :'company_id' ORDER BY id LIMIT 40
);
UPDATE schedule_shift_assignments SET status = 'declined'
WHERE company_id = :'company_id' AND id IN (
    SELECT id FROM schedule_shift_assignments WHERE company_id = :'company_id' AND status = 'assigned' ORDER BY id LIMIT 2
);

-- ── A handful of schedule_requests for workflow variety ────────────────

-- Pending swap: an outpatient employee wants to hand off a shift to a peer in the same dept.
INSERT INTO schedule_requests (company_id, employee_id, request_type, shift_id, target_employee_id, reason, status)
SELECT :'company_id', a.employee_id, 'swap', a.shift_id, peer.id,
       'Family commitment that day — asked a teammate to cover.', 'pending'
FROM schedule_shift_assignments a
JOIN schedule_shifts s ON s.id = a.shift_id AND s.template_id = :'outpatient_tpl'
JOIN LATERAL (
    SELECT id FROM employees
    WHERE org_id = :'company_id' AND department = 'Outpatient Services' AND employment_status = 'active'
      AND id <> a.employee_id
    ORDER BY id LIMIT 1
) peer ON true
ORDER BY a.id LIMIT 1;

-- Pending drop: a psychiatry staffer requests to drop a shift, no swap partner lined up yet.
INSERT INTO schedule_requests (company_id, employee_id, request_type, shift_id, reason, status)
SELECT :'company_id', a.employee_id, 'drop', a.shift_id,
       'Conflicting appointment — requesting coverage.', 'pending'
FROM schedule_shift_assignments a
JOIN schedule_shifts s ON s.id = a.shift_id AND s.template_id = :'psychiatry_tpl'
ORDER BY a.id LIMIT 1;

-- Approved unavailability: a residential staffer flags an upcoming date range.
INSERT INTO schedule_requests (company_id, employee_id, request_type, unavailable_start, unavailable_end, reason, status, reviewed_by, reviewed_at, review_notes)
SELECT :'company_id', re.id, 'unavailable', :'week_start'::date + 8, :'week_start'::date + 9,
       'Pre-approved time off.', 'approved', :'created_by', now(), 'Confirmed with coverage lined up.'
FROM (
    SELECT id FROM employees
    WHERE org_id = :'company_id' AND department = 'Residential Services' AND employment_status = 'active'
    ORDER BY id LIMIT 1
) re;

-- Denied drop: a substance-use staffer's drop request came in too late to cover.
INSERT INTO schedule_requests (company_id, employee_id, request_type, shift_id, reason, status, reviewed_by, reviewed_at, review_notes)
SELECT :'company_id', a.employee_id, 'drop', a.shift_id,
       'Would like to skip this group session.', 'denied', :'created_by', now(),
       'Too close to shift start — no coverage available.'
FROM schedule_shift_assignments a
JOIN schedule_shifts s ON s.id = a.shift_id AND s.template_id = :'sud_day_tpl'
ORDER BY a.id DESC LIMIT 1;

COMMIT;
