"""
Comprehensive validation of the reference list safeguard system.
Tests that no reference entries are silently omitted.
"""
from citations.verification import _split_ref_section_to_atomic, extract_references_from_text

results = {}

# ── TEST 1: Direct splitter — all edge case patterns ──────────────────────
print("=" * 60)
print("TEST 1: Direct splitter -- all edge case patterns")
print("=" * 60)
edge_cases = """Adams, R. (2018) 'Title here', Journal Name, 5(1), pp. 10-20.
3ie (2022) Impact evaluation of something. 3ie Working Paper.
Smith, J. (2021) Another title. Some Journal, 10(2), pp. 5-15.
uk parliament (2019) Some parliamentary report. London: HMSO.
de Vries, M. (2020) Dutch study title. European Journal, 8(3), pp. 100-110.
GBD 2021 Diabetes Collaborators (2023) Global burden study. The Lancet, 401(10394), pp. 2023-2050.
el-Sayed, A. M. (2017) Hyphenated prefix study. Am J Public Health, 107(5), pp. 700-706.
van der Berg, A. B. (2019) Multi-word prefix. Some Journal, 3(1), pp. 1-10.
al-Rashid, F. (2022) Another hyphenated. Int J Something, 15(2), pp. 200-210."""

refs = _split_ref_section_to_atomic(edge_cases)
expected_authors = ['Adams', '3ie', 'Smith', 'uk parliament', 'de Vries',
                    'GBD 2021', 'el-Sayed', 'van der Berg', 'al-Rashid']
found = [a for a in expected_authors if any(a.lower() in r.lower()[:60] for r in refs)]
missing = [a for a in expected_authors if a not in found]

print(f"Extracted {len(refs)} refs (expected 9):")
for i, r in enumerate(refs, 1):
    label = r[:95] + "..." if len(r) > 95 else r
    print(f"  {i}. {label}")
print(f"\nMissing: {missing}")
results["Test 1 (edge cases)"] = "PASS" if len(found) == 9 else "FAIL"
print(f"Result: {results['Test 1 (edge cases)']} ({len(found)}/9)")


# ── TEST 2: Full pipeline with reconciliation ─────────────────────────────
print("\n" + "=" * 60)
print("TEST 2: Full pipeline with reconciliation")
print("=" * 60)
full_doc = """This is the body of the document with some text.

References

Adams, R. (2018) 'Title here', Journal Name, 5(1), pp. 10-20.
3ie (2022) Impact evaluation of something. 3ie Working Paper.
Smith, J. (2021) Another title. Some Journal, 10(2), pp. 5-15.
uk parliament (2019) Some parliamentary report. London: HMSO.
de Vries, M. (2020) Dutch study title. European Journal, 8(3), pp. 100-110.
GBD 2021 Diabetes Collaborators (2023) Global burden study. The Lancet, 401(10394), pp. 2023-2050.
el-Sayed, A. M. (2017) Hyphenated prefix study. Am J Public Health, 107(5), pp. 700-706.
van der Berg, A. B. (2019) Multi-word prefix. Some Journal, 3(1), pp. 1-10.
al-Rashid, F. (2022) Another hyphenated. Int J Something, 15(2), pp. 200-210."""

refs2 = extract_references_from_text(full_doc)
found2 = [a for a in expected_authors if any(a.lower() in r.lower()[:60] for r in refs2)]
missing2 = [a for a in expected_authors if a not in found2]

print(f"Extracted {len(refs2)} refs (expected 9):")
for i, r in enumerate(refs2, 1):
    label = r[:95] + "..." if len(r) > 95 else r
    print(f"  {i}. {label}")
print(f"\nMissing: {missing2}")
results["Test 2 (full pipeline)"] = "PASS" if len(found2) == 9 else "FAIL"
print(f"Result: {results['Test 2 (full pipeline)']} ({len(found2)}/9)")


# ── TEST 3: Multi-line references ─────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 3: Multi-line references with continuation lines")
print("=" * 60)
multiline = """Capili, B. and Anastasi, J. K. (2020) 'Something something',
    Journal of Nursing, 5(1), pp. 10-20.
    doi: https://doi.org/10.1234/fake
de Vries, M., van Loon, A. and Peters, R. (2019) 'Dutch
    multi-line study title here', European Journal of
    Something, 8(3), pp. 100-110.
al-Rashid, F., Mohammed, K. and Hassan, A. (2022) 'Another
    hyphenated multi-line reference', International Journal
    of Something, 15(2), pp. 200-210.
    Available at: https://example.com
GBD 2021 Diabetes Collaborators (2023) Global, regional,
    and national burden of diabetes from 1990 to 2021.
    The Lancet, 401(10394), pp. 2023-2050."""

refs3 = _split_ref_section_to_atomic(multiline)
expected3 = ['Capili', 'de Vries', 'al-Rashid', 'GBD 2021']
found3 = [a for a in expected3 if any(a.lower() in r.lower()[:60] for r in refs3)]
missing3 = [a for a in expected3 if a not in found3]

print(f"Extracted {len(refs3)} refs (expected 4):")
for i, r in enumerate(refs3, 1):
    label = r[:95] + "..." if len(r) > 95 else r
    print(f"  {i}. {label}")
print(f"\nMissing: {missing3}")
results["Test 3 (multi-line)"] = "PASS" if len(found3) == 4 else "FAIL"
print(f"Result: {results['Test 3 (multi-line)']} ({len(found3)}/4)")


# ── TEST 4: False positive guard ──────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 4: False positive guard -- titles with embedded years")
print("=" * 60)
false_pos = """Johnson, A. (2018) 'The impact of policy changes
    implemented in (2015) on healthcare outcomes',
    Journal of Health Policy, 12(3), pp. 45-60.
Williams, B. (2020) 'Reviewing the evidence from a
    randomized trial', BMJ, 370, m2648."""

refs4 = _split_ref_section_to_atomic(false_pos)
print(f"Extracted {len(refs4)} refs (expected 2):")
for i, r in enumerate(refs4, 1):
    label = r[:95] + "..." if len(r) > 95 else r
    print(f"  {i}. {label}")
results["Test 4 (false positive)"] = "PASS" if len(refs4) == 2 else "FAIL"
print(f"Result: {results['Test 4 (false positive)']} ({len(refs4)}/2)")


# ── TEST 5: Demerge recovery ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 5: Demerge recovery -- merged entries on one line")
print("=" * 60)
merged_doc = """Some body text.

References

Adams, R. (2018) 'Title one', Journal A, 5(1), pp. 10-20.
Brown, C. (2019) 'Title two', Journal B, 3(2), pp. 30-40. Clark, D. (2020) 'Title three', Journal C, 7(4), pp. 50-60.
Evans, E. (2021) 'Title four', Journal D, 9(1), pp. 70-80."""

refs5 = extract_references_from_text(merged_doc)
expected5 = ['Adams', 'Brown', 'Clark', 'Evans']
found5 = [a for a in expected5 if any(a.lower() in r.lower()[:40] for r in refs5)]
missing5 = [a for a in expected5 if a not in found5]

print(f"Extracted {len(refs5)} refs (expected 4):")
for i, r in enumerate(refs5, 1):
    label = r[:95] + "..." if len(r) > 95 else r
    print(f"  {i}. {label}")
print(f"\nMissing: {missing5}")
results["Test 5 (demerge)"] = "PASS" if len(found5) == 4 else "FAIL"
print(f"Result: {results['Test 5 (demerge)']} ({len(found5)}/4)")


# ── TEST 6: Multi-signal — DOI-heavy ─────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 6: Multi-signal -- DOI-heavy references")
print("=" * 60)
doi_doc = """Some body text.

References

Adams, R. (2018) 'Title one', Journal A, 5(1), pp. 10-20.
    https://doi.org/10.1000/aaa
Brown, C. (2019) 'Title two', Journal B, 3(2), pp. 30-40.
    https://doi.org/10.1000/bbb
Clark, D. (2020) 'Title three', Journal C, 7(4), pp. 50-60.
    https://doi.org/10.1000/ccc
Evans, E. (2021) 'Title four', Journal D, 9(1), pp. 70-80.
    https://doi.org/10.1000/ddd"""

refs6 = extract_references_from_text(doi_doc)
expected6 = ['Adams', 'Brown', 'Clark', 'Evans']
found6 = [a for a in expected6 if any(a.lower() in r.lower()[:40] for r in refs6)]

print(f"Extracted {len(refs6)} refs (expected 4):")
for i, r in enumerate(refs6, 1):
    label = r[:95] + "..." if len(r) > 95 else r
    print(f"  {i}. {label}")
results["Test 6 (DOI signal)"] = "PASS" if len(found6) == 4 else "FAIL"
print(f"Result: {results['Test 6 (DOI signal)']} ({len(found6)}/4)")


# ── TEST 7: Vancouver numbered style ─────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 7: Vancouver numbered references")
print("=" * 60)
vancouver_doc = """Some body text.

References

[1] Adams R, Brown C. Title one. J Something. 2018;5(1):10-20.
[2] Clark D. Title two. BMJ. 2019;370:m2648.
[3] Evans E, Franks F, Green G. Title three. Lancet. 2020;395(1):100-110.
[4] Harris H. Title four. NEJM. 2021;384(2):200-210.
[5] Jones J, King K. Title five. Nature. 2022;600(3):300-310."""

refs7 = extract_references_from_text(vancouver_doc)
expected7 = ['[1]', '[2]', '[3]', '[4]', '[5]']
found7 = [a for a in expected7 if any(a in r[:10] for r in refs7)]

print(f"Extracted {len(refs7)} refs (expected 5):")
for i, r in enumerate(refs7, 1):
    label = r[:95] + "..." if len(r) > 95 else r
    print(f"  {i}. {label}")
results["Test 7 (Vancouver)"] = "PASS" if len(found7) == 5 else "FAIL"
print(f"Result: {results['Test 7 (Vancouver)']} ({len(found7)}/5)")


# ── TEST 8: Mixed signals ────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 8: Mixed signals -- some with DOIs, some without")
print("=" * 60)
mixed_doc = """Body text.

References

Adams, R. (2018) 'Title one', Journal A, 5(1), pp. 10-20. doi: https://doi.org/10.1000/aaa
Brown, C. (2019) 'Title two', Journal B, 3(2), pp. 30-40. doi: https://doi.org/10.1000/bbb
Clark, D. (2020) 'Title three', Journal C, 7(4), pp. 50-60.
Evans, E. (2021) 'Title four', Journal D, 9(1), pp. 70-80. doi: https://doi.org/10.1000/ddd
Franks, F. (2022) 'Title five', Journal E, 2(3), pp. 90-100."""

refs8 = extract_references_from_text(mixed_doc)
expected8 = ['Adams', 'Brown', 'Clark', 'Evans', 'Franks']
found8 = [a for a in expected8 if any(a.lower() in r.lower()[:40] for r in refs8)]

print(f"Extracted {len(refs8)} refs (expected 5):")
for i, r in enumerate(refs8, 1):
    label = r[:95] + "..." if len(r) > 95 else r
    print(f"  {i}. {label}")
results["Test 8 (mixed signals)"] = "PASS" if len(found8) == 5 else "FAIL"
print(f"Result: {results['Test 8 (mixed signals)']} ({len(found8)}/5)")


# ── TEST 9: Org-name demerge — NHS + NMC merged on one line ──────────────
print("\n" + "=" * 60)
print("TEST 9: Org-name demerge -- NHS + NMC merged on one line")
print("=" * 60)
nhs_merged = (
    "NHS (2023) NHS Health Check. Available at: https://www.nhs.uk/tests-and-treatments/nhs-health-check/ "
    "(Accessed: 18 April 2026). "
    "Nursing and Midwifery Council (NMC). (2018). The Code: Professional standards of practice and behaviour "
    "for nurses, midwives and nursing associates. Available at: https://www.nmc.org.uk/globalassets/sitedocuments/"
    "nmc-publications/nmc-code.pdf (Accessed: 27 April 2026). "
    "Nursing and Midwifery Council (NMC). (2024). Standards of proficiency for registered nurses. Available at: "
    "https://www.nmc.org.uk/globalassets/sitedocuments/standards/2024/standards-of-proficiency-for-nurses.pdf "
    "(Accessed: 27 April 2026)."
)

refs9 = _split_ref_section_to_atomic(nhs_merged)
expected9 = ['NHS (2023)', 'Nursing and Midwifery Council (NMC). (2018)', 'Nursing and Midwifery Council (NMC). (2024)']
found9 = [a for a in expected9 if any(a.lower() in r.lower()[:60] for r in refs9)]
missing9 = [a for a in expected9 if a not in found9]

print(f"Extracted {len(refs9)} refs (expected 3):")
for i, r in enumerate(refs9, 1):
    label = r[:100] + "..." if len(r) > 100 else r
    print(f"  {i}. {label}")
print(f"\nMissing: {missing9}")
results["Test 9 (NHS+NMC demerge)"] = "PASS" if len(found9) == 3 else "FAIL"
print(f"Result: {results['Test 9 (NHS+NMC demerge)']} ({len(found9)}/3)")


# ── TEST 10: Org-name demerge via full pipeline ──────────────────────────
print("\n" + "=" * 60)
print("TEST 10: Org-name demerge via full pipeline")
print("=" * 60)
nhs_doc = """Some body text referencing (NHS, 2023) and (NMC, 2018) and (NMC, 2024).

References

NHS (2023) NHS Health Check. Available at: https://www.nhs.uk/tests-and-treatments/nhs-health-check/ (Accessed: 18 April 2026). Nursing and Midwifery Council (NMC). (2018). The Code: Professional standards of practice and behaviour for nurses, midwives and nursing associates. Available at: https://www.nmc.org.uk/globalassets/sitedocuments/nmc-publications/nmc-code.pdf (Accessed: 27 April 2026). Nursing and Midwifery Council (NMC). (2024). Standards of proficiency for registered nurses. Available at: https://www.nmc.org.uk/globalassets/sitedocuments/standards/2024/standards-of-proficiency-for-nurses.pdf (Accessed: 27 April 2026)."""

refs10 = extract_references_from_text(nhs_doc)
found10 = [a for a in expected9 if any(a.lower() in r.lower()[:60] for r in refs10)]
missing10 = [a for a in expected9 if a not in found10]

print(f"Extracted {len(refs10)} refs (expected 3):")
for i, r in enumerate(refs10, 1):
    label = r[:100] + "..." if len(r) > 100 else r
    print(f"  {i}. {label}")
print(f"\nMissing: {missing10}")
results["Test 10 (NHS+NMC pipeline)"] = "PASS" if len(found10) == 3 else "FAIL"
print(f"Result: {results['Test 10 (NHS+NMC pipeline)']} ({len(found10)}/3)")


# ── SUMMARY ───────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
for name, status in results.items():
    icon = "+" if status == "PASS" else "X"
    print(f"  [{icon}] {name}: {status}")

all_pass = all(s == "PASS" for s in results.values())
overall = "ALL PASS" if all_pass else "SOME FAILURES"
print(f"\nOverall: {overall}")
