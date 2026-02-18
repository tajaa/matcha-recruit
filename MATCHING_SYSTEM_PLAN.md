# Matching System Implementation Plan

## Objective
Create a scoring and ranking system to match potential employees (Candidates) to a Company's specific culture profile.

## Current State
- **Data:** 
    - `Company`: "Matcha-Tech" (Seeded)
    - `Culture Interviews`: 3 baseline interviews defining values (Seeded)
    - `Candidate Interviews`: 5 applicant interviews with screening scores (Seeded)
- **Models:** `MatchResult` exists in `matching.py`.

## Phase 1: The Matching Engine (Backend)

### 1. Culture Profile Aggregation
Create a service to synthesize a "Target Profile" from all `culture` type interviews for a company.
- **Input:** List of `conversation_analysis` JSONs.
- **Output:** A set of weighted `dimensions` (e.g., "Autonomy", "Speed") and a consolidated `summary` text.
- **Mechanism:** Frequency analysis of `dimensions_covered` + heuristic keyword extraction from summaries.

### 2. Candidate Scoring Logic
Create a scoring algorithm that compares a Candidate's `screening_analysis` against the Target Profile.
- **Base Score (40%):** The `overall_score` from the candidate's screening (competence/soft skills).
- **Culture Fit (60%):** 
    - **Keyword Match:** Bonus points if candidate `summary` or `notes` contain Company Dimensions.
    - **Sentiment Alignment:** (Future) LLM-based semantic similarity.
- **Output:** `match_score` (0-100) and `match_reasoning` string.

### 3. API Endpoints
- `POST /matcha/matching/run`: Triggers the scoring process for a specific company (or all). Stores results in `match_results` table (needs creation).
- `GET /matcha/matching/results`: Returns ranked list of candidates with scores.

## Phase 2: User Interface (Frontend)

### 1. "Candidates" Tab in Onboarding Center
Extend `OnboardingCenter.tsx` to include a `Candidates` tab.
- **Why?** It sits naturally before "Employees" (Pre-boarding).
- **Features:**
    - List of Candidates sorted by `Match Score`.
    - "Run Matching" button to refresh scores.
    - Status badges (Strong Match, Good Fit, Mismatch).
    - Expandable details showing `match_reasoning`.

### 2. Integration
- Update `OnboardingCenter` to include the new tab.
- Reuse `setup` style cards for the "Run Matching" action if needed, or a simple table view.

## Phase 3: Database Schema
- **New Table:** `match_results`
    - `id` (UUID)
    - `company_id` (UUID)
    - `candidate_interview_id` (UUID) - *Note: Linking to Interview ID as we are using interviews as candidate proxies for now.*
    - `match_score` (Float)
    - `match_reasoning` (Text)
    - `created_at` (Timestamp)

## Execution Steps
1.  **Migration:** Create `match_results` table.
2.  **Backend:** Implement `MatchingService` and Routes.
3.  **Frontend:** Build `Candidates` tab in `OnboardingCenter`.
