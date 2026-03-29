"""
Reference extraction and formatting API routes.
"""
import re

from fastapi import APIRouter, UploadFile, File, HTTPException, Request

from utils.text_extraction import extract_doc_text
from references.metadata import extract_pdf_metadata, extract_docx_metadata
from references.parser import FormatRequest, parse_raw_reference
from citations.formatting import format_reference
from core.config import API_KEY, KEY_MANAGER_AVAILABLE, get_api_key_manager

router = APIRouter()


@router.post("/api/extract-reference")
async def extract_reference(file: UploadFile = File(...), style: str = "harvard"):
    """Upload a PDF/DOCX and get a formatted reference for citing it."""
    if not file.filename.lower().endswith(('.pdf', '.docx', '.doc')):
        raise HTTPException(status_code=400, detail="Unsupported file type. Please upload PDF, DOCX, or DOC.")
    
    file_bytes = await file.read()
    magic = file_bytes[:8]
    
    try:
        if magic[:4] == b'%PDF':
            metadata = await extract_pdf_metadata(file_bytes)
        elif magic[:2] == b'PK':
            metadata = extract_docx_metadata(file_bytes)
        elif magic[:4] == b'\xd0\xcf\x11\xe0':
            text = extract_doc_text(file_bytes)
            metadata = {
                "authors": None, "title": file.filename.rsplit('.', 1)[0],
                "year": None, "source": None, "doi": None, "url": None,
                "volume": None, "issue": None, "pages": None,
                "publisher": None, "type": "Other",
            }
            if text:
                doi_match = re.search(r'(?:doi[:\s]*|https?://(?:dx\.)?doi\.org/)(\S+?)(?:\s|$)', text, re.IGNORECASE)
                if doi_match:
                    metadata["doi"] = doi_match.group(1).rstrip('.,;)')
                year_match = re.search(r'\b(19|20)\d{2}\b', text[:2000])
                if year_match:
                    metadata["year"] = year_match.group(0)
        else:
            raise HTTPException(status_code=400, detail="Unrecognized file format.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")
    
    result = format_reference(metadata, style)
    return result


@router.post("/api/reformat-reference")
async def reformat_reference(request: Request, style: str = "harvard"):
    """Reformat an already-extracted reference with a different style. No re-extraction needed."""
    body = await request.json()
    metadata = body.get("metadata")
    if not metadata:
        raise HTTPException(status_code=400, detail="Missing metadata in request body.")
    result = format_reference(metadata, style)
    return result


@router.post("/api/format")
async def format_references(req: FormatRequest):
    """
    Parse raw reference text into metadata, then format deterministically.
    Returns metadata alongside formatted output so the frontend can do instant style switching.
    """
    formatted_refs = []
    for ref in req.references:
        try:
            metadata = await parse_raw_reference(ref)
            result = format_reference(metadata, req.style)
            result["original"] = ref
            formatted_refs.append(result)
        except Exception as e:
            formatted_refs.append({"original": ref, "error": str(e)})

    return {"formatted_references": formatted_refs}


@router.get("/api-key-usage")
async def api_key_usage():
    """Return current API key usage statistics for frontend dashboard."""
    if KEY_MANAGER_AVAILABLE:
        manager = get_api_key_manager()
        return manager.get_status()
    return {
        "service": "Google",
        "total_keys": 1 if API_KEY else 0,
        "available_keys": 1 if API_KEY else 0,
        "exhausted_keys": 0,
        "keys": [],
        "message": "Key manager not available, using single key mode"
    }
