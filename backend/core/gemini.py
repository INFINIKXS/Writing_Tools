"""
Gemini API client helpers: key rotation, retry logic with exponential backoff.
"""
import asyncio
import random

from google import genai
from fastapi import HTTPException

from core.config import API_KEY, KEY_MANAGER_AVAILABLE, get_api_key_manager

MAX_RETRIES = 5
RETRY_BASE_DELAY = 2  # seconds


def get_client(model: str = None):
    """Get a genai Client using the key manager (with rotation) or fallback to single env var."""
    api_key = None
    if KEY_MANAGER_AVAILABLE:
        manager = get_api_key_manager()
        api_key = manager.get_current_key(model=model)
    if not api_key:
        api_key = API_KEY
    if not api_key:
        raise HTTPException(status_code=500, detail="No API key available. Set GOOGLE_API_KEYS or GOOGLE_API_KEY in .env")
    return genai.Client(api_key=api_key)


async def gemini_request_with_retry(client, prompt, model='gemini-3-flash-preview', progress_callback=None, config=None):
    """
    Make a Gemini API request with exponential backoff retry for transient errors.
    Retries on 503 UNAVAILABLE, 429 RESOURCE_EXHAUSTED, and connection errors.
    On 429 errors, rotates to next API key via the key manager.
    Pass `config` (a GenerateContentConfig) to enable features like ThinkingConfig.
    """
    key_manager = get_api_key_manager() if KEY_MANAGER_AVAILABLE else None

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            kwargs = dict(model=model, contents=prompt)
            if config is not None:
                kwargs['config'] = config
            response = await asyncio.to_thread(
                client.models.generate_content,
                **kwargs,
            )
            # Track usage AFTER successful call (not before)
            if key_manager:
                new_key = key_manager.increment_usage(model=model)
                if new_key:
                    client = genai.Client(api_key=new_key)
            return response
        except Exception as e:
            error_str = str(e)
            is_rate_limited = any(code in error_str for code in ['429', 'RESOURCE_EXHAUSTED'])
            is_retryable = is_rate_limited or any(code in error_str for code in [
                '503', 'UNAVAILABLE',
                'SSL', 'ConnectionError', 'ConnectionReset',
                'Timeout', 'timeout',
                'ServiceUnavailable',
            ])

            # On rate limit, rotate to next key
            if is_rate_limited and key_manager:
                has_backup = key_manager.mark_exhausted(model=model)
                if has_backup:
                    new_key = key_manager.get_current_key(model=model)
                    if new_key:
                        client = genai.Client(api_key=new_key)
                        if progress_callback:
                            await progress_callback(f'Rate limited — rotated to next API key (attempt {attempt}/{MAX_RETRIES})')

            if is_retryable and attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1)
                if progress_callback:
                    await progress_callback(f'API temporarily unavailable (attempt {attempt}/{MAX_RETRIES}). Retrying in {delay:.0f}s...')
                await asyncio.sleep(delay)
                last_error = e
            else:
                raise
    raise last_error
