import re

ref = 'Nnate, D. A., & Nashwan, A. J. (2023). Emotional Intelligence and Delivering Bad News in Professional Nursing Practice. Cureus, 15(6), e40353. https://doi.org/10.7759/cureus.40353'

def extract_author_year(text):
    author = None
    year = None
    author_match = re.match(r'^[^a-z]*?([A-Z][a-zA-Zà-öø-ÿ\'-]+)', text.strip())
    if author_match:
        author = author_match.group(1).lower()
    year_match = re.search(r'\b(19|20)\d{2}\b', text)
    if year_match:
        year = year_match.group(0)
    return (author, year)

print('Nnate author/year:', extract_author_year(ref))

ref2 = 'Springer, F., Sautier, L., Schilling, G., Koch-Gromus, U., Bokemeyer, C., Friedrich, M., ... & Esser, P. (2023). Effect of depression, anxiety, and distress screeners on the need, intention, and utilization of psychosocial support services among cancer patients. Supportive Care in Cancer, 31(2), 117. https://doi.org/10.1007/s00520-023-07580-2'
print('Springer author/year:', extract_author_year(ref2))

