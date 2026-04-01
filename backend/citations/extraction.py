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
    r"(?:(?:Van|Von|Den|Der|Het|Ter|Ten|Uit|Del|Dos|Das|Los|Las|Dei|Bin|Ibn|Abu|Bat|Mac|San|Ben|"
    r"Delle|Della|Degli|De|Di|Da|Du|Le|La|Lo|Li|Al|El|Af|Av|Ap|Op|Ul|Mc|"
    r"van|von|den|der|het|ter|ten|uit|del|dos|das|los|las|dei|bin|ibn|abu|bat|mac|san|ben|"
    r"delle|della|degli|de|di|da|du|le|la|lo|li|al|el|af|av|ap|op|ul|mc)"
    r"(?:\s+(?:der|den|de|het|la|las|los|le|di))?\s+)?"
)
_SNAME = _SPREFIX + r"(?-i:[A-Z\u00C0-\u00D6])[a-z\u00E0-\u00F6]+(?:['\u2019\-\u2013\u2014](?-i:[A-Z\u00C0-\u00D6])?[a-z\u00E0-\u00F6]+)*"
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
    # Et al. narrative: Stokes-Parish et al. (2020)
    (re.compile(rf'{_SNAME}\s+et\s+al\.?[,.\s]*\({_YEAR}(?:[,.\s]+pp?\.\s*[\d\-\u2013]+)?\)', re.IGNORECASE), 'NAR_ETAL'),

    # Two authors narrative: Smith and Jones (2020)
    (re.compile(rf'{_SNAME}\s+(?:and|&)\s+{_SNAME}[,.\s]*\({_YEAR}(?:[,.\s]+pp?\.\s*[\d\-\u2013]+)?\)', re.IGNORECASE), 'NAR_TWO'),

    # Multi-word corporate narrative: NHS England (2025)
    (re.compile(rf'{_CORP}[,.\s]*\({_YEAR}(?:[,.\s]+pp?\.\s*[\d\-\u2013]+)?\)', re.IGNORECASE), 'NAR_CORP'),

    # Single author narrative: Smith (2020)
    (re.compile(rf'{_SNAME}[,.\s]*\({_YEAR}(?:[,.\s]+pp?\.\s*[\d\-\u2013]+)?\)', re.IGNORECASE), 'NAR_SINGLE'),

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
    ref_heading_patterns = [
        r'(?i)\n\s*(references|bibliography|works\s+cited|reference\s+list)\s*\n',
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
    words = re.findall(r'\b[a-zA-Z]+\b', citation_text)
    lower_words = [w for w in words if w.islower() and w.lower() not in ('et', 'al', 'and', 'in', 'cited', 'quoted', 'pp', 'p', 'the', 'of', 'for', 'a', 'an', 'nd', 'no', 'date', 'v', 'vol', 'issue', 'org', 'who', 'cdc')]
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
        
    return warnings


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
        
        for part in parts:
            part_clean = part.strip()
            if not part_clean:
                continue
            
            # Try to classify each piece
            classified = False
            for pattern, label in INNER_CITATION_PATTERNS:
                if pattern.search(part_clean):
                    citation_text = f"({part_clean})"
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
            if citation_text not in seen_texts:
                warnings = check_formatting_irregularities(citation_text)
                found_citations.append({"text": citation_text, "type": label, "irregularities": warnings})
                seen_texts.add(citation_text)
                matched_spans.append((match.start(), match.end()))
    
    return found_citations
