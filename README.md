# 🦷 Dental Clinic Voice Assistant (Alex)

Welcome to the **Dental Clinic Voice Assistant** project. This is a decoupled, RAG-enabled AI receptionist ("Alex") powered by the **Hermes Agent framework**. The assistant helps dental clinics manage incoming telephony calls, handle patient bookings, query clinic logistics (pricing, hours, rules), and visualize call metrics on a sleek React dashboard.

---

## 🗺️ System Architecture

```mermaid
graph TD
    Patient([Patient / Caller]) <-->|Voice Call| Twilio[Twilio Gateway]
    Twilio <-->|WebSocket Stream /voice/stream| FastAPI[FastAPI Server :8000]
    
    FastAPI <-->|OpenRouter API| LLM[Nous Hermes 3 Llama 8B]
    FastAPI <-->|Groq Cloud API| STT[Groq Whisper STT]
    FastAPI <-->|ElevenLabs API| TTS[ElevenLabs TTS]
    FastAPI <-->|SQL Queries| PostgreSQL[(PostgreSQL)]
    FastAPI <-->|Vector Search RAG| Qdrant[(Qdrant Vector DB :6333)]
    
    Dashboard[React Dashboard :5173] <-->|REST API| FastAPI
```

---

## 📂 Project Directory Structure

*   [**`client/`**](file:///c:/Users/Anujan/Desktop/Dental_clinic_assistant/client): A React + Vite web dashboard displaying real-time call volumes, sentiment charts, active call transcripts, and an interactive appointments calendar.
*   [**`server/`**](file:///c:/Users/Anujan/Desktop/Dental_clinic_assistant/server): A FastAPI server managing inbound Twilio WebSockets audio streams, orchestrating the `HermesAgent` core cognitive loop, integrating Speech services, and exposing API endpoints for the dashboard.
*   [**`db_server/`**](file:///c:/Users/Anujan/Desktop/Dental_clinic_assistant/db_server): Database management module holding PostgreSQL schema initialization (`schema.sql`) and Qdrant ingestion scripts (`qdrant_manager.py`) to chunk and index [**`MEMORY.md`**](file:///c:/Users/Anujan/Desktop/Dental_clinic_assistant/db_server/MEMORY.md).
*   [**`tests/`**](file:///c:/Users/Anujan/Desktop/Dental_clinic_assistant/tests): Automated test suites for validating vector chunking, metadata extraction, and RAG search queries.

---

## 🛠️ Prerequisites

Before starting, ensure you have:
*   [Docker](https://www.docker.com/) and Docker Compose installed.
*   *Alternatively, if running locally:* Python 3.11+, Node.js 18+, and WSL (Windows Subsystem for Linux) with `uv` package manager installed.
*   API keys for:
    *   **OpenRouter** (for the `nousresearch/hermes-3-llama-3.1-8b` model)
    *   **Groq Cloud** (for Whisper STT)
    *   **ElevenLabs** (for Neural TTS)
    *   **Twilio** (optional, for configuring voice lines)

---

## ⚙️ Environment Variables Configuration

Copy the `.env.example` templates in the respective directories to a new `.env` file:

1.  **Backend Config**: Copy [**`server/.env.example`**](file:///c:/Users/Anujan/Desktop/Dental_clinic_assistant/server/.env.example) to `server/.env` and update the keys:
    *   `OPENROUTER_API_KEY`
    *   `GROQ_API_KEY`
    *   `ELEVENLABS_API_KEY`
    *   `ELEVENLABS_VOICE_ID` (Optional, defaults to Rachel)
    *   `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` (Optional)
2.  **Database Config**: Copy [**`db_server/.env.example`**](file:///c:/Users/Anujan/Desktop/Dental_clinic_assistant/db_server/.env.example) to `db_server/.env`.
3.  **Frontend Config**: Copy [**`client/.env.example`**](file:///c:/Users/Anujan/Desktop/Dental_clinic_assistant/client/.env.example) to `client/.env`.

---

## 🚀 Running the Application

### Option A: Using Docker Compose (Unified Stack)

The fastest way to spin up the entire ecosystem (PostgreSQL, Qdrant initializer, FastAPI backend, and React frontend) is via Docker Compose.

1.  Start all services from the project root:
    ```bash
    docker compose up -d --build
    ```

Once all containers are running, navigate to:
*   **Frontend Dashboard**: `http://localhost:5173`
*   **FastAPI API Docs**: `http://localhost:8000/docs`

---

### Option B: Local Development Setup (WSL & Native)

If you are developing locally or debugging with your editor/IDE:

#### 1. Setup PostgreSQL and Qdrant
Ensure a local instance of Qdrant is running on port `6333` (e.g. via `docker run -d -p 6333:6333 -p 6334:6334 qdrant/qdrant`).
Run PostgreSQL locally (for example via Docker):
```bash
docker run -d --name radiant-pg -e POSTGRES_DB=radiant -e POSTGRES_USER=radiant -e POSTGRES_PASSWORD=radiant -p 5432:5432 postgres:16-alpine
```

Set `DATABASE_URL` in `db_server/.env` and `server/.env` to:
```bash
postgresql://radiant:radiant@localhost:5432/radiant
```

Then initialize database schema and ingest the knowledge base:
```bash
cd db_server
wsl uv pip install -r requirements.txt
python db_manager.py
python -c "import qdrant_manager; qdrant_manager.ingest_knowledge_document('MEMORY.md')"
```

#### 3. Start the Backend Server
```bash
cd ../server
wsl uv pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

#### 4. Start the React Frontend Dashboard
```bash
cd ../client
npm install
npm run dev
```

---

## 🧪 Running Automated Tests

To verify that the RAG indexing, chunking, and search logic works correctly, run the unittest suite from the root directory using your virtual environment interpreter:

*   **Under WSL/Linux**:
    ```bash
    wsl .venv/bin/python -m unittest tests/test_rag.py
    ```
*   **Under Windows Host**:
    ```powershell
    .venv-win\Scripts\python -m unittest tests/test_rag.py
    ```

---

## 🌐 Free Deployment (Interview)

Use this production-like free setup:
1. Backend: Render Web Service (Docker)
2. Database: Render PostgreSQL (free)
3. Frontend: Vercel (free)

### Backend on Render
1. Create a Render Web Service from this repository.
2. Set Dockerfile path to `server/Dockerfile`.
3. Set health check path to `/health`.
4. Set environment variables:
    - `DATABASE_URL` = Render Postgres Internal Database URL
    - `QDRANT_HOST` = your Qdrant cluster URL
    - `QDRANT_PORT` = `443`
    - `QDRANT_API_KEY` = your Qdrant API key
    - `OPENROUTER_API_KEY` = your OpenRouter key
    - `OPENROUTER_MODEL` = `nousresearch/hermes-3-llama-3.1-8b`
    - `ALLOWED_ORIGINS` = your Vercel frontend URL

### Frontend on Vercel
1. Import this repository on Vercel.
2. Set root directory to `client`.
3. Set environment variable:
    - `VITE_API_URL` = your Render backend URL

### Share these links with interviewers
1. Frontend URL (Vercel)
2. Backend health URL: `https://<backend>/health`
3. Backend API docs URL: `https://<backend>/docs`

---
