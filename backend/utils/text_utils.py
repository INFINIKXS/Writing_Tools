"""
Shared text utility functions: normalisation, DOI extraction, similarity, sentence case, page condensation.
"""
import re
import unicodedata
from difflib import SequenceMatcher


"""
Comprehensive DOI regex — matches ALL known academic DOI formats.

The pattern is used in two modes:
  1. PREFIXED mode (with a prefix like "doi:", "doi.org/", etc.) — high confidence.
  2. BARE mode (just "10.XXXX/...") — used as fallback when no prefix is found.

Known URL prefixes that precede a DOI:
  - https://doi.org/10.XXXX/...             (standard resolver)
  - https://dx.doi.org/10.XXXX/...          (legacy resolver)
  - https://search.informit.org/doi/10.XXXX/...  (Informit)
  - https://hdl.handle.net/10.XXXX/...      (Handle System)
  - https://www.tandfonline.com/doi/full/10.XXXX/...
  - https://onlinelibrary.wiley.com/doi/10.XXXX/...
  - https://link.springer.com/article/10.XXXX/...
  - https://journals.sagepub.com/doi/10.XXXX/...
  - https://www.sciencedirect.com/.../10.XXXX/...
  - doi: 10.XXXX/...
  - DOI: 10.XXXX/...
  - doi 10.XXXX/...

DOI suffix character class (per CrossRef spec):
  a-zA-Z0-9  .-_/:()
  Also seen in the wild: [], ;, #, @, !, ~, *, +, <, >, {}
  We use a conservative set and strip trailing junk.
"""

# ── Core DOI suffix pattern (shared across all regexes) ──
_DOI_SUFFIX = r'[a-zA-Z0-9.\-_/:()\\[\]<>#@!~*+]+'

# ── Prefixed DOI pattern — matches any known prefix before 10.XXXX/... ──
_DOI_PREFIXED_RE = re.compile(
    r'(?:'
    r'(?:https?://[^\s/]+/(?:[^\s/]+/)*)'   # Any URL with path segments ending at the DOI
    r'|'
    r'(?:\bdoi[:\s]+)'                       # "doi:" or "doi " text prefix
    r'|'
    r'(?:\bDOI[:\s]+)'                       # "DOI:" explicit
    r')'
    r'(10\.\d{4,9}/' + _DOI_SUFFIX + r')',
    re.IGNORECASE,
)

# ── Bare DOI pattern — matches raw "10.XXXX/..." without any prefix ──
_DOI_BARE_RE = re.compile(
    r'\b(10\.\d{4,9}/' + _DOI_SUFFIX + r')',
    re.IGNORECASE,
)

# ── Words/fragments that should never appear inside a real DOI suffix ──
_DOI_JUNK_TAIL_RE = re.compile(
    r'(?i)(?:Research|Article|Review|Copyright|Downloaded|Published|Available|Accessed|Retrieved'
    r'|Frontiers|Springer|Elsevier|Wiley|Nature|Science|Taylor|Francis|Oxford|Cambridge|PLOS'
    r'|Latest|Full|Text|HTML|PDF|Abstract|Supplement|Supporting|Information|Open|Access'
    r'|ACS|RSC|IEEE|ACM|BMC|BioMed|PubMed|CrossRef|Google|Scholar)\b.*$'
)

# ── Pattern to detect publisher/site names glued directly onto a DOI suffix ──
# Real DOI suffixes end in digits (e.g. "798962"). When a word like
# "frontiers" or "acs" gets concatenated without whitespace
# (e.g. "10.3389/frai.2021.798962frontiers"), this strips it.
# IMPORTANT: Only match alpha tails after a DIGIT — NOT after a dot or paren,
# because "10.1371/journal.pone.0294946" has legitimate alpha segments like "pone".
_DOI_TRAILING_ALPHA_RE = re.compile(
    r'(\d)([a-z]{5,})$',   # require 5+ chars (short segments like "pone" are real)
    re.IGNORECASE,
)


def _clean_doi(raw: str) -> str:
    """Normalise and clean a raw DOI match."""
    doi = raw.strip()
    # Strip trailing punctuation that isn't part of the DOI
    doi = doi.rstrip('.,;:)\'"]}> \t')
    # Remove garbage words that PDF text extractors append
    doi = _DOI_JUNK_TAIL_RE.sub('', doi).rstrip('.,;:) ')
    # Strip publisher/site names glued directly to the DOI suffix
    # e.g. "10.3389/frai.2021.798962frontiers" → "10.3389/frai.2021.798962"
    doi = _DOI_TRAILING_ALPHA_RE.sub(r'\1', doi)
    # Lowercase (DOIs are case-insensitive)
    return doi.lower()


def extract_doi(ref_string: str) -> str | None:
    """
    Extract and normalise a single DOI from a reference string.
    Tries prefixed patterns first (high confidence), then bare "10.XXXX/..." fallback.
    """
    m = _DOI_PREFIXED_RE.search(ref_string)
    if m:
        return _clean_doi(m.group(1))
    m = _DOI_BARE_RE.search(ref_string)
    if m:
        return _clean_doi(m.group(1))
    return None


def extract_all_dois(text: str) -> list[str]:
    """
    Extract ALL unique DOIs from a block of text (e.g. first 3 pages of a PDF).
    Returns a deduplicated list in order of appearance.
    """
    seen = set()
    results = []
    # First pass: prefixed DOIs (high confidence)
    for m in _DOI_PREFIXED_RE.finditer(text):
        doi = _clean_doi(m.group(1))
        if doi and doi not in seen:
            seen.add(doi)
            results.append(doi)
    # Second pass: bare DOIs
    for m in _DOI_BARE_RE.finditer(text):
        doi = _clean_doi(m.group(1))
        if doi and doi not in seen:
            seen.add(doi)
            results.append(doi)
    return results


def normalise_text(text):
    """Lowercase, remove accents, punctuation, and extra whitespace."""
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def title_similarity(t1, t2):
    return SequenceMatcher(None, t1, t2).ratio()


def full_string_similarity(r1, r2):
    return SequenceMatcher(None, normalise_text(r1), normalise_text(r2)).ratio()


def count_references_and_citations(analysis):
    num_unique_citations = len(analysis.get("in_text_citations", []))
    num_references = len(analysis.get("references", []))
    analysis["num_unique_citations"] = num_unique_citations
    analysis["num_references"] = num_references
    return analysis


def condense_pages(pages_str: str) -> str:
    """Condense page ranges for Vancouver style (e.g., 117-119 → 117-9, 301-307 → 301-7).
    Leaves non-numeric pages unchanged (e.g., 34A-37A stays as-is)."""
    match = re.match(r'^(\d+)\s*[-–]\s*(\d+)$', pages_str.strip())
    if not match:
        return pages_str  # Not a simple numeric range, return as-is
    start, end = match.group(1), match.group(2)
    if len(start) != len(end) or len(start) <= 1:
        return f"{start}-{end}"
    # Find where digits start to differ and truncate
    for i in range(len(start)):
        if start[i] != end[i]:
            return f"{start}-{end[i:]}"
    return f"{start}-{end}"  # Identical numbers, keep as-is


def make_sentence_case(text: str) -> str:
    """Intelligently downcase titles while preserving internal acronyms and proper nouns."""
    if not text: return ""
    words = text.split()
    
    # Check if string is aggressively Title Cased or UPPERCASED
    # If >50% of words start with a capital letter, assume it needs full conversion.
    capitalized_count = sum(1 for w in words if w[0].isupper() or w.isupper())
    is_title_case = (capitalized_count / len(words)) > 0.5 if words else False
    
    res = []
    for i, w in enumerate(words):
        # Always capitalize the very first word
        if i == 0:
            res.append(w.capitalize())
            continue
            
        # NLM Rule: ALWAYS lowercase the word immediately following a colon
        # (unless it's an acronym like USA)
        if i > 0 and words[i-1].endswith(':'):
            if w.isupper() and len(w) > 1:
                res.append(w) # Preserve acronym after colon
            else:
                res.append(w.lower())
            continue
            
        # Preserve acronyms anywhere
        if w.isupper() and len(w) > 1:
            res.append(w)
            continue
        elif sum(1 for c in w if c.isupper()) > 1:
            res.append(w)
            continue
            
        # If it was originally Title Cased, we downcase normal words
        if is_title_case:
            res.append(w.lower())
        else:
            # If it was already sentence cased (e.g., from PubMed or AI),
            # we PRESERVE the original capitalization! This saves proper nouns like "Mendelian".
            res.append(w)

    return " ".join(res)


def classify_source_type(metadata: dict) -> str:
    """Classify the source type based on available metadata fields."""
    title = (metadata.get("title") or "").lower()
    source = (metadata.get("source") or "").lower()
    
    if metadata.get("volume") or metadata.get("issue"):
        return "Journal Article"
    if metadata.get("doi"):
        return "Journal Article"  # Most DOI content is journal articles
    # Check for dissertation/thesis keywords in title
    if any(kw in title for kw in ("dissertation", "thesis")):
        return "Dissertation"
    # Check for report
    if metadata.get("report_number") or any(kw in title for kw in ("report", "working paper", "technical report")):
        return "Report"
    # Check for newspaper (has day_month and a source name)
    if metadata.get("day_month") and source:
        return "Newspaper Article"
    if metadata.get("publisher"):
        return "Book"
    if metadata.get("url"):
        return "Web Page"
    return "Other"
