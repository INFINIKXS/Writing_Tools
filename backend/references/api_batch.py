import asyncio
import time
import httpx
import logging
from dataclasses import dataclass, field
from typing import Optional
from tenacity import (
    retry, stop_after_attempt,
    wait_exponential, retry_if_exception_type
)

logger = logging.getLogger(__name__)

CR_BASE = 'https://api.crossref.org'
MAILTO  = 'support@writingtools.local'  # Required for Crossref polite pool
HEADERS = {'User-Agent': f'WritingTools/1.0 (mailto:{MAILTO})'}

@dataclass
class MetadataRecord:
    source:       str
    title:        str = ''
    authors:      list[str] = field(default_factory=list)
    journal:      str = ''
    year:         Optional[int] = None
    doi:          Optional[str] = None
    pmid:         Optional[str] = None
    abstract:     str = ''
    url:          Optional[str] = None
    open_access:  bool = False
    citations:    Optional[int] = None
    volume:       Optional[str] = None
    issue:        Optional[str] = None
    pages:        Optional[str] = None
    publisher:    Optional[str] = None
    type:         str = 'Journal Article'

class TokenBucket:
    def __init__(self, rate=5, capacity=5):
        self.rate = rate          # tokens added per second
        self.capacity = capacity  # max burst
        self.tokens = capacity
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.rate
            )
            self.last_refill = now
            if self.tokens < 1:
                wait = (1 - self.tokens) / self.rate
                await asyncio.sleep(wait)
                self.tokens = 0
                self.last_refill = time.monotonic()
            else:
                self.tokens -= 1

# Shared rate limiter across all batch API outbound requests
rate_limiter = TokenBucket(rate=5, capacity=5)

@retry(
    retry=retry_if_exception_type(httpx.HTTPStatusError),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=60),
    reraise=True
)
async def safe_get(client: httpx.AsyncClient, url: str, params=None, headers=None):
    r = await client.get(url, params=params, headers=headers)
    if r.status_code == 429:
        retry_after = int(r.headers.get('Retry-After', 10))
        logger.warning(f"429 Too Many Requests from {url}. Retrying after {retry_after}s.")
        await asyncio.sleep(retry_after)
        r.raise_for_status()
    r.raise_for_status()
    return r

def normalise_crossref(msg: dict) -> MetadataRecord:
    authors = []
    for a in msg.get('author', []):
        family = a.get('family', '')
        given = a.get('given', '')
        if family and given:
            # Initials formatting to match our existing expected schema
            initials = ". ".join(w[0].upper() for w in given.split() if w) + "."
            authors.append(f"{family}, {initials}")
        elif family:
            authors.append(family)
        elif given:
            authors.append(given)

    date_parts = (msg.get('issued', {}).get('date-parts') or [[]])[0]
    year = date_parts[0] if date_parts else None
    
    return MetadataRecord(
        source='crossref',
        title=(msg.get('title') or [''])[0],
        authors=authors, 
        year=year,
        doi=msg.get('DOI', '').lower() if msg.get('DOI') else None,
        journal=(msg.get('container-title') or [''])[0],
        url=msg.get('URL'),
        citations=msg.get('is-referenced-by-count'),
        open_access='license' in msg,
        volume=msg.get('volume'),
        issue=msg.get('issue'),
        pages=msg.get('page'),
        publisher=msg.get('publisher'),
        type=msg.get('type', 'Journal Article')
    )

async def fetch_one_doi(client: httpx.AsyncClient, doi: str) -> Optional[MetadataRecord]:
    await rate_limiter.acquire()
    url = f'{CR_BASE}/works/{doi}?mailto={MAILTO}'
    try:
        r = await safe_get(client, url, headers=HEADERS)
        data = r.json()['message']
        return normalise_crossref(data)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        logger.error(f"HTTPError fetching DOI {doi}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error fetching DOI {doi}: {e}")
        return None

async def fetch_crossref_batch(dois: list[str], client: Optional[httpx.AsyncClient] = None) -> list[MetadataRecord]:
    """Fetch multiple DOIs concurrently via the TokenBucket."""
    if client:
        tasks = [fetch_one_doi(client, doi) for doi in dois]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    else:
        async with httpx.AsyncClient(timeout=30) as new_client:
            tasks = [fetch_one_doi(new_client, doi) for doi in dois]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
    valid_results = []
    for r in results:
        if r and not isinstance(r, Exception):
            valid_results.append(r)
    return valid_results
