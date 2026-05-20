"""
Reference extraction and formatting API routes.
"""
import re
import json
import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import StreamingResponse

from utils.text_extraction import extract_doc_text
from references.metadata import extract_pdf_metadata, extract_docx_metadata
from references.parser import FormatRequest, parse_raw_reference
from citations.formatting import format_reference
from references.matcher import parse_reference_list, match_references_to_pdfs, extract_pdf_metadata_fast, parse_raw_reference_fast
from references.ref_list_verifier import detect_style, verify_single_reference
from utils.text_utils import extract_doi
from core.config import API_KEY, KEY_MANAGER_AVAILABLE, get_api_key_manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/extract-reference")
async def extract_reference(
    file: UploadFile = File(...),
    style: str = "harvard",
    advanced: bool = Form(False)
):
    """Upload a PDF/DOCX and get a formatted reference for citing it."""
    if not file.filename.lower().endswith(('.pdf', '.docx', '.doc')):
        raise HTTPException(status_code=400, detail="Unsupported file type. Please upload PDF, DOCX, or DOC.")
    
    file_bytes = await file.read()
    
    if advanced:
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Advanced Mode (AI Extraction) only supports PDF files.")
        
        import tempfile
        import os
        from references.ai_extractor import extract_metadata_with_ai
        from references.metadata import crossref_lookup, pubmed_lookup, _validate_api_result, _merge
        
        fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(file_bytes)
            
            # 1. Ask Gemini for the metadata
            ai_data = await extract_metadata_with_ai(tmp_path)
            if not ai_data:
                raise HTTPException(status_code=404, detail="AI failed to extract metadata from the document.")
                
            candidate_doi = ai_data.get("doi")
            verified = False
            
            local_meta = {
                "title": None, "authors": [], "year": None, "doi": None,
                "journal": None, "volume": None, "issue": None, "pages": None,
                "publisher": None, "type": "Other", "verification_status": "not_found",
                "extraction_layers": [],
            }
            
            # 2. Try Standard API Validation if a DOI was found
            if candidate_doi:
                pubmed = pubmed_lookup(candidate_doi)
                if pubmed and _validate_api_result(local_meta, pubmed, tmp_path):
                    _merge(local_meta, pubmed, overwrite=True)
                    local_meta["verification_status"] = "verified_pubmed"
                    local_meta.setdefault("extraction_layers", []).append("ai_rescue")
                    verified = True
                else:
                    crossref = crossref_lookup(candidate_doi)
                    if crossref and _validate_api_result(local_meta, crossref, tmp_path):
                        _merge(local_meta, crossref, overwrite=True)
                        local_meta["verification_status"] = "verified_crossref"
                        local_meta.setdefault("extraction_layers", []).append("ai_rescue")
                        verified = True
                        
            # 3. AI Full Metadata Fallback - If no DOI found or validation failed
            if not verified:
                from references.metadata import strict_ai_verify_against_pdf
                
                # Physically verify ALL of the AI hallucination against the raw PDF text
                if strict_ai_verify_against_pdf(ai_data, tmp_path):
                    for k in ["title", "authors", "year", "source", "journal", "volume", "issue", "pages", "publisher", "type"]:
                        if ai_data.get(k):
                            local_meta[k] = ai_data[k]
                    
                    # If it gave a journal but we need 'source'
                    if not local_meta.get("source") and ai_data.get("journal"):
                        local_meta["source"] = ai_data["journal"]
                        
                    local_meta["verification_status"] = "verified_ai_strict_scan"
                    local_meta.setdefault("extraction_layers", []).append("ai_full_extract")
                    verified = True
                    
            if not verified:
                raise HTTPException(status_code=400, detail="AI extraction failed identity verification against the PDF.")
                
        finally:
            if os.path.exists(tmp_path):
                try: os.unlink(tmp_path)
                except: pass
                
        result = format_reference(local_meta, style)
        return result
        
    magic = file_bytes[:8]
    
    try:
        if magic[:4] == b'%PDF':
            metadata = await extract_pdf_metadata(file_bytes)
        elif magic[:2] == b'PK':
            metadata = await asyncio.to_thread(extract_docx_metadata, file_bytes)
        elif magic[:4] == b'\xd0\xcf\x11\xe0':
            text = await asyncio.to_thread(extract_doc_text, file_bytes)
            metadata = {
                "authors": None, "title": file.filename.rsplit('.', 1)[0],
                "year": None, "source": None, "doi": None, "url": None,
                "volume": None, "issue": None, "pages": None,
                "publisher": None, "type": "Other",
            }
            if text:
                found_doi = extract_doi(text)
                if found_doi:
                    metadata["doi"] = found_doi
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


@router.post("/api/retry-ai-doi")
async def retry_ai_doi(
    file: UploadFile = File(...), 
    metadata: str = Form(...),
    style: str = Form("harvard")
):
    """Fallback endpoint to use AI (Gemini) to find the DOI when standard parsers fail."""
    import tempfile
    import os
    from references.ai_extractor import extract_metadata_with_ai
    from references.metadata import crossref_lookup, pubmed_lookup, _validate_api_result, _merge

    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="AI extraction only supports PDFs.")
    
    local_meta = json.loads(metadata)
    file_bytes = await file.read()
    
    fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(file_bytes)
        
        # 1. Ask Gemini for the metadata
        ai_data = await extract_metadata_with_ai(tmp_path)
        if not ai_data:
            raise HTTPException(status_code=404, detail="AI failed to extract metadata from the document.")
            
        candidate_doi = ai_data.get("doi")
        verified = False
        
        # 2. Try Standard API Validation if a DOI was found
        if candidate_doi:
            pubmed = pubmed_lookup(candidate_doi)
            if pubmed and _validate_api_result(local_meta, pubmed, tmp_path):
                _merge(local_meta, pubmed, overwrite=True)
                local_meta["verification_status"] = "verified_pubmed"
                if "ai_rescue" not in local_meta.get("extraction_layers", []):
                    local_meta.setdefault("extraction_layers", []).append("ai_rescue")
                verified = True
            else:
                crossref = crossref_lookup(candidate_doi)
                if crossref and _validate_api_result(local_meta, crossref, tmp_path):
                    _merge(local_meta, crossref, overwrite=True)
                    local_meta["verification_status"] = "verified_crossref"
                    if "ai_rescue" not in local_meta.get("extraction_layers", []):
                        local_meta.setdefault("extraction_layers", []).append("ai_rescue")
                    verified = True
                    
        # 3. AI Full Metadata Fallback - If no DOI found or validation failed
        if not verified:
            from references.metadata import strict_ai_verify_against_pdf
            
            # Physically verify ALL of the AI hallucination against the raw PDF text
            if strict_ai_verify_against_pdf(ai_data, tmp_path):
                for k in ["title", "authors", "year", "source", "journal", "volume", "issue", "pages", "publisher", "type"]:
                    if ai_data.get(k):
                        local_meta[k] = ai_data[k]
                
                # If it gave a journal but we need 'source'
                if not local_meta.get("source") and ai_data.get("journal"):
                    local_meta["source"] = ai_data["journal"]
                    
                local_meta["verification_status"] = "verified_ai_strict_scan"
                if "ai_full_extract" not in local_meta.get("extraction_layers", []):
                    local_meta.setdefault("extraction_layers", []).append("ai_full_extract")
                verified = True
                
        if not verified:
            raise HTTPException(status_code=400, detail="AI extraction failed identity verification against the PDF.")
            
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
            
    result = format_reference(local_meta, style)
    return result


@router.post("/api/extract-reference-batch")
async def extract_reference_batch(
    files: list[UploadFile] = File(...),
    ids: list[str] = Form(...),
    style: str = Form("harvard")
):
    """
    Extract metadata from multiple PDFs concurrently using Gemini batch extraction.
    Takes matching lists of `files` and frontend `ids`.
    Extracts the first 3 pages of each PDF, bundles them into a single Gemini prompt,
    and runs concurrent verification & formatting.
    """
    import tempfile
    import os
    import asyncio
    from pypdf import PdfReader
    from references.ai_extractor import extract_metadata_batch_with_ai
    from references.metadata import crossref_lookup, pubmed_lookup, _validate_api_result, _merge

    if not len(files) == len(ids):
        raise HTTPException(status_code=400, detail="Mismatched files and ids lists.")

    texts_for_ai = []
    local_metas_map = {}
    tmp_paths_map = {}
    
    try:
        # Save files and extract first 3 pages
        for f, pid in zip(files, ids):
            if not f.filename.lower().endswith('.pdf'):
                # We only support PDF for AI batch extraction
                local_metas_map[pid] = {"error": "AI Extraction only supports PDF files."}
                continue
                
            local_meta = {
                "title": None, "authors": [], "year": None, "doi": None,
                "journal": None, "volume": None, "issue": None, "pages": None,
                "publisher": None, "type": "Other", "verification_status": "not_found",
                "extraction_layers": [],
            }
            local_metas_map[pid] = local_meta
            
            file_bytes = await f.read()
            fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
            tmp_paths_map[pid] = tmp_path
            with os.fdopen(fd, 'wb') as fout:
                fout.write(file_bytes)
                
            # Extract text (first 3 pages based on user feedback)
            try:
                reader = PdfReader(tmp_path)
                pages_text = []
                for i, page in enumerate(reader.pages):
                    if i >= 3: break
                    text = page.extract_text()
                    if text: pages_text.append(text)
                
                doc_text = "\n\n".join(pages_text)
                if doc_text.strip():
                    texts_for_ai.append((pid, doc_text))
            except Exception as e:
                logger.warning(f"Failed to read PDF {pid} for batch extraction: {e}")
                
        if not texts_for_ai:
            final_output = []
            for pid, meta in local_metas_map.items():
                if "error" in meta:
                    final_output.append({"id": pid, "result": {"error": meta["error"]}})
                else:
                    final_output.append({"id": pid, "result": {"error": "No readable text found in PDF."}})
            return final_output
            
        # Call batch AI
        ai_results = await extract_metadata_batch_with_ai(texts_for_ai)
        
        # Gather all DOIs
        dois_to_fetch = [res["doi"] for res in ai_results if res.get("doi")]
        from references.api_batch import fetch_crossref_batch
        
        crossref_records = await fetch_crossref_batch(dois_to_fetch)
        
        # Convert MetadataRecord dataclass to dict matching the old schema
        def record_to_dict(rec) -> dict:
            return {
                "title": rec.title,
                "authors": rec.authors,
                "year": rec.year,
                "doi": rec.doi,
                "journal": rec.journal,
                "source": rec.journal,
                "url": rec.url,
                "volume": rec.volume,
                "issue": rec.issue,
                "pages": rec.pages,
                "publisher": rec.publisher,
                "type": rec.type,
            }
            
        crossref_map = {rec.doi: record_to_dict(rec) for rec in crossref_records if rec and rec.doi}
        
        # Process validation concurrently for the pubmed fallbacks + local logic
        async def process_one(ai_res):
            pid = str(ai_res.get("id")) if ai_res.get("id") else None
            candidate_doi = ai_res.get("doi")
            if not pid or pid not in local_metas_map:
                return None
                
            local_meta = local_metas_map[pid]
            tmp_path = tmp_paths_map[pid]
            verified = False
            
            # 1. Try API Validation if a DOI was found
            if candidate_doi:
                # Crossref first (fast from batch)
                crossref_data = crossref_map.get(candidate_doi)
                if crossref_data and _validate_api_result(local_meta, crossref_data, tmp_path):
                    _merge(local_meta, crossref_data, overwrite=True)
                    local_meta["verification_status"] = "verified_crossref"
                    if "ai_rescue" not in local_meta.get("extraction_layers", []):
                        local_meta.setdefault("extraction_layers", []).append("ai_rescue")
                    verified = True
                
                # Fallback to Pubmed if Crossref failed
                if not verified:
                    def do_pubmed_lookup():
                        pubmed = pubmed_lookup(candidate_doi)
                        if pubmed and _validate_api_result(local_meta, pubmed, tmp_path):
                            _merge(local_meta, pubmed, overwrite=True)
                            local_meta["verification_status"] = "verified_pubmed"
                            if "ai_rescue" not in local_meta.get("extraction_layers", []):
                                local_meta.setdefault("extraction_layers", []).append("ai_rescue")
                            return True
                        return False
                    verified = await asyncio.to_thread(do_pubmed_lookup)
            
            # 2. AI Full Metadata Fallback - If no DOI or API validation failed
            if not verified:
                from references.metadata import strict_ai_verify_against_pdf
                
                if strict_ai_verify_against_pdf(ai_res, tmp_path):
                    for k in ["title", "authors", "year", "source", "journal", "volume", "issue", "pages", "publisher", "type"]:
                        if ai_res.get(k):
                            local_meta[k] = ai_res[k]
                            
                    if not local_meta.get("source") and ai_res.get("journal"):
                        local_meta["source"] = ai_res["journal"]
                        
                    local_meta["verification_status"] = "verified_ai_strict_scan"
                    if "ai_full_extract" not in local_meta.get("extraction_layers", []):
                        local_meta.setdefault("extraction_layers", []).append("ai_full_extract")
                    verified = True
            
            if verified:
                return pid, format_reference(local_meta, style)
            else:
                return pid, {"error": "AI failed identity verification against the PDF."}

        tasks = [process_one(res) for res in ai_results]
        processed_results = await asyncio.gather(*tasks)
        
        final_output = []
        for res in processed_results:
            if res:
                pid, data = res
                final_output.append({"id": pid, "result": data})
                
        return final_output

    finally:
        for p in tmp_paths_map.values():
            if os.path.exists(p):
                try: os.unlink(p)
                except: pass


@router.post("/api/retry-ai-doi-batch")
async def retry_ai_doi_batch(
    files: list[UploadFile] = File(...),
    ids: list[str] = Form(...),
    metadatas: list[str] = Form(...),
    style: str = Form("harvard")
):
    """Fallback endpoint to process multiple AI DOI extraction retries in a single batch."""
    import tempfile
    import os
    import asyncio
    from pypdf import PdfReader
    from references.ai_extractor import extract_metadata_batch_with_ai
    from references.metadata import crossref_lookup, pubmed_lookup, _validate_api_result, _merge

    if not len(files) == len(ids) == len(metadatas):
        raise HTTPException(status_code=400, detail="Mismatched input lists.")

    texts_for_ai = []
    local_metas_map = {}
    tmp_paths_map = {}
    
    try:
        # Save files and extract first 2 pages
        for f, pid, meta_str in zip(files, ids, metadatas):
            if not f.filename.lower().endswith('.pdf'):
                continue
                
            local_meta = json.loads(meta_str)
            local_metas_map[pid] = local_meta
            
            file_bytes = await f.read()
            fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
            tmp_paths_map[pid] = tmp_path
            with os.fdopen(fd, 'wb') as fout:
                fout.write(file_bytes)
                
            # Extract text
            try:
                reader = PdfReader(tmp_path)
                pages_text = []
                for i, page in enumerate(reader.pages):
                    if i >= 2: break
                    text = page.extract_text()
                    if text: pages_text.append(text)
                
                doc_text = "\n\n".join(pages_text)
                if doc_text.strip():
                    texts_for_ai.append((pid, doc_text))
            except Exception as e:
                logger.warning(f"Failed to read PDF {pid} for batch extraction: {e}")
                
        if not texts_for_ai:
            raise HTTPException(status_code=400, detail="No readable text found in provided PDFs.")
            
        # Call batch AI
        ai_results = await extract_metadata_batch_with_ai(texts_for_ai)
        
        # Gather all DOIs
        dois_to_fetch = [res["doi"] for res in ai_results if res.get("doi")]
        from references.api_batch import fetch_crossref_batch
        
        crossref_records = await fetch_crossref_batch(dois_to_fetch)
        
        # Convert MetadataRecord dataclass to dict matching the old schema
        def record_to_dict(rec) -> dict:
            return {
                "title": rec.title,
                "authors": rec.authors,
                "year": rec.year,
                "doi": rec.doi,
                "journal": rec.journal,
                "source": rec.journal,
                "url": rec.url,
                "volume": rec.volume,
                "issue": rec.issue,
                "pages": rec.pages,
                "publisher": rec.publisher,
                "type": rec.type,
            }
            
        crossref_map = {rec.doi: record_to_dict(rec) for rec in crossref_records if rec and rec.doi}
        
        # Process validation concurrently for the pubmed fallbacks + local logic
        async def process_one(ai_res):
            pid = str(ai_res.get("id")) if ai_res.get("id") else None
            candidate_doi = ai_res.get("doi")
            if not pid or pid not in local_metas_map:
                return None
                
            local_meta = local_metas_map[pid]
            tmp_path = tmp_paths_map[pid]
            verified = False
            
            # 1. Try API Validation if a DOI was found
            if candidate_doi:
                # Crossref first (fast from batch)
                crossref_data = crossref_map.get(candidate_doi)
                if crossref_data and _validate_api_result(local_meta, crossref_data, tmp_path):
                    _merge(local_meta, crossref_data, overwrite=True)
                    local_meta["verification_status"] = "verified_crossref"
                    if "ai_rescue" not in local_meta.get("extraction_layers", []):
                        local_meta.setdefault("extraction_layers", []).append("ai_rescue")
                    verified = True
                
                # Fallback to Pubmed if Crossref failed
                if not verified:
                    def do_pubmed_lookup():
                        pubmed = pubmed_lookup(candidate_doi)
                        if pubmed and _validate_api_result(local_meta, pubmed, tmp_path):
                            _merge(local_meta, pubmed, overwrite=True)
                            local_meta["verification_status"] = "verified_pubmed"
                            if "ai_rescue" not in local_meta.get("extraction_layers", []):
                                local_meta.setdefault("extraction_layers", []).append("ai_rescue")
                            return True
                        return False
                    verified = await asyncio.to_thread(do_pubmed_lookup)
            
            # 2. AI Full Metadata Fallback - If no DOI or API validation failed
            if not verified:
                from references.metadata import strict_ai_verify_against_pdf
                
                if strict_ai_verify_against_pdf(ai_res, tmp_path):
                    for k in ["title", "authors", "year", "source", "journal", "volume", "issue", "pages", "publisher", "type"]:
                        if ai_res.get(k):
                            local_meta[k] = ai_res[k]
                            
                    if not local_meta.get("source") and ai_res.get("journal"):
                        local_meta["source"] = ai_res["journal"]
                        
                    local_meta["verification_status"] = "verified_ai_strict_scan"
                    if "ai_full_extract" not in local_meta.get("extraction_layers", []):
                        local_meta.setdefault("extraction_layers", []).append("ai_full_extract")
                    verified = True
            
            if verified:
                return pid, format_reference(local_meta, style)
            else:
                return pid, {"error": "AI failed identity verification against the PDF."}

        tasks = [process_one(res) for res in ai_results]
        processed_results = await asyncio.gather(*tasks)
        
        final_output = []
        for res in processed_results:
            if res:
                pid, data = res
                final_output.append({"id": pid, "result": data})
                
        return final_output

    finally:
        for p in tmp_paths_map.values():
            if os.path.exists(p):
                try: os.unlink(p)
                except: pass


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
    Streams SSE events as each reference is processed so the UI updates incrementally.
    """
    async def _stream():
        def event(stage: str, message: str, data=None):
            payload = {"stage": stage, "message": message}
            if data is not None:
                payload["data"] = data
            return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        total = len(req.references)
        yield event("start", f"Processing {total} reference{'s' if total != 1 else ''}...")

        api_count = 0
        regex_count = 0
        queue = asyncio.Queue()
        tasks = []

        async def worker(i, ref, client):
            """Process a single reference using the async parser with TokenBucket rate limiting."""
            try:
                from references.parser import parse_raw_reference_async
                metadata = await parse_raw_reference_async(ref, client=client)
                corrections = metadata.pop("corrections", [])
                api_verified = metadata.pop("api_verified", False)
                api_source = metadata.pop("api_source", None)

                result = format_reference(metadata, req.style)
                result["original"] = ref
                result["corrections"] = corrections
                result["api_verified"] = api_verified
                result["api_source"] = api_source
                await queue.put((i, result, api_verified))
            except Exception as e:
                await queue.put((i, {"original": ref, "error": str(e)}, False))

        import httpx
        try:
            async with httpx.AsyncClient(timeout=30) as shared_client:
                # Launch all workers concurrently (semaphore limits actual parallelism)
                tasks = [asyncio.create_task(worker(i, ref, shared_client)) for i, ref in enumerate(req.references)]

                # Consume results as they complete and stream SSE events
                completed = 0
                while completed < total:
                    i, result, verified = await queue.get()
                    completed += 1
                    if verified:
                        api_count += 1
                    elif "error" not in result:
                        regex_count += 1

                    yield event("ref_result", f"Processed {completed}/{total}.", data={
                        "index": i,
                        "result": result,
                    })

                # Ensure all tasks finished cleanly
                await asyncio.gather(*tasks)

            yield event("complete", "All references processed.", data={
                "summary": {
                    "total": total,
                    "api_verified": api_count,
                    "regex_only": regex_count,
                }
            })
        except asyncio.CancelledError:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            return

    return StreamingResponse(_stream(), media_type="text/event-stream")



@router.post("/api/match-references")
async def match_references_endpoint(
    pdf_files: List[UploadFile] = File(...),
    reference_text: Optional[str] = Form(None),
    reference_file: Optional[UploadFile] = File(None),
):
    """
    Match a reference list against uploaded PDFs.
    Streams SSE progress events, then a final 'complete' event with results.
    """
    async def _stream():
        def event(stage: str, message: str, data=None):
            payload = {"stage": stage, "message": message}
            if data is not None:
                payload["data"] = data
            return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        try:
            # ── 1. Obtain reference list text ──
            yield event("parsing", "Extracting reference list text…")
            ref_list_text = ""
            if reference_text and reference_text.strip():
                ref_list_text = reference_text.strip()
            elif reference_file and reference_file.filename:
                ref_bytes = await reference_file.read()
                magic = ref_bytes[:8]
                if magic[:4] == b'%PDF':
                    import io
                    from PyPDF2 import PdfReader
                    reader = PdfReader(io.BytesIO(ref_bytes))
                    for page in reader.pages:
                        ref_list_text += (page.extract_text() or "") + "\n"
                elif magic[:2] == b'PK':
                    from docx import Document as DocxDocument
                    import io
                    doc = DocxDocument(io.BytesIO(ref_bytes))
                    ref_list_text = "\n".join(p.text for p in doc.paragraphs)
                elif magic[:4] == b'\xd0\xcf\x11\xe0':
                    ref_list_text = extract_doc_text(ref_bytes) or ""
                else:
                    # try as plain text
                    ref_list_text = ref_bytes.decode("utf-8", errors="replace")

            if not ref_list_text.strip():
                yield event("error", "No reference list provided. Paste text or upload a file.")
                return

            # ── 2. Split into individual references ──
            yield event("splitting", "Splitting reference list into individual entries…")
            raw_refs = parse_reference_list(ref_list_text)
            if not raw_refs:
                yield event("error", "Could not detect any references in the provided text.")
                return
            yield event("splitting", f"Found {len(raw_refs)} references.")
            await asyncio.sleep(0)  # yield control

            # ── 3. Parse each reference into metadata (regex-only, no AI) ──
            yield event("parsing_refs", f"Parsing metadata from {len(raw_refs)} references…")
            ref_metadatas = []
            for i, raw in enumerate(raw_refs):
                try:
                    meta = parse_raw_reference_fast(raw)
                    ref_metadatas.append(meta)
                except Exception as e:
                    ref_metadatas.append({"_original": raw, "title": None, "authors": None, "year": None, "doi": None})
                    print(f"[Matcher] Failed to parse ref #{i+1}: {e}")
            yield event("parsing_refs", f"Parsed {len(raw_refs)}/{len(raw_refs)} references.")
            await asyncio.sleep(0)

            # ── 4. Extract metadata from each PDF (fast regex-only, no AI) ──
            total_pdfs = len(pdf_files)
            yield event("extracting_pdfs", f"Processing {total_pdfs} PDF files…")
            pdf_metadatas = []
            for i, pf in enumerate(pdf_files):
                fname = pf.filename or f"file_{i+1}.pdf"
                try:
                    pdf_bytes = await pf.read()
                    magic = pdf_bytes[:8]
                    if magic[:4] == b'%PDF':
                        meta = extract_pdf_metadata_fast(pdf_bytes)
                    elif magic[:2] == b'PK':
                        meta = extract_docx_metadata(pdf_bytes)
                    else:
                        meta = {"title": fname.rsplit('.', 1)[0], "authors": None, "year": None, "doi": None}
                    meta["_filename"] = fname
                    pdf_metadatas.append(meta)
                except Exception as e:
                    print(f"[Matcher] Failed to extract PDF {fname}: {e}")
                    pdf_metadatas.append({"_filename": fname, "title": fname.rsplit('.', 1)[0], "authors": None, "year": None, "doi": None})
            yield event("extracting_pdfs", f"Processed {total_pdfs}/{total_pdfs} PDFs.")
            await asyncio.sleep(0)

            # ── 5. Run matching ──
            yield event("matching", "Matching references against PDFs…")
            results = match_references_to_pdfs(ref_metadatas, pdf_metadatas)
            results["total_references"] = len(raw_refs)
            results["total_pdfs"] = total_pdfs

            yield event("complete", "Matching complete.", data=results)

        except Exception as e:
            yield event("error", f"Unexpected error: {type(e).__name__}: {e}")

    return StreamingResponse(_stream(), media_type="text/event-stream")


@router.post("/api/verify-reference-list")
async def verify_reference_list(request: Request):
    """
    Verify a list of references for metadata accuracy and formatting correctness.
    Accepts JSON body: { "references_text": "...", "style": "harvard"|"apa"|"vancouver"|null }
    If style is null/missing, auto-detects from the references.
    Streams SSE progress events.
    """
    body = await request.json()
    references_text = body.get("references_text", "").strip()
    user_style = body.get("style")  # null means auto-detect

    if not references_text:
        raise HTTPException(status_code=400, detail="No references text provided.")

    async def _stream():
        def event(stage: str, message: str, data=None):
            payload = {"stage": stage, "message": message}
            if data is not None:
                payload["data"] = data
            return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        tasks = []
        try:
            # ── 1. Split into individual references ──
            print(f"\n{'='*60}")
            print(f"[RefVerifier] Starting reference list verification")
            print(f"[RefVerifier] Input length: {len(references_text)} chars")
            print(f"{'='*60}")

            yield event("splitting", "Splitting reference list into individual entries…")
            raw_refs = parse_reference_list(references_text)
            if not raw_refs:
                print(f"[RefVerifier] ERROR: Could not split references from input")
                yield event("error", "Could not detect any references in the provided text.")
                return
            print(f"[RefVerifier] Split into {len(raw_refs)} references:")
            for idx, ref in enumerate(raw_refs):
                print(f"  [{idx+1}] {ref[:80]}{'…' if len(ref) > 80 else ''}")
            yield event("splitting", f"Found {len(raw_refs)} references.")
            await asyncio.sleep(0)

            # ── 2. Auto-detect style (if not specified) ──
            if user_style and user_style in ("harvard", "apa", "vancouver"):
                style = user_style
                style_info = {"style": style, "confidence": 100, "auto_detected": False, "evidence": ["User-selected"], "all_scores": {style: 100}}
                print(f"[RefVerifier] Style: {style.upper()} (user-selected)")
                yield event("detecting", f"Using user-selected style: {style.upper()}")
            else:
                yield event("detecting", "Auto-detecting citation style…")
                detection = detect_style(raw_refs)
                style = detection["style"]
                if style not in ("harvard", "apa", "vancouver"):
                    style = "apa"
                confidence = detection.get("confidence", 0)
                style_info = {
                    "style": style,
                    "confidence": confidence,
                    "auto_detected": True,
                    "evidence": detection.get("evidence", []),
                    "all_scores": detection.get("all_scores", {}),
                }
                print(f"[RefVerifier] Style: {style.upper()} (auto-detected, {confidence}% confidence)")
                print(f"[RefVerifier] Evidence: {detection.get('evidence', [])}")
                print(f"[RefVerifier] All scores: {detection.get('all_scores', {})}")
                yield event("detecting", f"Detected style: {style.upper()} ({confidence}% confidence)")

            # Send style_info immediately so frontend can display it
            yield event("style_detected", "Style determined.", data={"style_info": style_info})
            await asyncio.sleep(0)

            # ── 3. Verify each reference concurrently (stream results as they complete) ──
            total = len(raw_refs)
            verified_count = 0
            issues_count = 0
            unverifiable_count = 0
            queue = asyncio.Queue()
            api_semaphore = asyncio.Semaphore(3)

            async def verify_worker(i, ref):
                """Verify a single reference, gated by the global API semaphore."""
                try:
                    async with api_semaphore:
                        print(f"\n{'─'*50}")
                        print(f"[RefVerifier] [{i+1}/{total}] Verifying:")
                        print(f"  Input: {ref[:120]}{'…' if len(ref) > 120 else ''}")

                        ref_result = await asyncio.to_thread(verify_single_reference, ref, style)

                        # Log result details
                        status = ref_result.get("overall_status", "unverifiable")
                        print(f"  DOI: {ref_result.get('doi', 'none')}")
                        print(f"  API source: {ref_result.get('api_source', 'none')}")
                        print(f"  Status: {status}")
                        print(f"  Accuracy: {ref_result.get('accuracy_score', 0):.0%}")
                        meta_issues = [mi for mi in ref_result.get('metadata_issues', []) if mi.get('status') != 'correct']
                        if meta_issues:
                            print(f"  Metadata issues:")
                            for mi in meta_issues:
                                print(f"    - {mi['field']}: {mi['status']} (user: '{mi.get('user_value', '')}' \u2192 correct: '{mi.get('correct_value', '')}')")
                        fmt_issues = ref_result.get('formatting_issues', [])
                        if fmt_issues:
                            print(f"  Formatting issues:")
                            for fi in fmt_issues:
                                print(f"    - {fi['issue']}: {fi['detail']}")

                        await queue.put((i, ref_result))
                except Exception as e:
                    print(f"[RefVerifier] Worker {i+1} crashed: {e}")
                    import traceback; traceback.print_exc()
                    await queue.put((i, {"overall_status": "unverifiable", "error": str(e)}))

            # Launch workers with staggered starts to prevent API burst
            tasks = []
            for i, ref in enumerate(raw_refs):
                tasks.append(asyncio.create_task(verify_worker(i, ref)))
                # Small delay between launches to spread API requests over time
                if i < total - 1:
                    await asyncio.sleep(0.35)

            # Consume results as they complete and stream SSE events
            completed = 0
            while completed < total:
                i, ref_result = await queue.get()
                completed += 1

                status = ref_result.get("overall_status", "unverifiable")
                if status == "verified":
                    verified_count += 1
                elif status == "issues_found":
                    issues_count += 1
                else:
                    unverifiable_count += 1

                yield event("ref_result", f"Verified {completed}/{total}: {status}", data={
                    "index": i,
                    "result": ref_result,
                })

            # Ensure all tasks finished cleanly
            await asyncio.gather(*tasks)

            # ── 4. Summary ──
            summary_text = f"{verified_count} verified, {issues_count} with issues, {unverifiable_count} unverifiable"
            print(f"\n{'='*60}")
            print(f"[RefVerifier] DONE — {summary_text}")
            print(f"{'='*60}\n")

            yield event("complete", "Verification complete.", data={
                "summary": {
                    "total": total,
                    "verified": verified_count,
                    "issues_found": issues_count,
                    "unverifiable": unverifiable_count,
                },
            })

        except asyncio.CancelledError:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            print(f"[RefVerifier] Cancelled by client.")
            return
        except Exception as e:
            print(f"[RefVerifier] EXCEPTION: {type(e).__name__}: {e}")
            import traceback; traceback.print_exc()
            yield event("error", f"Unexpected error: {type(e).__name__}: {e}")

    return StreamingResponse(_stream(), media_type="text/event-stream")


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
