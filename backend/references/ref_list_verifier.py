"""
Reference List Verifier — verifies a list of references for metadata accuracy
(via CrossRef / PubMed APIs) and formatting correctness (against style rules).

Reuses the existing infrastructure:
  - references.metadata.perform_pubmed_lookup / perform_crossref_lookup
  - references.matcher.parse_raw_reference_fast, parse_reference_list
  - citations.formatting.format_reference
  - citations.detection.detect_style_from_references, classify_single_reference
"""
import os
import re
import regex as re_u
import json
import difflib
import logging
from typing import List, Optional

from google.genai import types as genai_types
from core.gemini import get_client, _try_model_with_retries

from references.metadata import perform_pubmed_lookup, perform_crossref_lookup
from references.matcher import parse_raw_reference_fast, parse_reference_list
from citations.formatting import format_reference
from citations.detection import detect_style_from_references, classify_single_reference

logger = logging.getLogger(__name__)


# ─── Style auto-detection ────────────────────────────────────────────────────

def detect_style(references: List[str]) -> dict:
    """
    Auto-detect the citation style from a list of reference strings.
    Wraps the existing detect_style_from_references from citations.detection.
    Returns { style, confidence, evidence, all_scores }.
    """
    return detect_style_from_references(references)


# ─── Single-reference verification ──────────────────────────────────────────

def _fuzzy_match(a: str, b: str, threshold: float = 0.80) -> tuple:
    """Return (is_match: bool, ratio: float) comparing two strings."""
    if not a or not b:
        return (False, 0.0)
    a_clean = re.sub(r'\s+', ' ', a.strip().lower())
    b_clean = re.sub(r'\s+', ' ', b.strip().lower())
    if a_clean == b_clean:
        return (True, 1.0)
    ratio = difflib.SequenceMatcher(None, a_clean, b_clean).ratio()
    return (ratio >= threshold, ratio)


def _compare_authors(user_authors, api_authors) -> dict:
    """
    Compare user-supplied author string/list against API-verified authors.
    Returns { status, detail, user_value, correct_value }.
    Only requires the first author surname to match, gracefully handling 'et al.' truncations.
    """
    if not api_authors:
        return {"status": "skipped", "detail": "API did not return authors"}

    # Normalise both to lists
    def to_list(val):
        if isinstance(val, list):
            return val
        if not val:
            return []
        if '; ' in val:
            return [a.strip() for a in val.split(';') if a.strip()]
        return [val.strip()]

    user_list = to_list(user_authors)
    api_list = to_list(api_authors)

    if not user_list:
        return {
            "status": "missing",
            "detail": "No authors found in user reference",
            "user_value": "",
            "correct_value": "; ".join(api_list),
        }

    # Compare first-author surname
    def first_surname(name):
        parts = re.split(r'[,\s]', name.strip())
        return parts[0].lower().rstrip('.') if parts else ""

    user_first = first_surname(user_list[0])
    api_first = first_surname(api_list[0])

    surname_match, surname_ratio = _fuzzy_match(user_first, api_first, 0.85)

    if surname_match:
        return {
            "status": "correct",
            "detail": f"First author matches ({api_first.capitalize()})",
            "user_value": "; ".join(user_list),
            "correct_value": "; ".join(api_list),
        }
    else:
        return {
            "status": "incorrect",
            "detail": f"First author mismatch: '{user_first}' vs '{api_first}' (similarity {surname_ratio:.0%})",
            "user_value": "; ".join(user_list),
            "correct_value": "; ".join(api_list),
        }


def _compare_field(field_name: str, user_val, api_val, threshold=0.80, original_ref: str = "") -> Optional[dict]:
    """
    Compare a single metadata field. Returns a dict describing the comparison,
    or None if there's nothing meaningful to compare.
    """
    import re
    if not api_val:
        # Return 'unavailable' so the UI can show "could not verify" instead of silently skipping
        return {"field": field_name, "status": "unavailable", "user_value": str(user_val).strip() if user_val else "", "correct_value": ""}

    user_str = str(user_val).strip() if user_val else ""
    api_str = str(api_val).strip()

    if not user_str:
        if original_ref:
            # Fallback: check if the correct API value literally exists in the raw reference text.
            # This covers cases where our regex extractor failed to split the string properly.
            a_clean = api_str.replace('–', '-').replace('—', '-')
            o_clean = original_ref.replace('–', '-').replace('—', '-')
            
            if field_name in ("year", "volume", "issue", "pages"):
                if re.search(r'\b' + re.escape(a_clean) + r'\b', o_clean, re.IGNORECASE):
                    return {"field": field_name, "status": "correct", "user_value": a_clean, "correct_value": api_str}
            else:
                if len(a_clean) > 4 and a_clean.lower() in o_clean.lower():
                    return {"field": field_name, "status": "correct", "user_value": a_clean, "correct_value": api_str}
                # Relaxed source check: maybe the API has "The Lancet. Global health" but text has "The Lancet Global health"
                elif field_name == "source" and len(a_clean) > 5:
                    a_words = [w for w in re.split(r'\W+', a_clean.lower()) if len(w) > 3]
                    o_words = [w for w in re.split(r'\W+', o_clean.lower()) if len(w) > 3]
                    if a_words and all(w in o_words for w in a_words):
                        return {"field": field_name, "status": "correct", "user_value": a_clean, "correct_value": api_str}

        return {
            "field": field_name,
            "status": "missing",
            "user_value": "",
            "correct_value": api_str,
        }

    # For year, volume, issue, pages — exact match
    if field_name in ("year", "volume", "issue", "pages"):
        # Normalise hyphens for pages
        u = user_str.replace('–', '-').replace('—', '-')
        a = api_str.replace('–', '-').replace('—', '-')
        if u == a:
            return {"field": field_name, "status": "correct", "user_value": user_str, "correct_value": api_str}
    else:
        # For title, source — fuzzy match
        is_match, ratio = _fuzzy_match(user_str, api_str, threshold)
        if is_match:
            return {"field": field_name, "status": "correct", "user_value": user_str, "correct_value": api_str}

    # Final Fallback: if we haven't returned correct, but we have original_ref, check if the api_str
    # literally exists unmodified in the text. This saves us from regex garbage extractions.
    if original_ref:
        a_clean = api_str.replace('–', '-').replace('—', '-')
        o_clean = original_ref.replace('–', '-').replace('—', '-')
        
        if field_name in ("year", "volume", "issue", "pages"):
            # For pages, strip DOIs/URLs first so page values don't match inside DOI strings
            if field_name == "pages":
                o_clean = re.sub(r'(?:doi[:\s]*|https?://\S+|10\.\d{4,}/\S+)', '', o_clean, flags=re.IGNORECASE)
            if re.search(r'\b' + re.escape(a_clean) + r'\b', o_clean, re.IGNORECASE):
                return {"field": field_name, "status": "correct", "user_value": a_clean, "correct_value": api_str}
        else:
            if len(a_clean) > 4 and a_clean.lower() in o_clean.lower():
                return {"field": field_name, "status": "correct", "user_value": a_clean, "correct_value": api_str}
            # Relaxed source / title check:
            elif len(a_clean) > 5:
                # remove punctuation, check tokens
                a_words = [w for w in re.split(r'\W+', a_clean.lower()) if len(w) > 3]
                o_words = [w for w in re.split(r'\W+', o_clean.lower()) if len(w) > 3]
                if a_words and all(w in o_words for w in a_words):
                    return {"field": field_name, "status": "correct", "user_value": a_clean, "correct_value": api_str}

    # If we still failed
    return {"field": field_name, "status": "incorrect", "user_value": user_str, "correct_value": api_str}


def _detect_formatting_issues(original_ref: str, correct_ref: str, style: str) -> list:
    """
    Compare the user's original reference against the correctly formatted version
    and identify specific formatting issues.
    """
    issues = []

    # 1. Year placement
    if style in ("harvard", "apa"):
        # Should have (YYYY) format
        user_year_paren = bool(re.search(r'\(\d{4}[a-z]?\)', original_ref))
        correct_year_paren = bool(re.search(r'\(\d{4}[a-z]?\)', correct_ref))
        if correct_year_paren and not user_year_paren:
            issues.append({
                "issue": "year_format",
                "detail": f"{style.upper()} requires year in parentheses: (YYYY).",
            })
    elif style == "vancouver":
        # Year should NOT be in parentheses
        user_year_paren = bool(re.search(r'\(\d{4}\)', original_ref))
        if user_year_paren:
            issues.append({
                "issue": "year_format",
                "detail": "Vancouver does not use parentheses around the year.",
            })

    # 2. Author format
    if style == "vancouver":
        # Should use "Surname AB" format (no commas between surname and initials, no periods in initials)
        vanc_author_ok = bool(re.search(
            r'^(?:\[\d+\]\s*|\d+\.\s*)?[A-Z][a-zA-Z\'\-]+\s+[A-Z]{1,3}[,.]',
            original_ref
        ))
        apa_author_present = bool(re.search(r'[A-Z][a-z]+,\s+[A-Z]\.', original_ref))
        if apa_author_present and not vanc_author_ok:
            issues.append({
                "issue": "author_format",
                "detail": "Vancouver requires 'Surname AB' format (no comma, no periods in initials).",
            })
    elif style in ("harvard", "apa"):
        # Should use "Surname, I." format
        apa_author_present = bool(re.search(r'[A-Z][a-z]+,\s+[A-Z]\.', original_ref))
        if not apa_author_present:
            vanc_author = bool(re.search(r'[A-Z][a-z]+\s+[A-Z]{1,3}[,.]', original_ref))
            if vanc_author:
                issues.append({
                    "issue": "author_format",
                    "detail": f"{style.upper()} requires 'Surname, I.' format (comma after surname, periods in initials).",
                })

    # 3. Title casing (APA uses sentence case for article titles)
    if style == "apa":
        # Check if title looks like Title Case when it should be sentence case
        year_match = re.search(r'\(\d{4}[a-z]?\)\.\s+', original_ref)
        if year_match:
            after_year = original_ref[year_match.end():]
            title_match = re.match(r'([^.]+)\.', after_year)
            if title_match:
                title = title_match.group(1)
                words = title.split()
                if len(words) > 3:
                    capitalised = sum(1 for w in words[1:] if w[0].isupper() and not re.match(r'^[A-Z]{2,}$', w))
                    if capitalised > len(words) * 0.5:
                        issues.append({
                            "issue": "title_case",
                            "detail": "APA requires sentence case for article titles (only first word and proper nouns capitalised).",
                        })

    # 4. Harvard title quotes
    if style == "harvard":
        has_quotes = bool(re.search(r"'[A-Z][^']+?'", original_ref))
        if not has_quotes:
            # Check if this is a journal article reference (has volume/issue)
            looks_like_journal = bool(re.search(r'\d+\(\d+\)', original_ref))
            if looks_like_journal:
                issues.append({
                    "issue": "title_quotes",
                    "detail": "Harvard requires article titles in single quotes: 'Title here'.",
                })

    # 5. DOI format
    doi_in_ref = re.search(r'(https?://doi\.org/\S+|doi:\s*\S+|DOI:\s*\S+)', original_ref)
    if doi_in_ref:
        if style == "apa":
            # APA: should be https://doi.org/xxx
            if not re.search(r'https://doi\.org/', original_ref):
                issues.append({
                    "issue": "doi_format",
                    "detail": "APA requires DOI as URL: https://doi.org/10.xxx",
                })
        elif style == "harvard":
            # Harvard: should be doi: https://doi.org/xxx
            if not re.search(r'doi:\s*https://doi\.org/', original_ref, re.IGNORECASE):
                issues.append({
                    "issue": "doi_format",
                    "detail": "Harvard uses: doi: https://doi.org/10.xxx",
                })
        elif style == "vancouver":
            # Vancouver: should be doi:10.xxx (compact, no URL prefix)
            if re.search(r'https://doi\.org/', original_ref):
                issues.append({
                    "issue": "doi_format",
                    "detail": "Vancouver uses compact DOI: doi:10.xxx (no URL prefix).",
                })

    # 6. Vancouver journal format: "Journal. YYYY;Vol(Issue):Pages."
    if style == "vancouver":
        has_vanc_journal = bool(re.search(r'\.\s*\d{4}\s*;\s*\d+\s*(?:\(\d+\))?\s*:\s*\d+', original_ref))
        has_apa_journal = bool(re.search(r',\s*\d+\(\d+\),\s*\d+', original_ref))
        if has_apa_journal and not has_vanc_journal:
            issues.append({
                "issue": "journal_format",
                "detail": "Vancouver requires 'Journal. YYYY;Vol(Issue):Pages.' format.",
            })

    # 7. Ampersand vs "and"
    if style == "apa":
        if ' and ' in original_ref.split('(')[0] if '(' in original_ref else original_ref:
            issues.append({
                "issue": "conjunction",
                "detail": "APA uses '&' between authors, not 'and'.",
            })
    elif style == "harvard":
        author_section = original_ref.split('(')[0] if '(' in original_ref else original_ref
        if ' & ' in author_section:
            issues.append({
                "issue": "conjunction",
                "detail": "Harvard uses 'and' between authors, not '&'.",
            })

    # 8. Incorrect p./pp. usage (Harvard & APA)
    if style in ("harvard", "apa"):
        # Find all occurrences of pp./p. followed by page values
        page_prefix_matches = re.finditer(r'\b(pp?)\.\s*([eE]?\d[\d\s,\-–—eE]*\d|[eE]?\d+)', original_ref)
        for m in page_prefix_matches:
            prefix = m.group(1)  # 'p' or 'pp'
            page_val = m.group(2)
            is_range = any(sep in page_val for sep in ('-', '–', '—', ','))
            if prefix == 'pp' and not is_range:
                issues.append({
                    "issue": "page_prefix",
                    "detail": f"Use 'p.' for a single page or article number ('{page_val}'), not 'pp.'.",
                })
                break
            elif prefix == 'p' and is_range:
                issues.append({
                    "issue": "page_prefix",
                    "detail": f"Use 'pp.' for page ranges ('{page_val}'), not 'p.'.",
                })
                break

    return issues


def verify_single_reference(original_ref: str, style: str) -> dict:
    """
    Verify a single reference string:
    1. Parse metadata via regex
    2. If DOI found, lookup via PubMed/CrossRef
    3. Compare metadata accuracy
    4. Generate correctly formatted reference
    5. Check formatting against style rules

    Returns a comprehensive result dict.
    """
    result = {
        "original": original_ref,
        "doi": None,
        "api_verified": False,
        "api_source": None,
        "metadata_issues": [],
        "formatting_issues": [],
        "corrected_reference": None,
        "corrected_reference_html": None,
        "overall_status": "unverifiable",
        "accuracy_score": 0.0,
        "ref_style_detected": None,
    }

    # Step 1: Parse metadata from the raw reference text
    parsed = parse_raw_reference_fast(original_ref)
    doi = parsed.get("doi")
    result["doi"] = doi

    # Classify this individual reference's style
    ref_style = classify_single_reference(original_ref)
    result["ref_style_detected"] = ref_style

    # Step 2: If DOI found, verify via API
    api_metadata = {
        "authors": None, "title": None, "year": None,
        "source": None, "doi": doi, "url": None,
        "volume": None, "issue": None, "pages": None,
        "publisher": None, "type": "Other",
    }
    field_sources = {}

    if doi:
        # Try PubMed first, then CrossRef (with one retry for transient failures)
        for attempt in range(2):
            if attempt > 0:
                import time
                time.sleep(2)  # Wait before retry to let rate limits cool down
                print(f"[RefVerifier] Retrying DOI lookup for {doi} (attempt {attempt + 1})")

            success = perform_pubmed_lookup(doi, api_metadata, field_sources)
            if success:
                result["api_verified"] = True
                result["api_source"] = "pubmed"
                # Supplement with CrossRef for any fields PubMed left empty
                # (e.g. pages for MDPI/open-access journals with DOI-only elocationids)
                missing_fields = [f for f in ("pages", "volume", "issue", "source") if not api_metadata.get(f)]
                if missing_fields:
                    cr_metadata = {k: None for k in api_metadata}
                    cr_sources = {}
                    if perform_crossref_lookup(doi, cr_metadata, cr_sources):
                        for field in missing_fields:
                            if cr_metadata.get(field):
                                api_metadata[field] = cr_metadata[field]
                                field_sources[field] = "crossref"
                break
            else:
                success = perform_crossref_lookup(doi, api_metadata, field_sources)
                if success:
                    result["api_verified"] = True
                    result["api_source"] = "crossref"
                    break

    if not result["api_verified"]:
        # Try searching CrossRef by title if we parsed one
        if parsed.get("title") and not doi:
            _try_title_search(parsed, api_metadata, field_sources, result)

    if not result["api_verified"]:
        result["overall_status"] = "unverifiable"
        result["accuracy_score"] = 0.0
        return result

    # Ensure authors is a list for api_metadata
    if isinstance(api_metadata.get("authors"), str):
        raw = api_metadata["authors"]
        if '; ' in raw:
            api_metadata["authors"] = [a.strip() for a in raw.split(';') if a.strip()]
        elif ' and ' in raw or ' & ' in raw:
            raw = raw.replace(' & ', ' and ')
            api_metadata["authors"] = [a.strip() for a in raw.split(' and ') if a.strip()]
        else:
            api_metadata["authors"] = [raw.strip()]

    # Step 3: Compare metadata accuracy
    metadata_issues = []
    scores = []

    # Authors
    author_result = _compare_authors(parsed.get("authors"), api_metadata.get("authors"))
    if author_result["status"] != "skipped":
        metadata_issues.append({"field": "authors", **author_result})
        scores.append(1.0 if author_result["status"] == "correct" else 0.0)

    # Title
    title_cmp = _compare_field("title", parsed.get("title"), api_metadata.get("title"), threshold=0.85, original_ref=original_ref)
    if title_cmp:
        metadata_issues.append(title_cmp)
        if title_cmp["status"] != "unavailable":
            scores.append(1.0 if title_cmp["status"] == "correct" else 0.0)

    # Year
    year_cmp = _compare_field("year", parsed.get("year"), api_metadata.get("year"), original_ref=original_ref)
    if year_cmp:
        metadata_issues.append(year_cmp)
        if year_cmp["status"] != "unavailable":
            scores.append(1.0 if year_cmp["status"] == "correct" else 0.0)

    # Source / Journal
    source_cmp = _compare_field("source", parsed.get("source"), api_metadata.get("source"), threshold=0.80, original_ref=original_ref)
    if source_cmp:
        metadata_issues.append(source_cmp)
        if source_cmp["status"] != "unavailable":
            scores.append(1.0 if source_cmp["status"] == "correct" else (0.5 if source_cmp["status"] == "missing" else 0.0))

    # Volume, Issue, Pages
    for field in ("volume", "issue", "pages"):
        cmp = _compare_field(field, parsed.get(field), api_metadata.get(field), original_ref=original_ref)
        if cmp:
            metadata_issues.append(cmp)
            if cmp["status"] != "unavailable":
                scores.append(1.0 if cmp["status"] == "correct" else 0.0)

    result["metadata_issues"] = metadata_issues
    result["accuracy_score"] = round(sum(scores) / max(len(scores), 1), 2)

    # Step 4: Generate the correctly formatted reference
    try:
        formatted = format_reference(api_metadata, style)
        result["corrected_reference"] = formatted.get("formatted")
        result["corrected_reference_html"] = formatted.get("formatted_html")
    except Exception as e:
        print(f"[RefVerifier] format_reference failed: {e}")

    # Step 5: Check formatting issues
    if result["corrected_reference"]:
        fmt_issues = _detect_formatting_issues(original_ref, result["corrected_reference"], style)
        result["formatting_issues"] = fmt_issues

    # Check if the reference's detected style matches the expected style
    if ref_style and ref_style != 'unknown' and ref_style != style:
        result["formatting_issues"].append({
            "issue": "wrong_style",
            "detail": f"Reference appears to be in {ref_style.upper()} style but {style.upper()} was expected.",
        })

    # Determine overall status
    has_metadata_issues = any(i["status"] == "incorrect" for i in metadata_issues)
    has_missing = any(i["status"] == "missing" for i in metadata_issues)
    has_formatting_issues = len(result["formatting_issues"]) > 0

    if not has_metadata_issues and not has_formatting_issues and not has_missing:
        result["overall_status"] = "verified"
    else:
        result["overall_status"] = "issues_found"

    return result


def _try_title_search(parsed: dict, api_metadata: dict, field_sources: dict, result: dict):
    """Attempt to find the reference via CrossRef title search if no DOI was found."""
    import urllib.parse
    import requests

    title = parsed.get("title", "")
    if not title or len(title) < 10:
        return

    try:
        title_encoded = urllib.parse.quote(title)
        url = f'https://api.crossref.org/works?query.bibliographic="{title_encoded}"&rows=3'
        resp = requests.get(url, timeout=10, headers={'User-Agent': 'WritingTools/1.0'})
        if resp.status_code != 200:
            return

        items = resp.json().get('message', {}).get('items', [])
        for item in items:
            cr_doi = item.get('DOI')
            if not cr_doi:
                continue

            cr_titles = item.get('title', [])
            cr_title = cr_titles[0] if cr_titles else ""

            if cr_title:
                t1 = "".join(c for c in title.lower() if c.isalnum() or c.isspace()).strip()
                t2 = "".join(c for c in cr_title.lower() if c.isalnum() or c.isspace()).strip()
                ratio = difflib.SequenceMatcher(None, t1, t2).ratio()
                if ratio < 0.85:
                    continue

            # Also verify year if available
            parsed_year = parsed.get("year")
            if parsed_year:
                cr_date = item.get('published-print', item.get('published-online', item.get('created', {})))
                if cr_date and 'date-parts' in cr_date:
                    cr_year = str(cr_date['date-parts'][0][0]) if cr_date['date-parts'][0] else None
                    if cr_year and cr_year != str(parsed_year):
                        continue

            # Found a match — do full lookup
            success = perform_pubmed_lookup(cr_doi, api_metadata, field_sources)
            if not success:
                success = perform_crossref_lookup(cr_doi, api_metadata, field_sources)
            if success:
                result["doi"] = cr_doi
                result["api_verified"] = True
                result["api_source"] = field_sources.get("doi", "crossref")
                return

    except Exception as e:
        print(f"[RefVerifier] Title search failed: {e}")


# ==============================================================================
# LOCAL REGEX ENGINE FALLBACK — Comprehensive Pattern Library (Zero-Cost)
# ==============================================================================
#
# Tiered confidence model:
#   Tier 1 — Numbered starters (near-certain reference boundary)
#   Tier 2 — Author-name starters (probabilistic, requires min-length guard)
#   Tier 3 — DOI / URL starters (contextual)
#   Tier 4 — Year-anchored fallback (last resort)
#
# Uses the `regex` module (pip install regex) for full Unicode \p{} support.
# ==============================================================================

# ── Unicode property shorthands (via `regex` module) ─────────────────────────
_U  = r'\p{Lu}'                  # any Unicode uppercase letter
_L  = r'\p{Ll}'                  # any Unicode lowercase letter
_A  = r'\p{L}'                   # any Unicode letter
_AH = r'[\p{L}\u2019\'\-]'       # letter, apostrophe, or hyphen

# ── Nobiliary / compound surname prefix ──────────────────────────────────────
_PARTICLE = (
    r'(?:'
        r'd[eo]\s(?:la\s|los?\s|las?\s)?'          # de, del, de la, de los
        r'|van\s(?:den?\s|der\s|het\s|\'t\s)?'      # Dutch: van, van de, van den, van der, van 't
        r'|von\s(?:der?\s)?'                         # German: von, von der
        r'|di\s|du\s'                                # French / Italian
        r'|le\s|la\s|les\s'                          # French
        r"|(?:O\u2019|O')(?=" + _U + r")"            # Irish O'Brien  (lookahead)
        r'|Mc(?=' + _U + r')'                        # Scottish Mc
        r'|Mac(?=' + _U + r')'                       # Scottish Mac
        r'|(?:al|el|Al|El)-(?=' + _U + r')'          # Arabic al-/el-
    r')'
)

# ── Tier 1: Numbered reference starters (high confidence) ────────────────────
_TIER1 = [
    re.compile(r'^\[\d{1,3}\]\s+\S'),                                   # [1] IEEE / Vancouver
    re.compile(r'^\d{1,3}\s*\.\s+\S'),                                  # 1. APA / MLA
    re.compile(r'^\(\d{1,3}\)\s+\S'),                                   # (1) legal / older
    re.compile(r'^[A-Z]\d{1,3}\.\s+\S'),                                # R1. regulatory
    re.compile(r'^[\u00B9\u00B2\u00B3\u2074-\u2079\u2070]+\s*\S'),      # ¹ ² ³ superscript OCR
]

# ── Tier 2: Author-name starters (medium confidence) ────────────────────────
_TIER2 = [
    # APA / Harvard / Chicago author-date:  Surname, F. (Year)  or  Surname, F. M. (Year)
    re_u.compile(
        r'^(?:' + _PARTICLE + r'\s*)?'
        + _U + _AH + r'{1,30}'
        + r',\s+'
        + _U + r'\.'
        + r'(?:\s*' + _U + r'\.)*'
        + r'\s*\(\d{4}',
        re_u.UNICODE
    ),
    # APA / Harvard without year in parens:  Surname, F.  or  Surname, F. M.,
    re_u.compile(
        r'^(?:' + _PARTICLE + r'\s*)?'
        + _U + _AH + r'{1,30}'
        + r',\s+'
        + _U + r'\.'
        + r'(?:\s*' + _U + r'\.)*'
        + r'[\s,]',
        re_u.UNICODE
    ),
    # Vancouver / AMA / NLM:  Surname AB.  or  Surname AB,
    re_u.compile(
        r'^(?:' + _PARTICLE + r'\s*)?'
        + _U + _AH + r'{1,30}'
        + r'\s+'
        + r'[A-Z]{1,4}'
        + r'[,.]',
        re_u.UNICODE
    ),
    # MLA / Chicago:  Surname, First.  (full first name, ≥3 chars to avoid initials)
    re_u.compile(
        r'^(?:' + _PARTICLE + r'\s*)?'
        + _U + _AH + r'{1,30}'
        + r',\s+'
        + _U + _L + r'{2,15}'
        + r'(?:\s+' + _U + _L + r'{2,15})*'
        + r'\.',
        re_u.UNICODE
    ),
    # IEEE initial-first:  F. Surname,  or  W.-K. Chen,  or  A. B. García,
    re_u.compile(
        r'^' + _U + r'(?:\.-' + _U + r')?\.(?:\s*' + _U + r'\.)*'
        + r'\s+'
        + _U + _AH + r'{1,30}'
        + r'[,\s]',
        re_u.UNICODE
    ),
    # et al. shorthand:  Smith et al.  /  García et al,
    re_u.compile(
        r'^(?:' + _PARTICLE + r'\s*)?'
        + _U + _AH + r'{1,30}'
        + r'\s+et\s+al[.,\s]',
        re_u.UNICODE
    ),
    # Standalone compound-surname start:  de la Cruz, ...  /  van der Berg, ...
    re_u.compile(
        r'^' + _PARTICLE + _U + _AH + r'{1,30}'
        + r'[,\s]',
        re_u.UNICODE
    ),
    # Corporate / institutional / government authors:
    #   "World Health Organization. (2022)."  or  "WHO (2023)."
    re_u.compile(
        r'^(?:'
            + _U + _A + r'[\s' + _A + r'\-&]{5,60}\.'       # multi-word org ending in period
            + r'|[A-Z]{2,8}\s+[\(\d]'                        # acronym org (WHO, CDC) + year/paren
            + r'|' + _U + _A + r'+\s+(?:of|for|on|in|and)\s+' + _U  # "Institute of X"
        + r')',
        re_u.UNICODE
    ),
]

# ── Tier 3: DOI / URL starters (contextual) ─────────────────────────────────
_TIER3 = [
    re.compile(r'^doi:\s*10\.', re.IGNORECASE),          # doi: 10.xxxx
    re.compile(r'^10\.\d{4,}/',  re.IGNORECASE),         # bare DOI  10.xxxx/
    re.compile(r'^https?://'),                             # https://...
    re.compile(r'^www\.\S'),                               # www.example.com
]

# ── Tier 4: Year-anchored last resort ───────────────────────────────────────
_TIER4 = re.compile(
    r'^.{5,60}'                        # some non-empty prefix (title / org)
    r'[\.\s,]\s*'
    r'(?:\()?\d{4}[a-z]?(?:\))?'       # (2020) or 2020 or 2020a
    r'[\.,:;\s]'
)

# ── Continuation-line detectors ──────────────────────────────────────────────
_CONT_INDENT = re.compile(r'^\s{3,}')
_CONT_LOWER  = re_u.compile(r'^\s*\p{Ll}')
_CONT_WORD   = re.compile(
    r'^\s*(?:and|or|in|of|for|the|a|an|with|on|at|by|from|to|into|as)\s',
    re.IGNORECASE,
)


def _preprocess_line(line: str) -> str:
    """Normalise a pasted reference line before pattern matching."""
    # Remove markdown emphasis artefacts ( _text_ / *text* / **text** )
    line = re.sub(r'[_*]{1,2}(.+?)[_*]{1,2}', r'\1', line)
    # Normalise en-/em-dashes to ASCII hyphen for name matching
    line = line.replace('\u2013', '-').replace('\u2014', '-')
    # Collapse multiple spaces
    line = re.sub(r'  +', ' ', line)
    # Strip zero-width spaces and other invisible Unicode
    line = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', line)
    # Normalise smart apostrophes (O\u2019Brien → O'Brien)
    line = line.replace('\u2018', "'").replace('\u2019', "'")
    return line.strip()


def _detect_paste_style(sample_lines: List[str]) -> str:
    """
    Identify the dominant citation style from the first few lines to choose the
    optimal Tier-2 pattern set.  Returns 'numbered', 'apa', 'vancouver', 'ieee',
    or 'unknown'.
    """
    numbered = sum(1 for l in sample_lines if re.match(r'^\[\d+\]|^\d+\.', l.strip()))
    apa      = sum(1 for l in sample_lines if re_u.search(
        r',\s+' + _U + r'\.\s*\(\d{4}', l))
    van      = sum(1 for l in sample_lines if re_u.search(
        _U + _AH + r'+\s+[A-Z]{2,4}[,.]', l))
    ieee     = sum(1 for l in sample_lines if re_u.match(
        r'^' + _U + r'\.\s+' + _U, l))

    scores = {'numbered': numbered, 'apa': apa, 'vancouver': van, 'ieee': ieee}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else 'unknown'


def _is_continuation(line: str) -> bool:
    """Return True if `line` is definitely a continuation of the previous ref."""
    stripped = line.strip()
    if len(stripped) < 15:
        return True
    if _CONT_INDENT.match(line):      # ≥3 leading spaces (hanging indent)
        return True
    # Check lowercase ONLY if it's not a compound-surname particle start
    if _CONT_LOWER.match(stripped):
        # Exempt nobiliary particles that legitimately start references
        if not re.match(
            r'^(?:d[eo]\s|van\s|von\s|di\s|du\s|le\s|la\s|les\s|al-|el-)',
            stripped, re.IGNORECASE
        ):
            return True
    if _CONT_WORD.match(stripped):     # starts with conjunction/preposition
        # Also exempt particle surnames from the conjunction check
        if not re.match(
            r'^(?:d[eo]\s|van\s|von\s|di\s|du\s|le\s|la\s|les\s)',
            stripped, re.IGNORECASE
        ):
            return True
    return False


def _is_reference_start(line: str, min_length: int = 20) -> bool:
    """
    Return True if `line` is likely the start of a new reference entry.
    Checks tiers in order; returns on first match.
    """
    stripped = line.strip()
    if len(stripped) < min_length:
        return False

    # Tier 1: numbered — near-certain
    for pat in _TIER1:
        if pat.match(stripped):
            return True

    # Tier 2: author-name — probabilistic; require ≥ 25 chars
    if len(stripped) >= 25:
        for pat in _TIER2:
            if pat.match(stripped):
                return True

    # Tier 3: URL / DOI lines — require ≥ 20 chars
    if len(stripped) >= 20:
        for pat in _TIER3:
            if pat.match(stripped):
                return True

    return False


def split_and_heal_verifier_text_fallback(raw_text: str) -> List[str]:
    """
    COMPREHENSIVE REGEX FALLBACK: Invoked immediately if the Gemini API fails,
    times out, or suffers an authentication error.

    Uses a 4-tier confidence model with 30+ patterns covering:
      - Numbered styles (IEEE, Vancouver, APA, MLA, legal, superscript OCR)
      - Author-name styles (APA, Harvard, Vancouver, MLA, Chicago, IEEE, CSE)
      - Unicode surnames, compound/particle surnames, corporate authors
      - DOI and URL-only references
      - Continuation-line detection (indent, lowercase, conjunctions)
      - Markdown / paste artefact pre-processing
    """
    raw_lines = [l for l in raw_text.splitlines() if l.strip()]
    if not raw_lines:
        return []

    # Pre-process all lines
    processed = [_preprocess_line(l) for l in raw_lines]
    processed = [l for l in processed if l]  # drop empties after cleanup

    # Detect dominant style for logging (not currently used for gating)
    sample = processed[:min(8, len(processed))]
    detected_style = _detect_paste_style(sample)
    logger.debug(f"[RegexFallback] detected paste style: {detected_style}")

    healed_references: List[str] = []
    current_buffer: List[str] = []

    for line in processed:
        # Explicit continuations are always appended
        if current_buffer and _is_continuation(line):
            current_buffer.append(line)
            continue

        is_new = _is_reference_start(line)

        # Guard: very short lines that matched a Tier-2 pattern are suspect
        if is_new and len(line) < 15 and not re.match(r'^\[\d+\]|^\d+\.', line):
            is_new = False

        if is_new:
            if current_buffer:
                healed_references.append(' '.join(current_buffer))
            current_buffer = [line]
        else:
            current_buffer.append(line)

    # Flush last buffer
    if current_buffer:
        healed_references.append(' '.join(current_buffer))

    # Final cleanup: collapse whitespace, drop noise lines
    return [re.sub(r'\s+', ' ', c).strip()
            for c in healed_references
            if len(re.sub(r'\s+', ' ', c).strip()) > 15]


# ==============================================================================
# GEMINI LITE-PREVIEW SPLITTING ENGINE
# ==============================================================================

def _extract_ref_section_with_llm_sync(full_text: str) -> str:
    """
    Use Gemini synchronously to find the start of the reference section.
    Slices the document to just the reference section and returns it.
    """
    if not full_text or not full_text.strip():
        return full_text

    # Take the last 100,000 characters as a window since references are at the end
    slice_window = 100000
    offset = max(0, len(full_text) - slice_window)
    text_to_analyze = full_text[offset:]

    prompt = f"""You are an expert academic bibliography assistant.
I will provide the end portion of an academic document. This document contains a body of text with in-text citations, and a reference list section (usually located at the end under a heading such as "References", "Bibliography", "Reference List", or "Works Cited").

Your job is to identify the EXACT starting text of the reference list section. This can be the heading itself (e.g., "References") or the first few words of the very first reference entry.

Provide a JSON object with:
1. "start_text": a string containing the exact first 50-80 characters of the first reference or the references heading itself, exactly as it appears in the text. This must match the original text character-for-character, including spacing and punctuation, so we can locate it with a .find() search.
2. "heading_found": a boolean indicating if a reference section heading was found.
3. "confidence": a float between 0 and 1.

Example output:
{{
  "start_text": "References\\n\\nAdams, R. (2018)",
  "heading_found": true,
  "confidence": 0.95
}}

Document Text Segment:
\"\"\"
{text_to_analyze}
\"\"\"
"""
    try:
        model_name = "gemini-3.1-flash-lite-preview"
        client = get_client(model=model_name)
        config = genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1
        )
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config
        )
        response_text = response.text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]

        data = json.loads(response_text.strip())
        start_text = data.get("start_text", "").strip()
        if start_text:
            idx = text_to_analyze.find(start_text)
            if idx >= 0:
                logger.info(f"Gemini located reference section start via LLM at window offset {idx}.")
                return full_text[offset + idx:]
            
            # Fuzzy fallback
            norm_start = ' '.join(start_text.split()).lower()
            if len(norm_start) > 10:
                norm_doc = ' '.join(text_to_analyze.split()).lower()
                doc_idx = norm_doc.find(norm_start)
                if doc_idx >= 0:
                    words = start_text.split()
                    first_word = words[0]
                    last_word = words[-1] if len(words) > 1 else words[0]
                    matches = [m.start() for m in re.finditer(re.escape(first_word), text_to_analyze, re.IGNORECASE)]
                    for m_start in matches:
                        sub = text_to_analyze[m_start:m_start + len(start_text) + 20]
                        if last_word.lower() in sub.lower():
                            logger.info(f"Gemini located reference section start via fuzzy word matching at window offset {m_start}.")
                            return full_text[offset + m_start:]
    except Exception as e:
        logger.error(f"Gemini reference section locator failed: {e}", exc_info=True)

    return full_text


def _extract_ref_section_simple(full_text: str) -> str:
    """
    Isolate the reference section from a full academic document using heading
    patterns.  Returns just the reference section text, or uses Gemini as fallback
    to determine the beginning of the reference section.
    """
    patterns = [
        r'(?i)\n\s*(references?|bibliography|works\s+cited|reference\s+list)\s*\n',
        r'(?im)^\s*(references?|bibliography|works\s+cited|reference\s+list)\s*$',
        r'(?i)^\s*(references?|bibliography|works\s+cited|reference\s+list)\s*\n',
        r'(?i)\n\s*(references?|bibliography|works\s+cited|reference\s+list)\s*(?=\S)',
    ]
    for pattern in patterns:
        match = re.search(pattern, full_text)
        if match:
            return full_text[match.end():]
            
    # If no heading pattern is found, use Gemini to determine the beginning of the reference section.
    return _extract_ref_section_with_llm_sync(full_text)



async def segment_verifier_text_via_llm(
    raw_text: str,
    is_full_document: bool = False,
) -> List[str]:
    """
    VARIABLE-COST MACHINE LEARNING SEGMENTER: Uses Gemini 3.1 Flash Lite
    via structured JSON to split references into pristine individual entries.

    When `is_full_document=True`, the LLM receives the entire academic
    document and is instructed to locate the reference section itself,
    then extract and split individual references from it.

    When `is_full_document=False` (default), the input is assumed to be
    raw copy-pasted reference text only.

    On any failure, falls back to the 30+ pattern regex engine.
    """
    if not raw_text or not raw_text.strip():
        return []

    # ── Build the appropriate prompt ──────────────────────────────────────
    if is_full_document:
        prompt = f"""You are an expert academic bibliography assistant.

I will provide the FULL TEXT of an academic document (essay, dissertation, thesis, or paper). This document contains a body of text with in-text citations, and a reference list section — usually located at the end under a heading such as "References", "Bibliography", "Reference List", or "Works Cited".

Your job is to:
1. LOCATE the reference list section in the document. Ignore the body text, abstracts, appendices, and any other non-reference content.
2. Extract each individual reference entry from that section as a COMPLETE, UNTRUNCATED string.
3. Stitch lines that were accidentally broken by page breaks, column layouts, or clipboard copying back together into single continuous reference strings.
4. Clean up layout artefacts (page numbers, headers/footers, column breaks) while leaving the reference content intact.
5. Do NOT invent, modify, or paraphrase any reference — extract them VERBATIM as written.

CRITICAL: Do NOT truncate references. Copy each reference VERBATIM from start to finish — include everything that appears in the original text. A typical complete reference includes some or all of these parts:
- Author names and year
- Article/chapter title
- Journal name, book title, or publisher (if present in original)
- Volume, issue, and page numbers (if present in original)
- DOI or URL (if present in original)
Not every reference will have all of these parts — that is fine. Just extract whatever IS there. Do NOT invent or add fields that are missing from the original.

Example of CORRECT extraction (full reference copied verbatim):
"Smith, J., & Jones, A. (2024). Example study title. Journal of Examples, 19(4), e0292983. https://doi.org/10.1371/journal.example.0292983"

Example of WRONG extraction (reference truncated after title):
"Smith, J., & Jones, A. (2024). Example study title."

Full Document Text:
\"\"\"
{raw_text}
\"\"\"

Return a JSON object containing an array of strings under the key "references".
Each string must be one COMPLETE, self-contained reference entry with ALL fields intact.
Do NOT include body text, section headings, page numbers, or appendix content."""
    else:
        prompt = f"""You are an expert academic bibliography assistant.
I will provide a block of raw copy-pasted academic references. This text contains messy layout artifacts, accidental line wraps, and broken sentences introduced by clipboard copying.

Your job is to:
1. Identify individual references.
2. Stitch lines that were accidentally broken back together into a single continuous reference string.
3. Separate distinct reference items clearly.
4. Clean up unnecessary dangling pagination fragments or layout noise while leaving the content of the reference intact.

Input Reference Text:
\"\"\"
{raw_text}
\"\"\"

Return a JSON object containing an array of strings under the key "references".
Ensure each reference string is completely self-contained and fully healed from structural row splits."""

    # ── Call Gemini ───────────────────────────────────────────────────────
    try:
        model_name = "gemini-3.1-flash-lite-preview"
        client = get_client(model=model_name)

        # Enforce JSON-mode via schema config
        config = genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1  # Lock down low creativity for high deterministic output
        )

        async def dummy_progress(msg):
            logger.debug(f"[LLM-Splitter] {msg}")

        # Execute Gemini transaction using the existing client wrapper infrastructure
        response, _ = await _try_model_with_retries(
            client=client,
            prompt=prompt,
            model=model_name,
            config=config,
            max_retries=3,
            progress_callback=dummy_progress,
            rotate_keys=True
        )

        response_text = response.text.strip()

        # Strip markdown syntax guardrails if generated by accident
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]

        data = json.loads(response_text.strip())
        references = data.get("references", [])

        if isinstance(references, list) and len(references) > 0:
            logger.info(f"Successfully segmented {len(references)} records using Gemini.")
            return [str(ref).strip() for ref in references if str(ref).strip()]

    except Exception as exc:
        logger.error(f"Gemini reference splitting failed: {exc}. Falling back to regex engine.", exc_info=True)

    # ── Regex fallback ────────────────────────────────────────────────────
    # For full documents, isolate the reference section first so the regex
    # engine doesn't try to split body text as references.
    if is_full_document:
        ref_section = _extract_ref_section_simple(raw_text)
        return split_and_heal_verifier_text_fallback(ref_section)
    else:
        return split_and_heal_verifier_text_fallback(raw_text)

