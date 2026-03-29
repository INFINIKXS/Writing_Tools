"""
Raw reference text parser: regex + AI extraction with anti-hallucination input containment check.
"""
import re
import json
import difflib
from typing import List

from pydantic import BaseModel

from core.gemini import get_client, gemini_request_with_retry
from utils.text_utils import classify_source_type


class FormatRequest(BaseModel):
    references: List[str]
    style: str = "harvard"


def _value_in_input(value: str, ref_text: str, threshold: float = 0.6) -> bool:
    """
    Anti-hallucination check: verify that a value extracted by AI actually
    appears in the original input text.
    """
    if not value or not ref_text:
        return False
    val_lower = value.lower().strip()
    ref_lower = ref_text.lower()
    if val_lower in ref_lower:
        return True
    val_clean = re.sub(r'[.,;:\'\"()\[\]{}]', '', val_lower).strip()
    ref_clean = re.sub(r'[.,;:\'\"()\[\]{}]', '', ref_lower)
    if val_clean in ref_clean:
        return True
    ratio = difflib.SequenceMatcher(None, val_clean, ref_clean).ratio()
    if len(val_clean) <= 6:
        return val_clean in ref_clean
    return ratio >= threshold


async def parse_raw_reference(ref_text: str) -> dict:
    """
    Parse a raw reference string into structured metadata.
    Pipeline: Regex first → AI extraction with Input Containment Check.
    """
    metadata = {
        "authors": None, "title": None, "year": None,
        "source": None, "doi": None, "url": None,
        "volume": None, "issue": None, "pages": None,
        "publisher": None, "type": "Other",
    }
    field_sources = {}

    # ─── Step 1: Regex extraction ───
    doi_match = re.search(
        r'(?:doi[:\s]*|https?://(?:dx\.)?doi\.org/)(10\.\d{4,}/[a-zA-Z0-9.\-_/:()]+)',
        ref_text, re.IGNORECASE
    )
    if doi_match:
        doi = doi_match.group(1).rstrip('.,;)')
        metadata["doi"] = doi
        field_sources["doi"] = "text_parsing"

    year_match = re.search(r'\b((?:19|20)\d{2})\b', ref_text)
    if year_match:
        metadata["year"] = year_match.group(1)
        field_sources["year"] = "text_parsing"

    vol_match = re.search(r'(\d+)\s*\((\d+)\)', ref_text)
    if vol_match:
        metadata["volume"] = vol_match.group(1)
        metadata["issue"] = vol_match.group(2)
        field_sources["volume"] = "text_parsing"
        field_sources["issue"] = "text_parsing"

    pages_match = re.search(r'(?:pp?\.?\s*)?(\d+)\s*[-–]\s*(\d+)', ref_text)
    if pages_match:
        metadata["pages"] = f"{pages_match.group(1)}-{pages_match.group(2)}"
        field_sources["pages"] = "text_parsing"

    if not metadata["doi"]:
        url_match = re.search(r'(https?://\S+)', ref_text)
        if url_match:
            metadata["url"] = url_match.group(1).rstrip('.,;)')
            field_sources["url"] = "text_parsing"

    # ─── Step 2: AI extraction with Input Containment Check ───
    try:
        model_name = 'gemini-3-flash-preview'
        client = get_client(model=model_name)

        prompt = f"""You are a metadata extraction tool. Extract ONLY what you can see in the reference text below.
DO NOT invent, guess, or hallucinate any information. If a field is not clearly visible, return null.
Every value you return MUST come directly from the text — do not rephrase, infer, or add information.

Extract these fields from the reference:
- authors: List of author names exactly as they appear in the text (e.g. ["Clair, A.", "Hughes, A."])
- title: The main title of the work, exactly as written in the text
- year: The publication year as it appears in the text
- source: Journal name or publisher, exactly as written in the text
- source_abbreviated: If the source is a journal, provide its strictly abbreviated NLM catalog form (e.g. 'J Am Med Assoc', 'Int J Obes Suppl'). Omit periods. If not a journal, return null. THIS IS EXEMPT FROM THE "EXACTLY AS WRITTEN" RULE.
- doi: The DOI if present, exactly as written

REFERENCE TEXT:
{ref_text}

Respond in strict JSON only:
{{
    "authors": ["author1", "author2"] or null,
    "title": "title text" or null,
    "year": "2025" or null,
    "source": "journal or publisher name" or null,
    "source_abbreviated": "J Am Med Assoc" or null,
    "doi": "10.1234/example" or null
}}"""

        response = await gemini_request_with_retry(client, prompt, model=model_name)
        ai_text = response.text.strip()
        if ai_text.startswith('```json'):
            ai_text = ai_text[7:].strip()
        if ai_text.endswith('```'):
            ai_text = ai_text[:-3].strip()
        ai_data = json.loads(ai_text)
        print(f"[Formatter AI] Raw extraction: {ai_data}")

        # ─── Input Containment Check ───
        ai_title = ai_data.get("title")
        if ai_title and _value_in_input(ai_title, ref_text):
            if not metadata.get("title"):
                metadata["title"] = ai_title
                field_sources["title"] = "ai_verified"
        elif ai_title:
            print(f"[Formatter Anti-Hallucination] REJECTED title: '{ai_title}' — not found in input")

        ai_authors = ai_data.get("authors")
        if ai_authors and isinstance(ai_authors, list):
            verified_authors = []
            for author in ai_authors:
                if _value_in_input(author, ref_text):
                    verified_authors.append(author)
                else:
                    surname = author.split(',')[0].strip() if ',' in author else author.split()[0].strip()
                    if _value_in_input(surname, ref_text):
                        verified_authors.append(author)
                    else:
                        print(f"[Formatter Anti-Hallucination] REJECTED author: '{author}' — not found in input")
            if verified_authors:
                metadata["authors"] = verified_authors
                field_sources["authors"] = "ai_verified"

        ai_source = ai_data.get("source")
        if ai_source and _value_in_input(ai_source, ref_text):
            if not metadata.get("source"):
                metadata["source"] = ai_source
                field_sources["source"] = "ai_verified"
        elif ai_source:
            print(f"[Formatter Anti-Hallucination] REJECTED source: '{ai_source}' — not found in input")

        ai_source_abbr = ai_data.get("source_abbreviated")
        if ai_source_abbr and not metadata.get("source_abbreviated"):
            metadata["source_abbreviated"] = ai_source_abbr
            field_sources["source_abbreviated"] = "ai_inferred"

        ai_year = ai_data.get("year")
        if ai_year and str(ai_year) in ref_text:
            if not metadata.get("year"):
                metadata["year"] = str(ai_year)
                field_sources["year"] = "ai_verified"

        ai_doi = ai_data.get("doi")
        if ai_doi and ai_doi in ref_text and not metadata.get("doi"):
            metadata["doi"] = ai_doi
            field_sources["doi"] = "ai_verified"

    except Exception as e:
        print(f"[Formatter AI] FAILED: {type(e).__name__}: {e}")

    # ─── Step 3: Classify type ───
    if metadata["type"] == "Other":
        metadata["type"] = classify_source_type(metadata)

    if isinstance(metadata["authors"], str):
        raw = metadata["authors"]
        if '; ' in raw:
            metadata["authors"] = [a.strip() for a in raw.split(';') if a.strip()]
        elif ' and ' in raw or ' & ' in raw:
            raw = raw.replace(' & ', ' and ')
            metadata["authors"] = [a.strip() for a in raw.split(' and ') if a.strip()]
        else:
            metadata["authors"] = [raw.strip()]

    metadata["field_sources"] = field_sources
    return metadata
