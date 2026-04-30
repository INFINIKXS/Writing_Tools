"""Test that PubMed/CrossRef lookups now populate day_month for Vancouver formatting."""
import sys
sys.path.append('.')

from references.metadata import perform_pubmed_lookup, perform_crossref_lookup
from citations.formatting import format_reference

# Test with a known DOI that has month data
doi = "10.1186/2110-5820-4-8"  # Ann Intensive Care, 2014 Mar

print("=" * 60)
print("TEST 1: PubMed lookup - day_month extraction")
print("=" * 60)

pm_meta = {
    "authors": None, "title": None, "year": None,
    "source": None, "doi": doi, "url": None,
    "volume": None, "issue": None, "pages": None,
    "publisher": None, "type": "Other",
}
pm_sources = {}

success = perform_pubmed_lookup(doi, pm_meta, pm_sources)
print(f"  PubMed success: {success}")
print(f"  year: {pm_meta.get('year')}")
print(f"  day_month: {pm_meta.get('day_month')}")
print(f"  source: {pm_meta.get('source_abbreviated') or pm_meta.get('source')}")

if success and pm_meta.get("day_month"):
    print("  >> PASS: day_month populated from PubMed")
else:
    print("  >> day_month not from PubMed, trying CrossRef...")

print()
print("=" * 60)
print("TEST 2: CrossRef lookup - day_month extraction")
print("=" * 60)

cr_meta = {
    "authors": None, "title": None, "year": None,
    "source": None, "doi": doi, "url": None,
    "volume": None, "issue": None, "pages": None,
    "publisher": None, "type": "Other",
}
cr_sources = {}

success2 = perform_crossref_lookup(doi, cr_meta, cr_sources)
print(f"  CrossRef success: {success2}")
print(f"  year: {cr_meta.get('year')}")
print(f"  day_month: {cr_meta.get('day_month')}")

if success2 and cr_meta.get("day_month"):
    print("  >> PASS: day_month populated from CrossRef")
else:
    print("  >> WARN: CrossRef did not return month data for this DOI")

# Test 3: Format the reference in Vancouver and check the date chain
print()
print("=" * 60)
print("TEST 3: Vancouver formatted output")
print("=" * 60)

# Use whichever metadata succeeded
meta = pm_meta if pm_meta.get("title") else cr_meta
if isinstance(meta.get("authors"), str):
    if '; ' in meta["authors"]:
        meta["authors"] = [a.strip() for a in meta["authors"].split(';') if a.strip()]
    else:
        meta["authors"] = [meta["authors"].strip()]

formatted = format_reference(meta, "vancouver")
print(f"  Formatted: {formatted['formatted']}")

has_month = any(m in formatted['formatted'] for m in [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
])
if has_month:
    print("  >> PASS: Month present in Vancouver output")
else:
    print("  >> FAIL: No month in Vancouver output")
