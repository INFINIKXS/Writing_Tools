"""
ner_author_extractor.py
=======================
Multi-pass NER sieve for extracting author names from academic PDFs.
Used as a fallback layer between GROBID (Layer 3) and CrossRef (Layer 5)
in metadata.py when GROBID fails to find authors.

Algorithm:
  Pass 1  — Regex: look for explicit "Author(s):" label near top of text
  Pass 2  — NER: run spaCy PERSON entity detection on first ~300 words
  Pass 3  — Heuristic: lines between title and abstract with title-case names
  Post    — Clean superscripts (1,2,*, †, ‡ etc.) from all candidates
"""

from __future__ import annotations

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Lazy model loader (load once, reuse) ──────────────────────────────────────
_nlp = None

def _get_nlp():
    """Load the spaCy model once and cache it."""
    global _nlp
    if _nlp is None:
        try:
            import spacy
            # Try transformer model first, fall back gracefully
            for model in ("en_core_web_trf", "en_core_web_lg", "en_core_web_sm"):
                try:
                    _nlp = spacy.load(model)
                    logger.info("Loaded spaCy model: %s", model)
                    break
                except OSError:
                    continue
            if _nlp is None:
                raise RuntimeError(
                    "No spaCy English model found. Run: "
                    "python -m spacy download en_core_web_sm"
                )
        except ImportError:
            raise ImportError("spaCy not installed. Run: pip install spacy")
    return _nlp


# ── Superscript / noise cleaner ────────────────────────────────────────────────

# Removes trailing superscript markers like  1,2*  †  ‡  a,b  (a)  *
_SUPERSCRIPT_RE = re.compile(
    r'[\s,]*(?:\d+,?)+[\s*†‡]*$'   # numeric: "1,2*"
    r'|[\s,]*[†‡✉*]+$'             # symbols: "†", "✉"
    r'|[\s,]*\([a-z,]+\)$'         # alpha: "(a,b)"
    r'|[\s,]+[a-z](,[a-z])*$',     # letter: "a,b" — requires leading separator
    re.IGNORECASE
)

def _clean_author(name: str) -> str:
    """Strip superscript affiliation markers and normalise whitespace."""
    name = _SUPERSCRIPT_RE.sub("", name).strip()
    # Remove leftover punctuation at end
    name = re.sub(r'[,;.\s]+$', '', name)
    return name


# Common non-name words that NER sometimes picks up from PDF text
_NON_NAME_RE = re.compile(
    r'\b(University|Department|Institute|School|College|Laboratory'
    r'|doi|http|©|Abstract|Introduction|Keywords|Background'
    r'|Netherlands|Germany|France|England|Scotland|Ireland|Sweden'
    r'|Norway|Denmark|Finland|Switzerland|Austria|Belgium|Spain'
    r'|Italy|Portugal|Canada|Australia|Zealand|Africa|China|Japan'
    r'|Korea|India|Brazil|Mexico|Singapore|Malaysia|Thailand'
    r'|United States|United Kingdom)\b',
    re.IGNORECASE,
)

def _is_valid_author(name: str) -> bool:
    """
    Sanity check: reject strings that are clearly not human names.
    An author name should:
      - Be 2+ words (first + last at minimum)
      - Not contain numbers or common non-name words
      - Be under 60 characters
    """
    if not name or len(name) < 4 or len(name) > 60:
        return False
    if re.search(r'\d', name):          # contains digits
        return False
    if _NON_NAME_RE.search(name):
        return False
    words = name.split()
    if len(words) < 2:                  # single word is not a full name
        return False
    return True


def _deduplicate(names: list[str]) -> list[str]:
    """Preserve order while removing duplicates (case-insensitive)."""
    seen = set()
    result = []
    for n in names:
        key = n.lower()
        if key not in seen:
            seen.add(key)
            result.append(n)
    return result


# ── Pass 1: Regex label match ──────────────────────────────────────────────────

_AUTHOR_LABEL_RE = re.compile(
    r'(?:Authors?|By|Written\s+by)\s*[:\-]?\s*(.+)',
    re.IGNORECASE
)

def _pass1_regex_label(text: str) -> list[str]:
    """
    Look for explicit author label like 'Authors: John Smith, Jane Doe'
    Scans only the first 50 lines.
    """
    authors = []
    for line in text.splitlines()[:50]:
        m = _AUTHOR_LABEL_RE.match(line.strip())
        if m:
            raw = m.group(1)
            # Authors are usually comma or semicolon separated
            candidates = re.split(r'[,;]', raw)
            for c in candidates:
                cleaned = _clean_author(c.strip())
                if _is_valid_author(cleaned):
                    authors.append(cleaned)
            if authors:
                break
    return authors


# ── Pass 2: spaCy NER ─────────────────────────────────────────────────────────

def _pass2_ner(text: str) -> list[str]:
    """
    Run spaCy PERSON NER on the first ~300 words of the document.
    Academic papers always list authors within the first screen of text,
    so we don't need to process the entire document.
    """
    nlp = _get_nlp()

    # Limit to first 300 words to keep this fast
    words = text.split()
    excerpt = " ".join(words[:300])

    doc = nlp(excerpt)
    authors = []
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            cleaned = _clean_author(ent.text)
            if _is_valid_author(cleaned):
                authors.append(cleaned)
    return authors


# ── Pass 3: Positional heuristic ──────────────────────────────────────────────

def _pass3_positional_heuristic(text: str, title: Optional[str] = None) -> list[str]:
    """
    Heuristic: author names in academic papers appear between the title
    and the abstract. They are:
      - Title-case (or ALL CAPS for some journals)
      - Shorter than the title and abstract lines
      - Not sentence-like (no verbs, no full stops mid-string)

    Strategy: scan lines 3-20, find title-case lines that aren't
    section headings or affiliations.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    authors = []

    # Find approximate title position
    title_line_idx = 0
    if title:
        for i, line in enumerate(lines[:15]):
            if title[:20].lower() in line.lower():
                title_line_idx = i
                break

    # Scan the window immediately after the title
    window_start = title_line_idx + 1
    window_end   = min(window_start + 15, len(lines))

    for line in lines[window_start:window_end]:
        # Stop at abstract
        if re.match(r'^(abstract|introduction|background|keywords)', line, re.IGNORECASE):
            break
        # Skip affiliations (usually start with superscript digit or dept name)
        if re.match(r'^\d', line):
            continue
        if re.search(r'\b(Department|University|Institute|School|College|Laboratory)\b',
                     line, re.IGNORECASE):
            continue
        # Skip email lines
        if '@' in line or 'doi' in line.lower():
            continue
        # Candidate: title-case line with 2+ words, no punctuation mid-string
        if re.match(r'^[A-Z][a-z]', line) and len(line.split()) >= 2:
            candidates = re.split(r'[,;]', line)
            for c in candidates:
                cleaned = _clean_author(c.strip())
                if _is_valid_author(cleaned):
                    authors.append(cleaned)

    return authors


# ── Public entry point ─────────────────────────────────────────────────────────

def extract_authors_ner(
    first_page_text: str,
    title: Optional[str] = None,
    max_authors: int = 20,
) -> list[str]:
    """
    Run the multi-pass NER sieve and return a deduplicated author list.

    Args:
        first_page_text: Raw text from first 1-2 pages of the PDF
        title:           Known title (improves positional heuristic)
        max_authors:     Cap result at this many (sanity limit)

    Returns:
        List of cleaned author name strings, or [] if nothing found.
    """
    all_candidates = []

    # Pass 1 — fastest, most precise when label is present
    p1 = _pass1_regex_label(first_page_text)
    if p1:
        logger.debug("NER Pass 1 (regex label) found: %s", p1)
        all_candidates.extend(p1)

    # Pass 2 — NER (runs regardless; cross-validates Pass 1)
    try:
        p2 = _pass2_ner(first_page_text)
        if p2:
            logger.debug("NER Pass 2 (spaCy PERSON) found: %s", p2)
            all_candidates.extend(p2)
    except Exception as exc:
        logger.warning("NER Pass 2 failed: %s", exc)

    # Pass 3 — positional heuristic (only if passes 1+2 found nothing)
    if not all_candidates:
        p3 = _pass3_positional_heuristic(first_page_text, title)
        if p3:
            logger.debug("NER Pass 3 (positional heuristic) found: %s", p3)
            all_candidates.extend(p3)

    result = _deduplicate(all_candidates)[:max_authors]
    logger.info("NER sieve final authors: %s", result)
    return result
