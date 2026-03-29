"""
Phrasebank API routes.
"""
import io

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from PyPDF2 import PdfReader

import phrasebank_store

router = APIRouter()


class PhrasebankRequest(BaseModel):
    text: str


@router.post("/api/phrasebank/rewrite")
async def api_phrasebank_rewrite(req: PhrasebankRequest):
    """Rewrite a sentence using Academic Phrasebank principles."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")

    from phrasebank import process_phrasebank_rewrite
    result = await process_phrasebank_rewrite(req.text)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
         
    return result


@router.post("/api/phrasebank/upload")
async def phrasebank_upload(files: list[UploadFile] = File(...)):
    """Upload PDF(s) and mine them for academic phrase templates."""
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
                
            result = await phrasebank_store.index_document(file.filename, pages_text)
            indexed.append({
                "doc_id": result["doc_id"],
                "filename": file.filename,
                "phrase_count": result["phrase_count"],
            })
        except Exception as e:
            errors.append({"filename": file.filename, "error": str(e)})
    return {"indexed": indexed, "errors": errors}


@router.get("/api/phrasebank/documents")
async def phrasebank_list_documents():
    """List all mapped phrasebank documents."""
    docs = phrasebank_store.list_documents()
    return {"documents": docs}


@router.delete("/api/phrasebank/document/{doc_id}")
async def phrasebank_delete_document(doc_id: str):
    """Remove a document and its phrases from the Phrasebank."""
    success = phrasebank_store.delete_document(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted": doc_id}


@router.get("/api/phrasebank/stats")
async def phrasebank_stats():
    """Get stats about the phrasebank database."""
    stats = phrasebank_store.get_stats()
    return stats
