import sys
sys.path.append('.')
from citations.verification import verify_matches_with_string_search

refs = [
    "UK Data Service (2026a) Something about data. Available at: https://example.com (Accessed: 24 April 2026).",
    "UK Data Service (2026b) Types of data access. Available at: https://ukdataservice.ac.uk/help/access-policy/types-of-data-access/ (Accessed: 24 April 2026).",
]

citations = [
    "(UK Data Service, 2026a)",
    "(UK Data Service, 2026b)",
]

result = verify_matches_with_string_search(citations, refs)

print("=== Confirmed Matches ===")
for m in result["confirmed_matches"]:
    print(f"  {m['citation']} -> {m['matched_ref'][:60]}...")

print(f"\n=== Unmatched Citations ({len(result['unmatched_citations'])}) ===")
for c in result["unmatched_citations"]:
    print(f"  {c}")

print(f"\n=== Unmatched References ({len(result['unmatched_references'])}) ===")
for r in result["unmatched_references"]:
    print(f"  {r[:60]}...")
