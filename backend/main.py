import os
import io
import json
import re
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
from google import genai
from google.genai import types
from PyPDF2 import PdfReader
from docx import Document
import struct
import olefile
from dotenv import load_dotenv

from harvard_guide import HARVARD_GUIDE

# Load env variables
load_dotenv()

app = FastAPI(title="Writing Tools API")

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.environ.get("GOOGLE_API_KEY")

def get_client():
    if not API_KEY:
        raise HTTPException(status_code=500, detail="Google API Key not configured at GOOGLE_API_KEY in .env")
    return genai.Client(api_key=API_KEY)

def extract_pdf_text(file_bytes: bytes) -> str:
    text = ""
    with io.BytesIO(file_bytes) as f:
        reader = PdfReader(f)
        for page in reader.pages:
            text += page.extract_text() + "\n"
    return text

def extract_docx_text(file_bytes: bytes) -> str:
    with io.BytesIO(file_bytes) as f:
        doc = Document(f)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
    return text

def extract_doc_text(file_bytes: bytes) -> str:
    """Extract text from legacy .doc (Word 97-2003) files using olefile (pure Python)."""
    try:
        f = io.BytesIO(file_bytes)
        ole = olefile.OleFileIO(f)
        
        # The main text stream in .doc files is "WordDocument"
        # But the actual text content is in the "1Table" or "0Table" stream  
        # We'll read the WordDocument stream to get the raw text
        
        if ole.exists('WordDocument'):
            word_stream = ole.openstream('WordDocument').read()
        else:
            raise HTTPException(status_code=400, detail="This file does not appear to be a valid Word .doc file.")
        
        # Read the FIB (File Information Block) to locate text
        # Bytes 24-27 contain flags, bytes 0x01A2 onwards contain text positions
        # For simplicity, try to extract via the compound document text
        
        text_pieces = []
        
        # Method 1: Try to read from the data stream directly
        # The text in a .doc is stored as either ASCII or Unicode
        # We look at ccpText field in FIB at offset 0x004C (76)
        if len(word_stream) > 80:
            ccp_text = struct.unpack_from('<I', word_stream, 0x004C)[0]
            
            # Check if text is Unicode (bit 0 of flags at offset 0x000A)
            flags = struct.unpack_from('<H', word_stream, 0x000A)[0]
            is_complex = not (flags & 0x0004)  # fComplex flag
            
            if not is_complex and ccp_text > 0:
                # Simple file: text starts at offset 0x0200 (512)
                start = 0x0200
                if flags & 0x0100:  # Unicode
                    raw = word_stream[start:start + ccp_text * 2]
                    text_pieces.append(raw.decode('utf-16-le', errors='ignore'))
                else:
                    raw = word_stream[start:start + ccp_text]
                    text_pieces.append(raw.decode('cp1252', errors='ignore'))
        
        # Method 2: If Method 1 got nothing, try brute-force decoding 
        if not text_pieces or not ''.join(text_pieces).strip():
            # Try all text streams
            for stream_name in ['WordDocument']:
                data = ole.openstream(stream_name).read()
                # Skip the FIB header (first 512 bytes) and try to decode
                raw_text = data[512:]
                # Try UTF-16 first, then cp1252
                try:
                    decoded = raw_text.decode('utf-16-le', errors='ignore')
                    # Filter to printable characters
                    cleaned = ''.join(c if c.isprintable() or c in '\n\r\t' else ' ' for c in decoded)
                    if len(cleaned.strip()) > 50:
                        text_pieces = [cleaned]
                except:
                    decoded = raw_text.decode('cp1252', errors='ignore')
                    cleaned = ''.join(c if c.isprintable() or c in '\n\r\t' else ' ' for c in decoded)
                    if len(cleaned.strip()) > 50:
                        text_pieces = [cleaned]

        ole.close()
        
        result = '\n'.join(text_pieces)
        # Clean up control characters but keep newlines
        result = ''.join(c if c.isprintable() or c in '\n\r\t' else '\n' for c in result)
        # Collapse multiple blank lines
        while '\n\n\n' in result:
            result = result.replace('\n\n\n', '\n\n')
        
        return result.strip()
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse .doc file: {str(e)}")

def verify_matches_with_string_search(in_text_citations, references):
    verification_results = {
        "confirmed_matches": [],
        "unmatched_citations": [],
        "unmatched_references": [],
        "duplicate_first_names": {},
        "summary": "Simple first-name match verification completed (case-insensitive)."
    }

    def extract_first_author(citation):
        match = re.search(r'^([A-Za-z\'-]+)', citation.strip('()[] ').split(' et al.')[0].split(' and ')[0].strip())
        if match:
            return match.group(1).strip()
        return None

    def extract_first_ref_author(ref):
        match = re.search(r'^([A-Za-z\s\'-]+)', ref.strip())
        if match:
            author = match.group(1).rstrip(',.').strip()
            return author
        return None

    ref_groups = {}
    for ref in references:
        ref_author = extract_first_ref_author(ref)
        if ref_author:
            ref_groups.setdefault(ref_author.lower(), []).append(ref)

    for first_name, refs in ref_groups.items():
        if len(refs) > 1:
            verification_results["duplicate_first_names"][first_name.capitalize()] = refs

    matched_refs = set()

    for cit in in_text_citations:
        cit_author = extract_first_author(cit)
        if not cit_author:
            verification_results["unmatched_citations"].append(cit)
            continue

        matched = False
        best_ref = None
        for ref in references:
            ref_author = extract_first_ref_author(ref)
            if ref_author and cit_author.lower() == ref_author.lower():
                matched = True
                best_ref = ref
                matched_refs.add(ref)
                break

        if matched:
            verification_results["confirmed_matches"].append({
                "citation": cit,
                "matched_ref": best_ref
            })
        else:
            verification_results["unmatched_citations"].append(cit)

    verification_results["unmatched_references"] = [ref for ref in references if ref not in matched_refs]

    return verification_results

def count_references_and_citations(analysis):
    num_unique_citations = len(analysis.get("in_text_citations", []))
    num_references = len(analysis.get("references", []))
    analysis["num_unique_citations"] = num_unique_citations
    analysis["num_references"] = num_references
    return analysis

def extract_verbatim_references(full_text: str, ai_references: list) -> dict:
    """
    For each reference identified by the AI, find the closest verbatim match
    in the original document text. Uses fuzzy matching so even if the AI slightly
    altered a reference, we can still locate the original.
    
    Returns a dict mapping AI reference -> verbatim source text.
    """
    from difflib import SequenceMatcher
    
    # Split the document into lines — references are typically line-separated
    doc_lines = [line.strip() for line in full_text.split('\n') if line.strip()]
    
    # Also build multi-line candidates (some references span 2-3 lines)
    candidates = list(doc_lines)
    for i in range(len(doc_lines) - 1):
        candidates.append(doc_lines[i] + ' ' + doc_lines[i + 1])
    for i in range(len(doc_lines) - 2):
        candidates.append(doc_lines[i] + ' ' + doc_lines[i + 1] + ' ' + doc_lines[i + 2])
    
    verbatim_map = {}
    
    for ai_ref in ai_references:
        best_score = 0
        best_match = ai_ref  # fallback to AI version
        
        # Normalize the AI reference for comparison
        ai_ref_lower = ai_ref.lower().strip()
        
        for candidate in candidates:
            candidate_lower = candidate.lower().strip()
            
            # Quick filter: skip candidates that are too short or too different in length
            if len(candidate_lower) < 15:
                continue
            len_ratio = len(candidate_lower) / max(len(ai_ref_lower), 1)
            if len_ratio < 0.3 or len_ratio > 3.0:
                continue
            
            # Check if the first author name appears in the candidate
            first_word = ai_ref_lower.split(',')[0].split('(')[0].strip()[:15]
            if first_word and first_word not in candidate_lower:
                continue
            
            score = SequenceMatcher(None, ai_ref_lower, candidate_lower).ratio()
            if score > best_score:
                best_score = score
                best_match = candidate
        
        verbatim_map[ai_ref] = {
            "verbatim": best_match,
            "confidence": round(best_score, 2)
        }
    
    return verbatim_map

@app.post("/api/verify")
async def verify_citations(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(('.pdf', '.docx', '.doc')):
        raise HTTPException(status_code=400, detail="Unsupported file type. Please upload PDF, DOCX, or DOC.")

    file_bytes = await file.read()

    async def event_stream():
        import asyncio

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

        word_count = len(full_text.split())
        yield f"data: {json.dumps({'stage': 'extracted', 'message': f'Extracted {word_count:,} words from document'})}\n\n"
        await asyncio.sleep(0.1)

        # Stage 2: AI Analysis
        yield f"data: {json.dumps({'stage': 'analyzing', 'message': 'Sending to Gemini AI for citation analysis...'})}\n\n"
        await asyncio.sleep(0.1)

        try:
            client = get_client()
            prompt = f"""
    Analyze the following document text for citations and references. Identify all in-text citations (e.g., (Author, Year), [1], Author (Year), etc.) and extract the reference list (typically at the end, under headings like 'References', 'Bibliography', etc.).

    Tasks:
    1. List all unique in-text citations found.
    2. Extract and list all references from the reference section.
    3. Match each citation to its corresponding reference.
    4. Identify mismatches:
       - Citations in text without a matching reference (missing references).
       - References without a corresponding citation in text (unused references).
       - Irregularities: Date mismatches, author name inconsistencies (e.g., 'Smith 2020' cited but 'Smyth 2019' in refs), formatting issues, duplicates, etc.

    Output in strict JSON format only:
    {{
        "in_text_citations": ["citation1", "citation2", ...],
        "references": ["ref1", "ref2", ...],
        "missing_references_for_citations": ["unmatched_citation1", ...],
        "unused_references": ["extra_ref1", ...],
        "irregularities": [
            {{"type": "date_mismatch", "citation": "Author (2020)", "ref": "Author (2019)", "details": "Year differs"}},
            {{"type": "name_mismatch", "citation": "Smith", "ref": "Smyth", "details": "Spelling error"}}
        ],
        "summary": "Brief overview of issues found."
    }}

    Document text:
    {full_text[:1000000]}
    """

            yield f"data: {json.dumps({'stage': 'analyzing', 'message': 'Gemini is reading your document...'})}\n\n"
            
            response = client.models.generate_content(
                model='gemini-3-flash-preview',
                contents=prompt
            )
        except Exception as e:
            yield f"data: {json.dumps({'stage': 'error', 'message': f'Gemini API error: {str(e)}'})}\n\n"
            return

        yield f"data: {json.dumps({'stage': 'processing', 'message': 'Parsing AI response...'})}\n\n"
        await asyncio.sleep(0.1)

        # Stage 3: Parse response
        try:
            output_text = response.text.strip()
            if output_text.startswith('```json'):
                output_text = output_text[7:].strip()
            if output_text.endswith('```'):
                output_text = output_text[:-3].strip()
            analysis = json.loads(output_text)

            analysis = count_references_and_citations(analysis)

            num_cit = analysis.get("num_unique_citations", 0)
            num_ref = analysis.get("num_references", 0)
            verify_msg = f"Found {num_cit} citations and {num_ref} references. Running string verification..."
            yield f"data: {json.dumps({'stage': 'verifying', 'message': verify_msg})}\n\n"
            await asyncio.sleep(0.1)

            # Stage 4: String verification
            verification = verify_matches_with_string_search(
                analysis.get("in_text_citations", []),
                analysis.get("references", []),
            )
            analysis["string_verification"] = verification

            # Stage 5: Extract verbatim references from source document
            yield f"data: {json.dumps({'stage': 'extracting', 'message': 'Extracting verbatim references from source document...'})}\n\n"
            await asyncio.sleep(0.1)

            verbatim_map = extract_verbatim_references(full_text, analysis.get("references", []))
            analysis["verbatim_references"] = verbatim_map

            yield f"data: {json.dumps({'stage': 'complete', 'message': 'Analysis complete!', 'data': analysis})}\n\n"

        except json.JSONDecodeError as e:
            yield f"data: {json.dumps({'stage': 'error', 'message': f'Error parsing Gemini response: {str(e)}'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'stage': 'error', 'message': f'Unexpected error: {str(e)}'})}\n\n"

    from starlette.responses import StreamingResponse
    return StreamingResponse(event_stream(), media_type="text/event-stream")

class FormatRequest(BaseModel):
    references: List[str]

@app.post("/api/format")
async def format_references(req: FormatRequest):
    client = get_client()
    
    formatted_refs = []
    for ref in req.references:
        prompt = f"""
        Using the Harvard referencing guide provided below, classify the following input reference and reformat it to match the exact Harvard style for its type (e.g., Book, Journal Article, Web page, etc.).

        If the input is already in Harvard style, confirm and output it as is. If not, identify the type and apply the correct format.

        Guide:
        {HARVARD_GUIDE}

        Input reference:
        {ref}

        Output in JSON:
        {{
            "original": "copy the exact input reference here",
            "type": "classified_type (e.g., Book, Journal Article)",
            "formatted": "reformatted Harvard reference"
        }}
        """

        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt
        )
        
        try:
            output_text = response.text.strip()
            if output_text.startswith('```json'):
                output_text = output_text[7:].strip()
            if output_text.endswith('```'):
                output_text = output_text[:-3].strip()
            result = json.loads(output_text)
            formatted_refs.append(result)
        except Exception as e:
            formatted_refs.append({"original": ref, "error": str(e), "raw_response": response.text})

    return {"formatted_references": formatted_refs}

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
