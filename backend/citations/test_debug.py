import sys
import re
sys.path.append('c:\\Users\\Paradox-Labs\\Documents\\Projects\\Writing_Tools\\backend')
from citations.extraction import CITATION_PATTERNS

text = '''have when truths about their health are disclosed acts as the primary barrier to the participation of nurses in this process. However, Fragkaki and Fasoi (2024) found that nurses with high emotional intelligence (EI) possess the emotional regulation and resilience required to handle such interactions without withdrawing.

In the first study Cheng et al. (2021), the sample size was adequate, and their findings were statistically significant (p < 0.05). But their reliance on self-reported questionnaires introduced the risk of response and social desirability bias. In contrast, Fragkaki and Fasoi (2024) synthesised multiple rigorous studies. The avoidance of truth-telling in Cheng et al.'s (2021) study was probably due to a lack of emotional confidence, the same quality which according to Fragkaki and Fasoi (2024), can be acquired through emotional intelligence.'''

body_text = text

for name, pattern in CITATION_PATTERNS:
    for match in re.finditer(pattern, body_text):
        matched_text = match.group(0).strip()
        print('Found', name, ':', repr(matched_text), 'at', match.start())
        # Replace the matched text with blanks to avoid double matching
        body_text = body_text[:match.start()] + ' ' * len(match.group(0)) + body_text[match.end():]
