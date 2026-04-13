import sys
import re
sys.path.insert(0, '.')
from citations.verification import extract_verbatim_references
doc_text = """Bawah, R. (2023). Nursing. Int J, 5, 100160. Children's Health Ireland. (2021). Emergency asthma. https://example.com/file.pdf"""
ai_refs = ["Children's Health Ireland. (2021). Emergency asthma. https://example.com/file.pdf"]

def extract_author_year(text):
    author = None
    year = None
    text_stripped = text.strip()
    org_match = re.match(
        r'^((?:[A-Z][a-zA-Zà-öø-ÿ\'\-]+(?:\s+(?:of|for|the|and|on|in|&))?\s+)*[A-Z][a-zA-Zà-öø-ÿ\'\-]+)'
        r'(?:\s*[.,]|\s*\()',
        text_stripped
    )
    if org_match and len(org_match.group(1).split()) > 1:
        author = org_match.group(1).lower()
    if not author:
        match = re.match(r'^((?:[A-Z][a-zA-Zà-öø-ÿ\'\-]+(?:\s*,\s*[A-Z][a-zA-Zà-öø-ÿ\'\-]+)*\s*,\s*(?:[A-Z]\.\s*)+\&?\s*)*[A-Z][a-zA-Zà-öø-ÿ\'\-]+)', text_stripped)
        if match:
            author = match.group(1).lower()
    if not author:
        match = re.match(r'^([A-Z][a-zA-Zà-öø-ÿ\'\-]+(?:\s*,?\s*[A-Z]\.?)+)', text_stripped)
        if match:
            author = match.group(1).lower()
    if not author:
        candidate_words = [w for w in text_stripped.split()[:5] if w[0].isupper() and len(w) > 3]
        if candidate_words:
            candidate = " ".join(candidate_words)
            if "and" not in candidate.lower():
                author = candidate.lower()
    if not author:
        author_match = re.match(r'^[^a-z]*?([A-Z][a-zA-Zà-öø-ÿ\'\-]+)', text_stripped)
        if author_match:
            author = author_match.group(1).lower()
    year_match = re.search(r'\b(19|20)\d{2}\b', text)
    if year_match:
        year = year_match.group(0)
    return (author, year)

ai_author, ai_year = extract_author_year(ai_refs[0])
cand_author, cand_year = extract_author_year(doc_text)
print("ai:", ai_author, ai_year)
print("cand:", cand_author, cand_year)
print("author_ok:", (not ai_author) or (not cand_author) or (ai_author in cand_author) or (cand_author in ai_author))
print("year_ok:", (not ai_year) or (not cand_year) or (ai_year == cand_year))
