"""Test irregularity detection fixes."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from citations.verification import detect_irregularities_deterministically as detect_irregularities

# Test 1: DATE_MISMATCH — should match each citation to correct year
print("=== Test 1: DATE_MISMATCH with multiple same-author refs ===")
citations = [
    {"text": "(Dema et al., 2021)", "type": "PAR_ETAL"},
    {"text": "(Dema et al., 2022)", "type": "PAR_ETAL"},
    {"text": "(Dema et al., 2024)", "type": "PAR_ETAL"},
]
refs = [
    "Dema, E. et al. (2021) Title one. Journal, 1(1), pp. 1-10.",
    "Dema, E. et al. (2022b) Methodology of Natsal-COVID Wave 2. Journal, 2(1).",
    "Dema, E. et al. (2024) Latest findings. Journal, 4(1), pp. 30-40.",
]
irregs = detect_irregularities(citations, refs)
date_mismatches = [i for i in irregs if i["type"] == "DATE_MISMATCH"]
print(f"  DATE_MISMATCH count: {len(date_mismatches)} (expected: 0)")
for dm in date_mismatches:
    print(f"  {dm['details']}")

# Test 2: NAME_MISMATCH with diacritics — MASLAKCI vs Maslakci
print("\n=== Test 2: NAME_MISMATCH diacritical normalization ===")
citations2 = [{"text": "( Sürücü and Maslakci, 2020)", "type": "PAR_TWO"}]
refs2 = ["SÜRÜCÜ, L. and MASLAKÇI, A. (2020) Some title. Journal, 8(3)."]
irregs2 = detect_irregularities(citations2, refs2)
name_mismatches = [i for i in irregs2 if i["type"] == "NAME_MISMATCH"]
print(f"  NAME_MISMATCH count: {len(name_mismatches)} (expected: 0)")
for nm in name_mismatches:
    print(f"  {nm['details']}")

# Test 3: Real spelling error should still be caught
print("\n=== Test 3: Real spelling error should still flag ===")
citations3 = [{"text": "(Hammmond et al., 2022)", "type": "PAR_ETAL"}]
refs3 = ["Hammond, R. et al. (2022) Some title. Journal, 3(1), pp. 21-30."]
irregs3 = detect_irregularities(citations3, refs3)
name_mismatches3 = [i for i in irregs3 if i["type"] == "NAME_MISMATCH"]
print(f"  NAME_MISMATCH count: {len(name_mismatches3)} (expected: 1)")
for nm in name_mismatches3:
    print(f"  {nm['details']}")
