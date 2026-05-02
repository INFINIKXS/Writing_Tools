"""
Seed script — populates the Supabase 'phrases' table with curated
academic phrase templates across 11 rhetorical categories.

Run once:  python seed_phrases.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from db.supabase_client import supabase

PHRASES = [
    # Paste new JSON batch here
]


def seed_phrases_safe(phrases: list[dict]):
    if not phrases:
        print("PHRASES list is empty — nothing to insert.")
        return

    print(f"Checking {len(phrases)} phrases for duplicates...")

    # Fetch all existing template+category combos from Supabase
    existing_response = supabase.table("phrases").select("template, category").execute()
    existing_records = existing_response.data or []
    
    # Create a set of existing (template, category) tuples for fast lookup
    existing_set = {(record["template"], record["category"]) for record in existing_records}
    
    new_phrases = []
    
    # Flatten phrases if the user accidentally pasted a JSON array inside the PHRASES array
    flat_phrases = []
    for item in phrases:
        if isinstance(item, list):
            flat_phrases.extend(item)
        elif isinstance(item, dict):
            flat_phrases.append(item)

    for phrase in flat_phrases:
        key = (phrase.get("template"), phrase.get("category"))
        if key not in existing_set:
            new_phrases.append(phrase)
            existing_set.add(key) # Add to set to prevent duplicates within the same batch

    if not new_phrases:
        print("All phrases already exist in the database. Nothing to insert.")
        return

    print(f"Found {len(new_phrases)} new unique phrases. Inserting in batches...")

    # Insert in batches
    BATCH = 50
    inserted = 0
    for i in range(0, len(new_phrases), BATCH):
        batch = new_phrases[i : i + BATCH]
        result = supabase.table("phrases").insert(batch).execute()
        inserted += len(result.data)
        print(f"  Inserted {inserted}/{len(new_phrases)}")

    print(f"\nDone! {inserted} new phrases seeded.")


def auto_clear_phrases():
    import os
    file_path = os.path.abspath(__file__)
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Find where PHRASES = [ starts
    start_str = "PHRASES = ["
    start_idx = content.find(start_str)
    if start_idx == -1: return

    # Find the function definition
    end_str = "def seed_phrases_safe("
    end_idx = content.find(end_str, start_idx)
    if end_idx == -1: return

    # Find the last closing bracket before the function
    last_bracket_idx = content.rfind("]", start_idx, end_idx)
    if last_bracket_idx == -1: return

    # Replace everything between the opening [ and the final ]
    new_content = content[:start_idx + len(start_str)] + "\n    # Paste new JSON batch here\n" + content[last_bracket_idx:]
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Auto-cleared PHRASES array from seed_phrases.py for the next run.")


if __name__ == "__main__":
    seed_phrases_safe(PHRASES)
    auto_clear_phrases()
