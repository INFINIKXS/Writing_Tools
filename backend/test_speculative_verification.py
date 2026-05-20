import sys
import unittest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, '.')
sys.path.insert(0, 'backend')

from references.metadata import _extract_metadata_async, robust_doi_resolver
from utils.text_utils import polish_extracted_string

class TestSpeculativeVerification(unittest.IsolatedAsyncioTestCase):
    
    @patch("references.metadata.verify_doi_online")
    async def test_robust_doi_resolver_scenarios(self, mock_verify):
        # Scenario A: Perfect valid DOI
        # Should be verified raw directly
        mock_verify.side_effect = lambda doi: doi == "10.1000/xyz123"
        
        res = await robust_doi_resolver("10.1000/xyz123")
        self.assertEqual(res["status"], "verified_raw")
        self.assertEqual(res["doi"], "10.1000/xyz123")
        
        # Scenario B: Glued publisher domain
        # verify_doi_online("10.1111/dme.70058wileyonlinelibrary.com") -> False
        # verify_doi_online("10.1111/dme.70058") -> True
        mock_verify.side_effect = lambda doi: doi == "10.1111/dme.70058"
        
        res = await robust_doi_resolver("10.1111/dme.70058wileyonlinelibrary.com")
        self.assertEqual(res["status"], "verified_after_sieve")
        self.assertEqual(res["doi"], "10.1111/dme.70058")
        
        # Scenario C: Glued routing keyword URL
        # verify_doi_online("10.1111/dme.70058wileyonlinelibrary.com/journal/dme") -> False
        # verify_doi_online("10.1111/dme.70058") -> True
        res = await robust_doi_resolver("10.1111/dme.70058wileyonlinelibrary.com/journal/dme")
        self.assertEqual(res["status"], "verified_after_sieve")
        self.assertEqual(res["doi"], "10.1111/dme.70058")
        
        # Scenario D: Unverifiable junk DOI
        # Should return unverifiable status and None
        mock_verify.side_effect = lambda doi: False
        res = await robust_doi_resolver("10.9999/notrealjournalgarbage")
        self.assertEqual(res["status"], "unverifiable")
        self.assertIsNone(res["doi"])

    @patch("references.metadata._extract_metadata_local_sync")
    @patch("references.metadata.robust_doi_resolver")
    @patch("references.api_batch.fetch_crossref_batch", new_callable=AsyncMock)
    @patch("references.metadata._validate_api_result")
    async def test_extract_metadata_async_speculative_sieve(
        self,
        mock_validate_result,
        mock_fetch_crossref,
        mock_robust_resolver,
        mock_local_sync
    ):
        # Setup local sync to return a glued concatenated candidate DOI
        mock_local_sync.return_value = (
            {
                "title": None, "authors": [], "year": None, "doi": None,
                "journal": None, "volume": None, "issue": None, "pages": None,
                "publisher": None, "type": "Other", "verification_status": "not_found",
                "extraction_layers": [],
            },
            ["10.1111/dme.70058wileyonlinelibrary.com"]
        )
        
        # Setup robust resolver to return verified after sieve with the polished DOI
        mock_robust_resolver.return_value = {
            "status": "verified_after_sieve",
            "doi": "10.1111/dme.70058"
        }
        
        # Mock Crossref record using the correct polished DOI
        mock_record = MagicMock()
        mock_record.doi = "10.1111/dme.70058"
        mock_record.title = "Verified Diabetes Medicine Paper"
        mock_record.authors = ["Smith, J. A."]
        mock_record.year = 2021
        mock_record.journal = "Diabetic Medicine"
        mock_record.url = "https://doi.org/10.1111/dme.70058"
        mock_record.volume = "38"
        mock_record.issue = "5"
        mock_record.pages = "e70058"
        mock_record.publisher = "Wiley"
        mock_record.type = "Journal Article"
        mock_fetch_crossref.return_value = [mock_record]
        
        # Mock standard validation check to succeed
        mock_validate_result.return_value = True
        
        # Invoke the main extraction entrypoint
        result = await _extract_metadata_async("dummy_path.pdf")
        
        # Verify that the concatenated candidate was resolved and passed through to CrossRef correctly
        mock_robust_resolver.assert_called_once_with("10.1111/dme.70058wileyonlinelibrary.com")
        mock_fetch_crossref.assert_called_once_with(["10.1111/dme.70058"])
        
        # Verify that the resulting metadata is enriched with the correct fields
        self.assertEqual(result["doi"], "10.1111/dme.70058")
        self.assertEqual(result["title"], "Verified Diabetes Medicine Paper")
        self.assertEqual(result["verification_status"], "verified_crossref")
        self.assertIn("crossref_verify", result["extraction_layers"])
        print("\n[Speculative Sieve Integration] PASS: Concatenated DOI successfully polished and verified.")

if __name__ == "__main__":
    unittest.main()
