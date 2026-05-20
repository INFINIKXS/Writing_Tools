"""
Raw reference text parser: deterministic DOI-first pipeline.
No AI — uses PubMed/Crossref APIs for authoritative metadata,
regex for everything else.
"""
import re
import difflib
from typing import List, Optional

from pydantic import BaseModel

from references.metadata import perform_pubmed_lookup, perform_crossref_lookup
from references.matcher import parse_raw_reference_fast
from utils.text_utils import classify_source_type


class FormatRequest(BaseModel):
    references: List[str]
    style: str = "harvard"


# ─── Correction detection ────────────────────────────────────────────────────

def _detect_corrections(user_parsed: dict, api_metadata: dict, original_ref: str) -> list:
    """
    Compare user's original reference text against API-verified metadata.
    Returns a list of corrections: [{"field": ..., "user_value": ..., "correct_value": ..., "detail": ...}]
    """
    corrections = []

    # Year
    user_year = user_parsed.get("year")
    api_year = api_metadata.get("year")
    if user_year and api_year and str(user_year) != str(api_year):
        corrections.append({
            "field": "year",
            "user_value": str(user_year),
            "correct_value": str(api_year),
            "detail": f"Publication year is {api_year}, not {user_year}.",
        })

    # Title
    user_title = user_parsed.get("title")
    api_title = api_metadata.get("title")
    if user_title and api_title:
        t1 = re.sub(r'[^\w\s]', '', user_title.lower()).strip()
        t2 = re.sub(r'[^\w\s]', '', api_title.lower()).strip()
        # If the API title is a substring of the user-parsed title (or vice versa),
        # it means the regex just grabbed extra text — not a real user error.
        if t2 in t1 or t1 in t2:
            pass  # Not a real correction
        else:
            ratio = difflib.SequenceMatcher(None, t1, t2).ratio()
            if 0.5 < ratio < 0.95:
                corrections.append({
                    "field": "title",
                    "user_value": user_title,
                    "correct_value": api_title,
                    "detail": f"Title differs from the published version ({ratio:.0%} match).",
                })

    # Authors (first-author surname check)
    user_authors = user_parsed.get("authors")
    api_authors = api_metadata.get("authors")
    if user_authors and api_authors:
        def first_surname(val):
            if isinstance(val, list):
                val = val[0] if val else ""
            return re.split(r'[,\s]', str(val).strip())[0].lower().rstrip('.')

        u_first = first_surname(user_authors)
        a_first = first_surname(api_authors)
        if u_first and a_first:
            surname_ratio = difflib.SequenceMatcher(None, u_first, a_first).ratio()
            if 0.5 < surname_ratio < 1.0:
                corrections.append({
                    "field": "authors",
                    "user_value": u_first.capitalize(),
                    "correct_value": a_first.capitalize(),
                    "detail": f"First author surname: '{u_first.capitalize()}' → '{a_first.capitalize()}'.",
                })

    # Volume
    user_vol = user_parsed.get("volume")
    api_vol = api_metadata.get("volume")
    if user_vol and api_vol and str(user_vol) != str(api_vol):
        corrections.append({
            "field": "volume",
            "user_value": str(user_vol),
            "correct_value": str(api_vol),
            "detail": f"Volume is {api_vol}, not {user_vol}.",
        })

    # Issue
    user_issue = user_parsed.get("issue")
    api_issue = api_metadata.get("issue")
    if user_issue and api_issue and str(user_issue) != str(api_issue):
        corrections.append({
            "field": "issue",
            "user_value": str(user_issue),
            "correct_value": str(api_issue),
            "detail": f"Issue is {api_issue}, not {user_issue}.",
        })

    # Pages
    user_pages = user_parsed.get("pages")
    api_pages = api_metadata.get("pages")
    if user_pages and api_pages:
        u_norm = str(user_pages).replace('–', '-').replace('—', '-')
        a_norm = str(api_pages).replace('–', '-').replace('—', '-')
        if u_norm != a_norm:
            corrections.append({
                "field": "pages",
                "user_value": str(user_pages),
                "correct_value": str(api_pages),
                "detail": f"Pages: {api_pages}, not {user_pages}.",
            })

    return corrections


# ─── Title search fallback ───────────────────────────────────────────────────

def _try_title_search_for_doi(parsed: dict) -> Optional[str]:
    """
    Search Crossref by title to find a DOI when none was provided.
    Returns a DOI string if a confident match is found, else None.
    """
    import urllib.parse
    import requests

    title = parsed.get("title", "")
    if not title or len(title) < 10:
        return None

    try:
        title_encoded = urllib.parse.quote(title)
        url = f'https://api.crossref.org/works?query.bibliographic="{title_encoded}"&rows=3'
        resp = requests.get(url, timeout=10, headers={'User-Agent': 'WritingTools/1.0'})
        if resp.status_code != 200:
            return None

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

            return cr_doi

    except Exception as e:
        print(f"[Formatter] Title search failed: {e}")

    return None


# ─── Main parse function ─────────────────────────────────────────────────────

def parse_raw_reference(ref_text: str) -> dict:
    """
    Parse a raw reference string into structured metadata.
    Deterministic pipeline: Regex → DOI lookup → Title search → Regex fallback.

    Returns metadata dict with optional 'corrections' list and 'api_source' field.
    """
    # Step 1: Fast regex extraction (DOI, year, vol, issue, pages, authors, title)
    parsed = parse_raw_reference_fast(ref_text)

    metadata = {
        "authors": None, "title": None, "year": None,
        "source": None, "doi": None, "url": None,
        "volume": None, "issue": None, "pages": None,
        "publisher": None, "type": "Other",
    }
    field_sources = {}

    # Copy regex-extracted DOI
    doi = parsed.get("doi")
    if doi:
        metadata["doi"] = doi
        field_sources["doi"] = "text_parsing"

    # Step 2: If DOI found, fetch authoritative metadata from PubMed/Crossref
    api_success = False
    api_source = None

    if doi:
        api_metadata = {
            "authors": None, "title": None, "year": None,
            "source": None, "doi": doi, "url": None,
            "volume": None, "issue": None, "pages": None,
            "publisher": None, "type": "Other",
        }
        api_sources = {}

        api_success = perform_pubmed_lookup(doi, api_metadata, api_sources)
        if api_success:
            api_source = "pubmed"
            # Supplement with Crossref for any fields PubMed left empty
            missing_fields = [f for f in ("pages", "volume", "issue", "source") if not api_metadata.get(f)]
            if missing_fields:
                cr_meta = {k: None for k in api_metadata}
                cr_src = {}
                if perform_crossref_lookup(doi, cr_meta, cr_src):
                    for field in missing_fields:
                        if cr_meta.get(field):
                            api_metadata[field] = cr_meta[field]
                            api_sources[field] = "crossref"
        else:
            api_success = perform_crossref_lookup(doi, api_metadata, api_sources)
            if api_success:
                api_source = "crossref"

        if api_success:
            # Use API metadata as the authoritative source
            for key in ("authors", "title", "year", "source", "volume", "issue", "pages", "publisher", "type"):
                if api_metadata.get(key):
                    metadata[key] = api_metadata[key]
                    field_sources[key] = api_sources.get(key, api_source)

            # Get abbreviated source if available
            if api_metadata.get("source_abbreviated"):
                metadata["source_abbreviated"] = api_metadata["source_abbreviated"]
                field_sources["source_abbreviated"] = api_sources.get("source_abbreviated", api_source)

            # Get day/month for Vancouver date chain
            if api_metadata.get("day_month"):
                metadata["day_month"] = api_metadata["day_month"]
                field_sources["day_month"] = api_sources.get("day_month", api_source)

    # Step 3: No DOI or API failed — try title search
    if not api_success:
        discovered_doi = _try_title_search_for_doi(parsed)
        if discovered_doi:
            print(f"[Formatter] Title search found DOI: {discovered_doi}")
            api_metadata = {
                "authors": None, "title": None, "year": None,
                "source": None, "doi": discovered_doi, "url": None,
                "volume": None, "issue": None, "pages": None,
                "publisher": None, "type": "Other",
            }
            api_sources = {}

            api_success = perform_pubmed_lookup(discovered_doi, api_metadata, api_sources)
            if not api_success:
                api_success = perform_crossref_lookup(discovered_doi, api_metadata, api_sources)

            if api_success:
                api_source = api_sources.get("doi", "crossref")
                metadata["doi"] = discovered_doi
                field_sources["doi"] = "title_search"
                for key in ("authors", "title", "year", "source", "volume", "issue", "pages", "publisher", "type"):
                    if api_metadata.get(key):
                        metadata[key] = api_metadata[key]
                        field_sources[key] = api_sources.get(key, api_source)
                if api_metadata.get("source_abbreviated"):
                    metadata["source_abbreviated"] = api_metadata["source_abbreviated"]
                    field_sources["source_abbreviated"] = api_sources.get("source_abbreviated", api_source)
                if api_metadata.get("day_month"):
                    metadata["day_month"] = api_metadata["day_month"]
                    field_sources["day_month"] = api_sources.get("day_month", api_source)

    # Step 4: Regex fallback — fill remaining gaps from user input
    for key in ("year", "volume", "issue", "pages", "doi"):
        if not metadata.get(key) and parsed.get(key):
            metadata[key] = parsed[key]
            field_sources[key] = "text_parsing"

    if not metadata.get("authors") and parsed.get("authors"):
        metadata["authors"] = parsed["authors"]
        field_sources["authors"] = "text_parsing"

    if not metadata.get("title") and parsed.get("title"):
        metadata["title"] = parsed["title"]
        field_sources["title"] = "text_parsing"

    if not metadata.get("source") and parsed.get("source"):
        metadata["source"] = parsed["source"]
        field_sources["source"] = "text_parsing"

    # URL fallback
    if not metadata.get("doi") and not metadata.get("url"):
        url_match = re.search(r'(https?://\S+)', ref_text)
        if url_match:
            metadata["url"] = url_match.group(1).rstrip('.,;)')
            field_sources["url"] = "text_parsing"

    # Step 5: Classify type
    if metadata["type"] == "Other":
        metadata["type"] = classify_source_type(metadata)

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

    # Step 6: Detect corrections (user input vs API truth)
    corrections = []
    if api_success:
        corrections = _detect_corrections(parsed, metadata, ref_text)

    metadata["field_sources"] = field_sources
    metadata["corrections"] = corrections
    metadata["api_verified"] = api_success
    metadata["api_source"] = api_source

    return metadata


async def parse_raw_reference_async(ref_text: str, client=None) -> dict:
    """
    Async version of parse_raw_reference that uses rate-limited batch APIs.
    """
    import asyncio
    from references.api_batch import fetch_crossref_batch
    
    # Run the fast regex part in a thread
    parsed = await asyncio.to_thread(parse_raw_reference_fast, ref_text)

    metadata = {
        "authors": None, "title": None, "year": None,
        "source": None, "doi": None, "url": None,
        "volume": None, "issue": None, "pages": None,
        "publisher": None, "type": "Other",
    }
    field_sources = {}

    doi = parsed.get("doi")
    if doi:
        metadata["doi"] = doi
        field_sources["doi"] = "text_parsing"

    api_success = False
    api_source = None

    if doi:
        # Try PubMed first (sync in thread, fast enough, not strictly limited yet)
        api_metadata = {k: None for k in metadata}
        api_sources = {}
        def do_pubmed():
            return perform_pubmed_lookup(doi, api_metadata, api_sources)
            
        api_success = await asyncio.to_thread(do_pubmed)
        if api_success:
            api_source = "pubmed"
            
            # Supplement with Crossref for missing fields using rate-limited batch API
            missing_fields = [f for f in ("pages", "volume", "issue", "source") if not api_metadata.get(f)]
            if missing_fields:
                records = await fetch_crossref_batch([doi], client=client)
                if records and records[0]:
                    cr_rec = records[0]
                    for field in missing_fields:
                        val = getattr(cr_rec, field, None)
                        if val:
                            api_metadata[field] = val
                            api_sources[field] = "crossref"
        else:
            # Fallback to rate-limited Crossref
            records = await fetch_crossref_batch([doi], client=client)
            if records and records[0]:
                cr_rec = records[0]
                api_metadata.update({
                    "authors": cr_rec.authors, "title": cr_rec.title, "year": cr_rec.year,
                    "source": cr_rec.journal, "doi": cr_rec.doi, "url": cr_rec.url,
                    "volume": cr_rec.volume, "issue": cr_rec.issue, "pages": cr_rec.pages,
                    "publisher": cr_rec.publisher, "type": cr_rec.type
                })
                for k in api_metadata:
                    if api_metadata[k]: api_sources[k] = "crossref"
                api_success = True
                api_source = "crossref"

        if api_success:
            for key in ("authors", "title", "year", "source", "volume", "issue", "pages", "publisher", "type"):
                if api_metadata.get(key):
                    metadata[key] = api_metadata[key]
                    field_sources[key] = api_sources.get(key, api_source)

    if not api_success:
        discovered_doi = await asyncio.to_thread(_try_title_search_for_doi, parsed)
        if discovered_doi:
            api_metadata = {k: None for k in metadata}
            api_sources = {}
            api_metadata["doi"] = discovered_doi

            def do_pubmed_title():
                return perform_pubmed_lookup(discovered_doi, api_metadata, api_sources)
            
            api_success = await asyncio.to_thread(do_pubmed_title)
            
            if not api_success:
                records = await fetch_crossref_batch([discovered_doi])
                if records and records[0]:
                    cr_rec = records[0]
                    api_metadata.update({
                        "authors": cr_rec.authors, "title": cr_rec.title, "year": cr_rec.year,
                        "source": cr_rec.journal, "doi": cr_rec.doi, "url": cr_rec.url,
                        "volume": cr_rec.volume, "issue": cr_rec.issue, "pages": cr_rec.pages,
                        "publisher": cr_rec.publisher, "type": cr_rec.type
                    })
                    for k in api_metadata:
                        if api_metadata[k]: api_sources[k] = "crossref"
                    api_success = True

            if api_success:
                api_source = api_sources.get("doi", "crossref")
                metadata["doi"] = discovered_doi
                field_sources["doi"] = "title_search"
                for key in ("authors", "title", "year", "source", "volume", "issue", "pages", "publisher", "type"):
                    if api_metadata.get(key):
                        metadata[key] = api_metadata[key]
                        field_sources[key] = api_sources.get(key, api_source)

    # Step 4: Regex fallback
    for key in ("year", "volume", "issue", "pages", "doi"):
        if not metadata.get(key) and parsed.get(key):
            metadata[key] = parsed[key]
            field_sources[key] = "text_parsing"

    if not metadata.get("authors") and parsed.get("authors"):
        metadata["authors"] = parsed["authors"]
        field_sources["authors"] = "text_parsing"

    if not metadata.get("title") and parsed.get("title"):
        metadata["title"] = parsed["title"]
        field_sources["title"] = "text_parsing"

    if not metadata.get("source") and parsed.get("source"):
        metadata["source"] = parsed["source"]
        field_sources["source"] = "text_parsing"

    if not metadata.get("doi") and not metadata.get("url"):
        import re
        url_match = re.search(r'(https?://\S+)', ref_text)
        if url_match:
            metadata["url"] = url_match.group(1).rstrip('.,;)')
            field_sources["url"] = "text_parsing"

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

    corrections = []
    if api_success:
        corrections = await asyncio.to_thread(_detect_corrections, parsed, metadata, ref_text)

    metadata["field_sources"] = field_sources
    metadata["corrections"] = corrections
    metadata["api_verified"] = api_success
    metadata["api_source"] = api_source

    return metadata

