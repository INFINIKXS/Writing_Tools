import sys
sys.path.insert(0, '.')
from citations.verification import extract_verbatim_references
doc_text = """
References
Children's Health Ireland. (2021). Emergency department management of asthma.
https://www.childrenshealthireland.ie/documents/1774/ED-Flowchart-Management-of-Asthma.pdf
"""
ai_refs = ["Children's Health Ireland. (2021). Emergency department management of asthma. https://www.childrenshealthireland.ie/documents/1774/ED-Flowchart-Management-of-Asthma.pdf"]

verbatim = extract_verbatim_references(doc_text, ai_refs)
print(verbatim)
