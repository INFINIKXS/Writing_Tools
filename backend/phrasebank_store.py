"""
Store for the Academic Phrase Bank — Supabase (PostgreSQL) backend.

All data lives in the Supabase 'phrases' and 'phrase_usage' tables.
No local SQLite file.  Function signatures are kept stable so that
phrasebank.py and phrasebank_routes/ can call them without changes.
"""
from collections import Counter
from typing import Optional

from db.supabase_client import supabase

# ──────────────────────────────────────────────────────────────────────
# Supported rhetorical phrase categories
# ──────────────────────────────────────────────────────────────────────
PHRASE_CATEGORIES = [
    "Stating the Aim",
    "Reviewing the Literature",
    "Identifying a Gap",
    "Defining Terms",
    "Describing Methodology",
    "Presenting Results",
    "Discussing Implications",
    "Hedging & Qualifying",
    "Comparing & Contrasting",
    "Concluding",
    "General Transitions",
]


# ──────────────────────────────────────────────────────────────────────
# Read helpers
# ──────────────────────────────────────────────────────────────────────

def get_categories() -> list[dict]:
    """Return all categories with their phrase counts.
    
    Returns: [{"category": "Stating the Aim", "count": 12}, ...]
    """
    result = supabase.table("phrases").select("category").execute()
    counts = Counter(row["category"] for row in result.data)
    return sorted(
        [{"category": cat, "count": cnt} for cat, cnt in counts.items()],
        key=lambda x: PHRASE_CATEGORIES.index(x["category"])
        if x["category"] in PHRASE_CATEGORIES else 999,
    )


def get_phrases_by_category(
    category: str,
    subcategory: Optional[str] = None,
) -> list[dict]:
    """Return all phrases in a category, optionally filtered by subcategory."""
    query = (
        supabase.table("phrases")
        .select("id, template, category, subcategory, example, formality_level")
        .eq("category", category)
        .order("id")
    )
    if subcategory:
        query = query.eq("subcategory", subcategory)
    result = query.execute()
    return result.data


def search_phrases(query: str, limit: int = 20) -> list[dict]:
    """Full-text search across template + example using Postgres tsvector.
    
    Converts the user query into a tsquery with OR between words so
    partial matches still surface results.
    """
    # Convert "study aims examine" -> "study | aims | examine"
    words = query.strip().split()
    if not words:
        return []
    ts_query = " | ".join(words)

    result = (
        supabase.table("phrases")
        .select("id, template, category, subcategory, example, formality_level")
        .text_search("search_vector", ts_query, config="english")
        .limit(limit)
        .execute()
    )
    return result.data


def get_phrase(phrase_id: int) -> Optional[dict]:
    """Get a single phrase by ID."""
    result = (
        supabase.table("phrases")
        .select("id, template, category, subcategory, example, formality_level")
        .eq("id", phrase_id)
        .maybe_single()
        .execute()
    )
    return result.data


def get_random_templates(category: str, count: int = 5) -> list[str]:
    """Backward-compatible helper used by phrasebank.py LLM prompts.
    
    Returns a list of template strings (not full phrase dicts).
    Uses Postgres random ordering — good enough for prompt variety.
    """
    # Supabase doesn't have a native .order("RANDOM()") helper,
    # so we fetch a larger pool and sample in Python.
    result = (
        supabase.table("phrases")
        .select("template")
        .eq("category", category)
        .limit(50)
        .execute()
    )
    templates = [row["template"] for row in result.data]

    import random
    random.shuffle(templates)
    selected = templates[:count]

    # If not enough in the requested category, backfill from others
    if len(selected) < count:
        needed = count - len(selected)
        extra = (
            supabase.table("phrases")
            .select("template")
            .neq("category", category)
            .limit(50)
            .execute()
        )
        extras = [row["template"] for row in extra.data]
        random.shuffle(extras)
        selected += extras[:needed]

    return selected


# ──────────────────────────────────────────────────────────────────────
# Write helpers
# ──────────────────────────────────────────────────────────────────────

def record_usage(phrase_id: int) -> None:
    """Log that a phrase was used (for analytics)."""
    supabase.table("phrase_usage").insert({"phrase_id": phrase_id}).execute()


def seed_phrases(phrases: list[dict]) -> list[dict]:
    """Bulk-insert phrases into Supabase.  Used by the seed script.
    
    Each dict should have: template, category, and optionally
    subcategory, example, formality_level.
    """
    # Insert in batches of 100 to avoid payload limits
    BATCH = 100
    all_inserted = []
    for i in range(0, len(phrases), BATCH):
        batch = phrases[i : i + BATCH]
        result = supabase.table("phrases").insert(batch).execute()
        all_inserted.extend(result.data)
    return all_inserted


# ──────────────────────────────────────────────────────────────────────
# Stats
# ──────────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    """Return aggregate stats about the phrase bank."""
    result = supabase.table("phrases").select("category").execute()
    counts = Counter(row["category"] for row in result.data)
    return {
        "total_phrases": len(result.data),
        "by_category": dict(counts),
    }
