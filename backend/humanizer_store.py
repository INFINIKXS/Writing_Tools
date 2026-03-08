"""
Skeleton Bank for the Cognitive Synthesizer.
Mines human-written sentences from uploaded PDFs using an LLM,
categorizes them by rhetorical intent, and stores masked skeletons
for random retrieval during humanization.

No more SentenceTransformer embeddings or vector search.
"""
import sqlite3
import os
import uuid
import json
import random
import asyncio
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "humanizer_index.db")

# Lazy-loaded spaCy
_nlp = None

# Supported rhetorical intent categories
INTENT_CATEGORIES = [
    "Speech_Summary",
    "Cause_and_Effect",
    "Concept_Definition",
    "Comparison",
    "Evidence_Claim",
    "Process_Description",
    "Counter_Argument",
    "General_Statement",
]


def _get_nlp():
    """Lazy-load the spaCy English model (for sentence splitting only)."""
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
    """Create tables if they don't exist. Migrates old schema if necessary."""
    conn = _get_conn()
    try:
        # ── Schema migration: rename sentence_count → skeleton_count if needed ──
        # The old schema used sentence_count; detect and drop the old tables cleanly.
        existing_cols = [
            row[1]
            for row in conn.execute("PRAGMA table_info(humanizer_documents)").fetchall()
        ]
        if existing_cols and "skeleton_count" not in existing_cols:
            print("[Humanizer DB] Old schema detected — migrating to Cognitive Synthesizer schema...")
            conn.execute("DROP TABLE IF EXISTS human_sentences")
            conn.execute("DROP TABLE IF EXISTS skeleton_bank")
            conn.execute("DROP TABLE IF EXISTS humanizer_documents")
            conn.commit()

        # Keep the old documents table name for compatibility
        conn.execute("""
            CREATE TABLE IF NOT EXISTS humanizer_documents (
                doc_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                skeleton_count INTEGER DEFAULT 0,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # New skeleton bank table (replaces human_sentences)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS skeleton_bank (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT NOT NULL,
                intent TEXT NOT NULL,
                skeleton_text TEXT NOT NULL,
                original_text TEXT NOT NULL,
                FOREIGN KEY (doc_id) REFERENCES humanizer_documents(doc_id)
            )
        """)
        # Index for fast intent lookups
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_skeleton_intent ON skeleton_bank(intent)
        """)
        conn.commit()
    finally:
        conn.close()



def _is_valid_prose_sentence(s: str) -> bool:
    """
    Returns True only if the sentence looks like genuine human prose.
    Rejects: citations, DOI strings, URLs, page headers, reference entries,
    figure captions, short fragments, and sentences with too many numbers.
    """
    import re

    # Too short
    word_count = len(s.split())
    if word_count < 8 or len(s) < 40:
        return False

    # Too long (likely a merged paragraph/header dump)
    if word_count > 60:
        return False

    # Contains a URL or DOI
    if re.search(r'https?://|doi\.org|dx\.doi|www\.', s, re.IGNORECASE):
        return False

    # Looks like a reference / citation line (e.g. "Smith et al. (2020). Title. Journal. Vol(Issue):Pages.")
    if re.search(r'\b(et al\.?|doi|vol\.|pp\.|ed\.|eds\.|no\.|issn)\b', s, re.IGNORECASE):
        return False

    # Starts with a number (numbered reference list items: "1. Smith, J...")
    if re.match(r'^\d+[\.\)]\s', s):
        return False

    # Too many numbers (tables, statistics fragments, page ranges)
    number_count = len(re.findall(r'\b\d+\b', s))
    if number_count > 4:
        return False

    # Contains brackets typical of citations like (Smith, 2020) or [1]
    if re.search(r'\(\w[\w\s,\.]+\d{4}\w*\)|\[\d+\]', s):
        return False

    # Contains figure/table captions
    if re.match(r'^(fig(ure)?|table|appendix|box)[\s\.\d]', s, re.IGNORECASE):
        return False

    # Must contain at least one lowercase letter run (has real words, not all-caps headers)
    if not re.search(r'[a-z]{3,}', s):
        return False

    return True


def _split_sentences(text: str) -> list[str]:
    """Split text into prose sentences using spaCy, filtering out citations and fragments."""
    nlp = _get_nlp()
    doc = nlp(text)
    sentences = []
    for sent in doc.sents:
        s = sent.text.strip()
        if _is_valid_prose_sentence(s):
            sentences.append(s)
    return sentences



async def _mine_skeletons_batch(sentences: list[str]) -> list[dict]:
    """
    Send a batch of sentences to Gemini to extract skeletons and intents.
    Returns list of {"intent": ..., "skeleton": ..., "original": ...}
    """
    from main import get_client, gemini_request_with_retry

    # Process in chunks of 75 to optimize API quota while staying within output limits
    CHUNK_SIZE = 75
    all_results = []

    for i in range(0, len(sentences), CHUNK_SIZE):
        chunk = sentences[i:i + CHUNK_SIZE]
        numbered = "\n".join(f"{j+1}. {s}" for j, s in enumerate(chunk))

        prompt = f"""You are a sentence structure analyst. For each sentence below, do TWO things:

1. **Classify its Rhetorical Intent** — choose exactly ONE from this list:
   - Speech_Summary (someone said/spoke/argued something)
   - Cause_and_Effect (X causes Y, because of X then Y)
   - Concept_Definition (what something is/means)
   - Comparison (X vs Y, unlike X, similarly to)
   - Evidence_Claim (studies show, research indicates, data suggests)
   - Process_Description (how something works, step by step)
   - Counter_Argument (however, despite, on the other hand)
   - General_Statement (doesn't fit the above categories)

2. **Create a masked skeleton** — replace the key content-specific nouns/concepts with these placeholders:
   - [ACTOR] for people, speakers, researchers, organizations
   - [CONCEPT] for the main topic/idea being discussed
   - [ARGUMENT] for claims, points, conclusions
   - [CAUSE] for causes/reasons
   - [EFFECT] for effects/outcomes/results
   - [CONTEXT] for places, events, time periods
   - [EVIDENCE] for data, studies, statistics
   - [DEFINITION] for definitions/explanations
   - [COMPARISON_A] and [COMPARISON_B] for compared items

   IMPORTANT: Keep all connecting words, prepositions, conjunctions, and verb phrases INTACT.
   Only replace the content-specific nouns and noun phrases. The skeleton must remain grammatically complete.

SENTENCES:
{numbered}

Respond with a JSON array. Each element must have exactly these fields:
- "index": the sentence number (1-based)
- "intent": one of the intent categories listed above
- "skeleton": the masked version with [PLACEHOLDER] variables

Example output:
[
  {{"index": 1, "intent": "Speech_Summary", "skeleton": "[ACTOR] in [CONTEXT] spoke about [CONCEPT], there they pointed out [ARGUMENT]."}},
  {{"index": 2, "intent": "Cause_and_Effect", "skeleton": "Because of [CAUSE], we are seeing a shift in [EFFECT]."}}
]

Output ONLY the JSON array, no other text."""

        try:
            model_name = 'gemini-3.1-flash-lite-preview'
            client = get_client(model=model_name)
            response = await gemini_request_with_retry(client, prompt, model=model_name)
            raw = response.text.strip()

            # Strip markdown code fences if present
            if raw.startswith('```json'):
                raw = raw[7:].strip()
            if raw.startswith('```'):
                raw = raw[3:].strip()
            if raw.endswith('```'):
                raw = raw[:-3].strip()

            parsed = json.loads(raw)

            for item in parsed:
                idx = item.get("index", 0) - 1
                intent = item.get("intent", "General_Statement")
                skeleton = item.get("skeleton", "")

                # Validate intent is one of our categories
                if intent not in INTENT_CATEGORIES:
                    intent = "General_Statement"

                # Validate skeleton has at least one placeholder
                if "[" not in skeleton or "]" not in skeleton:
                    continue

                # Skip if skeleton is too short
                if len(skeleton.split()) < 4:
                    continue

                if 0 <= idx < len(chunk):
                    all_results.append({
                        "intent": intent,
                        "skeleton": skeleton,
                        "original": chunk[idx],
                    })

        except Exception as e:
            print(f"[Skeleton Mining] LLM batch failed: {e}")
            continue

    return all_results


async def index_document(filename: str, pages_text: list[str]) -> dict:
    """
    Index a document by mining its sentences into the skeleton bank.
    Uses LLM to extract intents and masked skeletons.
    Returns {"doc_id": ..., "skeleton_count": ...}.
    """
    doc_id = str(uuid.uuid4())[:8]

    # Combine all pages
    full_text = "\n".join(pages_text)

    # Split into sentences
    sentences = _split_sentences(full_text)

    if not sentences:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO humanizer_documents (doc_id, filename, skeleton_count) VALUES (?, ?, ?)",
                (doc_id, filename, 0),
            )
            conn.commit()
            return {"doc_id": doc_id, "skeleton_count": 0}
        finally:
            conn.close()

    # Mine skeletons using LLM
    mined = await _mine_skeletons_batch(sentences)

    # Store in database
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO humanizer_documents (doc_id, filename, skeleton_count) VALUES (?, ?, ?)",
            (doc_id, filename, len(mined)),
        )

        rows = []
        for item in mined:
            rows.append((doc_id, item["intent"], item["skeleton"], item["original"]))

        conn.executemany(
            "INSERT INTO skeleton_bank (doc_id, intent, skeleton_text, original_text) VALUES (?, ?, ?, ?)",
            rows,
        )

        conn.commit()
        return {"doc_id": doc_id, "skeleton_count": len(mined)}
    finally:
        conn.close()


def get_skeletons_by_intent(intent: str, limit: int = 50) -> list[dict]:
    """Get all skeletons matching a specific intent category."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, skeleton_text, original_text, intent FROM skeleton_bank WHERE intent = ? LIMIT ?",
            (intent, limit),
        ).fetchall()
        return [{"id": row["id"], "skeleton": row["skeleton_text"], "original": row["original_text"], "intent": row["intent"]} for row in rows]
    finally:
        conn.close()


def get_random_skeletons(intent: str, count: int = 3) -> list[dict]:
    """Get random skeletons matching a specific intent. Used during humanization."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, skeleton_text, original_text, intent FROM skeleton_bank WHERE intent = ? ORDER BY RANDOM() LIMIT ?",
            (intent, count),
        ).fetchall()
        return [{"id": row["id"], "skeleton": row["skeleton_text"], "original": row["original_text"], "intent": row["intent"]} for row in rows]
    finally:
        conn.close()


def get_style_examples(intent: str, count: int = 8) -> list[str]:
    """
    Retrieve full human-written sentences from the DB to use as style anchors
    in the RAST (Retrieval-Augmented Style Transfer) pipeline.

    Prioritises sentences from the same intent category. If fewer than `count`
    exist for that intent, supplements with examples from other intents so the
    LLM always has a rich style palette.
    """
    conn = _get_conn()
    try:
        # Primary: same intent
        rows = conn.execute(
            "SELECT original_text FROM skeleton_bank WHERE intent = ? ORDER BY RANDOM() LIMIT ?",
            (intent, count),
        ).fetchall()
        examples = [row["original_text"] for row in rows]

        # Supplement from other intents if needed
        if len(examples) < count:
            needed = count - len(examples)
            extra = conn.execute(
                "SELECT original_text FROM skeleton_bank WHERE intent != ? ORDER BY RANDOM() LIMIT ?",
                (intent, needed),
            ).fetchall()
            examples += [row["original_text"] for row in extra]

        return examples
    finally:
        conn.close()


def get_all_intents_with_counts() -> dict:
    """Get a breakdown of how many skeletons exist per intent category."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT intent, COUNT(*) as count FROM skeleton_bank GROUP BY intent ORDER BY count DESC"
        ).fetchall()
        return {row["intent"]: row["count"] for row in rows}
    finally:
        conn.close()


def list_documents() -> list[dict]:
    """List all indexed documents."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT doc_id, filename, skeleton_count, indexed_at FROM humanizer_documents ORDER BY indexed_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def delete_document(doc_id: str) -> bool:
    """Remove a document and its skeletons from the bank."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT doc_id FROM humanizer_documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM skeleton_bank WHERE doc_id = ?", (doc_id,))
        conn.execute("DELETE FROM humanizer_documents WHERE doc_id = ?", (doc_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def get_stats() -> dict:
    """Get stats about the skeleton bank."""
    conn = _get_conn()
    try:
        doc_count = conn.execute("SELECT COUNT(*) FROM humanizer_documents").fetchone()[0]
        skeleton_count = conn.execute("SELECT COUNT(*) FROM skeleton_bank").fetchone()[0]
        return {
            "total_documents": doc_count,
            "total_skeletons": skeleton_count,
            # Keep backward compat for frontend
            "total_sentences": skeleton_count,
        }
    finally:
        conn.close()


# Initialize DB on import
init_db()
