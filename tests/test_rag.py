import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from db_server import qdrant_manager

class TestRagAndQdrantOperations(unittest.TestCase):
    def setUp(self):
        # Configure Qdrant to run fully in-memory for testing
        os.environ["QDRANT_HOST"] = ":memory:"
        
        # Mock the SentenceTransformer encoder to avoid downloading BGE weights during testing
        self.mock_encoder = MagicMock()
        # Mock encoding to return a dummy vector of 384 dimensions
        self.mock_encoder.encode.return_value = [0.1] * 384
        
        # Patch the get_encoder function to return our mock
        self.encoder_patcher = patch("db_server.qdrant_manager.get_encoder", return_value=self.mock_encoder)
        self.encoder_patcher.start()

    def tearDown(self):
        self.encoder_patcher.stop()
        if "QDRANT_HOST" in os.environ:
            del os.environ["QDRANT_HOST"]

    def test_markdown_chunking(self):
        # Create a mock MEMORY.md content
        md_content = """# Radiant Smile Memory
        
## Section A
Operating hours are Mon-Fri 8 AM - 5 PM.

## Section B
 Routine cleaning costs $120.
 Composite filling costs $150 to $250.
"""
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w", encoding="utf-8") as f:
            f.write(md_content)
            temp_file_path = f.name

        try:
            # Test Markdown chunking function
            chunks = qdrant_manager.chunk_markdown_file(temp_file_path, chunk_size=200, overlap=20)
            self.assertEqual(len(chunks), 2)
            self.assertEqual(chunks[0]["metadata"]["section"], "Section A")
            self.assertIn("Operating hours", chunks[0]["content"])
            
            self.assertEqual(chunks[1]["metadata"]["section"], "Section B")
            self.assertIn("cleaning costs", chunks[1]["content"])
        finally:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

    def test_qdrant_indexing_and_search(self):
        # Test full ingestion pipeline with mock MD file
        md_content = """# Clinic Memory
## Section A
Our clinical office is located at 123 Radiant Lane.
"""
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w", encoding="utf-8") as f:
            f.write(md_content)
            temp_file_path = f.name
            
        try:
            # 1. Initialize and ingest into in-memory Qdrant
            qdrant_manager.ingest_knowledge_document(temp_file_path, collection_name="test_collection")
            
            # Verify encoder was called
            self.assertTrue(self.mock_encoder.encode.called)
            
            # 2. Search knowledge (returns mock embeddings vector matches)
            # The search will match because the search query returns the same mock vector [0.1]*384
            # Qdrant will evaluate similarity score as 1.0 (exact match)
            results = qdrant_manager.search_knowledge(
                query="where is the office?", 
                collection_name="test_collection",
                threshold=0.5
            )
            
            self.assertGreater(len(results), 0)
            self.assertEqual(results[0]["section"], "Section A")
            self.assertIn("123 Radiant Lane", results[0]["content"])
            self.assertEqual(results[0]["score"], 1.0) # Cosine similarity of identical mock vectors
            
        finally:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

    # --- Validation rejection tests ---

    def test_search_empty_query(self):
        """Validation should reject an empty search query and return an empty list."""
        results = qdrant_manager.search_knowledge(query="", collection_name="test_collection")
        self.assertEqual(results, [])

        results_whitespace = qdrant_manager.search_knowledge(query="   ", collection_name="test_collection")
        self.assertEqual(results_whitespace, [])

    def test_chunk_nonexistent_file(self):
        """Validation should raise FileNotFoundError for a missing file."""
        with self.assertRaises(FileNotFoundError):
            qdrant_manager.chunk_markdown_file("/nonexistent/path/file.md")

    def test_chunk_empty_file_path(self):
        """Validation should raise FileNotFoundError for an empty file path."""
        with self.assertRaises(FileNotFoundError):
            qdrant_manager.chunk_markdown_file("")

if __name__ == "__main__":
    unittest.main()
