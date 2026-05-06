"""
In-text citation extraction using regex patterns.
Handles multi-citation blocks, formatting irregularity detection, and reference section splitting.
"""
import re

# ─── PYTHON-GUIDED CITATION EXTRACTION ───

# Reusable pattern components
# Surname prefix — comprehensive list covering Dutch, German, French, Italian,
# Spanish, Portuguese, Arabic, Hebrew, Irish/Scottish, Scandinavian, Armenian naming.
# Uses (?-i:...) to enforce case sensitivity even when outer pattern uses re.IGNORECASE.
_SPREFIX = (
    r"(?:(?<![a-zA-Z])(?:Van|Von|Den|Der|Het|Ter|Ten|Uit|Del|Dos|Das|Los|Las|Dei|Bin|Ibn|Abu|Bat|Mac|San|Ben|"
    r"Delle|Della|Degli|De|Di|Da|Du|Le|La|Lo|Li|Al|El|Af|Av|Ap|Op|Ul|Mc|"
    r"van|von|den|der|het|ter|ten|uit|del|dos|das|los|las|dei|bin|ibn|abu|bat|mac|san|ben|"
    r"delle|della|degli|de|di|da|du|le|la|lo|li|al|el|af|av|ap|op|ul|mc)"
    r"(?:\s+(?:der|den|de|het|la|las|los|le|di))?\s+)?"
)
_SNAME = _SPREFIX + r"(?:(?-i:[A-Z\u00C0-\u00D6\u00D8-\u00DD])['\u2019])?(?-i:[A-Z\u00C0-\u00D6\u00D8-\u00DD])[a-z\u00E0-\u00F6\u00F8-\u00FF]+(?:['\u2019\-\u2013\u2014](?-i:[A-Z\u00C0-\u00D6\u00D8-\u00DD])?[a-z\u00E0-\u00F6\u00F8-\u00FF]+)*"
# Year or n.d. or "no date"
_YEAR = r"(?:\d{4}[a-z]?|n\.d\.|no date)"
# Multi-word corporate author
_CORP = r"(?:(?-i:[A-Z\u00C0-\u00D6])[A-Za-z\u00C0-\u00F6'\-]*\s+)+(?:(?:and|of|for|the)\s+)*(?-i:[A-Z\u00C0-\u00D6])[A-Za-z\u00C0-\u00F6'\-]*(?:\s+(?:(?:and|of|for|the)\s+)*(?-i:[A-Z\u00C0-\u00D6])[A-Za-z\u00C0-\u00F6'\-]*)*"

# Phase 1: Detect multi-citation blocks (parens with semicolons + years)
MULTI_CITATION_PATTERN = re.compile(
    r'\([^()]*\b\d{4}[a-z]?\b[^()]*;[^()]*\b\d{4}[a-z]?\b[^()]*\)',
    re.IGNORECASE
)

# Phase 2: Individual citation patterns (most specific first)
CITATION_PATTERNS = [
    # ── Author-Date Parenthetical ──
    # Org abbreviation: (WHO, 2020) or (CDC, 2020) or (WHO, n.d.)
    (re.compile(rf'\(\s*(?-i:[A-Z]){{2,}}[,.\s]+{_YEAR}\s*\)', re.IGNORECASE), 'ORG_ABBREV'),

    # With initials: (J. Smith, 2020)
    (re.compile(rf'\(\s*[A-Z]\.\s+{_SNAME}[,.\s]+{_YEAR}\s*\)', re.IGNORECASE), 'INITIALS'),

    # Et al.: (Stokes-Parish et al., 2020) or (Dall'Ora et al., 2019, p. 45)
    (re.compile(rf'\(\s*{_SNAME}\s+et\s+al\.?\s*[,.\s]*{_YEAR}(?:[,.\s]+pp?\.\s*[\d\-\u2013]+)?\s*\)', re.IGNORECASE), 'PAR_ETAL'),

    # Two authors (and/&): (Smith and Jones, 2020) or (Smith & Jones, 2020)
    (re.compile(rf'\(\s*{_SNAME}\s+(?:and|&)\s+{_SNAME}[,.\s]+{_YEAR}(?:[,.\s]+pp?\.\s*[\d\-\u2013]+)?\s*\)', re.IGNORECASE), 'PAR_TWO'),

    # Secondary referencing: (Ecott, 2002, cited in Wilson, 2009)
    (re.compile(rf'\(\s*{_SNAME}(?:\s+et\s+al\.?)?\s*[,.\s]*{_YEAR}[,.\s]+(?:cited|quoted)\s+in\s+{_SNAME}(?:\s+et\s+al\.?)?\s*[,.\s]*{_YEAR}(?:[,.\s]+pp?\.\s*[\d\-\u2013]+)?\s*\)', re.IGNORECASE), 'PAR_SECONDARY'),

    # Multi-word corporate parenthetical: (NHS England, 2025)
    (re.compile(rf'\(\s*{_CORP}[,.\s]+{_YEAR}(?:[,.\s]+pp?\.\s*[\d\-\u2013]+)?\s*\)', re.IGNORECASE), 'PAR_CORP'),

    # Single author with optional page: (Smith, 2020) or (Smith, 2020, p. 45)
    (re.compile(rf'\(\s*{_SNAME}[,.\s]+{_YEAR}(?:[,:.\s]+(?:pp?\.\s*)?[\d\-\u2013]+)?\s*\)', re.IGNORECASE), 'PAR_SINGLE'),

    # ── Author-Date Narrative ──
    # Et al. narrative: Stokes-Parish et al. (2020) or Stokes-Parish et al.'s (2020)
    (re.compile(rf'{_SNAME}\s+et\s+al\.?(?:[\'’]s?)?[,.\s]*\({_YEAR}(?:[,.\s]+pp?\.\s*[\d\-\u2013]+)?\)', re.IGNORECASE), 'NAR_ETAL'),

    # Two authors narrative: Smith and Jones (2020) or Smith and Jones's (2020)
    (re.compile(rf'{_SNAME}\s+(?:and|&)\s+{_SNAME}(?:[\'’]s?)?[,.\s]*\({_YEAR}(?:[,.\s]+pp?\.\s*[\d\-\u2013]+)?\)', re.IGNORECASE), 'NAR_TWO'),

    # Multi-word corporate narrative: NHS England's (2025)
    (re.compile(rf'{_CORP}(?:[\'’]s?)?[,.\s]*\({_YEAR}(?:[,.\s]+pp?\.\s*[\d\-\u2013]+)?\)', re.IGNORECASE), 'NAR_CORP'),

    # Single author narrative: Smith's (2020)
    (re.compile(rf'{_SNAME}(?:[\'’]s?)?[,.\s]*\({_YEAR}(?:[,.\s]+pp?\.\s*[\d\-\u2013]+)?\)', re.IGNORECASE), 'NAR_SINGLE'),

    # ── Numbered Styles (Vancouver/IEEE) ──
    # Mixed/multiple numbers: [1, 3-5, 7]
    (re.compile(r'\[\d+(?:\s*[,\-\u2013]\s*\d+)+\]', re.IGNORECASE), 'NUM_MIXED'),

    # Single number: [1]
    (re.compile(r'\[\d+\]', re.IGNORECASE), 'NUM_SINGLE'),

    # ── MLA Style (Author Page) ──
    # (Smith 45) or (Smith 45-67)
    (re.compile(rf'\(\s*{_SNAME}\s+\d+(?:\s*[\-\u2013]\s*\d+)?\s*\)', re.IGNORECASE), 'MLA_PAGE'),
]

# Patterns to match individual citations inside multi-citation blocks (after semicolon split)
INNER_CITATION_PATTERNS = [
    # Org abbreviation: WHO, 2020
    (re.compile(rf'^\s*(?-i:[A-Z]){{2,}}[,.\s]+{_YEAR}\s*$', re.IGNORECASE), 'ORG_ABBREV'),
    # Et al.: Stokes-Parish et al., 2020
    (re.compile(rf'^\s*{_SNAME}\s+et\s+al\.?\s*[,.\s]*{_YEAR}', re.IGNORECASE), 'PAR_ETAL'),
    # Two authors: Smith and Jones, 2020
    (re.compile(rf'^\s*{_SNAME}\s+(?:and|&)\s+{_SNAME}[,.\s]+{_YEAR}', re.IGNORECASE), 'PAR_TWO'),
    # Multi-word corporate: NHS England, 2025
    (re.compile(rf'^\s*{_CORP}[,.\s]+{_YEAR}', re.IGNORECASE), 'PAR_CORP'),
    # Single author: Smith, 2020
    (re.compile(rf'^\s*{_SNAME}[,.\s]+{_YEAR}', re.IGNORECASE), 'PAR_SINGLE'),
    # Just a year (same author continuation): 2020
    (re.compile(r'^\s*\d{4}[a-z]?\s*$', re.IGNORECASE), 'YEAR_ONLY'),
]


def extract_reference_section(full_text: str) -> tuple:
    """
    Split the document into body text and reference section.
    Returns (body_text, reference_text).
    """
    # Patterns ordered from most specific to least specific.
    # Use re.MULTILINE so ^ matches start of every line.
    # "references?" matches both "Reference" (singular) and "References" (plural).
    ref_heading_patterns = [
        # Standard: heading on its own line with newlines around it
        r'(?i)\n\s*(references?|bibliography|works\s+cited|reference\s+list)\s*\n',
        # Heading on its own line (MULTILINE ^...$) — catches missing trailing \n
        r'(?im)^\s*(references?|bibliography|works\s+cited|reference\s+list)\s*$',
        # Heading at start of text (no leading \n)
        r'(?i)^\s*(references?|bibliography|works\s+cited|reference\s+list)\s*\n',
        # Heading followed directly by content (no trailing newline)
        r'(?i)\n\s*(references?|bibliography|works\s+cited|reference\s+list)\s*(?=\S)',
    ]
    
    for pattern in ref_heading_patterns:
        match = re.search(pattern, full_text)
        if match:
            body = full_text[:match.start()]
            refs = full_text[match.end():]
            return (body, refs)
    
    # Fallback: if no heading found, return full text as body
    return (full_text, "")


def check_formatting_irregularities(citation_text: str) -> list:
    warnings = []
    
    # Check lowercase names (no capital letters at start of words)
    # Use apostrophe-aware tokenising so surnames like Ng'andu stay intact
    words = re.findall(r"\b[a-zA-Z]+(?:'[a-zA-Z]+)*\b", citation_text)
    lower_words = [w for w in words if w.islower() and w.lower() not in ('et', 'al', 'and', 'in', 'cited', 'quoted', 'pp', 'p', 's', 'the', 'of', 'for', 'a', 'an', 'nd', 'no', 'date', 'v', 'vol', 'issue', 'org', 'who', 'cdc')]
    if lower_words:
        warnings.append(f"Potential uncapitalized author name/word: {', '.join(lower_words)}")
        
    # Check weird punctuation before the year (e.g., dot instead of comma)
    if re.search(r'\.\s*\d{4}', citation_text) and not re.search(r'al\.?\s*\d{4}', citation_text):
        warnings.append("Used a period (.) instead of a comma before the year.")
        
    # Check lack of space after comma
    if re.search(r',\d{4}', citation_text):
        warnings.append("Missing space after comma before the year.")
        
    # Check multiple spaces
    if re.search(r'\s{2,}', citation_text):
        warnings.append("Irregular spacing (multiple consecutive spaces).")
        
    # Check comma before parenthesis in narrative: "Name, (2020)"
    if re.search(r',\s*\(', citation_text):
        warnings.append("Extra comma before the opening parenthesis.")

    # Check missing comma after "et al." before year in parenthetical: (Author et al. 2019)
    if citation_text.startswith('(') and re.search(r'et\s+al\.\s+\d{4}', citation_text):
        warnings.append('Missing comma after "et al." before the year — should be "et al., 2020".')
        
    return warnings


def detect_document_consistency_issues(citations_list: list) -> list:
    """
    Analyze all extracted citations for document-wide consistency issues.
    Detects mixed usage of connectors (and/&), et al. comma placement, etc.
    Returns a list of warning dicts with type, details, and grouped examples.
    """
    warnings = []

    # ── Track usage patterns ──
    # Parenthetical two-author: and vs & (only compare within same form)
    par_and = []    # Parenthetical using "and": (Smith and Jones, 2020)
    par_amp = []    # Parenthetical using "&":   (Smith & Jones, 2020)
    # Narrative two-author: "and" is always correct; "&" is wrong
    nar_amp = []    # Narrative using "&" (incorrect): Smith & Jones (2020)

    etal_comma = []      # "et al.," (comma after period, inside parenthetical)
    etal_no_comma = []   # "et al." (no comma, inside parenthetical)
    etal_missing_period = []  # "et al" without period

    for cit in citations_list:
        text = cit.get("text", "")
        cit_type = cit.get("type", "")

        # ── and vs & (separated by citation form) ──
        if cit_type == 'PAR_TWO':
            if re.search(r'\band\b', text, re.IGNORECASE):
                par_and.append(text)
            elif '&' in text:
                par_amp.append(text)
        elif cit_type == 'NAR_TWO':
            # In narrative, "and" is always correct — only flag "&"
            if '&' in text:
                nar_amp.append(text)

        # ── et al. comma consistency (parenthetical only) ──
        if cit_type in ('PAR_ETAL',) and 'et al' in text.lower():
            if re.search(r'et\s+al\.,', text):
                etal_comma.append(text)
            elif re.search(r'et\s+al\.\s', text):
                etal_no_comma.append(text)

        # ── et al without period ──
        if re.search(r'et\s+al(?!\.)', text):
            etal_missing_period.append(text)

    # ── Flag inconsistencies ──

    # Parenthetical-only and/& mixing: (A and B, 2020) vs (C & D, 2021)
    if par_and and par_amp:
        warnings.append({
            'type': 'INCONSISTENT_CONNECTOR',
            'details': (
                f'Mixed use of "and" ({len(par_and)} citation{"s" if len(par_and) != 1 else ""}) '
                f'and "&" ({len(par_amp)} citation{"s" if len(par_amp) != 1 else ""}) '
                f'in parenthetical two-author citations. Use one form consistently.'
            ),
            'groups': [
                {'label': 'Uses "and"', 'count': len(par_and), 'examples': par_and[:3]},
                {'label': 'Uses "&"', 'count': len(par_amp), 'examples': par_amp[:3]},
            ],
        })

    # Narrative citations using "&" instead of "and"
    if nar_amp:
        warnings.append({
            'type': 'INCORRECT_NARRATIVE_AMPERSAND',
            'details': (
                f'{len(nar_amp)} narrative citation{"s" if len(nar_amp) != 1 else ""} '
                f'use{"s" if len(nar_amp) == 1 else ""} "&" instead of "and". '
                f'In narrative (in-text) citations, "and" is the correct connector.'
            ),
            'groups': [
                {'label': 'Should use "and"', 'count': len(nar_amp), 'examples': nar_amp[:3]},
            ],
        })

    if etal_comma and etal_no_comma:
        warnings.append({
            'type': 'INCONSISTENT_ET_AL_COMMA',
            'details': (
                f'Mixed use of "et al.," ({len(etal_comma)} citation{"s" if len(etal_comma) != 1 else ""}) '
                f'and "et al." without comma ({len(etal_no_comma)} citation{"s" if len(etal_no_comma) != 1 else ""}) '
                f'inside parenthetical citations. The comma placement after "et al." should be consistent.'
            ),
            'groups': [
                {'label': 'Has comma: "et al.,"', 'count': len(etal_comma), 'examples': etal_comma[:3]},
                {'label': 'No comma: "et al."', 'count': len(etal_no_comma), 'examples': etal_no_comma[:3]},
            ],
        })

    if etal_missing_period:
        warnings.append({
            'type': 'MISSING_ET_AL_PERIOD',
            'details': (
                f'"et al" appears without its period in {len(etal_missing_period)} '
                f'citation{"s" if len(etal_missing_period) != 1 else ""}. '
                f'It should always be written as "et al." (with a period).'
            ),
            'groups': [
                {'label': 'Missing period', 'count': len(etal_missing_period), 'examples': etal_missing_period[:3]},
            ],
        })

    return warnings


# ─── FALSE-POSITIVE FILTER ───────────────────────────────────────────────
# Reference list entries (e.g. "Serrano N. (2024)") look like corporate
# narrative citations to NAR_CORP because "Surname Initials" resembles a
# two-word organisation name.  This filter catches them.
_REF_ENTRY_FP = re.compile(
    r'^'
    r'(?:[A-Z][a-z\u00E0-\u00F6\u00F8-\u00FF]+(?:[\-\u2013][A-Z][a-z]+)*'
    r'(?:\s+(?:van|von|de|del|den|der|di|du|le|la|al|el|bin|ibn|mac|mc))*'
    r'\s+)'
    r'[A-Z]{1,4}\.'
    r'(?:\s*[A-Z]{1,4}\.)*'
    r'\s*[,.]?\s*'
    r'\(\d{4}',
)

# Bare initials leaked as a sub-match: "JM. (2024)" or "A. (2024)"
_BARE_INITIALS_FP = re.compile(
    r'^[A-Z]{1,4}\.'
    r'(?:\s*[A-Z]{1,4}\.)*'
    r'\s*[,.]?\s*'
    r'\(\d{4}',
)

# Common parenthetical labels that are NOT citations.
# e.g. (Wave 1), (Part 2), (Phase 3), (Group A), (Cohort 2)
_NON_CITATION_LABEL = re.compile(
    r'^\(\s*(?:Wave|Part|Phase|Step|Stage|Group|Section|Chapter|Item|'
    r'Option|Type|Level|Round|Trial|Version|Cohort|Arm|Cycle|Block|'
    r'Panel|Module|Unit|Band|Grade|Tier|Batch|Run|Test|Experiment|'
    r'Session|Period|Quarter|Volume|Issue|Edition|Series|Supplement|'
    r'Appendix|Table|Figure|Equation|Example|Sample|Case|Model|'
    r'Scenario|Condition|Study|Domain|Factor|Cluster|Theme|Track|'
    r'Stream|Zone|Area|Region|Site|Page|Strand|Category|Set)'
    r'\s+[\dA-Za-z]',
    re.IGNORECASE
)

# Parenthetical date ranges that are NOT citations.
# e.g. (July-August 2020), (March-April 2021), (Jan-Mar 2019)
_MONTH = (r'(?:January|February|March|April|May|June|July|August|September|'
          r'October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)')
_DATE_RANGE_FP = re.compile(
    r'^\(\s*' + _MONTH + r'\s*[-]\s*' + _MONTH,
    re.IGNORECASE
)

def _looks_like_ref_entry(citation_text: str, ctype: str) -> bool:
    """
    Returns True when a matched 'citation' is almost certainly a reference-
    list entry rather than a genuine in-text citation.

    Harvard/APA reference entries start with  Surname, I. (YEAR)  or
    Surname IM. (YEAR).  The NAR_CORP pattern misreads "Surname I." as a
    two-word corporate name.  Also catches bare-initial fragments like
    "JM. (2024)" that leak when the full match was already filtered.
    """
    if ctype not in ('NAR_CORP', 'NAR_SINGLE'):
        return False
    return bool(_REF_ENTRY_FP.search(citation_text) or
                _BARE_INITIALS_FP.search(citation_text))


def extract_citations_regex(body_text: str) -> list:
    """
    Extract all in-text citations from the body text using regex patterns.
    Uses two-phase approach for multi-citations:
      Phase 1: detect multi-citation blocks, split by semicolon
      Phase 2: match individual citations against single patterns
    
    Returns list of dicts: [{"text": "(Smith, 2020)", "type": "PAR_SINGLE", "irregularities": [...]}, ...]
    """
    found_citations = []

    # Normalize common Unicode variants and invisible field-code chars from PDF/DOCX
    body_text = body_text.replace('\u00a0', ' ')      # non-breaking space -> space
    body_text = body_text.replace('\u202f', ' ')      # narrow no-break space -> space
    body_text = body_text.replace('\u2006', ' ')      # thin space
    body_text = body_text.replace('\u2009', ' ')      # thin space
    body_text = body_text.replace('\u200b', '')       # zero-width space
    body_text = body_text.replace('\u200c', '')       # zero-width non-joiner
    body_text = body_text.replace('\u200d', '')       # zero-width joiner
    body_text = body_text.replace('\u2018', "'")      # left single quote -> apostrophe
    body_text = body_text.replace('\u2019', "'")      # right single quote -> apostrophe
    body_text = body_text.replace('\u201c', '"')      # left double quote -> quote
    body_text = body_text.replace('\u201d', '"')      # right double quote -> quote
    body_text = body_text.replace('\u2013', '-')      # en-dash -> hyphen
    body_text = body_text.replace('\u2014', '-')      # em-dash -> hyphen
    body_text = body_text.replace('\ufb01', 'fi')     # fi ligature
    body_text = body_text.replace('\ufb02', 'fl')     # fl ligature

    # Collapse newlines inside parentheses to spaces.
    # PDF extractors preserve visual line breaks from justified text, so a
    # citation like (UK Data Service, 2026a) can appear as (UK Data\nService, 2026a).
    body_text = re.sub(r'\(([^()]*)\)', lambda m: '(' + m.group(1).replace('\n', ' ') + ')', body_text)

    seen_texts = set()  # Deduplication
    
    # Track positions already matched to avoid double-matching
    matched_spans = []
    
    def is_overlapping(start, end):
        for s, e in matched_spans:
            if start < e and end > s:
                return True
        return False
    
    # ─── Filter out document cross-references ───
    cross_ref_pattern = re.compile(
        r'\(\s*(?:Table|Tab\.|Figure|Fig\.|Appendix|App\.)\s+[A-Za-z0-9]+'
        r'(?:\s*(?:,|and|&)?\s*(?:Table|Tab\.|Figure|Fig\.|Appendix|App\.)?\s*[A-Za-z0-9]+)*\s*\)', 
        re.IGNORECASE
    )
    for match in cross_ref_pattern.finditer(body_text):
        matched_spans.append((match.start(), match.end()))
        
    # Phase 1: Find and split multi-citation blocks
    for match in MULTI_CITATION_PATTERN.finditer(body_text):
        if is_overlapping(match.start(), match.end()):
            continue
        matched_spans.append((match.start(), match.end()))
        
        full_block = match.group(0)
        # Strip outer parentheses and split by semicolon
        inner = full_block[1:-1]  # Remove ( and )
        parts = [p.strip() for p in inner.split(';')]
        
        last_author = None  # Track author for YEAR_ONLY inheritance

        for part in parts:
            part_clean = part.strip()
            if not part_clean:
                continue
            
            # Try to classify each piece
            classified = False
            for pattern, label in INNER_CITATION_PATTERNS:
                if pattern.search(part_clean):
                    # For YEAR_ONLY, inherit author from previous citation in same block
                    if label == 'YEAR_ONLY' and last_author:
                        citation_text = f"({last_author}, {part_clean})"
                    else:
                        citation_text = f"({part_clean})"
                        # Extract author for potential YEAR_ONLY inheritance
                        author_match = re.match(r'^(.+?)\s*[,.]?\s*\d{4}', part_clean)
                        if author_match:
                            last_author = author_match.group(1).strip().rstrip(',')
                    if citation_text not in seen_texts:
                        warnings = check_formatting_irregularities(citation_text)
                        found_citations.append({"text": citation_text, "type": label, "irregularities": warnings})
                        seen_texts.add(citation_text)
                    classified = True
                    break
            
            # If no inner pattern matched but it has a year, still include it
            if not classified and re.search(r'\d{4}', part_clean):
                citation_text = f"({part_clean})"
                if citation_text not in seen_texts:
                    warnings = check_formatting_irregularities(citation_text)
                    found_citations.append({"text": citation_text, "type": "UNKNOWN", "irregularities": warnings})
                    seen_texts.add(citation_text)
    
    # Phase 2: Find standalone citations
    for pattern, label in CITATION_PATTERNS:
        for match in pattern.finditer(body_text):
            if is_overlapping(match.start(), match.end()):
                continue
            
            citation_text = match.group(0).strip()

            # Reject reference-list entries that leaked into body text.
            # Still consume the span so sub-matches can't leak through.
            if _looks_like_ref_entry(citation_text, label):
                matched_spans.append((match.start(), match.end()))
                continue

            # Reject date ranges: (July-August 2020), (March-April 2021)
            if _DATE_RANGE_FP.search(citation_text):
                matched_spans.append((match.start(), match.end()))
                continue

            # Reject common parenthetical labels mismatched as MLA_PAGE.
            # e.g. (Wave 1), (Part 2), (Phase 3)
            if label == 'MLA_PAGE' and _NON_CITATION_LABEL.search(citation_text):
                matched_spans.append((match.start(), match.end()))
                continue
            
            matched_spans.append((match.start(), match.end()))
            
            if citation_text not in seen_texts:
                warnings = check_formatting_irregularities(citation_text)
                found_citations.append({"text": citation_text, "type": label, "irregularities": warnings})
                seen_texts.add(citation_text)
    
    return found_citations
