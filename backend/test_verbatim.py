"""Test verbatim matching with curly apostrophes."""
import sys
sys.path.insert(0, '.')
from citations.verification import extract_verbatim_references

# Simulate: document has curly apostrophes, AI refs also have curly apostrophes
doc_text = """
References

Children\u2019s Health Ireland. (2021). Emergency department management of asthma. https://www.childrenshealthireland.ie/documents/1774/ED-Flowchart-Management-of-Asthma.pdf

Bawah, R. K., Osman, W., Pireh, D., Bapuah, M. A., Yakong, V. N., & Kala, M. (2023). Nursing staff involvement of children in care activities: A cross-sectional study. International journal of nursing studies advances, 5, 100160.

O\u2019Connor, P., O\u2019Connor, D., & Walsh, M. (2019). Time pressures and clinical urgency. Journal of Nursing, 45(3), 112-120.
"""

ai_refs = [
    "Children\u2019s Health Ireland. (2021). Emergency department management of asthma. https://www.childrenshealthireland.ie/documents/1774/ED-Flowchart-Management-of-Asthma.pdf",
    "Bawah, R. K., Osman, W., Pireh, D., Bapuah, M. A., Yakong, V. N., & Kala, M. (2023). Nursing staff involvement of children in care activities: A cross-sectional study. International journal of nursing studies advances, 5, 100160.",
    "O\u2019Connor, P., O\u2019Connor, D., & Walsh, M. (2019). Time pressures and clinical urgency. Journal of Nursing, 45(3), 112-120.",
]

verbatim = extract_verbatim_references(doc_text, ai_refs)
all_pass = True
for ai_ref, data in verbatim.items():
    conf = data['confidence']
    short = ai_ref[:60] + '...' if len(ai_ref) > 60 else ai_ref
    status = "PASS" if conf >= 0.75 else "FAIL"
    if conf < 0.75:
        all_pass = False
    print(f"  {status}: {short}")
    print(f"         confidence={conf:.0%}")

print(f"\nResult: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
