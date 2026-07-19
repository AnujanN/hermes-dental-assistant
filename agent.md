# Agent Specification: Dental Clinic Voice Assistant

This file outlines the core system configuration, behavioral constraints, memory architecture, and tool deployment parameters for the Dental Clinic Voice Assistant powered by the **Hermes Agent framework**.

---

## 1. Core Architecture Overview
The system utilizes a decoupled, cost-optimized pipeline to handle incoming voice traffic natively or via serverless cloud compute infrastructure.

*   **Telephony / Gateway Layer:** Handles inbound telephone requests using Twilio Media Streams or Vapi.
*   **Speech Services Layer:** Real-time audio stream conversion via Deepgram STT (Speech-to-Text) and TTS (Text-to-Speech).
*   **Cognitive & Orchestration Layer:** **Hermes Agent Core** running inside a containerized server environment.
*   **Inference Layer:** OpenRouter API executing the `Nous: Hermes-3-Llama-3.1-8B` model for cost efficiency.

---

## 2. Installation & Environment Setup
For comprehensive installation and configuration parameters, consult the official [Hermes Agent Installation Guide](https://hermes-agent.nousresearch.com/docs/).

### WSL & UV Local Environment Setup
This project executes inside **WSL (Windows Subsystem for Linux)** and uses **`uv`** for lightning-fast Python package and virtual environment management.

To set up the backend dependencies, run:
```bash
wsl uv pip install -r requirements.txt
```

### Profile & Configuration (`~/.hermes/config.yaml`)
```yaml
provider: openrouter
model: nousresearch/hermes-3-llama-3.1-8b
terminal:
  backend: docker
voice:
  provider: deepgram
  stt_model: nova-2-medical
  tts_model: aura-helios-en
```

---

## 3. Personality & Identity (`SOUL.md`)
The core persona of the agent is dictated by the framework's global identity configurations. For a deeper look at modifying the system voice, see [Personality & SOUL.md docs](https://hermes-agent.nousresearch.com/docs/).

```markdown
# SOUL.md - Operational Persona
- Identity: You are "Alex", the virtual front desk receptionist for Radiant Smile Dental Clinic.
- Tone: Warm, professional, concise, reassuring, and highly clear over phone lines.
- Rules: Never use markdown formatting (like asterisks or hashtags) in your spoken responses. Keep sentences under 15 words to maintain a natural phone conversational cadence. If a medical emergency is mentioned, immediately provide the emergency line (555-0199) and instruct them to hang up and call emergency services.
```

---

## 4. Memory Architecture
To avoid losing state between patient interactions, the system utilizes the native, cross-session [Hermes Memory System](https://hermes-agent.nousresearch.com/docs/).

*   **Durable Knowledge (`MEMORY.md`):** Stores static dental clinic details including operating hours (Mon-Fri 8 AM - 5 PM), clinical address, parking details, and pricing structures.
*   **Patient Context (`USER.md`):** Dynamically updated with recurring caller names, past booking histories, or specific anxieties (e.g., "Patient is afraid of needles") to customize future call flows.
*   **Cross-Session Recall:** Leverages the native FTS5 local database indexing to rapidly pull relevant past call logs when a patient rings from a recognized phone number.

---

## 5. Custom Tools & Skills
Hermes uses procedural memory to resolve tasks. For implementation patterns, see the [Hermes Tools & Toolsets documentation](https://hermes-agent.nousresearch.com/docs/).

### Custom Python Tools (`~/.hermes/skills/`)
The agent is explicitly equipped with two mission-critical, custom-engineered Python tool workflows:

1.  **`clinic_info_retriever`:** Parses local indexed structured files to answer incoming questions regarding operational logistics, accepted insurances, and treatment options.
2.  **`calendar_appointment_booker`:** Interacts directly with the Cal.com / Google Calendar API backend. 
    *   *Arguments:* `patient_name` (str), `phone_number` (str), `requested_date` (str), `requested_time` (str).
    *   *Action:* Checks slot availability. If open, commits the booking and returns a confirmation string. If blocked, provides the next 3 available time slots.

### Auto-Generated Skills
As the agent resolves unique scheduler bottlenecks over time, it will automatically compile human-readable procedural markdown strategies via the native [Hermes Skills System](https://hermes-agent.nousresearch.com/docs/) to speed up subsequent booking requests.

---

## 6. Serverless Deployment & Live Evaluation

### Web Gateway & Reverse Proxy
*   The application loop is exposed via a lightweight **FastAPI Webhook Server**.
*   Network traffic is securely tunneled and protected using an SSL layer managed through a reverse proxy.

### Project Deliverables for Evaluation
1.  **Live Sandbox Dashboard:** `https://vercel.app` (Displays an embedded live calendar and incoming call metrics).
2.  **Live Testing Line:** `+1 (555) 839-2001` (A fully functional Twilio inbound line routing directly into our active Hermes runtime environment for evaluation).
