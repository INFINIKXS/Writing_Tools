# AI-to-Human Style Transfer Engine — Technical Documentation

> **System**: Writing Tools — AI Humanizer Module
> **Version**: 1.0
> **Last Updated**: 2026-03-07

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Pipeline Stages](#pipeline-stages)
4. [Algorithm 1: Sentence Deconstruction (spaCy)](#algorithm-1-sentence-deconstruction)
5. [Algorithm 2: Human Skeleton Retrieval (Sentence Transformers)](#algorithm-2-human-skeleton-retrieval)
6. [Algorithm 3: Variable Reconstruction](#algorithm-3-variable-reconstruction)
7. [Algorithm 4: Grammar Polish (Gemini)](#algorithm-4-grammar-polish)
8. [Human Sentence Indexing Pipeline](#human-sentence-indexing-pipeline)
9. [Data Flow](#data-flow)
10. [Tech Stack & Dependencies](#tech-stack--dependencies)
11. [API Reference](#api-reference)
12. [Why This Beats Conventional AI Humanizers](#why-this-beats-conventional-ai-humanizers)

---

## System Overview

The AI Humanizer is a **4-step style transfer pipeline** that transforms AI-generated text by mathematically mapping its semantic content onto verified human sentence structures extracted from academic PDFs.

> **Core Principle**: Instead of asking an LLM to "rewrite to sound human" (which just produces more LLM-sounding text), this system forces AI content to conform to actual sentence structures written by real human authors — an automated, academic game of Mad Libs.

```mermaid
graph LR
    A["🤖 AI Text"] --> B["1. Deconstruct<br/>(spaCy NLP)"]
    B --> C["2. Retrieve<br/>(Sentence Transformer)"]
    C --> D["3. Reconstruct<br/>(Variable Swap)"]
    D --> E["4. Polish<br/>(Gemini LLM)"]
    E --> F["🧑 Human-Sounding Text"]

    style A fill:#dc2626,color:#fff
    style B fill:#2563eb,color:#fff
    style C fill:#7c3aed,color:#fff
    style D fill:#d97706,color:#fff
    style E fill:#059669,color:#fff
    style F fill:#059669,color:#fff
```

### The Key Insight

Most AI humanizers operate like this:

```
AI Text → LLM("rewrite this to sound human") → Still AI-Sounding Text
```

This system operates like this:

```
AI Text → Extract Facts → Find Real Human Phrasing → Inject Facts Into Human Structure → Polish
```

The LLM is only used for **grammar correction** at the end — never for rephrasing. The human structure comes directly from real academic authors.

---

## Architecture Diagram

```mermaid
graph TB
    subgraph Frontend ["Frontend (React + Vite)"]
        HV["HumanizerView.jsx"]
        LIB["Human Library Panel"]
        INP["Text Input Panel"]
        OUT["Output Panel"]
        HV --> LIB
        HV --> INP
        HV --> OUT
    end

    subgraph Backend ["Backend (FastAPI + Python)"]
        subgraph Endpoints ["API Endpoints"]
            UP["/api/humanizer/upload"]
            HUM["/api/humanizer/humanize"]
            DOC["/api/humanizer/documents"]
            DEL["/api/humanizer/document/{id}"]
            STAT["/api/humanizer/stats"]
        end

        subgraph IndexPipeline ["Indexing Pipeline (humanizer_store.py)"]
            PDF["PDF Text Extraction"]
            SS["Sentence Splitting (spaCy)"]
            MASK["Sentence Masking (spaCy)"]
            ENC["Embedding Encoding<br/>(all-MiniLM-L6-v2)"]
            DB[("SQLite DB<br/>humanizer_index.db")]
            PDF --> SS --> MASK --> ENC --> DB
        end

        subgraph TransferPipeline ["Style Transfer Pipeline (humanizer.py)"]
            D1["Step 1: Deconstruct<br/>spaCy dep parsing"]
            D2["Step 2: Retrieve<br/>cosine similarity search"]
            D3["Step 3: Reconstruct<br/>role-aware variable swap"]
            D4["Step 4: Polish<br/>Gemini grammar fix"]
            D1 --> D2 --> D3 --> D4
        end

        UP --> IndexPipeline
        HUM --> TransferPipeline
        D2 <--> DB
        DOC --> DB
        DEL --> DB
        STAT --> DB
    end

    LIB <-->|Upload PDFs| UP
    INP <-->|Humanize text| HUM
    LIB <-->|List/Delete| DOC
    LIB <-->|List/Delete| DEL
```

---

## Pipeline Stages

The humanization runs as a **per-sentence pipeline** — each sentence in the input text is independently transformed through all 4 stages.

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant BE as Backend
    participant SP as spaCy NLP
    participant ST as SentenceTransformer
    participant DB as SQLite Vector DB
    participant LLM as Gemini API

    U->>FE: Paste AI text + click Humanize
    FE->>BE: POST /api/humanizer/humanize

    Note over BE: Split text into sentences (spaCy)

    loop For each sentence
        Note over BE,SP: Step 1: Deconstruct
        BE->>SP: Parse sentence
        SP-->>BE: Dependency tree + noun chunks
        BE->>BE: Extract variables + create masked skeleton

        Note over BE,DB: Step 2: Retrieve
        BE->>ST: Encode masked skeleton → vector
        ST-->>BE: 384-dim embedding
        BE->>DB: Cosine similarity search
        DB-->>BE: Top-k human skeletons

        Note over BE: Step 3: Reconstruct
        BE->>BE: Map AI variables into human skeleton

        Note over BE,LLM: Step 4: Polish
        BE->>LLM: "Fix grammar only, change nothing else"
        LLM-->>BE: Polished sentence
    end

    BE-->>FE: Full result with per-sentence breakdown
    FE->>U: Display humanized text + step details
```

| Stage | Name | Engine | Purpose |
| --- | --- | --- | --- |
| 1 | Deconstruct | **spaCy** `en_core_web_sm` | Extract entities by syntactic role, create masked skeleton |
| 2 | Retrieve | **SentenceTransformer** `all-MiniLM-L6-v2` | Find closest human sentence skeleton via cosine similarity |
| 3 | Reconstruct | **Python** (role-aware mapping) | Slot AI's facts into the human's sentence structure |
| 4 | Polish | **Gemini** `gemini-3.1-flash-lite-preview` | Fix grammar friction without changing vocabulary |

---

## Algorithm 1: Sentence Deconstruction

**Function**: `deconstruct_sentence(sentence: str) → dict`
**Engine**: spaCy `en_core_web_sm` (dependency parser)

### Purpose

Programmatically separate a sentence into its **semantic content** (the "meat" — facts, entities, topics) and its **syntactic structure** (the "skeleton" — how those facts are arranged grammatically).

### Role Extraction Rules

```mermaid
flowchart TD
    S["Input Sentence"] --> NLP["spaCy Dependency Parse"]
    NLP --> NC["Extract Noun Chunks"]

    NC --> R1{"dep = nsubj<br/>or nsubjpass?"}
    NC --> R2{"dep = dobj?"}
    NC --> R3{"dep = pobj?"}
    NC --> R4{"dep = attr?"}
    NC --> R5{"other dep?"}

    R1 -->|Yes| S1["[SUBJECT]"]
    R2 -->|Yes| S2["[OBJECT]"]
    R3 -->|Yes| P{"Preposition?"}
    R4 -->|Yes| S4["[ATTRIBUTE]"]
    R5 -->|Yes| S5["[ENTITY]"]

    P -->|"into, to, towards"| S6["[OUTPUT]"]
    P -->|"from, of, through, via, by"| S7["[INPUT]"]
    P -->|other| S8["[OBJECT]"]

    style S1 fill:#2563eb,color:#fff
    style S2 fill:#059669,color:#fff
    style S4 fill:#7c3aed,color:#fff
    style S5 fill:#6b7280,color:#fff
    style S6 fill:#dc2626,color:#fff
    style S7 fill:#d97706,color:#fff
    style S8 fill:#059669,color:#fff
```

### Algorithm

```
INPUT: "Photosynthesis is the process by which green plants transform light energy into chemical energy."
OUTPUT: {
  "masked": "[SUBJECT] is [ATTRIBUTE] by which [OBJECT] transform [INPUT] into [OUTPUT].",
  "variables": {
    "SUBJECT": "Photosynthesis",
    "ATTRIBUTE": "the process",
    "OBJECT": "green plants",
    "INPUT": "light energy",
    "OUTPUT": "chemical energy"
  }
}

ALGORITHM:
1. Parse sentence with spaCy → dependency tree
2. FOR each noun chunk in the sentence:
   a. Skip pronouns (pos_ == "PRON")
   b. Read the root token's dependency label (dep_)
   c. Map dep_ to role using the Role Extraction Rules
   d. Handle duplicate roles by numbering: OBJECT, OBJECT_2, OBJECT_3...
   e. Record (start_char, end_char, placeholder) for each chunk
3. Sort replacements by position (reverse order to preserve indices)
4. Replace each chunk with its placeholder in the original text
5. RETURN { masked, variables }
```

### Dependency-to-Role Mapping Table

| spaCy `dep_` | Assigned Role | Example |
| --- | --- | --- |
| `nsubj`, `nsubjpass` | `[SUBJECT]` | "**Photosynthesis** is..." |
| `dobj` | `[OBJECT]` | "...transform **light energy**" |
| `pobj` + prep `into/to/towards` | `[OUTPUT]` | "...into **chemical energy**" |
| `pobj` + prep `from/of/through/via/by` | `[INPUT]` | "...by which **green plants**" |
| `pobj` + other prep | `[OBJECT]` | "...in **the cell**" |
| `attr` | `[ATTRIBUTE]` | "...is **the process**" |
| anything else | `[ENTITY]` | fallback catch-all |

---

## Algorithm 2: Human Skeleton Retrieval

**Function**: `retrieve_human_skeleton(masked_ai_sentence: str, top_k: int) → list`
**Engine**: SentenceTransformer `all-MiniLM-L6-v2` (384-dimensional embeddings)

### Purpose

Search the pre-indexed database of human sentences (from uploaded PDFs) to find the one whose **masked skeleton** is most structurally similar to the AI's masked skeleton. This is a semantic similarity search — not keyword matching.

### How It Works

```mermaid
flowchart LR
    subgraph Query ["AI Masked Skeleton"]
        Q["[SUBJECT] is [ATTRIBUTE]<br/>by which [OBJECT]<br/>transform [INPUT] into [OUTPUT]."]
    end

    subgraph Encode ["SentenceTransformer"]
        E["all-MiniLM-L6-v2<br/>→ 384-dim vector"]
    end

    subgraph Search ["Cosine Similarity Search"]
        DB[("SQLite DB<br/>N stored embeddings")]
        COS["dot(query, stored)<br/>= cosine similarity"]
    end

    subgraph Results ["Top-k Results"]
        R1["0.87 — 'At the heart of [SUBJECT]<br/>lies a remarkable mechanism,<br/>enabling [OBJECT] to harness<br/>[INPUT] and convert it into [OUTPUT].'"]
        R2["0.72 — '[SUBJECT] represents<br/>a fundamental process...'"]
        R3["0.65 — 'Through [SUBJECT],<br/>[OBJECT] are able to...'"]
    end

    Q --> E --> COS
    DB --> COS
    COS --> R1
    COS --> R2
    COS --> R3

    style R1 fill:#059669,color:#fff
```

### Algorithm

```
INPUT: masked_ai_sentence (string with [PLACEHOLDER] slots)
OUTPUT: list of {masked_text, sentence_text, similarity} sorted by similarity

1. Encode the masked AI sentence:
   query_vector = SentenceTransformer.encode(masked_ai_sentence)  → float32[384]
   Normalize to unit length

2. Load ALL stored human sentence embeddings from SQLite

3. FOR each stored embedding:
   similarity = dot_product(query_vector, stored_vector)
   (equivalent to cosine similarity because both are L2-normalized)

4. Sort by similarity descending

5. RETURN top_k results with:
   - masked_text: the human skeleton with placeholders
   - sentence_text: the original human sentence (for display)
   - similarity: cosine similarity score (0.0 to 1.0)
```

### Why Sentence Transformers (Not TF-IDF / BM25)?

| Method | What it compares | Problem |
| --- | --- | --- |
| TF-IDF / BM25 | Exact word overlap | `[SUBJECT]` would only match `[SUBJECT]` — no structural understanding |
| Sentence Transformers | **Semantic meaning** | "X is transformed by Y into Z" matches "Y converts X to Z" even with different words |

The Sentence Transformer understands that `"[SUBJECT] is [ATTRIBUTE] by which [OBJECT] transform [INPUT] into [OUTPUT]"` is structurally similar to `"At the heart of [SUBJECT] lies a mechanism enabling [OBJECT] to harness [INPUT] and convert it into [OUTPUT]"` — because both describe a **transformative process with the same role structure**.

---

## Algorithm 3: Variable Reconstruction

**Function**: `reconstruct_sentence(human_skeleton: str, variables: dict) → str`

### Purpose

Take the AI's extracted variables and slot them into the human skeleton. This is the "Mad Libs" step — same facts, completely different sentence structure.

### Reconstruction Strategy

```mermaid
flowchart TD
    subgraph Input
        AI["AI Variables:<br/>SUBJECT = Photosynthesis<br/>OBJECT = green plants<br/>INPUT = light energy<br/>OUTPUT = chemical energy"]
        HS["Human Skeleton:<br/>'At the heart of [SUBJECT] lies<br/>a remarkable mechanism, enabling<br/>[OBJECT] to harness [INPUT] and<br/>convert it into [OUTPUT].'"]
    end

    subgraph Pass1 ["Pass 1: Direct Key Match"]
        DK["Replace [SUBJECT] → Photosynthesis<br/>Replace [OBJECT] → green plants<br/>Replace [INPUT] → light energy<br/>Replace [OUTPUT] → chemical energy"]
    end

    subgraph Pass2 ["Pass 2: Role Similarity Fallback"]
        RS["If human skeleton has [ENTITY]<br/>but AI only has [SUBJECT]<br/>→ Map SUBJECT to ENTITY<br/>(same role group)"]
    end

    subgraph Pass3 ["Pass 3: Positional Fallback"]
        POS["Any remaining unfilled<br/>placeholders → fill with<br/>any remaining unused variable"]
    end

    subgraph Output
        RESULT["'At the heart of Photosynthesis<br/>lies a remarkable mechanism,<br/>enabling green plants to harness<br/>light energy and convert it into<br/>chemical energy.'"]
    end

    AI --> DK
    HS --> DK
    DK --> Pass2
    Pass2 --> Pass3
    Pass3 --> RESULT

    style RESULT fill:#059669,color:#fff
```

### Three-Pass Algorithm

```
INPUT:
  human_skeleton: "At the heart of [SUBJECT] lies a mechanism, enabling [ACTOR] to harness [INPUT]..."
  variables: {"SUBJECT": "Photosynthesis", "OBJECT": "green plants", "INPUT": "light energy", "OUTPUT": "chemical energy"}

OUTPUT: reconstructed sentence with all placeholders filled

PASS 1 — Direct Key Match:
  FOR each (key, value) in variables:
    IF "[{key}]" exists in human_skeleton:
      Replace first occurrence of "[{key}]" with value
      Mark key as used

PASS 2 — Role Similarity Fallback:
  Extract remaining unfilled placeholders from result
  Get unused variables (not matched in Pass 1)

  Role groups (priority-ordered):
    subject: [SUBJECT, ENTITY, ATTRIBUTE]
    actor:   [ACTOR, SUBJECT]
    object:  [OBJECT, ENTITY, OUTPUT, ATTRIBUTE]
    input:   [INPUT, OBJECT, ENTITY]
    output:  [OUTPUT, OBJECT, ENTITY]

  FOR each unfilled placeholder:
    Get its base role (strip trailing _2, _3 etc.)
    Look up the role group for that base role
    Find an unused variable whose base role matches any in the group
    IF found → replace placeholder, remove from unused

PASS 3 — Positional Fallback:
  FOR any still-unfilled placeholders:
    Fill with the first available unused variable (any role)
```

### Role Group Mapping

| Unfilled Placeholder | Will Accept Variable From |
| --- | --- |
| `[SUBJECT]` | SUBJECT → ENTITY → ATTRIBUTE |
| `[ACTOR]` | ACTOR → SUBJECT |
| `[OBJECT]` | OBJECT → ENTITY → OUTPUT → ATTRIBUTE |
| `[INPUT]` | INPUT → OBJECT → ENTITY |
| `[OUTPUT]` | OUTPUT → OBJECT → ENTITY |
| `[ENTITY]` | ENTITY → SUBJECT → OBJECT → ATTRIBUTE |
| `[ATTRIBUTE]` | ATTRIBUTE → ENTITY → OBJECT |

---

## Algorithm 4: Grammar Polish

**Function**: `polish_sentence(sentence: str) → str`
**Engine**: Gemini `gemini-3.1-flash-lite-preview`

### Purpose

After variable swapping, the reconstructed sentence may have minor grammatical friction — wrong articles ("a" vs "an"), subject-verb disagreement, or awkward punctuation. The LLM fixes **only grammar**, never vocabulary or structure.

### Strict Prompt Design

```
┌──────────────────────────────────────────────────────────────┐
│  You are a grammar-only proofreader. Your ONLY job is to    │
│  fix mechanical grammar errors in the sentence below.        │
│                                                              │
│  ALLOWED fixes (and NOTHING else):                           │
│    • Subject-verb agreement                                  │
│    • Article correction (a/an)                               │
│    • Pronoun case errors                                     │
│    • Capitalization at sentence start                         │
│    • Missing or extra punctuation                            │
│                                                              │
│  STRICTLY FORBIDDEN:                                         │
│    • Do NOT rewrite or rephrase any part                     │
│    • Do NOT change sentence structure or word order           │
│    • Do NOT add/remove/substitute words                      │
│    • Do NOT change the vocabulary in any way                 │
│    • Do NOT add explanations or quotation marks              │
│                                                              │
│  If already correct, return EXACTLY as-is.                    │
│                                                              │
│  Sentence: {reconstructed_sentence}                          │
│                                                              │
│  Return ONLY the corrected sentence. Nothing else.           │
└──────────────────────────────────────────────────────────────┘
```

### Why Use an LLM Here?

```mermaid
flowchart LR
    subgraph Before ["Before Polish"]
        B1["'a apple falls from the tree'"]
        B2["'the plants harnesses energy'"]
        B3["'Enabling organism to survive'"]
    end

    subgraph LLM ["Gemini 3.1 Flash-Lite"]
        FIX["Grammar Fix Only<br/>No vocabulary changes<br/>No restructuring"]
    end

    subgraph After ["After Polish"]
        A1["'an apple falls from the tree'"]
        A2["'the plants harness energy'"]
        A3["'Enabling organisms to survive'"]
    end

    B1 --> FIX --> A1
    B2 --> FIX --> A2
    B3 --> FIX --> A3

    style FIX fill:#059669,color:#fff
```

The LLM is constrained to a **single, narrow task** — it never generates creative content, only fixes mechanical grammar issues.

---

## Human Sentence Indexing Pipeline

Before the style transfer pipeline can run, the system needs a database of human sentence structures. This is built by uploading PDFs.

**Function**: `humanizer_store.index_document(filename, pages_text) → dict`

### Indexing Flow

```mermaid
flowchart TD
    PDF["Uploaded PDF"] --> EXT["PyPDF2: Extract text per page"]
    EXT --> JOIN["Join all pages into full text"]
    JOIN --> SPLIT["spaCy: Split into sentences"]
    SPLIT --> F{"sentence ≥ 6 words<br/>AND ≥ 30 chars?"}
    F -->|No| SKIP["Skip (too short)"]
    F -->|Yes| MASK["spaCy: Mask sentence<br/>Extract variables + placeholders"]
    MASK --> CHECK{"Variables found?<br/>Masked ≠ original?"}
    CHECK -->|No| SKIP2["Skip (no maskable entities)"]
    CHECK -->|Yes| ENCODE["SentenceTransformer:<br/>Encode masked text → 384-dim vector"]
    ENCODE --> STORE["SQLite: Store<br/>sentence_text + masked_text + embedding BLOB"]

    style MASK fill:#2563eb,color:#fff
    style ENCODE fill:#7c3aed,color:#fff
    style STORE fill:#059669,color:#fff
```

### Storage Schema

```mermaid
erDiagram
    humanizer_documents {
        TEXT doc_id PK "UUID (8 chars)"
        TEXT filename "e.g. 'biology_textbook.pdf'"
        INT sentence_count "Indexed sentence count"
        TIMESTAMP indexed_at "Auto-set on insert"
    }

    human_sentences {
        INT id PK "Auto-increment"
        TEXT doc_id FK "→ humanizer_documents"
        TEXT sentence_text "Original human sentence"
        TEXT masked_text "Skeleton with [PLACEHOLDERS]"
        BLOB embedding "float32[384] as bytes"
    }

    humanizer_documents ||--o{ human_sentences : "contains"
```

### Embedding Details

| Property | Value |
| --- | --- |
| Model | `all-MiniLM-L6-v2` |
| Dimensions | 384 |
| Normalization | L2-normalized (unit vectors) |
| Storage | `float32` array → raw bytes BLOB |
| Similarity | `dot_product(a, b)` = cosine similarity (since normalized) |
| Speed | ~50ms per sentence on CPU |

---

## Data Flow

### Complete End-to-End Flow

```mermaid
graph TB
    subgraph UserInput ["User Input"]
        AI_TEXT["AI-Generated Text<br/>'Photosynthesis is the process by which<br/>green plants transform light energy<br/>into chemical energy.'"]
    end

    subgraph Step1 ["Step 1: Deconstruct"]
        VARS["variables = {<br/>SUBJECT: 'Photosynthesis'<br/>OBJECT: 'green plants'<br/>INPUT: 'light energy'<br/>OUTPUT: 'chemical energy'}"]
        MASKED_AI["masked = '[SUBJECT] is [ATTRIBUTE]<br/>by which [OBJECT] transform<br/>[INPUT] into [OUTPUT].'"]
    end

    subgraph Step2 ["Step 2: Retrieve"]
        SEARCH["Vector search against<br/>human sentence DB"]
        HUMAN["Best match (0.87 similarity):<br/>'At the heart of [SUBJECT] lies<br/>a remarkable mechanism, enabling<br/>[OBJECT] to harness [INPUT] and<br/>convert it into [OUTPUT].'"]
    end

    subgraph Step3 ["Step 3: Reconstruct"]
        SWAP["Variable swap:<br/>'At the heart of Photosynthesis lies<br/>a remarkable mechanism, enabling<br/>green plants to harness light energy<br/>and convert it into chemical energy.'"]
    end

    subgraph Step4 ["Step 4: Polish"]
        FINAL["Grammar-checked:<br/>'At the heart of photosynthesis lies<br/>a remarkable mechanism, enabling<br/>green plants to harness light energy<br/>and convert it into chemical energy.'"]
    end

    AI_TEXT --> Step1
    Step1 --> MASKED_AI
    MASKED_AI --> SEARCH
    SEARCH --> HUMAN
    VARS --> Step3
    HUMAN --> Step3
    Step3 --> SWAP
    SWAP --> FINAL

    style Step1 fill:#2563eb,color:#fff
    style Step2 fill:#7c3aed,color:#fff
    style Step3 fill:#d97706,color:#fff
    style Step4 fill:#059669,color:#fff
```

### Response Object Structure

```json
{
  "original_text": "Photosynthesis is the process by which...",
  "humanized_text": "At the heart of photosynthesis lies...",
  "sentences": [
    {
      "original": "Photosynthesis is the process by which...",
      "humanized": "At the heart of photosynthesis lies...",
      "skipped": false,
      "steps": {
        "deconstruct": {
          "masked": "[SUBJECT] is [ATTRIBUTE] by which [OBJECT]...",
          "variables": {"SUBJECT": "Photosynthesis", "OBJECT": "green plants", ...}
        },
        "retrieve": {
          "human_skeleton": "At the heart of [SUBJECT] lies...",
          "original_human": "At the heart of evolution lies...",
          "similarity": 0.8723
        },
        "reconstruct": {
          "raw_output": "At the heart of Photosynthesis lies..."
        },
        "polish": {
          "final_output": "At the heart of photosynthesis lies..."
        }
      }
    }
  ],
  "stats": {
    "total_sentences": 1,
    "humanized_count": 1,
    "skipped_count": 0
  }
}
```

---

## Tech Stack & Dependencies

| Component | Technology | Role |
| --- | --- | --- |
| NLP Parser | **spaCy** `en_core_web_sm` (12 MB) | Dependency parsing, sentence splitting, entity extraction |
| Embeddings | **SentenceTransformer** `all-MiniLM-L6-v2` (80 MB) | Semantic encoding of masked sentences into 384-dim vectors |
| Vector Math | **NumPy** | Cosine similarity computation |
| Deep Learning | **PyTorch** (~2 GB) | Backend for SentenceTransformers (CPU mode) |
| Vector Storage | **SQLite** (humanizer_index.db) | Stored embeddings as BLOB, metadata tables |
| Grammar Polish | **Gemini** `gemini-3.1-flash-lite-preview` | Grammar-only correction (minimal thinking), reuses existing API key rotation |
| PDF Parsing | **PyPDF2** (already installed) | Page-by-page text extraction |

### Lazy Loading Strategy

Both spaCy and SentenceTransformers are **lazy-loaded** — they only initialize on first use. This means:

- Server startup is fast (no 2-second model loading delay)
- Memory is only allocated when the humanizer is first used
- Subsequent calls reuse the cached models

---

## API Reference

| Method | Endpoint | Description |
| --- | --- | --- |
| `POST` | `/api/humanizer/upload` | Upload PDFs to index human sentences |
| `POST` | `/api/humanizer/humanize` | Run style transfer on AI text |
| `GET` | `/api/humanizer/documents` | List indexed documents |
| `DELETE` | `/api/humanizer/document/{doc_id}` | Remove a document |
| `GET` | `/api/humanizer/stats` | Get sentence/document counts |

### POST `/api/humanizer/upload`

**Request**: `multipart/form-data` with `files` field (one or more PDFs)

**Response**:

```json
{
  "indexed": [{"doc_id": "a1b2c3d4", "filename": "textbook.pdf", "sentence_count": 847}],
  "errors": []
}
```

### POST `/api/humanizer/humanize`

**Request**:

```json
{"text": "Photosynthesis is the process by which green plants transform light energy into chemical energy."}
```

**Response**: See [Response Object Structure](#response-object-structure) above.

---

## Why This Beats Conventional AI Humanizers

```mermaid
flowchart TD
    subgraph Conventional ["❌ Conventional AI Humanizers"]
        C1["AI Text"] --> C2["LLM: 'Rewrite to sound human'"]
        C2 --> C3["Still uses LLM probability<br/>distributions = same patterns<br/>'delve', 'tapestry', 'crucial'"]
    end

    subgraph ThisSystem ["✅ This System"]
        T1["AI Text"] --> T2["Extract Facts<br/>(deterministic, no LLM)"]
        T2 --> T3["Find Real Human Structure<br/>(from actual PhD papers)"]
        T3 --> T4["Inject Facts Into<br/>Human Structure"]
        T4 --> T5["Grammar Fix Only<br/>(LLM constrained to<br/>a/an, verb agreement)"]
    end

    style C3 fill:#dc2626,color:#fff
    style T5 fill:#059669,color:#fff
```

| Approach | How It Works | Weakness |
| --- | --- | --- |
| **QuillBot / basic paraphrasers** | Synonym swapping | Shallow — same structure, different words |
| **"Humanize with AI" tools** | Ask LLM to rewrite | LLMs can only produce LLM-sounding text |
| **This system** | Force AI content into verified human structures | Requires a library of human PDFs (but that's a feature, not a bug) |

The critical difference: **the sentence structure itself** — the word order, the rhetorical flow, the subordinate clause placement — comes from a real human author, not from an LLM's probability distribution. AI detectors primarily flag structural patterns, not vocabulary. By using a human's actual structure, the output is mathematically congruent with human-written text.
