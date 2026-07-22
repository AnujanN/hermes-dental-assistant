"""
Validation utilities for the server (FastAPI gateway) package.

All request-level validation logic is centralised here so that route
handlers and helper functions in main.py stay focused on orchestration.
"""

import re
import base64
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when a server-layer input fails validation."""
    pass


# ---------------------------------------------------------------------------
# Chat / appointment request validation
# ---------------------------------------------------------------------------

def validate_chat_request(session_id: str, text: str, phone_number: str) -> tuple:
    """
    Validate fields for the ``/api/chat`` endpoint.

    Returns ``(session_key, text, phone_number)`` with cleaned values.
    Raises ``ValidationError`` on invalid input.
    """
    if not text or not text.strip():
        raise ValidationError("Chat text is required and cannot be empty.")
    cleaned_text = text.strip()

    session_key = (session_id or "").strip() or "sandbox-session"

    cleaned_phone = (phone_number or "").strip() or "555-0100"

    logger.debug(
        "Validated chat request — session: %s, text length: %d, phone: %s",
        session_key, len(cleaned_text), cleaned_phone,
    )
    return session_key, cleaned_text, cleaned_phone


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def validate_appointment_request(
    patient_name: str, phone_number: str, date: str, time: str
) -> tuple:
    """
    Validate fields for manual appointment creation via ``/api/appointments``.

    Returns ``(patient_name, phone_number, date, time)`` with cleaned values.
    Raises ``ValidationError`` on invalid input.
    """
    errors = []

    if not patient_name or not patient_name.strip():
        errors.append("Patient name is required.")
    if not phone_number or not phone_number.strip():
        errors.append("Phone number is required.")
    if not date or not date.strip():
        errors.append("Date is required.")
    elif not _DATE_RE.match(date.strip()):
        errors.append(f"Date '{date}' must be in YYYY-MM-DD format.")
    else:
        try:
            datetime.strptime(date.strip(), "%Y-%m-%d")
        except ValueError:
            errors.append(f"Date '{date}' is not a valid calendar date.")
    if not time or not time.strip():
        errors.append("Time is required.")
    elif not _TIME_RE.match(time.strip()):
        errors.append(f"Time '{time}' must be in HH:MM 24-hour format.")

    if errors:
        raise ValidationError("; ".join(errors))

    cleaned = (
        patient_name.strip(),
        phone_number.strip(),
        date.strip(),
        time.strip(),
    )
    logger.debug("Validated appointment request: %s", cleaned)
    return cleaned


# ---------------------------------------------------------------------------
# Twilio / WebSocket validation
# ---------------------------------------------------------------------------

def validate_twilio_form_data(form_data: dict) -> str:
    """
    Extract and validate the caller phone number from Twilio webhook form data.

    Returns the ``From`` value (defaults to ``"Unknown"`` when absent).
    """
    caller = form_data.get("From", "Unknown")
    if not caller or not str(caller).strip():
        caller = "Unknown"
    logger.debug("Validated Twilio caller: %s", caller)
    return str(caller).strip()


def validate_media_stream_event(data: dict) -> str:
    """
    Validate that a parsed WebSocket JSON message contains a recognised
    Twilio Media Stream ``event`` field.

    Returns the event name.
    Raises ``ValidationError`` for missing/unknown events.
    """
    if not isinstance(data, dict):
        raise ValidationError("Media stream message must be a JSON object.")

    event = data.get("event")
    if not event:
        raise ValidationError("Media stream message is missing the 'event' field.")

    valid_events = {"connected", "start", "media", "stop"}
    if event not in valid_events:
        logger.warning("Received unrecognised media stream event: '%s'", event)

    return event


# ---------------------------------------------------------------------------
# TTS / STT configuration guards
# ---------------------------------------------------------------------------

def validate_tts_config(api_key: str) -> bool:
    """
    Check that the ElevenLabs API key is configured.

    Returns ``True`` when valid, ``False`` otherwise (caller should skip TTS).
    """
    if not api_key:
        logger.warning("Skipping TTS synthesis: ELEVENLABS_API_KEY not configured.")
        return False
    return True


def validate_stt_config(api_key: str) -> bool:
    """
    Check that the Groq API key is configured.

    Returns ``True`` when valid, ``False`` otherwise (caller should skip STT).
    """
    if not api_key:
        logger.warning("Skipping transcription: GROQ_API_KEY not configured.")
        return False
    return True


# ---------------------------------------------------------------------------
# Audio payload
# ---------------------------------------------------------------------------

def validate_audio_payload(payload_base64: str) -> bytes:
    """
    Validate and decode a base64-encoded audio payload from Twilio.

    Returns the decoded bytes.
    Raises ``ValidationError`` if the payload is empty or cannot be decoded.
    """
    if not payload_base64:
        raise ValidationError("Audio payload is empty.")
    try:
        return base64.b64decode(payload_base64)
    except Exception as exc:
        raise ValidationError(f"Failed to decode base64 audio payload: {exc}")
