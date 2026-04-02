from citations.extraction import detect_document_consistency_issues

# Test 1: Mixed and/& in PARENTHETICAL only — should flag
print("=== Test 1: Parenthetical and/& mixing (SHOULD flag) ===")
citations = [
    {"text": "(Fragkaki and Fasoi, 2024)", "type": "PAR_TWO"},
    {"text": "(Capili & Anastasi, 2023)", "type": "PAR_TWO"},
]
issues = detect_document_consistency_issues(citations)
for issue in issues:
    print("  [" + issue["type"] + "] " + issue["details"])

# Test 2: Narrative "and" + Parenthetical "&" — should NOT flag inconsistency
print("\n=== Test 2: Narrative and + Parenthetical & (should NOT flag inconsistency) ===")
citations2 = [
    {"text": "Nnate and Nashwan (2023)", "type": "NAR_TWO"},
    {"text": "Wang and Zhang (2024)", "type": "NAR_TWO"},
    {"text": "(Capili & Anastasi, 2023)", "type": "PAR_TWO"},
]
issues2 = detect_document_consistency_issues(citations2)
print("  Issues found:", len(issues2))
for issue in issues2:
    print("  [" + issue["type"] + "] " + issue["details"])

# Test 3: Narrative using "&" — should flag as incorrect
print("\n=== Test 3: Narrative with & (SHOULD flag as incorrect) ===")
citations3 = [
    {"text": "Nnate & Nashwan (2023)", "type": "NAR_TWO"},
    {"text": "Nnate and Nashwan (2023)", "type": "NAR_TWO"},
]
issues3 = detect_document_consistency_issues(citations3)
for issue in issues3:
    print("  [" + issue["type"] + "] " + issue["details"])
    for g in issue.get("groups", []):
        print("    " + g["label"] + ": " + str(g["examples"]))

# Test 4: All consistent — no issues
print("\n=== Test 4: All consistent (should be empty) ===")
citations4 = [
    {"text": "Nnate and Nashwan (2023)", "type": "NAR_TWO"},
    {"text": "(Capili & Anastasi, 2023)", "type": "PAR_TWO"},
    {"text": "(Doe & Brown, 2021)", "type": "PAR_TWO"},
]
issues4 = detect_document_consistency_issues(citations4)
print("  Issues found:", len(issues4))
