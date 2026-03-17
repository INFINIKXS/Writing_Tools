import re

def extract_citations_regex(body_text: str):
    matched_spans = []
    
    # ─── Filter out document cross-references ───
    # Patterns like (Table 1), (Figure 2), (Appendix A)
    # Also handles multiple (Table 1, Figure 2) or (Table 1 and 2)
    cross_ref_pattern = re.compile(
        r'\(\s*(?:Table|Tab\.|Figure|Fig\.|Appendix|App\.)\s+[A-Za-z0-9]+'
        r'(?:\s*(?:,|and|&)\s*(?:Table|Tab\.|Figure|Fig\.|Appendix|App\.)?\s*[A-Za-z0-9]+)*\s*\)', 
        re.IGNORECASE
    )
    for match in cross_ref_pattern.finditer(body_text):
        matched_spans.append((match.start(), match.end()))
        print(f"Matched cross-ref: {match.group(0)}")
        
    return matched_spans


text = '''
Researchers found a significant correlation (Table 1).
The final study sample of 60 participants, including 30 participants each in the MBI and control groups (Appendix 1).
Detailed results can be seen below (Table 2).
Also, a prior study (Smith, 2020) confirmed this.
Here is another one (Table 1, Figure 2).
And another (Figure 3 and 4).
Even more complex (App. A, Table 3, and Fig. 4).
'''

results = extract_citations_regex(text)
print(results)
