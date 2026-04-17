import json
import re

ref_texts = [
    "Avsar TS, McLeod H and Jackson L (2021) 'Health outcomes of smoking during pregnancy and the postpartum period: an umbrella review.', BMC pregnancy and childbirth, 21(1), pp. 254. doi: https://doi.org/10.1186/s12884-021-03729-1",
    "Blanc, J. et al. (2021) 'Nicotine Replacement Therapy during Pregnancy and Child Health Outcomes: A Systematic Review', International Journal of Environmental Research and Public Health, 18(8), pp. 4004.",
    "Lange S et al. (2018) 'National, regional, and global prevalence of smoking during pregnancy in the general population: a systematic review and meta-analysis.', The Lancet. Global health, 6(7), pp. e769-e776.",
    "Fletcher C et al. (2022) 'Isolation, marginalisation and disempowerment - understanding how interactions with health providers can influence smoking cessation in pregnancy.', BMC pregnancy and childbirth, 22(1), pp. 396."
]

for ref_text in ref_texts:
    metadata = {"volume": None, "issue": None, "pages": None, "source": None}
    
    vol_match = re.search(r'\b(\d+)\s*\(([\d\-A-Za-z]+)\)', ref_text)
    if vol_match:
        metadata["volume"] = vol_match.group(1)
        metadata["issue"] = vol_match.group(2)
        
    if metadata["volume"]:
        vol_pattern = r'\b' + re.escape(metadata["volume"]) + r'\s*\('
        m = re.search(vol_pattern, ref_text)
        if m:
            left_part = ref_text[:m.start()].strip()
            title_end_m = re.search(r'([\'"]|\.\s+)(.*?)[.,]?\s*$', left_part)
            if title_end_m:
                candidate = title_end_m.group(2).strip(" ,.")
                if len(candidate) > 4 and not candidate.lower().startswith('pp'):
                    metadata["source"] = candidate
                
    print(json.dumps(metadata))
