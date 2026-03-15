# Plan: IR Investigation Interview Agent

## Overview

Create an agentic system that uses the existing Gemini Live voice interview infrastructure to conduct **investigation interviews** for IR (Incident Report) cases. When an IR incident requires witness interviews or follow-up questioning, the system:

1. Generates targeted interview questions based on the incident details
2. Conducts a live voice interview using Gemini Live API
3. Stores the transcript as an ER Copilot document
4. Makes transcript available for ER Copilot AI analysis (timeline, discrepancies, policy check)

This bridges IR Incidents → Voice Interviews → ER Copilot into a connected investigation pipeline.

---

## Architecture

```
IR Incident (investigating status)
    │
    ├── "Schedule Investigation Interview" action
    │       │
    │       ▼
    │   Generate Questions (Gemini)
    │   ─ incident details, type, witnesses, category_data
    │   ─ produces 8-12 targeted questions
    │       │
    │       ▼
    │   Create Interview Record
    │   ─ interview_type = "investigation"
    │   ─ linked to incident_id + optional er_case_id
    │       │
    │       ▼
    │   Live Voice Session (existing WebSocket infra)
    │   ─ custom investigation system prompt
    │   ─ questions injected into prompt
    │   ─ Gemini conducts structured interview
    │       │
    │       ▼
    │   Post-Session Processing
    │   ─ transcript saved to interview record
    │   ─ auto-create ER case if none exists
    │   ─ transcript uploaded as er_case_document (type="transcript")
    │   ─ chunked for RAG search
    │       │
    │       ▼
    │   ER Copilot
    │   ─ transcript available for timeline/discrepancy/policy analysis
    │   ─ searchable via evidence search
```

---

## Step-by-Step Implementation

### Step 1: Add `investigation` interview type

**Files:** `server/app/core/services/gemini_session.py`, `server/app/matcha/models/interview.py`

- Add `"investigation"` to the `InterviewType` enum/literal
- Add `investigation` system prompt to `gemini_session.py`:
  - Role: "You are conducting a workplace investigation interview"
  - Tone: neutral, fact-finding, non-leading
  - Structure: introduction → open-ended account → targeted questions → clarification → close
  - Injected context: incident summary, interviewee role (witness/complainant/respondent), generated questions
  - Rules: don't suggest conclusions, don't promise outcomes, note if interviewee seems distressed, document exact quotes when possible
- Add new fields to interview DB model: `incident_id` (UUID, nullable FK), `er_case_id` (UUID, nullable FK), `interviewee_role` (varchar: complainant/respondent/witness)

### Step 2: Question generation service

**New file:** `server/app/matcha/services/ir_interview_questions.py`

- `generate_investigation_questions(incident, interviewee_role, prior_transcripts=None) -> list[str]`
- Uses Gemini to generate 8-12 questions based on:
  - Incident type, description, severity, category_data
  - Interviewee's role (complainant gets different questions than witness)
  - Witness statements already on file
  - Prior interview transcripts (to avoid re-asking answered questions, and to probe gaps/discrepancies)
- Question categories:
  - **Foundational**: "Tell me what happened in your own words"
  - **Temporal**: "When did you first notice...?"
  - **Observational**: "Who else was present?"
  - **Behavioral**: Type-specific (safety → equipment/procedures, behavioral → interactions/statements)
  - **Follow-up**: Based on existing witness statements or prior transcripts
- Returns structured list with question text + category + rationale

### Step 3: Interview initiation endpoint

**File:** `server/app/matcha/routes/ir_incidents.py` (new endpoint)

- `POST /ir/incidents/{incident_id}/investigation-interviews`
- Request body: `{ interviewee_name, interviewee_email, interviewee_role, er_case_id? }`
- Validates: incident exists, status is `investigating` or `action_required`
- Generates questions via Step 2 service
- Creates interview record with `interview_type="investigation"`, linked `incident_id`
- Returns: `{ interview_id, questions_generated, invite_url, ws_auth_token }`
- Optionally sends email invite to interviewee with a secure link

### Step 4: Investigation interview prompt in Gemini Live

**File:** `server/app/core/services/gemini_session.py`

- New prompt template `INVESTIGATION_INTERVIEW_PROMPT`:
  ```
  You are conducting a workplace investigation interview on behalf of {company_name}.

  Context:
  - Incident: {incident_summary}
  - Interviewee: {interviewee_name} ({interviewee_role})
  - Your prepared questions (use as a guide, not a rigid script):
  {questions}

  Interview protocol:
  1. Introduce yourself, explain the process, note confidentiality
  2. Ask the interviewee to describe events in their own words
  3. Work through your prepared questions naturally
  4. Ask clarifying follow-ups when answers are vague
  5. Before closing, ask "Is there anything else relevant you'd like to share?"
  6. Thank them and explain next steps

  Rules:
  - Be neutral and non-judgmental
  - Do not lead the witness or suggest answers
  - Do not make promises about outcomes
  - Do not share other witnesses' statements
  - If the interviewee becomes distressed, acknowledge it and offer to pause
  - Keep responses to 2-3 sentences max
  ```

- Wire up in `connect()` method to handle `interview_type="investigation"`

### Step 5: WebSocket handler updates

**File:** `server/app/matcha/routes/interviews.py`

- Update `interview_websocket` to handle investigation type:
  - Load incident data and generated questions
  - Pass to `gemini_session.connect()` with investigation prompt
  - Use speaker labels: "Investigator" / interviewee_name
- Support public invite flow (interviewee may not be a platform user):
  - Generate a short-lived interview token similar to existing review/candidate flows
  - Token encodes `interview_id` + `incident_id`

### Step 6: Post-session transcript pipeline

**File:** `server/app/workers/tasks/interview_analysis.py` (extend existing)

- After investigation interview completes:
  1. Save transcript to interview record (existing flow)
  2. **New**: Create or link ER case:
     - If `er_case_id` provided, use it
     - If no ER case exists for this incident, auto-create one:
       - Title: "Investigation: {incident.title}"
       - Category: mapped from incident_type (safety→safety, behavioral→misconduct, etc.)
       - Status: "open"
       - Link involved employees from incident
  3. **New**: Upload transcript as `er_case_document`:
     - `document_type = "transcript"`
     - `filename = "Investigation Interview - {interviewee_name} - {date}.txt"`
     - Store formatted transcript text
     - Trigger document processing (text extraction + chunking for RAG)
  4. **New**: Run investigation-specific analysis:
     - `InvestigationAnalyzer.analyze_investigation_interview(transcript, incident)`
     - Produces: key facts extracted, credibility notes, gaps identified, follow-up questions suggested
     - Stored as `investigation_analysis` on the interview record

### Step 7: IR Incident ↔ ER Case linking

**Migration:** New columns + junction table

- `ir_incidents` table: add `er_case_id` (UUID, nullable FK to er_cases)
- `interviews` table: add `incident_id` (UUID, nullable FK to ir_incidents), add `er_case_id` (UUID, nullable FK to er_cases)
- New table `ir_investigation_interviews`:
  ```sql
  CREATE TABLE ir_investigation_interviews (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      incident_id UUID NOT NULL REFERENCES ir_incidents(id),
      interview_id UUID NOT NULL REFERENCES interviews(id),
      er_case_id UUID REFERENCES er_cases(id),
      interviewee_role VARCHAR(50),  -- complainant, respondent, witness
      questions_generated JSONB,     -- the prepared questions
      status VARCHAR(50) DEFAULT 'pending',  -- pending, scheduled, completed, cancelled
      created_at TIMESTAMP DEFAULT NOW(),
      completed_at TIMESTAMP
  );
  ```

### Step 8: ER Copilot integration

**File:** `server/app/matcha/routes/er_copilot.py`

- Update case detail endpoint to show linked investigation interviews
- Update suggested guidance to recommend interviews when:
  - Case has < 2 transcripts and witnesses are listed
  - Discrepancy analysis shows conflicting accounts needing clarification
  - Timeline has gaps that a specific witness could fill
- Add guidance action type: `"schedule_interview"` that links to the interview scheduling flow

### Step 9: List & manage investigation interviews on an incident

**File:** `server/app/matcha/routes/ir_incidents.py`

- `GET /ir/incidents/{incident_id}/investigation-interviews` — list all investigation interviews for an incident with status, interviewee info, transcript availability
- `GET /ir/incidents/{incident_id}/investigation-interviews/{interview_id}` — get detail with transcript + analysis
- `DELETE /ir/incidents/{incident_id}/investigation-interviews/{interview_id}` — cancel a pending interview

---

## Data Flow Summary

```
1. User clicks "Schedule Interview" on IR incident
2. System generates questions from incident context
3. Interview record created, invite sent to interviewee
4. Interviewee joins via link → WebSocket → Gemini Live voice session
5. Gemini conducts structured investigation interview
6. Session ends → transcript saved
7. Auto-create ER case if needed, upload transcript as case document
8. ER Copilot can now analyze all transcripts: timeline, discrepancies, policy violations
9. Suggested guidance updates: "2 interviews completed, consider interviewing witness X"
```

## Feature Flag

Gate behind `ir_interviews` in company `enabled_features`. Only available when both `incidents` and `er_copilot` features are also enabled.

---

## Migration Required

Single Alembic migration adding:
- `er_case_id` column to `ir_incidents`
- `incident_id` column to `interviews`
- `er_case_id` column to `interviews`
- `interviewee_role` column to `interviews`
- `ir_investigation_interviews` table
- `investigation_analysis` JSONB column to `interviews`
- Index on `ir_investigation_interviews(incident_id)`
- Index on `interviews(incident_id)` WHERE incident_id IS NOT NULL

---

## Files to Create/Modify

| File | Action |
|------|--------|
| `server/app/matcha/services/ir_interview_questions.py` | **New** — question generation service |
| `server/app/core/services/gemini_session.py` | Modify — add investigation prompt + type handling |
| `server/app/matcha/models/interview.py` | Modify — add investigation fields/types |
| `server/app/matcha/models/ir_incident.py` | Modify — add investigation interview response models |
| `server/app/matcha/routes/ir_incidents.py` | Modify — add interview scheduling/listing endpoints |
| `server/app/matcha/routes/interviews.py` | Modify — handle investigation type in WebSocket |
| `server/app/workers/tasks/interview_analysis.py` | Modify — add post-session ER case creation + doc upload |
| `server/app/matcha/services/er_guidance.py` | Modify — add interview recommendations to guidance |
| `server/app/matcha/routes/er_copilot.py` | Modify — show linked interviews on case detail |
| `server/app/database.py` | Modify — add new table/columns to init_db |
| `server/alembic/versions/xxx_add_investigation_interviews.py` | **New** — migration |
