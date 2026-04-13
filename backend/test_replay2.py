"""Replay: specifically target the Children's Health Ireland AI ref."""
import json, sys, re
from difflib import SequenceMatcher

sys.path.insert(0, '.')

with open("verbatim_debug.json", "r", encoding="utf-8") as f:
    data = json.load(f)

full_text = data["full_text"]
ai_references = data["ai_references"]

# Find the CORRECT AI ref
target_ai = [r for r in ai_references if r.startswith("Children")][0]
print(f"=== TARGET AI REF ===")
print(f"  {repr(target_ai)}")
print(f"  len={len(target_ai)}")
print()

# Normalize
def _normalize_text(t):
    t = t.replace('\u00a0', ' ')
    t = t.replace('\u202f', ' ')
    t = t.replace('\u2006', ' ')
    t = t.replace('\u2009', ' ')
    t = t.replace('\u200b', '')
    t = t.replace('\u200c', '')
    t = t.replace('\u200d', '')
    t = t.replace('\u2018', "'")
    t = t.replace('\u2019', "'")
    t = t.replace('\u201c', '"')
    t = t.replace('\u201d', '"')
    t = t.replace('\u2013', '-')
    t = t.replace('\u2014', '-')
    t = t.replace('\ufb01', 'fi')
    t = t.replace('\ufb02', 'fl')
    return t

full_text_norm = _normalize_text(full_text)
target_ai_norm = _normalize_text(target_ai)

print(f"=== NORMALIZED AI REF ===")
print(f"  {repr(target_ai_norm)}")
print()

# Direct substring search
idx = full_text_norm.find(target_ai_norm)
print(f"=== DIRECT SUBSTRING SEARCH ===")
print(f"  Index: {idx}")
if idx >= 0:
    print(f"  FOUND VERBATIM!")
else:
    # Find partial
    search = "Children's Health Ireland. (2021)"
    positions = [m.start() for m in re.finditer(re.escape(search), full_text_norm)]
    print(f"  Not found as exact substring.")
    print(f"  Searching for '{search}': {len(positions)} occurrences at {positions}")
    for pos in positions:
        doc_chunk = full_text_norm[pos:pos+len(target_ai_norm)+20]
        print(f"\n  Doc chunk from pos {pos}:")
        print(f"    {repr(doc_chunk)}")
        print(f"  AI ref:")
        print(f"    {repr(target_ai_norm)}")
        # Char-by-char diff
        for i in range(min(len(target_ai_norm), len(doc_chunk))):
            if target_ai_norm[i] != doc_chunk[i]:
                print(f"\n  FIRST MISMATCH at pos {i}:")
                print(f"    AI char: {repr(target_ai_norm[i])} (ord={ord(target_ai_norm[i])})")
                print(f"    Doc char: {repr(doc_chunk[i])} (ord={ord(doc_chunk[i])})")
                print(f"    AI context: ...{repr(target_ai_norm[max(0,i-15):i+15])}...")
                print(f"    Doc context: ...{repr(doc_chunk[max(0,i-15):i+15])}...")
                break

print()

# Atomic splitting
ref_heading_patterns = [
    r'(?im)^\s*references?\s*$',
    r'(?im)^\s*bibliography\s*$',
    r'(?im)^\s*works?\s+cited\s*$',
    r'(?im)^\s*reference\s+list\s*$',
]
ref_section = full_text_norm
ref_start_idx = None
for pattern in ref_heading_patterns:
    match = re.search(pattern, full_text_norm)
    if match:
        ref_start_idx = match.end()
        break
if ref_start_idx is not None:
    ref_section = full_text_norm[ref_start_idx:]

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
        if current_ref_lines:
            joined = ' '.join(current_ref_lines)
            if has_year.search(joined):
                atomic_refs.append(joined)
            current_ref_lines = []
        continue
    is_new_ref = ref_start_pattern.match(stripped)
    is_continuation = continuation_pattern.match(stripped)
    is_org = org_name_pattern.match(stripped)
    if is_new_ref and current_ref_lines and not is_continuation:
        joined = ' '.join(current_ref_lines)
        if has_year.search(joined):
            atomic_refs.append(joined)
        current_ref_lines = [stripped]
    else:
        current_ref_lines.append(stripped)

if current_ref_lines:
    joined = ' '.join(current_ref_lines)
    if has_year.search(joined):
        atomic_refs.append(joined)

# Find and print the Children's atomic ref
chi_refs = [(i, r) for i, r in enumerate(atomic_refs) if r.startswith("Children")]
print(f"=== CHILDREN'S ATOMIC REF ===")
for i, r in chi_refs:
    print(f"  Index: {i}")
    print(f"  Full text: {repr(r)}")
    print(f"  Length: {len(r)}")

print()

# Now score
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
        author_match = re.match(r'^[^a-z]*?([A-Z][a-zA-Zà-öø-ÿ\'\-]+)', text_stripped)
        if author_match:
            author = author_match.group(1).lower()
    year_match = re.search(r'\b(19|20)\d{2}\b', text)
    if year_match:
        year = year_match.group(0)
    return (author, year)

ai_author, ai_year = extract_author_year(target_ai_norm)
print(f"=== AUTHOR/YEAR EXTRACTION ===")
print(f"  AI author: {repr(ai_author)}")
print(f"  AI year: {repr(ai_year)}")

if chi_refs:
    cand = chi_refs[0][1]
    cand_author, cand_year = extract_author_year(cand)
    print(f"  Cand author: {repr(cand_author)}")
    print(f"  Cand year: {repr(cand_year)}")
    
    author_ok = (not ai_author) or (not cand_author) or (ai_author in cand_author) or (cand_author in ai_author)
    year_ok = (not ai_year) or (not cand_year) or (ai_year == cand_year)
    print(f"  author_ok: {author_ok}")
    print(f"  year_ok: {year_ok}")
    
    # Score anyway
    ai_ref_lower = target_ai_norm.lower().strip()
    cand_lower = cand.lower().strip()
    sm = SequenceMatcher(None, ai_ref_lower, cand_lower)
    score = sm.ratio()
    print(f"  SequenceMatcher score: {score:.4f}")
    print()
    print(f"  AI ref lower: {repr(ai_ref_lower)}")
    print(f"  Cand lower:   {repr(cand_lower)}")
