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
        match = re.search(r'^([A-Za-z\'\-]+)', core)
        if match:
            surname = match.group(1).strip()
            surname = re.sub(r'\s+[A-Z]{1,3}$', '', surname).strip()
            return surname
        return None

    def extract_year(text):
        """Extract the first 4-digit year found in a string."""
        m = re.search(r'\b(19|20)\d{2}\b', text)
        return m.group(0) if m else None

    # Build compound-key index
    ref_compound_index = {}
    ref_surname_index = {}

    for ref in references:
        ref_surname = extract_first_author(ref)
        if not ref_surname:
            continue
        ref_year = extract_year(ref)
        key = (ref_surname.lower(), ref_year)
        ref_compound_index.setdefault(key, []).append(ref)
        ref_surname_index.setdefault(ref_surname.lower(), []).append(ref)

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

        cit_year = extract_year(cit)

        # 1. Try compound key (surname + year)
        compound_key = (cit_surname.lower(), cit_year)
        candidates = ref_compound_index.get(compound_key, [])

        # 2. If no year in citation, fall back to surname-only match
        if not candidates:
            candidates = ref_surname_index.get(cit_surname.lower(), [])

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


def extract_verbatim_references(full_text: str, ai_references: list) -> dict:
    """
    For each reference identified by the AI, find the closest verbatim match
    in the original document text. Includes safeguards against DOI bleeding
    and cross-reference mixups.
    
    Returns a dict mapping AI reference -> verbatim source text with confidence.
    """
    # ─── PRE-STEP: Clean Invisible Garbage (Docs/PDFs) ───
    full_text = full_text.replace('\u00a0', ' ')      # non-breaking space
    full_text = full_text.replace('\u202f', ' ')      # narrow no-break space
    full_text = full_text.replace('\u2006', ' ')      # thin space
    full_text = full_text.replace('\u2009', ' ')      # thin space
    full_text = full_text.replace('\u200b', '')       # zero-width space
    full_text = full_text.replace('\u200c', '')       # zero-width non-joiner
    full_text = full_text.replace('\u200d', '')       # zero-width joiner
    full_text = full_text.replace('\u2018', "'")      # left single quote
    full_text = full_text.replace('\u2019', "'")      # right single quote
    full_text = full_text.replace('\u201c', '"')      # left double quote
    full_text = full_text.replace('\u201d', '"')      # right double quote
    full_text = full_text.replace('\u2013', '-')      # en-dash -> hyphen
    full_text = full_text.replace('\u2014', '-')      # em-dash -> hyphen
    full_text = full_text.replace('\ufb01', 'fi')     # fi ligature
    full_text = full_text.replace('\ufb02', 'fl')     # fl ligature

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
        r'|\[\d+\]'
        r'|\d+\.\s+[A-Z]'
        r'|[A-Z][a-zA-Zà-öø-ÿ\'\-]+\s+\('
        r'|[A-Z]\.?\s*,?\s*\('
        r'|[A-Z]\.?\s*,'
        r'|\(\d{4}\)'
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
            is_org_name = bool(has_year.search(stripped[:80]))
        
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
        author_match = re.match(r'^[^a-z]*?([A-Z][a-zA-Zà-öø-ÿ\'\-]+)', text.strip())
        if author_match:
            author = author_match.group(1).lower()
        year_match = re.search(r'\b(19|20)\d{2}\b', text)
        if year_match:
            year = year_match.group(0)
        return (author, year)
    
    verbatim_map = {}
    used_candidates = {}
    
    for ai_ref in ai_references:
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
            
            author_ok = (not ai_author) or (not cand_author) or (ai_author == cand_author)
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
        
        used_candidates[ai_ref] = best_match
        
        result = {
            "verbatim": best_match,
            "confidence": round(best_score, 2)
        }
        if conflict:
            result["conflict"] = conflict
        
        verbatim_map[ai_ref] = result
    
    return verbatim_map
