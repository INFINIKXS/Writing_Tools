# Library Reference Pipeline & Metadata Verification

This document details the architecture, data flows, and security gates governing the Library feature in Writing Tools. It specifically maps out how metadata is extracted from uploaded documents, validated against external APIs, and secured to ensure no unverified or incomplete references leak into the user's library.

## 1. High-Level Architecture

The Library module ingests user documents (PDFs and DOCX), extracts their bibliographic metadata, and stores them as structured references. The pipeline is designed around a **trust-but-verify** model:
- **Local Extraction** (Regex/GROBID for PDFs, Core Properties for DOCX) provides the initial "best guess" and searches for DOIs.
- **External APIs** (CrossRef, PubMed) provide authoritative metadata based on DOIs.
- **Strict Completeness Gates** ensure the API data isn't missing critical fields.
- **AI Fallback** is available but physically verified against the source text to prevent LLM hallucinations.

## 2. The Verification Status Lifecycle

A reference in the system carries one of the following statuses:
- `not_found`: Initial state. No authoritative metadata found yet.
- `verified_crossref`: Successfully matched and validated via CrossRef API.
- `verified_pubmed`: Successfully matched and validated via PubMed API.
- `verified_ai_strict_scan`: Extracted by Gemini and physically verified to exist in the PDF text.
- `unverified`: The fallback state. If the pipeline exhausts all options or data is incomplete, it stays here. The user must manually edit/verify.

## 3. The Extraction Cascade (PDF Uploads)

When a PDF is uploaded, it passes through the following layers (`_metadata_pipeline` in `metadata.py`):

1. **pdf2doi**: Fast exact DOI match.
2. **GROBID**: Deep machine-learning scan for DOIs and header metadata.
3. **Crossref / PubMed DOI Lookup**: If a DOI was found, query the APIs.
4. **`_validate_api_result` (The Choke Point)**: The API result is subjected to strict completeness and identity rules.

### The Strict Completeness Gate

A reference is only as good as its weakest field. To prevent "dirty" or partial data from being marked as verified, all API results MUST pass the Completeness Gate:
- Must have a `title`.
- Must have `authors`.
- Must have a `year`.
- *If it's a Journal Article*, must have a `journal` (or `source`).

If ANY of these are missing, the API result is **rejected outright**, and the pipeline falls through to the next layer or defaults to `unverified`.

## 4. The AI Retry Pathway

When standard extraction fails, or the user clicks "Retry with AI" in the frontend, the document is sent to Gemini. Because LLMs hallucinate, this pathway is strictly guarded.

**The Flow:**

```
AI extracts DOI
    ↓
PubMed lookup → _validate_api_result() ← COMPLETENESS GATE HERE
    │  incomplete (missing title/authors/year)? → REJECT
    │  passes? → merge + stamp "verified_pubmed"
    ↓ (if PubMed fails)
CrossRef lookup → _validate_api_result() ← COMPLETENESS GATE HERE  
    │  incomplete? → REJECT
    │  passes? → merge + stamp "verified_crossref"
    ↓ (if both fail or no DOI found)
strict_ai_verify_against_pdf() ← PHYSICAL PDF SCAN
    │  fields not found in PDF text? → REJECT
    │  passes? → stamp "verified_ai_strict_scan"
    ↓ (if all three fail)
HTTPException 400 — "AI extraction failed identity verification"
```

### Physical Verification (`strict_ai_verify_against_pdf`)
If the AI cannot find a DOI but hallucinates full metadata (e.g., Title, Authors, Year), the system does **not** blindly trust it. Instead, it converts the PDF to raw text and does string-matching:
- Every author surname must literally exist in the PDF text.
- The year must exist in the PDF text.
- At least a portion of the title must exist in the PDF text.

If these physical checks fail, the AI extraction is rejected entirely.

## 5. The Merge Hierarchy

When API data is accepted, it is merged with the local extraction data using `overwrite=True`.

- **Why Merge?** APIs like CrossRef provide authoritative core fields (`title`, `authors`, `year`, `journal`), but lack local document context (e.g., accessed date, specific edition). Local extraction is needed to find the DOI to query the API in the first place.
- **The Rule:** The external API always overwrites local guesses for fields it provides. Local data only survives for supplementary fields the API does not cover.

## 6. Known Leakage Vectors (Closed)

Historically, partial or unverified data could leak into the `verified` state. These paths have been intentionally sealed to maintain strict library integrity:
- **Title-Search Fallbacks**: Bypassed identity verification against the PDF and had no completeness checks. **Removed**. If DOI verification fails, the reference correctly remains `unverified`.
- **DOCX HTTP 200 Stamp**: Previously stamped `verified_crossref` simply if the CrossRef API responded with a 200 OK. **Fixed**: Now passes through the exact same strict completeness gate as PDFs.
- **Partial Authors Check**: Previously allowed missing authors if a year was present (intended for container-level records). **Fixed**: Now strictly rejects if *any* core field is missing.
