import sys
sys.path.insert(0, '.')
from citations.verification import extract_verbatim_references
doc_text = """Bawah, R. (2023). Nursing. Int J, 5, 100160. Children's Health Ireland. (2021). Emergency asthma. https://example.com/file.pdf"""
ai_refs = ["Children's Health Ireland. (2021). Emergency asthma. https://example.com/file.pdf"]
verbatim = extract_verbatim_references(doc_text, ai_refs)
print("Score after fix:", verbatim)
