import os
import logging
from pathlib import Path

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:  # pragma: no cover - handled at runtime in environments without PostgreSQL deps
    psycopg2 = None
    RealDictCursor = None

from db_server.validators import (
    ValidationError,
    validate_phone_number,
    validate_patient_name,
    validate_date_format,
    validate_time_format,
    validate_log_id,
    validate_duration,
)

logger = logging.getLogger(__name__)

# Load env variables from local db_server/.env if exists
try:
    from dotenv import load_dotenv
    dotenv_path = Path(__file__).resolve().parent / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path)
except ImportError:
    pass

def get_database_url():
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        raise RuntimeError("DATABASE_URL is required for PostgreSQL mode.")
    return db_url

def get_connection():
    if psycopg2 is None:
        raise RuntimeError("psycopg2 is required. Install dependencies from requirements.txt.")
    try:
        conn = psycopg2.connect(get_database_url(), cursor_factory=RealDictCursor)
        return conn
    except psycopg2.OperationalError as exc:
        logger.error("Failed to connect to PostgreSQL: %s", exc)
        raise RuntimeError(f"Database connection failed: {exc}") from exc

def init_db():
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
    if not os.path.exists(schema_path):
        logger.error("Schema initialization failed: schema file not found at %s", schema_path)
        raise FileNotFoundError(f"Schema file not found at {schema_path}")
    
    try:
        with open(schema_path, "r") as f:
            schema_sql = f.read()
    except OSError as exc:
        logger.error("Failed to read schema file at %s: %s", schema_path, exc)
        raise
        
    logger.info("Initializing PostgreSQL database schema...")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(schema_sql)
        conn.commit()
        logger.info("Database schema successfully initialized.")
    except Exception as exc:
        logger.exception("Error during PostgreSQL database schema initialization: %s", exc)
        raise
    finally:
        conn.close()

# --- Patient Database Operations ---

def get_patient(phone_number: str):
    """Retrieve a patient record by phone number."""
    try:
        phone_number = validate_phone_number(phone_number)
    except ValidationError as exc:
        logger.error("Invalid input for get_patient: %s", exc)
        raise

    logger.info("Querying patient profile for phone: %s", phone_number)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM patients WHERE phone_number = %s", (phone_number,))
        row = cursor.fetchone()
        patient_found = row is not None
        logger.debug("Patient profile query finished. Found: %s", patient_found)
        return row if row else None
    except Exception as exc:
        logger.error("Error retrieving patient for %s: %s", phone_number, exc, exc_info=True)
        raise
    finally:
        conn.close()

def upsert_patient(phone_number: str, name: str, anxieties: str = None, history: str = None):
    """Create or update a patient record."""
    try:
        phone_number = validate_phone_number(phone_number)
        name = validate_patient_name(name)
    except ValidationError as exc:
        logger.error("Invalid input for upsert_patient: %s", exc)
        raise

    logger.info("Upserting patient profile for phone: %s (name: '%s')", phone_number, name)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO patients (phone_number, name, anxieties, history)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (phone_number)
            DO UPDATE SET
                name = EXCLUDED.name,
                anxieties = COALESCE(EXCLUDED.anxieties, patients.anxieties),
                history = COALESCE(EXCLUDED.history, patients.history),
                last_called = CURRENT_TIMESTAMP
            """,
            (phone_number, name, anxieties, history),
        )
        conn.commit()
        logger.info("Successfully upserted patient %s.", phone_number)
        return get_patient(phone_number)
    except ValidationError:
        raise
    except Exception as exc:
        logger.error("Error upserting patient %s: %s", phone_number, exc, exc_info=True)
        raise
    finally:
        conn.close()

# --- Appointment Calendar Operations ---

def check_slot_available(requested_date: str, requested_time: str) -> bool:
    """Check whether a specific date/time slot is still open."""
    try:
        requested_date = validate_date_format(requested_date)
        requested_time = validate_time_format(requested_time)
    except ValidationError as exc:
        logger.error("Invalid input for check_slot_available: %s", exc)
        raise

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id FROM appointments 
            WHERE requested_date = %s AND requested_time = %s AND status = 'scheduled'
            """,
            (requested_date, requested_time)
        )
        row = cursor.fetchone()
        return row is None
    except Exception as exc:
        logger.error(
            "Error checking slot availability for %s at %s: %s",
            requested_date, requested_time, exc, exc_info=True,
        )
        raise
    finally:
        conn.close()

def get_next_available_slots(requested_date: str, count: int = 3):
    """Return up to *count* available time slots for a given date."""
    try:
        requested_date = validate_date_format(requested_date)
    except ValidationError as exc:
        logger.error("Invalid input for get_next_available_slots: %s", exc)
        raise

    working_hours = [f"{hour:02d}:00" for hour in range(8, 17)]
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT requested_time FROM appointments 
            WHERE requested_date = %s AND status = 'scheduled'
            """,
            (requested_date,)
        )
        booked = {row['requested_time'] for row in cursor.fetchall()}
        
        available = []
        for slot in working_hours:
            if slot not in booked:
                available.append(slot)
                if len(available) >= count:
                    break
        return available
    except Exception as exc:
        logger.error(
            "Error fetching available slots for %s: %s",
            requested_date, exc, exc_info=True,
        )
        raise
    finally:
        conn.close()

def book_appointment(patient_name: str, phone_number: str, requested_date: str, requested_time: str) -> dict:
    """Validate inputs, upsert the patient, and attempt to book a slot."""
    try:
        patient_name = validate_patient_name(patient_name)
        phone_number = validate_phone_number(phone_number)
        requested_date = validate_date_format(requested_date)
        requested_time = validate_time_format(requested_time)
    except ValidationError as exc:
        logger.error("Invalid input for book_appointment: %s", exc)
        raise

    logger.info(
        "Attempting to book appointment for '%s' (%s) on %s at %s",
        patient_name, phone_number, requested_date, requested_time,
    )
    upsert_patient(phone_number, patient_name)
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO appointments (patient_name, phone_number, requested_date, requested_time)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (patient_name, phone_number, requested_date, requested_time)
        )
        appointment_id = cursor.fetchone()["id"]
        conn.commit()
        logger.info("Appointment successfully booked. ID: %d", appointment_id)
        
        return {
            "success": True,
            "appointment_id": appointment_id,
            "patient_name": patient_name,
            "date": requested_date,
            "time": requested_time,
            "message": "Appointment booked successfully."
        }
    except psycopg2.IntegrityError:
        conn.rollback()
        alternative_slots = get_next_available_slots(requested_date)
        logger.warning(
            "Booking rejected by unique-slot guard for %s %s. Alternatives: %s",
            requested_date,
            requested_time,
            alternative_slots,
        )
        return {
            "success": False,
            "message": f"Slot {requested_date} at {requested_time} is fully booked.",
            "alternatives": alternative_slots,
        }
    except Exception as exc:
        logger.error(
            "Error booking appointment for %s on %s at %s: %s",
            patient_name, requested_date, requested_time, exc, exc_info=True,
        )
        raise
    finally:
        conn.close()

def get_all_appointments():
    """Retrieve every appointment ordered by date and time."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM appointments ORDER BY requested_date ASC, requested_time ASC")
        return [dict(row) for row in cursor.fetchall()]
    except Exception as exc:
        logger.error("Error fetching all appointments: %s", exc, exc_info=True)
        raise
    finally:
        conn.close()

# --- Call Log & Dashboard Metric Operations ---

def start_call_log(caller_phone: str) -> int:
    """Create a new call log entry and return its ID."""
    try:
        caller_phone = validate_phone_number(caller_phone)
    except ValidationError as exc:
        logger.error("Invalid input for start_call_log: %s", exc)
        raise

    logger.info("Starting call log for phone: %s", caller_phone)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO call_logs (caller_phone, start_time) VALUES (%s, CURRENT_TIMESTAMP) RETURNING id",
            (caller_phone,)
        )
        log_id = cursor.fetchone()["id"]
        conn.commit()
        logger.debug("Call log initialized. Log ID: %d", log_id)
        return log_id
    except Exception as exc:
        logger.error("Failed to start call log for %s: %s", caller_phone, exc, exc_info=True)
        raise
    finally:
        conn.close()

def end_call_log(log_id: int, transcript: str, sentiment: str, duration_seconds: int):
    """Close an open call log with its final data."""
    try:
        log_id = validate_log_id(log_id)
        duration_seconds = validate_duration(duration_seconds)
    except ValidationError as exc:
        logger.error("Invalid input for end_call_log: %s", exc)
        raise

    logger.info("Ending call log. ID: %d, Sentiment: %s, Duration: %ds", log_id, sentiment, duration_seconds)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE call_logs 
            SET end_time = CURRENT_TIMESTAMP, transcript = %s, sentiment = %s, duration_seconds = %s
            WHERE id = %s
            """,
            (transcript, sentiment, duration_seconds, log_id)
        )
        conn.commit()
        logger.debug("Call log %d successfully closed.", log_id)
    except Exception as exc:
        logger.error("Failed to close call log %d: %s", log_id, exc, exc_info=True)
        raise
    finally:
        conn.close()

def get_dashboard_metrics():
    """Aggregate call and appointment statistics for the dashboard."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) AS total_calls FROM call_logs")
        total_calls = cursor.fetchone()["total_calls"]
        
        cursor.execute("SELECT COUNT(*) AS active_appointments FROM appointments WHERE status = 'scheduled'")
        active_appointments = cursor.fetchone()["active_appointments"]
        
        cursor.execute("SELECT AVG(duration_seconds) AS avg_duration FROM call_logs WHERE duration_seconds IS NOT NULL")
        avg_duration = cursor.fetchone()["avg_duration"] or 0
        
        cursor.execute("SELECT * FROM call_logs ORDER BY start_time DESC LIMIT 5")
        latest_calls = [dict(row) for row in cursor.fetchall()]
        
        return {
            "total_calls": total_calls,
            "active_appointments": active_appointments,
            "avg_duration_seconds": round(avg_duration, 1),
            "latest_calls": latest_calls
        }
    except Exception as exc:
        logger.error("Error fetching dashboard metrics: %s", exc, exc_info=True)
        return {
            "total_calls": 0,
            "active_appointments": 0,
            "avg_duration_seconds": 0,
            "latest_calls": [],
        }
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
    print("Database schema successfully initialized in db_server.")
