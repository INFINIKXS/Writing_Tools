"""
Citation style detection from reference lists and individual reference classification.
"""
import re
from collections import defaultdict


def detect_style_from_references(reference_list):
    """
    Detects citation style using ONLY the reference list entries.
    Reference list formatting is far more distinctive than in-text citations.
    
    reference_list: list of strings, each being one reference entry.
    Returns: { style, confidence, evidence, all_scores }
    """
    scores = defaultdict(float)
    evidence = defaultdict(list)

    ref_block = '\n'.join(reference_list)
    total_refs = len(reference_list)
    if total_refs == 0:
        return {'style': 'apa', 'confidence': 0, 'evidence': ['Empty reference list']}

    # ── VANCOUVER ─────────────────────────────────────────────────────────
    # Refs start with a number: "1." or "[1]"
    v1 = [r for r in reference_list if re.match(r'^\[?\d+\]?\.?\s', r.strip())]
    if v1:
        scores['vancouver'] += 10 * (len(v1) / total_refs)
        evidence['vancouver'].append(f'{len(v1)}/{total_refs} entries start with a number')

    # Author format: "Smith J," or "Smith JA," — surname then initials, NO comma before initials
    v2 = re.findall(r'\b[A-Z][a-z]+\s+[A-Z]{1,3},', ref_block)
    if v2:
        scores['vancouver'] += 8 * min(len(v2) / total_refs, 1)
        evidence['vancouver'].append(f'Author format "Surname Initials," found ({len(v2)} times)')

    # Journal format: "Journal Name. YYYY;Vol(Issue):Pages"
    v3 = re.findall(r'\.\s*\d{4}\s*;\s*\d+\s*(?:\(\d+\))?\s*:\s*\d+', ref_block)
    if v3:
        scores['vancouver'] += 9 * min(len(v3) / total_refs, 1)
        evidence['vancouver'].append(f'Vancouver journal format "YYYY;Vol(Issue):Pages" ({len(v3)} entries)')

    # doi at end without "doi:" label or with lowercase "doi:"
    v4 = re.findall(r'\bdoi:\s*10\.\d{4}', ref_block, re.IGNORECASE)
    if v4:
        scores['vancouver'] += 3 * min(len(v4) / total_refs, 1)
        evidence['vancouver'].append(f'{len(v4)} DOI entries found')

    # ── VANCOUVER SHARED OVERRIDE ──
    # DOIs are shared by all styles. If no deeply Vancouver-specific
    # markers are found (numbered lists, "Surname JA", or Vancouver journal structure), zero out score.
    if not (v1 or v2 or v3):
        scores['vancouver'] = 0
        evidence['vancouver'] = []

    # ── APA ───────────────────────────────────────────────────────────────
    # Author format: "Smith, J." or "Smith, J. A." — surname COMMA initial DOT
    a1 = re.findall(r'\b[A-Z][a-z]+,\s+[A-Z]\.\s*(?:[A-Z]\.\s*)?(?:,|&|\()', ref_block)
    if a1:
        scores['apa'] += 9 * min(len(a1) / total_refs, 1)
        evidence['apa'].append(f'APA author format "Surname, I." found ({len(a1)} times)')

    # Year in parentheses after authors: "(2020)."
    a2 = re.findall(r'\(\d{4}[a-z]?\)\.', ref_block)
    if a2:
        scores['apa'] += 10 * min(len(a2) / total_refs, 1)
        evidence['apa'].append(f'APA year format "(YYYY)." found ({len(a2)} entries)')

    # Title NOT italicised (plain text title after year, before journal)
    # APA: Smith, J. (2020). Title of article. Journal Name, vol(issue), pages.
    a3 = re.findall(r'\(\d{4}\)\.\s+[A-Z][^.]+\.\s+[A-Z]', ref_block)
    if a3:
        scores['apa'] += 7 * min(len(a3) / total_refs, 1)
        evidence['apa'].append(f'APA sentence structure ".(YYYY). Title. Journal" ({len(a3)} entries)')

    # APA journal: volume in italics represented as "Journal, 10(2), 45–67."
    a4 = re.findall(r',\s*\d+\(\d+\),\s*\d+', ref_block)
    if a4:
        scores['apa'] += 8 * min(len(a4) / total_refs, 1)
        evidence['apa'].append(f'APA journal format "Vol(Issue), Pages" ({len(a4)} entries)')

    # ── APA SHARED OVERRIDE ──
    # APA shares "Surname, I." (a1) with styles like Harvard.
    # If no uniquely APA signals are found, zero out the score to prevent false positives.
    if not (a2 or a3 or a4):
        scores['apa'] = 0
        evidence['apa'] = []

    # ── HARVARD ───────────────────────────────────────────────────────────
    # Author format: "Surname, I." — comma before initial, dot after (shared with APA)
    h1 = re.findall(r'\b[A-Z][a-z]+,\s+[A-Z]\.', ref_block)
    if h1:
        scores['harvard'] += 4 * min(len(h1) / total_refs, 1)
        evidence['harvard'].append(f'Harvard/APA author format "Surname, I." ({len(h1)} times)')

    # Title in single quotes: 'Title of article', — STRONGEST Harvard signal, unique to Harvard
    h2 = re.findall(r"'[A-Z][^']{10,}'", ref_block)
    if h2:
        scores['harvard'] += 15 * min(len(h2) / total_refs, 1)
        evidence['harvard'].append(f'Harvard single-quoted title ({len(h2)} entries)')

    # Year in parentheses FOLLOWED by single-quoted title: (2020) 'Title'
    h3 = re.findall(r"\(\d{4}[a-z]?\)\s+'", ref_block)
    if h3:
        scores['harvard'] += 12 * min(len(h3) / total_refs, 1)
        evidence['harvard'].append(f'Harvard year+title pattern "(YYYY) \'Title\'" ({len(h3)} entries)')

    # "pp." page format: pp. 83-95
    h4 = re.findall(r'\bpp\.\s*\d+[–\-]\d+', ref_block)
    if h4:
        scores['harvard'] += 8 * min(len(h4) / total_refs, 1)
        evidence['harvard'].append(f'Harvard "pp. X-Y" page format ({len(h4)} entries)')

    # "Available at:" phrase — Harvard-specific
    h5 = re.findall(r'\bAvailable\s+at:', ref_block, re.IGNORECASE)
    if h5:
        scores['harvard'] += 7 * min(len(h5) / total_refs, 1)
        evidence['harvard'].append(f'Harvard "Available at:" phrase ({len(h5)} entries)')

    # "(Accessed:" phrase — Harvard-specific
    h6 = re.findall(r'\(Accessed:', ref_block, re.IGNORECASE)
    if h6:
        scores['harvard'] += 6 * min(len(h6) / total_refs, 1)
        evidence['harvard'].append(f'Harvard "(Accessed:" phrase ({len(h6)} entries)')

    # ── HARVARD SHARED OVERRIDE ──
    if not (h2 or h3 or h5 or h6):
        scores['harvard'] = 0
        evidence['harvard'] = []

    # ── MLA ───────────────────────────────────────────────────────────────
    # "Works Cited" heading is the strongest MLA signal
    if re.search(r'\bWorks\s+Cited\b', ref_block, re.IGNORECASE):
        scores['mla'] += 20
        evidence['mla'].append('"Works Cited" section heading found')

    # MLA author: "Smith, John." — full first name, not initials
    m1 = re.findall(r'^[A-Z][a-z]+,\s+[A-Z][a-z]{2,}\.', ref_block, re.MULTILINE)
    if m1:
        scores['mla'] += 9 * min(len(m1) / total_refs, 1)
        evidence['mla'].append(f'MLA author format "Surname, Firstname." ({len(m1)} entries)')

    # MLA ends with year: "Publisher, 2020." or "Publisher, 2020. Web."
    m2 = re.findall(r',\s*\d{4}\.\s*(?:Web\.|Print\.|$)', ref_block, re.MULTILINE)
    if m2:
        scores['mla'] += 8 * min(len(m2) / total_refs, 1)
        evidence['mla'].append(f'MLA year-at-end format ({len(m2)} entries)')

    # ── CHICAGO ───────────────────────────────────────────────────────────
    c1 = re.findall(
        r'[A-Z][a-z]+,\s+[A-Z][a-z]+\.\s+\d{4}\.\s+["\*_A-Z]',
        ref_block
    )
    if c1:
        scores['chicago'] += 10 * min(len(c1) / total_refs, 1)
        evidence['chicago'].append(f'Chicago format "Surname, Firstname. YYYY. Title." ({len(c1)} entries)')

    # Chicago uses em-dash for repeated author (———)
    if '———' in ref_block or '—' * 3 in ref_block:
        scores['chicago'] += 10
        evidence['chicago'].append('Chicago repeated-author em-dash (———) found')

    # ── RESULT ────────────────────────────────────────────────────────────
    if not any(scores.values()):
        return {
            'style': 'apa',
            'confidence': 0,
            'evidence': ['No strong signals detected — defaulting to APA'],
            'all_scores': {}
        }

    MAX_SCORE_PER_STYLE = 100

    # Cap each style's raw accumulated score to MAX_SCORE_PER_STYLE
    for style in scores:
        scores[style] = min(scores[style], MAX_SCORE_PER_STYLE)
    
    total_score = sum(scores.values())
    winner = max(scores, key=scores.get)
    
    confidence = min(
        round((scores[winner] / total_score) * 100),
        100
    )

    return {
        'style': winner,
        'confidence': confidence,
        'evidence': evidence[winner],
        'all_scores': {
            k: min(round((v / total_score) * 100), 100)
            for k, v in sorted(scores.items(), key=lambda x: -x[1])
        }
    }


def classify_single_reference(ref_text):
    """
    Classify a single reference entry into its most likely citation style.
    Returns the style name string (e.g. 'vancouver', 'apa', 'harvard').
    """
    scores = defaultdict(float)
    text = ref_text.strip()

    # ── Vancouver signals ──
    if re.match(r'^\[?\d+\]?\.?\s', text):
        scores['vancouver'] += 10
    van_authors = re.findall(r'\b[A-Z][a-z]+\s+[A-Z]{1,3},', text)
    if van_authors:
        scores['vancouver'] += 8
    if re.search(r'\.\s*\d{4}\s*;\s*\d+\s*(?:\(\d+\))?\s*:\s*\d+', text):
        scores['vancouver'] += 9

    # ── APA signals ──
    apa_authors = re.findall(r'\b[A-Z][a-z]+,\s+[A-Z]\.\s*(?:[A-Z]\.\s*)?(?:,|&|\()', text)
    if apa_authors:
        scores['apa'] += 9
    if re.search(r'\(\d{4}[a-z]?\)\.', text):
        scores['apa'] += 10
    if re.search(r',\s*\d+\(\d+\),\s*\d+', text):
        scores['apa'] += 8

    # ── Harvard signals ──
    if re.search(r'\b[A-Z][a-z]+,\s+[A-Z]\.', text):
        scores['harvard'] += 4
    if re.search(r"'[A-Z][^']{10,}'", text):
        scores['harvard'] += 15
    if re.search(r"\(\d{4}[a-z]?\)\s+'", text):
        scores['harvard'] += 12
    if re.search(r'\bpp\.\s*\d+[–\-]\d+', text):
        scores['harvard'] += 8
    if re.search(r'\bAvailable\s+at:', text, re.IGNORECASE):
        scores['harvard'] += 7
    if re.search(r'\(Accessed:', text, re.IGNORECASE):
        scores['harvard'] += 6

    # ── MLA signals ──
    if re.match(r'^[A-Z][a-z]+,\s+[A-Z][a-z]{2,}\.', text):
        scores['mla'] += 9
    if re.search(r',\s*\d{4}\.\s*(?:Web\.|Print\.|$)', text):
        scores['mla'] += 8

    # ── Chicago signals ──
    if re.search(r'[A-Z][a-z]+,\s+[A-Z][a-z]+\.\s+\d{4}\.\s+["*_A-Z]', text):
        scores['chicago'] += 10

    if not any(scores.values()):
        return 'unknown'

    return max(scores, key=scores.get)
