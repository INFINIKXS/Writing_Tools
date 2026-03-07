"""
AI-to-Human Style Transfer Pipeline.

4-step process:
1. Deconstruct — extract entities and mask AI sentence
2. Retrieve   — find closest human skeleton from the vector DB
3. Reconstruct — slot AI variables into human skeleton
4. Polish     — LLM grammar fix via Gemini
"""
import re
import asyncio


def _get_nlp():
    """Get shared spaCy model from humanizer_store."""
    from humanizer_store import _get_nlp as get_nlp
    return get_nlp()


def deconstruct_sentence(sentence: str) -> dict:
    """
    Step 1: Parse an AI sentence, extract key entities, and create a masked skeleton.
    
    Returns {
        "original": str,
        "masked": str,
        "variables": {"SUBJECT": "photosynthesis", "ACTOR": "green plants", ...}
    }
    """
    from humanizer_store import mask_sentence
    masked, variables = mask_sentence(sentence)
    return {
        "original": sentence,
        "masked": masked,
        "variables": variables,
    }


def retrieve_human_skeleton(masked_ai_sentence: str, top_k: int = 5) -> list[dict]:
    """
    Step 2: Search the human sentence database for structurally similar skeletons.
    
    Returns list of candidates with similarity scores.
    """
    from humanizer_store import search_similar
    candidates = search_similar(masked_ai_sentence, top_k=top_k)
    return candidates


def reconstruct_sentence(human_skeleton: str, variables: dict) -> str:
    """
    Step 3: Slot the AI's extracted variables into the human skeleton.
    
    Strategy:
    - The human skeleton has its OWN placeholders (from when it was masked).
    - We need to map AI variables to human placeholders by role.
    - E.g., AI's [SUBJECT] -> Human's [SUBJECT], AI's [INPUT] -> Human's [INPUT]
    
    If the human skeleton has placeholders that don't exist in AI variables,
    we try to map by position/role similarity. If a placeholder can't be filled,
    we leave it as-is (the LLM polish step will handle it).
    """
    result = human_skeleton
    
    # First pass: direct key matching (SUBJECT -> SUBJECT, etc.)
    for key, value in variables.items():
        placeholder = f"[{key}]"
        if placeholder in result:
            result = result.replace(placeholder, value, 1)
    
    # Second pass: try to fill remaining placeholders by role mapping
    # Extract unfilled placeholders from result
    unfilled = re.findall(r'\[([A-Z_0-9]+)\]', result)
    # Get unused variables (ones that weren't direct-matched)
    used_keys = set()
    for key in variables:
        if f"[{key}]" not in human_skeleton:
            continue
        used_keys.add(key)
    unused_vars = {k: v for k, v in variables.items() if k not in used_keys}
    
    # Role similarity mapping
    role_groups = {
        "subject": ["SUBJECT", "ENTITY", "ATTRIBUTE"],
        "actor": ["ACTOR", "SUBJECT"],
        "object": ["OBJECT", "ENTITY", "OUTPUT", "ATTRIBUTE"],
        "input": ["INPUT", "OBJECT", "ENTITY"],
        "output": ["OUTPUT", "OBJECT", "ENTITY"],
        "entity": ["ENTITY", "SUBJECT", "OBJECT", "ATTRIBUTE"],
        "attribute": ["ATTRIBUTE", "ENTITY", "OBJECT"],
    }
    
    for placeholder_key in unfilled:
        base_role = placeholder_key.rstrip("_0123456789").lower()
        candidates = role_groups.get(base_role, [])
        
        matched = False
        for candidate_role in candidates:
            # Look for unused variable with this role
            for var_key in list(unused_vars.keys()):
                var_base = var_key.rstrip("_0123456789")
                if var_base == candidate_role:
                    result = result.replace(f"[{placeholder_key}]", unused_vars[var_key], 1)
                    del unused_vars[var_key]
                    matched = True
                    break
            if matched:
                break
        
        # If still not matched, try any remaining unused variable
        if not matched and unused_vars:
            first_key = next(iter(unused_vars))
            result = result.replace(f"[{placeholder_key}]", unused_vars[first_key], 1)
            del unused_vars[first_key]
    
    return result


async def polish_sentence(sentence: str) -> str:
    """
    Step 4: Use Gemini to fix grammatical friction without changing vocabulary or structure.
    """
    # Import from main to reuse the existing Gemini infrastructure
    from main import get_client, gemini_request_with_retry
    
    prompt = f"""Fix any grammatical friction in this sentence without changing the vocabulary or structure. 
Only fix issues like subject-verb agreement, article usage (a/an), pronoun case, and punctuation.
Do NOT rewrite, rephrase, or add any new words. Do NOT change the sentence structure.
If the sentence is already grammatically correct, return it unchanged.

Sentence: "{sentence}"

Return ONLY the corrected sentence, nothing else. No quotes, no explanation."""

    try:
        model_name = 'gemini-2.0-flash'
        client = get_client(model=model_name)
        response = await gemini_request_with_retry(client, prompt, model=model_name)
        result = response.text.strip()
        # Remove quotes if the model wrapped it
        if result.startswith('"') and result.endswith('"'):
            result = result[1:-1]
        if result.startswith("'") and result.endswith("'"):
            result = result[1:-1]
        return result
    except Exception as e:
        print(f"[Humanizer Polish] LLM polish failed: {e}, returning as-is")
        return sentence


async def humanize_sentence(sentence: str) -> dict:
    """
    Run the full 4-step pipeline on a single sentence.
    
    Returns {
        "original": str,
        "humanized": str,
        "steps": {
            "deconstruct": {"masked": str, "variables": dict},
            "retrieve": {"human_skeleton": str, "similarity": float, "original_human": str},
            "reconstruct": {"raw_output": str},
            "polish": {"final_output": str}
        }
    }
    """
    # Step 1: Deconstruct
    decon = deconstruct_sentence(sentence)
    
    if not decon["variables"]:
        # No entities found — can't do style transfer, return original
        return {
            "original": sentence,
            "humanized": sentence,
            "skipped": True,
            "reason": "No extractable entities found in sentence",
            "steps": {},
        }
    
    # Step 2: Retrieve
    candidates = retrieve_human_skeleton(decon["masked"], top_k=5)
    
    if not candidates:
        return {
            "original": sentence,
            "humanized": sentence,
            "skipped": True,
            "reason": "No human sentences in database. Upload PDFs first.",
            "steps": {"deconstruct": {"masked": decon["masked"], "variables": decon["variables"]}},
        }
    
    # Pick the best candidate (highest similarity)
    best = candidates[0]
    
    # Step 3: Reconstruct
    reconstructed = reconstruct_sentence(best["masked_text"], decon["variables"])
    
    # Step 4: Polish
    polished = await polish_sentence(reconstructed)
    
    return {
        "original": sentence,
        "humanized": polished,
        "skipped": False,
        "steps": {
            "deconstruct": {
                "masked": decon["masked"],
                "variables": decon["variables"],
            },
            "retrieve": {
                "human_skeleton": best["masked_text"],
                "original_human": best["sentence_text"],
                "similarity": round(best["similarity"], 4),
            },
            "reconstruct": {
                "raw_output": reconstructed,
            },
            "polish": {
                "final_output": polished,
            },
        },
    }


async def humanize_text(text: str) -> dict:
    """
    Main entry point: humanize an entire block of AI-generated text.
    Splits into sentences, runs each through the pipeline.
    
    Returns {
        "original_text": str,
        "humanized_text": str,
        "sentences": [
            {
                "original": str,
                "humanized": str,
                "skipped": bool,
                "steps": {...}
            },
            ...
        ],
        "stats": {
            "total_sentences": int,
            "humanized_count": int,
            "skipped_count": int,
        }
    }
    """
    nlp = _get_nlp()
    doc = nlp(text)
    
    sentences = []
    for sent in doc.sents:
        s = sent.text.strip()
        if len(s.split()) >= 4:  # Skip very short fragments
            sentences.append(s)
    
    if not sentences:
        return {
            "original_text": text,
            "humanized_text": text,
            "sentences": [],
            "stats": {"total_sentences": 0, "humanized_count": 0, "skipped_count": 0},
        }
    
    # Process each sentence through the pipeline
    results = []
    for sent in sentences:
        result = await humanize_sentence(sent)
        results.append(result)
    
    # Reconstruct the full humanized text
    humanized_parts = [r["humanized"] for r in results]
    humanized_text = " ".join(humanized_parts)
    
    humanized_count = sum(1 for r in results if not r.get("skipped", False))
    skipped_count = sum(1 for r in results if r.get("skipped", False))
    
    return {
        "original_text": text,
        "humanized_text": humanized_text,
        "sentences": results,
        "stats": {
            "total_sentences": len(results),
            "humanized_count": humanized_count,
            "skipped_count": skipped_count,
        },
    }
