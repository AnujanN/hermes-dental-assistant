import unittest
from unittest.mock import patch, MagicMock
from server.tools import clinic_info_retriever, calendar_appointment_booker

class TestCustomTools(unittest.TestCase):
    
    @patch("db_server.qdrant_manager.search_knowledge")
    def test_clinic_info_retriever_success(self, mock_search):
        # Mock search results returned by Qdrant
        mock_search.return_value = [
            {"content": "Operating Hours: Mon-Fri 8 AM - 5 PM.", "section": "Hours", "score": 0.85},
            {"content": "Routine dental cleaning costs $120.", "section": "Pricing", "score": 0.78}
        ]
        
        result = clinic_info_retriever("what are your hours and pricing?")
        
        # Verify search was called
        mock_search.assert_called_once_with("what are your hours and pricing?", top_k=3, threshold=0.68)
        
        # Verify formatting output
        self.assertIn("[Fact 1 (Section: Hours)]", result)
        self.assertIn("Mon-Fri 8 AM - 5 PM", result)
        self.assertIn("[Fact 2 (Section: Pricing)]", result)
        self.assertIn("$120", result)

    @patch("db_server.qdrant_manager.search_knowledge")
    def test_clinic_info_retriever_no_hits(self, mock_search):
        # Mock search returning no hits
        mock_search.return_value = []
        
        result = clinic_info_retriever("tell me a joke")
        self.assertIn("No specific clinic documentation was found", result)

    @patch("db_server.db_manager.book_appointment")
    def test_calendar_appointment_booker_success(self, mock_book):
        # Mock booking success output
        mock_book.return_value = {
            "success": True,
            "appointment_id": 42,
            "patient_name": "John Doe",
            "date": "2026-08-01",
            "time": "10:00",
            "message": "Success"
        }
        
        result = calendar_appointment_booker("John Doe", "555-0100", "2026-08-01", "10:00")
        
        # Check database execution arguments (phone normalized to digits)
        mock_book.assert_called_once_with("John Doe", "5550100", "2026-08-01", "10:00")
        
        # Check confirmation message matches
        self.assertIn("CONFIRMED", result)
        self.assertIn("Appointment ID is 42", result)
        self.assertIn("2026-08-01 at 10:00", result)

    @patch("db_server.db_manager.book_appointment")
    def test_calendar_appointment_booker_failure(self, mock_book):
        # Mock booking slot taken, returning alternatives
        mock_book.return_value = {
            "success": False,
            "message": "Slot full",
            "alternatives": ["11:00", "12:00", "13:00"]
        }
        
        result = calendar_appointment_booker("John Doe", "555-0100", "2026-08-01", "10:00")
        
        self.assertIn("FAILED", result)
        self.assertIn("11:00, 12:00, 13:00", result)

if __name__ == "__main__":
    unittest.main()
