"""
Gemini API client helpers: key rotation, retry logic with exponential backoff,
and automatic model fallback chain.
"""
import asyncio
import random

from google import genai
from google.genai import types as genai_types
from fastapi import HTTPException

from core.config import API_KEY, KEY_MANAGER_AVAILABLE, get_api_key_manager

MAX_RETRIES = 5
RETRY_BASE_DELAY = 2  # seconds

# Fallback model chain: tried in order when the primary model is unavailable.
# Each entry: (model_id, thinking_level or None)
FALLBACK_MODELS = [
    ('gemini-3.1-flash-lite-preview', 'low'),
    ('gemini-2.5-pro', None),
]


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


def _build_fallback_config(thinking_level, original_config):
    """Build a GenerateContentConfig with thinking injected, merging with original if present."""
    if thinking_level is None:
        return original_config
    thinking = genai_types.ThinkingConfig(thinking_level=thinking_level)
    if original_config is not None:
        # Clone relevant fields from original config and add thinking
        return genai_types.GenerateContentConfig(
            thinking_config=thinking,
        )
    return genai_types.GenerateContentConfig(
        thinking_config=thinking,
    )


async def _try_model_with_retries(client, prompt, model, config, max_retries, progress_callback, rotate_keys=True):
    """
    Attempt a Gemini API call with retries for a single model.
    Returns (response, client) on success, raises the last exception on failure.
    When rotate_keys=False, key rotation on 429 is disabled (used during fallback
    since rate limits are per-model, not per-key).
    """
    key_manager = get_api_key_manager() if KEY_MANAGER_AVAILABLE else None
    last_error = None
    for attempt in range(1, max_retries + 1):
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
                if new_key and rotate_keys:
                    client = genai.Client(api_key=new_key)
            return response, client
        except Exception as e:
            error_str = str(e)
            is_rate_limited = any(code in error_str for code in ['429', 'RESOURCE_EXHAUSTED'])
            is_retryable = is_rate_limited or any(code in error_str for code in [
                '503', 'UNAVAILABLE',
                'SSL', 'ConnectionError', 'ConnectionReset',
                'Timeout', 'timeout',
                'ServiceUnavailable', 'Server disconnected', 'ReadError',
            ])

            # On rate limit, rotate to next key (only if allowed)
            if is_rate_limited and key_manager and rotate_keys:
                has_backup = key_manager.mark_exhausted(model=model)
                if has_backup:
                    new_key = key_manager.get_current_key(model=model)
                    if new_key:
                        client = genai.Client(api_key=new_key)
                        if progress_callback:
                            await progress_callback(f'Rate limited — rotated to next API key (attempt {attempt}/{max_retries})')

            if is_retryable and attempt < max_retries:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1)
                if progress_callback:
                    await progress_callback(f'[{model}] API temporarily unavailable (attempt {attempt}/{max_retries}). Retrying in {delay:.0f}s...')
                await asyncio.sleep(delay)
                last_error = e
            else:
                last_error = e
                raise
    raise last_error


async def gemini_request_with_retry(client, prompt, model='gemini-3-flash-preview', progress_callback=None, config=None):
    """
    Make a Gemini API request with exponential backoff retry for transient errors.
    Retries on 503 UNAVAILABLE, 429 RESOURCE_EXHAUSTED, and connection errors.
    On 429 errors, rotates to next API key via the key manager.
    
    If the primary model exhausts all retries, automatically falls back through
    FALLBACK_MODELS (gemini-3.1-flash-lite-preview with thinking, then gemini-2.5-pro).
    Fallback models reuse the SAME API key (no rotation) since rate limits are per-model.
    
    Pass `config` (a GenerateContentConfig) to enable features like ThinkingConfig.
    """
    # Try primary model first
    try:
        response, client = await _try_model_with_retries(
            client, prompt, model, config, MAX_RETRIES, progress_callback
        )
        return response
    except Exception as primary_error:
        primary_error_str = str(primary_error)
        is_transient = any(code in primary_error_str for code in [
            '503', 'UNAVAILABLE', '429', 'RESOURCE_EXHAUSTED',
            'SSL', 'ConnectionError', 'ConnectionReset',
            'Timeout', 'timeout', 'ServiceUnavailable',
            'Server disconnected', 'ReadError',
        ])
        if not is_transient:
            raise  # Non-transient errors (400, 404, etc.) should not trigger fallback

    # Try fallback models — reuse the SAME client/key (rate limits are per-model)
    for fallback_model, thinking_level in FALLBACK_MODELS:
        if fallback_model == model:
            continue  # Skip if fallback is same as primary
        if progress_callback:
            await progress_callback(f'Primary model {model} unavailable — falling back to {fallback_model}...')
        try:
            fb_config = _build_fallback_config(thinking_level, config)
            response, _ = await _try_model_with_retries(
                client, prompt, fallback_model, fb_config, 3, progress_callback,
                rotate_keys=False  # Same key — rate limits are per-model
            )
            return response
        except Exception:
            continue  # Try next fallback

    # All fallbacks exhausted — raise the original error
    raise primary_error

