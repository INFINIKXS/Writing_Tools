import os
import io
import json
import re
import asyncio
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
from google import genai
from google.genai import types
from PyPDF2 import PdfReader
from docx import Document
import struct
import olefile
from dotenv import load_dotenv

from harvard_guide import HARVARD_GUIDE
from apa_guide import APA_GUIDE

# Load env variables
load_dotenv()

app = FastAPI(title="Writing Tools API")

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.environ.get("GOOGLE_API_KEY")

def get_client():
    if not API_KEY:
        raise HTTPException(status_code=500, detail="Google API Key not configured at GOOGLE_API_KEY in .env")
    return genai.Client(api_key=API_KEY)

def extract_pdf_text(file_bytes: bytes) -> str:
    text = ""
    with io.BytesIO(file_bytes) as f:
        reader = PdfReader(f)
        for page in reader.pages:
            text += page.extract_text() + "\n"
    return text

def extract_docx_text(file_bytes: bytes) -> str:
    with io.BytesIO(file_bytes) as f:
        doc = Document(f)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
    return text

def extract_doc_text(file_bytes: bytes) -> str:
    """Extract text from legacy .doc (Word 97-2003) files using olefile (pure Python)."""
    try:
        f = io.BytesIO(file_bytes)
        ole = olefile.OleFileIO(f)
        
        # The main text stream in .doc files is "WordDocument"
        # But the actual text content is in the "1Table" or "0Table" stream  
        # We'll read the WordDocument stream to get the raw text
        
        if ole.exists('WordDocument'):
            word_stream = ole.openstream('WordDocument').read()
        else:
            raise HTTPException(status_code=400, detail="This file does not appear to be a valid Word .doc file.")
        
        # Read the FIB (File Information Block) to locate text
        # Bytes 24-27 contain flags, bytes 0x01A2 onwards contain text positions
        # For simplicity, try to extract via the compound document text
        
        text_pieces = []
        
        # Method 1: Try to read from the data stream directly
        # The text in a .doc is stored as either ASCII or Unicode
        # We look at ccpText field in FIB at offset 0x004C (76)
        if len(word_stream) > 80:
            ccp_text = struct.unpack_from('<I', word_stream, 0x004C)[0]
            
            # Check if text is Unicode (bit 0 of flags at offset 0x000A)
            flags = struct.unpack_from('<H', word_stream, 0x000A)[0]
            is_complex = not (flags & 0x0004)  # fComplex flag
            
            if not is_complex and ccp_text > 0:
                # Simple file: text starts at offset 0x0200 (512)
                start = 0x0200
                if flags & 0x0100:  # Unicode
                    raw = word_stream[start:start + ccp_text * 2]
                    text_pieces.append(raw.decode('utf-16-le', errors='ignore'))
                else:
                    raw = word_stream[start:start + ccp_text]
                    text_pieces.append(raw.decode('cp1252', errors='ignore'))
        
        # Method 2: If Method 1 got nothing, try brute-force decoding 
        if not text_pieces or not ''.join(text_pieces).strip():
            # Try all text streams
            for stream_name in ['WordDocument']:
                data = ole.openstream(stream_name).read()
                # Skip the FIB header (first 512 bytes) and try to decode
                raw_text = data[512:]
                # Try UTF-16 first, then cp1252
                try:
                    decoded = raw_text.decode('utf-16-le', errors='ignore')
                    # Filter to printable characters
                    cleaned = ''.join(c if c.isprintable() or c in '\n\r\t' else ' ' for c in decoded)
                    if len(cleaned.strip()) > 50:
                        text_pieces = [cleaned]
                except:
                    decoded = raw_text.decode('cp1252', errors='ignore')
                    cleaned = ''.join(c if c.isprintable() or c in '\n\r\t' else ' ' for c in decoded)
                    if len(cleaned.strip()) > 50:
                        text_pieces = [cleaned]

        ole.close()
        
        result = '\n'.join(text_pieces)
        # Clean up control characters but keep newlines
        result = ''.join(c if c.isprintable() or c in '\n\r\t' else '\n' for c in result)
        # Collapse multiple blank lines
        while '\n\n\n' in result:
            result = result.replace('\n\n\n', '\n\n')
        
        return result.strip()
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse .doc file: {str(e)}")

def verify_matches_with_string_search(in_text_citations, references):
    verification_results = {
        "confirmed_matches": [],
        "unmatched_citations": [],
        "unmatched_references": [],
        "duplicate_first_names": {},
        "summary": "Simple first-name match verification completed (case-insensitive)."
    }

    def extract_first_author(citation):
        match = re.search(r'^([A-Za-z\'-]+)', citation.strip('()[] ').split(' et al.')[0].split(' and ')[0].strip())
        if match:
            return match.group(1).strip()
        return None

    def extract_first_ref_author(ref):
        match = re.search(r'^([A-Za-z\s\'-]+)', ref.strip())
        if match:
            author = match.group(1).rstrip(',.').strip()
            return author
        return None

    ref_groups = {}
    for ref in references:
        ref_author = extract_first_ref_author(ref)
        if ref_author:
            ref_groups.setdefault(ref_author.lower(), []).append(ref)

    for first_name, refs in ref_groups.items():
        if len(refs) > 1:
            verification_results["duplicate_first_names"][first_name.capitalize()] = refs

    matched_refs = set()

    for cit in in_text_citations:
        cit_author = extract_first_author(cit)
        if not cit_author:
            verification_results["unmatched_citations"].append(cit)
            continue

        matched = False
        best_ref = None
        for ref in references:
            ref_author = extract_first_ref_author(ref)
            if ref_author and cit_author.lower() == ref_author.lower():
                matched = True
                best_ref = ref
                matched_refs.add(ref)
                break

        if matched:
            verification_results["confirmed_matches"].append({
                "citation": cit,
                "matched_ref": best_ref
            })
        else:
            verification_results["unmatched_citations"].append(cit)

    verification_results["unmatched_references"] = [ref for ref in references if ref not in matched_refs]

    return verification_results

def count_references_and_citations(analysis):
    num_unique_citations = len(analysis.get("in_text_citations", []))
    num_references = len(analysis.get("references", []))
    analysis["num_unique_citations"] = num_unique_citations
    analysis["num_references"] = num_references
    return analysis

def apply_italic_formatting(ref_text: str) -> str:
    """
    Apply <i> tags to parts of a reference that should be italicized
    per academic conventions (Harvard, APA). Uses regex pattern matching.
    
    Rules:
    - Journal/periodical names → italic
    - Book/report/media titles → italic
    - Article/chapter titles → NOT italic
    """
    import html as html_mod
    ref = html_mod.escape(ref_text)
    
    # === 1. JOURNAL / PERIODICAL: detected by volume(issue) OR bare page range ===
    vol_issue = re.search(r',\s*\d{1,4}\s*\(\d{1,4}\)', ref)
    page_range = re.search(r',\s*\d+\s*[-–]\s*\d+', ref)
    periodical_marker = vol_issue or page_range
    if periodical_marker:
        before = ref[:periodical_marker.start()]
        last_dot = before.rfind('. ')
        if last_dot >= 0:
            journal_name = before[last_dot + 2:].rstrip(', ')
            # Safety check: the ". " before the journal name must NOT be the one
            # right after the year — otherwise this text is the title (book), not
            # a journal name. This prevents false positives like book titles
            # containing date ranges (e.g. "History of science, 1900-2000").
            year_dot = re.search(r'\)\.\s', before)
            year_dot_pos = year_dot.start() + 1 if year_dot else -1
            if last_dot > year_dot_pos and len(journal_name) > 2 and not journal_name.startswith('http'):
                pos = last_dot + 2
                return ref[:pos] + '<i>' + journal_name + '</i>' + ref[pos + len(journal_name):]
        return ref
    
    # === 2. EDITED CHAPTER: contains "In ... (Ed.), " or "In ... (Eds.), " ===
    ed_match = re.search(r'\bIn\s+.*?\(Eds?\.\)[,.]?\s*', ref)
    if ed_match:
        title_start = ed_match.end()
        rest = ref[title_start:]
        # Book title ends at next period, or "(pp." or bracket
        title_end = re.search(r'(?:\.|\s\(pp?\.)', rest)
        if title_end:
            title = rest[:title_end.start()]
            if len(title) > 2:
                return ref[:title_start] + '<i>' + title + '</i>' + ref[title_start + len(title):]
        return ref
    
    # === 3. BOOK / REPORT / MEDIA: italicize the title after the year ===
    # Find year pattern: (2020) or (2020, May) or (2020, May 8) or (n.d.)
    year = re.search(r'\((?:\d{4}[a-z]?(?:,\s+\w+(?:\s+\d{1,2})?(?:[–\-]\d{1,2})?)?|n\.d\.)\)\.?\s*', ref)
    if year:
        after_year = ref[year.end():]
        # Split into sentence-like segments
        segments = re.split(r'(?<=\.)\s+(?=[A-Z])', after_year, maxsplit=3)
        
        if len(segments) >= 2:
            first = segments[0].rstrip('.')
            if len(first) > 2:
                pos = year.end()
                return ref[:pos] + '<i>' + first + '</i>' + ref[pos + len(first):]
        elif len(segments) == 1:
            title = segments[0].rstrip('.')
            if len(title) > 2:
                pos = year.end()
                return ref[:pos] + '<i>' + title + '</i>' + ref[pos + len(title):]
    
    return ref


def extract_verbatim_references(full_text: str, ai_references: list) -> dict:
    """
    For each reference identified by the AI, find the closest verbatim match
    in the original document text. Includes safeguards against DOI bleeding
    and cross-reference mixups.
    
    Returns a dict mapping AI reference -> verbatim source text with confidence.
    """
    from difflib import SequenceMatcher
    
    # ─── STEP 1: Isolate the reference section ───
    # Find where the reference list starts (look for common headings)
    ref_section = full_text
    ref_heading_patterns = [
        r'(?i)\n\s*(references|bibliography|works\s+cited|reference\s+list)\s*\n',
    ]
    ref_start_idx = None
    for pattern in ref_heading_patterns:
        match = re.search(pattern, full_text)
        if match:
            ref_start_idx = match.end()
            break
    
    if ref_start_idx is not None:
        ref_section = full_text[ref_start_idx:]
    
    # ─── STEP 2: Smart atomic splitting ───
    # Split the reference section into individual reference entries.
    # A new reference starts with a line that looks like an author name:
    #   "Surname, I." or "Surname, Initial" or "[1]" or "1."
    # Lines starting with DOI/URL/http are CONTINUATIONS, not new entries.
    
    ref_start_pattern = re.compile(
        r'^(?:'
        r'[A-Z][a-zA-Zà-öø-ÿ\'\-]+\s*,'       # Surname followed by comma (e.g., "Smith,")
        r'|\[\d+\]'                             # Numbered reference [1]
        r'|\d+\.\s+[A-Z]'                       # Numbered reference "1. Author"
        r'|[A-Z][a-zA-Zà-öø-ÿ\'\-]+\s+\('       # Surname followed by "(" (e.g., "Smith (2020)")
        r'|[A-Z]\.?\s*,?\s*\('                   # Single letter + date (e.g., "A. (2020)" or "A (2020)")
        r'|[A-Z]\.?\s*,'                         # Single letter + comma (e.g., "A, B." or "A.,")
        r'|\(\d{4}\)'                             # Year-first format "(2020) Report..."
        r')',
    )

    # Separate pattern for organizational names — requires a year nearby to avoid matching titles
    org_name_pattern = re.compile(r'^[A-Z][a-zA-Zà-öø-ÿ\'\-]+\s+[A-Z]')
    
    # Patterns that indicate a CONTINUATION line (never starts a new reference)
    continuation_pattern = re.compile(
        r'^(?:'
        r'https?://'                             # URL
        r'|[Dd]oi[\s.:]+'                        # DOI (case variants)
        r'|[Aa]vailable\s+at'                    # "Available at:"
        r'|[Aa]ccessed'                          # "Accessed 12 March"
        r'|pp?\.\s*\d'                           # "p. 123" or "pp. 45-67"
        r'|[Vv]ol\.|[Ii]ssue|[Rr]etrieved'      # Volume/Issue/Retrieved
        r'|(?:The|A|An|In|On|Of|For|And|Their|Its|Effects?|Impact)\s'  # Common title-start words
        r'|[a-z]'                                # Starts with lowercase letter (always continuation)
        r'|["\'\u201c\u2018]'                    # Starts with opening quotation mark (title)
        r')'
    )
    
    # Year pattern to validate organizational name lines
    has_year = re.compile(r'\b(?:19|20)\d{2}\b')
    
    lines = ref_section.split('\n')
    atomic_refs = []
    current_ref_lines = []
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        
        is_continuation = continuation_pattern.match(stripped)
        
        # For "two capitalized words" (org names), only treat as new ref if a year is found nearby
        is_org_name = org_name_pattern.match(stripped) and not is_continuation
        if is_org_name:
            # Only accept as new ref if line contains a year in first 80 chars
            is_org_name = bool(has_year.search(stripped[:80]))
        
        is_new_ref = (ref_start_pattern.match(stripped) or is_org_name) and not is_continuation
        
        if is_new_ref and current_ref_lines:
            # Save the previous complete reference
            atomic_refs.append(' '.join(current_ref_lines))
            current_ref_lines = [stripped]
        else:
            # Continuation of current reference (including DOIs, URLs, etc.)
            current_ref_lines.append(stripped)
    
    # Don't forget the last reference
    if current_ref_lines:
        atomic_refs.append(' '.join(current_ref_lines))
    
    # Filter out very short entries (likely not actual references)
    atomic_refs = [r for r in atomic_refs if len(r) > 20]

    # ─── POST-SPLIT PASS: detect merged references within a single entry ───
    # Sometimes PDFs put two references on the same line (DOI followed immediately
    # by the next author's name). Detect and split these.
    demerge_pattern = re.compile(
        r'(?<=[0-9])'                          # after a digit (end of DOI/year)
        r'\s+'                                  # whitespace
        r'(?=[A-Z][a-zA-Zà-öø-ÿ\'\-]+\s*,)'   # next author surname + comma
    )
    demerged_refs = []
    for ref in atomic_refs:
        # Check if entry contains multiple DOIs — strong signal of merge
        doi_count = len(re.findall(r'(?:doi[\s.:]+|https?://doi\.org/)', ref, re.IGNORECASE))
        if doi_count >= 2:
            # Split at the boundary between DOI end + next author start
            parts = demerge_pattern.split(ref, maxsplit=1)
            if len(parts) > 1:
                demerged_refs.extend([p.strip() for p in parts if len(p.strip()) > 20])
            else:
                demerged_refs.append(ref)
        else:
            demerged_refs.append(ref)
    atomic_refs = demerged_refs
    
    # ─── STEP 3: Match using author + year compound key ───
    def extract_author_year(text):
        """Extract (first_author_surname, year) from a reference string."""
        author = None
        year = None
        # First author: take text before first comma or parenthesis
        author_match = re.match(r'^[^a-z]*?([A-Z][a-zA-Zà-öø-ÿ\'\-]+)', text.strip())
        if author_match:
            author = author_match.group(1).lower()
        # Year: find a 4-digit year
        year_match = re.search(r'\b(19|20)\d{2}\b', text)
        if year_match:
            year = year_match.group(0)
        return (author, year)
    
    verbatim_map = {}
    used_candidates = {}  # Track which candidate was matched by which AI ref
    
    for ai_ref in ai_references:
        best_score = 0
        best_match = ai_ref  # fallback to AI version if no match found
        ai_author, ai_year = extract_author_year(ai_ref)
        ai_ref_lower = ai_ref.lower().strip()
        
        for candidate in atomic_refs:
            candidate_lower = candidate.lower().strip()
            
            # Quick filter: skip candidates too different in length
            len_ratio = len(candidate_lower) / max(len(ai_ref_lower), 1)
            if len_ratio < 0.3 or len_ratio > 3.0:
                continue
            
            # Compound key check: author AND year must both appear
            cand_author, cand_year = extract_author_year(candidate)
            
            author_ok = (not ai_author) or (not cand_author) or (ai_author == cand_author)
            year_ok = (not ai_year) or (not cand_year) or (ai_year == cand_year)
            
            if not author_ok or not year_ok:
                continue
            
            score = SequenceMatcher(None, ai_ref_lower, candidate_lower).ratio()
            if score > best_score:
                best_score = score
                best_match = candidate
        
        # ─── STEP 4: Conflict detection ───
        conflict = None
        if best_match in used_candidates.values():
            # Another AI reference already matched this same verbatim text
            conflicting_ref = [k for k, v in used_candidates.items() if v == best_match]
            conflict = f"Warning: This verbatim text was also matched by: {conflicting_ref[0][:50]}..."
        
        used_candidates[ai_ref] = best_match
        
        result = {
            "verbatim": best_match,
            "confidence": round(best_score, 2)
        }
        if conflict:
            result["conflict"] = conflict
        
        verbatim_map[ai_ref] = result
    
    return verbatim_map

# ─── PYTHON-GUIDED CITATION EXTRACTION ───

# Phase 1: Detect multi-citation blocks (parens with semicolons + years)
MULTI_CITATION_PATTERN = re.compile(
    r'\([^()]*\b\d{4}[a-z]?\b[^()]*;[^()]*\b\d{4}[a-z]?\b[^()]*\)'
)

# Phase 2: Individual citation patterns (most specific first)
CITATION_PATTERNS = [
    # ── Author-Date Parenthetical ──
    # Org abbreviation: (WHO, 2020) or (CDC, 2020)
    (re.compile(r'\(\s*[A-Z]{2,}[,\s]+\d{4}[a-z]?\s*\)'), 'ORG_ABBREV'),

    # With initials: (J. Smith, 2020)
    (re.compile(r'\(\s*[A-Z]\.\s+[A-ZÀ-Ö][a-zà-ö\'\-]+[,\s]+\d{4}[a-z]?\s*\)'), 'INITIALS'),

    # Et al.: (Smith et al., 2020) or (Smith et al., 2020, p. 45)
    (re.compile(r'\(\s*[A-ZÀ-Ö][a-zà-ö\'\-]+\s+et\s+al\.?\s*[,\s]*\d{4}[a-z]?(?:[,\s]+pp?\.\s*[\d\-–]+)?\s*\)'), 'PAR_ETAL'),

    # Two authors (and/&): (Smith and Jones, 2020) or (Smith & Jones, 2020)
    (re.compile(r'\(\s*[A-ZÀ-Ö][a-zà-ö\'\-]+\s+(?:and|&)\s+[A-ZÀ-Ö][a-zà-ö\'\-]+[,\s]+\d{4}[a-z]?(?:[,\s]+pp?\.\s*[\d\-–]+)?\s*\)'), 'PAR_TWO'),

    # No date: (Smith, n.d.)
    (re.compile(r'\(\s*[A-ZÀ-Ö][a-zà-ö\'\-]+[,\s]+n\.d\.\s*\)'), 'PAR_NO_DATE'),

    # Single author with optional page/colon-page: (Smith, 2020) or (Smith, 2020, p. 45) or (Smith, 2020:45)
    (re.compile(r'\(\s*[A-ZÀ-Ö][a-zà-ö\'\-]+[,\s]+\d{4}[a-z]?(?:[,:]\s*(?:pp?\.\s*)?[\d\-–]+)?\s*\)'), 'PAR_SINGLE'),

    # ── Author-Date Narrative ──
    # Et al. narrative: Smith et al. (2020)
    (re.compile(r'[A-ZÀ-Ö][a-zà-ö\'\-]+\s+et\s+al\.?\s*\(\d{4}[a-z]?(?:[,\s]+pp?\.\s*[\d\-–]+)?\)'), 'NAR_ETAL'),

    # Two authors narrative: Smith and Jones (2020)
    (re.compile(r'[A-ZÀ-Ö][a-zà-ö\'\-]+\s+(?:and|&)\s+[A-ZÀ-Ö][a-zà-ö\'\-]+\s+\(\d{4}[a-z]?(?:[,\s]+pp?\.\s*[\d\-–]+)?\)'), 'NAR_TWO'),

    # Single author narrative: Smith (2020) or Smith (2020, p. 45)
    (re.compile(r'[A-ZÀ-Ö][a-zà-ö\'\-]+\s+\(\d{4}[a-z]?(?:[,\s]+pp?\.\s*[\d\-–]+)?\)'), 'NAR_SINGLE'),

    # ── Numbered Styles (Vancouver/IEEE) ──
    # Mixed/multiple numbers: [1, 3-5, 7]
    (re.compile(r'\[\d+(?:\s*[,\-–]\s*\d+)+\]'), 'NUM_MIXED'),

    # Single number: [1]
    (re.compile(r'\[\d+\]'), 'NUM_SINGLE'),

    # ── MLA Style (Author Page) ──
    # (Smith 45) or (Smith 45-67)
    (re.compile(r'\(\s*[A-ZÀ-Ö][a-zà-ö\'\-]+\s+\d+(?:\s*[\-–]\s*\d+)?\s*\)'), 'MLA_PAGE'),
]

# Patterns to match individual citations inside multi-citation blocks (after semicolon split)
# These don't need parentheses — they match the inner text
INNER_CITATION_PATTERNS = [
    # Org abbreviation: WHO, 2020
    (re.compile(r'^\s*[A-Z]{2,}[,\s]+\d{4}[a-z]?\s*$'), 'ORG_ABBREV'),
    # Et al.: Smith et al., 2020
    (re.compile(r'^\s*[A-ZÀ-Ö][a-zà-ö\'\-]+\s+et\s+al\.?\s*[,\s]*\d{4}[a-z]?'), 'PAR_ETAL'),
    # Two authors: Smith and Jones, 2020 or Smith & Jones, 2020
    (re.compile(r'^\s*[A-ZÀ-Ö][a-zà-ö\'\-]+\s+(?:and|&)\s+[A-ZÀ-Ö][a-zà-ö\'\-]+[,\s]+\d{4}[a-z]?'), 'PAR_TWO'),
    # Single author: Smith, 2020
    (re.compile(r'^\s*[A-ZÀ-Ö][a-zà-ö\'\-]+[,\s]+\d{4}[a-z]?'), 'PAR_SINGLE'),
    # Just a year (same author continuation): 2020
    (re.compile(r'^\s*\d{4}[a-z]?\s*$'), 'YEAR_ONLY'),
]

def extract_reference_section(full_text: str) -> tuple:
    """
    Split the document into body text and reference section.
    Returns (body_text, reference_text).
    """
    ref_heading_patterns = [
        r'(?i)\n\s*(references|bibliography|works\s+cited|reference\s+list)\s*\n',
    ]
    
    for pattern in ref_heading_patterns:
        match = re.search(pattern, full_text)
        if match:
            body = full_text[:match.start()]
            refs = full_text[match.end():]
            return (body, refs)
    
    # Fallback: if no heading found, return full text as body
    return (full_text, "")

def extract_citations_regex(body_text: str) -> list:
    """
    Extract all in-text citations from the body text using regex patterns.
    Uses two-phase approach for multi-citations:
      Phase 1: detect multi-citation blocks, split by semicolon
      Phase 2: match individual citations against single patterns
    
    Returns list of dicts: [{"text": "(Smith, 2020)", "type": "PAR_SINGLE"}, ...]
    """
    found_citations = []
    seen_texts = set()  # Deduplication
    
    # Track positions already matched to avoid double-matching
    matched_spans = []
    
    def is_overlapping(start, end):
        for s, e in matched_spans:
            if start < e and end > s:
                return True
        return False
    
    # Phase 1: Find and split multi-citation blocks
    for match in MULTI_CITATION_PATTERN.finditer(body_text):
        if is_overlapping(match.start(), match.end()):
            continue
        matched_spans.append((match.start(), match.end()))
        
        full_block = match.group(0)
        # Strip outer parentheses and split by semicolon
        inner = full_block[1:-1]  # Remove ( and )
        parts = [p.strip() for p in inner.split(';')]
        
        for part in parts:
            part_clean = part.strip()
            if not part_clean:
                continue
            
            # Try to classify each piece
            classified = False
            for pattern, label in INNER_CITATION_PATTERNS:
                if pattern.search(part_clean):
                    citation_text = f"({part_clean})"
                    if citation_text not in seen_texts:
                        found_citations.append({"text": citation_text, "type": label})
                        seen_texts.add(citation_text)
                    classified = True
                    break
            
            # If no inner pattern matched but it has a year, still include it
            if not classified and re.search(r'\d{4}', part_clean):
                citation_text = f"({part_clean})"
                if citation_text not in seen_texts:
                    found_citations.append({"text": citation_text, "type": "UNKNOWN"})
                    seen_texts.add(citation_text)
    
    # Phase 2: Find standalone citations
    for pattern, label in CITATION_PATTERNS:
        for match in pattern.finditer(body_text):
            if is_overlapping(match.start(), match.end()):
                continue
            
            citation_text = match.group(0).strip()
            if citation_text not in seen_texts:
                found_citations.append({"text": citation_text, "type": label})
                seen_texts.add(citation_text)
                matched_spans.append((match.start(), match.end()))
    
    return found_citations

def cross_validate(python_citations: list, ai_citations: list, ai_references: list) -> dict:
    """
    Compare Python-extracted citations with AI-extracted citations.
    Flags discrepancies — citations found by Python but missed by AI,
    and citations claimed by AI but not found by Python (potential hallucination).
    """
    python_texts = set(c["text"] for c in python_citations)
    ai_texts = set(ai_citations)
    
    # Normalize for comparison (lowercase, strip whitespace)
    python_normalized = {t.lower().strip(): t for t in python_texts}
    ai_normalized = {t.lower().strip(): t for t in ai_texts}
    
    # Find discrepancies
    python_only = []  # Python found but AI missed
    ai_only = []      # AI found but Python didn't (possible hallucination)
    confirmed = []    # Both agree
    
    for norm, original in python_normalized.items():
        if norm in ai_normalized:
            confirmed.append(original)
        else:
            # Fuzzy check: maybe AI formatted slightly differently
            found_match = False
            for ai_norm, ai_orig in ai_normalized.items():
                # Check if core content overlaps (first author + year)
                py_author = re.search(r'[A-Za-z\'\-]{2,}', norm)
                ai_author = re.search(r'[A-Za-z\'\-]{2,}', ai_norm)
                py_year = re.search(r'\d{4}', norm)
                ai_year = re.search(r'\d{4}', ai_norm)
                
                if (py_author and ai_author and py_year and ai_year and 
                    py_author.group().lower() == ai_author.group().lower() and
                    py_year.group() == ai_year.group()):
                    confirmed.append(original)
                    found_match = True
                    break
            
            if not found_match:
                python_only.append(original)
    
    for norm, original in ai_normalized.items():
        if norm not in python_normalized:
            # Check fuzzy match as above
            found_match = False
            for py_norm in python_normalized:
                py_author = re.search(r'[A-Za-z\'\-]{2,}', py_norm)
                ai_author = re.search(r'[A-Za-z\'\-]{2,}', norm)
                py_year = re.search(r'\d{4}', py_norm)
                ai_year = re.search(r'\d{4}', norm)
                
                if (py_author and ai_author and py_year and ai_year and 
                    py_author.group().lower() == ai_author.group().lower() and
                    py_year.group() == ai_year.group()):
                    found_match = True
                    break
            
            if not found_match:
                ai_only.append(original)
    
    return {
        "confirmed_by_both": confirmed,
        "python_only": python_only,
        "ai_only_potential_hallucination": ai_only,
        "python_total": len(python_citations),
        "ai_total": len(ai_citations),
    }

@app.post("/api/verify")
async def verify_citations(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(('.pdf', '.docx', '.doc')):
        raise HTTPException(status_code=400, detail="Unsupported file type. Please upload PDF, DOCX, or DOC.")

    file_bytes = await file.read()

    async def event_stream():

        # Stage 1: Detect file format
        yield f"data: {json.dumps({'stage': 'parsing', 'message': 'Detecting file format...'})}\n\n"
        await asyncio.sleep(0.1)
        
        magic = file_bytes[:8]
        try:
            if magic[:4] == b'%PDF':
                yield f"data: {json.dumps({'stage': 'parsing', 'message': 'Reading PDF document...'})}\n\n"
                await asyncio.sleep(0.1)
                full_text = extract_pdf_text(file_bytes)
            elif magic[:2] == b'PK':
                yield f"data: {json.dumps({'stage': 'parsing', 'message': 'Reading Word document (.docx)...'})}\n\n"
                await asyncio.sleep(0.1)
                full_text = extract_docx_text(file_bytes)
            elif magic[:4] == b'\xd0\xcf\x11\xe0':
                yield f"data: {json.dumps({'stage': 'parsing', 'message': 'Reading legacy Word document (.doc)...'})}\n\n"
                await asyncio.sleep(0.1)
                full_text = extract_doc_text(file_bytes)
            else:
                yield f"data: {json.dumps({'stage': 'error', 'message': 'Unrecognized file format.'})}\n\n"
                return
        except Exception as e:
            yield f"data: {json.dumps({'stage': 'error', 'message': f'Failed to read file: {str(e)}'})}\n\n"
            return

        if not full_text:
            yield f"data: {json.dumps({'stage': 'error', 'message': 'No text could be extracted from the file.'})}\n\n"
            return

        word_count = len(full_text.split())
        yield f"data: {json.dumps({'stage': 'extracted', 'message': f'Extracted {word_count:,} words from document'})}\n\n"
        await asyncio.sleep(0.1)

        # Stage 2: Python citation extraction (deterministic — no hallucination)
        yield f"data: {json.dumps({'stage': 'scanning', 'message': 'Python regex scanning for in-text citations...'})}\n\n"
        await asyncio.sleep(0.1)

        body_text, ref_section_text = extract_reference_section(full_text)
        python_citations = extract_citations_regex(body_text)

        py_count = len(python_citations)
        type_counts = {}
        for c in python_citations:
            t = c["type"]
            type_counts[t] = type_counts.get(t, 0) + 1
        type_summary = ", ".join(f"{v} {k}" for k, v in type_counts.items())
        yield f"data: {json.dumps({'stage': 'scanning', 'message': f'Found {py_count} citations via regex ({type_summary})'})}\n\n"
        await asyncio.sleep(0.1)

        # Stage 3: AI Semantic Analysis (receives pre-extracted data — verify only)
        yield f"data: {json.dumps({'stage': 'analyzing', 'message': 'Sending to Gemini AI for semantic matching...'})}\n\n"
        await asyncio.sleep(0.1)

        try:
            client = get_client()

            citations_list = json.dumps([c["text"] for c in python_citations], indent=2)

            prompt = f"""You are a citation verification assistant. Python has already extracted the following in-text citations from a document using regex. Your PRIMARY source of truth is this pre-extracted list.

PRE-EXTRACTED IN-TEXT CITATIONS (found by Python regex — these are confirmed):
{citations_list}

DOCUMENT TEXT (for reference matching, irregularity detection, AND independent scanning):
{full_text[:1000000]}

Your tasks:
1. Extract and list all references from the reference section of the document (typically at the end, under headings like 'References', 'Bibliography', etc.).
2. Match each pre-extracted citation to its corresponding reference.
3. Identify mismatches:
   - Citations without a matching reference (missing references).
   - References without a corresponding citation (unused references).
   - Irregularities: Date mismatches, author name inconsistencies, formatting issues, duplicates.
4. INDEPENDENTLY scan the document for any in-text citations that Python may have MISSED. Report these separately as "ai_additional_citations". These are NOT confirmed — they are warnings for the user to review.

Output in strict JSON format only:
{{
    "in_text_citations": {citations_list},
    "references": ["ref1", "ref2", ...],
    "ai_additional_citations": ["any citations YOU found that are NOT in the pre-extracted list above"],
    "missing_references_for_citations": ["unmatched_citation1", ...],
    "unused_references": ["extra_ref1", ...],
    "irregularities": [
        {{"type": "date_mismatch", "citation": "Author (2020)", "ref": "Author (2019)", "details": "Year differs"}},
        {{"type": "name_mismatch", "citation": "Smith", "ref": "Smyth", "details": "Spelling error"}}
    ],
    "summary": "Brief overview of issues found."
}}
"""

            yield f"data: {json.dumps({'stage': 'analyzing', 'message': 'Gemini is matching citations to references...'})}\n\n"
            
            response = await asyncio.to_thread(
                client.models.generate_content,
                model='gemini-3-flash-preview',
                contents=prompt,
            )
        except Exception as e:
            yield f"data: {json.dumps({'stage': 'error', 'message': f'Gemini API error: {str(e)}'})}\n\n"
            return

        yield f"data: {json.dumps({'stage': 'processing', 'message': 'Parsing AI response...'})}\n\n"
        await asyncio.sleep(0.1)

        # Stage 4: Parse response and cross-validate
        try:
            output_text = response.text.strip()
            if output_text.startswith('```json'):
                output_text = output_text[7:].strip()
            if output_text.endswith('```'):
                output_text = output_text[:-3].strip()
            analysis = json.loads(output_text)

            analysis = count_references_and_citations(analysis)

            # Stage 5: Cross-validate Python vs AI
            yield f"data: {json.dumps({'stage': 'validating', 'message': 'Cross-validating Python extraction vs AI analysis...'})}\n\n"
            await asyncio.sleep(0.1)

            validation = cross_validate(
                python_citations,
                analysis.get("in_text_citations", []),
                analysis.get("references", [])
            )
            analysis["cross_validation"] = validation
            analysis["python_citations"] = [c["text"] for c in python_citations]
            analysis["python_citation_types"] = {c["text"]: c["type"] for c in python_citations}

            num_cit = analysis.get("num_unique_citations", 0)
            num_ref = analysis.get("num_references", 0)
            py_only = len(validation.get("python_only", []))
            ai_only = len(validation.get("ai_only_potential_hallucination", []))
            ai_additional = len(analysis.get("ai_additional_citations", []))
            validate_msg = f"Validated {num_cit} citations, {num_ref} references"
            if py_only:
                validate_msg += f" | {py_only} found by Python only"
            if ai_only:
                validate_msg += f" | {ai_only} AI-only (review needed)"
            if ai_additional:
                validate_msg += f" | {ai_additional} additional found by AI"
            yield f"data: {json.dumps({'stage': 'validating', 'message': validate_msg})}\n\n"
            await asyncio.sleep(0.1)

            # Stage 6: String verification
            verify_msg = f"Running string verification on {num_ref} references..."
            yield f"data: {json.dumps({'stage': 'verifying', 'message': verify_msg})}\n\n"
            await asyncio.sleep(0.1)

            verification = verify_matches_with_string_search(
                analysis.get("in_text_citations", []),
                analysis.get("references", []),
            )
            analysis["string_verification"] = verification

            # Stage 7: Extract verbatim references from source document
            yield f"data: {json.dumps({'stage': 'extracting', 'message': 'Extracting verbatim references from source document...'})}\n\n"
            await asyncio.sleep(0.1)

            verbatim_map = extract_verbatim_references(full_text, analysis.get("references", []))
            # Apply italic formatting to each verbatim reference
            for key in verbatim_map:
                plain = verbatim_map[key].get("verbatim", key)
                verbatim_map[key]["verbatim_html"] = apply_italic_formatting(plain)
            analysis["verbatim_references"] = verbatim_map

            yield f"data: {json.dumps({'stage': 'complete', 'message': 'Analysis complete!', 'data': analysis})}\n\n"

        except json.JSONDecodeError as e:
            yield f"data: {json.dumps({'stage': 'error', 'message': f'Error parsing Gemini response: {str(e)}'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'stage': 'error', 'message': f'Unexpected error: {str(e)}'})}\n\n"

    from starlette.responses import StreamingResponse
    return StreamingResponse(event_stream(), media_type="text/event-stream")

class FormatRequest(BaseModel):
    references: List[str]
    style: str = "harvard"

@app.post("/api/format")
async def format_references(req: FormatRequest):
    client = get_client()
    
    # Select guide based on style
    if req.style == "apa":
        guide = APA_GUIDE
        style_name = "APA 7th Edition"
    else:
        guide = HARVARD_GUIDE
        style_name = "Harvard"
    
    formatted_refs = []
    for ref in req.references:
        prompt = f"""
        Using the {style_name} referencing guide provided below, classify the following input reference and reformat it to match the exact {style_name} style for its type (e.g., Book, Journal Article, Web page, etc.).

        If the input is already in {style_name} style, confirm and output it as is. If not, identify the type and apply the correct format.

        IMPORTANT: In the "formatted" output, wrap parts that should be italicized with <i>...</i> HTML tags.
        Per {style_name} conventions, italicize: journal/periodical names, book titles, report titles, film titles, etc.
        Do NOT italicize: article titles, chapter titles, or webpage titles.

        Guide:
        {guide}

        Input reference:
        {ref}

        Output in JSON:
        {{
            "original": "copy the exact input reference here",
            "type": "classified_type (e.g., Book, Journal Article)",
            "formatted": "reformatted {style_name} reference with <i>italic</i> tags where appropriate"
        }}
        """

        response = await asyncio.to_thread(
            client.models.generate_content,
            model='gemini-3-flash-preview',
            contents=prompt,
        )
        
        try:
            output_text = response.text.strip()
            if output_text.startswith('```json'):
                output_text = output_text[7:].strip()
            if output_text.endswith('```'):
                output_text = output_text[:-3].strip()
            result = json.loads(output_text)
            formatted_refs.append(result)
        except Exception as e:
            formatted_refs.append({"original": ref, "error": str(e), "raw_response": response.text})

    return {"formatted_references": formatted_refs}

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
