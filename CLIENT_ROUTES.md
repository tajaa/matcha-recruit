# Client Routes Reference

Complete map of all routes, their purpose, and what each needs. Written before client rebuild.

---

## Public Routes (No Auth)

| Route | Component | Purpose | Needs |
|---|---|---|---|
| `/` | Landing / TopangaResearch | Marketing homepage (domain-conditional) | None |
| `/for-candidates` | ForCandidates | Candidate marketing | None |
| `/login` | Login | Auth form | `POST /api/auth/login` → stores JWT in localStorage |
| `/login/:brokerSlug` | Login | Broker-branded login | Same + broker branding API |
| `/register` | Register | New user signup | `POST /api/auth/register*` |
| `/register/invite/:token` | RegisterInvite | Accept company invite + register | Token validation API |
| `/register/broker-client/:token` | RegisterBrokerClient | Broker client self-reg | Token API |
| `/invite/:token` | AcceptInvitation | Employee invite acceptance | Token API |
| `/sign/:token` | PolicySign | Sign policy via public link | Token-based policy API |
| `/report/:token` | AnonymousReport | Anonymous incident report | Token-based incident API |
| `/investigation/:token` | InvestigationInterview | Witness/investigation interview | Token-based IR API |
| `/shared/er-export/:token` | ERExportDownload | Download ER case export | Token + optional password |
| `/review-request/:token` | MatchaWorkReviewRequest | Review request flow | Token API |
| `/blog`, `/blog/:slug` | PublicBlogList/Detail | Marketing blog | Blog read API |
| `/terms` | TermsOfService | Terms page | Static |
| `/unauthorized` | Unauthorized | 403 page | Static |

---

## Chat Routes (Separate JWT auth)

| Route | Purpose | Needs |
|---|---|---|
| `/chat/login`, `/chat/register` | Chat-specific auth | Separate chat JWT → `chatClient.ts` |
| `/chat` | Room lobby | List rooms API |
| `/chat/:slug` | Chat room | WebSocket connection, messages REST API |

---

## Protected Routes (JWT required, under `/app`)

### Dashboard & Core

| Route | Purpose | Needs |
|---|---|---|
| `/app` | Dashboard (admin/client analytics) | Company stats, interview data, compliance alerts |
| `/app/notifications` | Notification center | Notifications API |
| `/app/matcha/upcoming` | Deadlines tracker | Leave, compliance, onboarding deadlines |
| `/app/ai-chat` | Gemini/Qwen AI chat | WebSocket or REST AI chat API |
| `/app/settings` | User profile/account | `GET/PATCH /api/users/me`, password/email change |

### Company Setup

| Route | Purpose | Needs |
|---|---|---|
| `/app/matcha/onboarding` | Company setup wizard | Company profile, workspace, templates APIs |
| `/app/matcha/google-workspace` | Google Workspace provisioning | Provisioning status/connect API |
| `/app/matcha/slack-provisioning` | Slack provisioning | Slack OAuth + status API |

### Employee Management (`feature: employees`)

| Route | Purpose | Needs |
|---|---|---|
| `/app/matcha/employees` | Roster, add/edit/bulk import | `GET/POST /api/employees`, CSV bulk upload, Google domain check |
| `/app/matcha/employees/:id` | Employee profile + onboarding tasks | Employee detail, task completion, provisioning status |
| `/app/matcha/onboarding-templates` | Task template library | Templates CRUD API |
| `/app/matcha/pto` (`feature: time_off`) | PTO accrual + requests | PTO API (list, approve, deny) |
| `/app/matcha/leave` (`feature: time_off`) | FMLA/statutory leave | Leave requests, notice documents API |
| `/app/matcha/accommodations` (`feature: accommodations`) | ADA accommodations | Accommodations CRUD |
| `/app/matcha/training` (`feature: training`) | Training programs | Training CRUD + employee assignments |
| `/app/matcha/i9` (`feature: i9`) | I-9 verification | I-9 forms API |
| `/app/matcha/cobra` (`feature: cobra`) | COBRA events | COBRA events CRUD |
| `/app/matcha/separations` (`feature: separation_agreements`) | Exit agreements | Separation agreements API |
| `/app/matcha/pre-termination` (`feature: employees`) | Pre-termination checklist | Pre-termination checks API |

### Offers (`feature: offer_letters`)

| Route | Purpose | Needs |
|---|---|---|
| `/app/matcha/offer-letters` | Create, manage, track offer letters | Offers CRUD, salary guidance AI, PDF generation, signing |

### Policies & Handbooks

| Route | Purpose | Needs |
|---|---|---|
| `/app/matcha/policies` (`feature: policies`) | Policy list/search/distribute | Policies list API |
| `/app/matcha/policies/new`, `/policies/:id/edit` | Create/edit policy (AI-assisted) | Policy CRUD + AI draft endpoint |
| `/app/matcha/policies/:id` | View policy + signature tracking | Policy detail + signature list |
| `/app/matcha/handbook` (`feature: handbooks`) | Handbook list | Handbooks list API |
| `/app/matcha/handbook/new`, `/:id/edit` | Multi-step guided wizard with jurisdiction auto-research | Handbook CRUD, guided draft API, jurisdiction data, auto-research |
| `/app/matcha/handbook/:id` | View handbook + distribution/acks | Handbook detail + ack summary |

### Compliance (`feature: compliance`)

| Route | Purpose | Needs |
|---|---|---|
| `/app/matcha/compliance` | Jurisdiction registry, AI compliance scan, category filters | `compliance.ts` API: locations, requirements, SSE streaming scan, pin/unpin, alerts |

### ER & IR

| Route | Purpose | Needs |
|---|---|---|
| `/app/matcha/er-copilot` (`feature: er_copilot`) | ER case list/dashboard | ER cases list, metrics |
| `/app/matcha/er-copilot/:id` | Case timeline, AI analysis, policy checks, evidence | ER case detail, generate timeline/discrepancies/policy-check/outcome APIs, document upload |
| `/app/ir` (`feature: incidents`) | Incident list | Incidents list |
| `/app/ir/incidents/new` | Create incident + AI categorization | Incident create + AI categorize |
| `/app/ir/incidents/:id` | Incident detail + AI analysis | Incident detail, analytics, recommendations |
| `/app/ir/dashboard` | IR analytics/trends | Analytics APIs |

### Recruiting / Interviews

| Route | Purpose | Needs |
|---|---|---|
| `/interview/:id` | Candidate interview (Gemini Live voice/video) | Interview session + Gemini Live API |
| `/app/interviewer` | Interview practice tool | Tutor session API |
| `/app/admin/candidate-metrics` | Interview prep analytics | Tutor metrics API |
| `/app/admin/candidate-metrics/:id` | Individual prep session detail | Tutor session detail API |

### Matcha Work (`feature: matcha_work`)

| Route | Purpose | Needs |
|---|---|---|
| `/app/matcha/work` | AI task/project overview | MatchaWork API |
| `/app/matcha/work/chats` | AI chat management | MatchaWork chats API |
| `/app/matcha/work/elements` | Element/document library | Elements API |
| `/app/matcha/work/billing` | Billing & usage | Billing API |
| `/app/matcha/work/:threadId` | AI thread/conversation | Thread API |

### Risk Assessment (`feature: risk_assessment`)

**Route:** `/app/matcha/risk-assessment`

The page has two tabs: **Overview** and **Analytics**.

#### Overview Tab
- **Overall score band** — color-coded band (Low / Moderate / High / Critical) with numeric score
- **5 Dimension cards**: `compliance`, `incidents`, `er_cases`, `workforce`, `legislative` — each shows score, sub-metrics, and trend
- **Cost-of-Risk line items** — dollar estimates nested per dimension
- **AI Recommendations panel** — priority-ranked guidance generated by Gemini during snapshot computation
- **Action Items panel** — open items with assignee, due date, status; supports create/edit/complete

#### Analytics Tab
- **Monte Carlo Simulation panel** — expected loss distribution, percentile bands, category breakdown
- **Cohort Heat Map** — dimension scores broken down by `department | location | hire_quarter | tenure`
- **Industry Benchmarks panel** — NAICS peer comparison with percentile rank per dimension
- **Anomaly Detection panel** — statistical process control flags for metric spikes

#### Client / Business View
- Reads the latest stored snapshot (computed by admin)
- Banner: _"Snapshot computed by your account manager"_
- Can create, update, and complete action items; can assign to team members

#### Admin View
- Same as client PLUS:
  - **Company selector dropdown** — switch between companies to view their snapshots
  - **"Run Assessment" button** — calls `POST /admin/run/{company_id}` to recompute snapshot
  - **"Run Simulation" button** inside Monte Carlo panel — calls `POST /admin/monte-carlo/{company_id}`
  - Banner: _"Admin risk assessment console"_

| Route | Purpose | Needs |
|---|---|---|
| `/app/matcha/risk-assessment` | Enterprise risk assessment & action items | `GET /api/risk-assessment/`, `/history`, `/monte-carlo`, `/cohorts`, `/benchmarks`, `/anomalies`, `/action-items`, `/assignable-users`; admin adds `/admin/*` |

### Employee Portal (`role: employee`)

| Route | Purpose | Needs |
|---|---|---|
| `/app/portal` | Employee dashboard + task list | `portal.ts`: dashboard, tasks |
| `/app/portal/pto` | My PTO + requests | Portal PTO API |
| `/app/portal/leave` | My leave requests | Portal leave API |
| `/app/portal/policies` | Company policies/handbooks | Portal policies API |
| `/app/portal/documents` | My signed documents | Portal documents API |
| `/app/portal/profile` | My profile | Portal profile update |
| `/app/portal/onboarding` | My onboarding tasks | Portal onboarding + ack API |

### Broker Portal (`role: broker`)

| Route | Purpose | Needs |
|---|---|---|
| `/app/broker/clients` | Client list + setup | Broker setups CRUD, invite API |
| `/app/broker/reporting` | Portfolio analytics | Broker reporting API |
| `/app/broker/terms` | Partner agreement | Static + accept terms API |

### Admin Panel (`role: admin`)

| Route | Purpose | Needs |
|---|---|---|
| `/app/admin/overview` | Platform analytics | Admin stats API |
| `/app/admin/business-registrations` | Approve new companies | Registration approvals API |
| `/app/admin/company-features` | Feature flag management | Company features API |
| `/app/admin/companies`, `/:id` | Company management | Companies CRUD |
| `/app/admin/brokers` | Broker management | Broker CRUD |
| `/app/admin/jurisdictions` | Jurisdiction data | Jurisdictions API |
| `/app/admin/jurisdiction-data` | Compliance requirement data | Requirements data management |
| `/app/admin/blog`, `/blog/new`, `/blog/:slug` | Blog management | Blog CRUD |
| `/app/admin/blog/comments` | Comment moderation | Blog comments API |
| `/app/admin/poster-orders` | Labor law poster orders | Posters API |
| `/app/admin/news` | HR news tracker | News API |
| `/app/admin/legislative-tracker` | Regulatory change monitor | Legislative tracker API |
| `/app/admin/handbooks` | Industry handbook templates | Industry handbooks API |
| `/app/admin/error-logs` | App error logs | Error logs API |
| `/app/admin/test-bot` | AI chatbot debug | AI chat test API |
| `/app/companies/:id` | Company detail (admin view) | Company detail API |

---

## API Layer

| File | LOC | Purpose |
|---|---|---|
| `client.ts` | 3,822 | Everything except compliance/chat/portal — all REST calls |
| `compliance.ts` | 495 | Compliance locations, requirements, SSE streaming scan |
| `chatClient.ts` | 233 | Chat WebSocket + REST (separate JWT) |
| `portal.ts` | 129 | Employee self-service endpoints |
| `leave.ts` | 232 | Leave types + API |
| `accommodations.ts` | 215 | ADA accommodations API |

---

## Auth Model

- **JWT stored in `localStorage`** as `matcha_access_token` / `matcha_refresh_token`
- **Auto-refresh on 401** — transparent retry in API client
- **5 roles**: `admin`, `client`, `employee`, `candidate`, `broker`
- **Feature flags per company**: `offer_letters`, `policies`, `handbooks`, `compliance`, `employees`, `time_off`, `er_copilot`, `incidents`, `matcha_work`, `vibe_checks`, `enps`, `performance_reviews`, `accommodations`, `training`, `i9`, `cobra`, `separation_agreements`, `risk_assessment`, `interview_prep`
- **Chat has completely separate JWT** — different secret, different login, different token storage
- **Company approval flow**: register → `status='pending'` → admin approves → features enabled

---

## Page Size Reference (LOC before rebuild)

| Page | LOC | Notes |
|---|---|---|
| ERCaseDetail.tsx | 2,938 | 8+ Gemini generation endpoints |
| HandbookForm.tsx | 2,398 | Multi-step AI wizard |
| Compliance.tsx | 2,023 | SSE streaming + complex filters |
| EmployeeDetail.tsx | 1,961 | Nested task/provisioning state |
| OfferLetters.tsx | 1,619 | Offer lifecycle + salary guidance |
| Dashboard.tsx | 1,623 | Analytics + quick actions |
| IRCreate.tsx | 626 | AI categorization on create |
| IRDetail.tsx | 959 | AI analysis + recommendations |
| IRList.tsx | 539 | Case list + lifecycle wizard |
| ERCopilot.tsx | 984 | Case list + metrics |
| Employees.tsx | 915 | Roster + bulk import |

**Layout.tsx**: ~41k LOC — needs decomposition into per-section nav/shell components.
