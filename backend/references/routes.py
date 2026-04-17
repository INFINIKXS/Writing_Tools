"""
Reference extraction and formatting API routes.
"""
import re
import json
import asyncio
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import StreamingResponse

from utils.text_extraction import extract_doc_text
from references.metadata import extract_pdf_metadata, extract_docx_metadata
from references.parser import FormatRequest, parse_raw_reference
from citations.formatting import format_reference
from references.matcher import parse_reference_list, match_references_to_pdfs, extract_pdf_metadata_fast, parse_raw_reference_fast
from references.ref_list_verifier import detect_style, verify_single_reference
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

            # ── 3. Verify each reference (stream results one by one) ──
            total = len(raw_refs)
            verified_count = 0
            issues_count = 0
            unverifiable_count = 0

            for i, ref in enumerate(raw_refs):
                print(f"\n{'─'*50}")
                print(f"[RefVerifier] [{i+1}/{total}] Verifying:")
                print(f"  Input: {ref[:120]}{'…' if len(ref) > 120 else ''}")

                yield event("verifying", f"Verifying reference {i + 1}/{total}…")

                ref_result = await asyncio.to_thread(verify_single_reference, ref, style)

                status = ref_result.get("overall_status", "unverifiable")
                if status == "verified":
                    verified_count += 1
                elif status == "issues_found":
                    issues_count += 1
                else:
                    unverifiable_count += 1

                # Log result details
                print(f"  DOI: {ref_result.get('doi', 'none')}")
                print(f"  API source: {ref_result.get('api_source', 'none')}")
                print(f"  Status: {status}")
                print(f"  Accuracy: {ref_result.get('accuracy_score', 0):.0%}")
                meta_issues = [i for i in ref_result.get('metadata_issues', []) if i.get('status') != 'correct']
                if meta_issues:
                    print(f"  Metadata issues:")
                    for mi in meta_issues:
                        print(f"    - {mi['field']}: {mi['status']} (user: '{mi.get('user_value', '')}' → correct: '{mi.get('correct_value', '')}')")
                fmt_issues = ref_result.get('formatting_issues', [])
                if fmt_issues:
                    print(f"  Formatting issues:")
                    for fi in fmt_issues:
                        print(f"    - {fi['issue']}: {fi['detail']}")

                # Stream this result immediately to frontend
                yield event("ref_result", f"Reference {i + 1}/{total} verified: {status}", data={
                    "index": i,
                    "result": ref_result,
                })
                await asyncio.sleep(0)

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
