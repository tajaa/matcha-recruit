# Matcha Recruit

AI-powered recruitment tool that uses voice interviews to understand company culture and match candidates based on culture fit.

## How It Works

### The Problem

Traditional recruitment focuses heavily on skills and experience, but culture fit is often the deciding factor in whether a hire succeeds. Assessing culture fit is subjective, time-consuming, and inconsistent.

### The Solution

Matcha Recruit automates culture assessment through AI voice interviews with HR stakeholders, then uses that data to score candidates on culture fit.

## System Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         MATCHA RECRUIT                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. CREATE COMPANY                                                   │
│     └── Add company details (name, industry, size)                  │
│                                                                      │
│  2. CONDUCT VOICE INTERVIEWS                                        │
│     ├── HR head starts voice interview                              │
│     ├── AI interviewer asks about culture, values, work style       │
│     ├── Real-time audio streaming via WebSocket                     │
│     └── Transcript saved automatically                              │
│                                                                      │
│  3. BUILD CULTURE PROFILE                                           │
│     ├── Multiple stakeholders can be interviewed                    │
│     ├── AI extracts culture traits from each transcript             │
│     └── Aggregate into unified company culture profile              │
│                                                                      │
│  4. UPLOAD CANDIDATES                                               │
│     ├── Upload PDF/DOCX resumes                                     │
│     ├── AI parses skills, experience, education                     │
│     └── Infers work style preferences from resume signals           │
│                                                                      │
│  5. MATCH CANDIDATES                                                │
│     ├── AI compares candidate profiles to culture profile           │
│     ├── Generates match score (0-100)                               │
│     └── Provides detailed reasoning and fit breakdown               │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Architecture

```
┌──────────────────┐         ┌──────────────────┐
│                  │         │                  │
│  React Frontend  │◄───────►│  FastAPI Backend │
│  (Vite + TS)     │  HTTP   │                  │
│                  │  + WS   │                  │
└──────────────────┘         └────────┬─────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
            ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
            │  PostgreSQL  │  │ Gemini Live  │  │ Gemini Flash │
            │  Database    │  │ Voice API    │  │ Lite (Text)  │
            └──────────────┘  └──────────────┘  └──────────────┘
```

### Components

| Component | Purpose |
|-----------|---------|
| **Frontend** | React SPA for managing companies, interviews, candidates |
| **Backend** | FastAPI server handling API requests and WebSocket connections |
| **PostgreSQL** | Stores companies, interviews, candidates, culture profiles, matches |
| **Gemini Live Voice API** | Real-time voice conversations for culture interviews |
| **Gemini 2.5 Flash Lite** | Text analysis for culture extraction, resume parsing, matching |

## Features

### Voice Interviews

The AI interviewer conducts natural conversations about company culture:

- Work environment and collaboration style
- Company values and what gets celebrated
- Communication patterns (async vs sync)
- Growth and development opportunities
- Work-life balance expectations
- What makes someone successful

The interview is bidirectional audio - the HR person speaks naturally and the AI responds conversationally, asking follow-up questions.

### Culture Profile

After interviews, the system extracts structured culture data:

```json
{
  "collaboration_style": "highly_collaborative",
  "communication": "async_first",
  "pace": "fast_startup",
  "hierarchy": "flat",
  "values": ["innovation", "transparency", "ownership"],
  "work_life_balance": "flexible",
  "remote_policy": "hybrid",
  "key_traits": ["self-starter", "comfortable with ambiguity"],
  "red_flags": ["needs constant direction", "prefers rigid structure"]
}
```

Multiple interviews are aggregated into a single profile, capturing perspectives from different stakeholders.

### Resume Parsing

Upload PDF or DOCX resumes. The AI extracts:

- Contact information
- Skills (technical and soft)
- Years of experience
- Education history
- Work history with highlights
- Inferred culture preferences based on resume signals

### Culture Matching

The matching engine compares candidates against company culture:

- **Match Score** (0-100): Overall culture fit
- **Fit Breakdown**: Scores for collaboration, pace, values, growth, work style
- **Reasoning**: Detailed explanation of the match
- **Concerns**: Potential misalignments to explore
- **Interview Suggestions**: Follow-up questions for human interviews

## Setup

### Prerequisites

- Python 3.12+
- Node.js 18+
- PostgreSQL database
- Gemini API key or Google Cloud project with Vertex AI

### Backend Setup

```bash
cd server

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings:
#   DATABASE_URL=postgresql://user:pass@localhost:5432/matcha
#   LIVE_API=your-gemini-api-key

# Run the server
python run.py
```

Backend runs on `http://localhost:8000`

### Frontend Setup

```bash
cd client

# Install dependencies
npm install

# Run development server
npm run dev
```

Frontend runs on `http://localhost:5173`

### Database

The backend automatically creates tables on first startup. Required tables:

- `companies` - Company information
- `interviews` - Interview sessions and transcripts
- `culture_profiles` - Aggregated culture data per company
- `candidates` - Parsed resume data
- `match_results` - Culture fit scores and reasoning

## API Endpoints

### Companies
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/companies` | Create a company |
| GET | `/api/companies` | List all companies |
| GET | `/api/companies/{id}` | Get company with culture profile |
| DELETE | `/api/companies/{id}` | Delete company |

### Interviews
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/companies/{id}/interviews` | Create interview session |
| GET | `/api/companies/{id}/interviews` | List company interviews |
| GET | `/api/interviews/{id}` | Get interview details |
| WS | `/api/ws/interview/{id}` | WebSocket for voice interview |
| POST | `/api/companies/{id}/aggregate-culture` | Build culture profile |

### Candidates
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/candidates/upload` | Upload resume (multipart) |
| GET | `/api/candidates` | List all candidates |
| GET | `/api/candidates/{id}` | Get candidate details |
| DELETE | `/api/candidates/{id}` | Delete candidate |

### Matching
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/companies/{id}/match` | Run matching for company |
| GET | `/api/companies/{id}/matches` | Get match results |

## WebSocket Protocol

### Audio Format
- **Input**: 16kHz PCM, mono, 16-bit signed integers
- **Output**: 24kHz PCM, mono, 16-bit signed integers
- **Framing**: First byte indicates direction (0x01 = client→server, 0x02 = server→client)

### Text Messages

```json
// Transcription
{"type": "user", "content": "We value collaboration...", "timestamp": 1234567890}
{"type": "assistant", "content": "That's interesting...", "timestamp": 1234567891}

// Status
{"type": "status", "content": "ready", "timestamp": 1234567892}
{"type": "system", "content": "Connected to interview", "timestamp": 1234567893}
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `LIVE_API` | Gemini API key | Yes* |
| `VERTEX_PROJECT` | Google Cloud project ID | Yes* |
| `VERTEX_LOCATION` | Vertex AI region (default: us-central1) | No |
| `GEMINI_LIVE_MODEL` | Voice model (default: gemini-live-2.5-flash-native-audio) | No |
| `GEMINI_ANALYSIS_MODEL` | Text model (default: gemini-3-flash-preview) | No |
| `GEMINI_VOICE` | Voice name (default: Kore) | No |
| `PORT` | Server port (default: 8000) | No |

*Either `LIVE_API` or `VERTEX_PROJECT` is required.

## Usage Example

1. **Add a company**: Click "Add Company", enter "Acme Corp", Technology, Startup
2. **Start interview**: Click on Acme Corp → "New Interview" → Enter interviewer details → "Start Interview"
3. **Conduct interview**: Click "Connect" → "Start Speaking" → Have a conversation about culture
4. **End interview**: Click "End Interview" when done
5. **Repeat**: Interview multiple stakeholders for better profile
6. **Aggregate**: Click "Aggregate Culture Profile" to build the profile
7. **Upload candidates**: Go to Candidates → Upload resumes
8. **Match**: Go back to Acme Corp → Click "Run Matching"
9. **Review**: See candidates ranked by culture fit with explanations

## Tech Stack

**Backend**
- FastAPI (Python web framework)
- asyncpg (PostgreSQL async driver)
- google-genai (Gemini API client)
- PyMuPDF + python-docx (Resume parsing)

**Frontend**
- React 18 + TypeScript
- Vite (Build tool)
- Tailwind CSS v4
- React Router

**AI**
- Gemini Live 2.5 Flash Native Audio (Voice)
- Gemini 2.5 Flash Lite (Text analysis)
