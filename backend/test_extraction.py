import sys
sys.path.insert(0, '.')
from citations.verification import extract_verbatim_references
doc_text = """Bawah, R. (2023). Nursing. Int J, 5, 100160. Children's Health Ireland. (2021). Emergency asthma. https://example.com/file.pdf"""
ai_refs = ["Children's Health Ireland. (2021). Emergency asthma. https://example.com/file.pdf"]

# Local mock of the function body
from citations.verification import extract_author_year
ai_author, ai_year = extract_author_year(ai_refs[0])
cand_author, cand_year = extract_author_year(doc_text)
print("ai:", ai_author, ai_year)
print("cand:", cand_author, cand_year)
print("author_ok:", (not ai_author) or (not cand_author) or (ai_author in cand_author) or (cand_author in ai_author))
print("year_ok:", (not ai_year) or (not cand_year) or (ai_year == cand_year))
