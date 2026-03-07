"""
Vector store for human-written sentences.
Indexes sentences from uploaded PDFs with their masked skeletons and
sentence-transformer embeddings for semantic similarity search.
"""
import sqlite3
import os
import re
import uuid
import json
import numpy as np
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "humanizer_index.db")

# Lazy-loaded globals
_model = None
_nlp = None


def _get_model():
    """Lazy-load the SentenceTransformer model (first call takes a few seconds)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _get_nlp():
    """Lazy-load the spaCy English model."""
    global _nlp
    if _nlp is None:
        import spacy
        try:
            _nlp = spacy.load("en_core_web_sm")
        except OSError:
            # Model not installed yet — download it
            import subprocess, sys
            subprocess.check_call([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
            _nlp = spacy.load("en_core_web_sm")
    return _nlp


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS humanizer_documents (
                doc_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                sentence_count INTEGER DEFAULT 0,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS human_sentences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT NOT NULL,
                sentence_text TEXT NOT NULL,
                masked_text TEXT NOT NULL,
                embedding BLOB NOT NULL,
                FOREIGN KEY (doc_id) REFERENCES humanizer_documents(doc_id)
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences using spaCy."""
    nlp = _get_nlp()
    doc = nlp(text)
    sentences = []
    for sent in doc.sents:
        s = sent.text.strip()
        # Only keep sentences with enough substance
        word_count = len(s.split())
        if word_count >= 6 and len(s) >= 30:
            sentences.append(s)
    return sentences


def mask_sentence(sentence: str) -> tuple[str, dict]:
    """
    Mask a sentence by replacing key entities with placeholder slots.
    Returns (masked_text, variables_dict).
    
    Strategy: use spaCy dependency parsing to identify semantic roles,
    then replace them with generic placeholders.
    """
    nlp = _get_nlp()
    doc = nlp(sentence)
    
    variables = {}
    replacements = []  # (start, end, placeholder)
    
    # --- Extract noun chunks with their syntactic roles ---
    for chunk in doc.noun_chunks:
        # Skip very short chunks (pronouns, articles alone)
        if len(chunk.text.split()) < 1 or chunk.root.pos_ == "PRON":
            continue
        
        dep = chunk.root.dep_
        
        if dep in ("nsubj", "nsubjpass"):
            key = "SUBJECT"
        elif dep in ("dobj", "pobj") and chunk.root.head.dep_ in ("agent",):
            key = "ACTOR"
        elif dep == "dobj":
            key = "OBJECT"
        elif dep == "pobj":
            # Distinguish by preposition
            prep = chunk.root.head.text.lower()
            if prep in ("into", "to", "towards"):
                key = "OUTPUT"
            elif prep in ("from", "of", "through", "via", "by"):
                key = "INPUT"
            else:
                key = "OBJECT"
        elif dep == "attr":
            key = "ATTRIBUTE"
        else:
            key = "ENTITY"
        
        # Handle duplicate keys by numbering them
        actual_key = key
        counter = 1
        while actual_key in variables:
            counter += 1
            actual_key = f"{key}_{counter}"
        
        variables[actual_key] = chunk.text
        replacements.append((chunk.start_char, chunk.end_char, f"[{actual_key}]"))
    
    # Sort replacements in reverse order to preserve character positions
    replacements.sort(key=lambda x: x[0], reverse=True)
    
    masked = sentence
    for start, end, placeholder in replacements:
        masked = masked[:start] + placeholder + masked[end:]
    
    return masked, variables


def _encode(text: str) -> bytes:
    """Encode text into an embedding vector, returned as bytes."""
    model = _get_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.astype(np.float32).tobytes()


def _bytes_to_vector(blob: bytes) -> np.ndarray:
    """Convert stored bytes back to numpy vector."""
    return np.frombuffer(blob, dtype=np.float32)


def index_document(filename: str, pages_text: list[str]) -> dict:
    """
    Index a document's sentences into the humanizer store.
    Extracts sentences, masks them, encodes embeddings, stores everything.
    Returns {"doc_id": ..., "sentence_count": ...}.
    """
    doc_id = str(uuid.uuid4())[:8]
    
    # Combine all pages into one text
    full_text = "\n".join(pages_text)
    
    # Split into sentences
    sentences = _split_sentences(full_text)
    
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO humanizer_documents (doc_id, filename, sentence_count) VALUES (?, ?, ?)",
            (doc_id, filename, len(sentences)),
        )
        
        for sent_text in sentences:
            masked, variables = mask_sentence(sent_text)
            
            # Only index sentences where masking actually did something
            # (i.e., we found at least one entity to mask)
            if variables and masked != sent_text:
                embedding_bytes = _encode(masked)
                conn.execute(
                    "INSERT INTO human_sentences (doc_id, sentence_text, masked_text, embedding) VALUES (?, ?, ?, ?)",
                    (doc_id, sent_text, masked, embedding_bytes),
                )
        
        # Update actual indexed count
        actual_count = conn.execute(
            "SELECT COUNT(*) FROM human_sentences WHERE doc_id = ?", (doc_id,)
        ).fetchone()[0]
        conn.execute(
            "UPDATE humanizer_documents SET sentence_count = ? WHERE doc_id = ?",
            (actual_count, doc_id),
        )
        
        conn.commit()
        return {"doc_id": doc_id, "sentence_count": actual_count}
    finally:
        conn.close()


def search_similar(masked_query: str, top_k: int = 5) -> list[dict]:
    """
    Find the most similar human sentence skeletons to the given masked query.
    Uses cosine similarity between sentence-transformer embeddings.
    Returns list of {"masked_text": ..., "sentence_text": ..., "similarity": ...}.
    """
    query_embedding = np.frombuffer(_encode(masked_query), dtype=np.float32)
    
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, sentence_text, masked_text, embedding FROM human_sentences"
        ).fetchall()
        
        if not rows:
            return []
        
        results = []
        for row in rows:
            stored_emb = _bytes_to_vector(row["embedding"])
            # Cosine similarity (embeddings are already normalized)
            similarity = float(np.dot(query_embedding, stored_emb))
            results.append({
                "masked_text": row["masked_text"],
                "sentence_text": row["sentence_text"],
                "similarity": similarity,
            })
        
        # Sort by similarity descending
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]
    finally:
        conn.close()


def list_documents() -> list[dict]:
    """List all indexed documents."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT doc_id, filename, sentence_count, indexed_at FROM humanizer_documents ORDER BY indexed_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def delete_document(doc_id: str) -> bool:
    """Remove a document and its sentences from the index."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT doc_id FROM humanizer_documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM human_sentences WHERE doc_id = ?", (doc_id,))
        conn.execute("DELETE FROM humanizer_documents WHERE doc_id = ?", (doc_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def get_stats() -> dict:
    """Get stats about the humanizer store."""
    conn = _get_conn()
    try:
        doc_count = conn.execute("SELECT COUNT(*) FROM humanizer_documents").fetchone()[0]
        sent_count = conn.execute("SELECT COUNT(*) FROM human_sentences").fetchone()[0]
        return {
            "total_documents": doc_count,
            "total_sentences": sent_count,
        }
    finally:
        conn.close()


# Initialize DB on import
init_db()
