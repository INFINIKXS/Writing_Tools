import logging
import json
import re
from pypdf import PdfReader
from typing import Optional, Dict, Any

from google.genai import types as genai_types
from core.gemini import get_client, _try_model_with_retries

logger = logging.getLogger(__name__)

async def extract_metadata_with_ai(pdf_path: str) -> Optional[Dict[str, Any]]:
    """
    Extracts the DOI, Title, and Authors from the first two pages of a PDF using Gemini 3.1 Flash.
    Returns a dictionary or None if it fails.
    """
    try:
        reader = PdfReader(pdf_path)
        pages_text = []
        # Get the first 2 pages
        for i, page in enumerate(reader.pages):
            if i >= 2:
                break
            text = page.extract_text()
            if text:
                pages_text.append(text)
        
        document_text = "\n\n".join(pages_text)
        if not document_text.strip():
            logger.warning("No text found in first pages of PDF for AI extraction.")
            return None

        prompt = f"""
You are an expert academic metadata extractor.
I am providing the text from the first pages of an academic paper or document.
Your task is to extract the following information and return ONLY a valid JSON object.

Information to extract:
1. "doi": The exact Digital Object Identifier (DOI) string. It should NOT include 'https://doi.org/', just the '10.xxxx/yyyy' part. If there is no DOI, return null.
2. "title": The title of the paper. This must be the actual paper title, NOT the journal name. If not found, return null.
3. "authors": A list of strings, representing the names of the authors. If not found, return an empty array [].

Document Text:
{document_text}

Return ONLY a valid JSON object matching the requested schema. No markdown, no markdown codeblocks, no conversational text.
"""
        
        client = get_client(model="gemini-3.1-flash-lite-preview")
        
        config = genai_types.GenerateContentConfig(
            response_mime_type="application/json",
        )
        
        async def dummy_progress(msg):
            logger.debug(msg)

        # Call with retries
        response, _ = await _try_model_with_retries(
            client=client,
            prompt=prompt,
            model="gemini-3.1-flash-lite-preview",
            config=config,
            max_retries=3,
            progress_callback=dummy_progress,
            rotate_keys=True
        )

        response_text = response.text.strip()
        # Clean up if the model includes markdown formatting despite instructions
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
            
        data = json.loads(response_text)
        
        # Validate data format
        result = {
            "doi": data.get("doi"),
            "title": data.get("title"),
            "authors": data.get("authors") if isinstance(data.get("authors"), list) else []
        }
        
        # Clean DOI if necessary
        if result["doi"]:
            # remove 'doi:' or 'http' prefix if the model missed instructions
            match = re.search(r'(10\.\d{4,9}/[-._;()/:A-Z0-9]+)', result["doi"], re.IGNORECASE)
            if match:
                result["doi"] = match.group(1).lower()
            else:
                result["doi"] = None # Not a valid DOI format

        logger.info(f"AI Extracted Metadata: {result}")
        return result

    except Exception as exc:
        logger.error(f"AI metadata extraction failed: {exc}", exc_info=True)
        return None
