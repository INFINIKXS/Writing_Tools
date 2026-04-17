"""
Reference List ↔ PDF Matcher.

Given a list of raw reference strings and a set of PDF metadata dicts,
determine which references have a matching PDF and which are missing.
"""

import io
import re
import difflib
from typing import List, Optional

from PyPDF2 import PdfReader


def extract_pdf_metadata_fast(file_bytes: bytes) -> dict:
    """
    Lightweight PDF metadata extraction — regex + PDF properties ONLY.
    No AI calls, no PubMed/CrossRef lookups.
    Designed for the Matcher where we only need title/authors/year/DOI for matching.
    """
    metadata = {
        "authors": None, "title": None, "year": None,
        "doi": None, "source": None,
    }

    try:
        reader = PdfReader(io.BytesIO(file_bytes))

        # ─── PDF built-in metadata ───
        pdf_meta = reader.metadata
        if pdf_meta:
            raw_author = pdf_meta.get('/Author') or pdf_meta.get('author') or ''
            if raw_author and not any(skip in raw_author.lower() for skip in [
                'microsoft', 'adobe', 'scanner', 'latex', 'tex', 'kman', 'acrobat', 'pdf'
            ]):
                metadata["authors"] = raw_author

            raw_title = pdf_meta.get('/Title') or pdf_meta.get('title') or ''
            if raw_title and len(raw_title) > 3:
                metadata["title"] = raw_title

            raw_date = str(pdf_meta.get('/CreationDate') or pdf_meta.get('creation_date') or '')
            year_match = re.search(r'(19|20)\d{2}', raw_date)
            if year_match:
                metadata["year"] = year_match.group(0)

        # Sanity check: author == title → both bogus
        if (metadata.get("authors") and metadata.get("title") and
                str(metadata["authors"]).strip().lower() == str(metadata["title"]).strip().lower()):
            metadata["authors"] = None
            metadata["title"] = None

        # ─── First page text parsing ───
        first_page_text = ''
        for i in range(min(2, len(reader.pages))):
            first_page_text += (reader.pages[i].extract_text() or '') + '\n'

        if first_page_text.strip():
            # DOI
            doi_matches = re.findall(
                r'(?:doi[:\s]*|https?://(?:dx\.)?doi\.org/)?(10\.\d{4,}/[a-zA-Z0-9.\-_/:()\\[\]]+)',
                first_page_text, re.IGNORECASE
            )
            if doi_matches:
                clean_doi = doi_matches[0].rstrip('].;,()')
                clean_doi = re.sub(r'(?i)(Research|Article|Review|Copyright|Downloaded)\b.*$', '', clean_doi)
                metadata["doi"] = clean_doi

            # Title from text (if PDF metadata title was missing or suspicious)
            if not metadata["title"] or len(metadata["title"]) < 10 or ' ' not in metadata["title"]:
                lines = [l.strip() for l in first_page_text.split('\n') if l.strip()]
                skip_pat = re.compile(
                    r'^(vol|volume|issue|page|doi|http|www|©|ISSN|ISBN|'
                    r'RESEARCH|ARTICLE|REVIEW|Open Access|Creative Commons|'
                    r'Correspondence|Author|Received|Accepted|Published|'
                    r'Abstract|Background|Introduction|Methods|Results|'
                    r'Keywords|Licensed|Check for|updates|Citation|'
                    r'This article|The Author|Springer|Elsevier|Wiley|BMC|'
                    r'\d+\s*$|et al\.)', re.IGNORECASE
                )
                best_title, best_score = None, 0
                for line in lines:
                    if len(line) < 15 or len(line) > 300:
                        continue
                    if skip_pat.match(line):
                        continue
                    if re.match(r'^\d+\s*$', line):
                        continue
                    score = min(len(line), 150)
                    if line[0].isupper() and ':' in line:
                        score += 20
                    if score > best_score:
                        best_score = score
                        best_title = line
                if best_title:
                    metadata["title"] = best_title

            # Year from text
            if not metadata["year"]:
                year_m = re.search(r'\b(19|20)\d{2}\b', first_page_text)
                if year_m:
                    metadata["year"] = year_m.group(0)

    except Exception as e:
        print(f"[Matcher] Fast extract failed: {e}")

    # Ensure authors is a list
    if isinstance(metadata["authors"], str):
        raw = metadata["authors"]
        if '; ' in raw:
            metadata["authors"] = [a.strip() for a in raw.split(';') if a.strip()]
        elif ' and ' in raw or ' & ' in raw:
            raw = raw.replace(' & ', ' and ')
            metadata["authors"] = [a.strip() for a in raw.split(' and ') if a.strip()]
        else:
            metadata["authors"] = [raw.strip()]

    return metadata


def parse_raw_reference_fast(ref_text: str) -> dict:
    """
    Lightweight reference text parser — regex ONLY, no AI.
    Extracts DOI, year, volume/issue/pages, and tries basic author/title split.
    """
    metadata = {
        "authors": None, "title": None, "year": None,
        "doi": None, "source": None, "_original": ref_text,
    }

    # DOI
    doi_match = re.search(
        r'(?:doi[:\s]*|https?://(?:dx\.)?doi\.org/)(10\.\d{4,}/[a-zA-Z0-9.\-_/:()]+)',
        ref_text, re.IGNORECASE
    )
    if doi_match:
        metadata["doi"] = doi_match.group(1).rstrip('.,;)')

    # Year
    year_match = re.search(r'\b((?:19|20)\d{2})\b', ref_text)
    if year_match:
        metadata["year"] = year_match.group(1)

    # Volume & Issue (e.g. "21(1)")
    vol_match = re.search(r'\b(\d+)\s*\(([\d\-A-Za-z]+)\)', ref_text)
    if vol_match:
        metadata["volume"] = vol_match.group(1)
        metadata["issue"] = vol_match.group(2)
    elif re.search(r'vol\.?\s*(\d+)', ref_text, re.IGNORECASE):
        v = re.search(r'vol\.?\s*(\d+)', ref_text, re.IGNORECASE)
        if v: metadata["volume"] = v.group(1)

    # Pages (e.g. "pp. 254" or "4004" or "10-20")
    # Strip DOIs and URLs first so their numeric portions aren't matched as pages
    pages_text = re.sub(r'(?:doi[:\s]*|https?://\S+|10\.\d{4,}/\S+)', '', ref_text, flags=re.IGNORECASE)
    pages_match = re.search(r'(?:pp?\.?\s*|pages?\s*)?([eE]?\d+)\s*[-–]\s*([eE]?\d+)', pages_text)
    if pages_match:
        metadata["pages"] = f"{pages_match.group(1)}-{pages_match.group(2)}"
    else:
        single_page_match = re.search(r'pp?\.?\s*([eE]?\d+)', pages_text)
        if single_page_match:
            metadata["pages"] = single_page_match.group(1)

    # Source / Journal (heuristic: text between title and volume)
    if metadata.get("volume"):
        vol_pattern = r'\b' + re.escape(metadata["volume"]) + r'\s*\('
        m = re.search(vol_pattern, ref_text)
        if m:
            left_part = ref_text[:m.start()].strip()
            # Find the last quotation mark or period-space that might signify the end of the title
            title_end_m = re.search(r'.*([\'"]|\.\s+)(.*?)[.,]?\s*$', left_part)
            if title_end_m:
                candidate = title_end_m.group(2).strip(" ,.")
                if len(candidate) > 4 and not candidate.lower().startswith('pp'):
                    metadata["source"] = candidate

    # Try to split author/title from common patterns:
    # "Author, A. (2020). Title. ..."  or  "Author, A., 2020. Title. ..."
    author_title_m = re.match(
        r'^(.+?)\s*[\(\.]?\s*(?:19|20)\d{2}\s*[\)\.]?\s*[.\s]+(.+?)(?:\.|$)',
        ref_text
    )
    if author_title_m:
        metadata["authors"] = author_title_m.group(1).strip().rstrip(',.')
        title_candidate = author_title_m.group(2).strip().rstrip('.')
        # Only accept if it looks like a real title (not too short)
        if len(title_candidate) > 10:
            metadata["title"] = title_candidate
    
    # If authors not found, try "Surname, I." at start
    if not metadata["authors"]:
        lead = re.match(r'^([A-Z][a-z]+(?:,\s*[A-Z]\.?\s*)+)', ref_text)
        if lead:
            metadata["authors"] = lead.group(1).strip()

    return metadata


# ─── Reference list splitter ────────────────────────────────────────────────

_NUMBERED_RE = re.compile(
    r'^\s*(?:\[?\d+[\].)]\s*|•\s*|[-–—]\s*)',   # [1] or 1. or 1) or bullet
)


def parse_reference_list(text: str) -> List[str]:
    """
    Split a block of reference-list text into individual reference strings.

    Handles:
      - Numbered lists  ([1] … , 1. … , 1) … )
      - Blank-line separated paragraphs
      - Bullet / dash prefixed items
    """
    if not text or not text.strip():
        return []

    lines = text.splitlines()

    # Detect whether the list is numbered / bulleted
    numbered_lines = [i for i, l in enumerate(lines) if _NUMBERED_RE.match(l)]
    is_numbered = len(numbered_lines) >= 2

    refs: List[str] = []

    if is_numbered:
        # Each numbered/bulleted line starts a new reference; continuation
        # lines (non-blank, non-numbered) are appended to the current ref.
        current: List[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if _NUMBERED_RE.match(stripped):
                if current:
                    refs.append(" ".join(current))
                current = [_NUMBERED_RE.sub("", stripped).strip()]
            else:
                current.append(stripped)
        if current:
            refs.append(" ".join(current))
    else:
        # Paragraph mode: blank lines separate references.
        current = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if current:
                    refs.append(" ".join(current))
                    current = []
            else:
                current.append(stripped)
        if current:
            refs.append(" ".join(current))

    # Filter out very short fragments (e.g. headings like "References")
    refs = [r for r in refs if len(r) > 20]
    return refs


# ─── Normalisation helpers ───────────────────────────────────────────────────

def _normalise(text: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation edges."""
    if not text:
        return ""
    t = text.lower().strip()
    t = re.sub(r'\s+', ' ', t)
    t = re.sub(r'^[^a-z0-9]+|[^a-z0-9]+$', '', t)
    return t


def _extract_surnames(authors) -> List[str]:
    """
    Pull first-surname tokens from an authors value
    (which may be a list of strings, or a single string).
    """
    if not authors:
        return []
    if isinstance(authors, str):
        # Try splitting on semicolons or " and "
        parts = re.split(r';\s*|\s+and\s+|\s*&\s*', authors)
    elif isinstance(authors, list):
        parts = authors
    else:
        return []
    surnames = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # "Surname, Initials" or "Surname Initials"
        surname = re.split(r'[,\s]', p)[0].strip().rstrip('.')
        if surname and len(surname) > 1:
            surnames.append(surname.lower())
    return surnames


def _extract_year(meta: dict) -> Optional[str]:
    """Return 4-digit year string from metadata, or None."""
    y = meta.get("year")
    if y:
        m = re.search(r'((?:19|20)\d{2})', str(y))
        if m:
            return m.group(1)
    return None


def _extract_doi(meta: dict) -> Optional[str]:
    """Return normalised DOI string, or None."""
    doi = meta.get("doi")
    if doi:
        return doi.strip().lower().rstrip('.,;)')
    return None


# ─── Core matching function ──────────────────────────────────────────────────

def match_references_to_pdfs(
    ref_metadatas: List[dict],
    pdf_metadatas: List[dict],
    threshold: float = 0.50,
) -> dict:
    """
    Match parsed reference metadata against PDF metadata.

    Returns:
        {
            "matched": [
                {
                    "ref_index": int,
                    "ref_text": str,           # original reference string
                    "pdf_filename": str,
                    "confidence": float,        # 0-1
                    "match_reason": str,        # e.g. "DOI match", "Title + Author"
                }
            ],
            "missing": [
                {
                    "ref_index": int,
                    "ref_text": str,
                    "best_candidate": str | None,
                    "best_score": float,
                }
            ]
        }
    """
    matched = []
    missing = []
    used_pdfs = set()  # indices of already-matched PDFs

    for ri, ref in enumerate(ref_metadatas):
        ref_doi = _extract_doi(ref)
        ref_title = _normalise(ref.get("title") or "")
        ref_surnames = _extract_surnames(ref.get("authors"))
        ref_year = _extract_year(ref)
        ref_text = ref.get("_original", "")

        best_score = 0.0
        best_pi = -1
        best_reason = ""

        for pi, pdf in enumerate(pdf_metadatas):
            if pi in used_pdfs:
                continue

            # ── DOI shortcut ──
            pdf_doi = _extract_doi(pdf)
            if ref_doi and pdf_doi and ref_doi == pdf_doi:
                best_score = 1.0
                best_pi = pi
                best_reason = "DOI exact match"
                break

            # ── Composite score ──
            pdf_title = _normalise(pdf.get("title") or "")
            pdf_surnames = _extract_surnames(pdf.get("authors"))
            pdf_year = _extract_year(pdf)

            # Title similarity (weight 0.60)
            if ref_title and pdf_title:
                title_sim = difflib.SequenceMatcher(None, ref_title, pdf_title).ratio()
            else:
                title_sim = 0.0

            # Author similarity (weight 0.25) — first-author surname match
            if ref_surnames and pdf_surnames:
                # Check if ANY ref surname matches ANY pdf surname
                author_sim = 0.0
                for rs in ref_surnames[:3]:       # check first 3 ref authors
                    for ps in pdf_surnames[:3]:   # against first 3 pdf authors
                        s = difflib.SequenceMatcher(None, rs, ps).ratio()
                        if s > author_sim:
                            author_sim = s
            else:
                author_sim = 0.0

            # Year match (weight 0.15)
            year_sim = 1.0 if (ref_year and pdf_year and ref_year == pdf_year) else 0.0

            composite = title_sim * 0.60 + author_sim * 0.25 + year_sim * 0.15

            if composite > best_score:
                best_score = composite
                best_pi = pi
                parts = []
                if title_sim >= 0.5:
                    parts.append(f"Title ({title_sim:.0%})")
                if author_sim >= 0.5:
                    parts.append(f"Author ({author_sim:.0%})")
                if year_sim > 0:
                    parts.append("Year")
                best_reason = " + ".join(parts) if parts else "Low similarity"

        if best_score >= threshold and best_pi >= 0:
            used_pdfs.add(best_pi)
            matched.append({
                "ref_index": ri,
                "ref_text": ref_text,
                "pdf_filename": pdf_metadatas[best_pi].get("_filename", f"PDF #{best_pi + 1}"),
                "confidence": round(best_score, 3),
                "match_reason": best_reason,
                "ref_metadata": {k: v for k, v in ref.items() if k != "_original"},
                "pdf_metadata": {k: v for k, v in pdf_metadatas[best_pi].items() if k != "_original"},
            })
        else:
            missing.append({
                "ref_index": ri,
                "ref_text": ref_text,
                "best_candidate": pdf_metadatas[best_pi].get("_filename") if best_pi >= 0 else None,
                "best_score": round(best_score, 3) if best_pi >= 0 else 0,
            })

    return {"matched": matched, "missing": missing}
