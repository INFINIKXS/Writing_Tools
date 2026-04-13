import re
pattern = re.compile(
    r'^(?:'
    r'[A-Z][a-zA-Zà-öø-ÿ\'\-]+\s*,'
    r'|[A-Z][a-zA-Zà-öø-ÿ\'\-]+\s+[A-Z]{1,4},'
    r'|\[\d+\]'
    r'|\d+\.\s+[A-Z]'
    r'|[A-Z][a-zA-Zà-öø-ÿ\'\-]+\s+\('
    r'|[A-Z]\.?\s*,?\s*\('
    r'|[A-Z]\.?\s*,'
    r'|\(\d{4}\)'
    r'|(?:[A-Z][a-zA-Zà-öø-ÿ\'\-]+(?:\s+(?:of|for|the|and|on|in|&))?\s+)+[A-Z][a-zA-Zà-öø-ÿ\'\-]+\.?\s*\(\d{4}'
    r')'
)
text = "Children's Health Ireland. (2021)"
print("Match result:", pattern.match(text))
