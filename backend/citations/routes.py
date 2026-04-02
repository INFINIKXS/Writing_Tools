"""
Citation verification API route: POST /api/verify (SSE streaming).
"""
import json
import asyncio
import random
import re

from google import genai
from fastapi import APIRouter, UploadFile, File, HTTPException
from starlette.responses import StreamingResponse

from core.config import KEY_MANAGER_AVAILABLE, get_api_key_manager
from core.gemini import get_client, MAX_RETRIES, RETRY_BASE_DELAY
from utils.text_extraction import extract_pdf_text, extract_docx_text, extract_doc_text
from utils.text_utils import count_references_and_citations
from citations.extraction import extract_reference_section, extract_citations_regex, detect_document_consistency_issues
from citations.deduplication import deduplicate_references
from citations.verification import verify_matches_with_string_search, cross_validate, extract_verbatim_references, detect_irregularities_deterministically
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

        # Stage 3: AI Semantic Analysis (receives pre-extracted data — verify only)
        yield f"data: {json.dumps({'stage': 'analyzing', 'message': 'Sending to Gemini AI for semantic matching...'})}\n\n"
        await asyncio.sleep(0.1)

        try:
            model_name = 'gemini-3-flash-preview'
            client = get_client(model=model_name)
            key_manager = get_api_key_manager() if KEY_MANAGER_AVAILABLE else None

            citations_list = json.dumps([c["text"] for c in python_citations], indent=2)

            prompt = f"""You are a citation verification assistant. Python has already extracted the following in-text citations from a document using regex. Your PRIMARY source of truth is this pre-extracted list.

PRE-EXTRACTED IN-TEXT CITATIONS (found by Python regex — these are confirmed):
{citations_list}

DOCUMENT TEXT (for reference matching, irregularity detection, AND independent scanning):
{full_text[:1000000]}

Your tasks:
1. Extract and list all references from the reference section of the document (typically at the end, under headings like 'References', 'Bibliography', etc.). 
   -> CRITICAL: Ensure EACH unique reference is a separate string in the array. If the source text merged multiple references onto the same line (e.g., missing a newline between them), you MUST split them into distinct, separate array items. A new reference typically begins with authors' surnames and a year.
2. Match each pre-extracted citation to its corresponding reference.
3. Identify mismatches:
   - Citations without a matching reference (missing references).
   - References without a corresponding citation (unused references).
4. INDEPENDENTLY scan the document for any in-text citations that Python may have MISSED. Report these separately as "ai_additional_citations". These are NOT confirmed — they are warnings for the user to review.

Output in strict JSON format only:
{{
    "in_text_citations": {citations_list},
    "references": ["ref1", "ref2", ...],
    "ai_additional_citations": ["any citations YOU found that are NOT in the pre-extracted list above"],
    "missing_references_for_citations": ["unmatched_citation1", ...],
    "unused_references": ["extra_ref1", ...],
    "summary": "Brief overview of issues found."
}}
"""

            yield f"data: {json.dumps({'stage': 'analyzing', 'message': 'Gemini is matching citations to references...'})}\n\n"
            
            last_retry_error = None
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    response = await asyncio.to_thread(
                        client.models.generate_content,
                        model=model_name,
                        contents=prompt,
                    )
                    # Track usage after successful call
                    if key_manager:
                        key_manager.increment_usage(model=model_name)
                    break
                except Exception as e:
                    error_str = str(e)
                    is_rate_limited = any(code in error_str for code in ['429', 'RESOURCE_EXHAUSTED'])
                    is_retryable = is_rate_limited or any(code in error_str for code in [
                        '503', 'UNAVAILABLE',
                        'SSL', 'ConnectionError', 'ConnectionReset', 'Timeout', 'timeout',
                        'ServiceUnavailable',
                    ])

                    # On rate limit, rotate to next key
                    if is_rate_limited and key_manager:
                        has_backup = key_manager.mark_exhausted(model=model_name)
                        if has_backup:
                            new_key = key_manager.get_current_key(model=model_name)
                            if new_key:
                                client = genai.Client(api_key=new_key)
                                yield f"data: {json.dumps({'stage': 'analyzing', 'message': f'Rate limited — rotated to next API key (attempt {attempt}/{MAX_RETRIES})'})}\n\n"

                    if is_retryable and attempt < MAX_RETRIES:
                        delay = RETRY_BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1)
                        yield f"data: {json.dumps({'stage': 'analyzing', 'message': f'API temporarily unavailable (attempt {attempt}/{MAX_RETRIES}). Retrying in {delay:.0f}s...'})}\n\n"
                        await asyncio.sleep(delay)
                        last_retry_error = e
                    else:
                        raise
        except Exception as e:
            yield f"data: {json.dumps({'stage': 'error', 'message': f'Gemini API error: {str(e)}'})}\n\n"
            return

        yield f"data: {json.dumps({'stage': 'processing', 'message': 'Parsing AI response...'})}\n\n"
        await asyncio.sleep(0.1)

        # Stage 4: Parse response and cross-validate
        try:
            output_text = response.text.strip()
            if output_text.startswith('```json'):
                output_text = output_text[7:].strip()
            if output_text.endswith('```'):
                output_text = output_text[:-3].strip()
            analysis = json.loads(output_text)

            # Post-process: Split merged references
            def split_merged_references(refs):
                split_refs = []
                split_pattern = re.compile(
                    r'(?:(?<=pdf)|(?<=html)|(?<=org)|(?<=\d)|(?<=/))[.]?\s+'
                    r'(?='
                    r'(?:(?:[A-Z][a-zA-Zà-öø-ÿ\'-]+|[a-z][a-z]+)[ \u00a0]+)*[A-Z][a-zA-Zà-öø-ÿ\'-]+'
                    r'\s*,\s*(?:[A-Z]\.|[A-Z][A-Z]?[A-Z]?(?=\s*,|\s+&|\s+and|\s+et))'
                    r'|\[\d+\]'
                    r'|\d+\.\s+[A-Z]'
                    r')'
                )
                for ref in refs:
                    parts = split_pattern.split(ref)
                    if len(parts) == 1:
                        split_refs.append(parts[0].strip())
                        continue
                    current_ref = parts[0]
                    for pt in parts[1:]:
                        ends_like_ref = bool(re.search(r'(\b\d{4}\b|https?://\S+|doi\.org/\S+|\d+\s*|p\.\s*\d+|pp\.\s*\d+[-–]\d+\.?)$', current_ref.strip()))
                        
                        starts_like_ref = bool(re.match(
                            r'^(?:(?:[A-Z][a-zA-Zà-öø-ÿ\'-]+|[a-z]{2,3})[ \u00a0]+)*[A-Z][a-zA-Zà-öø-ÿ\'-]+\s*,\s*[A-Z]\.'
                            r'|\[\d+\]'
                            r'|\d+\.\s+[A-Z]', pt))
                            
                        if ends_like_ref and starts_like_ref:
                            split_refs.append(current_ref.strip())
                            current_ref = pt
                        else:
                            current_ref += " " + pt
                    if current_ref.strip():
                        split_refs.append(current_ref.strip())
                return split_refs

            if "references" in analysis:
                analysis["references"] = split_merged_references(analysis["references"])
                unique_refs, dup_groups, dup_flags = deduplicate_references(analysis["references"])
                analysis["references"] = unique_refs
                if dup_groups:
                    analysis["duplicate_reference_groups"] = dup_groups

            analysis = count_references_and_citations(analysis)

            # Stage 5: Cross-validate Python vs AI
            yield f"data: {json.dumps({'stage': 'validating', 'message': 'Cross-validating Python extraction vs AI analysis...'})}\n\n"
            await asyncio.sleep(0.1)

            validation = cross_validate(
                python_citations,
                analysis.get("in_text_citations", []),
                analysis.get("references", [])
            )
            analysis["cross_validation"] = validation
            analysis["python_citations"] = [c["text"] for c in python_citations]
            analysis["python_citation_types"] = {c["text"]: c["type"] for c in python_citations}
            analysis["python_formatting_warnings"] = {c["text"]: c["irregularities"] for c in python_citations if c.get("irregularities")}

            # Deterministic irregularity detection (replaces AI-based guessing)
            analysis["irregularities"] = detect_irregularities_deterministically(
                python_citations,
                analysis.get("references", [])
            )

            # Document-level consistency warnings (and/& mixing, et al. comma inconsistency, etc.)
            analysis["consistency_warnings"] = detect_document_consistency_issues(python_citations)

            num_cit = analysis.get("num_unique_citations", 0)
            num_ref = analysis.get("num_references", 0)
            py_only = len(validation.get("python_only", []))
            ai_only = len(validation.get("ai_only_potential_hallucination", []))
            ai_additional = len(analysis.get("ai_additional_citations", []))
            validate_msg = f"Validated {num_cit} citations, {num_ref} references"
            if py_only:
                validate_msg += f" | {py_only} found by Python only"
            if ai_only:
                validate_msg += f" | {ai_only} AI-only (review needed)"
            if ai_additional:
                validate_msg += f" | {ai_additional} additional found by AI"
            yield f"data: {json.dumps({'stage': 'validating', 'message': validate_msg})}\n\n"
            await asyncio.sleep(0.1)

            # Stage 6: String verification
            verify_msg = f"Running string verification on {num_ref} references..."
            yield f"data: {json.dumps({'stage': 'verifying', 'message': verify_msg})}\n\n"
            await asyncio.sleep(0.1)

            verification = verify_matches_with_string_search(
                analysis.get("in_text_citations", []),
                analysis.get("references", []),
            )
            analysis["string_verification"] = verification

            # Stage 7: Extract verbatim references from source document
            yield f"data: {json.dumps({'stage': 'extracting', 'message': 'Extracting verbatim references from source document...'})}\n\n"
            await asyncio.sleep(0.1)

            verbatim_map = extract_verbatim_references(full_text, analysis.get("references", []))
            for key in verbatim_map:
                plain = verbatim_map[key].get("verbatim", key)
                verbatim_map[key]["verbatim_html"] = apply_italic_formatting(plain)
            analysis["verbatim_references"] = verbatim_map

            # Stage 8: Detect citation style and reorder references
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

        except json.JSONDecodeError as e:
            yield f"data: {json.dumps({'stage': 'error', 'message': f'Error parsing Gemini response: {str(e)}'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'stage': 'error', 'message': f'Unexpected error: {str(e)}'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
