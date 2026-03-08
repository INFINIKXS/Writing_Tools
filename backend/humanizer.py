"""
AI-to-Human Retrieval-Augmented Style Transfer (RAST) Pipeline.

3-step process:
1. Extract   — LLM compresses the AI sentence into semantic facts + core_meaning summary
2. Retrieve  — Pull 8 real human sentences from the DB as a style palette
3. Rewrite   — LLM imitates the style of those examples while preserving all meaning
               guarded by an Input Containment Check (difflib similarity against core_meaning)
"""
import json
import difflib


# ── Step 1: Semantic Extraction ───────────────────────────────────────────────

async def cognitive_deconstruction(sentence: str) -> dict:
    """
    Extract:
    - rhetorical intent
    - key variable facts  
    - core_meaning: a plain-English compression of what the sentence says
      (this becomes the Containment Check oracle for Step 3)
    """
    from main import get_client, gemini_request_with_retry

    prompt = f"""You are a semantic analyst. Read this sentence and return a JSON with three things:

1. **intent** — pick exactly ONE rhetorical category:
   Speech_Summary | Cause_and_Effect | Concept_Definition | Comparison |
   Evidence_Claim | Process_Description | Counter_Argument | General_Statement

2. **core_meaning** — write ONE or TWO plain sentences that capture every fact
   in the source using simple words. This is the meaning oracle.
   Do NOT rephrase or expand — only state what the sentence actually says.

3. **variables** — extract the key facts as a JSON dict using these names:
   [ACTOR] [CONCEPT] [ARGUMENT] [CAUSE] [EFFECT] [CONTEXT] [EVIDENCE] [DEFINITION]
   [COMPARISON_A] [COMPARISON_B]
   Use only what is actually present. Do not force-fit.

SENTENCE: "{sentence}"

Respond with ONLY this JSON, nothing else:
{{
    "intent": "Concept_Definition",
    "core_meaning": "plain English summary of what the sentence says",
    "variables": {{
        "[CONCEPT]": "value from sentence",
        "[DEFINITION]": "value from sentence"
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

        from humanizer_store import INTENT_CATEGORIES
        intent = data.get("intent", "General_Statement")
        if intent not in INTENT_CATEGORIES:
            intent = "General_Statement"

        return {
            "intent": intent,
            "core_meaning": data.get("core_meaning", sentence),
            "variables": data.get("variables", {}),
        }
    except Exception as e:
        print(f"[Cognitive Deconstruction] LLM extraction failed: {e}")
        return {
            "intent": "General_Statement",
            "core_meaning": sentence,
            "variables": {},
        }


# ── Step 3a: Style-Guided Rewrite ─────────────────────────────────────────────

async def style_guided_rewrite(
    source_sentence: str,
    core_meaning: str,
    style_examples: list[str],
) -> list[str]:
    """
    Single LLM call that produces 3 alternative rewrites of the source sentence.

    The LLM is given real human sentences from the DB as a style palette.
    It must borrow their rhythm, connectors, and vocabulary patterns
    while preserving EVERY fact in core_meaning.
    """
    from main import get_client, gemini_request_with_retry

    examples_block = "\n".join(f"  {i+1}. {ex}" for i, ex in enumerate(style_examples))

    prompt = f"""You are a writing style transfer expert. Your task is to rewrite a sentence so it sounds like it was written by a human, not an AI.

SOURCE SENTENCE (preserve all its meaning):
"{source_sentence}"

MEANING TO PRESERVE (this is what the output MUST communicate — no more, no less):
"{core_meaning}"

HUMAN WRITING STYLE PALETTE (study these real sentences — borrow their:
 - sentence-opening patterns
 - connectors and transition words
 - clause structures and punctuation rhythms
 - vocabulary register
 Do NOT copy them verbatim. Use them as inspiration for structure only):
{examples_block}

YOUR TASK:
Write EXACTLY 3 alternative rewrites of the source sentence.
Rules:
- Every rewrite must preserve ALL the meaning stated in the MEANING section above
- DO NOT add any fact, claim, or idea not present in the source sentence
- DO NOT use the same sentence structure as the source sentence
- Vary the 3 rewrites from each other (different openings, different structures)
- Write naturally, like a human — contractions, varied clause length, real connectors

Return ONLY this JSON, nothing else:
{{
    "rewrites": [
        "First rewrite here.",
        "Second rewrite here.",
        "Third rewrite here."
    ]
}}"""

    try:
        from google.genai import types as genai_types
        model_name = 'gemini-3.1-flash-lite-preview'
        client = get_client(model=model_name)
        thinking_config = genai_types.GenerateContentConfig(
            thinking_config=genai_types.ThinkingConfig(thinking_level="high")
        )
        response = await gemini_request_with_retry(
            client, prompt, model=model_name, config=thinking_config
        )
        raw = response.text.strip()

        if raw.startswith('```json'):
            raw = raw[7:].strip()
        if raw.startswith('```'):
            raw = raw[3:].strip()
        if raw.endswith('```'):
            raw = raw[:-3].strip()

        data = json.loads(raw)
        rewrites = data.get("rewrites", [])

        # Ensure we always have 3 (pad with source if LLM returned fewer)
        while len(rewrites) < 3:
            rewrites.append(source_sentence)

        return rewrites[:3]

    except Exception as e:
        print(f"[Style-Guided Rewrite] LLM failed: {e}")
        return [source_sentence, source_sentence, source_sentence]


# ── Step 3b: Input Containment Check (anti-hallucination guard) ───────────────

def containment_check(rewrite: str, core_meaning: str, threshold: float = 0.45) -> dict:
    """
    Verify the rewrite preserves the core meaning using difflib.SequenceMatcher.
    
    Inspired by Tip 2 from the anti-hallucination playbook:
    The core_meaning is the source-of-truth oracle.
    If the rewrite's similarity drops below the threshold, flag it.
    
    Returns: { "passed": bool, "score": float, "warning": str|None }
    """
    # Normalise both texts before comparison
    def normalise(text: str) -> str:
        import re
        return re.sub(r'[^\w\s]', '', text.lower())

    score = difflib.SequenceMatcher(
        None,
        normalise(core_meaning),
        normalise(rewrite),
    ).ratio()

    passed = score >= threshold
    return {
        "passed": passed,
        "score": round(score, 3),
        "warning": None if passed else f"Low meaning similarity ({score:.0%}) — may have drifted from source.",
    }


# ── Main Pipeline ─────────────────────────────────────────────────────────────

async def humanize_sentence(sentence: str) -> dict:
    """
    RAST pipeline: Extract → Retrieve style examples → Style-guided rewrite → Containment check.
    Returns 3 alternative rewrites, each with a containment check result.
    """
    from humanizer_store import get_style_examples

    # ── Step 1: Semantic Extraction ──
    extraction = await cognitive_deconstruction(sentence)
    intent = extraction["intent"]
    core_meaning = extraction["core_meaning"]
    variables = extraction["variables"]

    # ── Step 2: Retrieve style examples from DB ──
    style_examples = get_style_examples(intent, count=8)

    if not style_examples:
        return {
            "original": sentence,
            "humanized": sentence,
            "skipped": True,
            "reason": "No human writing examples in the Skeleton Bank. Upload PDFs first.",
            "steps": {
                "extract": {"intent": intent, "core_meaning": core_meaning, "variables": variables},
            },
        }

    # ── Step 3a: Style-guided rewrite ──
    rewrites = await style_guided_rewrite(sentence, core_meaning, style_examples)

    # ── Step 3b: Containment check on each rewrite ──
    checked_rewrites = []
    for rw in rewrites:
        check = containment_check(rw, core_meaning)
        checked_rewrites.append({
            "text": rw,
            "containment_passed": check["passed"],
            "containment_score": check["score"],
            "warning": check["warning"],
        })

    # Primary output = first rewrite (best per LLM ordering)
    best = checked_rewrites[0]["text"]

    return {
        "original": sentence,
        "humanized": best,
        "skipped": False,
        "steps": {
            "extract": {
                "intent": intent,
                "core_meaning": core_meaning,
                "variables": variables,
            },
            "retrieve": {
                "example_count": len(style_examples),
                "examples": style_examples,
            },
            "rewrite": {
                "rewrites": checked_rewrites,
            },
        },
    }


async def humanize_text(text: str) -> dict:
    """
    Split text into sentences and humanize each one.
    Returns the combined humanized text and per-sentence details.
    """
    import spacy

    try:
        nlp = spacy.load("en_core_web_sm", disable=["ner", "parser"])
        nlp.add_pipe("sentencizer")
    except Exception:
        nlp = spacy.blank("en")
        nlp.add_pipe("sentencizer")

    doc = nlp(text)
    sentences = [s.text.strip() for s in doc.sents if s.text.strip()]

    results = []
    for sent in sentences:
        result = await humanize_sentence(sent)
        results.append(result)

    humanized_parts = [r["humanized"] for r in results]
    humanized_text = " ".join(humanized_parts)

    humanized_count = sum(1 for r in results if not r.get("skipped"))
    skipped_count = sum(1 for r in results if r.get("skipped"))

    return {
        "humanized_text": humanized_text,
        "sentences": results,
        "stats": {
            "total": len(results),
            "humanized_count": humanized_count,
            "skipped_count": skipped_count,
        },
    }
