import os
import re
import sys
import logging
from pathlib import Path
from datetime import datetime

# Add project root directory to path to ensure we can import db module
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from db_server import db_manager, qdrant_manager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Validation helpers (local to tools layer)
# ---------------------------------------------------------------------------

class ToolValidationError(Exception):
    """Raised when a tool receives invalid arguments from the LLM."""
    pass


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def _validate_query(query: str) -> str:
    """Validate and return a cleaned search query string."""
    if not query or not str(query).strip():
        raise ToolValidationError("Search query is required and cannot be empty.")
    return str(query).strip()


def _validate_booking_args(
    patient_name: str, phone_number: str, requested_date: str, requested_time: str
) -> tuple:
    """
    Validate and normalise all booking arguments.

    Returns ``(patient_name, phone_number, requested_date, requested_time)``.
    Raises ``ToolValidationError`` on invalid input.
    """
    errors = []

    # --- patient name ---
    if not patient_name or not patient_name.strip():
        errors.append("Patient name is required.")
    else:
        patient_name = patient_name.strip()

    # --- phone number (normalise) ---
    if not phone_number or not phone_number.strip():
        errors.append("Phone number is required.")
    else:
        phone_number = phone_number.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")

    # --- date ---
    if not requested_date or not requested_date.strip():
        errors.append("Requested date is required.")
    else:
        requested_date = requested_date.strip()
        if not _DATE_RE.match(requested_date):
            errors.append(f"Date '{requested_date}' must be in YYYY-MM-DD format.")
        else:
            try:
                datetime.strptime(requested_date, "%Y-%m-%d")
            except ValueError:
                errors.append(f"Date '{requested_date}' is not a valid calendar date.")

    # --- time ---
    if not requested_time or not requested_time.strip():
        errors.append("Requested time is required.")
    else:
        requested_time = requested_time.strip()
        if not _TIME_RE.match(requested_time):
            errors.append(f"Time '{requested_time}' must be in HH:MM 24-hour format.")

    if errors:
        raise ToolValidationError("; ".join(errors))

    return patient_name, phone_number, requested_date, requested_time


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def clinic_info_retriever(query: str) -> str:
    """
    Search the clinic's indexed knowledge base (operating hours, parking, pricing, insurances)
    to answer questions.
    
    Args:
        query: The semantic search query (e.g., 'what are your hours?', 'do you take Cigna?')
        
    Returns:
        A string containing relevant facts or a fallback notice.
    """
    try:
        query = _validate_query(query)
    except ToolValidationError as exc:
        logger.warning("clinic_info_retriever called with invalid query: %s", exc)
        return f"Error: {exc}"

    try:
        # We query Qdrant collection for semantic matching
        hits = qdrant_manager.search_knowledge(query, top_k=3, threshold=0.68)
        
        if not hits:
            logger.info("clinic_info_retriever: no matching documents for query '%s'.", query)
            return "No specific clinic documentation was found for this query. Inform the caller that you cannot locate that detail but can check with the doctor's manager if needed."
            
        formatted_results = []
        for idx, hit in enumerate(hits):
            formatted_results.append(f"[Fact {idx+1} (Section: {hit['section']})]:\n{hit['content']}")

        logger.info("clinic_info_retriever: returning %d facts for query '%s'.", len(formatted_results), query)
        return "\n\n".join(formatted_results)
    except Exception as exc:
        logger.error("clinic_info_retriever failed for query '%s': %s", query, exc, exc_info=True)
        return f"Error retrieving clinic details: {str(exc)}"

def calendar_appointment_booker(patient_name: str, phone_number: str, requested_date: str, requested_time: str) -> str:
    """
    Check slot availability and book a dental appointment.
    
    Args:
        patient_name: The first and last name of the patient.
        phone_number: Contact phone number of the patient.
        requested_date: Target date of appointment in YYYY-MM-DD format (e.g., '2026-07-20').
        requested_time: Target time of appointment in HH:MM format (24-hour clock, e.g., '09:00', '14:30').
        
    Returns:
        A confirmation message if booked, or a rejection message listing the next 3 available slots.
    """
    try:
        patient_name, phone_number, requested_date, requested_time = _validate_booking_args(
            patient_name, phone_number, requested_date, requested_time
        )
    except ToolValidationError as exc:
        logger.warning("calendar_appointment_booker called with invalid args: %s", exc)
        return f"Error: {exc}"

    try:
        result = db_manager.book_appointment(patient_name, phone_number, requested_date, requested_time)
        
        if result["success"]:
            logger.info(
                "Appointment booked — ID %s for %s on %s at %s.",
                result["appointment_id"], result["patient_name"], result["date"], result["time"],
            )
            return (
                f"Booking CONFIRMED for {result['patient_name']} "
                f"on {result['date']} at {result['time']}. "
                f"Appointment ID is {result['appointment_id']}. Please read the date and time back to confirm."
            )
        else:
            alts = result.get("alternatives", [])
            alts_str = ", ".join(alts) if alts else "no available slots left on this date"
            logger.info(
                "Booking rejected for %s on %s at %s. Alternatives: %s",
                patient_name, requested_date, requested_time, alts_str,
            )
            return (
                f"Booking FAILED. Slot {requested_date} at {requested_time} is already taken. "
                f"The next available slots on that date are: {alts_str}. Please offer these slots to the caller."
            )
    except Exception as exc:
        logger.error(
            "calendar_appointment_booker failed for %s on %s at %s: %s",
            patient_name, requested_date, requested_time, exc, exc_info=True,
        )
        return f"Error booking appointment: {str(exc)}"

# Define the tool definitions for the OpenAI / OpenRouter function calling API
AVAILABLE_TOOLS = {
    "clinic_info_retriever": clinic_info_retriever,
    "calendar_appointment_booker": calendar_appointment_booker
}

TOOLS_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "clinic_info_retriever",
            "description": "Searches the clinic knowledge database to answer logistical questions about operating hours, pricing, billing, address, parking, and insurance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The natural language query or keywords to search for."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_appointment_booker",
            "description": "Checks availability and books a dental appointment in the clinic calendar database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_name": {
                        "type": "string",
                        "description": "The first and last name of the patient."
                    },
                    "phone_number": {
                        "type": "string",
                        "description": "The callback telephone number of the patient."
                    },
                    "requested_date": {
                        "type": "string",
                        "description": "Target date of appointment in YYYY-MM-DD format (e.g., '2026-07-20')."
                    },
                    "requested_time": {
                        "type": "string",
                        "description": "Target time of appointment in HH:MM 24-hour format (e.g., '09:00', '14:00')."
                    }
                },
                "required": ["patient_name", "phone_number", "requested_date", "requested_time"]
            }
        }
    }
]
