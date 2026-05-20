# Reference Generator Architecture

This document outlines the current production architecture and processing pathways of the Reference Generator system within the Library feature. 

The system utilizes an **AI-free, lightweight, high-speed deterministic cascade** for standard extraction, combined with a **Three-Step Speculative Verification Sieve** and an **AI-Guided (Advanced) Pathway** when maximum accuracy is requested. 

No heavyweight local machine learning dependencies (such as PyTorch, spaCy, GROBID, or LayoutLM) are used.

---

## High-Level System Architecture

```mermaid
flowchart TB
    %% Definitions
    subgraph Client ["Client Interface (Web App)"]
        UI["Library UI"]
        Upload["PDF/DOCX Upload"]
        PasteRef["Paste Reference List"]
    end

    subgraph API_Router ["API Routing & Orchestration (FastAPI)"]
        RouteExtract["/api/extract-reference"]
        RouteBatch["/api/extract-reference-batch"]
        RouteVerifyList["/api/verify-reference-list"]
        RoutePasted["/api/verify-pasted-list"]
    end

    subgraph Extraction_Engine ["Metadata Extraction Engine (metadata.py)"]
        %% Deterministic Cascade
        subgraph Cascade ["Standard Mode: Deterministic Cascade"]
            L1["Layer 1: PDF Embedded properties\n(Dublin Core XMP & PDF Info)"]
            GarbageFilter{"Garbage Title\nFilter?"}
            L2["Layer 2: Local Heuristic Regex\n(First 3 Pages Text)"]
            L3["Layer 3: pdf2doi Rescue\n(Filename patterns & text scan)"]
        end

        %% Speculative Verification Sieve
        subgraph Sieve ["Speculative Sieve Step"]
            RegexClean["Polish & Clean Candidates\n(Trim platform domains & suffixes)"]
            SpecCheck{"Speculative HEAD Check\n(verify_doi_online)"}
        end

        %% AI Pathway
        subgraph AIPathway ["Advanced Mode: AI-Guided Pathway"]
            Gemini["Gemini AI (3.5 Flash / Lite)\nStructured JSON extraction"]
            StrictScan{"Strict PDF Text Scan\nVerification?"}
        end
    end

    subgraph Verifier ["Verification & Enrichment Layer"]
        BatchFetch["CrossRef Async Batch Fetch\n(api_batch.py)"]
        PubMed["PubMed Fallback Lookup\n(E-utilities)"]
        ValResult{"_validate_api_result\nVerification Gates"}
        
        %% Gates
        GateTitle["1. Title Similarity (difflib >= 90%)"]
        GateHard["2. Hard PDF text match (true title in PDF text)"]
        GateCompleteness["3. Strict Completeness Gate\n(No partial/missing fields)"]
    end

    subgraph Formatter ["Formatting Engine (citations/formatting.py)"]
        FormatStyles["Formatting Layer\n(APA, Harvard, Vancouver, etc.)"]
    end

    %% Flow/Connections
    Upload --> RouteExtract
    Upload --> RouteBatch
    PasteRef --> RouteVerifyList
    PasteRef --> RoutePasted

    RouteExtract --> |"Advanced = False"| L1
    RouteExtract --> |"Advanced = True"| Gemini
    RouteBatch --> Gemini
    
    %% Cascade Pipeline
    L1 --> GarbageFilter
    GarbageFilter --> |"Valid"| L2
    GarbageFilter --> |"Garbage"| L2
    L2 --> L3
    
    %% Speculative Sieve Step
    L2 --> |"Candidate DOIs"| RegexClean
    L3 --> |"Candidate DOIs"| RegexClean
    
    RegexClean --> SpecCheck
    SpecCheck --> |"Verified DOI"| BatchFetch
    SpecCheck --> |"Unverified fallback"| BatchFetch
    
    %% AI Pipeline Verification
    Gemini --> StrictScan
    StrictScan --> |"Passed"| BatchFetch
    StrictScan --> |"Failed"| RouteExtract
    
    BatchFetch --> ValResult
    ValResult --> GateTitle
    ValResult --> GateHard
    ValResult --> GateCompleteness
    
    ValResult --> |"Failed"| PubMed
    ValResult --> |"Verified"| FormatStyles
    PubMed --> |"Verified"| FormatStyles
    PubMed --> |"Unverified fallback"| FormatStyles
    
    FormatStyles --> UI
```

---

## Core Flow Components

### 1. Document Extraction Pipeline

#### A. Deterministic Cascade Flow (Standard Mode)
The deterministic cascade runs entirely locally on the CPU to extract metadata with zero-API-cost:

```mermaid
stateDiagram-v2
    [*] --> Layer1_PDF_Metadata
    Layer1_PDF_Metadata --> Garbage_Check
    Garbage_Check --> Layer2_Heuristic_Regex : Filter out structural internal IDs & CC Licenses
    Layer2_Heuristic_Regex --> Layer3_pdf2doi : Missing critical fields or DOI
    Layer2_Heuristic_Regex --> Speculative_Sieve : DOI Candidate found
    Layer3_pdf2doi --> Speculative_Sieve : DOI Candidate found
    
    state Speculative_Sieve {
        [*] --> Polish_Candidate
        Polish_Candidate --> Speculative_HEAD_Check
        Speculative_HEAD_Check --> [*]
    }
    
    Speculative_Sieve --> Gather_DOIs
    Gather_DOIs --> [*]
```

##### Cascade Precedence & Merge Logic
When running standard extraction, search layers are executed sequentially to build a candidate list.

1. **Layer 1 (Embedded Properties)** runs first, tapping metadata directly from the PDF dictionary properties and Dublin Core XMP fields.
2. **Layer 2 (Heuristic Regex Parser)** runs next, executing a regex sweep over the first **3 pages** of raw text. **Layer 2 is always executed, even if Layer 1 already found a title or DOI.** This ensures that stale, placeholder, or default embedded metadata (e.g. *"Microsoft Word - Document1.docx"*) is caught, and physical DOIs printed in the document are successfully captured.
3. **Data Merging and Conflict Resolution**:
   * **For standard metadata fields (Title, Authors, Year, etc.)**: The system merges results via a non-overwriting helper: `_merge(base, update, overwrite=False)`. Therefore, fields already populated by Layer 1 take precedence and are **not** overwritten by Layer 2 heuristic extraction.
   * **For Candidate DOIs (The Verification Queue)**: **Layer 2 (text-extracted regex) DOIs take precedence over Layer 1 (embedded) DOIs**. The unique candidates list prioritizes text-extracted candidates, as they are statistically far more accurate.

---

#### B. AI-Guided Flow (Advanced Mode)
Used when explicit precision is required, leveraging LLMs to parse layout-agnostic raw document contents:

1. **Gemini Extraction**: Extracts raw text from the first 3 pages of the PDF and submits it to Gemini with a structured JSON schema.
2. **Anti-Hallucination Verification**: If no valid database lookup successfully verifies, it invokes `strict_ai_verify_against_pdf(ai_data, pdf_path)`. This function scans the raw PDF text to physically confirm that all AI-inferred values (specifically the title, author surnames, and year) are present within the document text. If key details fail this scanner, they are discarded to prevent hallucinated references.

---

### 2. Speculative Sieve & Verification Loop

The newly added **Three-Step Speculative Verification Sieve** sits directly before the bulk lookup calls to CrossRef/PubMed. 

```mermaid
sequenceDiagram
    autonumber
    participant Engine as Metadata Engine
    participant Sieve as Speculative Sieve (robust_doi_resolver)
    participant API as CrossRef / PubMed API
    participant Doc as PDF Document (Raw Text)

    Engine->>Sieve: robust_doi_resolver(candidate_doi)
    Note over Sieve: Step 1: Bounded capture & context polish (Trim glued domains)
    Sieve->>API: Step 2: Speculative HEAD check (verify_doi_online)
    API-->>Sieve: HTTP 200 / 404 Status
    Sieve-->>Engine: Verified DOI / Unverified fallback
    
    Engine->>API: fetch_crossref_batch(clean_dois)
    API-->>Engine: Structured CrossRef Records
    
    rect rgb(240, 248, 255)
        note over Engine, Doc: _validate_api_result (Verification Gates)
        Engine->>Engine: Run Title Similarity check (difflib Ratio >= 90%)
        alt Title Similarity Mismatch
            Engine->>Doc: Search PDF text for True API Title + Author Surnames
            Doc-->>Engine: Found/Not Found
        end
        Engine->>Engine: Run Strict Completeness Gate (Verify Title, Authors, Year, Journal)
    end
    
    alt Verified successfully
        Engine->>Engine: Status: verified_crossref
    else Validation Failed / No DOI Matches
        Engine->>API: pubmed_lookup(doi)
        API-->>Engine: PubMed Bibliographic Details
        Engine->>Engine: Validate PubMed Details
        alt PubMed Verified
            Engine->>Engine: Status: verified_pubmed
        else PubMed Failed
            Engine->>Engine: Status: unverified (Retain local cascade fields)
        end
    end
```

#### Verification Gates (`_validate_api_result`)
To prevent bad metadata or incorrect DOI mappings from overwriting a PDF's local records, every single API-returned metadata block is validated using a multi-signal identity match check. 

1. **Fail-Safe Identity Check**: If the heuristic layers failed to find a local title, author list, or year, the system runs an aggressive local identity parser (`_extract_identity_from_pdf`) to scrape name signals from the page text. If no local identity signal can be gathered, **the system immediately rejects the API record** rather than blindly accepting it.
2. **Completeness Gate**: The system rejects any API record that is missing essential fields (Title, Authors, Year, or Journal/Publisher) to prevent partial/fragmented data from being shown to the user as "verified".
3. **Multi-Signal Verification Checks**:
   * **Title Similarity**: Compares the local title and the API title using `SequenceMatcher`. They must match at a similarity ratio $\ge 90\%$.
   * **Hard PDF Verification (Anti-Hallucination Override)**: If similarity is low due to extraction fragmentation, the system scans the raw text of the actual PDF (`hard_verify_against_pdf`) to physically check if the official API title and first-author surname are verifiably printed inside the document.
   * **Author Surname Overlap**: Extracts and normalizes surnames, requiring at least one matching surname intersection between local PDF metadata and the API response.
   * **Year Match**: Verifies that the publication years match exactly.
4. **Veto and Override Decision Logic**:
   * A title mismatch acts as a **hard veto** and immediately fails validation, **unless** it is overridden by a strong matching signal (first-author surname match) or if the local title is identified as garbage template metadata (e.g. *"Full list of author information"*).
   * **If validation fails**: The metadata is **not** overwritten. The original heuristic data is retained and labeled as `unverified` so that no incorrect reference records are introduced.

---

### 3. Pasted Reference List Pipeline
When a user pastes a raw bibliography text block into the Library interface:

```mermaid
flowchart LR
    Paste["Pasted Bibliography Block"] --> Seg["LLM Segmenter & Healer\n(segment_verifier_text_via_llm)"]
    Seg --> Workers["Verify Workers\n(verify_single_reference)"]
    subgraph Semaphore_Gate ["Rate Limiting Gate"]
        Workers --> |"3 Concurrent Workers Max"| API_Check["CrossRef & PubMed Check"]
    end
    API_Check --> Format["Formatting Layer\n(APA, Harvard, Vancouver)"]
    Format --> Output["Interactive Library UI"]
```
