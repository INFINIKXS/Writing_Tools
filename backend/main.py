"""
Writing Tools API — Slim entry point.

All domain logic has been refactored into subpackages:
    core/     — config, Gemini client, retry logic
    utils/    — text extraction, text utilities
    citations/ — detection, deduplication, extraction, ordering, verification, formatting, routes
    references/ — metadata extraction, parser, routes
    search/   — full-text search routes (wraps search_store)
    humanizer_routes/ — cognitive synthesizer routes (wraps humanizer / humanizer_store)
    phrasebank_routes/ — academic phrasebank routes (wraps phrasebank / phrasebank_store)
    converter/ — document conversion routes (PDF↔Word, OCR, merge, compress, etc.)

This file:
  1. Creates the FastAPI app with CORS middleware
  2. Includes all domain routers
  3. Re-exports key utilities for backward compatibility with existing modules
     (humanizer.py, phrasebank.py, phrasebank_store.py, humanizer_store.py,
      test_vancouver_formatter.py) that do `from main import ...`
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ─── App creation ─────────────────────────────────────────────────────────
app = FastAPI(title="Writing Tools API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Include domain routers ──────────────────────────────────────────────
from citations.routes import router as citations_router
from references.routes import router as references_router
from search import router as search_router
from humanizer_routes import router as humanizer_router
from phrasebank_routes import router as phrasebank_router
from converter import router as converter_router

app.include_router(citations_router)
app.include_router(references_router)
app.include_router(search_router)
app.include_router(humanizer_router)
app.include_router(phrasebank_router)
app.include_router(converter_router)
from pdf_routes.editor import router as pdf_editor_router
app.include_router(pdf_editor_router, prefix="/api/pdf")


# ─── Backward-compatibility re-exports ───────────────────────────────────
# These allow existing modules (humanizer.py, phrasebank.py, etc.) that do
#   `from main import get_client, gemini_request_with_retry`
# to keep working without code changes.
from core.gemini import get_client, gemini_request_with_retry          # noqa: F401
from citations.formatting import format_reference                       # noqa: F401


# ─── Dev server entry point ──────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
