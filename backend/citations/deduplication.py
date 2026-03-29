"""
Reference deduplication pipeline: DOI matching, author+year matching, fuzzy title matching.
"""
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher

from utils.text_utils import extract_doi, normalise_text, title_similarity, full_string_similarity


def extract_fields(ref_string):
    """Pull out the key comparable fields from a reference string."""
    author_match = re.match(r'^[^a-zA-Z]*([A-Z][a-zÀ-ÖØ-öø-ÿ\'\-]+)', ref_string.strip())
    first_author = author_match.group(1).lower() if author_match else ''

    year_match = re.search(r'\b(19|20)\d{2}\b', ref_string)
    year = year_match.group() if year_match else ''

    title_raw = re.sub(r'^\[?\d+\]?\.?\s*', '', ref_string.strip())
    title_raw = re.sub(r'^[A-Z][a-z]+.*?\.\s+', '', title_raw, count=1)
    title_raw = re.sub(r'\b(19|20)\d{2}\b.*', '', title_raw)
    title_clean = normalise_text(title_raw)

    return {
        'first_author': first_author,
        'year': year,
        'title': title_clean,
        'raw': ref_string
    }


def deduplicate_references(reference_list, title_threshold=0.92, full_string_threshold=0.97):
    """
    Returns:
      - unique_refs: deduplicated list (one entry per unique work)
      - duplicate_groups: list of lists, each group = same work repeated
      - duplicate_flags: dict mapping index -> canonical duplicate index
    """
    n = len(reference_list)
    parsed = [extract_fields(r) for r in reference_list]
    dois   = [extract_doi(r) for r in reference_list]

    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    for i in range(n):
        for j in range(i + 1, n):
            # Tier 1: DOI match
            if dois[i] and dois[j] and dois[i] == dois[j]:
                union(i, j)
                continue

            # Tier 2: Author + year match, then fuzzy title
            if (parsed[i]['first_author'] and parsed[j]['first_author'] and
                parsed[i]['first_author'] == parsed[j]['first_author'] and
                parsed[i]['year'] == parsed[j]['year']):
                sim = title_similarity(parsed[i]['title'], parsed[j]['title'])
                if sim >= title_threshold:
                    union(i, j)
                    continue

            # Tier 3: Full string similarity fallback
            sim = full_string_similarity(reference_list[i], reference_list[j])
            if sim >= full_string_threshold:
                union(i, j)

    clusters = defaultdict(list)
    for i in range(n):
        clusters[find(i)].append(i)

    unique_refs = []
    duplicate_groups = []
    duplicate_flags = {}

    for root, members in clusters.items():
        canonical_idx = min(members)
        unique_refs.append(reference_list[canonical_idx])

        if len(members) > 1:
            duplicate_groups.append([reference_list[m] for m in members])
            for m in members:
                if m != canonical_idx:
                    duplicate_flags[m] = canonical_idx

    return unique_refs, duplicate_groups, duplicate_flags
