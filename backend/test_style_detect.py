"""Test style detection after fixes — more comprehensive."""
import sys
sys.path.insert(0, '.')
from citations.detection import detect_style_from_references
import re

# Pure APA references — no Harvard signals at all
apa_refs = [
    "Trubey, R., Huang, C., Lugg-Widger, F. V., Hood, K., Allen, D., Edwards, D., ... & Powell, C. (2019). Validity and effectiveness of paediatric early warning systems. Bmj Open, 9(5), e022105.",
    "Department of Health. (2016). The Irish paediatric early warning system. National clinical guideline No. 12.",
    "O'Connor, P., O'Connor, D., & Walsh, M. (2019). Time pressures and clinical urgency. Journal of Nursing, 45(3), 112-120.",
    "Smith, J. A. (2020). Title of the article. Journal Name, 10(2), 45-67.",
    "Jones, B., & Brown, C. (2018). Another title here. BMJ, 360, k123.",
]

result = detect_style_from_references(apa_refs)
print(f"Detected style: {result['style']}")
print(f"Confidence: {result['confidence']}%")
print(f"All scores: {result['all_scores']}")
print(f"Evidence:")
for ev in result.get('evidence', []):
    print(f"  - {ev}")

# Verify no Harvard leak
ref_block = '\n'.join(apa_refs)

# Check which Harvard signals actually fire
h1 = re.findall(r'\b[A-Z][a-z]+,\s+[A-Z]\.', ref_block)
h2 = re.findall(r"'[A-Z][^']{10,}'", ref_block)
h3 = re.findall(r"\(\d{4}[a-z]?\)\s+'", ref_block)
h4 = re.findall(r'\bpp\.\s*\d+[–\-]\d+', ref_block)
h5 = re.findall(r'\bAvailable\s+at:', ref_block, re.IGNORECASE)
h6 = re.findall(r'\(Accessed:', ref_block, re.IGNORECASE)

print(f"\nHarvard signal breakdown:")
print(f"  h1 (Surname, I.):     {len(h1)} matches")
print(f"  h2 (single-quoted):   {len(h2)} matches")
print(f"  h3 (year+quote):      {len(h3)} matches")
print(f"  h4 (pp. X-Y):         {len(h4)} matches")
print(f"  h5 (Available at:):   {len(h5)} matches")
print(f"  h6 (Accessed:):       {len(h6)} matches")
print(f"  Unique markers: {bool(h2 or h3 or h5 or h6)}")
