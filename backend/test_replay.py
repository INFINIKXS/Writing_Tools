"""Replay the exact verbatim_debug.json through the pipeline and trace the Children's Health Ireland reference."""
import json, sys, re
from difflib import SequenceMatcher

sys.path.insert(0, '.')

with open("verbatim_debug.json", "r", encoding="utf-8") as f:
    data = json.load(f)

full_text = data["full_text"]
ai_references = data["ai_references"]

# Find the Children's Health Ireland AI ref
target_ai = [r for r in ai_references if "Children" in r][0]
print(f"=== TARGET AI REF ===")
print(f"  {target_ai[:100]}...")
print(f"  len={len(target_ai)}")
print(f"  repr of apostrophe char: {repr(target_ai[8])}")  # the ' in Children's
print()

# --- Replicate the normalization ---
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

print(f"=== AFTER NORMALIZATION ===")
print(f"  AI apostrophe char: {repr(target_ai_norm[8])}")
print()

# Check: does the normalized AI ref appear verbatim in the normalized full text?
idx = full_text_norm.find(target_ai_norm)
print(f"=== DIRECT SUBSTRING SEARCH ===")
print(f"  full_text_norm.find(target_ai_norm) = {idx}")
if idx >= 0:
    print(f"  FOUND at position {idx}")
    print(f"  Context: ...{full_text_norm[idx-20:idx]}<<<HERE>>>{full_text_norm[idx:idx+40]}...")
else:
    # Find partial matches
    print(f"  NOT FOUND as exact substring. Investigating why...")
    # Try to find "Children's Health Ireland" in the normalized text
    search = "Children's Health Ireland"
    positions = [m.start() for m in re.finditer(re.escape(search), full_text_norm)]
    print(f"  Occurrences of '{search}': {len(positions)} at positions {positions}")
    
    if positions:
        # Show the reference section occurrence
        for pos in positions:
            context = full_text_norm[pos:pos+250]
            print(f"\n  --- Context at {pos} ---")
            print(f"  {repr(context[:250])}")

    # Now check: what's different between the AI ref and the doc text?
    # Find the ref section occurrence (should be the last one)
    ref_idx = full_text_norm.rfind("Children's Health Ireland. (2021)")
    if ref_idx >= 0:
        doc_chunk = full_text_norm[ref_idx:ref_idx+len(target_ai_norm)+50]
        print(f"\n=== CHARACTER-BY-CHARACTER DIFF ===")
        print(f"  AI ref length: {len(target_ai_norm)}")
        print(f"  Doc chunk length: {len(doc_chunk)}")
        for i in range(min(len(target_ai_norm), len(doc_chunk))):
            if target_ai_norm[i] != doc_chunk[i]:
                print(f"  MISMATCH at pos {i}: AI={repr(target_ai_norm[i])} doc={repr(doc_chunk[i])}")
                print(f"    AI context: ...{repr(target_ai_norm[max(0,i-10):i+10])}...")
                print(f"    Doc context: ...{repr(doc_chunk[max(0,i-10):i+10])}...")
                break
        else:
            if len(target_ai_norm) <= len(doc_chunk):
                print(f"  All {len(target_ai_norm)} chars match! Doc has trailing: {repr(doc_chunk[len(target_ai_norm):len(target_ai_norm)+20])}")

print()

# --- Now replicate the atomic splitting ---
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

print(f"=== REFERENCE SECTION ===")
print(f"  ref_start_idx={ref_start_idx}")
print(f"  ref_section length={len(ref_section)}")
print()

# Atomic splitting
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

# Find Children's in atomic_refs
print(f"=== ATOMIC REFS ({len(atomic_refs)} total) ===")
children_refs = [r for r in atomic_refs if "children" in r.lower() and "ireland" in r.lower()]
print(f"  Refs containing 'Children' + 'Ireland': {len(children_refs)}")
for r in children_refs:
    print(f"    {repr(r[:150])}...")

# If not found standalone, find which atomic ref contains it
if not children_refs:
    print("  Checking all atomic refs for partial content...")
    for i, r in enumerate(atomic_refs):
        if "children" in r.lower():
            print(f"    atomic_refs[{i}]: {repr(r[:200])}...")
            print(f"    length: {len(r)}")

print()

# Now simulate the scoring
print(f"=== SCORING SIMULATION ===")
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
print(f"  AI author: {ai_author}")
print(f"  AI year: {ai_year}")

for i, candidate in enumerate(atomic_refs):
    candidate_lower = candidate.lower().strip()
    ai_ref_lower = target_ai_norm.lower().strip()
    
    len_ratio = len(candidate_lower) / max(len(ai_ref_lower), 1)
    if len_ratio < 0.3 or len_ratio > 15.0:
        continue
    
    cand_author, cand_year = extract_author_year(candidate)
    
    author_ok = (not ai_author) or (not cand_author) or (ai_author in cand_author) or (cand_author in ai_author)
    year_ok = (not ai_year) or (not cand_year) or (ai_year == cand_year)
    
    if "children" in candidate.lower() or (cand_author and "children" in cand_author):
        print(f"\n  --- Candidate {i} (contains 'children') ---")
        print(f"    cand_author={cand_author}, cand_year={cand_year}")
        print(f"    author_ok={author_ok}, year_ok={year_ok}")
        print(f"    len_ratio={len_ratio:.2f}")
        sm = SequenceMatcher(None, ai_ref_lower, candidate_lower)
        score = sm.ratio()
        print(f"    SequenceMatcher score={score:.4f}")
        print(f"    candidate[:150]={repr(candidate[:150])}")
    
    if not author_ok or not year_ok:
        continue
    
    sm = SequenceMatcher(None, ai_ref_lower, candidate_lower)
    score = sm.ratio()
    if score > 0.5:
        print(f"\n  HIGH SCORE candidate {i}: score={score:.4f}, author={cand_author}, year={cand_year}")
        print(f"    {candidate[:150]}...")
