import sys
sys.path.append('.')
from citations.ordering import _order_by_appearance

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

references = [
    "Alrashid Alhiraki, O., et al., 2022. Title.",
    "Marzouk, M., et al., 2023. Title.",
    "Garry, S. and Checchi, F., 2020. Title.",
    "Kohrt, B., et al., 2019. Title.",
    "Marou, et al., 2024. Title.",
    "Bogale, et al., 2024. Title.",
    "Kodo, et al., 2024. Title.",
    "Belaid, et al., 2020. Title."
]

reordered = _order_by_appearance(text, references, {})
for r in reordered:
    print(f"[{r['display_number']}] {r['ref']} (Cited as: {r['first_cited_as']})")
