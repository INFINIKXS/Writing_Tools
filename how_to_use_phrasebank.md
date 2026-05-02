# How to Use the Academic Phrase Bank

This guide explains the end-to-end workflow for extracting high-quality academic phrases from PDFs, formatting them, and seamlessly seeding them into the Supabase database.

## Workflow Overview

The phrase extraction and insertion process relies on three steps:
1. **Extraction (LLM/Prompting):** Extract JSON objects from scientific PDFs using a strict System Prompt.
2. **Copying:** Paste the extracted batch into the seeding script (`seed_phrases.py`).
3. **Seeding:** Run the script to safely insert new records, skipping duplicates.

---

## 1. Extracting Phrases (using the System Prompt)

You use a large language model (e.g., Claude, GPT-4) combined with the project's official system prompt to process scientific PDFs. 

1. Give the LLM the contents of the file `phrasebank_extractor_system_prompt.md`.
2. Provide a section (or full text) of an academic paper.
3. The LLM will return a JSON array containing phrases mapped to one of the 11 rhetorical categories.

**Important Data Quality Rule:**
The LLM has been explicitly instructed to **avoid generic, interchangeable phrases** (e.g., "The results show that [X]", "However, [X] is important") and instead focus on highly specific, structural, and sophisticated templates. 

---

## 2. Pasting to the Seeding Script

Once you have your JSON batch output from the LLM, you need to add it to the python seeder script.

1. Open `backend/seed_phrases.py`.
2. Locate the `PHRASES = [` block at the top of the file (around line 14).
3. Replace the existing content between the brackets `[ ... ]` with your newly extracted JSON batch.

> [!WARNING]
> Ensure the JSON is properly formatted! Multi-line string literals (newlines inside quotes) will cause a `SyntaxError` in Python. The LLM output should have strings contained on a single line or escaped correctly.

*Example formatting:*
```python
PHRASES = [
    {
        "template": "There is a perception that [X] will have deleterious effects on [Y]",
        "category": "Reviewing the Literature",
        "subcategory": "Consensus Statement",
        "example": "There is a perception that population ageing will have deleterious effects on future health financing sustainability.",
        "formality_level": "formal"
    },
    # ... more phrases
]
```

---

## 3. Running the Seeder (Idempotent Insertion)

We use a safe duplication strategy. **The script will never wipe the existing database**; it checks the Supabase table for existing `(template, category)` combinations and only inserts unique, new records.

1. Ensure your IDE terminal or command prompt is using the correct virtual environment so that dependencies (like `supabase`) are resolved.

   ```bash
   cd backend
   # Activate venv on Windows:
   .\venv\Scripts\activate
   ```

2. Run the seeding script:

   ```bash
   python seed_phrases.py
   ```

3. The script will output its progress, indicating how many existing phrases were skipped and how many new, unique phrases were batch-inserted into Supabase.

> [!NOTE]
> Database Constraint: 
> The database enforces unique template-category pairs at the storage level via a SQL constraint:
> `ALTER TABLE phrases ADD CONSTRAINT unique_template_category UNIQUE (template, category);`

4. Once finished, **clear out the `PHRASES` list** in the script and you are ready to repeat the process for your next PDF batch.
