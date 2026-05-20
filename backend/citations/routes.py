"""
Citation verification API route: POST /api/verify (SSE streaming).
Uses Python regex for in-text citation extraction and LLM-powered
reference list splitting (with 30+ pattern regex fallback).
"""
import json
import asyncio
import re

from fastapi import APIRouter, UploadFile, File, HTTPException
from starlette.responses import StreamingResponse

from utils.text_extraction import extract_pdf_text, extract_docx_text, extract_doc_text
from utils.text_utils import count_references_and_citations
from citations.extraction import extract_reference_section, extract_citations_regex, detect_document_consistency_issues
from citations.deduplication import deduplicate_references
from citations.verification import verify_matches_with_string_search, extract_verbatim_references, detect_irregularities_deterministically, extract_references_from_text, validate_extracted_references
from references.ref_list_verifier import segment_verifier_text_via_llm
from citations.formatting import apply_italic_formatting
from citations.ordering import apply_reference_ordering

router = APIRouter()


@router.post("/api/verify")
async def verify_citations(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(('.pdf', '.docx', '.doc')):
        raise HTTPException(status_code=400, detail="Unsupported file type. Please upload PDF, DOCX, or DOC.")

    file_bytes = await file.read()

    async def event_stream():

        # Stage 1: Detect file format
        yield f"data: {json.dumps({'stage': 'parsing', 'message': 'Detecting file format...'})}\n\n"
        await asyncio.sleep(0.1)
        
        magic = file_bytes[:8]
        try:
            if magic[:4] == b'%PDF':
                yield f"data: {json.dumps({'stage': 'parsing', 'message': 'Reading PDF document...'})}\n\n"
                await asyncio.sleep(0.1)
                full_text = extract_pdf_text(file_bytes)
            elif magic[:2] == b'PK':
                yield f"data: {json.dumps({'stage': 'parsing', 'message': 'Reading Word document (.docx)...'})}\n\n"
                await asyncio.sleep(0.1)
                full_text = extract_docx_text(file_bytes)
            elif magic[:4] == b'\xd0\xcf\x11\xe0':
                yield f"data: {json.dumps({'stage': 'parsing', 'message': 'Reading legacy Word document (.doc)...'})}\n\n"
                await asyncio.sleep(0.1)
                full_text = extract_doc_text(file_bytes)
            else:
                yield f"data: {json.dumps({'stage': 'error', 'message': 'Unrecognized file format.'})}\n\n"
                return
        except Exception as e:
            yield f"data: {json.dumps({'stage': 'error', 'message': f'Failed to read file: {str(e)}'})}\n\n"
            return

        if not full_text:
            yield f"data: {json.dumps({'stage': 'error', 'message': 'No text could be extracted from the file.'})}\n\n"
            return

        # Compress wide spacing/justified text formatting from PDF extraction 
        # (This collapses multiple contiguous spaces to 1, preserving newlines)
        full_text = re.sub(r' {2,}', ' ', full_text)

        word_count = len(full_text.split())
        yield f"data: {json.dumps({'stage': 'extracted', 'message': f'Extracted {word_count:,} words from document'})}\n\n"
        await asyncio.sleep(0.1)

        # Stage 2: Python citation extraction (deterministic — no hallucination)
        yield f"data: {json.dumps({'stage': 'scanning', 'message': 'Python regex scanning for in-text citations...'})}\n\n"
        await asyncio.sleep(0.1)

        body_text, ref_section_text = extract_reference_section(full_text)
        python_citations = extract_citations_regex(body_text)

        py_count = len(python_citations)
        type_counts = {}
        for c in python_citations:
            t = c["type"]
            type_counts[t] = type_counts.get(t, 0) + 1
        type_summary = ", ".join(f"{v} {k}" for k, v in type_counts.items())
        yield f"data: {json.dumps({'stage': 'scanning', 'message': f'Found {py_count} citations via regex ({type_summary})'})}\n\n"
        await asyncio.sleep(0.1)

        # Stage 3: Extract references from document text using LLM + regex fallback
        yield f"data: {json.dumps({'stage': 'analyzing', 'message': 'Sending document to AI for reference extraction...'})}\n\n"
        await asyncio.sleep(0.1)

        references = await segment_verifier_text_via_llm(full_text, is_full_document=True)

        llm_count = len(references)
        yield f"data: {json.dumps({'stage': 'analyzing', 'message': f'AI extracted {llm_count} references from document'})}\n\n"
        await asyncio.sleep(0.1)

        # Deduplicate
        unique_refs, dup_groups, dup_flags = deduplicate_references(references)
        references = unique_refs

        ref_count = len(references)

        # Run quality validation on extracted references
        ref_validation = validate_extracted_references(references)
        ref_health = ref_validation["health"]
        health_msg = f'Found {ref_count} references'
        if ref_health["flagged"] > 0:
            health_msg += f' ({ref_health["flagged"]} flagged for review)'
        yield f"data: {json.dumps({'stage': 'analyzing', 'message': health_msg})}\n\n"
        await asyncio.sleep(0.1)

        # Stage 4: Build analysis result
        try:
            yield f"data: {json.dumps({'stage': 'processing', 'message': 'Building analysis...'})}\n\n"
            await asyncio.sleep(0.1)

            analysis = {
                "in_text_citations": [c["text"] for c in python_citations],
                "references": references,
                "missing_references_for_citations": [],
                "unused_references": [],
                "summary": "",
            }

            if dup_groups:
                analysis["duplicate_reference_groups"] = dup_groups

            # Attach reference quality validation
            analysis["reference_validation"] = ref_validation

            analysis = count_references_and_citations(analysis)

            # Python citation metadata
            analysis["python_citations"] = [c["text"] for c in python_citations]
            analysis["python_citation_types"] = {c["text"]: c["type"] for c in python_citations}
            analysis["python_formatting_warnings"] = {c["text"]: c["irregularities"] for c in python_citations if c.get("irregularities")}

            # Deterministic irregularity detection
            analysis["irregularities"] = detect_irregularities_deterministically(
                python_citations,
                analysis.get("references", [])
            )

            # Document-level consistency warnings (and/& mixing, et al. comma inconsistency, etc.)
            analysis["consistency_warnings"] = detect_document_consistency_issues(python_citations)

            num_cit = analysis.get("num_unique_citations", 0)
            num_ref = analysis.get("num_references", 0)
            yield f"data: {json.dumps({'stage': 'processing', 'message': f'Processed {num_cit} citations, {num_ref} references'})}\n\n"
            await asyncio.sleep(0.1)

            # Stage 5: String verification
            verify_msg = f"Running string verification on {num_ref} references..."
            yield f"data: {json.dumps({'stage': 'verifying', 'message': verify_msg})}\n\n"
            await asyncio.sleep(0.1)

            verification = verify_matches_with_string_search(
                analysis.get("in_text_citations", []),
                analysis.get("references", []),
            )
            analysis["string_verification"] = verification

            # Populate missing/unused from string verification
            analysis["missing_references_for_citations"] = verification.get("unmatched_citations", [])
            analysis["unused_references"] = verification.get("unmatched_references", [])

            # Generate summary
            matched = len(verification.get("confirmed_matches", []))
            unmatched_cit = len(verification.get("unmatched_citations", []))
            unmatched_ref = len(verification.get("unmatched_references", []))
            disambig_warnings = len(verification.get("disambiguation_warnings", []))
            summary_parts = [f"{matched} citations matched to references"]
            if unmatched_cit:
                summary_parts.append(f"{unmatched_cit} citations without matching references")
            if unmatched_ref:
                summary_parts.append(f"{unmatched_ref} references not cited in text")
            if disambig_warnings:
                summary_parts.append(f"{disambig_warnings} author-year disambiguation issue(s)")
            analysis["summary"] = ". ".join(summary_parts) + "."

            # Stage 6: Extract verbatim references from source document
            yield f"data: {json.dumps({'stage': 'extracting', 'message': 'Extracting verbatim references from source document...'})}\n\n"
            await asyncio.sleep(0.1)

            verbatim_map = extract_verbatim_references(full_text, analysis.get("references", []))
            for key in verbatim_map:
                plain = verbatim_map[key].get("verbatim", key)
                verbatim_map[key]["verbatim_html"] = apply_italic_formatting(plain)
            analysis["verbatim_references"] = verbatim_map

            # Stage 7: Detect citation style and reorder references
            ordering_result = apply_reference_ordering(
                body_text,
                analysis.get("references", []),
                verbatim_map,
            )
            analysis["detected_style"] = ordering_result["style"]
            analysis["style_detection_confidence"] = ordering_result.get("style_detection_confidence", 0)
            analysis["style_detection_evidence"] = ordering_result.get("style_detection_evidence", [])
            analysis["style_all_scores"] = ordering_result.get("style_all_scores", {})
            analysis["ordered_references"] = ordering_result["ordered_refs"]

            yield f"data: {json.dumps({'stage': 'complete', 'message': 'Analysis complete!', 'data': analysis})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'stage': 'error', 'message': f'Unexpected error: {str(e)}'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

