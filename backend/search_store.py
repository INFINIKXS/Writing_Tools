"""
SQLite FTS5 full-text search store for PDF documents.
Indexes extracted PDF text per-page for verbatim sentence search.
"""
import sqlite3
import os
import re
import uuid
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "search_index.db")


def _normalize(text: str) -> str:
    """Collapse all whitespace (newlines, tabs, multiple spaces) into single spaces."""
    return re.sub(r'\s+', ' ', text).strip()


def _get_conn() -> sqlite3.Connection:
    """Get a connection to the search index database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the FTS5 table and metadata table if they don't exist."""
    conn = _get_conn()
    try:
        # Metadata table for document info
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                doc_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                total_pages INTEGER NOT NULL,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # FTS5 virtual table for full-text search
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
                doc_id,
                page_num,
                content,
                tokenize='unicode61'
            )
        """)
        conn.commit()
    finally:
        conn.close()


def index_document(filename: str, pages_text: list[str]) -> str:
    """
    Index a document's pages into the FTS5 store.
    Stores each page AND overlapping regions between adjacent pages
    so queries spanning page boundaries can match.
    Returns the generated doc_id.
    """
    OVERLAP_CHARS = 500  # chars from end of page N + start of page N+1
    doc_id = str(uuid.uuid4())[:8]
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO documents (doc_id, filename, total_pages) VALUES (?, ?, ?)",
            (doc_id, filename, len(pages_text)),
        )
        for page_num, text in enumerate(pages_text, start=1):
            if text.strip():
                conn.execute(
                    "INSERT INTO pages_fts (doc_id, page_num, content) VALUES (?, ?, ?)",
                    (doc_id, str(page_num), text),
                )
        # Store overlapping regions between adjacent pages
        for i in range(len(pages_text) - 1):
            tail = pages_text[i][-OVERLAP_CHARS:] if len(pages_text[i]) > OVERLAP_CHARS else pages_text[i]
            head = pages_text[i + 1][:OVERLAP_CHARS] if len(pages_text[i + 1]) > OVERLAP_CHARS else pages_text[i + 1]
            overlap = tail + " " + head
            if overlap.strip():
                # Store as "page N-N+1" to indicate it spans pages
                conn.execute(
                    "INSERT INTO pages_fts (doc_id, page_num, content) VALUES (?, ?, ?)",
                    (doc_id, f"{i + 1}-{i + 2}", overlap),
                )
        conn.commit()
        return doc_id
    finally:
        conn.close()


def search(query: str, max_results: int = 50) -> list[dict]:
    """
    Search for a phrase across all indexed pages.
    Normalizes whitespace in both query and content so pasted text
    with different newlines/spaces still matches PDF-extracted text.
    Uses FTS5 phrase search first, then falls back to normalized substring match.
    Returns list of { doc_id, filename, page_num, snippet, match_context }.
    """
    conn = _get_conn()
    try:
        results = []

        # Normalize query: collapse all whitespace to single spaces
        query_clean = _normalize(query)
        if not query_clean:
            return []

        # Strategy 1: FTS5 phrase search (fast, handles tokenized matching)
        # FTS5 tokenizer already normalizes whitespace, so this handles most cases
        fts_query = '"' + query_clean.replace('"', '""') + '"'
        try:
            rows = conn.execute("""
                SELECT p.doc_id, p.page_num, p.content, d.filename,
                       rank
                FROM pages_fts p
                JOIN documents d ON p.doc_id = d.doc_id
                WHERE pages_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, max_results)).fetchall()

            for row in rows:
                snippet = _extract_context(row["content"], query_clean)
                page_display = row["page_num"]
                # If it's an overlap row like "3-4", show as "Pages 3-4"
                results.append({
                    "doc_id": row["doc_id"],
                    "filename": row["filename"],
                    "page_num": page_display,
                    "snippet": snippet["text"],
                    "match_start": snippet["match_start"],
                    "match_end": snippet["match_end"],
                    "match_type": "phrase",
                })
        except sqlite3.OperationalError:
            pass  # FTS5 query syntax error, fall through to substring

        # Strategy 2: Normalized substring fallback
        # Collapses whitespace in both query and content so different
        # newline/space patterns still match
        if not results:
            query_norm_lower = query_clean.lower()
            rows = conn.execute("""
                SELECT p.doc_id, p.page_num, p.content, d.filename
                FROM pages_fts p
                JOIN documents d ON p.doc_id = d.doc_id
            """).fetchall()

            for row in rows:
                content_normalized = _normalize(row["content"]).lower()
                if query_norm_lower in content_normalized:
                    snippet = _extract_context(row["content"], query_clean)
                    page_display = row["page_num"]
                    results.append({
                        "doc_id": row["doc_id"],
                        "filename": row["filename"],
                        "page_num": page_display,
                        "snippet": snippet["text"],
                        "match_start": snippet["match_start"],
                        "match_end": snippet["match_end"],
                        "match_type": "substring",
                    })
                    if len(results) >= max_results:
                        break

        # Strategy 3: Chunked fallback for long/messy queries
        # If the user copy-pasted a whole paragraph, exact phrase and substring
        # might fail due to extraction errors (e.g. missing space) or page boundaries.
        if not results and len(query_clean) > 80:
            words = query_clean.split()
            chunk_len = 15 # Take a 15-word chunk
            chunks = []
            # Extract chunks every 7 words for overlap
            for i in range(0, len(words), max(1, chunk_len // 2)):
                chunk = " ".join(words[i:i+chunk_len])
                if len(chunk) > 30:
                    chunks.append(chunk)

            if chunks:
                # rows is already defined from Strategy 2
                for row in rows:
                    content_normalized = _normalize(row["content"]).lower()
                    matched_positions = [] # Track match positions to avoid overlapping snippets
                    for chunk in chunks:
                        idx = content_normalized.find(chunk.lower())
                        if idx != -1:
                            # Check if we already have a snippet for this region (within 250 chars)
                            if not any(abs(idx - pos) < 250 for pos in matched_positions):
                                matched_positions.append(idx)
                                snippet = _extract_context(row["content"], chunk)
                                results.append({
                                    "doc_id": row["doc_id"],
                                    "filename": row["filename"],
                                    "page_num": row["page_num"],
                                    "snippet": snippet["text"],
                                    "match_start": snippet["match_start"],
                                    "match_end": snippet["match_end"],
                                    "match_type": "chunk_fallback",
                                })
                                if len(results) >= max_results:
                                    break
                    if len(results) >= max_results:
                        break

        return results
    finally:
        conn.close()


def _extract_context(
    full_text: str, query: str, context_chars: int = 150
) -> dict:
    """
    Extract a snippet from full_text centered around the query match.
    Normalizes whitespace for matching, then maps back to original text positions.
    Returns { text, match_start, match_end } where start/end are
    positions within the returned snippet text.
    """
    # Normalize both for matching
    text_norm = _normalize(full_text)
    query_norm = _normalize(query)

    idx = text_norm.lower().find(query_norm.lower())
    if idx == -1:
        # No match found, return beginning of text
        preview = text_norm[:context_chars * 2].strip()
        return {"text": preview, "match_start": -1, "match_end": -1}

    query_len = len(query_norm)

    # Calculate context window
    start = max(0, idx - context_chars)
    end = min(len(text_norm), idx + query_len + context_chars)
    snippet = text_norm[start:end].strip()

    # Add ellipsis if truncated
    if start > 0:
        snippet = "..." + snippet
        match_start = idx - start + 3  # +3 for "..."
    else:
        match_start = idx - start

    if end < len(text_norm):
        snippet = snippet + "..."

    match_end = match_start + query_len

    return {"text": snippet, "match_start": match_start, "match_end": match_end}


def delete_document(doc_id: str) -> bool:
    """Remove a document and its pages from the index."""
    conn = _get_conn()
    try:
        # Check if document exists
        row = conn.execute(
            "SELECT doc_id FROM documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        if not row:
            return False

        conn.execute("DELETE FROM pages_fts WHERE doc_id = ?", (doc_id,))
        conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def list_documents() -> list[dict]:
    """List all indexed documents."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT doc_id, filename, total_pages, indexed_at FROM documents ORDER BY indexed_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# Initialize the database on import
init_db()
