"""Test whether O'Connor is matched by the citation regex patterns."""
import sys
sys.path.insert(0, '.')
from citations.extraction import extract_citations_regex, _SNAME
import re

# Test 1: Does _SNAME match O'Connor?
sname_pat = re.compile(_SNAME)
names = ["O'Connor", "O\u2019Connor", "Smith", "Stokes-Parish", "McDonald", "Al-Rashid"]
print("=== _SNAME pattern test ===")
for name in names:
    m = sname_pat.match(name)
    print(f"  {name!r:25s} -> {'MATCH: ' + m.group(0) if m else 'NO MATCH'}")

# Test 2: Full extraction on the user's text
print("\n=== Full extraction test ===")
text = "According to O\u2019Connor et al. (2019), time pressures and clinical urgency can reorient clinical interactions to task-orientated communication."
citations = extract_citations_regex(text)
print(f"Found {len(citations)} citations:")
for c in citations:
    print(f"  {c['text']!r}  type={c['type']}")

# Test 3: Same with ASCII apostrophe
text2 = "According to O'Connor et al. (2019), time pressures and clinical urgency can reorient."
citations2 = extract_citations_regex(text2)
print(f"\nWith ASCII apostrophe, found {len(citations2)} citations:")
for c in citations2:
    print(f"  {c['text']!r}  type={c['type']}")

# Test 4: Parenthetical form
text3 = "(O'Connor et al., 2019)"
citations3 = extract_citations_regex(text3)
print(f"\nParenthetical (O'Connor et al., 2019), found {len(citations3)} citations:")
for c in citations3:
    print(f"  {c['text']!r}  type={c['type']}")
