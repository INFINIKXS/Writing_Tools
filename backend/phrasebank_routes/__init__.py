"""
Phrasebank API routes — Supabase-backed.

All data access goes through phrasebank_store (which talks to Supabase).
LLM operations go through phrasebank (suggest, fit, rewrite).
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

import phrasebank_store

router = APIRouter()


# ── Request models ────────────────────────────────────────────────────

class RewriteRequest(BaseModel):
    text: str

class SuggestRequest(BaseModel):
    text: str

class FitRequest(BaseModel):
    phrase_id: int
    user_text: str

class SeedRequest(BaseModel):
    phrases: list[dict]


# ── Category & Browse endpoints ───────────────────────────────────────

@router.get("/api/phrasebank/categories")
async def api_phrasebank_categories():
    """Return all categories with their phrase counts."""
    categories = phrasebank_store.get_categories()
    return {"categories": categories}


@router.get("/api/phrasebank/by-category")
async def api_phrasebank_by_category(
    category: str = Query(..., description="Category name"),
    subcategory: Optional[str] = Query(None, description="Optional subcategory filter"),
):
    """Return all phrases in a category."""
    phrases = phrasebank_store.get_phrases_by_category(category, subcategory)
    return {"phrases": phrases, "count": len(phrases)}


# ── Search endpoint ───────────────────────────────────────────────────

@router.get("/api/phrasebank/search")
async def api_phrasebank_search(
    q: str = Query(..., min_length=1, description="Search query"),
):
    """Full-text search across templates and examples (Postgres tsvector)."""
    phrases = phrasebank_store.search_phrases(q)
    return {"phrases": phrases, "count": len(phrases)}


# ── Suggest endpoint (LLM-ranked) ────────────────────────────────────

@router.post("/api/phrasebank/suggest")
async def api_phrasebank_suggest(req: SuggestRequest):
    """
    Takes user text → does a broad full-text search in Supabase →
    passes candidates to the LLM for relevance ranking →
    returns top 8 phrases.
    """
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")

    # Step 1: Get broad candidates from Supabase full-text search
    candidates = phrasebank_store.search_phrases(req.text, limit=20)

    # If full-text search returns too few, supplement with random phrases
    if len(candidates) < 5:
        all_cats = phrasebank_store.get_categories()
        for cat_info in all_cats[:3]:
            extras = phrasebank_store.get_phrases_by_category(cat_info["category"])
            for p in extras:
                if p not in candidates:
                    candidates.append(p)
                if len(candidates) >= 15:
                    break
            if len(candidates) >= 15:
                break

    # Step 2: LLM ranks the candidates by relevance
    from phrasebank import process_phrasebank_suggest
    ranked = await process_phrasebank_suggest(req.text, candidates)
    return {"phrases": ranked, "count": len(ranked)}


# ── Fit endpoint (LLM-adapted) ───────────────────────────────────────

@router.post("/api/phrasebank/fit")
async def api_phrasebank_fit(req: FitRequest):
    """
    Takes a phrase ID + user text → fetches the phrase template →
    LLM adapts the template to the user's content.
    """
    if not req.user_text.strip():
        raise HTTPException(status_code=400, detail="User text is required")

    # Fetch the phrase
    phrase = phrasebank_store.get_phrase(req.phrase_id)
    if not phrase:
        raise HTTPException(status_code=404, detail="Phrase not found")

    # Record usage
    phrasebank_store.record_usage(req.phrase_id)

    # LLM fit
    from phrasebank import process_phrasebank_fit
    result = await process_phrasebank_fit(
        template=phrase["template"],
        example=phrase.get("example", ""),
        user_text=req.user_text,
    )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return result


# ── Rewrite endpoint (kept from v1) ──────────────────────────────────

@router.post("/api/phrasebank/rewrite")
async def api_phrasebank_rewrite(req: RewriteRequest):
    """Rewrite a sentence using Academic Phrasebank principles."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")

    from phrasebank import process_phrasebank_rewrite
    result = await process_phrasebank_rewrite(req.text)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return result


# ── Stats endpoint ────────────────────────────────────────────────────

@router.get("/api/phrasebank/stats")
async def api_phrasebank_stats():
    """Get stats about the phrasebank database."""
    stats = phrasebank_store.get_stats()
    return stats


# ── Admin seed endpoint ──────────────────────────────────────────────

@router.post("/api/admin/phrasebank/seed")
async def api_phrasebank_seed(req: SeedRequest):
    """Bulk insert phrases (admin-only by convention)."""
    if not req.phrases:
        raise HTTPException(status_code=400, detail="No phrases provided")

    inserted = phrasebank_store.seed_phrases(req.phrases)
    return {"inserted": len(inserted)}
