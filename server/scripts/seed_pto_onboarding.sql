-- Seed script for PTO and Onboarding test data
-- Run this after you have at least one company and employee in the system

-- First, let's see what we're working with
\echo '=== Existing Companies ==='
SELECT id, name FROM companies LIMIT 5;

\echo '=== Existing Employees ==='
SELECT e.id, e.first_name, e.last_name, e.email, e.start_date, c.name as company
FROM employees e
JOIN companies c ON e.org_id = c.id
LIMIT 10;

\echo '=== Existing Users (for creating employees) ==='
SELECT id, email, role FROM users WHERE role IN ('client', 'admin', 'employee') LIMIT 10;

-- ============================================================================
-- ONBOARDING TEMPLATES (run this section to create templates for a company)
-- Replace {ORG_ID} with an actual company UUID from above
-- ============================================================================

\echo '=== Creating Onboarding Templates ==='

-- You can run this with a specific org_id like:
-- \set org_id '''your-uuid-here'''

DO $$
DECLARE
    v_org_id UUID;
BEGIN
    -- Get the first company (or specify one)
    SELECT id INTO v_org_id FROM companies LIMIT 1;

    IF v_org_id IS NULL THEN
        RAISE NOTICE 'No companies found. Create a company first.';
        RETURN;
    END IF;

    RAISE NOTICE 'Using company: %', v_org_id;

    -- Insert onboarding templates if they don't exist
    INSERT INTO onboarding_tasks (org_id, title, description, category, is_employee_task, due_days, sort_order)
    VALUES
        -- Documents (HR completes)
        (v_org_id, 'Complete I-9 Form', 'Verify employment eligibility documentation', 'documents', false, 3, 1),
        (v_org_id, 'Submit W-4 Form', 'Federal tax withholding form', 'documents', true, 3, 2),
        (v_org_id, 'Sign Employee Handbook Acknowledgment', 'Review and sign company policies', 'documents', true, 7, 3),
        (v_org_id, 'Complete Direct Deposit Form', 'Set up payroll direct deposit', 'documents', true, 5, 4),

        -- Equipment (IT completes)
        (v_org_id, 'Set up laptop/workstation', 'Configure employee computer with required software', 'equipment', false, 1, 5),
        (v_org_id, 'Create email account', 'Set up company email and calendar', 'equipment', false, 1, 6),
        (v_org_id, 'Issue access badge', 'Create and distribute building access card', 'equipment', false, 2, 7),
        (v_org_id, 'Set up VPN access', 'Configure remote access if applicable', 'equipment', false, 3, 8),

        -- Training (Employee completes)
        (v_org_id, 'Complete security awareness training', 'Online cybersecurity basics course', 'training', true, 7, 9),
        (v_org_id, 'Complete harassment prevention training', 'Required compliance training', 'training', true, 14, 10),
        (v_org_id, 'Review safety procedures', 'Building evacuation and emergency protocols', 'training', true, 5, 11),

        -- Admin (HR/Manager completes)
        (v_org_id, 'Schedule orientation meeting', 'First day welcome and overview', 'admin', false, 0, 12),
        (v_org_id, 'Introduce to team', 'Team introductions and workspace tour', 'admin', false, 1, 13),
        (v_org_id, 'Set up 30-day check-in', 'Schedule follow-up meeting', 'admin', false, 7, 14)
    ON CONFLICT DO NOTHING;

    RAISE NOTICE 'Onboarding templates created for company %', v_org_id;
END $$;

\echo '=== Onboarding Templates ==='
SELECT id, title, category, is_employee_task, due_days
FROM onboarding_tasks
ORDER BY sort_order;

-- ============================================================================
-- PTO BALANCES (create balance for existing employees)
-- ============================================================================

\echo '=== Creating PTO Balances ==='

DO $$
DECLARE
    emp RECORD;
BEGIN
    FOR emp IN SELECT id FROM employees LOOP
        INSERT INTO pto_balances (employee_id, balance_hours, accrued_hours, used_hours, carryover_hours, year)
        VALUES (emp.id, 120, 10, 0, 0, 2026)
        ON CONFLICT (employee_id, year) DO NOTHING;

        RAISE NOTICE 'Created PTO balance for employee %', emp.id;
    END LOOP;
END $$;

\echo '=== PTO Balances ==='
SELECT pb.*, e.first_name, e.last_name
FROM pto_balances pb
JOIN employees e ON pb.employee_id = e.id;

-- ============================================================================
-- SAMPLE PTO REQUESTS (creates test requests for first employee)
-- ============================================================================

\echo '=== Creating Sample PTO Requests ==='

DO $$
DECLARE
    v_emp_id UUID;
BEGIN
    SELECT id INTO v_emp_id FROM employees LIMIT 1;

    IF v_emp_id IS NULL THEN
        RAISE NOTICE 'No employees found. Create an employee first.';
        RETURN;
    END IF;

    -- Pending vacation request
    INSERT INTO pto_requests (employee_id, request_type, start_date, end_date, hours, reason, status)
    VALUES (v_emp_id, 'vacation', '2026-02-10', '2026-02-14', 40, 'Family vacation', 'pending');

    -- Pending sick day
    INSERT INTO pto_requests (employee_id, request_type, start_date, end_date, hours, reason, status)
    VALUES (v_emp_id, 'sick', '2026-01-27', '2026-01-27', 8, 'Doctor appointment', 'pending');

    -- Already approved request (past)
    INSERT INTO pto_requests (employee_id, request_type, start_date, end_date, hours, reason, status, approved_at)
    VALUES (v_emp_id, 'personal', '2026-01-06', '2026-01-06', 8, 'Personal errand', 'approved', NOW() - INTERVAL '10 days');

    RAISE NOTICE 'Created PTO requests for employee %', v_emp_id;
END $$;

\echo '=== PTO Requests ==='
SELECT pr.id, e.first_name, e.last_name, pr.request_type, pr.start_date, pr.end_date, pr.hours, pr.status
FROM pto_requests pr
JOIN employees e ON pr.employee_id = e.id
ORDER BY pr.created_at DESC;

-- ============================================================================
-- ASSIGN ONBOARDING TASKS TO EMPLOYEES
-- ============================================================================

\echo '=== Assigning Onboarding Tasks to Employees ==='

DO $$
DECLARE
    emp RECORD;
    task RECORD;
    v_due_date DATE;
BEGIN
    FOR emp IN SELECT e.id, e.start_date, e.org_id FROM employees e LOOP
        -- Check if employee already has tasks assigned
        IF EXISTS (SELECT 1 FROM employee_onboarding_tasks WHERE employee_id = emp.id) THEN
            RAISE NOTICE 'Employee % already has tasks, skipping', emp.id;
            CONTINUE;
        END IF;

        FOR task IN SELECT * FROM onboarding_tasks WHERE org_id = emp.org_id AND is_active = true LOOP
            v_due_date := COALESCE(emp.start_date, CURRENT_DATE) + task.due_days;

            INSERT INTO employee_onboarding_tasks
                (employee_id, task_id, title, description, category, is_employee_task, due_date, status)
            VALUES
                (emp.id, task.id, task.title, task.description, task.category, task.is_employee_task, v_due_date, 'pending');
        END LOOP;

        RAISE NOTICE 'Assigned tasks to employee %', emp.id;
    END LOOP;
END $$;

\echo '=== Employee Onboarding Tasks ==='
SELECT eot.id, e.first_name, e.last_name, eot.title, eot.category, eot.is_employee_task, eot.due_date, eot.status
FROM employee_onboarding_tasks eot
JOIN employees e ON eot.employee_id = e.id
ORDER BY e.last_name, eot.due_date;

\echo '=== SEED COMPLETE ==='
\echo 'You can now:'
\echo '  - View PTO requests at /app/matcha/pto (as admin/client)'
\echo '  - View employee onboarding at /app/matcha/employees/{id} (as admin/client)'
\echo '  - Employee portal at /app/portal/pto and /app/portal/onboarding (as employee)'
