"""
Citation-to-reference verification, cross-validation, and verbatim reference extraction.
"""
import re
from difflib import SequenceMatcher


def verify_matches_with_string_search(in_text_citations, references):
    verification_results = {
        "confirmed_matches": [],
        "unmatched_citations": [],
        "unmatched_references": [],
        "duplicate_first_names": {},
        "summary": "Surname + year compound-key match verification completed (case-insensitive)."
    }

    def extract_first_author(text):
        """Extract the first author's bare surname from a citation or reference string."""
        core = text.strip('()[] ').split(' et al.')[0].split(' and ')[0].strip()
        # Include curly apostrophe \u2019
        match = re.search(r'^([A-Za-z\'\-\u2019]+)', core)
        if match:
            surname = match.group(1).strip()
            surname = re.sub(r'\s+[A-Z]{1,3}$', '', surname).strip()
            return surname
        return None

    def extract_year(text, mode='first'):
        """Extract a 4-digit year (with optional letter suffix) from a string.
        mode='first': returns the first year found (for references — pub year is early).
        mode='last':  returns the last year found (for citations — pub year is at the end).
        Preserves letter suffixes (e.g. 2026a, 2026b) so they form distinct compound keys.
        """
        matches = re.findall(r'\b(?:19|20)\d{2}[a-z]?\b', text)
        if not matches:
            return None
        return matches[-1] if mode == 'last' else matches[0]

    # Build compound-key index
    ref_compound_index = {}
    ref_surname_index = {}

    for ref in references:
        ref_surname = extract_first_author(ref)
        if not ref_surname:
            continue
        ref_year = extract_year(ref, mode='first')
        normalized_surname = ref_surname.lower().replace('\u2019', "'")
        key = (normalized_surname, ref_year)
        ref_compound_index.setdefault(key, []).append(ref)
        ref_surname_index.setdefault(normalized_surname, []).append(ref)

    # Report duplicate surnames
    for surname_lower, refs in ref_surname_index.items():
        if len(refs) > 1:
            verification_results["duplicate_first_names"][surname_lower.capitalize()] = refs

    matched_refs = set()

    for cit in in_text_citations:
        cit_surname = extract_first_author(cit)
        if not cit_surname:
            verification_results["unmatched_citations"].append(cit)
            continue

        cit_year = extract_year(cit, mode='last')
        normalized_cit_surname = cit_surname.lower().replace('\u2019', "'")

        # 1. Try compound key (surname + year, including suffix like 2026b)
        compound_key = (normalized_cit_surname, cit_year)
        candidates = ref_compound_index.get(compound_key, [])

        # 2. Fallback: try base year without suffix (2026b -> 2026)
        if not candidates and cit_year and re.match(r'\d{4}[a-z]', cit_year):
            base_year = cit_year[:4]
            candidates = ref_compound_index.get((normalized_cit_surname, base_year), [])
        if not candidates and cit_year and not re.match(r'\d{4}[a-z]', cit_year or ''):
            # Citation has no suffix — check if refs have suffixed variants
            for key, refs in ref_compound_index.items():
                if key[0] == normalized_cit_surname and key[1] and key[1][:4] == cit_year:
                    candidates = refs
                    break

        # 3. If still nothing, fall back to surname-only match
        if not candidates:
            candidates = ref_surname_index.get(normalized_cit_surname, [])

        if candidates:
            best_ref = candidates[0]
            matched_refs.add(best_ref)
            try:
                canonical_ref_id = f"ref_{references.index(best_ref)}"
            except ValueError:
                canonical_ref_id = "ref_unknown"
                
            verification_results["confirmed_matches"].append({
                "citation": cit,
                "matched_ref": best_ref,
                "canonical_ref_id": canonical_ref_id
            })
        else:
            verification_results["unmatched_citations"].append(cit)

    verification_results["unmatched_references"] = [ref for ref in references if ref not in matched_refs]

    return verification_results


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
    python_only = []
    ai_only = []
    confirmed = []
    
    for norm, original in python_normalized.items():
        if norm in ai_normalized:
            confirmed.append(original)
        else:
            found_match = False
            for ai_norm, ai_orig in ai_normalized.items():
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

def detect_irregularities_deterministically(citations_list: list, references: list) -> list:
    """
    Deterministically cross-references in-text citations against the reference list 
    to find mismatched dates, spelling errors, or invalid formats.
    """
    import datetime
    from difflib import SequenceMatcher
    current_year = datetime.datetime.now().year
    irregularities = []
    
    # Lowercase everything for faster/simpler reference checking
    ref_pool = [(ref, ref[:150].lower()) for ref in references]

    for cit in citations_list:
        cit_text = cit.get("text", "")
        if not cit_text: continue
        
        # 1. Extract the year
        year_match = re.search(r'\b(18\d\d|19\d\d|20\d\d)\b', cit_text)
        if not year_match: continue
        cit_year = year_match.group(1)
        
        # Check unusual date
        if int(cit_year) > current_year:
            irregularities.append({
                'type': 'UNUSUAL_DATE',
                'citation': cit_text,
                'ref': cit_text, # Unpaired at this stage
                'details': f'Citation uses a future publication year ({cit_year}).'
            })
            
        # 2. Extract Author Block (strip possessive 's before processing)
        author_part_raw = cit_text[:year_match.start()].strip(' (,')
        cit_author_clean = re.sub(r'(?i)\s+et\s+al\.?', '', author_part_raw)
        cit_author_clean = re.sub(r"['\u2019]s\b", '', cit_author_clean)  # strip possessive 's
        c_words = [w for w in re.sub(r'[^A-Za-z\s]', '', cit_author_clean).split() if len(w) > 2 and w.lower() not in ('and')]
        if not c_words: continue

        # 3. Find the best matching reference (match against PRIMARY authors only)
        best_ref = None
        best_ref_year = None
        best_score = 0
        best_r_words = []

        cit_author_lower = cit_author_clean.lower()
        for ref, ref_lower in ref_pool:
            ref_year_match = re.search(r'(?<!\d)(18\d\d|19\d\d|20\d\d)(?!\d)', ref_lower)
            if not ref_year_match: continue
            
            ref_year = ref_year_match.group(1)
            ref_author_part = ref[:ref_year_match.start()]
            
            # Extract only primary authors (before first "&" or "...") to avoid
            # matching citation "Wang and Zhang" against co-authors buried inside
            # an unrelated "Cheng, Q., Duan, Y., Wang, Y., Zhang, Q." reference.
            # For single/two-author citations, match only the first 1-2 surnames.
            # For "et al." citations, match only the first surname.
            first_amp = ref_author_part.find('&')
            if len(c_words) == 1:
                # Single author or et al. — only check the first surname in the ref.
                first_comma = ref_author_part.find(',')
                if first_comma > 0:
                    ref_author_part = ref_author_part[:first_comma]
            elif len(c_words) == 2 and first_amp > 0:
                # Two-author citation — check if this ref is genuinely a 2-author ref.
                # A real two-author ref: "Capili, B., & Anastasi, J. K." has ~2 commas before &
                # A multi-author ref:   "Cheng, Q., Duan, Y., Wang, Y., Zhang, Q., &" has many more
                before_amp = ref_author_part[:first_amp]
                commas_before = before_amp.count(',')
                if commas_before > 2:
                    # This is a multi-author ref, not a two-author ref — skip
                    continue
                    
            # Strip possessive 's from reference author exactly as we do for the citation author
            ref_author_clean = re.sub(r"['\u2019]s\b", '', ref_author_part, flags=re.IGNORECASE)
            r_words = [w for w in re.sub(r'[^A-Za-z\s]', '', ref_author_clean).split() if len(w) > 2 and w.lower() not in ('and')]
            
            # Simple word overlap scoring
            matches = 0
            for cw in c_words:
                if any(SequenceMatcher(None, cw.lower(), rw.lower()).ratio() > 0.8 for rw in r_words):
                    matches += 1
            
            score = (matches / len(c_words)) if c_words else 0
            
            if score > best_score:
                best_score = score
                best_ref = ref
                best_ref_year = ref_year
                best_r_words = r_words

        # 4. Process Irregularities on the best match
        if best_score > 0.6 and best_ref:
            # Check Date Mismatch
            if cit_year != best_ref_year:
                irregularities.append({
                    'type': 'DATE_MISMATCH',
                    'citation': cit_text,
                    'ref': best_ref[:80] + '...' if len(best_ref) > 80 else best_ref,
                    'details': f'Citation year ({cit_year}) does not match the reference year ({best_ref_year}).'
                })
            
            # Check Spelling Errors
            for cw in c_words:
                best_w_score = 0
                best_rw = None
                for rw in best_r_words:
                    w_score = SequenceMatcher(None, cw.lower(), rw.lower()).ratio()
                    if w_score > best_w_score:
                        best_w_score = w_score
                        best_rw = rw
                
                # If they are very similar but not identical (Spelling error found!)
                if 0.82 <= best_w_score < 1.0:
                    irregularities.append({
                        'type': 'NAME_MISMATCH',
                        'citation': cit_text,
                        'ref': best_ref[:80] + '...' if len(best_ref) > 80 else best_ref,
                        'details': f"The surname '{best_rw}' in the reference is cited as '{cw}' in the text."
                    })
                    break # Only flag one name mismatch per citation to avoid spam
                    
    return irregularities


def extract_verbatim_references(full_text: str, ai_references: list) -> dict:
    """
    For each reference identified by the AI, find the closest verbatim match
    in the original document text. Includes safeguards against DOI bleeding
    and cross-reference mixups.
    
    Returns a dict mapping AI reference -> verbatim source text with confidence.
    """
    # ─── PRE-STEP: Clean Invisible Garbage (Docs/PDFs) ───
    def _normalize_text(t):
        """Normalize Unicode characters for consistent comparison."""
        t = t.replace('\u00a0', ' ')      # non-breaking space
        t = t.replace('\u202f', ' ')      # narrow no-break space
        t = t.replace('\u2006', ' ')      # thin space
        t = t.replace('\u2009', ' ')      # thin space
        t = t.replace('\u200b', '')       # zero-width space
        t = t.replace('\u200c', '')       # zero-width non-joiner
        t = t.replace('\u200d', '')       # zero-width joiner
        t = t.replace('\u2018', "'")      # left single quote
        t = t.replace('\u2019', "'")      # right single quote
        t = t.replace('\u201c', '"')      # left double quote
        t = t.replace('\u201d', '"')      # right double quote
        t = t.replace('\u2013', '-')      # en-dash -> hyphen
        t = t.replace('\u2014', '-')      # em-dash -> hyphen
        t = t.replace('\ufb01', 'fi')     # fi ligature
        t = t.replace('\ufb02', 'fl')     # fl ligature
        return t

    full_text = _normalize_text(full_text)
    # Keep original AI references for use as dictionary keys (must match frontend lookups),
    # but create normalized copies for internal comparison against normalized full_text.
    original_ai_references = list(ai_references)
    ai_references_norm = [_normalize_text(r) for r in ai_references]

    # ─── STEP 1: Isolate the reference section ───
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
    ref_start_pattern = re.compile(
        r'^(?:'
        r'[A-Z][a-zA-Zà-öø-ÿ\'\-]+\s*,'
        r'|[A-Z][a-zA-Zà-öø-ÿ\'\-]+\s+[A-Z]{1,4},'
        # Multi-word surname + initials: "Solberg Nes L," or "Van der Berg AB,"
        r'|[A-Z][a-zA-Zà-öø-ÿ\'\-]+(?:\s+[A-Za-z][a-zA-Zà-öø-ÿ\'\-]+)+\s+[A-Z]{1,4},'
        r'|\[\d+\]'
        r'|\d+\.\s+[A-Z]'
        r'|[A-Z][a-zA-Zà-öø-ÿ\'\-]+\s+\('
        r'|[A-Z]\.?\s*,?\s*\('
        r'|[A-Z]\.?\s*,'
        r'|\(\d{4}\)'
        # Org-name references: "Department of Health. (2016)." or "World Health Organization. (2020)."
        r'|(?:[A-Z][a-zA-Zà-öø-ÿ\'\-]+(?:\s+(?:of|for|the|and|on|in|&))?\s+)+[A-Z][a-zA-Zà-öø-ÿ\'\-]+\.?\s*\(\d{4}'
        r')',
    )

    org_name_pattern = re.compile(r'^[A-Z][a-zA-Zà-öø-ÿ\'\-]+\s+[A-Z]')
    
    continuation_pattern = re.compile(
        r'^(?:'
        r'https?://'
        r'|[Dd]oi[\s.:]+'
        r'|[Aa]vailable\s+at'
        r'|[Aa]ccessed'
        r'|pp?\.\s*\d'
        r'|[Vv]ol\.|[Ii]ssue|[Rr]etrieved'
        r'|(?:The|A|An|In|On|Of|For|And|Their|Its|Effects?|Impact)\s'
        r'|[a-z]'
        r'|["\'\u201c\u2018]'
        r')'
    )
    
    has_year = re.compile(r'\b(?:19|20)\d{2}\b')
    
    lines = ref_section.split('\n')
    atomic_refs = []
    current_ref_lines = []
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        
        is_continuation = continuation_pattern.match(stripped)
        
        is_org_name = org_name_pattern.match(stripped) and not is_continuation
        if is_org_name:
            is_org_name = bool(has_year.search(stripped[:150]))
        
        is_new_ref = (ref_start_pattern.match(stripped) or is_org_name) and not is_continuation
        
        if is_new_ref and current_ref_lines:
            atomic_refs.append(' '.join(current_ref_lines))
            current_ref_lines = [stripped]
        else:
            current_ref_lines.append(stripped)
    
    if current_ref_lines:
        atomic_refs.append(' '.join(current_ref_lines))
    
    atomic_refs = [r for r in atomic_refs if len(r) > 20]

    # ─── POST-SPLIT PASS: detect merged references ───
    demerge_pattern = re.compile(
        r'(?:(?<=pdf)|(?<=html)|(?<=org)|(?<=\d)|(?<=/))[.]?\s+'
        r'(?='
        r'(?:(?:[A-Z][a-zA-Zà-öø-ÿ\'-]+|[a-z][a-z]+)[ \u00a0]+)*[A-Z][a-zA-Zà-öø-ÿ\'-]+'
        r'\s*,\s*(?:[A-Z]\.|[A-Z][A-Z]?[A-Z]?(?=\s*,|\s+&|\s+and|\s+et))'
        r'|\[\d+\]'
        r'|\d+\.\s+[A-Z]'
        r')'
    )
    demerged_refs = []
    for ref in atomic_refs:
        parts = demerge_pattern.split(ref)
        if len(parts) == 1:
            demerged_refs.append(parts[0].strip())
            continue
        current_ref = parts[0]
        for pt in parts[1:]:
            ends_like_ref = bool(re.search(r'(\b\d{4}\b|https?://\S+|doi\.org/\S+|\d+\s*|p\.\s*\d+|pp\.\s*\d+[-–]\d+\.?)$', current_ref.strip()))
            
            starts_like_ref = bool(re.match(
                r'^(?:(?:[A-Z][a-zA-Zà-öø-ÿ\'-]+|[a-z]{2,3})[ \u00a0]+)*[A-Z][a-zA-Zà-öø-ÿ\'-]+\s*,\s*[A-Z]\.'
                r'|\[\d+\]'
                r'|\d+\.\s+[A-Z]', pt))
                
            if ends_like_ref and starts_like_ref:
                demerged_refs.append(current_ref.strip())
                current_ref = pt
            else:
                current_ref += " " + pt
        if current_ref.strip():
            demerged_refs.append(current_ref.strip())
    atomic_refs = demerged_refs
    
    # ─── STEP 3: Match using author + year compound key ───
    def extract_author_year(text):
        author = None
        year = None
        text_stripped = text.strip()
        # Try multi-word org name first: "Department of Health" or "GBD 2021 Diabetes Collaborators"
        # Allow digits/mixed tokens (e.g. "2021") inside the org name
        org_match = re.match(
            r'^((?:[A-Za-z0-9][A-Za-z0-9à-öø-ÿ\'\-]*(?:\s+(?:of|for|the|and|on|in|&))?\s+)*[A-Z][a-zA-Zà-öø-ÿ\'\-]+)'
            r'(?:\s*[.,]|\s*\()',
            text_stripped
        )
        if org_match:
            candidate = org_match.group(1).strip()
            # Only use as org name if it contains multiple words (otherwise it's a surname)
            if ' ' in candidate:
                author = candidate.lower()
        # Fallback: single surname
        if not author:
            author_match = re.match(r'^[^a-z]*?([A-Z][a-zA-Zà-öø-ÿ\'\-]+)', text_stripped)
            if author_match:
                author = author_match.group(1).lower()
        # Prefer parenthesized year (YYYY) — that's the publication year in APA/Harvard.
        # Falls back to the first bare year if no parenthesized year is found.
        paren_year = re.search(r'\((\d{4})\)', text)
        if paren_year:
            year = paren_year.group(1)
        else:
            year_match = re.search(r'\b(19|20)\d{2}\b', text)
            if year_match:
                year = year_match.group(0)
        return (author, year)
    
    verbatim_map = {}
    used_candidates = {}
    
    for orig_ref, ai_ref in zip(original_ai_references, ai_references_norm):
        best_score = 0
        best_match = ai_ref
        ai_author, ai_year = extract_author_year(ai_ref)
        ai_ref_lower = ai_ref.lower().strip()
        
        for candidate in atomic_refs:
            candidate_lower = candidate.lower().strip()
            
            len_ratio = len(candidate_lower) / max(len(ai_ref_lower), 1)
            if len_ratio < 0.3 or len_ratio > 15.0:  # Loosened massively to handle un-split document text
                continue
            
            cand_author, cand_year = extract_author_year(candidate)
            
            author_ok = (not ai_author) or (not cand_author) or (ai_author in cand_author) or (cand_author in ai_author)
            year_ok = (not ai_year) or (not cand_year) or (ai_year == cand_year)
            
            if not author_ok or not year_ok:
                continue
            
            sm = SequenceMatcher(None, ai_ref_lower, candidate_lower)
            score = sm.ratio()
            
            # If candidate is a massive merged block, calculate partial matching score
            if len_ratio > 1.5:
                # Find the longest contiguous matching block
                match_blocks = sm.get_matching_blocks()
                if match_blocks:
                    best_block = max(match_blocks[:-1], key=lambda x: x.size)
                    # If we matched at least 80% of the AI reference in one contiguous block
                    if best_block.size / max(len(ai_ref_lower), 1) > 0.8:
                        score = 1.0
                        # Slice the candidate down to just the matched area
                        start_idx = max(0, best_block.b - best_block.a)
                        end_idx = min(len(candidate), start_idx + len(ai_ref_lower))
                        candidate = candidate[start_idx:end_idx].strip()
            
            if score > best_score:
                best_score = score
                best_match = candidate
        
        # ─── STEP 4: Conflict detection ───
        conflict = None
        if best_match in used_candidates.values():
            conflicting_ref = [k for k, v in used_candidates.items() if v == best_match]
            conflict = f"Warning: This verbatim text was also matched by: {conflicting_ref[0][:50]}..."
        
        used_candidates[orig_ref] = best_match
        
        result = {
            "verbatim": best_match,
            "confidence": round(best_score, 2)
        }
        if conflict:
            result["conflict"] = conflict
        
        # Use original (un-normalized) reference string as key so the frontend
        # can look it up with the same key it received from the AI analysis.
        verbatim_map[orig_ref] = result
    
    return verbatim_map
