"""
Citation-to-reference verification, cross-validation, and verbatim reference extraction.
"""
import re
import unicodedata
from difflib import SequenceMatcher
from references.ref_list_verifier import split_and_heal_verifier_text_fallback, _extract_ref_section_simple


def verify_matches_with_string_search(in_text_citations, references):
    verification_results = {
        "confirmed_matches": [],
        "unmatched_citations": [],
        "unmatched_references": [],
        "duplicate_first_names": {},
        "disambiguation_warnings": [],
        "summary": "Surname + year compound-key match verification completed (case-insensitive)."
    }

    def extract_first_author(text):
        """Extract the first author's bare surname from a citation or reference string."""
        core = text.strip('()[] ').split(' et al.')[0].split(' and ')[0].strip()
        # Include diacritics (À-Ö, Ø-ö, ø-ÿ) and curly apostrophe \u2019
        # Allow compound surnames: space-separated words (e.g. "Bosó Pérez")
        _W = r'[A-Za-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u00FF\'\-\u2019]+'
        match = re.search(rf'^({_W}(?:\s+{_W})*)', core)
        if match:
            surname = match.group(1).strip()
            # Remove trailing initials like " R" from "Bosó Pérez, R."
            surname = re.sub(r'[,.]?\s+[A-Z\u00C0-\u00D6\u00D8-\u00DD]{1,3}$', '', surname).strip()
            surname = surname.rstrip(',').strip()
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
    ref_lastword_index = {}  # Fallback: index by last word of compound surname

    for ref in references:
        ref_surname = extract_first_author(ref)
        if not ref_surname:
            continue
        ref_year = extract_year(ref, mode='first')
        normalized_surname = ref_surname.lower().replace('\u2019', "'")
        key = (normalized_surname, ref_year)
        ref_compound_index.setdefault(key, []).append(ref)
        ref_surname_index.setdefault(normalized_surname, []).append(ref)
        # For compound surnames like "Bosó Pérez", also index by last word "pérez"
        surname_words = normalized_surname.split()
        if len(surname_words) > 1:
            last_word = surname_words[-1]
            ref_lastword_index.setdefault((last_word, ref_year), []).append(ref)

    # Report duplicate surnames
    for surname_lower, refs in ref_surname_index.items():
        if len(refs) > 1:
            verification_results["duplicate_first_names"][surname_lower.capitalize()] = refs

    # ─── Harvard disambiguation check ───────────────────────────────────
    # Detect same-author, same-base-year pairs in the reference list and
    # verify that both the references AND the in-text citations use proper
    # letter suffixes (2022a, 2022b) to distinguish them.
    # Group references by (surname, base_year) — ignoring any existing suffix
    base_year_groups = {}
    for (surname_lower, year_with_suffix), refs in ref_compound_index.items():
        if not year_with_suffix:
            continue
        base_year = year_with_suffix[:4]
        group_key = (surname_lower, base_year)
        base_year_groups.setdefault(group_key, []).extend(refs)

    for (surname_lower, base_year), refs in base_year_groups.items():
        if len(refs) < 2:
            continue
        # Multiple references share the same first author + year.
        # Check if the references themselves already use letter suffixes.
        ref_years = []
        for ref in refs:
            y = extract_year(ref, mode='first')
            ref_years.append(y)
        refs_have_suffixes = all(
            y and re.match(r'\d{4}[a-z]$', y)
            for y in ref_years
        )
        # Check if the citations targeting this author+year use suffixes.
        matching_citations = [
            c for c in in_text_citations
            if (extract_first_author(c) or '').lower().replace('\u2019', "'") == surname_lower
            and (extract_year(c, mode='last') or '')[:4] == base_year
        ]
        cits_have_suffixes = all(
            re.match(r'\d{4}[a-z]$', extract_year(c, mode='last') or '')
            for c in matching_citations
        ) if matching_citations else False

        display_name = surname_lower.capitalize()
        if not refs_have_suffixes and not cits_have_suffixes:
            # Neither references nor citations are disambiguated
            sorted_refs = sorted(refs)  # alphabetical by title for a/b assignment
            verification_results["disambiguation_warnings"].append({
                "type": "MISSING_DISAMBIGUATION",
                "author": display_name,
                "year": base_year,
                "references": sorted_refs,
                "message": (
                    f"Multiple references by {display_name} ({base_year}) detected. "
                    f"Harvard style requires letter suffixes to distinguish them. "
                    f"Please add '{base_year}a' and '{base_year}b' (etc.) to both "
                    f"the in-text citations and the reference list entries, "
                    f"assigning letters alphabetically by title."
                ),
            })
        elif refs_have_suffixes and not cits_have_suffixes and matching_citations:
            # References are disambiguated but citations are not
            verification_results["disambiguation_warnings"].append({
                "type": "CITATION_MISSING_SUFFIX",
                "author": display_name,
                "year": base_year,
                "references": refs,
                "citations": matching_citations,
                "message": (
                    f"References by {display_name} ({base_year}) use letter suffixes "
                    f"but the in-text citations do not. Update citations to use "
                    f"({display_name}, {base_year}a), ({display_name}, {base_year}b), etc."
                ),
            })
        elif not refs_have_suffixes and cits_have_suffixes:
            # Citations are disambiguated but references are not
            verification_results["disambiguation_warnings"].append({
                "type": "REFERENCE_MISSING_SUFFIX",
                "author": display_name,
                "year": base_year,
                "references": refs,
                "message": (
                    f"In-text citations use letter suffixes for {display_name} ({base_year}) "
                    f"but the reference list entries do not. Add the matching suffixes "
                    f"to the year in each reference entry."
                ),
            })

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

        # 3. Fallback: compound surname last-word match (e.g. "Pérez" matches "Bosó Pérez")
        if not candidates:
            candidates = ref_lastword_index.get((normalized_cit_surname, cit_year), [])

        # 4. If still nothing, fall back to surname-only match
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
        c_words = [w for w in re.sub(r'[^A-Za-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u00FF\s]', '', cit_author_clean).split() if len(w) > 2 and w.lower() not in ('and',)]
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
            # Include diacritical characters when extracting words
            r_words = [w for w in re.sub(r'[^A-Za-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u00FF\s]', '', ref_author_clean).split() if len(w) > 2 and w.lower() not in ('and',)]
            
            # Simple word overlap scoring
            matches = 0
            for cw in c_words:
                if any(SequenceMatcher(None, cw.lower(), rw.lower()).ratio() > 0.8 for rw in r_words):
                    matches += 1
            
            score = (matches / len(c_words)) if c_words else 0
            
            # Prefer year-matching references to avoid false DATE_MISMATCH on
            # same-author, different-year works (e.g. Dema et al. 2021 vs 2022).
            # Give a bonus to candidates whose base year matches the citation year.
            if ref_year == cit_year:
                score += 0.1  # Year-match bonus
            
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
            
            # Check Spelling Errors — normalize diacriticals before comparison

            def _strip_diacritics(s):
                """Remove diacritical marks: Ç→C, ü→u, é→e, etc."""
                nfkd = unicodedata.normalize('NFKD', s)
                return ''.join(c for c in nfkd if not unicodedata.combining(c))

            for cw in c_words:
                best_w_score = 0
                best_rw = None
                for rw in best_r_words:
                    # Compare with diacritics stripped for fair matching
                    cw_norm = _strip_diacritics(cw.lower())
                    rw_norm = _strip_diacritics(rw.lower())
                    # If normalized forms are identical, it's not a real mismatch
                    if cw_norm == rw_norm:
                        best_w_score = 1.0
                        best_rw = rw
                        break
                    w_score = SequenceMatcher(None, cw_norm, rw_norm).ratio()
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


def _split_ref_section_to_atomic(ref_section: str) -> list:
    """
    Split a reference section string into individual atomic reference entries.
    Handles multi-line references, merged entries, and various formatting styles.
    Returns a list of cleaned reference strings (entries > 20 chars).
    """
    # ── Known lowercase surname prefixes that start a NEW reference ──
    # These must not be swallowed by the catch-all `[a-z]` continuation rule.
    _LC_SURNAME_PREFIXES = (
        'de', 'del', 'della', 'di', 'du', 'da', 'das', 'dos', 'do',
        'van', 'von', 'vom',
        'el', 'al', 'bin', 'ibn', 'abd', 'abu',
        'la', 'le', 'les', 'lo',
        'mc', 'mac',
        'den', 'der', 'ter', 'ten',
        'op', 'het',
    )

    ref_start_pattern = re.compile(
        r'^(?:'
        r'[A-Z\u00C0-\u00D6\u00D8-\u00DD][a-zA-Z\u00C0-\u00D6\u00D8-\u00DD\u00E0-\u00F6\u00F8-\u00FF\'\-]+\s*,'
        r'|[A-Z\u00C0-\u00D6\u00D8-\u00DD][a-zA-Z\u00C0-\u00D6\u00D8-\u00DD\u00E0-\u00F6\u00F8-\u00FF\'\-]+\s+[A-Z\u00C0-\u00D6\u00D8-\u00DD]{1,4},'
        # Multi-word surname + initials: "Solberg Nes L," or "Van der Berg AB,"
        r'|[A-Z\u00C0-\u00D6\u00D8-\u00DD][a-zA-Z\u00C0-\u00D6\u00D8-\u00DD\u00E0-\u00F6\u00F8-\u00FF\'\-]+(?:\s+[A-Za-z\u00C0-\u00D6\u00D8-\u00DD\u00E0-\u00F6\u00F8-\u00FF][a-zA-Z\u00C0-\u00D6\u00D8-\u00DD\u00E0-\u00F6\u00F8-\u00FF\'\-]+)+\s+[A-Z\u00C0-\u00D6\u00D8-\u00DD]{1,4},'
        r'|\[\d+\]'
        r'|\d+\.\s+[A-Z]'
        r'|[A-Z\u00C0-\u00D6\u00D8-\u00DD][a-zA-Z\u00C0-\u00D6\u00D8-\u00DD\u00E0-\u00F6\u00F8-\u00FF\'\-]+\s+\('
        r'|[A-Z\u00C0-\u00D6\u00D8-\u00DD]\.?\s*,?\s*\('
        r'|[A-Z\u00C0-\u00D6\u00D8-\u00DD]\.?\s*,'
        r'|\(\d{4}\)'
        # Org-name references: "Department of Health. (2016)." or "World Health Organization. (2020)."
        r'|(?:[A-Z\u00C0-\u00D6\u00D8-\u00DD][a-zA-Z\u00C0-\u00D6\u00D8-\u00DD\u00E0-\u00F6\u00F8-\u00FF\'\-]+(?:\s+(?:of|for|the|and|on|in|&))?\s+)+[A-Z\u00C0-\u00D6\u00D8-\u00DD][a-zA-Z\u00C0-\u00D6\u00D8-\u00DD\u00E0-\u00F6\u00F8-\u00FF\'\-]+\.?\s*\(\d{4}'
        # All-caps abbreviation (2+ letters) followed by digit or letter: "GBD 2021 ...", "UNICEF (2020)", "NCD Risk ..."
        r'|[A-Z\u00C0-\u00D6\u00D8-\u00DD]{2,}\s+[\dA-Z]'
        # Lowercase-prefix surname: "de Vries, M.", "van der Berg, A.", "el-Sayed, A.", "al-Rashid, F."
        r'|(?:de|del|della|di|du|da|das|dos|do|van|von|vom|el|al|bin|ibn|abd|abu|la|le|les|lo|den|der|ter|ten|op|het)'
        r'(?:[\s\-]+(?:de|del|della|di|du|da|das|dos|do|van|von|vom|el|al|bin|ibn|abd|abu|la|le|les|lo|den|der|ter|ten|op|het))*'
        r'[\s\-]+[A-Z\u00C0-\u00D6\u00D8-\u00DD][a-zA-Z\u00C0-\u00D6\u00D8-\u00DD\u00E0-\u00F6\u00F8-\u00FF\'\-]+\s*,'
        # Digit-prefixed org: "3ie (2022)"
        r'|\d+[a-zA-Z]+\s*\(\d{4}'
        r')',
    )

    # Matches both mixed-case org starts ("Department of ...") and abbreviation starts ("GBD 2021 ...", "WHO ...")
    org_name_pattern = re.compile(r'^(?:[A-Z\u00C0-\u00D6\u00D8-\u00DD][a-zA-Z\u00C0-\u00D6\u00D8-\u00DD\u00E0-\u00F6\u00F8-\u00FF\'\-]+|[A-Z\u00C0-\u00D6\u00D8-\u00DD]{2,})\s+(?:[A-Z]|\d)')

    continuation_pattern = re.compile(
        r'^(?:'
        r'https?://'
        r'|[Dd]oi[\s.:]+'
        r'|[Aa]vailable\s+at'
        r'|[Aa]ccessed'
        r'|pp?\.\s*\d'
        r'|[Vv]ol\.|[Ii]ssue|[Rr]etrieved'
        r'|(?:The|A|An|In|On|Of|For|And|Their|Its|Effects?|Impact)\s'
        r'|["\'\u201c\u2018]'
        r')'
    )
    # Separate lowercase-start check — only treat as continuation if it's NOT
    # a known surname prefix or digit-prefixed org with a year nearby.
    _lc_prefixes_re = re.compile(
        r'^(?:'
        # Known surname prefixes followed by an uppercase surname: "de Vries," "van der Berg," "el-Sayed,"
        r'(?:' + '|'.join(_LC_SURNAME_PREFIXES) + r')'
        r'(?:[\s\-]+(?:' + '|'.join(_LC_SURNAME_PREFIXES) + r'))*'
        r'[\s\-]+[A-Z]'
        # OR digit-prefixed org with year in parens: "3ie (2022)"
        r'|\d+[a-zA-Z]+\s*\(\d{4}'
        r')',
        re.IGNORECASE
    )

    has_year = re.compile(r'\b(?:19|20)\d{2}\b')

    lines = ref_section.split('\n')
    atomic_refs = []
    current_ref_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        is_continuation = bool(continuation_pattern.match(stripped))
        force_new_ref = False  # Set when lowercase-start lines are positively identified as refs

        # Lowercase lines: treat as continuation UNLESS they match a known
        # surname-prefix or digit-prefixed org pattern AND contain a year,
        # OR they look like a standalone lowercase org name with a year.
        if not is_continuation and re.match(r'^[a-z\d]', stripped):
            if _lc_prefixes_re.match(stripped) and has_year.search(stripped[:200]):
                is_continuation = False  # Known prefix — this is a new ref
                force_new_ref = True
            elif re.search(r'\(\d{4}\)', stripped[:50]) and not line[0:1].isspace():
                # Lowercase org name with parenthesized year near the start:
                # "uk parliament (2019) ..." — strong signal for a standalone reference.
                # Guards: year must be within 50 chars (org names are short),
                # and the original line must NOT be indented (indentation = continuation).
                is_continuation = False
                force_new_ref = True
            else:
                is_continuation = True  # Default: lowercase start = continuation

        is_org_name = org_name_pattern.match(stripped) and not is_continuation
        if is_org_name:
            is_org_name = bool(has_year.search(stripped[:150]))

        is_new_ref = (ref_start_pattern.match(stripped) or is_org_name or force_new_ref) and not is_continuation

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
        r'(?:(?:[A-Z\u00C0-\u00D6\u00D8-\u00DD][a-zA-Z\u00C0-\u00D6\u00D8-\u00DD\u00E0-\u00F6\u00F8-\u00FF\'-]+|[a-z][a-z]+)[ \u00a0]+)*[A-Z\u00C0-\u00D6\u00D8-\u00DD][a-zA-Z\u00C0-\u00D6\u00D8-\u00DD\u00E0-\u00F6\u00F8-\u00FF\'-]+'
        r'\s*,?\s*(?:[A-Z\u00C0-\u00D6\u00D8-\u00DD][A-Z\u00C0-\u00D6\u00D8-\u00DD]?\.|[A-Z\u00C0-\u00D6\u00D8-\u00DD][A-Z\u00C0-\u00D6\u00D8-\u00DD]?[A-Z\u00C0-\u00D6\u00D8-\u00DD]?(?=\s*,|\s+&|\s+and|\s+et))'
        r'|\[\d+\]'
        r'|\d+\.\s+[A-Z]'
        # Demerge at all-caps abbreviation boundaries: "...doi GBD 2021 Diabetes"
        r'|[A-Z\u00C0-\u00D6\u00D8-\u00DD]{2,}\s+\d'
        # Demerge at org-name boundaries: "Nursing and Midwifery Council (NMC). (2018)."
        # Matches Title-Case multi-word name, optional (ABBR), then (YYYY).
        r'|(?:[A-Z\u00C0-\u00D6\u00D8-\u00DD][a-zA-Z\u00C0-\u00D6\u00D8-\u00DD\u00E0-\u00F6\u00F8-\u00FF]+(?:\s+(?:and|for|of|the|in|on|&)\s+|\s+)[A-Z\u00C0-\u00D6\u00D8-\u00DD][a-zA-Z\u00C0-\u00D6\u00D8-\u00DD\u00E0-\u00F6\u00F8-\u00FF]+(?:\s+[A-Za-z\u00C0-\u00D6\u00D8-\u00DD\u00E0-\u00F6\u00F8-\u00FF]+)*\s*(?:\([A-Z]+\))?\s*[.,]?\s*\(\d{4})'
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
                r'^(?:(?:[A-Z][a-zA-Z\u00e0-\u00f6\u00f8-\u00ff\'-]+|[a-z]{2,3})[ \u00a0]+)*[A-Z][a-zA-Z\u00e0-\u00f6\u00f8-\u00ff\'-]+\s*,?\s*[A-Z][A-Z]?\.'
                r'|\[\d+\]'
                r'|\d+\.\s+[A-Z]'
                r'|[A-Z]{2,}\s+\d'
                # Org-name start: "Nursing and Midwifery Council (NMC). (2018)"
                r'|[A-Z][a-zA-Z]+(?:\s+(?:and|for|of|the|in|on|&)\s+|\s+)[A-Z][a-zA-Z]+(?:\s+[A-Za-z]+)*\s*(?:\([A-Z]+\))?\s*[\.,]?\s*\(\d{4}', pt))

            if ends_like_ref and starts_like_ref and len(current_ref.strip()) >= 40:
                demerged_refs.append(current_ref.strip())
                current_ref = pt
            else:
                current_ref += " " + pt
        if current_ref.strip():
            demerged_refs.append(current_ref.strip())
    atomic_refs = demerged_refs

    # ─── SAFETY NET: split oversized entries that still contain merged refs ───
    # If an atomic ref is suspiciously long, it likely contains multiple
    # references that the primary splitter missed.  We look for embedded
    # reference-start boundaries (author+year patterns) and split there.
    safety_split_pattern = re.compile(
        r'(?<=\.)\s+'                  # split after a period + whitespace
        r'(?='
        # Standard author start: "Smith, A." / "Cu, A." / "Smith A."
        # Requires comma-or-whitespace before the initial to avoid false
        # positives on abbreviations like "GOV.UK" where the period is part
        # of the abbreviation (no space between "GOV" and ".UK").
        r'(?:[A-Z][a-zA-Z\u00e0-\u00f6\u00f8-\u00ff\'\-]+(?:\s*,\s+|\s+)[A-Z][A-Z]?\.)'
        # OR lowercase-prefix surname start: "de Vries, A."
        r'|(?:(?:de|del|della|di|du|da|van|von|el|al|bin|ibn|la|le|den|der|ter|ten)\s+[A-Z][a-zA-Z\u00e0-\u00f6\u00f8-\u00ff\'\-]+\s*,)'
        # OR org/abbreviation start with year within 150 chars
        r'|(?:[A-Z]{2,}\s+[\dA-Z])'
        # OR digit-prefixed org: "3ie (2022)"
        r'|(?:\d+[a-zA-Z]+\s*\(\d{4})'
        # OR numbered: "[1]" or "1. "
        r'|(?:\[\d+\])'
        r'|(?:\d+\.\s+[A-Z])'
        # OR org-name start: "Nursing and Midwifery Council (NMC). (2018)"
        r'|(?:[A-Z][a-zA-Z]+(?:\s+(?:and|for|of|the|in|on|&)\s+|\s+)[A-Z][a-zA-Z]+(?:\s+[A-Za-z]+)*\s*(?:\([A-Z]+\))?\s*[.,]?\s*\(\d{4})'
        r')'
    )
    # Pattern to detect fragments that start with "Available at", "Accessed",
    # URLs, etc. — these are NOT standalone references and should be merged back.
    accessed_only_year = re.compile(
        r'^\s*(?:Available\s+at|Accessed|Retrieved|https?://)'
        r'|^\s*\(?Accessed',
        re.IGNORECASE,
    )
    final_refs = []
    for ref in atomic_refs:
        if len(ref) > 300:
            parts = safety_split_pattern.split(ref)
            if len(parts) > 1:
                # Validate: only keep splits where both sides contain a year
                rebuilt = []
                for p in parts:
                    p = p.strip()
                    if not p:
                        continue
                    if rebuilt and not has_year.search(rebuilt[-1]):
                        # Previous chunk has no year — merge back
                        rebuilt[-1] = rebuilt[-1] + ' ' + p
                    else:
                        # If this fragment starts with "Available at" / URL /
                        # "Accessed" it's a continuation, not a new reference.
                        if rebuilt and accessed_only_year.match(p):
                            rebuilt[-1] = rebuilt[-1] + ' ' + p
                        else:
                            rebuilt.append(p)
                final_refs.extend(r for r in rebuilt if len(r) > 20)
            else:
                final_refs.append(ref)
        else:
            final_refs.append(ref)
    atomic_refs = final_refs

    return atomic_refs

def _reconcile_references(ref_section: str, extracted_refs: list) -> list:
    """
    Post-extraction reconciliation: guarantees no references are silently dropped.

    Uses two complementary techniques:
      1. Multi-signal control total — counts several independent reference
         anchors (DOIs, author patterns, numbered entries, parenthesized
         years, abbreviation starts) in the raw section and compares the
         maximum against extracted count.
      2. Character-span gap recovery — maps each extracted ref back to its
         position in the raw text, finds uncovered regions that contain
         reference-like content, and rescues them as recovered references.

    Returns the (possibly augmented) list of references.
    """
    has_year = re.compile(r'\b(?:19|20)\d{2}\b')

    # ── Step 1: Multi-signal control total ────────────────────────────────
    # Count several independent "reference anchor" signals in the raw text.
    # Each signal independently estimates how many references exist.
    # Taking the MAX across all signals gives the most robust expected count.

    lines = ref_section.split('\n')
    non_blank_lines = [ln.strip() for ln in lines if ln.strip()]

    # Continuation-line exclusion pattern (shared across signals)
    _continuation_re = re.compile(
        r'^(?:https?://|[Dd]oi[\s.:]|[Aa]vailable\s+at|[Aa]ccessed'
        r'|pp?\.\s*\d|[Vv]ol\.|[Ii]ssue|[Rr]etrieved'
        r'|(?:The|A|An|In|On|Of|For|And)\s[a-z])'
    )

    # ── Signal 1: DOI count ───────────────────────────────────────────────
    # Each DOI belongs to exactly one reference.  Count unique DOIs.
    doi_pattern = re.compile(r'(?:doi[:\s]+|doi\.org/)(\S+)', re.IGNORECASE)
    unique_dois = set()
    for ln in non_blank_lines:
        for m in doi_pattern.finditer(ln):
            # Normalize: strip trailing punctuation
            doi_val = m.group(1).rstrip('.,;)')
            unique_dois.add(doi_val.lower())
    doi_count = len(unique_dois)

    # ── Signal 2: Author-comma-initial pattern ────────────────────────────
    # "Surname, A." or "Surname, A. B." at the start of a non-continuation
    # line is a near-certain reference start (APA/Harvard).
    author_comma_re = re.compile(
        r'^(?:[A-Z][a-zA-Z\u00e0-\u00f6\u00f8-\u00ff\'\-]+\s*,\s*[A-Z]\.)'     # Standard: Smith, A.
        r'|^(?:(?:de|del|van|von|el|al|da|di)\s+[A-Z][a-zA-Z\'\-]+\s*,)'  # Prefix: de Vries, M.
    )
    author_count = 0
    for ln in non_blank_lines:
        if author_comma_re.match(ln) and not _continuation_re.match(ln):
            author_count += 1

    # ── Signal 3: Numbered entry count ────────────────────────────────────
    # Vancouver-style "[1]", "[2]", ... or "1. ", "2. " at line start.
    numbered_re = re.compile(r'^(?:\[\d+\]|\d+\.\s+[A-Z])')
    numbered_count = 0
    for ln in non_blank_lines:
        if numbered_re.match(ln):
            numbered_count += 1

    # ── Signal 4: Parenthesized year after author-like text ───────────────
    # "Author (YYYY)" pattern — the parenthesized year is highly specific
    # to reference starts in APA/Harvard.  Only count non-continuation lines
    # where the (YYYY) appears within the first 100 chars.
    paren_year_re = re.compile(
        r'^[A-Za-z\[\d(].*?\(\d{4}[a-z]?\)'
    )
    paren_year_count = 0
    for ln in non_blank_lines:
        if paren_year_re.match(ln[:100]) and not _continuation_re.match(ln):
            paren_year_count += 1

    # ── Signal 5: All-caps abbreviation start ─────────────────────────────
    # "GBD 2021 ...", "WHO (2020) ...", "NCD Risk ..." — org abbreviations
    # that start reference entries.
    abbrev_re = re.compile(r'^[A-Z]{2,}\s+[\dA-Z]')
    abbrev_count = 0
    for ln in non_blank_lines:
        if abbrev_re.match(ln) and has_year.search(ln[:150]):
            abbrev_count += 1

    # ── Determine expected count ──────────────────────────────────────────
    # Take the maximum across all signals.  Each signal independently
    # estimates the reference count; the highest is the most informative.
    signal_counts = {
        'doi': doi_count,
        'author_comma': author_count,
        'numbered': numbered_count,
        'paren_year': paren_year_count,
        'abbreviation': abbrev_count,
    }
    expected_starts = max(signal_counts.values())
    best_signal = max(signal_counts, key=signal_counts.get)

    actual_count = len(extracted_refs)

    if actual_count >= expected_starts:
        return extracted_refs  # No deficit — all refs accounted for

    print(f"[Reconciliation] Deficit: expected ~{expected_starts} refs "
          f"(best signal: {best_signal}={signal_counts[best_signal]}), "
          f"got {actual_count}. Signals: {signal_counts}. Scanning for gaps...")

    # ── Step 2: Character-span coverage map ───────────────────────────────
    # For each extracted ref, find where it sits in the raw section so we
    # can identify uncovered "gaps."
    ref_section_lower = ref_section.lower()
    claimed_ranges = []  # list of (start, end) positions in ref_section

    for ref in extracted_refs:
        # Use the first 60 non-whitespace chars as a search key
        ref_clean = ' '.join(ref.split())
        search_key = ref_clean[:min(60, len(ref_clean))].lower()
        if len(search_key) < 10:
            continue
        idx = ref_section_lower.find(search_key)
        if idx >= 0:
            # Estimate the full span
            end_idx = idx + len(ref_clean)
            # Clamp to section length
            end_idx = min(end_idx, len(ref_section))
            claimed_ranges.append((idx, end_idx))

    # Sort and merge overlapping ranges
    claimed_ranges.sort()
    merged = []
    for start, end in claimed_ranges:
        if merged and start <= merged[-1][1] + 5:  # small tolerance for whitespace
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    # ── Step 3: Find gaps containing unclaimed references ─────────────────
    gap_boundaries = []
    prev_end = 0
    for start, end in merged:
        if start > prev_end:
            gap_boundaries.append((prev_end, start))
        prev_end = end
    # Trailing gap
    if prev_end < len(ref_section):
        gap_boundaries.append((prev_end, len(ref_section)))

    # ── Step 4: Recover references from gaps ──────────────────────────────
    # Build a set of normalized keys for existing refs to deduplicate
    existing_keys = set()
    for ref in extracted_refs:
        # Normalize: lowercase, collapse whitespace, strip punctuation
        key = ' '.join(ref.lower().split())[:80]
        existing_keys.add(key)

    recovered = []
    for gap_start, gap_end in gap_boundaries:
        gap_text = ref_section[gap_start:gap_end].strip()

        if len(gap_text) < 25:
            continue
        if not has_year.search(gap_text):
            continue

        # The gap might contain one or more references — split it using
        # the same atomic splitter to handle multi-line gaps cleanly.
        gap_refs = _split_ref_section_to_atomic(gap_text)

        for gr in gap_refs:
            if len(gr) > 20 and has_year.search(gr):
                # Deduplicate: skip if this recovered ref already exists
                gr_key = ' '.join(gr.lower().split())[:80]
                if gr_key not in existing_keys:
                    recovered.append(gr)
                    existing_keys.add(gr_key)

    if recovered:
        print(f"[Reconciliation] Recovered {len(recovered)} reference(s):")
        for r in recovered:
            print(f"  + {r[:100]}{'...' if len(r) > 100 else ''}")
    else:
        print(f"[Reconciliation] No recoverable references found in gaps "
              f"(deficit may be from multi-year titles).")

    return extracted_refs + recovered


def extract_references_from_text(full_text: str) -> list:
    """
    Extract individual references from a document's full text.
    Finds the reference section, splits it into atomic entries, demerges
    any accidentally-joined references, and runs a reconciliation pass
    to guarantee no references are silently dropped.

    Returns a list of reference strings.
    """
    full_text = _normalize_text(full_text)

    # Isolate the reference section
    ref_section = _extract_ref_section_simple(full_text)
    if len(ref_section.strip()) < 100:
        ref_section = full_text

    # Primary extraction
    refs = _split_ref_section_to_atomic(ref_section)

    # Reconciliation: detect and recover any silently dropped references
    refs = _reconcile_references(ref_section, refs)

    return refs


def extract_verbatim_references(full_text: str, ai_references: list) -> dict:
    """
    For each reference in the provided list, find the closest verbatim match
    in the original document text. Matches directly against the raw reference
    section using a robust sequence alignment / word overlap sliding window
    search to completely avoid splitter dependency.
    
    Returns a dict mapping reference -> verbatim source text with confidence.
    """
    full_text = _normalize_text(full_text)
    original_ai_references = list(ai_references)
    ai_references_norm = [_normalize_text(r) for r in ai_references]

    # Isolate the references section (or use the full text if not found)
    ref_section = _extract_ref_section_simple(full_text)
    if len(ref_section.strip()) < 100:
        ref_section = full_text

    # Tokenize the ref_section into words and record their exact character positions
    words_in_doc = []
    word_pattern = re.compile(r'[a-zA-Z0-9\u00C0-\u00FF\u2019\']+')
    for m in word_pattern.finditer(ref_section):
        words_in_doc.append({
            "word": m.group(0).lower(),
            "start": m.start(),
            "end": m.end()
        })

    # Index by word for fast lookup
    word_to_indices = {}
    for idx, w_info in enumerate(words_in_doc):
        word_to_indices.setdefault(w_info["word"], []).append(idx)

    verbatim_map = {}
    used_candidates = {}

    for orig_ref, ai_ref in zip(original_ai_references, ai_references_norm):
        ai_ref_stripped = ai_ref.strip()
        ai_words = [m.group(0).lower() for m in word_pattern.finditer(ai_ref_stripped)]
        if not ai_words:
            # Fallback if no words tokenized
            verbatim_map[orig_ref] = {"verbatim": orig_ref, "confidence": 0.0}
            continue

        # Extract signature/anchor terms to search
        # 1. First 3 words (usually author surname(s))
        # 2. Publication year (if present)
        anchors = []
        for w in ai_words[:3]:
            if len(w) >= 2:
                anchors.append((w, 2.5 if w == ai_words[0] else 1.5))
        
        # Look for a 4-digit year in ai_words
        year_match = re.search(r'\b(19|20)\d{2}\b', ai_ref_stripped)
        if year_match:
            year_str = year_match.group(0)
            anchors.append((year_str, 2.0))

        # Look for other longer words in the middle to disambiguate
        # We can extract words of length >= 6 that aren't common stopwords
        stopwords = {"journal", "volume", "number", "pages", "article", "university", "press", "association", "http", "https", "www"}
        for w in ai_words[3:]:
            if len(w) >= 6 and w not in stopwords:
                anchors.append((w, 1.0))
                if len(anchors) >= 8:  # Limit signature words
                    break

        # Collect candidate starting positions in words_in_doc
        candidate_indices = set()
        for term, weight in anchors:
            indices = word_to_indices.get(term, [])
            for idx in indices:
                # If we matched an author name/start word, candidate starts near it
                # If we matched a year or title word, candidate starts some words before it
                if term in ai_words[:3]:
                    candidate_indices.add(max(0, idx - 5))
                else:
                    try:
                        ai_pos = ai_words.index(term)
                    except ValueError:
                        ai_pos = 10
                    candidate_indices.add(max(0, idx - ai_pos - 5))

        # If no candidate indices found, default to scanning everywhere (very rare)
        if not candidate_indices:
            first_word_indices = word_to_indices.get(ai_words[0], [])
            if first_word_indices:
                for idx in first_word_indices:
                    candidate_indices.add(max(0, idx - 5))
            else:
                candidate_indices = set(range(0, len(words_in_doc), 50))

        # Evaluate each candidate window
        best_score = 0.0
        best_window_info = None

        window_size = len(ai_words) + 15

        for start_w_idx in candidate_indices:
            end_w_idx = min(len(words_in_doc), start_w_idx + window_size)
            if start_w_idx >= len(words_in_doc) or end_w_idx <= start_w_idx:
                continue

            doc_subwords = [w["word"] for w in words_in_doc[start_w_idx:end_w_idx]]
            
            # Sequence match at word level
            sm = SequenceMatcher(None, ai_words, doc_subwords)
            ratio = sm.ratio()

            if ratio > best_score:
                best_score = ratio
                best_window_info = (start_w_idx, end_w_idx, sm)

        # Refine boundaries within the best window using sequence alignment blocks
        if best_window_info and best_score >= 0.25:
            start_w_idx, end_w_idx, sm = best_window_info
            doc_subwords = [w["word"] for w in words_in_doc[start_w_idx:end_w_idx]]
            matching_blocks = sm.get_matching_blocks()
            
            valid_blocks = [b for b in matching_blocks[:-1] if b.size > 0]
            if valid_blocks:
                first_block = valid_blocks[0]
                last_block = valid_blocks[-1]
                
                w_start_in_window = max(0, first_block.b - first_block.a)
                w_end_in_window = min(len(doc_subwords), last_block.b + last_block.size + (len(ai_words) - (last_block.a + last_block.size)))
                
                matched_w_start = start_w_idx + w_start_in_window
                matched_w_end = start_w_idx + w_end_in_window
                
                char_start = words_in_doc[matched_w_start]["start"]
                char_end = words_in_doc[matched_w_end - 1]["end"]
                
                # Recalculate confidence based on the trimmed matching segment
                matched_doc_words = [w["word"] for w in words_in_doc[matched_w_start:matched_w_end]]
                exact_sm = SequenceMatcher(None, ai_words, matched_doc_words)
                best_score = exact_sm.ratio()

                pre_text = ref_section[max(0, char_start - 25) : char_start]
                pre_match = re.search(r'(?:\[\d{1,3}\]|\b\d{1,3}\.)\s*$', pre_text)
                if pre_match:
                    char_start -= len(pre_match.group(0))

                verbatim_text = ref_section[char_start:char_end].strip()
                
                if len(verbatim_text) / max(1, len(ai_ref_stripped)) < 0.35:
                    verbatim_text = orig_ref
                    best_score = 0.0
            else:
                verbatim_text = orig_ref
                best_score = 0.0
        else:
            verbatim_text = orig_ref
            best_score = 0.0

        # Conflict detection
        conflict = None
        if verbatim_text in used_candidates.values():
            conflicting_ref = [k for k, v in used_candidates.items() if v == verbatim_text]
            conflict = f"Warning: This verbatim text was also matched by: {conflicting_ref[0][:50]}..."
        
        used_candidates[orig_ref] = verbatim_text
        
        result = {
            "verbatim": verbatim_text,
            "confidence": round(best_score, 2)
        }
        if conflict:
            result["conflict"] = conflict
        
        # Use original (un-normalized) reference string as key so the frontend
        # can look it up with the same key it received from the analysis.
        verbatim_map[orig_ref] = result
    
    return verbatim_map


def validate_extracted_references(references: list) -> dict:
    """
    Post-extraction quality validation layer.
    
    Scans every extracted reference for structural anomalies that indicate
    extraction errors (fragments, merges, missing fields).  Returns a dict
    with per-reference warnings and an overall health summary.
    
    Returns:
        {
            "warnings": { "<ref_text[:80]>": [{"type": str, "severity": str, "message": str}] },
            "health": {"total": int, "clean": int, "flagged": int, "flags": [str]}
        }
    """
    has_year = re.compile(r'\b(?:19|20)\d{2}\b')
    warnings = {}
    flagged_count = 0
    flag_types = set()
    
    for ref in references:
        ref_key = ref[:80]
        ref_warnings = []
        
        # ── Check 1: Fragment detection (too short) ───────────────────────
        # A real reference should be at least 40 characters.  Anything shorter
        # is almost certainly a fragment from an incorrect split.
        if len(ref) < 40:
            ref_warnings.append({
                "type": "fragment",
                "severity": "error",
                "message": f"Entry is only {len(ref)} characters — likely an incomplete fragment from a split error."
            })
            flag_types.add("fragment")
        
        # ── Check 2: Missing publication year ─────────────────────────────
        # Every valid reference should contain a 4-digit year (19xx or 20xx).
        if not has_year.search(ref):
            ref_warnings.append({
                "type": "no_year",
                "severity": "warning",
                "message": "No publication year (19xx/20xx) found — may be a continuation line or malformed entry."
            })
            flag_types.add("no_year")
        
        # ── Check 3: Suspiciously long (likely merged) ────────────────────
        # Most single references are under 400 characters.  If one is over
        # 500, it may contain multiple merged references.
        if len(ref) > 500:
            # Count how many year instances appear — multiple years strongly
            # suggest multiple merged references.
            year_matches = has_year.findall(ref)
            unique_years = set(year_matches)
            if len(year_matches) >= 3 or len(unique_years) >= 2:
                ref_warnings.append({
                    "type": "likely_merged",
                    "severity": "error",
                    "message": f"Entry is {len(ref)} chars with {len(year_matches)} year mentions ({', '.join(sorted(unique_years)[:4])}) — likely contains multiple merged references."
                })
                flag_types.add("likely_merged")
            else:
                ref_warnings.append({
                    "type": "long_entry",
                    "severity": "info",
                    "message": f"Entry is {len(ref)} characters — unusually long but may be legitimate (e.g., collaborative group)."
                })
        
        # ── Check 4: Missing title/content ────────────────────────────────
        # A reference with a year but very little text after the year is
        # likely truncated.
        if has_year.search(ref):
            year_match = has_year.search(ref)
            text_after_year = ref[year_match.end():]
            if len(text_after_year.strip()) < 10 and len(ref) < 80:
                ref_warnings.append({
                    "type": "truncated",
                    "severity": "warning",
                    "message": "Very little content after the publication year — entry may be truncated."
                })
                flag_types.add("truncated")
        
        if ref_warnings:
            warnings[ref_key] = ref_warnings
            flagged_count += 1
    
    return {
        "warnings": warnings,
        "health": {
            "total": len(references),
            "clean": len(references) - flagged_count,
            "flagged": flagged_count,
            "flags": sorted(flag_types)
        }
    }
