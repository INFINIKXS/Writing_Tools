import asyncio
import unittest
import io
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import UploadFile

# Import the direct endpoint function without booting main app
from references.routes import extract_reference_batch

class TestBatchRouteDirect(unittest.IsolatedAsyncioTestCase):
    @patch("references.ai_extractor.extract_metadata_batch_with_ai", new_callable=AsyncMock)
    @patch("references.api_batch.fetch_crossref_batch", new_callable=AsyncMock)
    @patch("references.metadata.strict_ai_verify_against_pdf")
    @patch("pypdf.PdfReader")
    async def test_extract_reference_batch_success(
        self,
        mock_pdf_reader,
        mock_strict_verify,
        mock_fetch_crossref,
        mock_extract_batch_ai
    ):
        # Setup mocks
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "This is page text with DOI 10.1000/xyz123."
        mock_reader_inst = MagicMock()
        mock_reader_inst.pages = [mock_page, mock_page, mock_page, mock_page]  # 4 pages
        mock_pdf_reader.return_value = mock_reader_inst

        # Gemini Mock Output
        mock_extract_batch_ai.return_value = [
            {
                "id": "item1",
                "doi": "10.1000/xyz123",
                "title": "Mocked Title",
                "authors": ["Author One"],
                "year": "2026",
                "journal": "Mock Journal",
                "volume": "1",
                "issue": "2",
                "pages": "100-110",
                "publisher": "Mock Pub",
                "type": "Journal Article"
            }
        ]

        # Crossref Mock Output
        mock_record = MagicMock()
        mock_record.doi = "10.1000/xyz123"
        mock_record.title = "Mocked Title"
        mock_record.authors = ["Author One"]
        mock_record.year = "2026"
        mock_record.journal = "Mock Journal"
        mock_record.url = "https://doi.org/10.1000/xyz123"
        mock_record.volume = "1"
        mock_record.issue = "2"
        mock_record.pages = "100-110"
        mock_record.publisher = "Mock Pub"
        mock_record.type = "Journal Article"
        mock_fetch_crossref.return_value = [mock_record]

        # Mock standard API validation to pass
        with patch("references.metadata._validate_api_result", return_value=True):
            # Create a real FastAPI UploadFile in-memory
            dummy_file = UploadFile(
                filename="test1.pdf", 
                file=io.BytesIO(b"%PDF-1.4 dummy contents")
            )
            
            # Invoke the async controller function directly!
            response = await extract_reference_batch(
                files=[dummy_file],
                ids=["item1"],
                style="harvard"
            )
            
            # Verify the result structure
            self.assertEqual(len(response), 1)
            self.assertEqual(response[0]["id"], "item1")
            self.assertIn("result", response[0])
            # Response schema uses 'formatted' and 'formatted_html', not 'bibliography'
            self.assertIn("formatted", response[0]["result"])
            self.assertIn("formatted_html", response[0]["result"])
            self.assertEqual(response[0]["result"]["metadata"]["title"], "Mocked Title")
            
            # Assert text extraction stopped at page 3 (first 3 pages rule)
            self.assertTrue(mock_page.extract_text.call_count <= 3)
            print("\n[Lightweight Verification] SUCCESS: Batch extraction and 3-page text limit passed perfectly.")

if __name__ == "__main__":
    unittest.main()
