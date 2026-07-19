import os
import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Load env variables from local db_server/.env if exists
try:
    from dotenv import load_dotenv
    dotenv_path = Path(__file__).resolve().parent / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path)
except ImportError:
    pass

# Default database file path inside the db_server container
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dental_clinic.sqlite")

def get_db_path():
    return os.environ.get("SQLITE_DB_PATH", DEFAULT_DB_PATH)

def get_connection():
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
    if not os.path.exists(schema_path):
        logger.error(f"Schema initialization failed: schema file not found at {schema_path}")
        raise FileNotFoundError(f"Schema file not found at {schema_path}")
    
    with open(schema_path, "r") as f:
        schema_sql = f.read()
        
    db_path = get_db_path()
    logger.info(f"Initializing SQLite database at: {db_path}")
    conn = get_connection()
    try:
        conn.executescript(schema_sql)
        conn.commit()
        logger.info("Database schema successfully initialized.")
    except Exception as e:
        logger.exception(f"Error during SQLite database schema initialization: {e}")
        raise e
    finally:
        conn.close()

# --- Patient Database Operations ---

def get_patient(phone_number: str):
    logger.info(f"Querying patient profile for phone: {phone_number}")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM patients WHERE phone_number = ?", (phone_number,))
        row = cursor.fetchone()
        patient_found = row is not None
        logger.debug(f"Patient profile query finished. Found: {patient_found}")
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error retrieving patient for {phone_number}: {e}", exc_info=True)
        raise e
    finally:
        conn.close()

def upsert_patient(phone_number: str, name: str, anxieties: str = None, history: str = None):
    logger.info(f"Upserting patient profile for phone: {phone_number} (name: '{name}')")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT phone_number FROM patients WHERE phone_number = ?", (phone_number,))
        exists = cursor.fetchone()
        
        if exists:
            logger.debug(f"Patient {phone_number} exists. Performing UPDATE.")
            cursor.execute(
                """
                UPDATE patients 
                SET name = ?, anxieties = COALESCE(?, anxieties), history = COALESCE(?, history), last_called = CURRENT_TIMESTAMP
                WHERE phone_number = ?
                """,
                (name, anxieties, history, phone_number)
            )
        else:
            logger.debug(f"Patient {phone_number} is new. Performing INSERT.")
            cursor.execute(
                """
                INSERT INTO patients (phone_number, name, anxieties, history)
                VALUES (?, ?, ?, ?)
                """,
                (phone_number, name, anxieties, history)
            )
        conn.commit()
        logger.info(f"Successfully upserted patient {phone_number}.")
        return get_patient(phone_number)
    except Exception as e:
        logger.error(f"Error upserting patient {phone_number}: {e}", exc_info=True)
        raise e
    finally:
        conn.close()

# --- Appointment Calendar Operations ---

def check_slot_available(requested_date: str, requested_time: str) -> bool:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id FROM appointments 
            WHERE requested_date = ? AND requested_time = ? AND status = 'scheduled'
            """,
            (requested_date, requested_time)
        )
        row = cursor.fetchone()
        return row is None
    finally:
        conn.close()

def get_next_available_slots(requested_date: str, count: int = 3):
    working_hours = [f"{hour:02d}:00" for hour in range(8, 17)]
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT requested_time FROM appointments 
            WHERE requested_date = ? AND status = 'scheduled'
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
    finally:
        conn.close()

def book_appointment(patient_name: str, phone_number: str, requested_date: str, requested_time: str) -> dict:
    logger.info(f"Attempting to book appointment for '{patient_name}' ({phone_number}) on {requested_date} at {requested_time}")
    upsert_patient(phone_number, patient_name)
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO appointments (patient_name, phone_number, requested_date, requested_time)
            VALUES (?, ?, ?, ?)
            """,
            (patient_name, phone_number, requested_date, requested_time)
        )
        appointment_id = cursor.lastrowid
        conn.commit()
        logger.info(f"Appointment successfully booked. ID: {appointment_id}")
        
        return {
            "success": True,
            "appointment_id": appointment_id,
            "patient_name": patient_name,
            "date": requested_date,
            "time": requested_time,
            "message": "Appointment booked successfully."
        }
    except sqlite3.IntegrityError:
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
    except Exception as e:
        logger.error(f"Error booking appointment for {patient_name} on {requested_date} at {requested_time}: {e}", exc_info=True)
        raise e
    finally:
        conn.close()

def get_all_appointments():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM appointments ORDER BY requested_date ASC, requested_time ASC")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

# --- Call Log & Dashboard Metric Operations ---

def start_call_log(caller_phone: str) -> int:
    logger.info(f"Starting call log for phone: {caller_phone}")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO call_logs (caller_phone, start_time) VALUES (?, CURRENT_TIMESTAMP)",
            (caller_phone,)
        )
        log_id = cursor.lastrowid
        conn.commit()
        logger.debug(f"Call log initialized. Log ID: {log_id}")
        return log_id
    except Exception as e:
        logger.error(f"Failed to start call log for {caller_phone}: {e}", exc_info=True)
        raise e
    finally:
        conn.close()

def end_call_log(log_id: int, transcript: str, sentiment: str, duration_seconds: int):
    logger.info(f"Ending call log. ID: {log_id}, Sentiment: {sentiment}, Duration: {duration_seconds}s")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE call_logs 
            SET end_time = CURRENT_TIMESTAMP, transcript = ?, sentiment = ?, duration_seconds = ?
            WHERE id = ?
            """,
            (transcript, sentiment, duration_seconds, log_id)
        )
        conn.commit()
        logger.debug(f"Call log {log_id} successfully closed.")
    except Exception as e:
        logger.error(f"Failed to close call log {log_id}: {e}", exc_info=True)
        raise e
    finally:
        conn.close()

def get_dashboard_metrics():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM call_logs")
        total_calls = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM appointments WHERE status = 'scheduled'")
        active_appointments = cursor.fetchone()[0]
        
        cursor.execute("SELECT AVG(duration_seconds) FROM call_logs WHERE duration_seconds IS NOT NULL")
        avg_duration = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT * FROM call_logs ORDER BY start_time DESC LIMIT 5")
        latest_calls = [dict(row) for row in cursor.fetchall()]
        
        return {
            "total_calls": total_calls,
            "active_appointments": active_appointments,
            "avg_duration_seconds": round(avg_duration, 1),
            "latest_calls": latest_calls
        }
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
    print("Database schema successfully initialized in db_server.")
