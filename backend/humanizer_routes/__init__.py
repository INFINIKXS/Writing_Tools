"""
Humanizer (Cognitive Synthesizer) API routes.
"""
import io

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from PyPDF2 import PdfReader

import humanizer_store
import humanizer

router = APIRouter()


class HumanizeRequest(BaseModel):
    text: str


@router.post("/api/humanizer/upload")
async def humanizer_upload(files: list[UploadFile] = File(...)):
    """Upload PDF(s) and mine their sentences into the skeleton bank using LLM."""
    indexed = []
    errors = []
    for file in files:
        if not file.filename.lower().endswith('.pdf'):
            errors.append({"filename": file.filename, "error": "Only PDF files are supported"})
            continue
        try:
            file_bytes = await file.read()
            if file_bytes[:4] != b'%PDF':
                errors.append({"filename": file.filename, "error": "Not a valid PDF file"})
                continue
            reader = PdfReader(io.BytesIO(file_bytes))
            pages_text = []
            for page in reader.pages:
                text = page.extract_text() or ''
                pages_text.append(text)
            if not any(t.strip() for t in pages_text):
                errors.append({"filename": file.filename, "error": "No text could be extracted from PDF"})
                continue
            result = await humanizer_store.index_document(file.filename, pages_text)
            indexed.append({
                "doc_id": result["doc_id"],
                "filename": file.filename,
                "skeleton_count": result["skeleton_count"],
                "sentence_count": result["skeleton_count"],
            })
        except Exception as e:
            errors.append({"filename": file.filename, "error": str(e)})
    return {"indexed": indexed, "errors": errors}


@router.post("/api/humanizer/humanize")
async def humanizer_humanize(req: HumanizeRequest):
    """Run the Cognitive Synthesizer pipeline on the given text."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")
    
    stats = humanizer_store.get_stats()
    if stats["total_skeletons"] == 0:
        raise HTTPException(
            status_code=400,
            detail="No human skeletons in database. Upload PDFs with human-written text first."
        )
    
    result = await humanizer.humanize_text(req.text)
    return result


@router.get("/api/humanizer/documents")
async def humanizer_list_documents():
    """List all documents in the skeleton bank."""
    docs = humanizer_store.list_documents()
    return {"documents": docs}


@router.delete("/api/humanizer/document/{doc_id}")
async def humanizer_delete_document(doc_id: str):
    """Remove a document and its skeletons from the bank."""
    success = humanizer_store.delete_document(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted": doc_id}


@router.get("/api/humanizer/stats")
async def humanizer_stats():
    """Get stats about the skeleton bank."""
    stats = humanizer_store.get_stats()
    return stats
