"""Test tightened v2 regex that requires the pattern to end with a period (last author)."""
import re

# Vancouver requires: Surname IA, Surname IB, Surname IC. Title...
# The author list ALWAYS ends with a period after the final author's initials.
# APA publisher locations like "London UK, Sage" do NOT end with a period after the initials.
#
# New approach: require at least TWO "Surname IA," matches (or one ending in period)

# Option A: require the full author block to end with period:
# Surname IA, Surname IB. (title follows)
v2_tight = r'^(?:\[\d+\]\s*|\d+\.\s*)?(?:[A-Z][A-Za-z\'\u2019-]+\s+[A-Z]{1,3},\s*)+[A-Z][A-Za-z\'\u2019-]+\s+[A-Z]{1,3}\.'

# This requires at least 2 authors: one with comma, last one with period.

test_refs = [
    # Real Vancouver - should match
    "Smith JA, Doe B, Jones CD. Title of article. BMJ. 2020;360:k123.",
    "Bawah RK, Osman W. Nursing staff. Int J Nursing. 2023;12(4):112.",
    "1. O'Connor PA, Walsh M. Time pressures. J Nurs. 2019;45(3):112.",

    # APA - should NOT match
    "Bawah, R. K., Osman, W. (2023). Nursing staff. Int J Nursing.",
    "Smith, J. A. (2020). Title. Journal Name, 10(2), 45-67.",
    "Children\u2019s Health Ireland. (2021). Emergency department management.",

    # Publisher locations - should NOT match
    "London UK, Sage Publications.",
    "Cambridge MA, MIT Press.",
    "Washington DC, American Psychological Association.",
    "New York NY, Publisher.",
]

print("Testing tightened v2 regex:")
print(f"Pattern: {v2_tight}")
print()
for ref in test_refs:
    m = re.findall(v2_tight, ref, re.MULTILINE)
    status = "MATCH" if m else "no match"
    print(f"  {status:>8}: {ref[:70]}")
    if m:
        print(f"           -> {m}")
