"""Test O'Connor-style apostrophe names in citation detection."""
import re
from citations.extraction import extract_citations_regex, _SNAME, CITATION_PATTERNS

test_cases = [
    # Narrative et al.
    "According to O\u2019Connor et al. (2019), the clinical interactions",
    "According to O'Connor et al. (2019), the clinical interactions",
    # Parenthetical et al.
    "(O'Connor et al., 2019)",
    "(O\u2019Connor et al., 2019)",
    # Narrative single
    "O'Connor (2019) stated that",
    "O\u2019Connor (2019) stated that",
    # Parenthetical single
    "(O'Connor, 2019)",
    "(O\u2019Connor, 2019)",
    # Two-author narrative
    "O'Connor and Smith (2019)",
    # Two-author parenthetical  
    "(O'Connor & Smith, 2019)",
    # Possessive narrative
    "O'Connor's (2019) study",
    # Control: normal names should still work
    "Smith et al. (2020) found",
    "(Jones, 2021)",
]

print("=" * 70)
print("_SNAME pattern test:")
print("=" * 70)

# Test _SNAME directly
sname_pat = re.compile(_SNAME)
for name in ["O'Connor", "O\u2019Connor", "Smith", "Dall'Ora", "Stokes-Parish"]:
    m = sname_pat.match(name)
    print(f"  {name!r:30s} -> {'MATCH: ' + m.group() if m else 'NO MATCH'}")

print()
print("=" * 70)
print("Full extraction test:")
print("=" * 70)

for text in test_cases:
    results = extract_citations_regex(text)
    if results:
        for r in results:
            print(f"  OK   {text!r}")
            print(f"       -> {r['text']} [{r['type']}]")
    else:
        print(f"  FAIL {text!r}")
        print(f"       -> (no citations detected)")
    print()
