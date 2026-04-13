"""End-to-end test: replay verbatim_debug.json through the ACTUAL function and verify
that the returned dictionary uses original (un-normalized) keys."""
import json, sys

sys.path.insert(0, '.')

with open("verbatim_debug.json", "r", encoding="utf-8") as f:
    data = json.load(f)

from citations.verification import extract_verbatim_references

result = extract_verbatim_references(data["full_text"], data["ai_references"])

# Find the Children's Health Ireland entry
target_key = [k for k in data["ai_references"] if k.startswith("Children")][0]
print(f"=== LOOKUP KEY ===")
print(f"  Original AI ref key: {repr(target_key[:60])}...")
has_curly = '\u2019' in target_key
print(f"  Key contains curly apostrophe: {has_curly}")
print()

# Check if the key exists in the result
if target_key in result:
    entry = result[target_key]
    print(f"=== LOOKUP RESULT ===")
    print(f"  FOUND! confidence={entry['confidence']}")
    print(f"  verbatim preview: {entry['verbatim'][:80]}...")
else:
    print(f"=== LOOKUP RESULT ===")
    print(f"  NOT FOUND - key mismatch still exists!")
    print(f"  Available keys containing 'Children':")
    for k in result:
        if "Children" in k or "children" in k:
            print(f"    {repr(k[:60])}...")
    
    # Check if a normalized version exists
    normalized_key = target_key.replace('\u2019', "'")
    if normalized_key in result:
        print(f"\n  Normalized key IS in result — key mismatch confirmed!")

print()
# Print ALL references with low confidence
print(f"=== LOW CONFIDENCE REFS ===")
for k, v in result.items():
    if v['confidence'] < 0.75:
        print(f"  {k[:60]}... -> confidence={v['confidence']}")

if not any(v['confidence'] < 0.75 for v in result.values()):
    print(f"  NONE! All {len(result)} references have confidence >= 0.75")
