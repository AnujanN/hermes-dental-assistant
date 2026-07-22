import os
import json
import base64
import asyncio
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

from server.config import Config
from server.agent import HermesAgent
from server.validators import (
    ValidationError,
    validate_chat_request,
    validate_appointment_request,
    validate_twilio_form_data,
    validate_media_stream_event,
    validate_tts_config,
    validate_stt_config,
    validate_audio_payload,
)
from db_server import db_manager, qdrant_manager

logger = logging.getLogger(__name__)

app = FastAPI(title="Dental Clinic Voice Assistant Gateway")

_session_agents = {}

# Enable CORS for local Vite + React frontend dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
        if origin.strip()
    ],
    allow_origin_regex=os.environ.get("ALLOWED_ORIGIN_REGEX", None),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup routine: Ingest static memory file and configure DB
@app.on_event("startup")
async def startup_event():
    logger.info("Starting Dental Clinic Gateway server...")
    
    # 1. Initialize PostgreSQL schema
    try:
        db_manager.init_db()
        logger.info("PostgreSQL schema initialized.")
    except Exception as exc:
        logger.error("Error initializing PostgreSQL schema: %s", exc, exc_info=True)
        
    # 2. Trigger RAG ingestion in the background to keep startup and health checks responsive.
    asyncio.create_task(_ingest_knowledge_background())


async def _ingest_knowledge_background():
    """Locate and ingest the MEMORY.md knowledge document into Qdrant."""
    try:
        memory_file = os.path.join(os.path.dirname(__file__), "..", "db_server", "MEMORY.md")
        if not os.path.exists(memory_file):
            memory_file = os.path.join(os.path.dirname(__file__), "MEMORY.md")

        if os.path.exists(memory_file):
            await asyncio.to_thread(qdrant_manager.ingest_knowledge_document, memory_file)
            logger.info("RAG Knowledge base ingested into Qdrant collection.")
        else:
            logger.warning("MEMORY.md file not found at %s, skipping RAG ingestion.", memory_file)
    except Exception as exc:
        logger.error("Error loading Qdrant knowledge base: %s", exc, exc_info=True)

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
    try:
        session_key, text, phone_number = validate_chat_request(
            req.session_id, req.text, req.phone_number
        )
    except ValidationError as exc:
        logger.warning("Chat request rejected: %s", exc)
        return {"error": str(exc), "session_id": req.session_id or "sandbox-session"}

    try:
        agent = _get_or_create_agent(session_key, phone_number)
        response_text = await agent.process_message(text)
    except Exception as exc:
        logger.error("Error processing chat message for session %s: %s", session_key, exc, exc_info=True)
        response_text = "I'm sorry, something went wrong on my end. Please try again."

    return {
        "response": response_text,
        "session_id": session_key
    }


def _get_or_create_agent(session_key: str, phone_number: str) -> HermesAgent:
    """Return the cached agent for *session_key*, creating one if needed."""
    agent = _session_agents.get(session_key)
    if agent is None:
        agent = HermesAgent(session_id=session_key, caller_phone=phone_number)
        _session_agents[session_key] = agent
        logger.info("Created new HermesAgent for session '%s'.", session_key)
    elif phone_number and phone_number != agent.caller_phone:
        # Refresh patient context if caller changes within a reused UI session.
        agent.caller_phone = phone_number
        logger.debug("Updated caller_phone to '%s' for session '%s'.", phone_number, session_key)
    return agent


@app.get("/api/metrics")
async def get_metrics():
    """Retrieve call volumes, durations, and logs for the dashboard charts"""
    try:
        return db_manager.get_dashboard_metrics()
    except Exception as exc:
        logger.error("Error fetching dashboard metrics: %s", exc, exc_info=True)
        return {"total_calls": 0, "active_appointments": 0, "avg_duration_seconds": 0, "latest_calls": []}


@app.get("/health")
async def health_check():
    """Lightweight health endpoint for deployment probes."""
    return {"status": "ok", "service": "radiant-backend"}

@app.get("/api/appointments")
async def get_appointments():
    """Retrieve list of scheduled appointments for the React calendar component"""
    try:
        return db_manager.get_all_appointments()
    except Exception as exc:
        logger.error("Error fetching appointments: %s", exc, exc_info=True)
        return []

class ManualAppointmentRequest(BaseModel):
    patient_name: str
    phone_number: str
    date: str
    time: str

@app.post("/api/appointments")
async def manual_appointment(req: ManualAppointmentRequest):
    """Allows front-desk admin to manually add/schedule appointments on the dashboard"""
    try:
        patient_name, phone_number, date, time = validate_appointment_request(
            req.patient_name, req.phone_number, req.date, req.time
        )
    except ValidationError as exc:
        logger.warning("Manual appointment request rejected: %s", exc)
        return {"success": False, "message": str(exc)}

    try:
        result = db_manager.book_appointment(
            patient_name=patient_name,
            phone_number=phone_number,
            requested_date=date,
            requested_time=time
        )
        return result
    except Exception as exc:
        logger.error("Error booking manual appointment: %s", exc, exc_info=True)
        return {"success": False, "message": "An internal error occurred while booking the appointment."}

# --- Twilio Voice Media Stream Integration ---

@app.post("/voice/incoming")
async def voice_incoming(request: Request):
    """
    Twilio inbound call entrypoint. Responds with TwiML instructions
    directing Twilio to stream call audio over WebSockets to /voice/stream.
    """
    try:
        form_data = await request.form()
        caller = validate_twilio_form_data(form_data)
        logger.info("Twilio /voice/incoming: call received from: %s", caller)
    except Exception as exc:
        logger.error("Error parsing Twilio inbound call form data: %s", exc, exc_info=True)
        caller = "Unknown"

    try:
        ws_url = _build_websocket_url(request)
        twiml_response = _generate_twiml(ws_url, caller)
        logger.debug("Twilio /voice/incoming: generated TwiML directing to %s", ws_url)
        return Response(content=twiml_response, media_type="application/xml")
    except Exception as exc:
        logger.error("Error generating TwiML response: %s", exc, exc_info=True)
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response><Say>We are experiencing technical difficulties. Please call back later.</Say></Response>',
            media_type="application/xml",
        )


def _build_websocket_url(request: Request) -> str:
    """Construct the external WebSocket URL for Twilio Media Streams."""
    host = request.headers.get("host", "localhost:8000")
    protocol = "wss" if "ngrok" in host or "tunnel" in host else "ws"
    return f"{protocol}://{host}/voice/stream"


def _generate_twiml(ws_url: str, caller: str) -> str:
    """Generate the TwiML XML response directing Twilio to the media stream."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Matthew-Neural">Thank you for calling Radiant Smile Dental. Please hold while I connect you to our virtual receptionist Alex.</Say>
    <Connect>
        <Stream url="{ws_url}">
            <Parameter name="callerNumber" value="{caller}" />
        </Stream>
    </Connect>
</Response>
"""


@app.websocket("/voice/stream")
async def voice_stream(websocket: WebSocket):
    """
    WebSocket endpoint handling Twilio Media Streams.
    Pipes caller audio to Deepgram for STT, triggers Hermes agent LLM loop,
    converts replies to speech via Deepgram TTS, and sends audio back to Twilio.
    """
    await websocket.accept()
    logger.info("Twilio Media Stream WebSocket connected.")
    
    stream_sid = None
    caller_phone = "Unknown"
    agent = None
    
    audio_buffer = bytearray()
    
    try:
        while True:
            message = await websocket.receive_text()

            try:
                data = json.loads(message)
            except json.JSONDecodeError as exc:
                logger.warning("Received non-JSON message on media stream: %s", exc)
                continue

            try:
                event = validate_media_stream_event(data)
            except ValidationError as exc:
                logger.warning("Invalid media stream event: %s", exc)
                continue
            
            if event == "start":
                stream_sid, caller_phone, agent = await _handle_stream_start(websocket, data)
                
            elif event == "media":
                await _handle_media_chunk(websocket, data, stream_sid, agent, audio_buffer)
                
            elif event == "stop":
                logger.info("Media Stream stopped event received. StreamSid: %s", stream_sid)
                break
                
    except WebSocketDisconnect:
        logger.info("Twilio Media Stream WebSocket disconnected for StreamSid: %s", stream_sid)
    except Exception as exc:
        logger.error("Error in Twilio Media Stream loop: %s", exc, exc_info=True)
    finally:
        logger.info("Closing WebSocket connection for StreamSid: %s", stream_sid)
        await websocket.close()


async def _handle_stream_start(websocket: WebSocket, data: dict) -> tuple:
    """Process a Twilio 'start' event: extract identifiers and send the greeting."""
    stream_sid = data["start"]["streamSid"]
    params = data["start"].get("customParameters", {})
    caller_phone = params.get("callerNumber", "Unknown")
    logger.info("Media Stream started. StreamSid: %s, Caller: %s", stream_sid, caller_phone)

    agent = HermesAgent(session_id=stream_sid, caller_phone=caller_phone)

    greeting = "Hello, this is Alex from Radiant Smile Dental. How can I help you today?"
    try:
        await synthesize_and_send_audio(websocket, stream_sid, greeting)
    except Exception as exc:
        logger.error("Failed to send greeting for StreamSid %s: %s", stream_sid, exc, exc_info=True)

    return stream_sid, caller_phone, agent


async def _handle_media_chunk(
    websocket: WebSocket,
    data: dict,
    stream_sid: str,
    agent: HermesAgent | None,
    audio_buffer: bytearray,
) -> None:
    """Process a Twilio 'media' event: decode, buffer, transcribe, and respond."""
    payload_base64 = data.get("media", {}).get("payload")
    if not payload_base64:
        return

    try:
        audio_chunk = validate_audio_payload(payload_base64)
    except ValidationError as exc:
        logger.warning("Skipping media chunk for StreamSid %s: %s", stream_sid, exc)
        return

    audio_buffer.extend(audio_chunk)

    # Process in coarse batches to avoid one LLM call per packet.
    if len(audio_buffer) < 24000:
        return

    if not agent:
        return

    try:
        transcript = await transcribe_audio_groq(
            bytes(audio_buffer), filename=f"{stream_sid or 'stream'}_caller.wav"
        )
    except Exception as exc:
        logger.error("Transcription failed for StreamSid %s: %s", stream_sid, exc, exc_info=True)
        audio_buffer.clear()
        return

    audio_buffer.clear()

    transcript = transcript.strip()
    if not transcript:
        return

    logger.info("Caller transcript [%s]: %s", stream_sid, transcript)

    try:
        response_text = await agent.process_message(transcript)
        if response_text:
            await synthesize_and_send_audio(websocket, stream_sid, response_text)
    except Exception as exc:
        logger.error("Failed to process/send response for StreamSid %s: %s", stream_sid, exc, exc_info=True)


async def synthesize_and_send_audio(websocket: WebSocket, stream_sid: str, text: str):
    """
    Calls ElevenLabs TTS REST API to synthesize text response into mulaw 8000Hz audio,
    and forwards it to the active Twilio Media Stream connection.
    """
    if not validate_tts_config(Config.ELEVENLABS_API_KEY):
        return
        
    voice_id = Config.ELEVENLABS_VOICE_ID or "21m00Tcm4TlvDq8ikWAM"
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=ulaw_8000"
    
    headers = {
        "xi-api-key": Config.ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "text": text,
        "model_id": Config.ELEVENLABS_MODEL_ID or "eleven_turbo_v2_5"
    }
    
    logger.info("Synthesizing speech via ElevenLabs for StreamSid: %s. Text length: %d", stream_sid, len(text))
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload, timeout=15.0)
        except Exception as exc:
            logger.exception("ElevenLabs HTTP request failed for StreamSid %s: %s", stream_sid, exc)
            return

        if response.status_code != 200:
            logger.error(
                "ElevenLabs TTS error. Status: %d, Response: %s",
                response.status_code, response.text,
            )
            return

        try:
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
            logger.info("Audio response sent to Twilio via ElevenLabs for StreamSid: %s.", stream_sid)
        except Exception as exc:
            logger.exception("Failed to send TTS audio to Twilio WebSocket for StreamSid %s: %s", stream_sid, exc)

async def transcribe_audio_groq(audio_bytes: bytes, filename: str = "caller_audio.wav") -> str:
    """
    Sends compiled audio bytes to Groq Cloud's Whisper API endpoint to transcribe.
    """
    if not validate_stt_config(Config.GROQ_API_KEY):
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
    
    logger.info("Sending audio bytes to Groq Cloud for STT transcription. Filename: %s", filename)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, files=files, data=data, timeout=15.0)
        except Exception as exc:
            logger.exception("Groq HTTP request failed for file '%s': %s", filename, exc)
            return ""

        if response.status_code != 200:
            logger.error("Groq STT error. Status: %d, Response: %s", response.status_code, response.text)
            return ""

        try:
            result_json = response.json()
            transcript = result_json.get("text", "")
            logger.info("Groq transcription completed. Text length: %d", len(transcript))
            return transcript
        except Exception as exc:
            logger.exception("Failed to parse Groq transcription response for '%s': %s", filename, exc)
            return ""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.main:app", host=Config.HOST, port=Config.PORT, reload=True)
