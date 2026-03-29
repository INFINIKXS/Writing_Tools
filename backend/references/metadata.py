"""
Metadata extraction from PDFs and DOCX files, plus PubMed/CrossRef API lookups.
"""
import io
import re
import json
import difflib

import requests
from PyPDF2 import PdfReader
from docx import Document

from core.gemini import get_client, gemini_request_with_retry
from utils.text_utils import classify_source_type


def perform_pubmed_lookup(doi: str, metadata: dict, field_sources: dict, expected_title: str = None) -> bool:
    """Attempt to fill metadata via PubMed NCBI E-utilities API. Returns True if successful.
    PubMed natively returns NLM-abbreviated sources, sentence-cased titles, and e-locators."""
    try:
        search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={doi}[doi]&retmode=json"
        rs = requests.get(search_url, timeout=10)
        if rs.status_code == 200:
            s_data = rs.json()
            pmids = s_data.get("esearchresult", {}).get("idlist", [])
            if pmids:
                pmid = pmids[0]
                summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={pmid}&retmode=json"
                r2 = requests.get(summary_url, timeout=10)
                if r2.status_code == 200:
                    sum_data = r2.json()
                    result = sum_data.get("result", {}).get(str(pmid), {})
                    if not result:
                        return False

                    pubmed_title = result.get("title", "")
                    if expected_title and pubmed_title:
                        t1 = "".join(c for c in expected_title.lower() if c.isalnum() or c.isspace()).strip()
                        t2 = "".join(c for c in pubmed_title.lower() if c.isalnum() or c.isspace()).strip()
                        ratio = difflib.SequenceMatcher(None, t1, t2).ratio()
                        if ratio < 0.9:
                            print(f"[PubMed] Title mismatch for {doi}. Expected: '{expected_title}'. Got: '{pubmed_title}' (Ratio: {ratio:.2f})")
                            return False
                            
                    authors = [a.get("name") for a in result.get("authors", []) if a.get("name")]
                    if authors:
                        metadata["authors"] = authors
                        field_sources["authors"] = "pubmed"
                        
                    if result.get("title"):
                        metadata["title"] = result.get("title")
                        field_sources["title"] = "pubmed"
                        
                    if result.get("pubdate"):
                        year_match = re.search(r'\b(19|20)\d{2}\b', result.get("pubdate"))
                        if year_match:
                            metadata["year"] = year_match.group(0)
                        field_sources["year"] = "pubmed"
                        
                    if result.get("fulljournalname"):
                        metadata["source"] = result.get("fulljournalname")
                        field_sources["source"] = "pubmed"
                        
                    if result.get("source"):
                        metadata["source_abbreviated"] = result.get("source")
                        field_sources["source_abbreviated"] = "pubmed"
                        
                    if result.get("volume"):
                        metadata["volume"] = str(result.get("volume"))
                        field_sources["volume"] = "pubmed"
                        
                    if result.get("issue"):
                        metadata["issue"] = str(result.get("issue"))
                        field_sources["issue"] = "pubmed"
                        
                    if result.get("pages"):
                        metadata["pages"] = str(result.get("pages"))
                        field_sources["pages"] = "pubmed"
                    elif result.get("elocationid"):
                        eloc = str(result.get("elocationid"))
                        if "doi:" in eloc.lower():
                            eloc = eloc.split(":")[-1].strip()
                            if "/" in eloc:
                                eloc = eloc.split("/")[-1]
                        metadata["pages"] = eloc
                        field_sources["pages"] = "pubmed"
                        
                    metadata["type"] = "Journal Article"
                    field_sources["type"] = "pubmed"
                    
                    field_sources["doi"] = "pubmed"
                    
                    return True
    except Exception as e:
        print(f"[PubMed] Lookup failed for {doi}: {e}")
    return False


def perform_crossref_lookup(doi: str, metadata: dict, field_sources: dict, expected_title: str = None) -> bool:
    """Attempt to fill metadata via CrossRef API. Returns True if successful.
    If expected_title is provided, rejects the lookup if the CrossRef title doesn't match."""
    try:
        crossref_url = f"https://api.crossref.org/works/{doi}"
        resp = requests.get(crossref_url, timeout=10, headers={
            'User-Agent': 'WritingTools/1.0 (mailto:support@paradoxlabs.com)'
        })
        if resp.status_code == 200:
            data = resp.json().get('message', {})
            
            if expected_title:
                titles = data.get('title', [])
                crossref_title = titles[0] if titles else ""
                if crossref_title:
                    t1 = "".join(c for c in expected_title.lower() if c.isalnum() or c.isspace()).strip()
                    t2 = "".join(c for c in crossref_title.lower() if c.isalnum() or c.isspace()).strip()
                    ratio = difflib.SequenceMatcher(None, t1, t2).ratio()
                    if ratio < 0.9:
                        print(f"[CrossRef] Title mismatch for {doi}. Expected: '{expected_title}'. Got: '{crossref_title}' (Ratio: {ratio:.2f})")
                        return False
            
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
                    field_sources["authors"] = "crossref"
            
            titles = data.get('title', [])
            if titles:
                metadata["title"] = titles[0]
                field_sources["title"] = "crossref"
            
            date_parts = data.get('published-print', data.get('published-online', data.get('created', {})))
            if date_parts and 'date-parts' in date_parts:
                parts = date_parts['date-parts'][0]
                if parts:
                    metadata["year"] = str(parts[0])
                    field_sources["year"] = "crossref"
            
            container = data.get('container-title', [])
            if container:
                metadata["source"] = container[0]
                field_sources["source"] = "crossref"
                
            short_container = data.get('short-container-title', [])
            if short_container:
                metadata["source_abbreviated"] = short_container[0]
                field_sources["source_abbreviated"] = "crossref"
            
            if data.get('volume'):
                metadata["volume"] = str(data['volume'])
                field_sources["volume"] = "crossref"
            if data.get('issue'):
                metadata["issue"] = str(data['issue'])
                field_sources["issue"] = "crossref"
            if data.get('page'):
                metadata["pages"] = str(data['page'])
                field_sources["pages"] = "crossref"
            elif data.get('article-number'):
                metadata["pages"] = str(data['article-number'])
                field_sources["pages"] = "crossref"
            if data.get('publisher'):
                metadata["publisher"] = data['publisher']
                field_sources["publisher"] = "crossref"
            
            cr_type = data.get('type', '')
            type_map = {
                'journal-article': 'Journal Article',
                'book': 'Book',
                'book-chapter': 'Book Chapter',
                'proceedings-article': 'Conference Paper',
                'report': 'Report',
                'dissertation': 'Dissertation',
            }
            metadata["type"] = type_map.get(cr_type, 'Other')
            if cr_type in type_map:
                field_sources["type"] = "crossref"
                
            field_sources["doi"] = "crossref"

            return True
    except Exception as e:
        print(f"[CrossRef] Lookup failed for {doi}: {e}")
    return False


async def extract_pdf_metadata(file_bytes: bytes) -> dict:
    """
    Extract metadata from a PDF file using PDF properties + first-3-page text parsing.
    Enrichment priority: CrossRef DOI > Python regex > Gemini AI fallback.
    """
    metadata = {
        "authors": None, "title": None, "year": None,
        "source": None, "doi": None, "url": None,
        "volume": None, "issue": None, "pages": None,
        "publisher": None, "type": "Other",
    }
    field_sources = {}
    
    with io.BytesIO(file_bytes) as f:
        reader = PdfReader(f)
        
        # ─── Step 1: PDF built-in metadata ───
        pdf_meta = reader.metadata
        if pdf_meta:
            if pdf_meta.get('/Author') or pdf_meta.get('author'):
                raw_author = pdf_meta.get('/Author') or pdf_meta.get('author') or ''
                if raw_author and not any(skip in raw_author.lower() for skip in ['microsoft', 'adobe', 'scanner', 'latex', 'tex', 'kman', 'acrobat', 'pdf']):
                    metadata["authors"] = raw_author
                    field_sources["authors"] = "pdf_metadata"
            
            if pdf_meta.get('/Title') or pdf_meta.get('title'):
                raw_title = pdf_meta.get('/Title') or pdf_meta.get('title') or ''
                if raw_title and len(raw_title) > 3:
                    metadata["title"] = raw_title
                    field_sources["title"] = "pdf_metadata"
            
            if pdf_meta.get('/CreationDate') or pdf_meta.get('creation_date'):
                raw_date = str(pdf_meta.get('/CreationDate') or pdf_meta.get('creation_date') or '')
                year_match = re.search(r'(19|20)\d{2}', raw_date)
                if year_match:
                    metadata["year"] = year_match.group(0)
                    field_sources["year"] = "pdf_metadata"
        
        # Sanity check: if author == title, both are likely bogus
        if (metadata.get("authors") and metadata.get("title") and 
            str(metadata["authors"]).strip().lower() == str(metadata["title"]).strip().lower() and
            field_sources.get("authors") == "pdf_metadata"):
            metadata["authors"] = None
            metadata["title"] = None
            field_sources.pop("authors", None)
            field_sources.pop("title", None)
        
        # ─── Step 2: First 3 pages text parsing ───
        pages_to_scan = min(3, len(reader.pages))
        first_pages_text = ''
        for i in range(pages_to_scan):
            page_text = reader.pages[i].extract_text() or ''
            first_pages_text += page_text + '\n'
        
        regex_dois = []
        if first_pages_text.strip():
            # DOI extraction
            all_doi_matches = re.findall(
                r'(?:doi[:\s]*|https?://(?:dx\.)?doi\.org/)?(10\.\d{4,}/[a-zA-Z0-9.\-_/:()\\[\]]+)',
                first_pages_text, re.IGNORECASE
            )
            if all_doi_matches:
                for match in all_doi_matches:
                    clean_doi = match.rstrip('].;,()')
                    clean_doi = re.sub(r'(?i)(Research|Article|Review|Copyright|Downloaded)\b.*$', '', clean_doi)
                    if clean_doi not in regex_dois:
                        regex_dois.append(clean_doi)
            
            if regex_dois:
                metadata["doi"] = regex_dois[0]
                field_sources["doi"] = "text_parsing"
            
            # Title extraction from text
            lines = [l.strip() for l in first_pages_text.split('\n') if l.strip()]
            skip_patterns = re.compile(
                r'^('
                r'vol|volume|issue|page|doi|http|www|©|ISSN|ISBN|'
                r'RESEARCH|ARTICLE|REVIEW|Open Access|Creative Commons|'
                r'Correspondence|Author|Received|Accepted|Published|'
                r'Abstract|Background|Introduction|Methods|Results|'
                r'Keywords|Licensed|Check for|updates|Citation|'
                r'This article|The Author|Springer|Elsevier|Wiley|BMC|'
                r'\d+\s*$|et al\.'
                r')', re.IGNORECASE
            )
            best_title = None
            best_score = 0
            for line in lines:
                if len(line) < 15 or len(line) > 300:
                    continue
                if skip_patterns.match(line):
                    continue
                if re.match(r'^\d+\s*$', line):
                    continue
                if re.search(r'\d+:\d+\s*\(\d{4}\)', line):
                    continue
                if re.search(r'\(\d{4}\)\s*\d+[-–]\d+', line):
                    continue
                if re.search(r'\b\d+[-–]\d+\s*$', line):
                    continue
                score = min(len(line), 150)
                if line[0].isupper() and ':' in line:
                    score += 20
                if score > best_score:
                    best_score = score
                    best_title = line
            if best_title:
                if not metadata["title"]:
                    metadata["title"] = best_title
                    field_sources["title"] = "text_parsing"
                elif field_sources.get("title") == "pdf_metadata":
                    current = str(metadata["title"]).strip()
                    is_suspicious = (
                        len(current) < 10 or
                        ' ' not in current or
                        current.isupper() and len(current) < 20
                    )
                    if is_suspicious:
                        metadata["title"] = best_title
                        field_sources["title"] = "text_parsing"
            
            # Year from text
            if not metadata["year"]:
                year_match = re.search(r'\b(19|20)\d{2}\b', first_pages_text)
                if year_match:
                    metadata["year"] = year_match.group(0)
                    field_sources["year"] = "text_parsing"

            # Volume/Issue/Pages
            vol_match = re.search(r'(?:vol(?:ume)?\.?\s*|(?<=,\s))(\d+)\s*\((\d+)\)', first_pages_text, re.IGNORECASE)
            if vol_match:
                metadata["volume"] = vol_match.group(1)
                metadata["issue"] = vol_match.group(2)
                field_sources["volume"] = "text_parsing"
                field_sources["issue"] = "text_parsing"
            
            pages_match = re.search(r'(?:pp?\.?\s*)(\d+)\s*[-–]\s*(\d+)', first_pages_text, re.IGNORECASE)
            if pages_match:
                metadata["pages"] = f"{pages_match.group(1)}-{pages_match.group(2)}"
                field_sources["pages"] = "text_parsing"

            # URL extraction
            if not metadata["doi"]:
                url_match = re.search(r'(https?://\S+)', first_pages_text)
                if url_match:
                    metadata["url"] = url_match.group(1).rstrip('.,;)')
                    field_sources["url"] = "text_parsing"

    # ─── Step 3: API lookups (PubMed -> CrossRef) ───
    api_success = False
    if metadata["doi"]:
        expected_title_guard = metadata.get("title")
        api_success = perform_pubmed_lookup(metadata["doi"], metadata, field_sources, expected_title=expected_title_guard)
        if not api_success:
            api_success = perform_crossref_lookup(metadata["doi"], metadata, field_sources)
    
    metadata["crossref_failed"] = not api_success
    
    # ─── Step 4: Gemini AI — verify non-CrossRef fills + fill missing fields ───
    has_unverified_fields = any(v in ("text_parsing", "pdf_metadata") for v in field_sources.values())
    has_missing = not metadata["authors"] or not metadata["title"] or not metadata["year"]
    
    if (not api_success or has_unverified_fields or has_missing) and first_pages_text.strip():
        python_found = {}
        for key in ["authors", "title", "year", "source", "doi"]:
            if metadata.get(key) and field_sources.get(key) in ("text_parsing", "pdf_metadata"):
                python_found[key] = metadata[key]
        
        verification_context = ""
        if python_found:
            verification_context = f"""
Python regex has already extracted these fields (VERIFY them — confirm or correct):
{json.dumps(python_found, indent=2, ensure_ascii=False)}
"""
        
        try:
            model_name = 'gemini-3-flash-preview'
            client = get_client(model=model_name)
            prompt = f"""You are a metadata extraction tool. Extract ONLY what you can see in the document text below.
DO NOT invent, guess, or hallucinate any information. If a field is not clearly visible, return null.
{verification_context}
Extract these fields from the document:
- authors: List of author names in "Surname, Initials." format (e.g. ["Smith, J.", "Jones, A. B."])
- title: The main title of the paper/document (not section headings, not journal name)
- year: The publication year (not copyright year if different)
- source: Journal name or publisher name if visible
- source_abbreviated: If the source is a journal, provide its strictly abbreviated NLM catalog form (e.g. 'J Am Med Assoc'). Omit periods. If not a journal, return null. THIS IS EXEMPT FROM THE "ONLY WHAT YOU CAN SEE" RULE.
- doi: The Digital Object Identifier of exactly THIS main document (Beware: do not extract DOIs of cited references in the bibliography or abstract!)

DOCUMENT TEXT (first 3 pages):
{first_pages_text[:8000]}

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
            print(f"[AI Verification] AI returned: {ai_data}")
            
            ai_doi = ai_data.get("doi")
            expected = ai_data.get("title") or metadata.get("title")
            
            candidate_dois = []
            if ai_doi:
                candidate_dois.append(ai_doi)
            candidate_dois.extend(regex_dois)
            candidate_dois = list(dict.fromkeys(d for d in candidate_dois if d))
            
            needs_recovery = (not api_success) or (ai_doi and ai_doi != metadata.get("doi")) or (not metadata.get("doi"))
            
            if needs_recovery and candidate_dois:
                print(f"[AI Verification] Attempting verification loop using {len(candidate_dois)} candidate DOIs...")
                retry_success = False
                for c_doi in candidate_dois:
                    print(f"  -> Testing candidate DOI: {c_doi}")
                    retry_success = perform_pubmed_lookup(c_doi, metadata, field_sources, expected_title=expected)
                    if not retry_success:
                        retry_success = perform_crossref_lookup(c_doi, metadata, field_sources, expected_title=expected)
                        
                    if retry_success:
                        print(f"  ✓ Success! Recovered correct paper metadata using DOI: {c_doi}")
                        metadata["doi"] = c_doi
                        api_success = True
                        metadata["crossref_failed"] = False
                        break
                
                if retry_success:
                    needs_recovery = False
            
            # ─── RETRY: Focused AI DOI Extraction ───
            if needs_recovery and not api_success and not ai_doi and first_pages_text:
                print(f"[AI Verification] AI returned no DOI. Retrying with focused DOI extraction prompt...")
                try:
                    retry_prompt = f"""You are a DOI extraction specialist. Your ONLY job is to find the DOI of the main document below.

IMPORTANT RULES:
- Look for patterns like "doi:", "DOI:", "https://doi.org/", or raw "10.XXXX/..." strings
- The DOI usually appears near the top of the first page, in headers, footers, or citation boxes
- Do NOT extract DOIs from the bibliography/reference list — only the MAIN document's DOI
- If you cannot find a DOI, return null. Do NOT guess or hallucinate.

DOCUMENT TEXT (first 3 pages):
{first_pages_text[:8000]}

Respond with ONLY the DOI string, or the word "null" if not found. No JSON, no explanation."""

                    retry_response = await gemini_request_with_retry(client, retry_prompt, model=model_name)
                    retry_doi_text = retry_response.text.strip().strip('"').strip("'")
                    
                    if retry_doi_text and retry_doi_text.lower() != "null" and retry_doi_text.startswith("10."):
                        retry_doi_text = retry_doi_text.rstrip('.,;)')
                        print(f"[AI Verification] Focused DOI retry found: {retry_doi_text}")
                        
                        retry_doi_success = perform_pubmed_lookup(retry_doi_text, metadata, field_sources, expected_title=expected)
                        if not retry_doi_success:
                            retry_doi_success = perform_crossref_lookup(retry_doi_text, metadata, field_sources, expected_title=expected)
                        
                        if retry_doi_success:
                            print(f"  ✓ Focused DOI retry VERIFIED! DOI: {retry_doi_text}")
                            metadata["doi"] = retry_doi_text
                            api_success = True
                            needs_recovery = False
                            metadata["crossref_failed"] = False
                        else:
                            print(f"  ✗ Focused DOI retry found {retry_doi_text} but it failed title verification.")
                    else:
                        print(f"[AI Verification] Focused DOI retry also returned nothing.")
                except Exception as retry_e:
                    print(f"[AI Verification] Focused DOI retry FAILED: {retry_e}")
            
            # ─── FALLBACK: Search CrossRef by Title ───
            if needs_recovery and not api_success and expected:
                print(f"[AI Verification] Attempting Title Search Fallback via CrossRef for '{expected}'...")
                try:
                    import urllib.parse
                    title_encoded = urllib.parse.quote(expected)
                    url = f'https://api.crossref.org/works?query.bibliographic="{title_encoded}"&rows=5'
                    cr_resp = requests.get(url, timeout=10, headers={'User-Agent': 'WritingTools'})
                    if cr_resp.status_code == 200:
                        items = cr_resp.json().get('message', {}).get('items', [])
                        for item in items:
                            discovered_doi = item.get('DOI')
                            if not discovered_doi or discovered_doi in candidate_dois or discovered_doi == metadata.get("doi"):
                                continue
                            
                            cr_titles = item.get('title', [])
                            cr_title = cr_titles[0] if cr_titles else ""
                            
                            if cr_title and re.match(r'^(Correction|Erratum|Retraction|Corrigendum|Author Correction)\s*:', cr_title, re.IGNORECASE):
                                print(f"  -> Skipping correction/erratum: {discovered_doi} ('{cr_title[:60]}...')")
                                continue
                            
                            if cr_title:
                                t1 = "".join(c for c in expected.lower() if c.isalnum() or c.isspace()).strip()
                                t2 = "".join(c for c in cr_title.lower() if c.isalnum() or c.isspace()).strip()
                                pre_ratio = difflib.SequenceMatcher(None, t1, t2).ratio()
                                if pre_ratio < 0.9:
                                    print(f"  -> Skipping low-confidence match: {discovered_doi} ('{cr_title[:60]}...' ratio={pre_ratio:.2f})")
                                    continue
                            
                            cr_authors = item.get('author', [])
                            ai_authors = ai_data.get('authors', []) or metadata.get('authors', [])
                            if cr_authors and ai_authors:
                                cr_first_surname = cr_authors[0].get('family', '').lower().strip()
                                ai_first = ai_authors[0] if isinstance(ai_authors[0], str) else ''
                                ai_first_surname = re.split(r'[,\s]', ai_first)[0].lower().strip() if ai_first else ''
                                if cr_first_surname and ai_first_surname and cr_first_surname != ai_first_surname:
                                    print(f"  -> Skipping author mismatch: {discovered_doi} (expected '{ai_first_surname}', got '{cr_first_surname}')")
                                    continue
                            
                            ai_year = ai_data.get('year') or metadata.get('year')
                            if ai_year:
                                cr_date = item.get('published-print', item.get('published-online', item.get('created', {})))
                                if cr_date and 'date-parts' in cr_date:
                                    cr_year = str(cr_date['date-parts'][0][0]) if cr_date['date-parts'][0] else None
                                    if cr_year and cr_year != str(ai_year):
                                        print(f"  -> Skipping year mismatch: {discovered_doi} (expected {ai_year}, got {cr_year})")
                                        continue
                            
                            print(f"  -> Testing discovered DOI from Title Search: {discovered_doi}")
                            found_success = perform_pubmed_lookup(discovered_doi, metadata, field_sources, expected_title=expected)
                            if not found_success:
                                found_success = perform_crossref_lookup(discovered_doi, metadata, field_sources, expected_title=expected)
                            if found_success:
                                print(f"  ✓ Success! Rescue via Title Search! Found DOI: {discovered_doi}")
                                metadata["doi"] = discovered_doi
                                api_success = True
                                metadata["crossref_failed"] = False
                                break
                except Exception as fall_e:
                    print(f"[AI Verification] Title Search Fallback Failed: {fall_e}")
            
            # For each field: fill if missing, or override if from unreliable source
            for key in ["authors", "title", "year", "source", "source_abbreviated", "doi"]:
                ai_value = ai_data.get(key)
                if not ai_value:
                    continue
                current_source = field_sources.get(key)
                if current_source in ("crossref", "pubmed"):
                    continue
                if not metadata.get(key):
                    metadata[key] = str(ai_value) if key in ("year", "volume", "issue") else ai_value
                    field_sources[key] = "ai"
                elif current_source in ("text_parsing", "pdf_metadata"):
                    if key in ("year", "volume", "issue"):
                        ai_value = str(ai_value)
                    metadata[key] = ai_value
                    field_sources[key] = "ai_verified"
                
        except Exception as e:
            print(f"[AI Verification] FAILED: {type(e).__name__}: {e}")
            metadata["ai_warning"] = f"AI verification failed: {type(e).__name__}. Metadata may be inaccurate."
    
    # ─── Step 5: Classify type if not set by CrossRef ───
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
    
    metadata["field_sources"] = field_sources
    
    # ─── Step 6: Track AI-filled fields ───
    ai_filled = {}
    for key in ["authors", "title", "year", "source", "source_abbreviated", "doi", "volume", "issue", "pages"]:
        src = field_sources.get(key)
        if src in ("ai", "ai_verified", "ai_inferred") and metadata.get(key):
            val = metadata[key]
            if isinstance(val, list):
                val = "; ".join(str(v) for v in val)
            ai_filled[key] = {"value": str(val), "source": src}
    if ai_filled:
        metadata["ai_filled_fields"] = ai_filled
    
    # ─── Step 7: Compute verification_status ───
    critical_fields = ["title", "authors", "year"]
    all_from_api = all(
        field_sources.get(f) in ("pubmed", "crossref", "ai_verified")
        for f in critical_fields
    )
    has_doi = bool(metadata.get("doi"))
    
    if api_success and all_from_api and has_doi:
        metadata["verification_status"] = "verified"
    elif api_success and has_doi:
        metadata["verification_status"] = "partial"
    else:
        metadata["verification_status"] = "unverified"
    
    return metadata


def extract_docx_metadata(file_bytes: bytes) -> dict:
    """Extract metadata from a DOCX file using document core properties."""
    metadata = {
        "authors": None, "title": None, "year": None,
        "source": None, "doi": None, "url": None,
        "volume": None, "issue": None, "pages": None,
        "publisher": None, "type": "Other",
    }
    
    with io.BytesIO(file_bytes) as f:
        doc = Document(f)
        
        props = doc.core_properties
        if props.author:
            metadata["authors"] = props.author
        if props.title and len(props.title) > 3:
            metadata["title"] = props.title
        if props.created:
            metadata["year"] = str(props.created.year)
        
        full_text = '\n'.join(p.text for p in doc.paragraphs[:5])
        doi_match = re.search(r'(?:doi[:\s]*|https?://(?:dx\.)?doi\.org/)(\S+?)(?:\s|$)', full_text, re.IGNORECASE)
        if doi_match:
            metadata["doi"] = doi_match.group(1).rstrip('.,;)')
        
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
        except Exception:
            pass
    
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
    
    return metadata
