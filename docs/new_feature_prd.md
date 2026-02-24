Product Requirements Document
HR Compliance Platform for SMBs

# 1. Product Overview

## 1.1 Problem Statement

Solo HR professionals at SMBs (50-500 employees) are overwhelmed by multi-state compliance complexity. They spend 60%+ of their time on reactive tasks: answering employee questions, chasing documents, and researching state-specific requirements. One compliance mistake can cost $160,000+ in legal fees.

## 1.2 Solution

A unified HR compliance platform that acts as an intelligent second brain: proactively surfacing compliance requirements, automating document collection, and enabling employee self-service to reduce the HR person's burden.

## 1.3 Target User

Primary: Solo HR manager or HR generalist at companies with 50-500 employees
Secondary: Employees who need self-service access to HR information
Tertiary: Company leadership needing compliance visibility

## 1.4 Success Metrics

# 2. Feature Requirements

## 2.1 MVP Features (Phase 1)

### Feature A: Compliance Engine

Priority: P0 (Must Have)
Detect which states/jurisdictions apply based on employee locations
Surface applicable compliance requirements with plain-English explanations
Proactive alerts when: new employee added in new state, deadlines approaching, laws change
Compliance checklist per jurisdiction with completion tracking
Cover core areas: wage/hour, I-9, state tax registration, required postings, leave laws

### Feature B: Document Management & Automation

Priority: P0 (Must Have)
Central document storage organized by employee and document type
E-signature integration for offer letters, policies, I-9s
Auto-reminder sequences: Day 1, Day 3, Day 7, escalate to manager
Document expiration tracking (licenses, certifications, work authorizations)
Audit trail for all document actions

### Feature C: Employee Self-Service Portal

Priority: P0 (Must Have)
Employee dashboard: PTO balance, pay stubs, benefits summary, personal info
Policy lookup with search (employee handbook, leave policies, etc.)
PTO request submission and approval workflow
Personal information updates (address, emergency contact, banking)
Pending tasks view (documents to sign, training to complete)

## 2.2 Phase 2 Features

AI-powered document drafting (offer letters, policy updates, termination checklists)
Employee-facing chatbot for FAQ handling
Manager dashboard with team compliance status
Payroll integration (read-only sync for PTO, employee data)
Custom reporting and analytics

# 3. Technical Architecture

## 3.1 System Overview

The application follows a standard three-tier architecture with async task processing for background jobs.

## 3.2 Database Schema (Core Tables)

### Organizations & Users

organizations

employees

### Compliance Tracking

compliance_requirements

org_compliance_status

### Documents

documents

document_reminders

# 4. API Specification

## 4.1 Authentication

JWT tokens with 15-minute access token, 7-day refresh token
Role-based access: admin, hr_manager, manager, employee
Org-scoped tenancy (all queries filtered by org_id from token)

## 4.2 Core Endpoints

### Compliance

### Employees

### Documents

### Self-Service (Employee Portal)

# 5. Background Tasks (Celery)

## 5.1 Task Definitions

## 5.2 Task Implementation Notes

Use Celery Beat for scheduled tasks
Implement idempotency keys for document reminder sends
Use task chaining: employee_created → recalculate_org_compliance → send_welcome_email
Set appropriate timeouts (compliance recalc: 5min, report gen: 30min)
Dead letter queue for failed tasks with manual retry UI

# 6. Frontend Architecture

## 6.1 Tech Stack

Vite + React 18 + TypeScript
TanStack Query (React Query) for server state
React Router v6 for routing
Tailwind CSS + shadcn/ui components
Zustand for client state (auth, UI preferences)

## 6.2 Route Structure

## 6.3 Key Components

### HR Manager Views

ComplianceDashboard: Kanban-style board (Pending | In Progress | Complete | Overdue)
AlertsPanel: Prioritized list of upcoming deadlines and new requirements
RequirementDetail: Explanation, checklist, action buttons, audit log
DocumentTracker: Status of all pending documents with bulk actions
EmployeeOnboarding: Wizard for adding new employee + auto-assigning docs

### Employee Portal Views

PortalHome: Quick stats (PTO balance, pending tasks count)
MyDocuments: List of docs to sign with inline signature capture
PTODashboard: Calendar view of requests, balance, request form
PolicySearch: Full-text search across company policies
ProfileEdit: Self-service info updates with change request workflow

# 7. Implementation Plan

## 7.1 Phase 1: MVP (8-10 weeks)

## 7.2 Phase 2: Enhancement (6-8 weeks)

E-signature integration (DocuSign or HelloSign API)
AI document drafting (OpenAI API for templates)
Employee chatbot for policy questions
Expand compliance coverage to all 50 states + federal
Reporting dashboard with export

## 7.3 Technical Debt & Risks

# 8. Appendix

## 8.1 Compliance Categories (MVP)

## 8.2 Sample Compliance Rule (JSON)

{
"id": "ca-sick-leave-accrual",
"jurisdiction": "CA",
"category": "leave",
"title": "California Paid Sick Leave",
"description": "California requires employers to provide paid sick leave to employees who work 30+ days within a year. Employees accrue 1 hour for every 30 hours worked, usable after 90 days.",
"applies_when": {
"has_employees_in_state": "CA",
"employee_works_days_gte": 30
},
"deadline_type": "ongoing",
"action_items": [
"Configure sick leave accrual in payroll system",
"Update employee handbook with CA sick leave policy",
"Post required notice (included in CA labor law poster)"
],
"resources": [
{"title": "CA DIR Sick Leave FAQ", "url": "https://www.dir.ca.gov/dlse/paid_sick_leave.htm"}
],
"effective_date": "2024-01-01",
"last_updated": "2024-01-15"
}

## 8.3 Environment Variables

| Version    | 1.0                                     |
| ---------- | --------------------------------------- |
| Date       | January 2026                            |
| Status     | Draft                                   |
| Tech Stack | FastAPI, PostgreSQL, Celery, Vite/React |

| Metric                     | Baseline     | Target (6mo) |
| -------------------------- | ------------ | ------------ |
| Time on compliance tasks   | 15 hrs/week  | 5 hrs/week   |
| Employee questions to HR   | 30/week      | 10/week      |
| Document completion rate   | 70% on time  | 95% on time  |
| Compliance audit readiness | 2 weeks prep | Always ready |

| Layer        | Technology                | Purpose                       |
| ------------ | ------------------------- | ----------------------------- |
| Frontend     | Vite + React + TypeScript | SPA with role-based views     |
| API          | FastAPI                   | REST API with OpenAPI docs    |
| Database     | PostgreSQL                | Primary data store            |
| Task Queue   | Celery + Redis            | Async jobs, reminders, alerts |
| File Storage | S3-compatible             | Document storage              |

| Column         | Type         | Description                    |
| -------------- | ------------ | ------------------------------ |
| id             | UUID         | Primary key                    |
| name           | VARCHAR(255) | Company name                   |
| ein            | VARCHAR(20)  | Employer ID number (encrypted) |
| primary_state  | VARCHAR(2)   | HQ state code                  |
| employee_count | INTEGER      | For ACA threshold tracking     |
| created_at     | TIMESTAMP    | Record creation time           |

| Column           | Type         | Description                      |
| ---------------- | ------------ | -------------------------------- |
| id               | UUID         | Primary key                      |
| org_id           | UUID FK      | Reference to organization        |
| email            | VARCHAR(255) | Unique per org                   |
| first_name       | VARCHAR(100) | Legal first name                 |
| last_name        | VARCHAR(100) | Legal last name                  |
| work_state       | VARCHAR(2)   | State where employee works       |
| employment_type  | ENUM         | full_time, part_time, contractor |
| start_date       | DATE         | Employment start date            |
| termination_date | DATE NULL    | Null if active                   |
| role             | ENUM         | admin, hr_manager, employee      |

| Column         | Type         | Description                          |
| -------------- | ------------ | ------------------------------------ |
| id             | UUID         | Primary key                          |
| jurisdiction   | VARCHAR(10)  | federal, CA, TX, NYC, etc.           |
| category       | VARCHAR(50)  | wage_hour, leave, tax, posting, etc. |
| title          | VARCHAR(255) | Human-readable requirement name      |
| description    | TEXT         | Plain-English explanation            |
| applies_when   | JSONB        | Conditions (employee count, etc.)    |
| deadline_type  | ENUM         | one_time, recurring, triggered       |
| effective_date | DATE         | When requirement takes effect        |

| Column         | Type      | Description                             |
| -------------- | --------- | --------------------------------------- |
| id             | UUID      | Primary key                             |
| org_id         | UUID FK   | Organization reference                  |
| requirement_id | UUID FK   | Compliance requirement ref              |
| status         | ENUM      | pending, in_progress, complete, overdue |
| due_date       | DATE      | Calculated deadline                     |
| completed_at   | TIMESTAMP | When marked complete                    |
| completed_by   | UUID FK   | User who completed                      |
| notes          | TEXT      | HR notes                                |

| Column       | Type         | Description                               |
| ------------ | ------------ | ----------------------------------------- |
| id           | UUID         | Primary key                               |
| org_id       | UUID FK      | Organization reference                    |
| employee_id  | UUID FK NULL | Null for org-wide docs                    |
| doc_type     | VARCHAR(50)  | i9, offer_letter, handbook, etc.          |
| title        | VARCHAR(255) | Document title                            |
| storage_path | VARCHAR(500) | S3 path                                   |
| status       | ENUM         | draft, pending_signature, signed, expired |
| expires_at   | DATE NULL    | For licenses, work auth                   |
| signed_at    | TIMESTAMP    | E-signature timestamp                     |

| Column        | Type         | Description                                 |
| ------------- | ------------ | ------------------------------------------- |
| id            | UUID         | Primary key                                 |
| document_id   | UUID FK      | Document reference                          |
| reminder_type | ENUM         | initial, followup_1, followup_2, escalation |
| scheduled_for | TIMESTAMP    | When to send                                |
| sent_at       | TIMESTAMP    | Null if not yet sent                        |
| escalate_to   | UUID FK NULL | Manager to escalate to                      |

| Method | Endpoint                        | Description                              |
| ------ | ------------------------------- | ---------------------------------------- |
| GET    | /api/v1/compliance/requirements | List all applicable requirements for org |
| GET    | /api/v1/compliance/status       | Get org compliance dashboard             |
| GET    | /api/v1/compliance/status/{id}  | Get single requirement status            |
| PATCH  | /api/v1/compliance/status/{id}  | Update status (mark complete, add notes) |
| GET    | /api/v1/compliance/alerts       | Get upcoming deadlines & alerts          |
| POST   | /api/v1/compliance/recalculate  | Trigger recalculation of requirements    |

| Method | Endpoint                         | Description                                  |
| ------ | -------------------------------- | -------------------------------------------- |
| GET    | /api/v1/employees                | List employees (paginated, filterable)       |
| POST   | /api/v1/employees                | Create employee (triggers compliance recalc) |
| GET    | /api/v1/employees/{id}           | Get employee details                         |
| PATCH  | /api/v1/employees/{id}           | Update employee                              |
| GET    | /api/v1/employees/{id}/documents | Get employee's documents                     |
| GET    | /api/v1/employees/{id}/tasks     | Get pending tasks for employee               |

| Method | Endpoint                        | Description                                 |
| ------ | ------------------------------- | ------------------------------------------- |
| GET    | /api/v1/documents               | List documents (filterable by type, status) |
| POST   | /api/v1/documents               | Upload new document                         |
| GET    | /api/v1/documents/{id}          | Get document metadata                       |
| GET    | /api/v1/documents/{id}/download | Get presigned download URL                  |
| POST   | /api/v1/documents/{id}/send     | Send for signature                          |
| POST   | /api/v1/documents/{id}/sign     | Record signature (from employee)            |

| Method | Endpoint               | Description                 |
| ------ | ---------------------- | --------------------------- |
| GET    | /api/v1/me             | Get current user profile    |
| PATCH  | /api/v1/me             | Update personal info        |
| GET    | /api/v1/me/documents   | Get my documents            |
| GET    | /api/v1/me/tasks       | Get my pending tasks        |
| GET    | /api/v1/me/pto         | Get PTO balance and history |
| POST   | /api/v1/me/pto/request | Submit PTO request          |
| GET    | /api/v1/policies       | Search company policies     |

| Task Name                  | Schedule   | Description                                       |
| -------------------------- | ---------- | ------------------------------------------------- |
| check_compliance_deadlines | Daily 6am  | Scan for upcoming deadlines, generate alerts      |
| send_document_reminders    | Hourly     | Process reminder queue, send emails               |
| recalculate_org_compliance | On trigger | When employee added/updated, recalc requirements  |
| check_document_expirations | Daily 7am  | Flag expiring documents (30/14/7 day warnings)    |
| sync_compliance_updates    | Weekly     | Check for law/regulation updates from data source |
| generate_compliance_report | On demand  | Async report generation for large orgs            |
| cleanup_expired_tokens     | Daily 2am  | Remove expired refresh tokens                     |

| Route             | Role       | View                         |
| ----------------- | ---------- | ---------------------------- |
| /dashboard        | hr_manager | Compliance overview, alerts  |
| /compliance       | hr_manager | Full compliance checklist    |
| /compliance/:id   | hr_manager | Requirement detail & actions |
| /employees        | hr_manager | Employee directory           |
| /employees/:id    | hr_manager | Employee profile & docs      |
| /documents        | hr_manager | Document management          |
| /portal           | employee   | Employee self-service home   |
| /portal/documents | employee   | My documents to sign         |
| /portal/pto       | employee   | PTO balance & requests       |
| /portal/policies  | employee   | Policy search                |

| Week | Deliverable                                           | Owner          |
| ---- | ----------------------------------------------------- | -------------- |
| 1-2  | DB schema, auth system, basic API scaffold            | Backend        |
| 2-3  | Compliance data model + seed data (10 states)         | Backend + Data |
| 3-4  | Compliance engine: detection, status tracking, alerts | Backend        |
| 4-5  | Document upload, storage, reminder system             | Backend        |
| 5-6  | HR dashboard + compliance views (frontend)            | Frontend       |
| 6-7  | Employee self-service portal (frontend)               | Frontend       |
| 7-8  | Celery tasks: reminders, deadline checks              | Backend        |
| 9-10 | Integration testing, bug fixes, soft launch           | Full team      |

| Risk                        | Mitigation                                 | Priority |
| --------------------------- | ------------------------------------------ | -------- |
| Compliance data accuracy    | Partner with legal firm for validation     | High     |
| Multi-tenant data isolation | Row-level security in Postgres             | High     |
| E-signature vendor lock-in  | Abstract behind interface                  | Medium   |
| Compliance data freshness   | Automated update pipeline + alerts         | Medium   |
| Scale of reminder emails    | Use transactional email service (SendGrid) | Low      |

| Category           | Examples                                                      |
| ------------------ | ------------------------------------------------------------- |
| Wage & Hour        | Minimum wage, overtime rules, meal/rest breaks, pay frequency |
| Tax Registration   | State withholding registration, unemployment insurance        |
| Required Postings  | Federal and state labor law posters (physical and remote)     |
| Leave Laws         | State sick leave, FMLA, parental leave, voting leave          |
| I-9 & Work Auth    | I-9 completion deadlines, reverification, E-Verify states     |
| New Hire Reporting | State new hire reporting deadlines and requirements           |

| Variable         | Description                        |
| ---------------- | ---------------------------------- |
| DATABASE_URL     | PostgreSQL connection string       |
| REDIS_URL        | Redis connection for Celery broker |
| AWS_S3_BUCKET    | S3 bucket for document storage     |
| JWT_SECRET_KEY   | Secret for signing JWTs            |
| SENDGRID_API_KEY | For transactional emails           |
| ESIGN_API_KEY    | DocuSign/HelloSign API key         |
| SENTRY_DSN       | Error tracking                     |
