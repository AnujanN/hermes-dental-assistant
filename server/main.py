import os
import json
import base64
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

from server.config import Config
from server.agent import HermesAgent
from db_server import db_manager, qdrant_manager

app = FastAPI(title="Dental Clinic Voice Assistant Gateway")

# Enable CORS for local Vite + React frontend dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In development, allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup routine: Ingest static memory file and configure DB
@app.on_event("startup")
async def startup_event():
    print("Starting Dental Clinic Gateway server...")
    
    # 1. Initialize SQLite Database
    try:
        db_manager.init_db()
        print("SQLite Database initialized.")
    except Exception as e:
        print(f"Error initializing SQLite database: {e}")
        
    # 2. Ingest MEMORY.md into Qdrant Vector Collection
    try:
        # Check in local folder or relative db_server folder
        memory_file = os.path.join(os.path.dirname(__file__), "..", "db_server", "MEMORY.md")
        if not os.path.exists(memory_file):
            memory_file = os.path.join(os.path.dirname(__file__), "MEMORY.md")
            
        if os.path.exists(memory_file):
            qdrant_manager.ingest_knowledge_document(memory_file)
            print("RAG Knowledge base ingested into Qdrant collection.")
        else:
            print(f"Warning: MEMORY.md file not found at {memory_file}, skipping RAG ingestion.")
    except Exception as e:
        print(f"Error loading Qdrant knowledge base: {e}")

# --- Rest API Endpoints for Dashboard UI ---

class ChatRequest(BaseModel):
    text: str
    phone_number: str = "555-0100"
    session_id: str = "sandbox-session"

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    """
    Text-based Chat endpoint for the Sandbox Simulator.
    Allows testing the agent's memory, persona, and tools via text.
    """
    agent = HermesAgent(session_id=req.session_id, caller_phone=req.phone_number)
    
    # Start call log in DB if it is the first request in session
    log_id = db_manager.start_call_log(req.phone_number)
    
    response_text = await agent.process_message(req.text)
    
    # Close call log with transcription summary
    db_manager.end_call_log(
        log_id=log_id,
        transcript=f"Caller: {req.text}\nAlex: {response_text}",
        sentiment="Neutral",
        duration_seconds=10
    )
    
    return {
        "response": response_text,
        "session_id": req.session_id
    }

@app.get("/api/metrics")
async def get_metrics():
    """Retrieve call volumes, durations, and logs for the dashboard charts"""
    return db_manager.get_dashboard_metrics()

@app.get("/api/appointments")
async def get_appointments():
    """Retrieve list of scheduled appointments for the React calendar component"""
    return db_manager.get_all_appointments()

class ManualAppointmentRequest(BaseModel):
    patient_name: str
    phone_number: str
    date: str
    time: str

@app.post("/api/appointments")
async def manual_appointment(req: ManualAppointmentRequest):
    """Allows front-desk admin to manually add/schedule appointments on the dashboard"""
    result = db_manager.book_appointment(
        patient_name=req.patient_name,
        phone_number=req.phone_number,
        requested_date=req.date,
        requested_time=req.time
    )
    return result

# --- Twilio Voice Media Stream Integration ---

@app.post("/voice/incoming")
async def voice_incoming(request: Request):
    """
    Twilio inbound call entrypoint. Responds with TwiML instructions
    directing Twilio to stream call audio over WebSockets to /voice/stream.
    """
    form_data = await request.form()
    caller = form_data.get("From", "Unknown")
    print(f"Incoming call from: {caller}")
    
    # Construct external WebSocket URL (using relative protocol for local tunnels)
    host = request.headers.get("host", "localhost:8000")
    protocol = "wss" if "ngrok" in host or "tunnel" in host else "ws"
    ws_url = f"{protocol}://{host}/voice/stream"
    
    twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Matthew-Neural">Thank you for calling Radiant Smile Dental. Please hold while I connect you to our virtual receptionist Alex.</Say>
    <Connect>
        <Stream url="{ws_url}">
            <Parameter name="callerNumber" value="{caller}" />
        </Stream>
    </Connect>
</Response>
"""
    return Response(content=twiml_response, media_type="application/xml")

@app.websocket("/voice/stream")
async def voice_stream(websocket: WebSocket):
    """
    WebSocket endpoint handling Twilio Media Streams.
    Pipes caller audio to Deepgram for STT, triggers Hermes agent LLM loop,
    converts replies to speech via Deepgram TTS, and sends audio back to Twilio.
    """
    await websocket.accept()
    print("Twilio Media Stream WebSocket connected.")
    
    stream_sid = None
    caller_phone = "Unknown"
    agent = None
    
    # We maintain standard conversation states
    loop = asyncio.get_event_loop()
    
    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            
            event = data.get("event")
            
            if event == "start":
                stream_sid = data["start"]["streamSid"]
                params = data["start"].get("customParameters", {})
                caller_phone = params.get("callerNumber", "Unknown")
                print(f"Media Stream started. StreamSid: {stream_sid}, Caller: {caller_phone}")
                
                # Initialize Agent for this session
                agent = HermesAgent(session_id=stream_sid, caller_phone=caller_phone)
                
                # We could play an initial greeting here
                greeting = "Hello, this is Alex from Radiant Smile Dental. How can I help you today?"
                await synthesize_and_send_audio(websocket, stream_sid, greeting)
                
            elif event == "media":
                # Raw audio chunk received from Twilio (mulaw 8000Hz base64 encoded)
                payload_base64 = data["media"]["payload"]
                # In production, we stream this payload into the Deepgram STT WebSocket client
                # For this setup: We process audio frames. We mock audio pipeline logs:
                pass
                
            elif event == "stop":
                print(f"Media Stream stopped. StreamSid: {stream_sid}")
                break
                
    except WebSocketDisconnect:
        print("Twilio Media Stream WebSocket disconnected.")
    except Exception as e:
        print(f"Error in Media Stream loop: {e}")
    finally:
        await websocket.close()

async def synthesize_and_send_audio(websocket: WebSocket, stream_sid: str, text: str):
    """
    Calls ElevenLabs TTS REST API to synthesize text response into mulaw 8000Hz audio,
    and forwards it to the active Twilio Media Stream connection.
    """
    if not Config.ELEVENLABS_API_KEY:
        print("Skipping TTS synthesis: ELEVENLABS_API_KEY not configured.")
        return
        
    voice_id = Config.ELEVENLABS_VOICE_ID or "21m00Tcm4TlvDq8ikWAM"
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=ulaw_8000"
    
    headers = {
        "xi-api-key": Config.ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    
    data = {
        "text": text,
        "model_id": Config.ELEVENLABS_MODEL_ID or "eleven_turbo_v2_5"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=data, timeout=15.0)
            if response.status_code == 200:
                audio_bytes = response.content
                audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
                
                # Construct Twilio media packet
                media_message = {
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {
                        "payload": audio_base64
                    }
                }
                await websocket.send_text(json.dumps(media_message))
                print(f"Audio response sent to Twilio via ElevenLabs: '{text}'")
            else:
                print(f"ElevenLabs TTS error {response.status_code}: {response.text}")
        except Exception as e:
            print(f"Failed to generate TTS audio via ElevenLabs: {e}")

async def transcribe_audio_groq(audio_bytes: bytes, filename: str = "caller_audio.wav") -> str:
    """
    Sends compiled audio bytes to Groq Cloud's Whisper API endpoint to transcribe.
    """
    if not Config.GROQ_API_KEY:
        print("Skipping transcription: GROQ_API_KEY not configured.")
        return ""
        
    url = f"{Config.GROQ_BASE_URL}/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {Config.GROQ_API_KEY}"
    }
    
    # Send as multipart/form-data
    files = {
        "file": (filename, audio_bytes, "audio/wav")
    }
    data = {
        "model": Config.GROQ_TRANSCRIPTION_MODEL or "whisper-large-v3",
        "response_format": "json"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, files=files, data=data, timeout=15.0)
            if response.status_code == 200:
                result_json = response.json()
                transcript = result_json.get("text", "")
                return transcript
            else:
                print(f"Groq STT error {response.status_code}: {response.text}")
                return ""
        except Exception as e:
            print(f"Failed to transcribe audio via Groq: {e}")
            return ""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.main:app", host=Config.HOST, port=Config.PORT, reload=True)
