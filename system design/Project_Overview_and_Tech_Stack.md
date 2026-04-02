# Writing Tools: Project Overview & Tech Stack

Writing Tools is an advanced, full-stack application designed to aid academic and professional writing. It provides a comprehensive suite of AI-powered utilities, including intelligent citation verification, reference formatting, text humanization through semantic analysis, document conversion, and full-text document search.

The application uses an isolated domain-driven backend architecture and a modern, responsive React frontend.

---

## 🛠 Tech Stack

### Frontend
- **Framework:** React 19 via Vite
- **Styling:** TailwindCSS, standard CSS integrations (Glassmorphism aesthetics)
- **Icons:** `lucide-react`
- **PDF Handling:** `@cantoo/pdf-lib`, `react-pdf`
- **Linting:** ESLint with React standard plugins

### Backend
- **Framework:** FastAPI (Python)
- **AI/LLM Engine:** Google Gemini (via `google-genai`), orchestrated using a custom smart API Key Manager with automatic quota tracking, rate-limit handling, and auto-rotation.
- **Document Processing & OCR:**
  - `PyMuPDF` (fitz) & `PyPDF2`: PDF parsing and manipulation
  - `python-docx` & `pdf2docx`: Word & PDF interoperability
  - `pytesseract`, `pdf2image`: Scanned PDF handling and OCR
  - LibreOffice Headless (called via subprocess): Word-to-PDF conversion
- **Data & APIs:**
  - PubMed NCBI E-utilities & CrossRef REST APIs for Metadata enrichment.
  - `SQLite` (via standard Python `sqlite3`/file stores) to persist AI style palettes and phrase databases (`humanizer_index.db`, `phrasebank_index.db`, `search_index.db`).
- **NLP & Search Logic:**
  - `spaCy`: Sentence boundarization (`sentencizer`)
  - `fuzzywuzzy`, `python-Levenshtein`, `difflib`: Intelligent fuzzy string matching to verify dates, authors, and AI hallucination guardrails.

---

## 🏗 System Architecture & Core Modules

The backend (`backend/main.py`) acts as a slim entry point, wrapping a modular system where business logic is heavily decentralized into specific packages:

### 1. `citations/` & `references/` (Citation Verifier & Formatter)
This is the core academic engine responsible for reading uploaded papers and cross-checking references.
- **Regex Extraction (`extraction.py`)**: Uses massive, complex Regex blocks to extract in-text citations from academic texts representing almost all conventions (APA, Harvard, Vancouver, MLA, Numbered).
- **Verification Loop (`verification.py`)**: A deterministic Python engine that pairs extracted in-text citations with their reference list entries using author-year compound keys. It fuzzy-matches texts to locate spelling errors, irregular capitalizations, future-date anomalies, and mismatched styles.
- **Reference Parsing & Metadata (`metadata.py`)**: Connects to the CrossRef and PubMed APIs using Digital Object Identifiers (DOIs). It intelligently cascades if CrossRef fails: it tries PubMed, falls back to Regex-based PDF text extraction, and as a last resort uses a Gemini AI extraction loop shielded by verification layers.

### 2. `humanizer.py` (AI-to-Human Cognitive Synthesizer)
A sophisticated Retrieval-Augmented Style Transfer (RAST) pipeline that makes AI-generated text sound like human writing.
1. **Deconstruction:** Uses an LLM to extract the *intent*, *key variable facts*, and the *core_meaning* of a sentence.
2. **Retrieval:** Pulls human example sentences from a local database ("Skeleton Bank") based on the matching intent.
3. **Rewrite & Guardrails:** Passes the AI text and the human style examples to the LLM to rewrite the sentence, preventing hallucination by diff-checking the result's core semantic closeness to the original `core_meaning` using `difflib.SequenceMatcher` (Containment Check).

### 3. `converter/` (Document Converters)
Extensive format conversion REST APIs:
- **PDF $\leftrightarrow$ Word:** Converts PDFs to Word docs and uses LibreOffice to convert `.docx` back to PDF.
- **OCR Engine:** Handles scanned PDFs. Can detect columns and tables using geometry analysis built atop `PyMuPDF`, formatting them perfectly into a `.docx`.
- **Image handling:** Merges images to PDF, cracks PDFs into images.
- **PDF Tools:** Compresses and merges multiple PDFs.

### 4. `core/gemini.py` & `api_key_manager.py` (Resilient AI Fabric)
Implements an enterprise-grade AI connection loop:
- Maintains a pool of Google Gemini keys.
- Implements exponential backoffs.
- Tracks requests-per-minute limits. If a key returns a `429 RESOURCE_EXHAUSTED` error, it seamlessly routes the request to a backup API key mid-execution.

### 5. `phrasebank/` & `search/`
- **Phrasebank**: Local academic phrase routing logic.
- **Search**: Full-text indexing of uploaded PDFs to allow instantaneous exact-phrase checking using local datastores.

---

## 🖥 Frontend Structure

The frontend (`frontend/src/`) is built around a persistent view architecture. Views remain mounted in the background to ensure processes (like massive PDF document parsing) don't crash or lose state when the user navigates away.

- **Component Views**: `VerifierView.jsx`, `FormatterView.jsx`, `LibraryView.jsx`, `SearchView.jsx`, `HumanizerView.jsx`, `ConverterView.jsx`, etc.
- **PDFEditorPage.jsx**: An intricate GUI for displaying, annotating, and reading PDFs natively using `@cantoo/pdf-lib`.

## ⚙️ Summary
Writing Tools represents a sophisticated synthesis of classic deterministic logic (Regex, string-matching, APIs) and stochastic LLM capabilities. The architecture intentionally prevents "LLM hallucinations" by using strict Python-based cross-referencing to check AI outputs before displaying them to the user.
