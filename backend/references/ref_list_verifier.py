"""
Reference List Verifier — verifies a list of references for metadata accuracy
(via CrossRef / PubMed APIs) and formatting correctness (against style rules).

Reuses the existing infrastructure:
  - references.metadata.perform_pubmed_lookup / perform_crossref_lookup
  - references.matcher.parse_raw_reference_fast, parse_reference_list
  - citations.formatting.format_reference
  - citations.detection.detect_style_from_references, classify_single_reference
"""
import re
import difflib
from typing import List, Optional

from references.metadata import perform_pubmed_lookup, perform_crossref_lookup
from references.matcher import parse_raw_reference_fast, parse_reference_list
from citations.formatting import format_reference
from citations.detection import detect_style_from_references, classify_single_reference


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
