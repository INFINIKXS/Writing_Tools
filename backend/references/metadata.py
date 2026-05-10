"""
Metadata extraction from PDFs and DOCX files.
AI-FREE deterministic cascade version.
==========================================================
Replaces Gemini with a deterministic cascade:

  Layer 1  →  PDF embedded properties  (fast, zero cost)
  Layer 2  →  Custom regex on first 3 pages  (your existing text_utils.py)
  Layer 3  →  GROBID header extraction  (fallback for title/authors/year/DOI)
  Layer 4  →  pdf2doi  (focused DOI rescue if GROBID also misses it)
  Layer 5  →  CrossRef API  (verification + metadata enrichment)
  Layer 6  →  PubMed API   (secondary verification)

GROBID must be running locally before importing this module.
Start it with:
    docker run --rm --init --ulimit core=0 -p 8070:8070 grobid/grobid:0.9.0-crf
"""

from __future__ import annotations

import io
import logging
import os
import re
import tempfile
import time
import asyncio
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

import requests
from docx import Document

from utils.text_utils import classify_source_type, extract_doi, extract_all_dois

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
GROBID_URL      = os.getenv("GROBID_URL", "http://localhost:8070")
CROSSREF_API    = "https://api.crossref.org/works"
PUBMED_SEARCH   = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH    = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
TEI_NS          = {"tei": "http://www.tei-c.org/ns/1.0"}
REQUEST_TIMEOUT = 15   # seconds  (local-only, no CrossRef consolidation)


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — PDF embedded metadata
# ══════════════════════════════════════════════════════════════════════════════

# Patterns that indicate the PDF /Title field contains internal production IDs,
# copyright notices, or other junk — NOT a real paper title.
_GARBAGE_TITLE_RE = re.compile(
    r'(?:'
    r'^[a-z0-9_\-]{5,}\s+\d+\.\.\d+'     # "ao2c00362 1..9", "pone_0294946 1..23"
    r'|^©'                                 # copyright symbol
    r'|^The Author\(?s?\)?'                # "The Author(s)"
    r'|Creative Commons'                   # CC licence text
    r'|NoDerivatives'
    r'|Open Access'
    r'|International License'
    r'|licensed material'
    r'|permission under this licence'
    r'|terms of the Creative Commons'
    r'|exceeds the permitted use'
    r'|copyright holder'
    r'|obtain permission'
    r'|et al\.\s+\w'                    # "Gupta et al. BioData..." citation header
    r'|\(\d{4}\)\s+\d+:\d+'             # journal volume format "(2024) 17:54"
    r'|full list of author'              # "Full list of author information is..."
    r'|author information'               # author info section boilerplate
    r'|distributed under the terms'
    r'|creativecommons\.org'
    r'|^doi:'                              # DOI string used as title
    r'|^https?://'                         # URL used as title
    r'|^Microsoft Word'                    # Word doc conversion artefact
    r'|^untitled'                          # literally "untitled"
    r'|^\d{4}-\d{4}'                       # ISSN used as title
    r')',
    re.IGNORECASE,
)


def _is_garbage_title(title: str) -> bool:
    """
    Return True if a PDF metadata title is clearly NOT a real paper title.
    Publishers often dump internal production IDs, filenames, or copyright
    notices into the PDF /Title field.
    """
    if not title or len(title.strip()) < 5:
        return True
    t = title.strip()
    # Matches known garbage patterns
    if _GARBAGE_TITLE_RE.search(t):
        return True
    # Mostly digits/punctuation with very few alpha chars → probably a code
    alpha_ratio = sum(c.isalpha() for c in t) / max(len(t), 1)
    if alpha_ratio < 0.4:
        return True
    # Fewer than 3 actual words → unlikely to be a paper title
    words = [w for w in t.split() if len(w) > 1 and w.isalpha()]
    if len(words) < 3:
        return True
    return False


def _extract_pdf_metadata(pdf_path: str) -> dict:
    """
    Read the hidden metadata baked into the PDF file itself.
    This is the fastest and most reliable source when available.
    Returns a dict with keys: title, authors, year, doi  (all may be None).
    """
    result = {"title": None, "authors": [], "year": None, "doi": None}
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        info   = reader.metadata or {}

        raw_title = info.get("/Title") or info.get("Title")
        if raw_title and not _is_garbage_title(raw_title):
            result["title"] = raw_title.strip()
        elif raw_title:
            logger.debug("Rejected garbage PDF title: %r", raw_title)

        raw_author = info.get("/Author") or info.get("Author")
        if raw_author:
            # Authors can be semicolon- or comma-separated
            result["authors"] = [
                a.strip() for a in re.split(r"[;,]", raw_author) if a.strip()
            ]

        # Year — check CreationDate or ModDate  (format: D:YYYYMMDDHHmmSS)
        for date_key in ("/CreationDate", "/ModDate", "CreationDate", "ModDate"):
            raw_date = info.get(date_key, "")
            year_match = re.search(r"(\d{4})", str(raw_date))
            if year_match:
                year = int(year_match.group(1))
                if 1900 < year <= 2100:
                    result["year"] = year
                    break

        # DOI — try Subject/Keywords/custom fields first
        for field in ("/Subject", "/Keywords", "Subject", "Keywords", "/doi", "doi"):
            raw = info.get(field, "")
            doi = extract_doi(str(raw))
            if doi:
                result["doi"] = doi
                break

    except Exception as exc:
        logger.warning("PDF metadata read failed: %s", exc)

    return result


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 2 — Your existing regex  (text_utils.py)
# ══════════════════════════════════════════════════════════════════════════════

def _extract_via_regex(pdf_path: str, pages: int = 2) -> dict:
    """
    Extract raw text from the first `pages` pages and run your existing
    two-pass DOI regex from text_utils.  Also pulls a naive title/year guess.
    Returns: { doi, year, title }  — authors are not reliably found via regex.
    """
    result = {"doi": None, "year": None, "title": None}
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        text_pages = []
        for i, page in enumerate(reader.pages):
            if i >= pages:
                break
            text_pages.append(page.extract_text() or "")
        full_text = "\n".join(text_pages)

        # ── Heal line-wrapped DOI URLs before regex ──────────────────────────
        healed = re.sub(
            r'(https?://[^\s]*?)\n\s*',
            lambda m: m.group(1),
            full_text
        )
        healed = re.sub(r'(10\.\d{4,9}/[^\s]*?)-?\n\s*([a-zA-Z0-9])', r'\1\2', healed)
        # Heal DOIs split at a dot boundary:  "journal.pone.\n0294946" → joined
        healed = re.sub(r'(10\.\d{4,9}/[^\s]*\.)\s*\n\s*(\d)', r'\1\2', healed)

        # DOI — your robust two-pass regex
        result["doi"] = extract_doi(healed)

        # Year — look for 4-digit years in plausible publication range
        years = re.findall(r"\b(19[5-9]\d|20[0-2]\d)\b", full_text)
        if years:
            result["year"] = int(years[0])

        # Title — heuristic: first non-empty line on page 0 longer than 20 chars
        for line in text_pages[0].splitlines() if text_pages else []:
            line = line.strip()
            if len(line) > 20 and not re.match(r"^\d", line) and not _is_garbage_title(line):
                result["title"] = line
                break

    except Exception as exc:
        logger.warning("Regex extraction failed: %s", exc)

    return result


def _extract_identity_from_pdf(pdf_path: str) -> dict:
    """
    Aggressively extract a paper identity fingerprint directly from PDF text.
    Used as a last-resort source of comparison identifiers before API verification,
    so that we always have *something* to validate against.

    Returns: { title: str|None, surnames: list[str], year: int|None }
      - title  : longest plausible title candidate found in pages 0-1
      - surnames: list of capitalised words that look like author surnames
      - year   : first plausible 4-digit publication year found
    """
    result = {"title": None, "surnames": [], "year": None}
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        pages_text = []
        for i, page in enumerate(reader.pages):
            if i >= 2:   # only look at cover pages
                break
            pages_text.append(page.extract_text() or "")
        text = "\n".join(pages_text)
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        # ── Title: pick the longest line in the first 30 that looks like a title ──
        # Titles tend to be: ≥20 chars, <200 chars, no leading digits, not all-caps junk,
        # not a URL, not a copyright/affiliation line.
        _junk_re = re.compile(
            r'^(https?://|doi:|©|copyright|received|accepted|published|volume|issue'
            r'|correspondence|email|department|university|abstract|introduction|keywords'
            r'|license|open access|noderivatives)',
            re.IGNORECASE,
        )
        candidates = [
            l for l in lines[:30]
            if len(l) >= 20
            and len(l) < 200
            and not re.match(r'^\d', l)
            and not _junk_re.search(l)
            and not l.isupper()
            and not _is_garbage_title(l)
        ]
        if candidates:
            # Prefer the longest — titles are usually the longest non-junk line on page 1
            result["title"] = max(candidates, key=len)

        # ── Year: first plausible publication year ───────────────────────────
        years = re.findall(r'\b(19[5-9]\d|20[0-2]\d)\b', text)
        if years:
            result["year"] = int(years[0])

        # ── Author surnames: capitalised words that look like surnames ────────
        # Look for patterns like "Smith, J." or "J. Smith" or lines that are
        # a comma-separated list of capitalised single words.
        surname_re = re.compile(r'\b([A-Z][a-z]{2,}(?:-[A-Z][a-z]+)?)\b')
        # Only scan the first 15 lines (author block is near the top)
        author_block = "\n".join(lines[:15])
        all_caps_words = surname_re.findall(author_block)
        # Filter out common non-surname words
        _stop = {
            'Abstract', 'Introduction', 'Keywords', 'Background', 'Methods',
            'Results', 'Discussion', 'Conclusion', 'References', 'Received',
            'Accepted', 'Published', 'Correspondence', 'Journal', 'University',
            'Department', 'Research', 'Science', 'Nature', 'Review', 'Article',
        }
        result["surnames"] = [w for w in all_caps_words if w not in _stop]

    except Exception as exc:
        logger.warning("PDF identity extraction failed: %s", exc)
    return result


def _validate_api_result(
    local_meta: dict,
    api_result: dict,
    pdf_path: str,
    threshold: float = 0.90,
) -> bool:
    """
    Validate that an API-returned metadata record actually belongs to the PDF.
    Uses a multi-signal approach:
      1. Title similarity (primary, ≥threshold)
      2. Author surname overlap (secondary)
      3. Year match (tertiary)

    If NO local signals exist after an aggressive extraction attempt,
    returns False — we refuse to blindly accept an unverifiable result.

    Returns True only if at least one signal passes and none actively fail.
    """
    from difflib import SequenceMatcher

    def _sim(a: str, b: str) -> float:
        a = re.sub(r'[^\w\s]', '', (a or '').lower())
        b = re.sub(r'[^\w\s]', '', (b or '').lower())
        return SequenceMatcher(None, a, b).ratio()

    # ── Gather local signals ─────────────────────────────────────────────────
    local_title   = local_meta.get("title")
    local_authors = local_meta.get("authors") or []
    local_year    = local_meta.get("year")

    # If the local layers gave us nothing, do an aggressive PDF scan now.
    if not local_title and not local_authors and not local_year:
        logger.info("No local identity data — running aggressive PDF identity extraction.")
        identity = _extract_identity_from_pdf(pdf_path)
        local_title   = local_title   or identity.get("title")
        local_year    = local_year    or identity.get("year")
        # Don't overwrite local_authors from pdf scan — surnames are too noisy
        # to match against structured API authors; use separately below.
        pdf_surnames  = identity.get("surnames", [])
    else:
        pdf_surnames = []

    # ── Gather API signals ───────────────────────────────────────────────────
    api_title   = api_result.get("title")
    api_authors = api_result.get("authors") or []
    api_year    = api_result.get("year")

    # Extract API author surnames ("Smith, J." → "Smith")
    api_surnames = [a.split(',')[0].strip() for a in api_authors if ',' in a]

    # Extract local author surnames from structured list
    local_surnames = [a.split(',')[0].strip() for a in local_authors if ',' in a]
    # Also extract surnames from "Firstname Lastname" format
    for a in local_authors:
        parts = a.strip().split()
        if len(parts) >= 2 and ',' not in a:
            local_surnames.append(parts[-1])  # last word = surname
    # Also include raw PDF surnames as a fallback
    combined_surnames = set(local_surnames + pdf_surnames)

    # ── If still no signals after extraction, fail safe ─────────────────────
    if not local_title and not combined_surnames and not local_year:
        logger.info(
            "Refusing API result for DOI %s — could not extract any local identity "
            "signal from the PDF to validate against.",
            api_result.get("doi", "?")
        )
        return False

    # ── Check each signal ───────────────────────────────────────────────────
    passes   = []   # signals that actively confirm a match
    failures = []   # signals that actively deny a match

    # 1. Title similarity
    if local_title and api_title:
        sim = _sim(local_title, api_title)
        logger.debug("Title similarity: %.2f ('%s' vs '%s')", sim, local_title[:60], api_title[:60])
        if sim >= threshold:
            passes.append(("title", sim))
        else:
            failures.append(("title", sim))

    # 2. Author surname overlap (at least 1 surname in common)
    if combined_surnames and api_surnames:
        # Normalise for comparison (strip accents, lowercase)
        import unicodedata
        def _norm(s):
            return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
        norm_local = {_norm(s) for s in combined_surnames}
        norm_api   = {_norm(s) for s in api_surnames}
        overlap    = norm_local & norm_api
        logger.debug("Author surname overlap: %s (local) vs %s (api) → %s", norm_local, norm_api, overlap)
        if overlap:
            passes.append(("authors", len(overlap)))
        else:
            failures.append(("authors", 0))

    # 3. Year match (exact)
    if local_year and api_year:
        if int(local_year) == int(api_year):
            passes.append(("year", int(local_year)))
        else:
            failures.append(("year", (local_year, api_year)))

    # ── Decision logic ───────────────────────────────────────────────────────
    # Check if first-author surname matches (strong identity signal)
    first_author_match = any(s == "authors" for s, _ in passes)

    # A title failure is a hard veto UNLESS the first author matches.
    # Rationale: garbage titles (e.g. "Full list of author information") cause
    # false title mismatches, but a matching first-author surname is a strong
    # signal that the DOI is correct.
    for signal, val in failures:
        if signal == "title":
            if first_author_match:
                logger.info(
                    "DOI validation — title mismatch (sim=%.2f) OVERRIDDEN by "
                    "first-author match. Accepting DOI.", val
                )
                return True
            # Also override if local title looks like garbage
            if local_title and _is_garbage_title(local_title):
                logger.info(
                    "DOI validation — title mismatch (sim=%.2f) OVERRIDDEN because "
                    "local title is garbage: %r. Accepting DOI.", val, local_title[:60]
                )
                return True
            logger.info("DOI validation FAILED — title mismatch (sim=%.2f)", val)
            return False

    # Any passing signal is sufficient if no hard vetoes.
    if passes:
        logger.info("DOI validation PASSED — signals: %s", passes)
        return True

    # No signals checked at all (e.g. API returned no title/authors/year).
    logger.info("DOI validation INCONCLUSIVE — no overlapping signals to compare.")
    return False



# ══════════════════════════════════════════════════════════════════════════════
# LAYER 3 — GROBID fallback
# ══════════════════════════════════════════════════════════════════════════════

def _grobid_is_alive() -> bool:
    """Ping the GROBID server. Returns True if it responds."""
    try:
        r = requests.get(f"{GROBID_URL}/api/isalive", timeout=5)
        return r.status_code == 200 and r.text.strip().lower() == "true"
    except Exception:
        return False


def _parse_tei_xml(tei_xml: str) -> dict:
    """
    Parse a GROBID TEI-XML string and extract:
      title, authors (list of full names), year (int), doi (str)
    Returns a dict; any field may be None / empty list.
    """
    result = {"title": None, "authors": [], "year": None, "doi": None}
    try:
        root = ET.fromstring(tei_xml)

        # ── Title ──
        title_el = root.find(".//tei:titleStmt/tei:title[@type='main']", TEI_NS)
        if title_el is not None and title_el.text:
            raw_title = title_el.text.strip()
            if not _is_garbage_title(raw_title):
                result["title"] = raw_title
            else:
                logger.debug("Rejected garbage GROBID title: %r", raw_title)

        # ── Authors ──
        authors = []
        for person in root.findall(".//tei:fileDesc//tei:persName", TEI_NS):
            forename = person.findtext("tei:forename", namespaces=TEI_NS) or ""
            surname  = person.findtext("tei:surname",  namespaces=TEI_NS) or ""
            full     = f"{forename} {surname}".strip()
            if full:
                authors.append(full)
        result["authors"] = authors

        # ── Year ──
        for date_el in root.findall(".//tei:date", TEI_NS):
            when = date_el.get("when", "")
            year_match = re.search(r"(\d{4})", when)
            if year_match:
                yr = int(year_match.group(1))
                if 1900 < yr <= 2100:
                    result["year"] = yr
                    break

        # ── DOI  (GROBID writes <idno type="DOI">) ──
        for idno in root.findall(".//tei:idno", TEI_NS):
            if idno.get("type", "").upper() == "DOI" and idno.text:
                result["doi"] = idno.text.strip().lower()
                break

    except ET.ParseError as exc:
        logger.warning("TEI XML parse error: %s", exc)

    return result


def _extract_via_grobid(pdf_path: str) -> dict:
    """
    Send the PDF to the local GROBID server's processHeaderDocument endpoint.
    consolidateHeader=2  →  CrossRef lookup, inject DOI only (no extra API cost).
    Returns the same dict shape as the other layers.
    """
    empty = {"title": None, "authors": [], "year": None, "doi": None}

    if not _grobid_is_alive():
        logger.warning(
            "GROBID server not reachable at %s — skipping GROBID layer. "
            "Start it with: docker run --rm --init --ulimit core=0 "
            "-p 8070:8070 grobid/grobid:0.9.0-crf",
            GROBID_URL,
        )
        return empty

    try:
        with open(pdf_path, "rb") as fh:
            response = requests.post(
                f"{GROBID_URL}/api/processHeaderDocument",
                files={"input": (Path(pdf_path).name, fh, "application/pdf")},
                data={"consolidateHeader": "0"},   # 0 = local parsing only, no external API calls
                timeout=REQUEST_TIMEOUT,
            )

        if response.status_code != 200:
            logger.warning("GROBID returned HTTP %s", response.status_code)
            return empty

        return _parse_tei_xml(response.text)

    except requests.Timeout:
        logger.warning("GROBID request timed out after %ss", REQUEST_TIMEOUT)
    except Exception as exc:
        logger.warning("GROBID extraction failed: %s", exc)

    return empty


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 4 — pdf2doi focused DOI rescue
# ══════════════════════════════════════════════════════════════════════════════

def _rescue_doi_via_pdf2doi(pdf_path: str) -> Optional[str]:
    """
    Last-resort DOI finder. pdf2doi applies multiple methods sequentially:
      1. PDF metadata fields
      2. Filename pattern match
      3. Text regex scan (first 3 pages)
      4. Web search using paper title (if textract is installed)
    Returns a DOI string or None.
    """
    try:
        import pdf2doi  # pip install pdf2doi
        result = pdf2doi.pdf2doi(pdf_path)
        if result and result.get("identifier"):
            doi = str(result["identifier"]).strip().lower()
            logger.info("pdf2doi rescued DOI: %s", doi)
            return doi
    except ImportError:
        logger.warning("pdf2doi not installed — skipping DOI rescue layer.")
    except Exception as exc:
        logger.warning("pdf2doi failed: %s", exc)
    return None


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 5 — CrossRef API verification + enrichment
# ══════════════════════════════════════════════════════════════════════════════

def crossref_lookup(doi: str) -> Optional[dict]:
    """
    Verify a DOI against CrossRef and return enriched metadata if found.
    Returns a normalised dict or None on failure.
    """
    try:
        url = f"{CROSSREF_API}/{doi}"
        r   = requests.get(url, timeout=REQUEST_TIMEOUT,
                           headers={"User-Agent": "metadata-extractor/1.0"})
        if r.status_code != 200:
            return None

        item = r.json().get("message", {})
        authors = []
        for a in item.get("author", []):
            given  = a.get("given", "")
            family = a.get("family", "")
            if family and given:
                initials = ". ".join(w[0].upper() for w in given.split() if w) + "."
                authors.append(f"{family}, {initials}")
            elif family:
                authors.append(family)
            elif given:
                authors.append(given)

        year = None
        for date_field in ("published-print", "published-online", "issued"):
            parts = item.get(date_field, {}).get("date-parts", [[]])
            if parts and parts[0]:
                year = parts[0][0]
                break

        titles = item.get("title", [])

        # Normalise CrossRef types to match the internal format used by the
        # formatter (e.g. "journal-article" → "Journal Article")
        _CROSSREF_TYPE_MAP = {
            "journal-article":       "Journal Article",
            "book-chapter":          "Book Chapter",
            "book":                  "Book",
            "proceedings-article":   "Conference Paper",
            "posted-content":        "Preprint",
            "report":                "Report",
            "dissertation":          "Thesis",
            "dataset":               "Dataset",
            "monograph":             "Book",
            "edited-book":           "Book",
            "reference-entry":       "Other",
        }
        raw_type = item.get("type", "")
        normalised_type = _CROSSREF_TYPE_MAP.get(raw_type, raw_type.replace("-", " ").title() if raw_type else "Other")

        return {
            "title":               titles[0] if titles else None,
            "authors":             authors,
            "year":                year,
            "doi":                 item.get("DOI", doi).lower(),
            "journal":             (item.get("container-title") or [None])[0],
            "volume":              item.get("volume"),
            "issue":               item.get("issue"),
            "pages":               item.get("page"),
            "publisher":           item.get("publisher"),
            "type":                normalised_type,
            "verification_status": "verified_crossref",
        }
    except Exception as exc:
        logger.warning("CrossRef lookup failed for %s: %s", doi, exc)
    return None


def _crossref_search_by_title(title: str) -> Optional[dict]:
    """
    Search CrossRef by title string (fuzzy) when we have no DOI.
    Validates similarity between the query title and the returned title
    before accepting the match — prevents wrong-DOI assignments.

    Uses two thresholds:
      - 0.90 for general similarity (strict)
      - 0.80 + prefix check for truncated titles (e.g. PDF line-wrap cut-offs)
    """
from difflib import SequenceMatcher

def _norm(s: str) -> str:
    return re.sub(r'[^\w\s]', '', s.lower()).strip()

def _title_sim(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()

def _is_prefix(shorter: str, longer: str) -> bool:
    """Check if shorter is a clean prefix of longer (>=60% of longer)."""
    ns, nl = _norm(shorter), _norm(longer)
    return len(ns) >= 20 and nl.startswith(ns) and len(ns) / max(len(nl), 1) >= 0.60

def _pubmed_search_by_title(title: str) -> Optional[dict]:
    """
    Fallback: search PubMed explicitly by title if we have no DOI.
    Applies the same strict similarity checks as the CrossRef search.
    """
    try:
        search_r = requests.get(
            PUBMED_SEARCH,
            params={"db": "pubmed", "term": f"{title}[Title]", "retmode": "json", "retmax": 3},
            timeout=REQUEST_TIMEOUT,
        )
        if search_r.status_code != 200:
            return None
            
        pmids = search_r.json().get("esearchresult", {}).get("idlist", [])
        if not pmids:
            return None

        # Fetch XML for the top PMIDs
        fetch_r = requests.get(
            PUBMED_FETCH,
            params={"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"},
            timeout=REQUEST_TIMEOUT,
        )
        root = ET.fromstring(fetch_r.text)
        
        for article in root.findall(".//PubmedArticle"):
            medline = article.find(".//MedlineCitation")
            if medline is None:
                continue
                
            candidate_title = medline.findtext(".//ArticleTitle")
            if not candidate_title:
                continue
                
            sim = _title_sim(title, candidate_title)
            article_id_list = article.find(".//PubmedData/ArticleIdList")
            doi_el = article_id_list.find('.//ArticleId[@IdType="doi"]') if article_id_list is not None else None
            doi = doi_el.text if doi_el is not None else None

            # Strict match or prefix match
            if sim >= 0.90 or (sim >= 0.80 and _is_prefix(title, candidate_title)):
                if doi:
                    logger.info("PubMed title search matched (sim=%.2f): %s", sim, candidate_title)
                    res = pubmed_lookup(doi)
                    if res:
                        return res
    except Exception as exc:
        logger.warning("PubMed title search failed: %s", exc)
    return None

def _crossref_search_by_title(title: str) -> Optional[dict]:
    """
    Fallback: search CrossRef explicitly by title if we have no DOI.
    Applies a strict title similarity check (and author checks if available)
    before accepting the match - prevents wrong-DOI assignments.

    Uses two thresholds:
      - 0.90 for general similarity (strict)
      - 0.80 + prefix check for truncated titles (e.g. PDF line-wrap cut-offs)
    """
    try:
        r = requests.get(
            CROSSREF_API,
            params={"query.title": title, "rows": 3, "select": "DOI,title,author,issued"},
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "metadata-extractor/1.0"},
        )
        if r.status_code != 200:
            return None
        items = r.json().get("message", {}).get("items", [])
        if not items:
            return None

        # Pick the first candidate whose title is similar enough to ours
        for item in items:
            candidate_titles = item.get("title", [])
            if not candidate_titles:
                continue
            candidate_title = candidate_titles[0]
            sim = _title_sim(title, candidate_title)

            # Strict match
            if sim >= 0.90:
                doi = item.get("DOI")
                if doi:
                    logger.info("CrossRef title search matched (sim=%.2f): %s", sim, candidate_title)
                    return crossref_lookup(doi)

            # Prefix match — our title is truncated but is a clean start of the real title
            elif sim >= 0.80 and _is_prefix(title, candidate_title):
                doi = item.get("DOI")
                if doi:
                    logger.info(
                        "CrossRef title search PREFIX matched (sim=%.2f): '%s' → '%s'",
                        sim, title[:50], candidate_title[:80],
                    )
                    return crossref_lookup(doi)
            else:
                logger.debug(
                    "CrossRef title search candidate rejected (sim=%.2f): %s", sim, candidate_title
                )

        logger.info("CrossRef title search found no sufficiently similar match for: %s", title)
    except Exception as exc:
        logger.warning("CrossRef title search failed: %s", exc)
    return None


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 6 — PubMed API secondary verification
# ══════════════════════════════════════════════════════════════════════════════

def pubmed_lookup(doi: str) -> Optional[dict]:
    """
    Search PubMed by DOI. Returns a slim metadata dict or None.
    Only used as a secondary check when CrossRef fails.
    """
    try:
        # Step 1 — search for the PMID
        search_r = requests.get(
            PUBMED_SEARCH,
            params={"db": "pubmed", "term": f"{doi}[doi]", "retmode": "json", "retmax": 1},
            timeout=REQUEST_TIMEOUT,
        )
        pmids = search_r.json().get("esearchresult", {}).get("idlist", [])
        if not pmids:
            return None

        # Step 2 — fetch the record
        fetch_r = requests.get(
            PUBMED_FETCH,
            params={"db": "pubmed", "id": pmids[0], "retmode": "xml"},
            timeout=REQUEST_TIMEOUT,
        )
        root = ET.fromstring(fetch_r.text)
        article = root.find(".//Article")
        if article is None:
            return None

        title = article.findtext("ArticleTitle")
        year_el = root.find(".//PubDate/Year")
        year    = int(year_el.text) if year_el is not None and year_el.text else None

        authors = []
        for a in root.findall(".//Author"):
            last    = a.findtext("LastName", "")
            fore    = a.findtext("ForeName", "")
            if last and fore:
                initials = ". ".join(w[0].upper() for w in fore.split() if w) + "."
                authors.append(f"{last}, {initials}")
            elif last:
                authors.append(last)
            elif fore:
                authors.append(fore)

        # Journal metadata
        journal_el = root.find(".//Journal")
        journal_title = None
        volume = None
        issue = None
        if journal_el is not None:
            journal_title = journal_el.findtext("Title") or journal_el.findtext("ISOAbbreviation")
            ji = journal_el.find("JournalIssue")
            if ji is not None:
                volume = ji.findtext("Volume")
                issue = ji.findtext("Issue")

        # Pages
        pages = article.findtext("Pagination/MedlinePgn")

        return {
            "title":               title,
            "authors":             authors,
            "year":                year,
            "doi":                 doi.lower(),
            "journal":             journal_title,
            "volume":              volume,
            "issue":               issue,
            "pages":               pages,
            "type":                "Journal Article",
            "verification_status": "verified_pubmed",
        }
    except Exception as exc:
        logger.warning("PubMed lookup failed for %s: %s", doi, exc)
    return None


# ══════════════════════════════════════════════════════════════════════════════
# COMPATIBILITY ADAPTERS FOR PARSER.PY
# ══════════════════════════════════════════════════════════════════════════════

def perform_pubmed_lookup(doi: str, api_metadata: dict, api_sources: dict) -> bool:
    res = pubmed_lookup(doi)
    if not res:
        return False
    for k in ["title", "authors", "year", "type"]:
        if res.get(k):
            api_metadata[k] = res[k]
            api_sources[k] = "pubmed"
    api_sources["doi"] = "pubmed"
    return True

def perform_crossref_lookup(doi: str, api_metadata: dict, api_sources: dict) -> bool:
    res = crossref_lookup(doi)
    if not res:
        return False
    if res.get("journal"):
        res["source"] = res["journal"]
    for k in ["title", "authors", "year", "source", "volume", "issue", "pages", "publisher", "type"]:
        if res.get(k):
            api_metadata[k] = res[k]
            api_sources[k] = "crossref"
    api_sources["doi"] = "crossref"
    return True


# ══════════════════════════════════════════════════════════════════════════════
# MERGE HELPER
# ══════════════════════════════════════════════════════════════════════════════

def _merge(base: dict, update: dict, overwrite: bool = False) -> dict:
    """
    Fill in missing fields in `base` from `update`.
    If overwrite=True, replaces existing non-empty values in base (provided update has them).
    """
    for key, val in update.items():
        if val is None:
            continue
        if isinstance(val, list) and not val:
            continue
        if overwrite or not base.get(key):
            base[key] = val
    return base


def _is_complete(meta: dict) -> bool:
    """Return True when all four critical fields are present."""
    return bool(
        meta.get("title")
        and meta.get("authors")
        and meta.get("year")
        and meta.get("doi")
    )


# ══════════════════════════════════════════════════════════════════════════════
# MAIN EXTRACTION LOGIC
# ══════════════════════════════════════════════════════════════════════════════

def _extract_metadata_sync(pdf_path: str) -> dict:
    """
    Runs the full cascade and returns a metadata dict:
    {
        "title":               str | None,
        "authors":             list[str],
        "year":                int | None,
        "doi":                 str | None,
        "journal":             str | None,
        "volume":              str | None,
        "issue":               str | None,
        "pages":               str | None,
        "publisher":           str | None,
        "type":                str,
        "verification_status": "verified_crossref" | "verified_pubmed" | "unverified" | "not_found",
        "extraction_layers":   list[str],   # audit trail of what contributed
    }
    """
    meta = {
        "title": None, "authors": [], "year": None, "doi": None,
        "journal": None, "volume": None, "issue": None, "pages": None,
        "publisher": None, "type": "Other", "verification_status": "not_found",
        "extraction_layers": [],
    }

    # ── Layer 1: PDF embedded metadata ────────────────────────────────────────
    layer1 = _extract_pdf_metadata(pdf_path)
    _merge(meta, layer1)
    if any(layer1.values()):
        meta["extraction_layers"].append("pdf_metadata")
    logger.debug("After Layer 1 (PDF metadata): %s", meta)

    # ── Layer 2: Regex (text_utils.py) ────────────────────────────────────────
    layer2 = _extract_via_regex(pdf_path)
    _merge(meta, layer2)
    if any(v for v in layer2.values() if v):
        meta["extraction_layers"].append("regex")
    logger.debug("After Layer 2 (regex): %s", meta)

    # ── Layer 3: GROBID — only if something is still missing ─────────────────
    if not _is_complete(meta):
        layer3 = _extract_via_grobid(pdf_path)
        _merge(meta, layer3)
        if any(v for v in layer3.values() if v):
            meta["extraction_layers"].append("grobid")
        logger.debug("After Layer 3 (GROBID): %s", meta)

    # ── Layer 3b: NER sieve — only if authors still missing after GROBID ──────────
    if not meta.get("authors"):
        try:
            from utils.ner_author_extractor import extract_authors_ner
            from pypdf import PdfReader
            reader = PdfReader(pdf_path)
            first_page_text = reader.pages[0].extract_text() or "" if reader.pages else ""

            ner_authors = extract_authors_ner(
                first_page_text=first_page_text,
                title=meta.get("title"),
            )
            if ner_authors:
                meta["authors"] = ner_authors
                meta["extraction_layers"].append("ner_sieve")
                logger.info("NER sieve found authors: %s", ner_authors)
        except Exception as exc:
            logger.warning("NER sieve failed: %s", exc)

    # ── Layer 3c: LayoutLM — when GROBID + NER both fail ─────────────────────────
    if not meta.get("title") or not meta.get("authors"):
        try:
            from utils.layoutlm_extractor import extract_title_authors_layoutlm
            layoutlm = extract_title_authors_layoutlm(pdf_path)

            if layoutlm.get("title") and not meta.get("title"):
                meta["title"] = layoutlm["title"]
                meta["extraction_layers"].append("layoutlm_title")

            if layoutlm.get("authors") and not meta.get("authors"):
                meta["authors"] = layoutlm["authors"]
                meta["extraction_layers"].append("layoutlm_authors")
        except Exception as exc:
            logger.warning("LayoutLM extraction failed: %s", exc)

    # ── Shared identity validation ─────────────────────────────────────────────
    # _validate_api_result uses title, authors, and year as multi-signal checks.
    # It also does an aggressive PDF scan if the local layers found nothing.

    # ── VERIFICATION & RESCUE LOOP ───────────────────────────────────────────
    # Try PubMed first (cleaner metadata for biomedical), then CrossRef.
    # If the extracted DOI is invalid, we clear it and try pdf2doi to rescue.
    for attempt in range(2):
        if meta.get("doi"):
            # ── PubMed first ──
            pubmed = pubmed_lookup(meta["doi"])
            if pubmed:
                if _validate_api_result(meta, pubmed, pdf_path):
                    _merge(meta, pubmed, overwrite=True)
                    meta["verification_status"] = "verified_pubmed"
                    if "pubmed_verify" not in meta["extraction_layers"]:
                        meta["extraction_layers"].append("pubmed_verify")
                    logger.debug("After PubMed verification: %s", meta)
                    break
                else:
                    logger.info(
                        "PubMed result for DOI %s failed identity validation.",
                        meta["doi"]
                    )

            # ── CrossRef fallback ──
            if meta.get("doi"):
                crossref = crossref_lookup(meta["doi"])
                if crossref:
                    if _validate_api_result(meta, crossref, pdf_path):
                        _merge(meta, crossref, overwrite=True)
                        meta["verification_status"] = "verified_crossref"
                        if "crossref_verify" not in meta["extraction_layers"]:
                            meta["extraction_layers"].append("crossref_verify")
                        logger.debug("After CrossRef verification: %s", meta)
                        break
                    else:
                        logger.info(
                            "CrossRef result for DOI %s failed identity validation. Clearing DOI.",
                            meta["doi"]
                        )
                        meta["doi"] = None

            if meta.get("doi"):
                logger.info("APIs could not verify DOI: %s. Clearing it.", meta["doi"])
                meta["doi"] = None

        if not meta.get("doi") and "pdf2doi" not in meta["extraction_layers"]:
            rescued = _rescue_doi_via_pdf2doi(pdf_path)
            if rescued:
                meta["doi"] = rescued
                meta["extraction_layers"].append("pdf2doi")
                logger.debug("After Layer 4 (pdf2doi rescue): doi=%s", meta.get("doi"))
                continue  # loop again to verify rescued DOI

        break

    # ── Layer 5b: Title search fallback — if still no doi but have title ──────
    if not meta.get("doi") and meta.get("title") and meta["verification_status"] == "not_found":
        # Try PubMed title search first
        pubmed = _pubmed_search_by_title(meta["title"])
        if pubmed:
            _merge(meta, pubmed, overwrite=True)
            meta["verification_status"] = pubmed.get("verification_status", "verified_pubmed_title_search")
            meta["extraction_layers"].append("pubmed_title_search")
            # Flag a warning so the user can cross-check
            meta["warning"] = "Verified via title match only. Please cross-check for accuracy."
            logger.debug("After Layer 5b (PubMed title search): %s", meta)
        else:
            # Fallback to CrossRef title search
            crossref = _crossref_search_by_title(meta["title"])
            if crossref:
                _merge(meta, crossref, overwrite=True)
                meta["verification_status"] = crossref.get("verification_status", "verified_crossref_title_search")
                meta["extraction_layers"].append("crossref_title_search")
                # Flag a warning so the user can cross-check
                meta["warning"] = "Verified via title match only. Please cross-check for accuracy."
                logger.debug("After Layer 5b (CrossRef title search): %s", meta)

    # ── Final status tagging ──────────────────────────────────────────────────
    if meta["verification_status"] == "not_found" and any([
        meta.get("title"), meta.get("doi"), meta.get("year")
    ]):
        meta["verification_status"] = "unverified"

    if meta["type"] == "Other":
        meta["type"] = classify_source_type(meta)

    logger.info(
        "Extraction complete | status=%s | layers=%s | doi=%s",
        meta["verification_status"],
        meta["extraction_layers"],
        meta.get("doi"),
    )
    return meta

# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC ASYNC WRAPPERS FOR FASTAPI ROUTES
# ══════════════════════════════════════════════════════════════════════════════

async def extract_pdf_metadata(file_bytes: bytes) -> dict:
    """
    Extract metadata from a PDF file (in-memory bytes).
    Writes bytes to a temporary file, runs the deterministic cascade,
    then cleans up the file. Returns the populated metadata dict.
    """
    # Create temp file
    fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(file_bytes)
        
        # Run sync cascade in thread pool
        meta = await asyncio.to_thread(_extract_metadata_sync, tmp_path)
        return meta
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError as e:
                logger.warning("Failed to clean up temp PDF %s: %s", tmp_path, e)


def extract_docx_metadata(file_bytes: bytes) -> dict:
    """Extract metadata from a DOCX file using document core properties."""
    metadata = {
        "authors": None, "title": None, "year": None,
        "source": None, "doi": None, "url": None,
        "volume": None, "issue": None, "pages": None,
        "publisher": None, "type": "Other",
        "verification_status": "not_found",
        "extraction_layers": ["docx_metadata"]
    }
    
    with io.BytesIO(file_bytes) as f:
        doc = Document(f)
        
        props = doc.core_properties
        if props.author:
            metadata["authors"] = [a.strip() for a in re.split(r'[;,]', props.author) if a.strip()]
        if props.title and len(props.title) > 3:
            metadata["title"] = props.title
        if props.created:
            metadata["year"] = str(props.created.year)
        
        full_text = '\n'.join(p.text for p in doc.paragraphs[:5])
        docx_doi = extract_doi(full_text)
        if docx_doi:
            metadata["doi"] = docx_doi
        
        if not metadata["title"]:
            lines = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            if lines:
                metadata["title"] = lines[0]
    
    # CrossRef DOI lookup
    if metadata["doi"]:
        try:
            crossref_url = f"https://api.crossref.org/works/{metadata['doi']}"
            resp = requests.get(crossref_url, timeout=10, headers={
                'User-Agent': 'WritingTools/1.0 (mailto:support@paradoxlabs.com)'
            })
            if resp.status_code == 200:
                data = resp.json().get('message', {})
                
                authors = data.get('author', [])
                if authors:
                    author_parts = []
                    for a in authors:
                        family = a.get('family', '')
                        given = a.get('given', '')
                        if family and given:
                            initials = '. '.join(w[0].upper() for w in given.split() if w) + '.'
                            author_parts.append(f"{family}, {initials}")
                        elif family:
                            author_parts.append(family)
                    if author_parts:
                        metadata["authors"] = author_parts
                
                titles = data.get('title', [])
                if titles:
                    metadata["title"] = titles[0]
                
                date_parts = data.get('published-print', data.get('published-online', data.get('created', {})))
                if date_parts and 'date-parts' in date_parts:
                    parts = date_parts['date-parts'][0]
                    if parts:
                        metadata["year"] = str(parts[0])
                
                container = data.get('container-title', [])
                if container:
                    metadata["source"] = container[0]
                
                if data.get('volume'): metadata["volume"] = data['volume']
                if data.get('issue'): metadata["issue"] = data['issue']
                if data.get('page'): metadata["pages"] = data['page']
                if data.get('publisher'): metadata["publisher"] = data['publisher']
                
                cr_type = data.get('type', '')
                type_map = {
                    'journal-article': 'Journal Article',
                    'book': 'Book',
                    'book-chapter': 'Book Chapter',
                    'proceedings-article': 'Conference Paper',
                    'report': 'Report',
                }
                metadata["type"] = type_map.get(cr_type, 'Other')
                metadata["verification_status"] = "verified_crossref"
                metadata["extraction_layers"].append("crossref_verify")
        except Exception:
            pass
    
    if metadata["type"] == "Other":
        metadata["type"] = classify_source_type(metadata)
    
    return metadata
