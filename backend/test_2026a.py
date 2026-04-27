"""Test with the actual PDF to see what text is extracted around '2026a'."""
import io
import sys
from PyPDF2 import PdfReader
from citations.extraction import extract_reference_section, extract_citations_regex

# Read the PDF
pdf_path = sys.argv[1] if len(sys.argv) > 1 else None
if not pdf_path:
    print("Usage: python test_2026a.py <path_to_pdf>")
    sys.exit(1)

with open(pdf_path, 'rb') as f:
    reader = PdfReader(f)
    full_text = ""
    for page in reader.pages:
        full_text += page.extract_text() + "\n"

import re
full_text = re.sub(r' {2,}', ' ', full_text)

# Find all occurrences of "2026a" in the full text
print("=== Searching for '2026a' in full text ===")
for m in re.finditer(r'.{80}2026a.{80}', full_text, re.DOTALL):
    print(f"Position {m.start()}: {repr(m.group())}")
    print()

# Split into body and ref section  
body, refs = extract_reference_section(full_text)
print(f"\n=== Body length: {len(body)}, Ref section length: {len(refs)} ===")

# Check if 2026a is in body or refs
if '2026a' in body:
    print("'2026a' IS in body text")
else:
    print("'2026a' is NOT in body text (it's in the reference section!)")

if '2026a' in refs:
    print("'2026a' IS in reference section")

# Extract citations from body
citations = extract_citations_regex(body)
uk_cits = [c for c in citations if 'UK' in c['text'] or 'Data' in c['text']]
print(f"\n=== UK/Data citations found: {len(uk_cits)} ===")
for c in uk_cits:
    print(f"  {c['text']} ({c['type']})")

# Also show all citations
print(f"\n=== Total citations: {len(citations)} ===")
