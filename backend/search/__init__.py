"""
Full-text search API routes.
"""
import io

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from PyPDF2 import PdfReader

import search_store

router = APIRouter()


class SearchQuery(BaseModel):
    queries: list[str]


@router.post("/api/search/upload")
async def search_upload(files: list[UploadFile] = File(...)):
    """Upload PDF(s) and index their full text for searching."""
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
            doc_id = search_store.index_document(file.filename, pages_text)
            indexed.append({
                "doc_id": doc_id,
                "filename": file.filename,
                "total_pages": len(pages_text),
            })
        except Exception as e:
            errors.append({"filename": file.filename, "error": str(e)})
    return {"indexed": indexed, "errors": errors}


@router.post("/api/search/query")
async def search_query(req: SearchQuery):
    """Search for multiple phrases across all indexed documents simultaneously."""
    clean_queries = [q.strip() for q in req.queries if q.strip()]
    if not clean_queries:
        raise HTTPException(status_code=400, detail="At least one query is required")
    
    all_results = []
    for query_text in clean_queries:
        matches = search_store.search(query_text)
        all_results.append({
            "query": query_text,
            "results": matches,
            "total": len(matches),
        })
    return {"groups": all_results, "total_queries": len(clean_queries)}


@router.delete("/api/search/document/{doc_id}")
async def search_delete_document(doc_id: str):
    """Remove a document from the search index."""
    success = search_store.delete_document(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted": doc_id}


@router.get("/api/search/documents")
async def search_list_documents():
    """List all indexed documents."""
    docs = search_store.list_documents()
    return {"documents": docs}
