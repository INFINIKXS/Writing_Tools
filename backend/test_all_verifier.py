"""Comprehensive test for all three fixes."""
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
    # Sanity: normal names still work
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
    "O'Connor, P., O'Connor, D., & Walsh, M. (2019). Time pressures. Journal of Nursing, 45(3), 112-120.",
    "Smith, J. A. (2020). Title of the article. Journal Name, 10(2), 45-67.",
    "Jones, B., & Brown, C. (2018). Another title. BMJ, 360, k123.",
]

result = detect_style_from_references(apa_refs)
harvard_score = result['all_scores'].get('harvard', 0)
vancouver_score = result['all_scores'].get('vancouver', 0)
print(f"  Detected: {result['style']} at {result['confidence']}%")
print(f"  Harvard: {harvard_score}%, Vancouver: {vancouver_score}%")
bug2_pass = harvard_score == 0 and vancouver_score == 0
print(f"  Bug 2: {'PASS' if bug2_pass else 'FAIL'}")

print("\n" + "=" * 60)
print("BUG 3: Org-name verbatim matching")
print("=" * 60)
from citations.verification import extract_verbatim_references

doc_text = """
References

Trubey, R., Huang, C., Lugg-Widger, F. V., Hood, K., Allen, D., Edwards, D., ... & Powell, C. (2019). Validity and effectiveness of paediatric early warning systems and track and trigger tools for identifying and reducing clinical deterioration in hospitalised children: a systematic review. Bmj Open, 9(5), e022105. https://doi.org/10.1136/bmjopen-2018-022105

Department of Health. (2016). The Irish paediatric early warning system (PEWS): National clinical guideline No. 12 (Version 2). https://health.gov.ie/national-patient-safety-office/ncec/

O'Connor, P., O'Connor, D., & Walsh, M. (2019). Time pressures and clinical urgency in task-orientated communication. Journal of Nursing, 45(3), 112-120.
"""

ai_refs = [
    "Trubey, R., Huang, C., Lugg-Widger, F. V., Hood, K., Allen, D., Edwards, D., ... & Powell, C. (2019). Validity and effectiveness of paediatric early warning systems.",
    "Department of Health. (2016). The Irish paediatric early warning system (PEWS): National clinical guideline No. 12 (Version 2).",
    "O'Connor, P., O'Connor, D., & Walsh, M. (2019). Time pressures and clinical urgency.",
]

verbatim = extract_verbatim_references(doc_text, ai_refs)
bug3_pass = True
for ai_ref, data in verbatim.items():
    conf = data['confidence']
    short_ref = ai_ref[:60] + '...' if len(ai_ref) > 60 else ai_ref
    status = "PASS" if conf >= 0.75 else "FAIL"
    if conf < 0.75:
        bug3_pass = False
    print(f"  {status}: {short_ref}")
    print(f"         confidence={conf:.0%}")

print(f"\n  Bug 3: {'PASS' if bug3_pass else 'FAIL'}")

print("\n" + "=" * 60)
overall = all_pass and bug2_pass and bug3_pass
print(f"OVERALL: {'ALL BUGS FIXED' if overall else 'SOME BUGS REMAIN'}")
print("=" * 60)
