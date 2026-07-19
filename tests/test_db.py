import os
import tempfile
import unittest
from db_server import db_manager

class TestDatabaseOperations(unittest.TestCase):
    def setUp(self):
        # Create a temp file path for the SQLite test database
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".sqlite")
        os.close(self.db_fd)
        
        # Override the env variable so db_manager points to the test DB
        os.environ["SQLITE_DB_PATH"] = self.db_path
        db_manager.init_db()

    def tearDown(self):
        # Clean up the test database file
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        if "SQLITE_DB_PATH" in os.environ:
            del os.environ["SQLITE_DB_PATH"]

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

if __name__ == "__main__":
    unittest.main()
