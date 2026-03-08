import json

async def process_phrasebank_rewrite(sentence: str) -> dict:
    """
    Sends a dense sentence to the LLM to rewrite using Academic Phrasebank principles.
    Focuses on:
    1. Defining Terms templates
    2. Reducing nominalisations (complex noun stacks)
    """
    from main import get_client, gemini_request_with_retry
    import phrasebank_store
    
    # Try to get real examples from the uploaded PDFs
    # We pull from standard descriptive categories for general rewriting
    db_templates = phrasebank_store.get_random_templates("Defining Terms", count=3)
    db_templates += phrasebank_store.get_random_templates("General Transition", count=2)
    
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
