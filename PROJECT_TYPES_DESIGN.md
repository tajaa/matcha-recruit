# Project Types Design

## Concept

Each project has a **type** that determines its right-panel UI, sections, and available tools. The chat stays generic — the project type only affects what the right panel shows and what actions are available.

## Project Types

### 1. General / Research Project
**Use case:** Leadership plans, reports, analysis, strategy docs
**Right panel:** Document editor (current TipTap sections)
**Tools:** Add from chat, export PDF/DOCX/MD, image upload
**Sections:** Freeform — user adds/edits sections freely

### 2. Presentation
**Use case:** Slide decks, pitch decks, training materials
**Right panel:** Slide viewer/editor (existing PresentationPanel)
**Tools:** Slide navigation, speaker notes, theme picker, PDF export
**Sections:** Slides with title + bullets + speaker notes

### 3. Job Posting / Recruiting Pipeline
**Use case:** Post a role, collect resumes, review candidates, interview top picks
**Right panel:** Multi-tab pipeline view
**Tabs:**
- **Posting** — job title, description, requirements, compensation (editable)
- **Candidates** — resume batch view (existing ResumeBatchPanel) with status tracking
- **Interviews** — candidates sent to Gemini Live, interview status/scores
- **Shortlist** — earmarked top candidates with notes

**Tools:**
- Drop resumes into chat → auto-added to candidates tab
- Select candidates → send to interview (existing flow)
- Sync interview results
- Export candidate comparison report

**Workflow:**
1. User creates project, picks "Job Posting"
2. Chat: "I need to hire a senior nurse for our Dallas clinic"
3. AI drafts job posting → user adds to Posting tab, edits
4. User drops 20 resumes → candidates populate
5. User reviews, earmarks top 5
6. Sends top 3 to Gemini Live interview
7. Reviews interview scores, makes hiring decision

### 4. Policy / Handbook (future)
**Use case:** Draft compliance policies, employee handbooks
**Right panel:** Policy editor with compliance checks
**Tools:** Jurisdiction-aware suggestions, compliance validation

### 5. Onboarding Plan (future)
**Use case:** Plan onboarding for a batch of new hires
**Right panel:** Employee list + task tracker
**Tools:** Assign tasks, track progress, provisioning

## Data Model Change

Add `project_type` to `mw_projects`:

```sql
ALTER TABLE mw_projects ADD COLUMN project_type VARCHAR(30) DEFAULT 'general'
  CHECK (project_type IN ('general', 'presentation', 'recruiting', 'policy', 'onboarding'));
```

The `sections` JSONB stays generic but each type interprets it differently:
- **general** → `[{ id, title, content }]` (current)
- **presentation** → `[{ id, title, bullets, speaker_notes }]` (slide format)
- **recruiting** → `{ posting: {...}, candidates: [...], interviews: [...], shortlist: [...] }` (structured pipeline)

Or better: add a `project_data` JSONB for type-specific data alongside the generic `sections`:

```sql
ALTER TABLE mw_projects ADD COLUMN project_data JSONB DEFAULT '{}'::jsonb;
```

- `sections` = the document (editable text sections, used by general + policy)
- `project_data` = type-specific structured data (candidates, interviews, posting, slides)

## Frontend Architecture

The right panel renders a different component based on `project_type`:

```tsx
{project.project_type === 'general' && <ProjectPanel ... />}
{project.project_type === 'presentation' && <PresentationPanel ... />}
{project.project_type === 'recruiting' && <RecruitingPipeline ... />}
```

### RecruitingPipeline Component

Tabs: Posting | Candidates | Interviews | Shortlist

```
┌─────────────────────────────────────────┐
│  [Posting] [Candidates] [Interviews]    │
├─────────────────────────────────────────┤
│  Tab: Candidates                        │
│  ┌───────────────────────────────────┐  │
│  │ ★ Sarah Chen · Senior SWE · 6yr  │  │
│  │   "Strong full-stack with cloud"  │  │
│  │   [Interview Sent · 85%]          │  │
│  ├───────────────────────────────────┤  │
│  │   Marcus Johnson · HR Mgr · 10yr │  │
│  │   "Seasoned HR with healthcare"   │  │
│  │   [Not interviewed]               │  │
│  └───────────────────────────────────┘  │
│                                         │
│  Drop resumes here to add candidates    │
└─────────────────────────────────────────┘
```

This reuses `ResumeBatchPanel` and `sendCandidateInterviews` logic but scoped to the project.

## Project Creation Flow

When clicking "+ New Project", show a type picker:

```
┌──────────────────────────────┐
│  What kind of project?       │
│                              │
│  📄 Research / Report        │
│  📊 Presentation             │
│  👥 Job Posting              │
│                              │
│  [Create]                    │
└──────────────────────────────┘
```

## Priority

1. **General** — already built
2. **Recruiting (Job Posting)** — highest value, reuses existing resume batch + interview features
3. **Presentation** — reuses existing PresentationPanel
4. **Policy / Onboarding** — future
