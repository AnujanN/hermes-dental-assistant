import os
import sys
from pathlib import Path

# Add project root directory to path to ensure we can import db module
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from db_server import db_manager, qdrant_manager

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
        # We query Qdrant collection for semantic matching
        hits = qdrant_manager.search_knowledge(query, top_k=3, threshold=0.68)
        
        if not hits:
            return "No specific clinic documentation was found for this query. Inform the caller that you cannot locate that detail but can check with the doctor's manager if needed."
            
        formatted_results = []
        for idx, hit in enumerate(hits):
            formatted_results.append(f"[Fact {idx+1} (Section: {hit['section']})]:\n{hit['content']}")
            
        return "\n\n".join(formatted_results)
    except Exception as e:
        return f"Error retrieving clinic details: {str(e)}"

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
    # Normalize inputs
    patient_name = patient_name.strip()
    phone_number = phone_number.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    requested_date = requested_date.strip()
    requested_time = requested_time.strip()
    
    try:
        result = db_manager.book_appointment(patient_name, phone_number, requested_date, requested_time)
        
        if result["success"]:
            return (
                f"Booking CONFIRMED for {result['patient_name']} "
                f"on {result['date']} at {result['time']}. "
                f"Appointment ID is {result['appointment_id']}. Please read the date and time back to confirm."
            )
        else:
            alts = result.get("alternatives", [])
            alts_str = ", ".join(alts) if alts else "no available slots left on this date"
            return (
                f"Booking FAILED. Slot {requested_date} at {requested_time} is already taken. "
                f"The next available slots on that date are: {alts_str}. Please offer these slots to the caller."
            )
    except Exception as e:
        return f"Error booking appointment: {str(e)}"

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
