"""Verify the newline-in-parentheses fix works for all scenarios."""
from citations.extraction import extract_citations_regex

tests = [
    # Normal - should always work
    ("normal", "purpose (UK Data Service, 2026a). Therefore"),
    # Line break between Data and Service (most likely PDF scenario)
    ("Data\\nService", "purpose (UK Data\nService, 2026a). Therefore"),
    # Line break between UK and Data  
    ("UK\\nData", "purpose (UK\nData Service, 2026a). Therefore"),
    # Citation starts on new line
    ("newline before", "purpose\n(UK Data Service, 2026a). Therefore"),
    # The b version for comparison
    ("2026b normal", "Act 2018 (UK Data Service, 2026b). As used"),
    ("2026b linebreak", "Act 2018 (UK Data\nService, 2026b). As used"),
]

print("Testing UK Data Service citation detection:")
print("-" * 70)
all_pass = True
for label, text in tests:
    results = extract_citations_regex(text)
    found = [c["text"] for c in results]
    passed = len(found) == 1 and "UK Data Service" in found[0]
    status = "PASS" if passed else "FAIL"
    if not passed:
        all_pass = False
    print(f"  [{status}] {label:20s} -> {found}")

print("-" * 70)
print(f"{'All tests passed!' if all_pass else 'SOME TESTS FAILED'}")
