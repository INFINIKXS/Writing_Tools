import re
import unicodedata

text = """
fighting. Among the first casualties of any conflict are the surveillance systems, civil
registries, and health information networks on which mortality measurement depends
(Alrashid Alhiraki et al., 2022; Marzouk et al., 2023). This is why the most-cited
mortality figures are unreliable. The popular 9:1 ratio of indirect to direct deaths is
itself an estimate built on a handful of studies (Garry and Checchi, 2020). Until real-
time surveillance exists, the true scale of excess mortality cannot be known. And the
regression of SDG 3 targets in conflict zones is almost certainly worse than current
figures suggest (Kohrt et al., 2019; Marou et al., 2024).

Critical Evaluation of War's Impact on SDG 3 Targets

Women and newborns bear the heaviest burden of war's infrastructural collapse. The
SDG targets that aim to reduce maternal and child mortality — 3.1 and 3.2 — cannot
be reached without them (Kohrt et al., 2019). Maternal survival depends on three
things working together: a timely decision to seek care, a way to reach it, and the
means to deliver it once a gravid woman arrives (Bogale et al., 2024; Kodo et al.,
2024). Kodo et al.'s (2024) study of the Ethiopian conflict shows each part of that
chain breaking down. According to their study, this is due to the destruction of health
facilities, the looting of ambulances, and frequent power outages that followed,
leading to a surge in obstructed labour, postpartum haemorrhage, and unassisted home
deliveries. The pattern recurs in South Sudan, but at a different level. Belaid et al.'s
(2020) evaluation of reproductive health programmes there identified shortages in
workforce, supply chain failures, and weak governance as barriers to maternal
survival. While Belaid et al. (2020) largely attribute maternal health failures to macro-
level governance and workforce deficits, Kodo et al. (2024) demonstrate that the
micro-level physical destruction of referral logistics renders existing policies and staff
"""

def _normalise_surname(surname):
    s = unicodedata.normalize('NFKD', surname)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()

def _extract_citations(body_text):
    seen = {}
    text_flat = body_text.replace('\n', ' ')

    # 1. Parenthetical APA/Harvard: (Author, 2020; Author 2021)
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

    # 2. Narrative APA/Harvard: Author et al. (2020)
    # Use a strict word match to avoid grabbing preceding words
    for m in re.finditer(r'\b([A-Z][a-zA-Z\u00C0-\u00F6\u00F8-\u00FF\-\']+)(?:\s+(?:and|&)\s+[A-Z][a-zA-Z\u00C0-\u00F6\u00F8-\u00FF\-\']+)*(?:\s+et\s+al\.?)?(?:\'s)?\s*\(((?:19|20)\d{2}[a-z]?)\)', text_flat):
        pos = m.start()
        author_part = m.group(1).strip()
        year = m.group(2)
        key = (_normalise_surname(author_part), year)
        if key not in seen:
            seen[key] = (pos, m.group(0))

    return seen

citations = _extract_citations(text)
appearance_order = sorted(citations.keys(), key=lambda k: citations[k][0])
for key in appearance_order:
    print(key, "at", citations[key])
