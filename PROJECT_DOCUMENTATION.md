# HR Recruitment Agent — Project Documentation

This document describes what was built, how it maps to the specification, and what was fixed or added during development.

---

## 1. Project overview

**Goal:** An end-to-end, AI-assisted HR recruitment pipeline: resume ingestion and ATS scoring, technical interview, HR screening, scheduling with email, an HR dashboard, and a DB-grounded chatbot.

**Mandatory stack (per spec):**

- **Python** with **FastAPI** for HTTP and WebSockets  
- **LangGraph** for every agent (explicit graphs, session state)  
- **Async I/O** for I/O-bound work  
- **OOP**-style service and agent classes  

**Flexible choices used:**

- **Frontend:** React + Vite (dashboard, forms, WebSocket clients)  
- **Database:** SQLite via SQLAlchemy 2 async (`aiosqlite`) — easy local demo; can swap to PostgreSQL via `DATABASE_URL`  
- **Email:** `aiosmtplib` with deduplication table; `MOCK_EMAIL=true` logs only  
- **Calendar / meeting link:** Placeholder URL pattern (`default_meeting_base` + unique path)  

**Bonus:**

- **MCP-style** stdio server (`mcp_server/hr_recruitment_mcp.py`) exposing a `list_candidates` tool over the SQLite file  

---

## 2. Repository layout

| Path | Purpose |
|------|---------|
| `backend/hr_agent/` | Application package: config, DB models, agents, API, services |
| `backend/hr_agent/agents/` | LangGraph graphs: ATS, technical interview, screening, scheduling, chatbot |
| `backend/hr_agent/api/` | FastAPI `main`, REST routers, WebSocket handlers |
| `backend/hr_agent/db/` | SQLAlchemy models, async engine/session, `init_db` |
| `backend/hr_agent/services/` | LLM, RAG, email, resume text extraction |
| `frontend/` | React + Vite UI |
| `package.json` (repo root) | npm workspace so `npm install` / `npm run dev` work from root |
| `mcp_server/hr_recruitment_mcp.py` | Optional stdio MCP-style server |
| `README.md` | Quick architecture, setup, API highlights |

---

## 3. Implemented agents (LangGraph)

Each agent is implemented as a **stateful graph** with nodes and edges; short-term state lives in graph state; outputs are persisted to the database before downstream steps.

### 3.1 ATS agent (`ats_agent.py`)

- **Nodes:** RAG context over resume vs JD → LLM JSON score (skills, experience, keywords, overall 0–100) → persist candidate + stage → optional rejection email if below threshold  
- **Threshold:** Configurable `ats_pass_threshold` (default **80**): pass → `technical_interview`, fail → `ats_rejected`  
- **RAG:** `RAGService.build_ats_context` chunks resume, embeds (OpenAI or mock vectors), scores chunks vs JD centroid  
- **Persistence:** `Candidate` row updated with `ats_score`, `ats_breakdown`, email extracted from resume text when possible  

### 3.2 Technical interview agent (`technical_interview_agent.py`)

- **Flow:** Router → generate question (LLM, level from junior/mid/senior) → user answers via WebSocket → evaluate (score + reasoning) → repeat or finalize  
- **Timer:** Enforced on the server in `api/ws/interview.py` (deadline after each question)  
- **State:** `question_index` echoed from **generate** so cache/WebSocket never lose progress (fix documented in code comments)  
- **Persistence:** `TechnicalInterviewSession.transcript`, candidate `technical_total_score`, stage → `hr_screening`  

### 3.3 HR screening agent (`screening_agent.py`)

- **Flow:** Load resume → LLM generates questions (avoid facts already in resume; include availability + education topics) → persist questions → later submit structured answers  
- **Persistence:** `ScreeningSession`; candidate stage → `scheduling` after answers submitted  

### 3.4 Scheduling + email agent (`scheduling_agent.py`)

- **Flow:** Build meeting link → persist `SchedulingRecord` → send candidate + HR emails (deduped via `EmailLog`)  
- **Persistence:** Stage → `interview_scheduled`  

### 3.5 HR chatbot agent (`chatbot_agent.py`)

- **Flow:** Ground on DB rows + RAG snippets over resume text → tool-like parsing (stage updates, create role + HR notification) → LLM reply constrained to facts + tool results  
- **Requirement:** Answers grounded in database reads, not free-form hallucination of candidate data  

---

## 4. API surface

- **REST:** `/api/health`, `/api/roles`, `/api/candidates/upload`, screening and schedule routes, `/api/dashboard/summary`  
- **WebSockets:** `/ws/interview` (technical round + timer), `/ws/hr-chat` (HR assistant)  
- **OpenAPI:** `/docs` when the server is running  

---

## 5. Frontend (`frontend/`)

- **Filters:** Role and pipeline stage  
- **Create role:** POST job title, JD, headcount  
- **Upload resume:** Multipart upload → ATS pipeline  
- **Candidates table:** Stage, ATS score, technical score, email  
- **Technical interview:** REST start session + WebSocket; 30s-style countdown; paste disabled on answer field  
- **Screening & scheduling:** Forms wired to API  
- **Chatbot:** WebSocket chat to grounded agent  
- **Dev proxy:** Vite proxies `/api` and `/ws` to the backend (see `frontend/vite.config.ts`)  

---

## 6. Memory model (spec compliance)

- **Short-term:** LangGraph state carries resume excerpts, transcripts, chat context within a run  
- **Long-term:** SQLite stores roles, candidates, sessions, email log; HR chatbot reads from DB (+ RAG snippets)  

---

## 7. Fixes and improvements applied during development

These were implemented in code and commits; they address real errors or UX issues encountered while building and running the app.

| Area | Issue | Resolution |
|------|--------|------------|
| **Python 3.9** | `zip(..., strict=True)` in `rag_service.py` not supported | Removed `strict=True` so ATS RAG runs on 3.9 |
| **ATS / upload** | Internal server error on upload | Same as above (trace showed failure in RAG zip) |
| **Technical interview** | `question_index` lost between WebSocket turns | `node_generate_question` returns `question_index`; WebSocket `_question_index_from_state()` fallback uses `len(transcript)` if key missing |
| **SQLite** | `database is locked` with DB Browser open | Engine `connect_args={"timeout": 30.0}` for SQLite; guidance to close DB Browser or avoid long write locks |
| **Create role** | 500 when SQLite locked | Same timeout + close external DB tools |
| **Scheduling** | 422: `availability_note` min length 3 | `SchedulingIn` relaxed to `min_length=1`, `max_length=8000`; frontend trims input and placeholder text |
| **Mock ATS** | Always **81.5** without API key | Mock ATS scores derived deterministically from SHA-256 of resume/JD prompt text (varied scores; rationale explains mock mode) |
| **npm** | `npm install` at repo root failed (no `package.json`) | Root `package.json` with `workspaces: ["frontend"]` and scripts `dev` / `build` |
| **Git / GitHub** | Push needs auth | Documented HTTPS + PAT and SSH setup; remote `origin` can point to `HR-Recruitment-Agent-System-` (adjust username/URL) |

---

## 8. Configuration (environment)

Copy `backend/.env.example` to `backend/.env` and set as needed:

- `OPENAI_API_KEY` — real LLM + embeddings (leave empty for mock LLM path)  
- `MOCK_LLM` — force mock even if a key is present (testing)  
- `MOCK_EMAIL` — skip SMTP; log emails only  
- `DATABASE_URL` — default SQLite under `backend/` when the API runs from `backend/`  
- `CORS_ORIGINS` — frontend origins for browser access  
- `ATS_PASS_THRESHOLD`, `INTERVIEW_QUESTION_COUNT`, `INTERVIEW_ANSWER_SECONDS`, etc.  

---

## 9. How to run (short)

**Backend**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn hr_agent.api.main:app --host 127.0.0.1 --port 8000 --reload
```

**Frontend**

```bash
cd "/path/to/HR Agent"    # repo root
npm install
npm run dev
```

Or `cd frontend && npm install && npm run dev`.

**MCP (optional)**

```bash
python3 mcp_server/hr_recruitment_mcp.py
```

---

## 10. Git

- Repository initialized with incremental commits  
- Remote `origin` should be set to your GitHub repo; use **HTTPS + Personal Access Token** or **SSH key** registered on GitHub to push  

---

## 11. Specification mapping (high level)

| Requirement | Implementation |
|-------------|----------------|
| LangGraph agents | ATS, technical, screening, scheduling, chatbot — each as a graph |
| FastAPI + WebSockets | REST + `/ws/interview`, `/ws/hr-chat` |
| ATS scoring + threshold | RAG + LLM; 80% gate; persistence |
| Technical interview | LLM Q&A, timed answers, evaluation, transcript |
| HR screening | Resume-based questions, structured storage |
| Scheduling + email | Availability, link, emails, dedupe log, stage update |
| Dashboard + filters | Summary API + React UI |
| Chatbot grounded in DB | Graph + SQL/RAG-backed context |
| Memory | Graph state + SQLite |
| Pydantic | Request/response models |
| Bonus MCP | `mcp_server/hr_recruitment_mcp.py` |

---

*Document generated for the HR Recruitment Agent System codebase. Update this file when you add features or change deployment.*
