# Writing Tools Project Architecture & File Tree

This document details the file structure of the **Writing Tools** project, explaining what each file does and how the different components (frontend, backend modules) are connected together.

## System Overview

The project is a client-server application consisting of:
- **Frontend (`frontend/`)**: A React (Vite) application utilizing TailwindCSS for styling. It provides various features like PDF Editing, Citation Formatting, and Document Conversion. 
- **Backend (`backend/`)**: A FastAPI Python backend. It handles complex, resource-intensive tasks like PDF manipulation (PyMuPDF), document conversion, text search, academic phrasebank management, and LLM text generation (Gemini).

The frontend sends requests to the FastAPI backend REST routes, and uses global stores or component-state to render the results.

---

## 1. Backend File Tree (`/backend`)

The backend is modularized to prevent a monolithic `main.py` entry point. Functionality is split into specific subpackages.

### Entry & Core
- `main.py`: **The main FastAPI entry point**. Defines the FastAPI application, mounts CORS middleware, and includes all domain routers (e.g., `citations_router`, `converter_router`).
- `api_key_manager.py`: Manages the tracking, rotation, or usage limits of external API keys.
- `api_key_usage.json`: Data store for tracking API key usage metrics.
- `requirements.txt`: Python package dependencies.
- **`core/`**
  - `config.py`: App configuration limits, paths, or environment loading.
  - `gemini.py`: Configuration and client setup for Google's Gemini LLM.

### Document Conversion (`converter/`)
- `pdf_edit.py`: Inline PDF editing logic via PyMuPDF. Receives pre-scaled baseline coordinates, ensures precise text alignment, handles bold/stroke text bleeding via unconditional redaction, and directly injects text into native PDF metric space.
- `font_utils.py`: Extracts and matches document fonts to keep editing consistent with original typography.

### Citations & References (`citations/` & `references/`)
Handles analyzing documents to find and format citations.
- **`citations/`**
   - `detection.py`: Detects unstructured citation texts within documents.
   - `extraction.py`: Pulls out the detailed information (author, year) from references.
   - `deduplication.py`: Removes duplicate or overlapping citations.
   - `formatting.py`: Defines citation output formats.
   - `ordering.py`: Sorts citations correctly (e.g., alphabetically).
   - `verification.py`: Verifies if extracted citations are correct and valid.
   - `routes.py`: FastAPI endpoints for the frontend to access these citation features.
- **`references/`**
   - `metadata.py`: Fetches and standardizes metadata (DOI, URL lookup).
   - `parser.py`: Parses reference strings into structured objects.
   - `matcher.py`: Matches in-text citations back to the reference list.
   - `routes.py`: Reference-specific API endpoints.
- **Root Citation Guides:** 
   - `apa_guide.py`, `harvard_guide.py`, `vancouver_guide.py`: Rule books for formatting citations strictly according to standard academic styles.

### Additional Micro-Services
- **`humanizer_routes/` / `humanizer.py` / `humanizer_store.py`**: The completely integrated "cognitive synthesizer." Connects to `humanizer_index.db` to adjust and humanize AI-generated text styles.
- **`phrasebank_routes/` / `phrasebank.py` / `phrasebank_store.py`**: Serves academic phrasing recommendations, sourcing from `phrasebank_index.db`.
- **`search/` / `search_store.py`**: Full-text searching mechanism across documents, querying `search_index.db`.
- **`utils/`**: Shared helpers.
   - `text_extraction.py`: Extracts unformatted strings from PDFs and generic documents.
   - `text_utils.py`: String cleaning, normalization, capitalization rules.
- **`pdf_routes/`**
   - `editor.py`: Specific PDF annotation / modification backend routes.

---

## 2. Frontend File Tree (`/frontend`)

The frontend organizes features primarily into modular React UI Views ("components") and state managers ("stores").

### Configuration files
- `vite.config.js`: Configuration for the Vite bundler.
- `tailwind.config.js` & `postcss.config.js`: Tailwind styling configuration and utilities.
- `package.json` / `package-lock.json`: NPM dependencies.
- `index.html`: Base HTML template where the React root is injected.

### Core React Entry (`src/`)
- `main.jsx`: Bootstraps React, mounting the `<App />` component into the DOM.
- `App.jsx`: Main routing file and application shell. Sets up the navigation to different primary routes and loads Views.
- `App.css` & `index.css`: Global styles and Tailwind base imports.

### Views & Standalone Tools (`src/components/`)
These represent the distinct 'Tools' in the application UI:
- `DashboardView.jsx`: The main landing hub summarizing activity and active tools.
- `ConverterView.jsx`: UI for converting documents (e.g. Word ↔ PDF, OCR).
- `FormatterView.jsx`: UI to enforce academic style guides on text.
- `HumanizerView.jsx`: Interacts with the backend humanizer logic to rewrite text naturally.
- `LibraryView.jsx`: Document/Asset management system interface.
- `MatcherView.jsx`: Connects to reference/citation matching logic.
- `PhrasebankView.jsx`: User interface for browsing and inserting academic phrases.
- `SearchView.jsx`: Queries the full-text search backend endpoints.
- `VerifierView.jsx`: Complex tool for auditing documents and comparing citations against references to catch errors.
- `SettingsView.jsx`: Global configuration for users.
- `Logo.jsx`: The branding component.

### The PDF Editor (`src/components/PDFEditor/`)
The interactive web-based PDF annotation system.
- `Viewer.jsx`: The main canvas that uses `react-pdf` / `pdf.js` to render PDF pages locally. Employs precise DOM-level text layer span measurement and pixel color-sampling. Uses stable `useRef` guards to manage extraction state and passes raw metric-accurate PDF points down to the backend.
- `Toolbar.jsx`: User controls for navigating and selecting annotation tools (text, redaction).
- `TextOverlay.jsx`: Renders an interactable layer on top of PDF documents so users can select textual elements.
- `InlineEditor.jsx`: Small absolute-positioned text input for user edits (replacing or adding text).
- `DraggableItem.jsx`: Handles custom user-placed free-form annotations around the canvas.

### Pages & Store (`src/pages/` & `src/stores/`)
- `pages/PDFEditorPage.jsx`: The full-page route wrapping the PDFEditor components.
- `stores/pdfEditStore.js`: Zustand or similar state management module to keep track of user pdf modifications (rectangles, text changes, deleted nodes) before they are fully finalized and sent to the backend.

### Utilities (`src/utils/`)
- `pdfCoords.js`: Very crucial math utility. Calculates the complex coordinate translations between `pdf.js` canvas space and raw PyMuPDF backend space for inserting text correctly.
- `pdfModifier.js`: Frontend helper making the HTTP fetch calls or preprocessing for pdf-related backend duties.

---

## How They Connect (Summary Flow)

1. **User Action:** A user opens the PDF Editor (`Viewer.jsx`) on the frontend.
2. **Local Render:** `Viewer.jsx` fetches a local PDF blob, rendering it via `react-pdf`. 
3. **User Interaction:** The user adds text via `InlineEditor.jsx`. The exact position, extracted font, and span width are tracked and held in `src/stores/pdfEditStore.js`. `Viewer.jsx` and `pdfCoords.js` ensure coordinates are mapped natively to standard PyMuPDF baseline metrics (top-left origin), eliminating scaling and alignment errors.
4. **API Call:** The frontend sends a request containing the precisely aligned edits payload to `backend/api/pdf/edit` (`backend/converter/pdf_edit.py`). 
5. **Backend Processing:** `pdf_edit.py` opens the PDF using PyMuPDF locally. It leverages `font_utils.py` for matching or embedding fonts. It then applies structural erasure boxes using explicit ascender/descender bounds and inserts new text exactly at the supplied baseline without needing further coordinate transformation.
6. **Delivery:** The backend spits out a modified `blob` binary response.
7. **Frontend Update:** The frontend receives the blob and updates the active `Viewer.jsx` context to show the truly flattened, completed document.
