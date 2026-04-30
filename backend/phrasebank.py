"""
LLM-powered phrase operations for the Academic Phrase Bank.

Three core functions:
  - process_phrasebank_rewrite()  — rewrite dense sentences (kept from v1)
  - process_phrasebank_suggest()  — rank phrase candidates by relevance to user text
  - process_phrasebank_fit()      — adapt a phrase template to the user's content
"""
import json


# ──────────────────────────────────────────────────────────────────────
# 1.  Rewrite  (kept from v1, updated to use new store)
# ──────────────────────────────────────────────────────────────────────

async def process_phrasebank_rewrite(sentence: str) -> dict:
    """
    Sends a dense sentence to the LLM to rewrite using Academic Phrasebank principles.
    Focuses on:
    1. Defining Terms templates
    2. Reducing nominalisations (complex noun stacks)
    """
    from main import get_client, gemini_request_with_retry
    import phrasebank_store

    # Pull real examples from the curated phrase bank
    db_templates = phrasebank_store.get_random_templates("Defining Terms", count=3)
    db_templates += phrasebank_store.get_random_templates("General Transitions", count=2)

    if db_templates:
        examples_block = "REAL EXAMPLES FROM YOUR PHRASEBANK:\n" + "\n".join(f"- {t}" for t in db_templates)
    else:
        examples_block = "Use standard Academic Phrasebank templates for defining terms and transitions."

    prompt = f"""You are an expert academic writing tutor. Your task is to rewrite a dense, overly complex sentence using the principles of the Academic Phrasebank.

Specifically, you need to:
1. Identify the core concepts and any nominalisations (verbs turned into noun stacks, e.g., "administration", "delivery", "predictability").
2. Select 1 or 2 templates from the provided Phrasebank examples (or use standard Academic Phrasebank templates if none are provided) that best fit the core concept. 
3. Break down complex noun stacks to create clearer, more active sentences.
4. IMPORTANT: Your rewritten options MUST visibly and strictly use the templates you list in `templates_applied`. Do not list a template if you do not use it in your options.

{examples_block}

SOURCE SENTENCE:
"{sentence}"

Provide a structural analysis and two rewritten options in JSON format.

Respond with ONLY this JSON, nothing else:
{{
    "analysis": {{
        "core_concept": "The main concept being discussed",
        "nominalisations_found": ["list", "of", "noun", "stacks"]
    }},
    "templates_applied": [
        "The exact template you used in the options below, e.g. 'The term [X] refers to...'"
    ],
    "drafts": [
        "First working draft mapped exactly to the first template.",
        "Second working draft mapped exactly to the second template (if applicable)."
    ],
    "options": [
        {{
            "name": "Option A (Direct & Active)",
            "text": "Your first rewritten sentence that CLEARLY incorporates the template."
        }},
        {{
            "name": "Option B (Two-sentence breakdown for clarity)",
            "text": "Your second option that CLEARLY incorporates the template."
        }}
    ],
    "follow_up": "A prompt asking the user if they'd like to apply these templates to surrounding sentences to ensure paragraph flow."
}}"""

    try:
        model_name = 'gemini-3.1-flash-lite-preview'
        client = get_client(model=model_name)
        response = await gemini_request_with_retry(client, prompt, model=model_name)
        raw = response.text.strip()

        if raw.startswith('```json'):
            raw = raw[7:].strip()
        if raw.startswith('```'):
            raw = raw[3:].strip()
        if raw.endswith('```'):
            raw = raw[:-3].strip()

        data = json.loads(raw)
        return data
    except Exception as e:
        print(f"[Phrasebank Rewrite] LLM failed: {e}")
        return {"error": str(e)}


# ──────────────────────────────────────────────────────────────────────
# 2.  Suggest  (NEW — ranks DB phrase candidates for relevance)
# ──────────────────────────────────────────────────────────────────────

async def process_phrasebank_suggest(user_text: str, candidate_phrases: list[dict]) -> list[dict]:
    """
    Takes user text + a list of phrase candidates (from Supabase search)
    and asks the LLM to rank them by relevance.

    Returns the top candidates with a 'relevance_reason' added to each.
    If the LLM fails, returns candidates as-is (graceful degradation).
    """
    if not candidate_phrases:
        return []

    from main import get_client, gemini_request_with_retry

    # Build a numbered list of candidates for the prompt
    numbered = "\n".join(
        f"{i+1}. [{p['category']}] {p['template']}"
        for i, p in enumerate(candidate_phrases)
    )

    prompt = f"""You are an academic writing assistant. A user has written this text:

"{user_text}"

Below are phrase templates from an Academic Phrasebank that might be relevant.
Rank the TOP 8 most relevant phrases for the user's text.

CANDIDATE PHRASES:
{numbered}

Respond with ONLY a JSON array. Each element must have:
- "index": the phrase number (1-based) from the list above
- "relevance_reason": a brief (1 sentence) reason why this phrase fits the user's text

Order from most to least relevant. Include at most 8 phrases.
Output ONLY the JSON array, nothing else."""

    try:
        model_name = 'gemini-3.1-flash-lite-preview'
        client = get_client(model=model_name)
        response = await gemini_request_with_retry(client, prompt, model=model_name)
        raw = response.text.strip()

        if raw.startswith('```json'):
            raw = raw[7:].strip()
        if raw.startswith('```'):
            raw = raw[3:].strip()
        if raw.endswith('```'):
            raw = raw[:-3].strip()

        rankings = json.loads(raw)

        # Map back to full phrase objects
        result = []
        for item in rankings:
            idx = item.get("index", 0) - 1
            if 0 <= idx < len(candidate_phrases):
                phrase = dict(candidate_phrases[idx])
                phrase["relevance_reason"] = item.get("relevance_reason", "")
                result.append(phrase)

        return result[:8]

    except Exception as e:
        print(f"[Phrasebank Suggest] LLM ranking failed: {e}")
        # Graceful fallback — return candidates unranked
        return candidate_phrases[:8]


# ──────────────────────────────────────────────────────────────────────
# 3.  Fit  (NEW — adapts a phrase template to user's content)
# ──────────────────────────────────────────────────────────────────────

async def process_phrasebank_fit(template: str, example: str, user_text: str) -> dict:
    """
    Takes a phrase template (e.g. "This study aims to [X] by [Y]")
    and the user's sentence, then produces a fitted version that
    slots their content into the template structure.
    """
    from main import get_client, gemini_request_with_retry

    example_block = f'\nEXAMPLE of this template in use:\n"{example}"' if example else ""

    prompt = f"""You are an expert academic writing tutor. Your task is to adapt a user's sentence to fit a specific academic phrase template.

TEMPLATE:
"{template}"
{example_block}

USER'S ORIGINAL SENTENCE:
"{user_text}"

Instructions:
1. Extract the key content/arguments from the user's sentence.
2. Slot that content into the template structure, replacing [X], [Y], [Z] placeholders.
3. Ensure the result is grammatically correct, academically appropriate, and faithful to the user's meaning.
4. Provide TWO fitted versions: one close to the template, one slightly more flexible.

Respond with ONLY this JSON:
{{
    "template_used": "{template}",
    "fitted_versions": [
        {{
            "name": "Close fit",
            "text": "The sentence rewritten to closely follow the template structure."
        }},
        {{
            "name": "Flexible fit",
            "text": "A slightly looser adaptation that prioritises natural flow."
        }}
    ],
    "content_extracted": {{
        "X": "What was mapped to [X]",
        "Y": "What was mapped to [Y] (if applicable)"
    }}
}}"""

    try:
        model_name = 'gemini-3.1-flash-lite-preview'
        client = get_client(model=model_name)
        response = await gemini_request_with_retry(client, prompt, model=model_name)
        raw = response.text.strip()

        if raw.startswith('```json'):
            raw = raw[7:].strip()
        if raw.startswith('```'):
            raw = raw[3:].strip()
        if raw.endswith('```'):
            raw = raw[:-3].strip()

        data = json.loads(raw)
        return data
    except Exception as e:
        print(f"[Phrasebank Fit] LLM failed: {e}")
        return {"error": str(e)}
