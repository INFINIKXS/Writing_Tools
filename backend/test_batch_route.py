import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from main import app

class TestBatchRoute(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("references.routes.extract_metadata_batch_with_ai", new_callable=AsyncMock)
    @patch("references.routes.fetch_crossref_batch", new_callable=AsyncMock)
    @patch("references.routes.strict_ai_verify_against_pdf")
    @patch("pypdf.PdfReader")
    def test_extract_reference_batch_success(
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

        with patch("references.routes._validate_api_result", return_value=True):
            files = [
                ("files", ("test1.pdf", b"%PDF-1.4 dummy contents", "application/pdf"))
            ]
            data = {
                "ids": ["item1"],
                "style": "harvard"
            }

            response = self.client.post("/api/extract-reference-batch", files=files, data=data)
            
            self.assertEqual(response.status_code, 200)
            json_data = response.json()
            self.assertEqual(len(json_data), 1)
            self.assertEqual(json_data[0]["id"], "item1")
            self.assertIn("result", json_data[0])
            self.assertIn("bibliography", json_data[0]["result"])
            self.assertTrue(mock_page.extract_text.call_count <= 3)

if __name__ == "__main__":
    unittest.main()
