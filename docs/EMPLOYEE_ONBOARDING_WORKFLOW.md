# Employee Onboarding Workflow

## Overview

The employee onboarding system allows HR administrators to invite new employees to set up their accounts and access the employee portal. This document outlines the complete workflow from employee creation to portal access.

---

## The Flow (High Level)

```
1. Admin creates employee record
   ↓
2. Admin sends invitation email
   ↓
3. Employee receives email with setup link
   ↓
4. Employee clicks link and creates password
   ↓
5. Employee logs in and accesses portal
```

---

## Detailed Workflow

### Step 1: Admin Creates Employee Record

**Who:** HR Admin or Client user
**Where:** `/app/employees`

1. Navigate to **Recruiting > Employees** in the sidebar
2. Click **Add Employee** button
3. Fill in employee information:
   - **Email** (required) - Employee's work email
   - **First Name** (required)
   - **Last Name** (required)
   - **Work State** (optional) - Two-letter state code (e.g., CA, NY)
   - **Employment Type** - Full Time, Part Time, Contractor, or Intern
   - **Start Date** (optional)
4. Click **Add Employee**

**Result:** Employee record is created but the employee cannot log in yet (no account).

**Status:** Employee appears in the list with "Not Invited" badge (gray).

---

### Step 2: Admin Sends Invitation

**Who:** HR Admin or Client user
**Where:** `/app/employees`

1. Find the employee in the list
2. Click the **Send Invite** button next to their name
3. System generates a secure invitation token (expires in 7 days)
4. Email is sent to the employee with subject: "Welcome to [Company Name] - Set Up Your Account"

**Result:** Invitation email sent.

**Status:** Employee badge changes to "Invited" (yellow).

**Email Contents:**
- Welcome message with company name
- "Set Up My Account" button linking to `/invite/{token}`
- Expiration notice (7 days)

---

### Step 3: Employee Receives Email

**Who:** New Employee
**Where:** Their email inbox

The employee receives an email that looks like this:

```
Subject: Welcome to [Company Name] - Set Up Your Account

Hi [First Name],

Welcome! You've been invited to join the employee portal.

[Company Name]
is inviting you to set up your account

Steps:
1. Click the button below to get started
2. Create your password
3. Access your employee portal

[Set Up My Account Button]

This invitation expires on [Date].
```

---

### Step 4: Employee Sets Up Account

**Who:** New Employee
**Where:** `/invite/{token}` (from email link)

1. Employee clicks **Set Up My Account** in the email
2. Browser opens to the invitation acceptance page
3. Employee sees:
   - Welcome message with their name
   - Company name
   - Email address (pre-filled, disabled)
   - Password field (min 8 characters)
   - Confirm Password field
4. Employee enters and confirms their password
5. Click **Create Account**

**Result:**
- User account is created with role `employee`
- Employee record is linked to the user account
- Invitation status changes to `accepted`
- Employee is automatically logged in
- Redirected to `/app/portal` (Employee Dashboard)

**Status:** Employee badge changes to "Active" (green).

---

### Step 5: Employee Accesses Portal

**Who:** Employee
**Where:** `/app/portal/*`

After setup, the employee can access their portal with 5 main sections:

#### Portal Navigation (Employee Sidebar):

1. **Dashboard** (`/app/portal`)
   - PTO balance overview
   - Pending documents count
   - Pending PTO requests
   - Quick links

2. **My Documents** (`/app/portal/documents`)
   - View documents requiring signature
   - Sign documents electronically
   - View document history (pending/signed/expired)
   - Filter by status

3. **Time Off** (`/app/portal/pto`)
   - View PTO balance (available, used, accrued)
   - Submit PTO requests
   - View pending requests (can cancel)
   - View approved/denied request history

4. **Policies** (`/app/portal/policies`)
   - Search company policies
   - View policy details
   - Full-text search

5. **My Profile** (`/app/portal/profile`)
   - View employment info (read-only)
   - Edit contact info (phone, address)
   - Manage emergency contact

**Login for Future Sessions:**
- Employees log in at `/login` using their email and password
- After login, they see the Employee Portal section in the sidebar

---

## User Roles & Permissions

### Admin
- Can access **all** companies (defaults to first company)
- Can create, view, edit, and delete employees
- Can send invitations
- Cannot access employee portal

### Client (HR Manager)
- Can access **their company's** employees only
- Can create, view, edit, and delete employees
- Can send invitations
- Cannot access employee portal

### Employee
- Can **only** access their own employee portal
- Cannot see or manage other employees
- Cannot send invitations
- Read-only access to their employment info

---

## Employee Statuses

Employees can have the following statuses:

| Status | Badge Color | Meaning |
|--------|-------------|---------|
| **Not Invited** | Gray | Employee record created but no invitation sent |
| **Invited** | Yellow | Invitation sent, awaiting employee setup |
| **Active** | Green | Employee has set up account and can log in |
| **Terminated** | Gray | Employee has been terminated (has termination date) |

---

## Filter Tabs

The Employees page has filter tabs to quickly find employees:

- **All** - Show all employees
- **Active** - Show only employees with accounts (no termination date)
- **Pending Invite** - Show only employees without accounts (not yet invited or pending setup)
- **Terminated** - Show only terminated employees

---

## Invitation Details

### Token Security
- Tokens are generated using `secrets.token_urlsafe(32)` (cryptographically secure)
- Tokens are 64 characters long
- Stored in `employee_invitations` table with unique constraint

### Expiration
- Invitations expire after **7 days**
- Expired invitations cannot be accepted
- Admin can resend invitation to generate a new token

### Resending Invitations

If an employee doesn't receive the email or the link expires:

1. Find the employee in the list
2. Click **Resend Invite** (same button, different text if already invited)
3. Previous invitation is cancelled
4. New invitation with new token is sent

---

## Database Schema

### Tables Created

#### `employees`
- Stores employee profile information
- Links to `users` table via `user_id` (NULL until account created)
- Links to `companies` via `org_id`
- Can reference manager via `manager_id` (self-referencing)

#### `employee_invitations`
- Tracks invitation tokens and status
- Links to `employees` via `employee_id`
- Links to inviter via `invited_by`
- Status: pending, accepted, expired, cancelled

#### `pto_balances`
- Tracks PTO accrual per employee per year
- Balance, accrued, used hours

#### `pto_requests`
- PTO request/approval workflow
- Status: pending, approved, denied, cancelled
- Links to approver via `approved_by`

#### `employee_documents`
- Documents assigned to employees
- Status: draft, pending_signature, signed, expired
- Can store document in S3 via `storage_path` or inline via `content`

---

## Email Template

The invitation email includes:
- **From:** Matcha Recruit (`outreach@matcha.app`)
- **Subject:** "Welcome to {Company Name} - Set Up Your Account"
- **Body:** HTML email with company branding
- **CTA Button:** "Set Up My Account" → `/invite/{token}`
- **Expiration Notice:** Date when invitation expires
- **Footer:** "Sent via Matcha Recruit"

Email service: MailerSend API

---

## Common Scenarios

### Scenario 1: New Hire Onboarding
1. HR creates employee record with start date
2. HR sends invitation 1 week before start date
3. Employee sets up account before first day
4. On day 1, employee can immediately access portal

### Scenario 2: Invitation Expired
1. Employee doesn't click link within 7 days
2. Invitation expires
3. HR clicks "Resend Invite"
4. New invitation sent with fresh 7-day expiration

### Scenario 3: Employee Never Received Email
1. Employee reports not receiving email
2. HR verifies email address is correct
3. HR clicks "Resend Invite"
4. HR can also share the invitation link directly if needed

### Scenario 4: Terminated Employee
1. HR updates employee record with termination date
2. Employee status shows as "Terminated"
3. Employee can still log in to view historical data (unless account is disabled)

---

## Technical Notes

### Authentication
- Uses JWT tokens (24hr access, 30-day refresh)
- Password hashed with bcrypt (12 rounds)
- Token stored as `matcha_access_token` in localStorage

### API Endpoints

#### Admin/Client Endpoints (requires auth):
- `GET /api/employees` - List employees
- `POST /api/employees` - Create employee
- `GET /api/employees/{id}` - Get employee details
- `PUT /api/employees/{id}` - Update employee
- `DELETE /api/employees/{id}` - Delete employee
- `POST /api/employees/{id}/invite` - Send invitation

#### Public Endpoints (no auth):
- `GET /api/invitations/{token}` - Get invitation details
- `POST /api/invitations/{token}/accept` - Accept invitation and create account

#### Employee Portal Endpoints (requires employee auth):
- `GET /api/v1/portal/me` - Get employee dashboard
- `GET /api/v1/portal/me/documents` - List my documents
- `POST /api/v1/portal/me/documents/{id}/sign` - Sign document
- `GET /api/v1/portal/me/pto` - Get PTO summary
- `POST /api/v1/portal/me/pto/request` - Submit PTO request
- `GET /api/v1/portal/policies` - Search policies

---

## Future Enhancements

Potential improvements to the workflow:

1. **Company Selector for Admins**
   - Allow admins to switch between companies
   - Currently defaults to first company

2. **Bulk Import**
   - Upload CSV of employees
   - Send batch invitations

3. **Custom Email Templates**
   - Allow companies to customize invitation email
   - Add company logo

4. **Manager Approval Workflow**
   - Require manager approval for PTO requests
   - Email notifications to managers

5. **Document Reminders**
   - Auto-reminder emails for unsigned documents
   - Escalation to manager after X days

6. **Compliance Integration**
   - Link employee work_state to compliance requirements
   - Auto-calculate compliance alerts when employees added

7. **Employee Self-Registration**
   - Allow employees to request access
   - Admin approves and creates account

---

## Support & Troubleshooting

### Common Issues

**Q: Employee says they didn't receive the email**
- A: Check spam/junk folder first, then resend invitation

**Q: Invitation link shows "expired"**
- A: Click "Resend Invite" to generate a new link

**Q: Employee can't create account - says email already exists**
- A: User may have created account through different flow. Contact admin.

**Q: I don't see the Employees tab**
- A: Only admin and client roles can see this. Employees cannot.

**Q: Admin sees no employees**
- A: Admin sees employees from the first company in the database. This will be improved with company selector.

**Q: Where do employees log in?**
- A: Regular login page at `/login` with their email and password

---

## Deployment Checklist

Before launching employee onboarding:

- [ ] Run Alembic migrations: `alembic upgrade head`
- [ ] Verify MailerSend API key is configured
- [ ] Test invitation email delivery
- [ ] Verify frontend routes are accessible
- [ ] Test complete workflow end-to-end
- [ ] Ensure `APP_BASE_URL` is set correctly for invitation links
- [ ] Seed test data if needed

---

## Database Migrations

Employee onboarding uses Alembic for database migrations:

```bash
# View current migration version
alembic current

# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

**Migration files:**
- `7c1de748641e_add_employee_portal_tables.py` - Creates employee, PTO, and document tables
- `6e4ad940b98b_update_users_role_constraint_for_.py` - Adds 'employee' role to users
- `7c2a6a0d729f_add_employee_invitations_table.py` - Creates invitation tracking table

---

## Summary

The employee onboarding workflow is designed to be simple and secure:

1. **HR creates** employee records with basic info
2. **System sends** secure, time-limited invitation emails
3. **Employees accept** invitations and create passwords
4. **Employees access** their self-service portal

This ensures employees only need to remember one password, have immediate access to their portal, and HR maintains full control over who gets invited.
