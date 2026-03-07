# How to Beat Hallucination in AI-Powered Apps

## Tip 1: The "Expected Variable" Similarity Check (The CrossRef DOI Strategy)

When relying on Generative AI to extract structured identifiers (like a DOI) that you will use to perform strict database queries or third-party API lookups (like CrossRef), you run a critical risk: the AI might hallucinate a fake identifier that _coincidentally_ resolves to a real, but completely incorrect, record in that external database.

**The Solution:**
Force the AI to extract an additional, human-readable "verifying variable" (such as the actual "Title" of the document) from the exact same source text within the same prompt.

When you execute your database or API lookup using the AI's extracted identifier (e.g., the DOI), take the resulting payload from that third-party service and extract its corresponding title. Compare this third-party title against your "expected title" (the one the AI physically read from your source document) using a string similarity algorithm like Python's `difflib.SequenceMatcher`.

If the text overlap ratio drops below a reasonable threshold (e.g., 60%), you instantly know the AI hallucinated the identifier. Why? Because the title of the record pulled from the database does not resemble the title of the document you uploaded.

By catching this mismatch, you can immediately reject the hallucinated lookup payload and safely fall back to using the raw, verified text that the AI initially extracted natively from the document, ensuring your app never silently assigns incorrect data to a user's workflow.

## Tip 2: The "Input Containment Check" (The Reference Formatter Strategy)

When using Generative AI to extract structured fields (like authors, titles, or sources) from user-provided text that the user has already confirmed as correct, you face a subtle risk: the AI might rephrase, infer, or entirely fabricate field values that plausibly fit the context but were never actually present in the input.

**The Solution:**
Treat the user's original input text as the single source of truth. After the AI returns its extracted fields, validate every value against the original input using a containment check:

1. **Exact substring match** — is the AI's value found verbatim in the input? (fast path)
2. **Punctuation-stripped match** — strip punctuation from both and recheck (handles `Smith, J.` vs `Smith J`)
3. **Fuzzy similarity** — use `difflib.SequenceMatcher` with a threshold (e.g., ≥ 0.6) to catch minor reformatting differences
4. **Short value strictness** — for values ≤ 6 characters (like years), require exact presence in the input to prevent false positives

If any AI-extracted value fails all containment checks, it is provably hallucinated (it doesn't exist in the text the AI was reading) and should be rejected immediately. This approach requires no external API or database lookup — the input itself is the verification oracle.

This is particularly effective when the AI's job is purely to **identify and label** parts of existing text (e.g., "which part is the title?") rather than to generate new content.
