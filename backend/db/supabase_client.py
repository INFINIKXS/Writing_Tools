"""
Supabase client — centralised connection for the Writing Tools backend.

Uses the service_role key so the backend has full CRUD access.
Frontend never sees this key; it talks to FastAPI, not Supabase directly.
"""
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()


def get_supabase() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


# Singleton — import this from anywhere in the backend
supabase: Client = get_supabase()
