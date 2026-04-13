"""Comprehensive test for all verifier fixes including tightened Vancouver."""
import sys
sys.path.insert(0, '.')

print("=" * 60)
print("BUG 1: O'Connor citation detection")
print("=" * 60)
from citations.extraction import extract_citations_regex

tests = [
    ("According to O\u2019Connor et al. (2019), time pressures.", "NAR_ETAL"),
    ("According to O'Connor et al. (2019), time pressures.", "NAR_ETAL"),
    ("(O'Connor et al., 2019)", "PAR_ETAL"),
    ("(O'Connor, 2019)", "PAR_SINGLE"),
    ("O'Connor (2019)", "NAR_SINGLE"),
    ("(D'Angelo & Smith, 2020)", "PAR_TWO"),
    ("L'Amour et al. (2018)", "NAR_ETAL"),
    ("(Smith, 2020)", "PAR_SINGLE"),
    ("(Stokes-Parish et al., 2019)", "PAR_ETAL"),
    ("Van der Berg (2021)", "NAR_SINGLE"),
]

all_pass = True
for text, expected_type in tests:
    citations = extract_citations_regex(text)
    if len(citations) == 0:
        print(f"  FAIL: {text!r} -> NO MATCH (expected {expected_type})")
        all_pass = False
    else:
        c = citations[0]
        status = "PASS" if c['type'] == expected_type else f"WARN type={c['type']}"
        print(f"  {status}: {text!r} -> {c['text']!r} ({c['type']})")

print(f"\nBug 1: {'ALL PASS' if all_pass else 'SOME FAILURES'}")

print("\n" + "=" * 60)
print("BUG 2: Style detection false positives")
print("=" * 60)
from citations.detection import detect_style_from_references

apa_refs = [
    "Trubey, R., Huang, C., Lugg-Widger, F. V., Hood, K., Allen, D., Edwards, D., ... & Powell, C. (2019). Validity and effectiveness. Bmj Open, 9(5), e022105.",
    "Department of Health. (2016). The Irish paediatric early warning system.",
    "O'Connor, P., O\u2019Connor, D., & Walsh, M. (2019). Time pressures. Journal of Nursing, 45(3), 112-120.",
    "Smith, J. A. (2020). Title of the article. Journal Name, 10(2), 45-67.",
    "Jones, B., & Brown, C. (2018). Another title. BMJ, 360, k123.",
    "Children\u2019s Health Ireland. (2021). Emergency department management of asthma. https://www.childrenshealthireland.ie",
    "Health Service Executive. (2021). National clinical programme. Washington DC, Publisher.",
]

result = detect_style_from_references(apa_refs)
harvard_score = result['all_scores'].get('harvard', 0)
vancouver_score = result['all_scores'].get('vancouver', 0)
print(f"  Detected: {result['style']} at {result['confidence']}%")
print(f"  All scores: {result['all_scores']}")
bug2_pass = result['style'] == 'apa' and vancouver_score == 0 and harvard_score == 0
print(f"  Bug 2: {'PASS' if bug2_pass else 'FAIL'}")

print("\n" + "=" * 60)
print("VANCOUVER FALSE POSITIVE CHECK")
print("=" * 60)
# Make sure real Vancouver still works
van_refs = [
    "1. Smith JA, Doe B, Jones CD. Title of article. BMJ. 2020;360:k123.",
    "2. O'Connor PA, Walsh M. Time pressures. J Nurs. 2019;45(3):112.",
    "3. Bawah RK, Osman W. Nursing staff. Int J Nursing. 2023;12(4):112.",
]
van_result = detect_style_from_references(van_refs)
van_pass = van_result['style'] == 'vancouver'
print(f"  Detected: {van_result['style']} at {van_result['confidence']}%")
print(f"  All scores: {van_result['all_scores']}")
print(f"  Vancouver detection: {'PASS' if van_pass else 'FAIL'}")

print("\n" + "=" * 60)
print("BUG 3: Children's Health matching")
print("=" * 60)
from citations.verification import verify_matches_with_string_search

refs = [
    "Children\u2019s Health Ireland. (2021). Emergency department management of asthma.",
    "Health Service Executive. (2021). National clinical programme.",
    "O\u2019Connor, P., O\u2019Connor, D. (2019). Time pressures. Journal of Nursing.",
]
cits = [
    "(Children's Health Ireland, 2021)",
    "(Health Service Executive, 2021)",
    "(O'Connor et al., 2019)",
]

out = verify_matches_with_string_search(cits, refs)
bug3_pass = True
for match in out['confirmed_matches']:
    print(f"  MATCHED: {match['citation'][:50]} -> {match['matched_ref'][:50]}")
for unm in out['unmatched_citations']:
    print(f"  UNMATCHED CIT: {unm}")
    bug3_pass = False
for unr in out['unmatched_references']:
    print(f"  UNUSED REF: {unr[:60]}")
    bug3_pass = False
print(f"  Bug 3: {'PASS' if bug3_pass else 'FAIL'}")

print("\n" + "=" * 60)
overall = all_pass and bug2_pass and van_pass and bug3_pass
print(f"OVERALL: {'ALL BUGS FIXED' if overall else 'SOME BUGS REMAIN'}")
print("=" * 60)
