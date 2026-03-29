"""
Shared text utility functions: normalisation, DOI extraction, similarity, sentence case, page condensation.
"""
import re
import unicodedata
from difflib import SequenceMatcher


def extract_doi(ref_string):
    """Extract and normalise DOI from a reference string."""
    m = re.search(
        r'\bdoi[:\s]*'           # "doi:" or "doi " prefix
        r'(10\.\d{4,9}'         # DOI prefix: 10.XXXX
        r'/[^\s,;\]]+)',         # DOI suffix
        ref_string,
        re.IGNORECASE
    )
    if m:
        # Normalise: lowercase, strip trailing punctuation
        doi = m.group(1).lower().rstrip('.,;)')
        return doi
    return None


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
