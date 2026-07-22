import os
import unittest
from db_server import db_manager
from db_server.validators import ValidationError

class TestDatabaseOperations(unittest.TestCase):
    def setUp(self):
        self.database_url = os.environ.get("DATABASE_URL", "").strip()
        if not self.database_url:
            self.skipTest("DATABASE_URL is not configured; skipping PostgreSQL integration tests.")

        db_manager.init_db()

    def tearDown(self):
        pass

    def test_upsert_and_get_patient(self):
        # Test patient creation
        phone = "1234567890"
        name = "Alice Testing"
        anxieties = "Scared of drilling sounds"
        history = "Clean record, last visit 2025"
        
        patient = db_manager.upsert_patient(phone, name, anxieties, history)
        self.assertIsNotNone(patient)
        self.assertEqual(patient["phone_number"], phone)
        self.assertEqual(patient["name"], name)
        self.assertEqual(patient["anxieties"], anxieties)
        
        # Test retrieving patient
        retrieved = db_manager.get_patient(phone)
        self.assertEqual(retrieved["name"], name)

    def test_check_slot_available_and_booking(self):
        # Test slot is initially open
        date = "2026-08-10"
        time = "09:00"
        self.assertTrue(db_manager.check_slot_available(date, time))
        
        # Book slot
        res = db_manager.book_appointment("Bob Test", "9876543210", date, time)
        self.assertTrue(res["success"])
        self.assertEqual(res["patient_name"], "Bob Test")
        
        # Slot should now be occupied
        self.assertFalse(db_manager.check_slot_available(date, time))
        
        # Booking again in the same slot should fail
        fail_res = db_manager.book_appointment("Charlie Test", "5551112222", date, time)
        self.assertFalse(fail_res["success"])
        self.assertIn("alternatives", fail_res)
        
    def test_call_logs_and_metrics(self):
        phone = "555-4444"
        
        # Start a call log
        log_id = db_manager.start_call_log(phone)
        self.assertIsNotNone(log_id)
        
        # End the call log
        db_manager.end_call_log(
            log_id=log_id,
            transcript="Caller: Can I book a cleaning?\nAlex: Yes, routine cleaning is $120.",
            sentiment="Positive",
            duration_seconds=45
        )
        
        # Query metrics
        metrics = db_manager.get_dashboard_metrics()
        self.assertEqual(metrics["total_calls"], 1)
        self.assertEqual(metrics["avg_duration_seconds"], 45.0)
        self.assertEqual(len(metrics["latest_calls"]), 1)
        self.assertEqual(metrics["latest_calls"][0]["caller_phone"], phone)

    # --- Validation rejection tests ---

    def test_get_patient_invalid_phone(self):
        """Validation should reject an empty phone number."""
        with self.assertRaises(ValidationError):
            db_manager.get_patient("")

    def test_upsert_patient_invalid_name(self):
        """Validation should reject an empty patient name."""
        with self.assertRaises(ValidationError):
            db_manager.upsert_patient("1234567890", "")

    def test_check_slot_invalid_date(self):
        """Validation should reject a malformed date."""
        with self.assertRaises(ValidationError):
            db_manager.check_slot_available("08-10-2026", "09:00")

    def test_check_slot_invalid_time(self):
        """Validation should reject a malformed time."""
        with self.assertRaises(ValidationError):
            db_manager.check_slot_available("2026-08-10", "9am")

    def test_end_call_log_invalid_log_id(self):
        """Validation should reject a non-positive log ID."""
        with self.assertRaises(ValidationError):
            db_manager.end_call_log(log_id=-1, transcript="", sentiment="", duration_seconds=10)

    def test_end_call_log_invalid_duration(self):
        """Validation should reject a negative duration."""
        with self.assertRaises(ValidationError):
            db_manager.end_call_log(log_id=1, transcript="", sentiment="", duration_seconds=-5)

if __name__ == "__main__":
    unittest.main()
