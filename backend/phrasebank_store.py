"""
Store for the Academic Phrase Bank.
Extracts templates and phrases from uploaded PDFs and stores them 
in a SQLite database (phrasebank_index.db).
"""
import sqlite3
import os
import uuid
import json
import asyncio
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "phrasebank_index.db")

# Supported rhetorical phrase categories
PHRASE_CATEGORIES = [
    "Defining Terms",
    "Establishing a Gap",
    "Stating the Aim",
    "Describing Methods",
    "Reporting Results",
    "Discussing Findings",
    "Concluding",
    "General Transition",
]

_nlp = None
def _get_nlp():
    global _nlp
    if _nlp is None:
        import spacy
        try:
            _nlp = spacy.load("en_core_web_sm")
        except OSError:
            import subprocess, sys
            subprocess.check_call([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
            _nlp = spacy.load("en_core_web_sm")
    return _nlp

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS phrasebank_documents (
                doc_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                phrase_count INTEGER DEFAULT 0,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS phrase_bank (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT NOT NULL,
                category TEXT NOT NULL,
                template_text TEXT NOT NULL,
                original_text TEXT NOT NULL,
                FOREIGN KEY (doc_id) REFERENCES phrasebank_documents(doc_id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_phrase_category ON phrase_bank(category)
        """)
        conn.commit()
    finally:
        conn.close()

def _is_valid_prose_sentence(s: str) -> bool:
    import re
    word_count = len(s.split())
    if word_count < 6 or len(s) < 30: return False
    if word_count > 60: return False
    if re.search(r'https?://|doi\.org|dx\.doi|www\.', s, re.IGNORECASE): return False
    if re.search(r'\b(et al\.?|doi|vol\.|pp\.|ed\.|eds\.|no\.|issn)\b', s, re.IGNORECASE): return False
    if re.match(r'^\d+[\.\)]\s', s): return False
    if len(re.findall(r'\b\d+\b', s)) > 4: return False
    if re.search(r'\(\w[\w\s,\.]+\d{4}\w*\)|\[\d+\]', s): return False
    if not re.search(r'[a-z]{3,}', s): return False
    return True

def _split_sentences(text: str) -> list[str]:
    nlp = _get_nlp()
    doc = nlp(text)
    sentences = []
    for sent in doc.sents:
        s = sent.text.strip()
        if _is_valid_prose_sentence(s):
            sentences.append(s)
    return sentences

async def _mine_phrases_batch(sentences: list[str]) -> list[dict]:
    from main import get_client, gemini_request_with_retry
    
    CHUNK_SIZE = 50
    all_results = []
    
    for i in range(0, len(sentences), CHUNK_SIZE):
        chunk = sentences[i:i + CHUNK_SIZE]
        numbered = "\n".join(f"{j+1}. {s}" for j, s in enumerate(chunk))
        
        prompt = f"""You are analyzing academic text to build an Academic Phrasebank.
Read each sentence below and extract highly generic, reusable academic phrases or templates.

1. **Categorize the Phrase**:
   - Defining Terms (e.g., "The term X refers to...")
   - Establishing a Gap (e.g., "However, little is known about...")
   - Stating the Aim (e.g., "The aim of this study is to...")
   - Describing Methods (e.g., "Data were collected using...")
   - Reporting Results (e.g., "The results indicate that...")
   - Discussing Findings (e.g., "These findings suggest...")
   - Concluding (e.g., "In conclusion, we have shown...")
   - General Transition (e.g., "On the other hand...")

2. **Extract the Template**:
   Remove the specific topic nouns and replace them with [X], [Y], or generic labels.
   Only return a result if the sentence actually contains a strong, reusable academic template. If it's just topic-specific facts, ignore it.

SENTENCES:
{numbered}

Respond with a JSON array. Each element must have:
- "index": the sentence number (1-based)
- "category": one of the categories listed above
- "template": the extracted generic phrase (e.g., "The term [X] refers to...")

Output ONLY the JSON array, no other text."""

        try:
            model_name = 'gemini-3.1-flash-lite-preview'
            client = get_client(model=model_name)
            response = await gemini_request_with_retry(client, prompt, model=model_name)
            raw = response.text.strip()

            if raw.startswith('```json'): raw = raw[7:].strip()
            if raw.startswith('```'): raw = raw[3:].strip()
            if raw.endswith('```'): raw = raw[:-3].strip()

            parsed = json.loads(raw)
            for item in parsed:
                idx = item.get("index", 0) - 1
                cat = item.get("category", "General Transition")
                template = item.get("template", "")
                
                if cat not in PHRASE_CATEGORIES:
                    cat = "General Transition"
                if len(template.split()) < 3:
                    continue
                    
                if 0 <= idx < len(chunk):
                    all_results.append({
                        "category": cat,
                        "template": template,
                        "original": chunk[idx],
                    })
        except Exception as e:
            print(f"[Phrase Mining] LLM batch failed: {e}")
            continue

    return all_results

async def index_document(filename: str, pages_text: list[str]) -> dict:
    doc_id = str(uuid.uuid4())[:8]
    full_text = "\n".join(pages_text)
    sentences = _split_sentences(full_text)

    if not sentences:
        conn = _get_conn()
        try:
            conn.execute("INSERT INTO phrasebank_documents (doc_id, filename, phrase_count) VALUES (?, ?, ?)", (doc_id, filename, 0))
            conn.commit()
            return {"doc_id": doc_id, "phrase_count": 0}
        finally:
            conn.close()

    mined = await _mine_phrases_batch(sentences)

    conn = _get_conn()
    try:
        conn.execute("INSERT INTO phrasebank_documents (doc_id, filename, phrase_count) VALUES (?, ?, ?)", (doc_id, filename, len(mined)))
        
        rows = [(doc_id, item["category"], item["template"], item["original"]) for item in mined]
        conn.executemany("INSERT INTO phrase_bank (doc_id, category, template_text, original_text) VALUES (?, ?, ?, ?)", rows)
        conn.commit()
        return {"doc_id": doc_id, "phrase_count": len(mined)}
    finally:
        conn.close()

def get_random_templates(category: str, count: int = 5) -> list[str]:
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT template_text FROM phrase_bank WHERE category = ? ORDER BY RANDOM() LIMIT ?", (category, count)).fetchall()
        templates = [row["template_text"] for row in rows]
        
        if len(templates) < count:
            needed = count - len(templates)
            extra = conn.execute("SELECT template_text FROM phrase_bank WHERE category != ? ORDER BY RANDOM() LIMIT ?", (category, needed)).fetchall()
            templates += [row["template_text"] for row in extra]
            
        return templates
    finally:
        conn.close()

def get_stats() -> dict:
    conn = _get_conn()
    try:
        doc_count = conn.execute("SELECT COUNT(*) FROM phrasebank_documents").fetchone()[0]
        phrase_count = conn.execute("SELECT COUNT(*) FROM phrase_bank").fetchone()[0]
        return {
            "total_documents": doc_count,
            "total_phrases": phrase_count
        }
    finally:
        conn.close()

def list_documents() -> list[dict]:
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT doc_id, filename, phrase_count, indexed_at FROM phrasebank_documents ORDER BY indexed_at DESC").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def delete_document(doc_id: str) -> bool:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT doc_id FROM phrasebank_documents WHERE doc_id = ?", (doc_id,)).fetchone()
        if not row: return False
        conn.execute("DELETE FROM phrase_bank WHERE doc_id = ?", (doc_id,))
        conn.execute("DELETE FROM phrasebank_documents WHERE doc_id = ?", (doc_id,))
        conn.commit()
        return True
    finally:
        conn.close()

init_db()
