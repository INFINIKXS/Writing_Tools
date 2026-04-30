"""
Reference ordering: by appearance (Vancouver) or alphabetically (Harvard/APA).
"""
import re
import unicodedata
from collections import OrderedDict

from citations.detection import detect_style_from_references, classify_single_reference


def _expand_range(s):
    """Turn '1,2,3' or '1-4' or '1–4' into a list of ints."""
    nums = []
    for part in re.split(r',\s*', s):
        ends = re.split(r'[–\-]', part.strip())
        if len(ends) == 2:
            try:
                nums.extend(range(int(ends[0]), int(ends[1]) + 1))
            except ValueError:
                continue
        else:
            try:
                nums.append(int(ends[0]))
            except ValueError:
                continue
    return nums


def _extract_ref_number(ref_string):
    """Extract the leading number from a numbered reference like '1. Smith...' or '[1] Smith...'"""
    m = re.match(r'^\[?(\d+)\]?\.?\s', ref_string.strip())
    return int(m.group(1)) if m else None


def _normalise_surname(surname):
    """Lowercase and strip punctuation for consistent key comparison."""
    s = unicodedata.normalize('NFKD', surname)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def _order_by_appearance(body_text, references, verbatim_map):
    """Order references by their first appearance in the body text (Vancouver style)."""
    seen = OrderedDict()  # canonical_key -> (position, original_text)

    # Clean newlines to make parsing easier without changing string length
    text_flat = body_text.replace('\n', ' ')

    # 1. Vancouver numbered: [1], [1, 2], [1-3]
    for m in re.finditer(r'\[(\d+(?:\s*[,–\-]\s*\d+)*)\]', text_flat):
        pos = m.start()
        # skip if it looks like a year, e.g. [2020]
        if re.match(r'^\[(19|20)\d{2}\]$', m.group(0)):
            continue
        for part in re.split(r',\s*', m.group(1)):
            ends = re.split(r'[–\-]', part.strip())
            try:
                if len(ends) == 2:
                    for num in range(int(ends[0]), int(ends[1]) + 1):
                        key = ('__numbered__', str(num))
                        if key not in seen:
                            seen[key] = (pos, m.group(0))
                else:
                    num = int(ends[0])
                    key = ('__numbered__', str(num))
                    if key not in seen:
                        seen[key] = (pos, m.group(0))
            except ValueError:
                pass

    # 2. Parenthetical APA/Harvard: (Author, 2020; Author 2021)
    for m in re.finditer(r'\(([^)]*\b(?:19|20)\d{2}[a-z]?[^)]*)\)', text_flat):
        pos = m.start()
        content = m.group(1)
        
        parts = content.split(';')
        for i, part in enumerate(parts):
            part = part.strip()
            ym = re.search(r'\b((?:19|20)\d{2}[a-z]?)\b', part)
            if ym:
                year = ym.group(1)
                author_part = part[:ym.start()].strip(', ')
                if author_part:
                    author_part = re.sub(r'\s+et\s+al\.?$', '', author_part).strip()
                    first_author = re.split(r'\s+and\s+|\s+&\s+|,', author_part)[0].strip()
                    if first_author:
                        first_word = first_author.split()[0]
                        key = (_normalise_surname(first_word), year)
                        if key not in seen: 
                            seen[key] = (pos + i, m.group(0))

    # 3. Narrative APA/Harvard: Author et al. (2020) or Author et al.'s (2020)
    for m in re.finditer(r'\b([A-Z][a-zA-Z\u00C0-\u00F6\u00F8-\u00FF\-\']+)(?:\s+(?:and|&)\s+[A-Z][a-zA-Z\u00C0-\u00F6\u00F8-\u00FF\-\']+)*(?:\s+et\s+al\.?)?(?:\'s)?\s*\(((?:19|20)\d{2}[a-z]?)\)', text_flat):
        pos = m.start()
        author_part = m.group(1).strip()
        year = m.group(2)
        key = (_normalise_surname(author_part), year)
        if key not in seen:
            seen[key] = (pos, m.group(0))

    appearance_order = sorted(seen.keys(), key=lambda k: seen[k][0])

    # Build lookup indices for the reference list
    ref_by_num = {}
    ref_by_surname_year = {}
    
    def _ref_surname(ref_text):
        match = re.search(r'^([A-Z][a-zA-Z\u00C0-\u00F6\u00F8-\u00FF\'\-]+)', ref_text.strip())
        return _normalise_surname(match.group(1)) if match else None

    def _ref_year(ref_text):
        m = re.search(r'\b(19|20)\d{2}[a-z]?\b', ref_text)
        return m.group(0) if m else None

    for ref in references:
        old_num = _extract_ref_number(ref)
        if old_num is not None:
            ref_by_num[str(old_num)] = ref
            
        s = _ref_surname(ref)
        y = _ref_year(ref)
        if s:
            ref_by_surname_year.setdefault((s, y), ref)

    reordered = []
    counter = 1
    matched_refs = set()

    for key in appearance_order:
        matched_ref = None
        if key[0] == '__numbered__':
            matched_ref = ref_by_num.get(key[1])
        else:
            matched_ref = ref_by_surname_year.get(key)
            if not matched_ref:
                for rk, rv in ref_by_surname_year.items():
                    if rk[0] == key[0]:
                        matched_ref = rv
                        break

        if not matched_ref or matched_ref in matched_refs:
            continue

        matched_refs.add(matched_ref)
        verbatim_entry = (verbatim_map or {}).get(matched_ref, {})
        reordered.append({
            "display_number": counter,
            "ref": matched_ref,
            "verbatim": verbatim_entry.get("verbatim"),
            "verbatim_html": verbatim_entry.get("verbatim_html"),
            "first_cited_as": seen[key][1],
        })
        counter += 1

    # Append uncited references
    for ref in references:
        if ref not in matched_refs:
            verbatim_entry = (verbatim_map or {}).get(ref, {})
            reordered.append({
                "display_number": counter,
                "ref": ref,
                "verbatim": verbatim_entry.get("verbatim"),
                "verbatim_html": verbatim_entry.get("verbatim_html"),
                "first_cited_as": None,
            })
            counter += 1

    return reordered


def _order_alphabetically(references, verbatim_map):
    """Order references alphabetically by first author surname."""
    def sort_key(ref):
        m = re.match(r'^([A-Za-z\u00C0-\u00F6\u00F8-\u00FF\'\-]+)', ref.strip())
        return m.group(1).lower() if m else ''

    sorted_refs = sorted(references, key=sort_key)
    result = []
    for ref in sorted_refs:
        verbatim_entry = (verbatim_map or {}).get(ref, {})
        result.append({
            "display_number": None,
            "ref": ref,
            "verbatim": verbatim_entry.get("verbatim"),
            "verbatim_html": verbatim_entry.get("verbatim_html"),
            "first_cited_as": None,
        })
    return result


def apply_reference_ordering(body_text, references, verbatim_map=None):
    """
    Main pipeline: detect style, reorder references accordingly.
    Returns dict with 'style', 'ordered_refs', and confidence specs.
    """
    detection_result = detect_style_from_references(references)
    style = detection_result['style']

    if style == 'vancouver':
        ordered = _order_by_appearance(body_text, references, verbatim_map)
    else:
        ordered = _order_alphabetically(references, verbatim_map)

    # ── Per-reference style classification & outlier flagging ──
    for entry in ordered:
        ref_text = entry.get('ref', '')
        ref_style = classify_single_reference(ref_text)
        entry['ref_style'] = ref_style
        entry['is_style_outlier'] = (ref_style != style and ref_style != 'unknown')

    return {
        "style": style,
        "style_detection_confidence": detection_result.get('confidence', 0),
        "style_detection_evidence": detection_result.get('evidence', []),
        "style_all_scores": detection_result.get('all_scores', {}),
        "ordered_refs": ordered,
    }
